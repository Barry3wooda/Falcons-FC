from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
from decimal import Decimal
from core.models import (
    CustomUser, Match, Section, Seat, Row,
    Ticket, Booking, Waitlist
)
import random


class Command(BaseCommand):
    help = 'Seeds realistic user booking data for testing recommendations and ML pricing'

    USERS = [
        # Derby fans (love high-intensity matches)
        {'username': 'marco_rossi',    'email': 'marco@test.com',    'password': 'test1234', 'profile': 'derby'},
        {'username': 'sofia_ferrari',  'email': 'sofia@test.com',    'password': 'test1234', 'profile': 'derby'},
        {'username': 'luca_bianchi',   'email': 'luca@test.com',     'password': 'test1234', 'profile': 'derby'},

        # League fans (regular match attendees)
        {'username': 'anna_greco',     'email': 'anna@test.com',     'password': 'test1234', 'profile': 'league'},
        {'username': 'paolo_romano',   'email': 'paolo@test.com',    'password': 'test1234', 'profile': 'league'},
        {'username': 'chiara_ricci',   'email': 'chiara@test.com',   'password': 'test1234', 'profile': 'league'},

        # Cup fans (knockout match enthusiasts)
        {'username': 'matteo_conti',   'email': 'matteo@test.com',   'password': 'test1234', 'profile': 'cup'},
        {'username': 'giulia_marino',  'email': 'giulia@test.com',   'password': 'test1234', 'profile': 'cup'},

        # VIP fans (always book premium seats)
        {'username': 'roberto_villa',  'email': 'roberto@test.com',  'password': 'test1234', 'profile': 'vip'},
        {'username': 'elena_costa',    'email': 'elena@test.com',    'password': 'test1234', 'profile': 'vip'},

        # Curve fans (the ultras — always in Curve Nord or Sud)
        {'username': 'antonio_gallo',  'email': 'antonio@test.com',  'password': 'test1234', 'profile': 'curve'},
        {'username': 'francesca_espo', 'email': 'francesca@test.com','password': 'test1234', 'profile': 'curve'},

        # Mixed fans (attend everything)
        {'username': 'davide_russo',   'email': 'davide@test.com',   'password': 'test1234', 'profile': 'mixed'},
        {'username': 'valentina_mele', 'email': 'valentina@test.com','password': 'test1234', 'profile': 'mixed'},
        {'username': 'simone_rizzo',   'email': 'simone@test.com',   'password': 'test1234', 'profile': 'mixed'},
    ]

    SECTION_PROFILES = {
        'derby':  {'VIP': 0.5, 'Tribune': 0.3, 'Curve Nord': 0.1, 'Curve Sud': 0.1},
        'league': {'VIP': 0.2, 'Tribune': 0.5, 'Curve Nord': 0.15, 'Curve Sud': 0.15},
        'cup':    {'VIP': 0.3, 'Tribune': 0.4, 'Curve Nord': 0.15, 'Curve Sud': 0.15},
        'vip':    {'VIP': 0.8, 'Tribune': 0.15, 'Curve Nord': 0.025, 'Curve Sud': 0.025},
        'curve':  {'VIP': 0.05, 'Tribune': 0.1, 'Curve Nord': 0.5, 'Curve Sud': 0.35},
        'mixed':  {'VIP': 0.25, 'Tribune': 0.25, 'Curve Nord': 0.25, 'Curve Sud': 0.25},
    }

    COMPETITION_PROFILES = {
        'derby':  {'Derby': 0.6, 'Cup': 0.25, 'League': 0.15},
        'league': {'Derby': 0.15, 'Cup': 0.2, 'League': 0.65},
        'cup':    {'Derby': 0.2, 'Cup': 0.6, 'League': 0.2},
        'vip':    {'Derby': 0.4, 'Cup': 0.35, 'League': 0.25},
        'curve':  {'Derby': 0.5, 'Cup': 0.2, 'League': 0.3},
        'mixed':  {'Derby': 0.33, 'Cup': 0.33, 'League': 0.34},
    }

    def handle(self, *args, **kwargs):
        random.seed(42)
        self.stdout.write(self.style.WARNING('🦅 Seeding realistic user data...'))

        # ── CREATE USERS ──────────────────────────────────────
        created_users = []
        for user_data in self.USERS:
            user, created = CustomUser.objects.get_or_create(
                username=user_data['username'],
                defaults={
                    'email': user_data['email'],
                    'phone': f'+39 33{random.randint(1000000, 9999999)}',
                }
            )
            if created:
                user.set_password(user_data['password'])
                user.save()
                self.stdout.write(self.style.SUCCESS(f'✅ Created user: {user.username} ({user_data["profile"]} fan)'))
            else:
                self.stdout.write(f'ℹ️  User {user.username} already exists')

            created_users.append((user, user_data['profile']))

        # ── GET FINISHED MATCHES ───────────────────────────────
        # Use matches that have already passed for booking history
        all_matches = list(Match.objects.all().select_related('competition'))
        if not all_matches:
            self.stdout.write(self.style.ERROR('No matches found! Run seed_stadium first.'))
            return

        sections = {s.name: s for s in Section.objects.all()}
        booking_count = 0

        # ── CREATE BOOKING HISTORY ─────────────────────────────
        for user, profile in created_users:
            comp_prefs = self.COMPETITION_PROFILES[profile]
            section_prefs = self.SECTION_PROFILES[profile]

            # Each user gets 3-8 historical bookings
            num_bookings = random.randint(3, 8)

            for _ in range(num_bookings):
                # Pick competition type based on profile
                comp_type = random.choices(
                    list(comp_prefs.keys()),
                    weights=list(comp_prefs.values())
                )[0]

                # Pick a match of that competition type
                matching_matches = [m for m in all_matches if m.competition.competition_type == comp_type]
                if not matching_matches:
                    matching_matches = all_matches

                match = random.choice(matching_matches)

                # Pick section based on profile
                section_name = random.choices(
                    list(section_prefs.keys()),
                    weights=list(section_prefs.values())
                )[0]
                section = sections[section_name]

                # Find an available seat
                taken_seat_ids = Ticket.objects.filter(
                    match=match,
                    status__in=['booked', 'used'],
                    seat__row__section=section
                ).values_list('seat_id', flat=True)

                available_seats = Seat.objects.filter(
                    row__section=section,
                    is_active=True
                ).exclude(id__in=taken_seat_ids)

                if not available_seats.exists():
                    continue

                seat = random.choice(list(available_seats))

                # Calculate dynamic price
                from core.pricing import calculate_dynamic_price
                price = calculate_dynamic_price(match, section)

                # Create ticket
                ticket = Ticket.objects.create(
                    seat=seat,
                    match=match,
                    user=user,
                    status='booked',
                    final_price=Decimal(str(price)),
                    lock_expires_at=None,
                )

                # Create booking
                booking = Booking.objects.create(
                    user=user,
                    match=match,
                    total_price=Decimal(str(price)),
                    payment_status='paid',
                    stripe_payment_intent=f'test_seed_{ticket.id}',
                )
                booking.tickets.add(ticket)
                booking_count += 1

        # ── SUMMARY ───────────────────────────────────────────
        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS('═' * 55))
        self.stdout.write(self.style.SUCCESS('🦅  USER DATA SEEDED SUCCESSFULLY'))
        self.stdout.write(self.style.SUCCESS('═' * 55))
        self.stdout.write(f'   Users created : {len(self.USERS)}')
        self.stdout.write(f'   Bookings created: {booking_count}')
        self.stdout.write(f'   Total users now : {CustomUser.objects.count()}')
        self.stdout.write(self.style.SUCCESS('═' * 55))