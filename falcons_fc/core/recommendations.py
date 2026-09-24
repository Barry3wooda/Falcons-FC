import numpy as np
from core.models import CustomUser, Section, Booking, Ticket


def build_interaction_matrix():
    """
    Builds a user-section interaction matrix from booking history.
    Rows = users, Columns = sections, Values = number of bookings.
    Returns: (matrix, user_ids, section_ids)
    """
    users = list(CustomUser.objects.filter(
        tickets__status__in=['booked', 'used']
    ).distinct().order_by('id'))

    sections = list(Section.objects.all().order_by('id'))

    user_ids = [u.id for u in users]
    section_ids = [s.id for s in sections]

    user_index = {uid: i for i, uid in enumerate(user_ids)}
    section_index = {sid: i for i, sid in enumerate(section_ids)}

    matrix = np.zeros((len(users), len(sections)))

    tickets = Ticket.objects.filter(
        status__in=['booked', 'used'],
        user__isnull=False
    ).select_related('seat__row__section', 'user')

    for ticket in tickets:
        uid = ticket.user.id
        sid = ticket.seat.row.section.id
        if uid in user_index and sid in section_index:
            matrix[user_index[uid]][section_index[sid]] += 1

    return matrix, user_ids, section_ids

def cosine_similarity(vector_a, vector_b):
    """
    Computes cosine similarity between two vectors from scratch using NumPy.
    Returns a value between 0 and 1 (since our data is non-negative).
    """
    dot_product = np.dot(vector_a, vector_b)
    norm_a = np.linalg.norm(vector_a)
    norm_b = np.linalg.norm(vector_b)

    if norm_a == 0 or norm_b == 0:
        return 0.0

    similarity = dot_product / (norm_a * norm_b)
    return similarity


def compute_similarity_matrix(matrix):
    """
    Computes pairwise cosine similarity between all users in the matrix.
    Returns an NxN matrix where entry [i][j] = similarity between user i and user j.
    """
    n_users = matrix.shape[0]
    similarity_matrix = np.zeros((n_users, n_users))

    for i in range(n_users):
        for j in range(n_users):
            similarity_matrix[i][j] = cosine_similarity(matrix[i], matrix[j])

    return similarity_matrix


def get_top_neighbors(user_id, matrix, user_ids, similarity_matrix, top_n=10):
    """
    Finds the top-N most similar users to a given user, excluding themselves.
    Returns: list of (user_id, similarity_score) tuples, sorted by similarity descending.
    """
    if user_id not in user_ids:
        return []

    user_index = user_ids.index(user_id)
    similarities = similarity_matrix[user_index]

    neighbor_scores = []
    for i, other_user_id in enumerate(user_ids):
        if other_user_id == user_id:
            continue
        neighbor_scores.append((other_user_id, similarities[i]))

    neighbor_scores.sort(key=lambda x: x[1], reverse=True)

    return neighbor_scores[:top_n]


def recommend_section(user_id, matrix, user_ids, section_ids, similarity_matrix, top_n=10):
    """
    Recommends the best section for a user based on:
    - 40% their own booking history
    - 60% weighted neighbor preferences
    """
    neighbors = get_top_neighbors(user_id, matrix, user_ids, similarity_matrix, top_n)

    if not neighbors:
        return None

    n_sections = len(section_ids)
    section_scores = np.zeros(n_sections)

    # ── Own history weight (40%) ───────────────────────
    user_index = user_ids.index(user_id)
    user_vector = matrix[user_index]
    user_total = user_vector.sum()

    if user_total > 0:
        own_normalized = user_vector / user_total
        section_scores += own_normalized * 0.7

    # ── Neighbor preferences weight (60%) ──────────────
    neighbor_scores = np.zeros(n_sections)
    total_sim = 0

    for neighbor_id, sim_score in neighbors:
        if sim_score <= 0:
            continue
        neighbor_index = user_ids.index(neighbor_id)
        neighbor_vector = matrix[neighbor_index]
        neighbor_total = neighbor_vector.sum()

        if neighbor_total > 0:
            neighbor_normalized = neighbor_vector / neighbor_total
            neighbor_scores += sim_score * neighbor_normalized
            total_sim += sim_score

    if total_sim > 0:
        neighbor_scores = neighbor_scores / total_sim
        section_scores += neighbor_scores * 0.3

    if section_scores.sum() == 0:
        return None

    best_section_index = np.argmax(section_scores)
    best_section_id = section_ids[best_section_index]
    best_score = section_scores[best_section_index]

    return best_section_id, best_score


def get_popular_section(match=None):
    """
    Cold-start fallback: returns the most popular section overall,
    or for a specific match's competition type if provided.
    """
    from core.models import Section, Ticket

    tickets = Ticket.objects.filter(status__in=['booked', 'used'])

    if match:
        tickets = tickets.filter(match__competition__competition_type=match.competition.competition_type)

    if not tickets.exists():
        return Section.objects.first()

    section_counts = {}
    for ticket in tickets.select_related('seat__row__section'):
        section = ticket.seat.row.section
        section_counts[section.id] = section_counts.get(section.id, 0) + 1

    if not section_counts:
        return Section.objects.first()

    most_popular_id = max(section_counts, key=section_counts.get)
    return Section.objects.get(id=most_popular_id)


def get_recommended_section_for_user(user, match=None, top_n=10):
    """
    Main entry point: recommends a section for a user.
    Handles cold-start automatically and all error cases.
    """
    from core.models import Section
    try:
        matrix, user_ids, section_ids = build_interaction_matrix()

        if len(user_ids) == 0:
            return Section.objects.first(), 'cold_start_no_data'

        if user.id not in user_ids:
            return get_popular_section(match), 'cold_start_new_user'

        similarity_matrix = compute_similarity_matrix(matrix)
        result = recommend_section(
            user.id, matrix, user_ids, section_ids, similarity_matrix, top_n
        )

        if result is None:
            return get_popular_section(match), 'cold_start_no_signal'

        section_id, score = result
        return Section.objects.get(id=section_id), 'collaborative_filtering'

    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f'Recommendation error: {e}')
        from core.models import Section
        return Section.objects.first(), 'error_fallback'


def recommend_matches(user, top_n_neighbors=10, top_n_matches=3):
    """
    Recommends upcoming matches based on:
    - 70% the user's own competition-type preference
    - 30% weighted neighbor competition-type preferences
    Handles all error cases gracefully.
    """
    from core.models import Match, Ticket
    from django.utils import timezone
    try:
        matrix, user_ids, section_ids = build_interaction_matrix()

        upcoming_matches = Match.objects.filter(
            status='upcoming',
            date__gte=timezone.now(),
            is_away_match=False
        ).select_related('home_team', 'away_team', 'competition')

        if len(user_ids) == 0 or user.id not in user_ids:
            return list(upcoming_matches.order_by('-match_importance_score')[:top_n_matches])

        similarity_matrix = compute_similarity_matrix(matrix)
        neighbors = get_top_neighbors(
            user.id, matrix, user_ids, similarity_matrix, top_n_neighbors
        )

        # ── OWN competition preference (70%) ─────────────
        own_tickets = Ticket.objects.filter(
            user=user, status__in=['booked', 'used']
        ).select_related('match__competition')

        own_counts = {}
        for t in own_tickets:
            ct = t.match.competition.competition_type
            own_counts[ct] = own_counts.get(ct, 0) + 1

        own_total = sum(own_counts.values())
        own_scores = {k: v / own_total for k, v in own_counts.items()} if own_total > 0 else {}

        # ── Neighbor competition preference (30%), similarity-weighted ──
        neighbor_scores = {}
        if neighbors:
            neighbor_ids = [uid for uid, score in neighbors if score > 0]
            neighbor_tickets = Ticket.objects.filter(
                user_id__in=neighbor_ids, status__in=['booked', 'used']
            ).select_related('match__competition')

            raw_counts = {}
            for t in neighbor_tickets:
                ct = t.match.competition.competition_type
                raw_counts[ct] = raw_counts.get(ct, 0) + 1

            total = sum(raw_counts.values())
            neighbor_scores = {k: v / total for k, v in raw_counts.items()} if total > 0 else {}

        # ── Combine 70/30 ─────────────────────────────────
        combined = {}
        all_types = set(own_scores) | set(neighbor_scores)
        for ct in all_types:
            combined[ct] = own_scores.get(ct, 0) * 0.7 + neighbor_scores.get(ct, 0) * 0.3

        if not combined:
            return list(upcoming_matches.order_by('-match_importance_score')[:top_n_matches])

        favorite_competition_type = max(combined, key=combined.get)

        recommended = upcoming_matches.filter(
            competition__competition_type=favorite_competition_type
        ).order_by('date')[:top_n_matches]

        if not recommended.exists():
            recommended = upcoming_matches.order_by('-match_importance_score')[:top_n_matches]

        return list(recommended)

    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f'Match recommendation error: {e}')
        from core.models import Match
        from django.utils import timezone
        return list(Match.objects.filter(
            status='upcoming',
            date__gte=timezone.now(),
            is_away_match=False
        ).order_by('-match_importance_score')[:top_n_matches])