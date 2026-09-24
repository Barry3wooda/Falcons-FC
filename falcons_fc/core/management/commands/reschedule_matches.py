from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
from core.models import Match


class Command(BaseCommand):
    help = 'Reschedules upcoming matches with realistic, non-overlapping spacing by competition type'

    def handle(self, *args, **kwargs):
        now = timezone.now()
        self.stdout.write(self.style.WARNING('🦅 Rescheduling matches...'))

        upcoming = Match.objects.filter(status='upcoming').order_by('date')

        derby_matches = list(upcoming.filter(competition__competition_type='Derby'))
        cup_matches = list(upcoming.filter(competition__competition_type='Cup'))
        league_matches = list(upcoming.filter(competition__competition_type='League'))

        # ── DERBY: rare and high-stakes. First one = nearest HOME match, 
        #    any additional derby spaced far apart (~8 weeks, derbies don't repeat often)
        for i, m in enumerate(derby_matches):
            new_date = now + timedelta(days=1) if i == 0 else now + timedelta(days=1 + i * 56)
            m.date = new_date
            m.save(update_fields=['date'])
            side = 'HOME' if m.home_team.name == 'Falcons FC' else 'AWAY'
            self.stdout.write(f'  🔥 Derby ({side}): {m} → {new_date.strftime("%Y-%m-%d")}')

        # ── LEAGUE: split by home/away, force nearest AWAY match early for demo,
        #    then space everything else one match per week (realistic league calendar)
        home_league = [m for m in league_matches if m.home_team.name == 'Falcons FC']
        away_league = [m for m in league_matches if m.away_team.name == 'Falcons FC']

        remaining = []
        if away_league:
            nearest_away = away_league.pop(0)
            nearest_away.date = now + timedelta(days=2)  # nearest AWAY match
            nearest_away.save(update_fields=['date'])
            self.stdout.write(f'  ⚽ League (AWAY, nearest): {nearest_away} → {nearest_away.date.strftime("%Y-%m-%d")}')

        # Interleave the rest home/away like a real fixture list
        max_len = max(len(home_league), len(away_league))
        for i in range(max_len):
            if i < len(home_league):
                remaining.append(home_league[i])
            if i < len(away_league):
                remaining.append(away_league[i])

        league_start = now + timedelta(days=9)  # one week after the nearest away match
        for i, m in enumerate(remaining):
            new_date = league_start + timedelta(weeks=i)
            m.date = new_date
            m.save(update_fields=['date'])
            side = 'HOME' if m.home_team.name == 'Falcons FC' else 'AWAY'
            self.stdout.write(f'  ⚽ League ({side}): {m} → {new_date.strftime("%Y-%m-%d")}')

        # ── CUP: knockout rounds, spaced ~3 weeks apart (Round of 16 → QF → SF),
        #    offset from league so a cup match never lands the same week as a league match
        home_cup = [m for m in cup_matches if m.home_team.name == 'Falcons FC']
        away_cup = [m for m in cup_matches if m.away_team.name == 'Falcons FC']

        cup_interleaved = []
        max_len = max(len(home_cup), len(away_cup))
        for i in range(max_len):
            if i < len(home_cup):
                cup_interleaved.append(home_cup[i])
            if i < len(away_cup):
                cup_interleaved.append(away_cup[i])

        cup_start = now + timedelta(days=15)  # offset so it doesn't clash with early league weeks
        for i, m in enumerate(cup_interleaved):
            new_date = cup_start + timedelta(weeks=i * 3)
            m.date = new_date
            m.save(update_fields=['date'])
            side = 'HOME' if m.home_team.name == 'Falcons FC' else 'AWAY'
            self.stdout.write(f'  🏆 Cup ({side}): {m} → {new_date.strftime("%Y-%m-%d")}')

        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS('═' * 60))
        self.stdout.write(self.style.SUCCESS('✅ Schedule rebuilt:'))
        self.stdout.write('   Nearest HOME match: Derby, tomorrow')
        self.stdout.write('   Nearest AWAY match: League, in 2 days')
        self.stdout.write('   League matches: one per week from there')
        self.stdout.write('   Cup matches: spaced 3 weeks apart, offset from league weeks')
        self.stdout.write(self.style.SUCCESS('═' * 60))