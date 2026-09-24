from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
from core.models import Match, Team, Competition, Stadium


class Command(BaseCommand):
    help = 'Seeds away match fixtures with real external ticket links'

    AWAY_MATCHES = [
        # ── SICILY RIVALS ─────────────────────────────
        {
            'opponent': 'Palermo FC',
            'competition': 'Sicily Derby',
            'days': 15,
            'description': '🔥 Away Derby at Renzo Barbera — Palermo',
            'external_url': 'https://www.palermofc.com/en/tickets',
            'stadium_name': 'Renzo Barbera Stadium',
            'stadium_city': 'Palermo',
            'stadium_capacity': 36349,
        },
        {
            'opponent': 'Catania FC',
            'competition': 'Serie A',
            'days': 28,
            'description': '⚽ Away League match at Angelo Massimino — Catania',
            'external_url': 'https://cataniafc.ticketone.it/catalog',
            'stadium_name': 'Angelo Massimino Stadium',
            'stadium_city': 'Catania',
            'stadium_capacity': 20266,
        },
        # ── BIG CLUBS ─────────────────────────────────
        {
            'opponent': 'Roma FC',
            'competition': 'Coppa Italia',
            'days': 38,
            'description': '🏆 Away Cup match at Stadio Olimpico — Rome',
            'external_url': 'https://www.asroma.com/en/tickets',
            'stadium_name': 'Stadio Olimpico',
            'stadium_city': 'Rome',
            'stadium_capacity': 70634,
        },
        {
            'opponent': 'Milano FC',
            'competition': 'Serie A',
            'days': 48,
            'description': '⚽ Away League match at San Siro — Milan',
            'external_url': 'https://booking.acmilan.com/en/',
            'stadium_name': 'San Siro Stadium',
            'stadium_city': 'Milan',
            'stadium_capacity': 75817,
        },
        {
            'opponent': 'Napoli FC',
            'competition': 'Serie A',
            'days': 58,
            'description': '⚽ Away League match at Diego Armando Maradona — Naples',
            'external_url': 'https://www.sscnapoli.it/en/tickets',
            'stadium_name': 'Diego Armando Maradona Stadium',
            'stadium_city': 'Naples',
            'stadium_capacity': 54726,
        },
        {
            'opponent': 'Juventus FC',
            'competition': 'Coppa Italia',
            'days': 68,
            'description': '🏆 Away Cup match at Allianz Stadium — Turin',
            'external_url': 'https://www.juventus.com/en/tickets/',
            'stadium_name': 'Allianz Stadium',
            'stadium_city': 'Turin',
            'stadium_capacity': 41507,
        },
        {
            'opponent': 'Lazio FC',
            'competition': 'Serie A',
            'days': 78,
            'description': '⚽ Away League match at Stadio Olimpico — Rome',
            'external_url': 'https://www.sslazio.it/en/tickets',
            'stadium_name': 'Stadio Olimpico',
            'stadium_city': 'Rome',
            'stadium_capacity': 70634,
        },
        {
            'opponent': 'Atalanta FC',
            'competition': 'Serie A',
            'days': 88,
            'description': '⚽ Away League match at Gewiss Stadium — Bergamo',
            'external_url': 'https://en.atalanta.it/ticket',
            'stadium_name': 'Gewiss Stadium',
            'stadium_city': 'Bergamo',
            'stadium_capacity': 24747,
        },
        {
            'opponent': 'Fiorentina FC',
            'competition': 'Serie A',
            'days': 98,
            'description': '⚽ Away League match at Stadio Artemio Franchi — Florence',
            'external_url': 'https://www.acffiorentina.com/en/tickets',
            'stadium_name': 'Stadio Artemio Franchi',
            'stadium_city': 'Florence',
            'stadium_capacity': 43147,
        },
        {
            'opponent': 'Torino FC',
            'competition': 'Serie A',
            'days': 108,
            'description': '⚽ Away League match at Stadio Olimpico Grande Torino',
            'external_url': 'https://www.torinofc.it/en/biglietti',
            'stadium_name': 'Stadio Olimpico Grande Torino',
            'stadium_city': 'Turin',
            'stadium_capacity': 28177,
        },
        {
            'opponent': 'Bologna FC',
            'competition': 'Serie A',
            'days': 118,
            'description': '⚽ Away League match at Stadio Renato Dall Ara — Bologna',
            'external_url': 'https://www.bolognacalcio.it/en/tickets',
            'stadium_name': "Stadio Renato Dall'Ara",
            'stadium_city': 'Bologna',
            'stadium_capacity': 38279,
        },
        {
            'opponent': 'Verona FC',
            'competition': 'Serie A',
            'days': 128,
            'description': '⚽ Away League match at Stadio Marc Antonio Bentegodi — Verona',
            'external_url': 'https://www.hellasverona.it/en/tickets',
            'stadium_name': 'Stadio Marc Antonio Bentegodi',
            'stadium_city': 'Verona',
            'stadium_capacity': 39211,
        },
        {
            'opponent': 'Genoa FC',
            'competition': 'Serie A',
            'days': 138,
            'description': '⚽ Away League match at Stadio Luigi Ferraris — Genoa',
            'external_url': 'https://www.genoafc.it/en/tickets',
            'stadium_name': 'Stadio Luigi Ferraris',
            'stadium_city': 'Genoa',
            'stadium_capacity': 36685,
        },
        {
            'opponent': 'Udinese FC',
            'competition': 'Serie A',
            'days': 148,
            'description': '⚽ Away League match at Dacia Arena — Udine',
            'external_url': 'https://www.udinese.it/en/tickets',
            'stadium_name': 'Dacia Arena',
            'stadium_city': 'Udine',
            'stadium_capacity': 25165,
        },
    ]

    def handle(self, *args, **kwargs):
        self.stdout.write(self.style.WARNING('🦅 Seeding away matches...'))

        falcons = Team.objects.get(name='Falcons FC')
        now = timezone.now()
        created_count = 0

        for match_data in self.AWAY_MATCHES:
            try:
                opponent = Team.objects.get(name=match_data['opponent'])
                competition = Competition.objects.get(
                    name__icontains=match_data['competition'].replace(' FC', '')
                )

                stadium, _ = Stadium.objects.get_or_create(
                    name=match_data['stadium_name'],
                    defaults={
                        'city': match_data['stadium_city'],
                        'capacity': match_data['stadium_capacity']
                    }
                )

                match, created = Match.objects.get_or_create(
                    home_team=opponent,
                    away_team=falcons,
                    competition=competition,
                    defaults={
                        'stadium': stadium,
                        'date': now + timedelta(days=match_data['days']),
                        'status': 'upcoming',
                        'description': match_data['description'],
                        'external_ticket_url': match_data['external_url'],
                        'is_away_match': True,
                        'match_importance_score': competition.get_importance_score(),
                    }
                )

                if created:
                    created_count += 1
                    self.stdout.write(self.style.SUCCESS(
                        f'✅ Away: {opponent.name} vs Falcons FC '
                        f'— {match_data["stadium_city"]} '
                        f'→ {match_data["external_url"]}'
                    ))
                else:
                    match.external_ticket_url = match_data['external_url']
                    match.save()
                    self.stdout.write(f'↻  Updated: {opponent.name} vs Falcons FC')

            except Team.DoesNotExist:
                self.stdout.write(self.style.ERROR(
                    f'❌ Team not found: {match_data["opponent"]}'
                ))
            except Competition.DoesNotExist:
                self.stdout.write(self.style.ERROR(
                    f'❌ Competition not found: {match_data["competition"]}'
                ))
            except Exception as e:
                self.stdout.write(self.style.ERROR(f'❌ Error: {e}'))

        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS('═' * 60))
        self.stdout.write(self.style.SUCCESS('🦅  ALL AWAY MATCHES SEEDED'))
        self.stdout.write(self.style.SUCCESS('═' * 60))
        self.stdout.write(f'   Away matches created : {created_count}')
        self.stdout.write(f'   Total away matches   : {Match.objects.filter(is_away_match=True).count()}')
        self.stdout.write(self.style.SUCCESS('═' * 60))