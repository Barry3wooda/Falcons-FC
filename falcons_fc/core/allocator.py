from core.models import Row, Seat, Ticket, Section, Match


def get_available_seats_per_row(match, section):
    """
    Returns a dict: {row_number: [list of available seat objects in order]}
    Only includes seats that are truly available for this match.
    """
    taken_ids = set(
        Ticket.objects.filter(
            match=match,
            status__in=['locked', 'booked', 'used'],
            seat__row__section=section
        ).values_list('seat_id', flat=True)
    )

    rows = Row.objects.filter(section=section).prefetch_related('seats').order_by('row_number')
    result = {}

    for row in rows:
        available = [
            seat for seat in row.seats.order_by('seat_number')
            if seat.id not in taken_ids and seat.is_active
        ]
        if available:
            result[row.row_number] = available

    return result


def find_contiguous_blocks(available_seats_per_row, block_size):
    """
    Sliding window scan: finds ALL contiguous blocks of exactly block_size
    available seats across all rows.
    Returns list of blocks: each block is a list of Seat objects.
    """
    blocks = []

    for row_number, seats in available_seats_per_row.items():
        if len(seats) < block_size:
            continue

        # Sliding window across the row
        for start in range(len(seats) - block_size + 1):
            window = seats[start:start + block_size]

            # Verify the window is truly contiguous (no gaps in seat numbers)
            seat_numbers = [s.seat_number for s in window]
            is_contiguous = all(
                seat_numbers[i+1] - seat_numbers[i] == 1
                for i in range(len(seat_numbers) - 1)
            )

            if is_contiguous:
                blocks.append({
                    'seats': window,
                    'row_number': row_number,
                    'start_seat': seat_numbers[0],
                    'end_seat': seat_numbers[-1],
                    'size': block_size,
                })

    return blocks

def score_block(block, total_rows):
    """
    Scores a candidate block on three criteria:
    1. Centrality score — center of row = better sightlines
    2. Orphan penalty — avoid leaving single isolated seats
    3. Row proximity — closer to pitch (lower row number) = better
    Returns: float score (higher = better)
    """
    seats = block['seats']
    row_number = block['row_number']

    # Get all seats in this row to calculate row width
    row = seats[0].row
    all_row_seats = list(row.seats.filter(is_active=True).order_by('seat_number'))
    row_width = len(all_row_seats)

    if row_width == 0:
        return 0

    # ── Criterion 1: Centrality score ─────────────────────
    # Block center position relative to row center
    block_center = (block['start_seat'] + block['end_seat']) / 2
    row_center = (all_row_seats[0].seat_number + all_row_seats[-1].seat_number) / 2
    max_distance = row_width / 2
    distance_from_center = abs(block_center - row_center)
    centrality_score = 1 - (distance_from_center / max_distance) if max_distance > 0 else 1

    # ── Criterion 2: Orphan penalty ────────────────────────
    # Penalise if block leaves exactly 1 seat isolated at either end
    seat_numbers_in_block = set(s.seat_number for s in seats)
    all_seat_numbers = set(s.seat_number for s in all_row_seats)
    remaining = sorted(all_seat_numbers - seat_numbers_in_block)

    orphan_penalty = 0
    if remaining:
        # Check left side: is seat before block isolated?
        left_side = [s for s in remaining if s < block['start_seat']]
        right_side = [s for s in remaining if s > block['end_seat']]

        if len(left_side) == 1:
            orphan_penalty += 0.3
        if len(right_side) == 1:
            orphan_penalty += 0.3

    # ── Criterion 3: Row proximity ─────────────────────────
    # Lower row number = closer to pitch = better
    # Row 1 gets score 1.0, last row gets score approaching 0
    row_proximity_score = 1 - ((row_number - 1) / total_rows)

    # ── Final weighted score ───────────────────────────────
    final_score = (
        centrality_score * 0.5 +
        row_proximity_score * 0.3 -
        orphan_penalty * 0.2
    )

    return round(final_score, 4)

def find_all_contiguous_blocks(available_seats_per_row):
    """
    Finds ALL contiguous sub-blocks of any size across all rows.
    Used by the splitting algorithm when no perfect block exists.
    Returns: list of blocks sorted by size descending.
    """
    all_blocks = []

    for row_number, seats in available_seats_per_row.items():
        if not seats:
            continue

        current_block = [seats[0]]

        for i in range(1, len(seats)):
            prev_seat = seats[i-1]
            curr_seat = seats[i]

            if curr_seat.seat_number - prev_seat.seat_number == 1:
                current_block.append(curr_seat)
            else:
                if current_block:
                    all_blocks.append({
                        'seats': current_block,
                        'row_number': row_number,
                        'start_seat': current_block[0].seat_number,
                        'end_seat': current_block[-1].seat_number,
                        'size': len(current_block),
                    })
                current_block = [curr_seat]

        if current_block:
            all_blocks.append({
                'seats': current_block,
                'row_number': row_number,
                'start_seat': current_block[0].seat_number,
                'end_seat': current_block[-1].seat_number,
                'size': len(current_block),
            })

    all_blocks.sort(key=lambda b: b['size'], reverse=True)
    return all_blocks


def split_allocation(available_seats_per_row, n_seats, total_rows=1, min_group_size=2):
    """
    Splitting algorithm: partitions N seats into sub-groups
    that together equal N seats total.
    - No group smaller than min_group_size
    - Uses minimum number of rows needed
    - Balances seats evenly across those rows
    """
    all_blocks = find_all_contiguous_blocks(available_seats_per_row)

    total_available = sum(b['size'] for b in all_blocks)
    if total_available < n_seats:
        return None

    rows_with_seats = list(available_seats_per_row.keys())

    # ── STRATEGY 1: Find minimum rows needed ──────────────
    # Sort rows by capacity descending
    # Use fewest rows possible to fit N seats
    rows_by_capacity = sorted(
        rows_with_seats,
        key=lambda r: len(available_seats_per_row[r]),
        reverse=True
    )

    # Find minimum number of rows needed
    cumulative = 0
    min_rows_needed = 0
    for row in rows_by_capacity:
        cumulative += len(available_seats_per_row[row])
        min_rows_needed += 1
        if cumulative >= n_seats:
            break

    # Use only the rows we need
    selected_rows = rows_by_capacity[:min_rows_needed]
    selected_rows.sort()  # Sort by row number (low to high)

    # Try balanced split across minimum rows
    seats_per_row = n_seats // min_rows_needed
    remainder = n_seats % min_rows_needed

    balanced_groups = []
    remaining_needed = n_seats
    success = True

    for i, row_number in enumerate(selected_rows):
        if remaining_needed <= 0:
            break

        # Give extra seat to first rows if remainder
        target = seats_per_row + (1 if i < remainder else 0)

        # Must be at least min_group_size
        if target < min_group_size:
            success = False
            break

        # Find contiguous block of target size in this row
        # Find best scoring contiguous block
        # of target size in this row
        row_seats = available_seats_per_row[row_number]

        # Collect all valid windows
        candidate_blocks = []
        for start in range(len(row_seats) - target + 1):
            window = row_seats[start:start + target]
            seat_numbers = [s.seat_number for s in window]
            is_contiguous = all(
                seat_numbers[j+1] - seat_numbers[j] == 1
                for j in range(len(seat_numbers) - 1)
            )
            if is_contiguous:
                candidate_blocks.append({
                    'seats': window,
                    'row_number': row_number,
                    'start_seat': seat_numbers[0],
                    'end_seat': seat_numbers[-1],
                    'size': target,
                })

        block_found = False
        if candidate_blocks:
            # Score each candidate and pick best
            best_block = None
            best_score = -999

            for block in candidate_blocks:
                score = score_block(
                    block, total_rows
                )
                if score > best_score:
                    best_score = score
                    best_block = block

            balanced_groups.append(best_block)
            remaining_needed -= target
            block_found = True

        if not block_found:
            success = False
            break

    # Balanced split worked
    if success and remaining_needed == 0:
        all_valid = all(
            g['size'] >= min_group_size
            for g in balanced_groups
        )
        if all_valid:
            return balanced_groups

    # ── STRATEGY 2: Greedy with minimum group size ─────────
    selected_groups = []
    remaining_needed = n_seats

    for block in all_blocks:
        if remaining_needed <= 0:
            break

        if block['size'] <= remaining_needed:
            leftover = remaining_needed - block['size']

            if leftover == 0:
                selected_groups.append(block)
                remaining_needed = 0

            elif leftover >= min_group_size:
                selected_groups.append(block)
                remaining_needed -= block['size']

            else:
                # Taking this block leaves orphan group
                # Trim current block to avoid it
                trimmed_size = block['size'] - (min_group_size - leftover)
                if trimmed_size >= min_group_size:
                    trimmed_seats = block['seats'][:trimmed_size]
                    selected_groups.append({
                        'seats': trimmed_seats,
                        'row_number': block['row_number'],
                        'start_seat': trimmed_seats[0].seat_number,
                        'end_seat': trimmed_seats[-1].seat_number,
                        'size': trimmed_size,
                    })
                    remaining_needed -= trimmed_size
                else:
                    continue

        else:
            # Block larger than needed — trim it
            trimmed_seats = block['seats'][:remaining_needed]
            if len(trimmed_seats) >= min_group_size:
                selected_groups.append({
                    'seats': trimmed_seats,
                    'row_number': block['row_number'],
                    'start_seat': trimmed_seats[0].seat_number,
                    'end_seat': trimmed_seats[-1].seat_number,
                    'size': len(trimmed_seats),
                })
                remaining_needed = 0
            else:
                continue

    if remaining_needed > 0:
        return None

    return selected_groups

MAX_GROUP_SIZE = 10 

def allocate_group_seats(match, section, n_seats):
    """
    Main entry point for the Smart Group Seat Allocator.

    Returns a dict with:
    - 'type': 'perfect' or 'split' or 'impossible'
    - 'groups': list of seat groups
    - 'total_seats': total seats allocated
    - 'message': human-readable explanation
    """
    if n_seats < 2:
        return {
            'type': 'error',
            'groups': [],
            'total_seats': 0,
            'message': 'Group booking requires at least 2 seats.'
        }
    if n_seats > MAX_GROUP_SIZE:
        return {
            'type': 'error',
            'groups': [],
            'total_seats': 0,
            'message': f'Group bookings are limited to {MAX_GROUP_SIZE} seats. Please contact the club directly for larger groups.'
        }

    available_seats_per_row = get_available_seats_per_row(match, section)
    total_rows = Row.objects.filter(section=section).count()
    total_available = sum(len(seats) for seats in available_seats_per_row.values())

    if total_available < n_seats:
        return {
            'type': 'impossible',
            'groups': [],
            'total_seats': 0,
            'message': f'Not enough seats available. Only {total_available} seats remaining in {section.name}.'
        }

    # ── STEP 1: Try to find a perfect contiguous block ────
    blocks = find_contiguous_blocks(available_seats_per_row, n_seats)

    if blocks:
        # Score all candidate blocks
        scored_blocks = []
        for block in blocks:
            score = score_block(block, total_rows)
            scored_blocks.append((block, score))

        # Pick the best scoring block
        scored_blocks.sort(key=lambda x: x[1], reverse=True)
        best_block, best_score = scored_blocks[0]

        return {
            'type': 'perfect',
            'groups': [best_block],
            'total_seats': n_seats,
            'score': best_score,
            'message': f'Found {n_seats} seats together in Row {best_block["row_number"]}, '
                      f'Seats {best_block["start_seat"]}–{best_block["end_seat"]}.'
        }

    # ── STEP 2: No perfect block — use splitting algorithm ─
    groups = split_allocation(
    available_seats_per_row,
    n_seats,
    total_rows=total_rows
)

    if not groups:
        return {
            'type': 'impossible',
            'groups': [],
            'total_seats': 0,
            'message': f'Unable to allocate {n_seats} seats in {section.name}.'
        }

    total_allocated = sum(g['size'] for g in groups)
    group_descriptions = [
        f'Row {g["row_number"]} Seats {g["start_seat"]}–{g["end_seat"]}'
        for g in groups
    ]

    return {
        'type': 'split',
        'groups': groups,
        'total_seats': total_allocated,
        'n_groups': len(groups),
        'message': f'No single block of {n_seats} seats available. '
                  f'Best split: {len(groups)} groups — {", ".join(group_descriptions)}.'
    }