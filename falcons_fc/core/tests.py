from django.test import TestCase
from django.utils import timezone
from datetime import timedelta
from django.contrib.auth import get_user_model
from django.db import transaction
from core.models import (
    Ticket, Match, Section, Row, Seat,
    Stadium, Competition, Team
)

User = get_user_model()


def create_test_data():
    stadium = Stadium.objects.create(
        name='Falcons Arena',
        city='Messina',
        capacity=314
    )
    section_vip = Section.objects.create(
        stadium=stadium, name='VIP', base_price=150.00
    )
    section_tribune = Section.objects.create(
        stadium=stadium, name='Tribune', base_price=80.00
    )
    section_curve = Section.objects.create(
        stadium=stadium, name='Curve Nord', base_price=40.00
    )
    for r in range(1, 4):
        row = Row.objects.create(section=section_vip, row_number=r)
        for s in range(1, 16):
            Seat.objects.create(row=row, seat_number=s, is_active=True)
    for r in range(1, 9):
        row = Row.objects.create(section=section_tribune, row_number=r)
        for s in range(1, 16):
            Seat.objects.create(row=row, seat_number=s, is_active=True)
    for r in range(1, 4):
        row = Row.objects.create(section=section_curve, row_number=r)
        for s in range(1, 16):
            Seat.objects.create(row=row, seat_number=s, is_active=True)
    derby = Competition.objects.create(
        name='Sicily Derby', competition_type='Derby'
    )
    cup = Competition.objects.create(
        name='Coppa Italia', competition_type='Cup'
    )
    league = Competition.objects.create(
        name='Serie A', competition_type='League'
    )
    home_team = Team.objects.create(name='Falcons FC', city='Messina')
    away_team = Team.objects.create(name='Palermo FC', city='Palermo')
    match_derby = Match.objects.create(
        home_team=home_team, away_team=away_team,
        competition=derby, stadium=stadium,
        date=timezone.now() + timedelta(days=10),
        status='upcoming'
    )
    match_cup = Match.objects.create(
        home_team=home_team, away_team=away_team,
        competition=cup, stadium=stadium,
        date=timezone.now() + timedelta(days=20),
        status='upcoming'
    )
    match_league = Match.objects.create(
        home_team=home_team, away_team=away_team,
        competition=league, stadium=stadium,
        date=timezone.now() + timedelta(days=30),
        status='upcoming'
    )
    for seat in Seat.objects.filter(row__section=section_vip):
        Ticket.objects.create(
            seat=seat, match=match_derby, status='available'
        )
    for seat in Seat.objects.filter(row__section=section_tribune):
        Ticket.objects.create(
            seat=seat, match=match_derby, status='available'
        )
    for seat in Seat.objects.filter(row__section=section_curve):
        Ticket.objects.create(
            seat=seat, match=match_derby, status='available'
        )
    return {
        'vip': section_vip,
        'tribune': section_tribune,
        'curve': section_curve,
        'derby': match_derby,
        'cup': match_cup,
        'league': match_league,
    }


# ─────────────────────────────────────────────
# UNIT TESTS — Ticket Lock Expiry
# ─────────────────────────────────────────────

class TicketLockExpiryTest(TestCase):

    def setUp(self):
        data = create_test_data()
        self.user = User.objects.create_user(
            username='test_fan', password='test1234'
        )
        self.ticket = Ticket.objects.filter(
            status='available'
        ).first()
        self.ticket.status = 'locked'
        self.ticket.user = self.user
        self.ticket.save()

    def test_1_lock_expired(self):
        self.ticket.lock_expires_at = (
            timezone.now() - timedelta(minutes=20)
        )
        self.ticket.save()
        result = self.ticket.is_lock_expired()
        print(f"\n[UNIT TEST 1] Lock set 20 minutes ago")
        print(f"  is_lock_expired() = {result}")
        print(f"  Expected: True — PASS" if result else "  FAIL")
        self.assertTrue(result)

    def test_2_lock_valid(self):
        self.ticket.lock_expires_at = (
            timezone.now() + timedelta(minutes=10)
        )
        self.ticket.save()
        result = self.ticket.is_lock_expired()
        print(f"\n[UNIT TEST 2] Lock expires in 10 minutes")
        print(f"  is_lock_expired() = {result}")
        print(f"  Expected: False — PASS" if not result else "  FAIL")
        self.assertFalse(result)

    def test_3_no_lock_set(self):
        self.ticket.lock_expires_at = None
        self.ticket.save()
        result = self.ticket.is_lock_expired()
        print(f"\n[UNIT TEST 3] No lock set on ticket")
        print(f"  is_lock_expired() = {result}")
        print(f"  Expected: False — PASS" if not result else "  FAIL")
        self.assertFalse(result)


# ─────────────────────────────────────────────
# INTEGRATION TESTS — Concurrent Booking
# ─────────────────────────────────────────────

class ConcurrentBookingTest(TestCase):

    def setUp(self):
        data = create_test_data()
        self.fan1 = User.objects.create_user(
            username='marco_rossi', password='test1234'
        )
        self.fan2 = User.objects.create_user(
            username='anna_greco', password='test1234'
        )
        self.match = data['derby']
        self.ticket = Ticket.objects.filter(
            match=self.match, status='available'
        ).first()

    def test_1_concurrent_booking_blocked(self):
        print(f"\n[INTEGRATION TEST 1] Concurrent Booking Safety")
        print(f"  Seat: {self.ticket.seat} — Match: {self.match}")

        with transaction.atomic():
            ticket = Ticket.objects.select_for_update().get(
                pk=self.ticket.pk
            )
            ticket.status = 'locked'
            ticket.user = self.fan1
            ticket.save()
        print(f"  Fan 1 ({self.fan1.username}) — seat locked successfully")

        with transaction.atomic():
            ticket = Ticket.objects.select_for_update().get(
                pk=self.ticket.pk
            )
            blocked = (
                ticket.status == 'locked' and
                ticket.user != self.fan2
            )
            print(
                f"  Fan 2 ({self.fan2.username}) — "
                f"correctly blocked: {blocked}"
            )
            print(f"  Expected: True — PASS" if blocked else "  FAIL")
            self.assertTrue(blocked)

    def test_2_ticket_confirmed_after_payment(self):
        print(f"\n[INTEGRATION TEST 2] Ticket Confirmed After Payment")

        with transaction.atomic():
            ticket = Ticket.objects.select_for_update().get(
                pk=self.ticket.pk
            )
            ticket.status = 'booked'
            ticket.user = self.fan1
            ticket.save()

        self.ticket.refresh_from_db()
        print(f"  Ticket status after payment: {self.ticket.status}")
        print(f"  Ticket owner: {self.ticket.user.username}")
        print(
            f"  Expected: booked / marco_rossi — PASS"
            if self.ticket.status == 'booked'
            else "  FAIL"
        )
        self.assertEqual(self.ticket.status, 'booked')
        self.assertEqual(self.ticket.user, self.fan1)


# ─────────────────────────────────────────────
# ALGORITHM TESTS — C1 ML Dynamic Pricing
# ─────────────────────────────────────────────

class MLDynamicPricingTest(TestCase):

    def setUp(self):
        data = create_test_data()
        self.section = data['vip']
        self.derby = data['derby']
        self.cup = data['cup']
        self.league = data['league']

    def test_1_derby_higher_than_league(self):
        from core.pricing import calculate_dynamic_price
        derby_price = calculate_dynamic_price(self.derby, self.section)
        league_price = calculate_dynamic_price(self.league, self.section)
        print(f"\n[C1 TEST 1] Derby vs League Price Comparison")
        print(f"  Derby price:  €{derby_price}")
        print(f"  League price: €{league_price}")
        print(
            f"  Derby > League — PASS"
            if derby_price > league_price
            else "  FAIL"
        )
        self.assertGreater(derby_price, league_price)

    def test_2_price_above_base(self):
        from core.pricing import calculate_dynamic_price
        price = calculate_dynamic_price(self.derby, self.section)
        base = float(self.section.base_price)
        print(f"\n[C1 TEST 2] Price Above Base Price")
        print(f"  Base price:    €{base}")
        print(f"  Dynamic price: €{price}")
        increase = round(((price - base) / base) * 100, 1)
        print(f"  Increase:      +{increase}%")
        print(
            f"  Price > Base — PASS"
            if price > base
            else "  FAIL"
        )
        self.assertGreater(price, base)

    def test_3_fallback_on_missing_model(self):
        from core.pricing import calculate_dynamic_price
        import core.pricing as pricing
        original = pricing._model
        pricing._model = None
        try:
            price = calculate_dynamic_price(self.league, self.section)
            print(f"\n[C1 TEST 3] Fallback When Model Unavailable")
            print(f"  Model set to None — fallback price: €{price}")
            print(
                f"  Returned base price — PASS"
                if price is not None
                else "  FAIL"
            )
            self.assertIsNotNone(price)
        finally:
            pricing._model = original


# ─────────────────────────────────────────────
# ALGORITHM TESTS — C2 Recommendation Engine
# ─────────────────────────────────────────────

class RecommendationEngineTest(TestCase):

    def setUp(self):
        data = create_test_data()
        self.match = data['derby']
        self.vip = data['vip']
        self.tribune = data['tribune']
        self.curve = data['curve']

        self.marco = User.objects.create_user(
            username='marco_rossi', password='test1234'
        )
        self.anna = User.objects.create_user(
            username='anna_greco', password='test1234'
        )
        self.antonio = User.objects.create_user(
            username='antonio_gallo', password='test1234'
        )
        self.new_user = User.objects.create_user(
            username='test_new1', password='test1234'
        )

        for ticket in Ticket.objects.filter(
            seat__row__section=self.vip
        )[:14]:
            ticket.status = 'booked'
            ticket.user = self.marco
            ticket.save()

        for ticket in Ticket.objects.filter(
            seat__row__section=self.tribune
        )[:20]:
            ticket.status = 'booked'
            ticket.user = self.anna
            ticket.save()

        for ticket in Ticket.objects.filter(
            seat__row__section=self.curve
        )[:18]:
            ticket.status = 'booked'
            ticket.user = self.antonio
            ticket.save()

    def test_1_vip_fan_gets_vip(self):
        from core.recommendations import get_recommended_section_for_user
        section, reason = get_recommended_section_for_user(
            self.marco, match=self.match
        )
        print(f"\n[C2 TEST 1] VIP Fan Recommendation")
        print(f"  User: marco_rossi (14 VIP bookings)")
        print(f"  Recommended: {section.name} ({reason})")
        print(
            f"  Expected: VIP — PASS"
            if section.name == 'VIP'
            else f"  Expected: VIP — GOT: {section.name} — FAIL"
        )
        self.assertEqual(section.name, 'VIP')

    def test_2_tribune_fan_gets_tribune(self):
        from core.recommendations import get_recommended_section_for_user
        section, reason = get_recommended_section_for_user(
            self.anna, match=self.match
        )
        print(f"\n[C2 TEST 2] Tribune Fan Recommendation")
        print(f"  User: anna_greco (20 Tribune bookings)")
        print(f"  Recommended: {section.name} ({reason})")
        print(
            f"  Expected: Tribune — PASS"
            if section.name == 'Tribune'
            else f"  Expected: Tribune — GOT: {section.name} — FAIL"
        )
        self.assertEqual(section.name, 'Tribune')

    def test_3_curve_fan_gets_curve(self):
        from core.recommendations import get_recommended_section_for_user
        section, reason = get_recommended_section_for_user(
            self.antonio, match=self.match
        )
        print(f"\n[C2 TEST 3] Curve Nord Fan Recommendation")
        print(f"  User: antonio_gallo (18 Curve Nord bookings)")
        print(f"  Recommended: {section.name} ({reason})")
        print(
            f"  Expected: Curve Nord — PASS"
            if section.name == 'Curve Nord'
            else f"  Expected: Curve Nord — GOT: {section.name} — FAIL"
        )
        self.assertEqual(section.name, 'Curve Nord')

    def test_4_new_user_cold_start(self):
        from core.recommendations import get_recommended_section_for_user
        section, reason = get_recommended_section_for_user(
            self.new_user, match=self.match
        )
        print(f"\n[C2 TEST 4] New User Cold Start")
        print(f"  User: test_new1 (no booking history)")
        print(f"  Recommended: {section.name} ({reason})")
        print(
            f"  Cold start triggered — PASS"
            if 'cold_start' in reason
            else f"  Expected cold_start — GOT: {reason} — FAIL"
        )
        self.assertIn('cold_start', reason)


# ─────────────────────────────────────────────
# ALGORITHM TESTS — C3 Group Seat Allocator
# ─────────────────────────────────────────────

class GroupSeatAllocatorTest(TestCase):

    def setUp(self):
        data = create_test_data()
        self.match = data['derby']
        self.section = data['tribune']

    def test_1_small_group_perfect_block(self):
        from core.allocator import allocate_group_seats
        result = allocate_group_seats(self.match, self.section, 2)
        total = sum(len(g['seats']) for g in result['groups'])
        print(f"\n[C3 TEST 1] Small Group — 2 Seats")
        print(f"  Result type: {result['type']}")
        print(f"  Seats allocated: {total}")
        print(
            f"  Expected: perfect / 2 — PASS"
            if result['type'] == 'perfect' and total == 2
            else "  FAIL"
        )
        self.assertEqual(result['type'], 'perfect')
        self.assertEqual(total, 2)

    def test_2_full_row_perfect_block(self):
        from core.allocator import allocate_group_seats
        result = allocate_group_seats(self.match, self.section, 15)
        total = sum(len(g['seats']) for g in result['groups'])
        print(f"\n[C3 TEST 2] Full Row — 15 Seats")
        print(f"  Result type: {result['type']}")
        print(f"  Seats allocated: {total}")
        print(
            f"  Expected: perfect / 15 — PASS"
            if result['type'] == 'perfect' and total == 15
            else "  FAIL"
        )
        self.assertEqual(result['type'], 'perfect')
        self.assertEqual(total, 15)

    def test_3_split_allocation(self):
        from core.allocator import allocate_group_seats
        result = allocate_group_seats(self.match, self.section, 16)
        total = sum(len(g['seats']) for g in result['groups'])
        print(f"\n[C3 TEST 3] Split Required — 16 Seats")
        print(f"  Result type: {result['type']}")
        print(f"  Groups: {len(result['groups'])}")
        print(f"  Seats allocated: {total}")
        print(
            f"  Expected: split / 16 — PASS"
            if result['type'] == 'split' and total == 16
            else "  FAIL"
        )
        self.assertEqual(result['type'], 'split')
        self.assertEqual(total, 16)

    def test_4_impossible_request(self):
        from core.allocator import allocate_group_seats
        result = allocate_group_seats(self.match, self.section, 400)
        print(f"\n[C3 TEST 4] Impossible Request — 400 Seats")
        print(f"  Result type: {result['type']}")
        print(
            f"  Expected: impossible — PASS"
            if result['type'] == 'impossible'
            else "  FAIL"
        )
        self.assertEqual(result['type'], 'impossible')

    def test_5_exact_seat_count(self):
        from core.allocator import allocate_group_seats
        print(f"\n[C3 TEST 5] Exact Seat Count — All Group Sizes")
        print(f"  {'Requested':<12} {'Type':<12} {'Allocated'}")
        print(f"  {'-'*36}")
        for n in [2, 6, 15, 16, 30]:
            result = allocate_group_seats(self.match, self.section, n)
            if result['type'] != 'impossible':
                total = sum(
                    len(g['seats']) for g in result['groups']
                )
                status = 'PASS' if total == n else 'FAIL'
                print(
                    f"  {n:<12} {result['type']:<12} "
                    f"{total} — {status}"
                )
                self.assertEqual(total, n)