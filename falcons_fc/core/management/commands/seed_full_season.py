from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
from decimal import Decimal
from core.models import (
    CustomUser, Stadium, Section, Seat, Row,
    Team, Competition, Match, Ticket, Booking, Waitlist
)
import random


class Command(BaseCommand):
    help = 'Seeds complete realistic season data for Falcons FC'

    # ── USERS ────────────────────────────────────────────
    USERS = [
        {'username': 'barry',          'email': 'barry@test.com',     'first_name': 'Barry',     'last_name': 'Demo',      'profile': 'vip_derby'},
        # Group A — VIP + Derby fans
        {'username': 'marco_rossi',    'email': 'marco@test.com',     'first_name': 'Marco',     'last_name': 'Rossi',     'profile': 'vip_derby'},
        {'username': 'sofia_ferrari',  'email': 'sofia@test.com',     'first_name': 'Sofia',     'last_name': 'Ferrari',   'profile': 'vip_derby'},
        {'username': 'luca_bianchi',   'email': 'luca@test.com',      'first_name': 'Luca',      'last_name': 'Bianchi',   'profile': 'vip_derby'},

        # Group B — Tribune + League fans
        {'username': 'anna_greco',     'email': 'anna@test.com',      'first_name': 'Anna',      'last_name': 'Greco',     'profile': 'tribune_league'},
        {'username': 'paolo_romano',   'email': 'paolo@test.com',     'first_name': 'Paolo',     'last_name': 'Romano',    'profile': 'tribune_league'},
        {'username': 'chiara_ricci',   'email': 'chiara@test.com',    'first_name': 'Chiara',    'last_name': 'Ricci',     'profile': 'tribune_league'},

        # Group C — Cup enthusiasts
        {'username': 'matteo_conti',   'email': 'matteo@test.com',    'first_name': 'Matteo',    'last_name': 'Conti',     'profile': 'vip_cup'},
        {'username': 'giulia_marino',  'email': 'giulia@test.com',    'first_name': 'Giulia',    'last_name': 'Marino',    'profile': 'vip_cup'},

        # Group D — Curve fans / Ultras
        {'username': 'antonio_gallo',  'email': 'antonio@test.com',   'first_name': 'Antonio',   'last_name': 'Gallo',     'profile': 'curve_derby'},
        {'username': 'francesca_espo', 'email': 'francesca@test.com', 'first_name': 'Francesca', 'last_name': 'Esposito',  'profile': 'curve_derby'},

        # Group E — Mixed fans
        {'username': 'davide_russo',   'email': 'davide@test.com',    'first_name': 'Davide',    'last_name': 'Russo',     'profile': 'mixed'},
        {'username': 'valentina_mele', 'email': 'valentina@test.com', 'first_name': 'Valentina', 'last_name': 'Mele',      'profile': 'mixed'},
        {'username': 'simone_rizzo',   'email': 'simone@test.com',    'first_name': 'Simone',    'last_name': 'Rizzo',     'profile': 'mixed'},

        # Group F — New users (cold start)
        {'username': 'test_new1',      'email': 'new1@test.com',      'first_name': 'New',       'last_name': 'User1',     'profile': 'new'},
        {'username': 'test_new2',      'email': 'new2@test.com',      'first_name': 'New',       'last_name': 'User2',     'profile': 'new'},

                # Backup/extra users — same profiles, for redundancy during demo
        {'username': 'giovanni_deluca',  'email': 'giovanni@test.com',  'first_name': 'Giovanni',  'last_name': 'De Luca',   'profile': 'vip_derby'},
        {'username': 'martina_bruno',    'email': 'martina@test.com',   'first_name': 'Martina',   'last_name': 'Bruno',     'profile': 'tribune_league'},
        {'username': 'alessandro_gatti', 'email': 'alessandro@test.com','first_name': 'Alessandro','last_name': 'Gatti',     'profile': 'vip_cup'},
        {'username': 'elisa_ferro',      'email': 'elisa@test.com',     'first_name': 'Elisa',     'last_name': 'Ferro',     'profile': 'curve_derby'},
        {'username': 'riccardo_costa',   'email': 'riccardo@test.com',  'first_name': 'Riccardo',  'last_name': 'Costa',     'profile': 'mixed'},
        {'username': 'test_new3',        'email': 'new3@test.com',      'first_name': 'New',       'last_name': 'User3',     'profile': 'new'},

                {'username': 'filler1', 'email': 'filler1@test.com', 'first_name': 'Filler', 'last_name': 'One',   'profile': 'filler'},
        {'username': 'filler2', 'email': 'filler2@test.com', 'first_name': 'Filler', 'last_name': 'Two',   'profile': 'filler'},
        {'username': 'filler3', 'email': 'filler3@test.com', 'first_name': 'Filler', 'last_name': 'Three', 'profile': 'filler'},
        {'username': 'filler4', 'email': 'filler4@test.com', 'first_name': 'Filler', 'last_name': 'Four',  'profile': 'filler'},
    ]

    # Section preference per profile (section_name: weight)
    SECTION_PREFS = {
        'vip_derby':      {'VIP': 0.75, 'Tribune': 0.15, 'Curve Nord': 0.05, 'Curve Sud': 0.05},
        'tribune_league': {'VIP': 0.10, 'Tribune': 0.70, 'Curve Nord': 0.10, 'Curve Sud': 0.10},
        'vip_cup':        {'VIP': 0.65, 'Tribune': 0.25, 'Curve Nord': 0.05, 'Curve Sud': 0.05},
        'curve_derby':    {'VIP': 0.05, 'Tribune': 0.10, 'Curve Nord': 0.50, 'Curve Sud': 0.35},
        'mixed':          {'VIP': 0.25, 'Tribune': 0.25, 'Curve Nord': 0.25, 'Curve Sud': 0.25},
        'new':            {},
        'filler':         {},
    }

    # Competition preference per profile (comp_type: weight)
    COMP_PREFS = {
        'vip_derby':      {'Derby': 0.65, 'Cup': 0.20, 'League': 0.15},
        'tribune_league': {'Derby': 0.10, 'Cup': 0.15, 'League': 0.75},
        'vip_cup':        {'Derby': 0.15, 'Cup': 0.65, 'League': 0.20},
        'curve_derby':    {'Derby': 0.60, 'Cup': 0.15, 'League': 0.25},
        'mixed':          {'Derby': 0.33, 'Cup': 0.33, 'League': 0.34},
        'new':            {},
        'filler':         {},
    }

    def handle(self, *args, **kwargs):
        random.seed(42)
        now = timezone.now()
        exam_date = now + timedelta(days=6)  # July 9

        self.stdout.write(self.style.WARNING('🦅 Starting full season seed...'))

        # ── GET BASE OBJECTS ──────────────────────────────
        try:
            stadium = Stadium.objects.get(name='Falcons Arena')
            falcons = Team.objects.get(name='Falcons FC')
            serie_a = Competition.objects.get(name='Serie A')
            coppa = Competition.objects.get(name='Coppa Italia')
            derby_comp = Competition.objects.get(name='Sicily Derby')
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'❌ Missing base data: {e}'))
            self.stdout.write(self.style.ERROR('Run seed_stadium first!'))
            return

        sections = {s.name: s for s in Section.objects.filter(stadium=stadium)}
        opponents = list(Team.objects.exclude(name='Falcons FC'))
        derby_teams = [t for t in opponents if t.name in ['Palermo FC', 'Catania FC']]
        other_teams = [t for t in opponents if t.name not in ['Palermo FC', 'Catania FC']]

        # ── CREATE USERS ──────────────────────────────────
        self.stdout.write('\n📋 Creating users...')
        created_users = []
        for u in self.USERS:
            user, created = CustomUser.objects.get_or_create(
                username=u['username'],
                defaults={
                    'email': u['email'],
                    'first_name': u['first_name'],
                    'last_name': u['last_name'],
                }
            )
            if created:
                user.set_password('test1234')
                user.save()
                self.stdout.write(f'  ✅ {user.username} ({u["profile"]})')
            created_users.append((user, u['profile']))

        # ── CREATE MATCHES ────────────────────────────────
        self.stdout.write('\n📅 Creating matches...')
        home_matches = []
        away_matches = []

        # Past Serie A home matches (8) — spread over last 60 days
        past_league_opponents = other_teams[:8]
        for i, opp in enumerate(past_league_opponents):
            m = Match.objects.create(
                home_team=falcons,
                away_team=opp,
                competition=serie_a,
                stadium=stadium,
                date=now - timedelta(days=60 - i*7),
                status='finished',
                match_importance_score=1.0,
                description=f'Serie A Matchday {i+1}',
                is_away_match=False,
            )
            home_matches.append(m)
            self.stdout.write(f'  ✅ PAST HOME: {m}')

        # Past Derby home (1)
        m = Match.objects.create(
            home_team=falcons,
            away_team=derby_teams[0],
            competition=derby_comp,
            stadium=stadium,
            date=now - timedelta(days=30),
            status='finished',
            match_importance_score=3.0,
            description='Sicily Derby — First Leg',
            is_away_match=False,
        )
        home_matches.append(m)
        self.stdout.write(f'  ✅ PAST DERBY: {m}')

        # Past Cup home (2)
        for i, opp in enumerate(other_teams[8:10]):
            m = Match.objects.create(
                home_team=falcons,
                away_team=opp,
                competition=coppa,
                stadium=stadium,
                date=now - timedelta(days=45 - i*15),
                status='finished',
                match_importance_score=2.5,
                description=f'Coppa Italia Round {i+1}',
                is_away_match=False,
            )
            home_matches.append(m)
            self.stdout.write(f'  ✅ PAST CUP: {m}')

        # Upcoming Serie A home (6) — after exam date
        upcoming_league_opponents = other_teams[8:]
        for i, opp in enumerate(upcoming_league_opponents[:6]):
            m = Match.objects.create(
                home_team=falcons,
                away_team=opp,
                competition=serie_a,
                stadium=stadium,
                date=exam_date + timedelta(days=i*7 + 3),
                status='upcoming',
                match_importance_score=1.0,
                description=f'Serie A Matchday {i+9}',
                is_away_match=False,
            )
            home_matches.append(m)
            self.stdout.write(f'  ✅ UPCOMING HOME LEAGUE: {m}')

        # Upcoming Derby home (1) — July 7 (before exam, perfect for demo)
        m = Match.objects.create(
            home_team=falcons,
            away_team=derby_teams[1],
            competition=derby_comp,
            stadium=stadium,
            date=now + timedelta(days=4),  # July 7
            status='upcoming',
            match_importance_score=3.0,
            description='🔥 Sicily Derby — Revenge Match',
            is_away_match=False,
        )
        home_matches.append(m)
        self.stdout.write(f'  ✅ UPCOMING DERBY: {m}')

        # Upcoming Cup home (2)
        for i, opp in enumerate(other_teams[10:12]):
            m = Match.objects.create(
                home_team=falcons,
                away_team=opp,
                competition=coppa,
                stadium=stadium,
                date=exam_date + timedelta(days=i*14 + 10),
                status='upcoming',
                match_importance_score=2.5,
                description=f'Coppa Italia Quarter Final {i+1}',
                is_away_match=False,
            )
            home_matches.append(m)
            self.stdout.write(f'  ✅ UPCOMING CUP: {m}')

        # Away matches for all 14 opponents
        AWAY_URLS = {
            'Palermo FC':    ('https://www.palermofc.com/en/tickets', 'Renzo Barbera Stadium', 'Palermo', 36349),
            'Catania FC':    ('https://cataniafc.ticketone.it/catalog', 'Angelo Massimino Stadium', 'Catania', 20266),
            'Roma FC':       ('https://www.asroma.com/en/tickets', 'Stadio Olimpico', 'Rome', 70634),
            'Milano FC':     ('https://booking.acmilan.com/en/', 'San Siro Stadium', 'Milan', 75817),
            'Napoli FC':     ('https://www.sscnapoli.it/en/tickets', 'Diego Armando Maradona Stadium', 'Naples', 54726),
            'Juventus FC':   ('https://www.juventus.com/en/tickets/', 'Allianz Stadium', 'Turin', 41507),
            'Lazio FC':      ('https://www.sslazio.it/en/tickets', 'Stadio Olimpico', 'Rome', 70634),
            'Atalanta FC':   ('https://en.atalanta.it/ticket', 'Gewiss Stadium', 'Bergamo', 24747),
            'Fiorentina FC': ('https://www.acffiorentina.com/en/tickets', 'Stadio Artemio Franchi', 'Florence', 43147),
            'Torino FC':     ('https://www.torinofc.it/en/biglietti', 'Stadio Olimpico Grande Torino', 'Turin', 28177),
            'Bologna FC':    ('https://www.bolognacalcio.it/en/tickets', "Stadio Renato Dall'Ara", 'Bologna', 38279),
            'Verona FC':     ('https://www.hellasverona.it/en/tickets', 'Stadio Marc Antonio Bentegodi', 'Verona', 39211),
            'Genoa FC':      ('https://www.genoafc.it/en/tickets', 'Stadio Luigi Ferraris', 'Genoa', 36685),
            'Udinese FC':    ('https://www.udinese.it/en/tickets', 'Dacia Arena', 'Udine', 25165),
        }

        all_opponents = derby_teams + other_teams
        for i, opp in enumerate(all_opponents):
            if opp.name in AWAY_URLS:
                url, stad_name, stad_city, capacity = AWAY_URLS[opp.name]
                away_stad, _ = Stadium.objects.get_or_create(
                    name=stad_name,
                    defaults={'city': stad_city, 'capacity': capacity}
                )
                comp = derby_comp if opp in derby_teams else serie_a
                importance = 3.0 if opp in derby_teams else 1.0
                days_offset = -50 + i * 7 if i < 7 else i * 7
                status = 'finished' if days_offset < 0 else 'upcoming'
                m = Match.objects.create(
                    home_team=opp,
                    away_team=falcons,
                    competition=comp,
                    stadium=away_stad,
                    date=now + timedelta(days=days_offset),
                    status=status,
                    match_importance_score=importance,
                    description=f'Away at {stad_city}',
                    is_away_match=True,
                    external_ticket_url=url,
                )
                away_matches.append(m)
                self.stdout.write(f'  ✅ AWAY: {m} ({status})')

        # ── CREATE BOOKINGS ───────────────────────────────
        self.stdout.write('\n🎟️  Creating realistic bookings...')

        # Only book on finished/past matches for history
        past_home = [m for m in home_matches if m.status == 'finished']
        upcoming_home = [m for m in home_matches if m.status == 'upcoming']
        booking_count = 0

        for user, profile in created_users:
            if profile in ('new', 'filler'):
                 continue
            section_prefs = self.SECTION_PREFS[profile]
            comp_prefs = self.COMP_PREFS[profile]

            # Each user books 5-10 past matches
            num_bookings = random.randint(5, 10)

            for _ in range(num_bookings):
                # Pick competition type
                comp_type = random.choices(
                    list(comp_prefs.keys()),
                    weights=list(comp_prefs.values())
                )[0]

                # Find matching past matches
                eligible = [
                    m for m in past_home
                    if m.competition.competition_type == comp_type
                ]
                if not eligible:
                    eligible = past_home
                if not eligible:
                    continue

                match = random.choice(eligible)

                # Pick section
                section_name = random.choices(
                    list(section_prefs.keys()),
                    weights=list(section_prefs.values())
                )[0]
                section = sections[section_name]

                # Find available seat
                taken_ids = set(
                    Ticket.objects.filter(
                        match=match,
                        status__in=['booked', 'used'],
                        seat__row__section=section
                    ).values_list('seat_id', flat=True)
                )

                available = Seat.objects.filter(
                    row__section=section,
                    is_active=True
                ).exclude(id__in=taken_ids)

                if not available.exists():
                    continue

                seat = random.choice(list(available))
                price = float(section.base_price) * random.uniform(1.0, 1.4)
                price = round(price, 2)

                ticket = Ticket.objects.create(
                    seat=seat,
                    match=match,
                    user=user,
                    status='used' if match.status == 'finished' else 'booked',
                    final_price=Decimal(str(price)),
                    holder_name=f'{user.first_name} {user.last_name}',
                )

                booking = Booking.objects.create(
                    user=user,
                    match=match,
                    total_price=Decimal(str(price)),
                    payment_status='paid',
                    stripe_payment_intent=f'pi_seed_{ticket.id}',
                )
                booking.tickets.add(ticket)
                booking_count += 1

        # ── PARTIAL OCCUPANCY ON UPCOMING MATCHES ─────────
        self.stdout.write('\n📊 Adding partial occupancy to upcoming matches...')

        # Derby match (July 7) — make it 60% full to show high ML pricing
        derby_upcoming = [m for m in home_matches if m.status == 'upcoming' and m.competition.competition_type == 'Derby']
        if derby_upcoming:
            derby = derby_upcoming[0]
            vip = sections['VIP']
            tribune = sections['Tribune']

            # Book 70% of VIP seats
            vip_seats = list(Seat.objects.filter(
                row__section=vip, is_active=True
            ).order_by('?')[:35])

            barry = CustomUser.objects.get(username='barry')
            for seat in vip_seats:
                t = Ticket.objects.create(
                    seat=seat, match=derby, user=barry,
                    status='booked',
                    final_price=Decimal('200.00'),
                )
                b = Booking.objects.create(
                    user=barry, match=derby,
                    total_price=Decimal('200.00'),
                    payment_status='paid',
                    stripe_payment_intent=f'pi_derby_{t.id}',
                )
                b.tickets.add(t)
                booking_count += 1

            # Book 50% of Tribune
            trib_seats = list(Seat.objects.filter(
                row__section=tribune, is_active=True
            ).order_by('?')[:60])

            for seat in trib_seats:
                user = random.choice([u for u, p in created_users if p == 'filler'])
                t = Ticket.objects.create(
                    seat=seat, match=derby, user=user,
                    status='booked',
                    final_price=Decimal('110.00'),
                )
                b = Booking.objects.create(
                    user=user, match=derby,
                    total_price=Decimal('110.00'),
                    payment_status='paid',
                    stripe_payment_intent=f'pi_derby_t_{t.id}',
                )
                b.tickets.add(t)
                booking_count += 1

            self.stdout.write(f'  ✅ Derby match: VIP 70% full, Tribune 50% full')

        # First upcoming League match — 20% full
        upcoming_league = [m for m in home_matches if m.status == 'upcoming' and m.competition.competition_type == 'League']
        if upcoming_league:
            league = upcoming_league[0]
            trib = sections['Tribune']
            trib_seats = list(Seat.objects.filter(
                row__section=trib, is_active=True
            ).order_by('?')[:24])

            for seat in trib_seats:
                user = random.choice([u for u, p in created_users if p == 'filler'])
                t = Ticket.objects.create(
                    seat=seat, match=league, user=user,
                    status='booked',
                    final_price=Decimal('85.00'),
                )
                b = Booking.objects.create(
                    user=user, match=league,
                    total_price=Decimal('85.00'),
                    payment_status='paid',
                    stripe_payment_intent=f'pi_league_{t.id}',
                )
                b.tickets.add(t)
                booking_count += 1

            self.stdout.write(f'  ✅ League match: Tribune 20% full')

        # ── SUMMARY ───────────────────────────────────────
        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS('═' * 60))
        self.stdout.write(self.style.SUCCESS('🦅  FULL SEASON SEEDED SUCCESSFULLY'))
        self.stdout.write(self.style.SUCCESS('═' * 60))
        self.stdout.write(f'   Users created        : {CustomUser.objects.filter(is_superuser=False).count()}')
        self.stdout.write(f'   Home matches         : {Match.objects.filter(is_away_match=False).count()}')
        self.stdout.write(f'   Away matches         : {Match.objects.filter(is_away_match=True).count()}')
        self.stdout.write(f'   Past matches         : {Match.objects.filter(status="finished").count()}')
        self.stdout.write(f'   Upcoming matches     : {Match.objects.filter(status="upcoming").count()}')
        self.stdout.write(f'   Total bookings       : {Booking.objects.count()}')
        self.stdout.write(f'   Total tickets        : {Ticket.objects.count()}')
        self.stdout.write(self.style.SUCCESS('═' * 60))
        self.stdout.write('')
        self.stdout.write('👥 Test users (password: test1234):')
        for u, p in created_users:
            self.stdout.write(f'   {u.username:<20} → {p}')
        self.stdout.write(self.style.SUCCESS('═' * 60))