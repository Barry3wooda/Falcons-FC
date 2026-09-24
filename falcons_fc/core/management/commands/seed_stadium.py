from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
from core.models import (
    Stadium, Section, Row, Seat,
    Competition, Team, Match
)


class Command(BaseCommand):
    help = 'Seeds the database with stadium, seats, teams, competitions and matches'

    SECTIONS = [
        {'name': 'VIP',        'base_price': 150.00, 'rows': 5,  'seats_per_row': 10},
        {'name': 'Tribune',    'base_price': 80.00,  'rows': 8,  'seats_per_row': 15},
        {'name': 'Curve Nord', 'base_price': 40.00,  'rows': 6,  'seats_per_row': 12},
        {'name': 'Curve Sud',  'base_price': 40.00,  'rows': 6,  'seats_per_row': 12},
    ]

    def handle(self, *args, **kwargs):
        self.stdout.write(self.style.WARNING('🦅 Starting Falcons FC seeder...'))

        # ── STADIUM ──────────────────────────────────────
        stadium, created = Stadium.objects.get_or_create(
            name='Falcons Arena',
            defaults={'city': 'Messina', 'capacity': 314}
        )
        if created:
            self.stdout.write(self.style.SUCCESS('✅ Stadium created: Falcons Arena'))
        else:
            self.stdout.write('ℹ️  Stadium already exists, skipping.')

        # ── SECTIONS → ROWS → SEATS ───────────────────────
        total_seats = 0
        for section_data in self.SECTIONS:
            section, s_created = Section.objects.get_or_create(
                stadium=stadium,
                name=section_data['name'],
                defaults={
                    'base_price': section_data['base_price'],
                    'description': f"{section_data['name']} section of Falcons Arena"
                }
            )
            if not s_created:
                self.stdout.write(f"ℹ️  Section {section_data['name']} already exists, skipping.")
                continue

            for row_num in range(1, section_data['rows'] + 1):
                row = Row.objects.create(
                    section=section,
                    row_number=row_num
                )
                for seat_num in range(1, section_data['seats_per_row'] + 1):
                    Seat.objects.create(
                        row=row,
                        seat_number=seat_num,
                        is_active=True
                    )
                    total_seats += 1

            self.stdout.write(self.style.SUCCESS(
                f'✅ Section {section_data["name"]}: '
                f'{section_data["rows"]} rows × '
                f'{section_data["seats_per_row"]} seats = '
                f'{section_data["rows"] * section_data["seats_per_row"]} seats'
            ))

        if total_seats > 0:
            self.stdout.write(self.style.SUCCESS(f'✅ Total seats created: {total_seats}'))

        # ── COMPETITIONS ──────────────────────────────────
        league, _ = Competition.objects.get_or_create(
            name='Serie A',
            defaults={'competition_type': 'League'}
        )
        cup, _ = Competition.objects.get_or_create(
            name='Coppa Italia',
            defaults={'competition_type': 'Cup'}
        )
        derby_comp, _ = Competition.objects.get_or_create(
            name='Sicily Derby',
            defaults={'competition_type': 'Derby'}
        )
        self.stdout.write(self.style.SUCCESS('✅ Competitions created/verified'))

        # ── TEAMS (15 total) ──────────────────────────────
        falcons, _ = Team.objects.get_or_create(
            name='Falcons FC',
            defaults={'city': 'Messina'}
        )

        rivals_data = [
            ('Palermo FC',      'Palermo'),
            ('Catania FC',      'Catania'),
            ('Roma FC',         'Rome'),
            ('Milano FC',       'Milan'),
            ('Napoli FC',       'Naples'),
            ('Juventus FC',     'Turin'),
            ('Lazio FC',        'Rome'),
            ('Atalanta FC',     'Bergamo'),
            ('Fiorentina FC',   'Florence'),
            ('Torino FC',       'Turin'),
            ('Bologna FC',      'Bologna'),
            ('Verona FC',       'Verona'),
            ('Genoa FC',        'Genoa'),
            ('Udinese FC',      'Udine'),
        ]

        teams = {}
        for team_name, city in rivals_data:
            team, _ = Team.objects.get_or_create(
                name=team_name,
                defaults={'city': city}
            )
            teams[team_name] = team

        self.stdout.write(self.style.SUCCESS(f'✅ {Team.objects.count()} teams created/verified'))

        # ── MATCHES (10 total) ────────────────────────────
        now = timezone.now()
        matches_data = [
            # Derby matches — highest importance (3) — high demand pricing
            {
                'home': falcons,
                'away': teams['Palermo FC'],
                'competition': derby_comp,
                'days': 5,
                'desc': '🔥 The big Sicily Derby — city rivals clash!'
            },
            {
                'home': falcons,
                'away': teams['Catania FC'],
                'competition': derby_comp,
                'days': 40,
                'desc': '🔥 Sicily Derby — revenge match!'
            },
            # Cup matches — importance (2.5) — medium demand
            {
                'home': falcons,
                'away': teams['Roma FC'],
                'competition': cup,
                'days': 12,
                'desc': 'Coppa Italia Round of 16'
            },
            {
                'home': falcons,
                'away': teams['Juventus FC'],
                'competition': cup,
                'days': 26,
                'desc': 'Coppa Italia Quarter Final'
            },
            {
                'home': falcons,
                'away': teams['Napoli FC'],
                'competition': cup,
                'days': 54,
                'desc': 'Coppa Italia Semi Final'
            },
            # League matches — importance (1) — normal demand
            {
                'home': falcons,
                'away': teams['Milano FC'],
                'competition': league,
                'days': 19,
                'desc': 'Serie A Matchday 22'
            },
            {
                'home': falcons,
                'away': teams['Lazio FC'],
                'competition': league,
                'days': 33,
                'desc': 'Serie A Matchday 24'
            },
            {
                'home': falcons,
                'away': teams['Atalanta FC'],
                'competition': league,
                'days': 47,
                'desc': 'Serie A Matchday 26'
            },
            {
                'home': falcons,
                'away': teams['Fiorentina FC'],
                'competition': league,
                'days': 61,
                'desc': 'Serie A Matchday 28'
            },
            {
                'home': falcons,
                'away': teams['Bologna FC'],
                'competition': league,
                'days': 75,
                'desc': 'Serie A Matchday 30'
            },
        ]

        matches_created = 0
        for m in matches_data:
            match, created = Match.objects.get_or_create(
                home_team=m['home'],
                away_team=m['away'],
                competition=m['competition'],
                defaults={
                    'stadium': stadium,
                    'date': now + timedelta(days=m['days']),
                    'status': 'upcoming',
                    'description': m['desc'],
                }
            )
            if created:
                matches_created += 1
                self.stdout.write(self.style.SUCCESS(f'✅ Match: {match}'))
            else:
                self.stdout.write(f'ℹ️  Match already exists: {match}')

        # ── SUMMARY ───────────────────────────────────────
        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS('═' * 55))
        self.stdout.write(self.style.SUCCESS('🦅  FALCONS FC DATABASE SEEDED SUCCESSFULLY'))
        self.stdout.write(self.style.SUCCESS('═' * 55))
        self.stdout.write(f'   Stadium     : {stadium.name}, {stadium.city}')
        self.stdout.write(f'   Sections    : {Section.objects.filter(stadium=stadium).count()}')
        self.stdout.write(f'   Rows        : {Row.objects.filter(section__stadium=stadium).count()}')
        self.stdout.write(f'   Seats       : {Seat.objects.filter(row__section__stadium=stadium).count()}')
        self.stdout.write(f'   Teams       : {Team.objects.count()}')
        self.stdout.write(f'   Competitions: {Competition.objects.count()}')
        self.stdout.write(f'   Matches     : {Match.objects.count()}')
        self.stdout.write(self.style.SUCCESS('═' * 55))