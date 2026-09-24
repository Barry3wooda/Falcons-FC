from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView
from django.contrib import messages
from django.utils import timezone
from django.db import transaction
from django.conf import settings
from datetime import timedelta
import stripe
from .models import CustomUser, Stadium, Section, Row, Seat, Match, Ticket, Booking, Waitlist, Competition, Team

from .forms import RegisterForm, ProfileUpdateForm
from .models import (
    Match, Section, Seat, Ticket, Booking, Waitlist, CustomUser
)

stripe.api_key = settings.STRIPE_SECRET_KEY


# ─────────────────────────────────────────
# AUTH VIEWS (unchanged from Sprint 1)
# ─────────────────────────────────────────

def register_view(request):
    if request.user.is_authenticated:
        return redirect('home')
    if request.method == 'POST':
        form = RegisterForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            messages.success(request, f'Welcome to Falcons FC, {user.username}!')
            return redirect('home')
    else:
        form = RegisterForm()
    return render(request, 'auth/register.html', {'form': form})


def logout_view(request):
    logout(request)
    messages.info(request, 'You have been logged out.')
    return redirect('login')


@login_required
def profile_view(request):
    if request.method == 'POST':
        form = ProfileUpdateForm(request.POST, request.FILES, instance=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, 'Profile updated successfully!')
            return redirect('profile')
    else:
        form = ProfileUpdateForm(instance=request.user)
    bookings = Booking.objects.filter(
        user=request.user
    ).select_related('match').prefetch_related('tickets').order_by('-created_at')
    return render(request, 'auth/profile.html', {'form': form, 'bookings': bookings})


class CustomLoginView(LoginView):
    template_name = 'auth/login.html'


# ─────────────────────────────────────────
# HOME
# ─────────────────────────────────────────

def home_view(request):
    upcoming_matches = Match.objects.filter(
        status='upcoming',
        date__gte=timezone.now()
    ).select_related('home_team', 'away_team', 'competition')[:3]

    recommended_matches = []
    recommended_section = None
    if request.user.is_authenticated:
        from core.recommendations import recommend_matches, get_recommended_section_for_user
        recommended_matches = [
        m for m in recommend_matches(
        request.user,
        top_n_matches=3
             )
            if not m.is_away_match
        ]
        recommended_section, _reason = get_recommended_section_for_user(request.user)

    return render(request, 'home.html', {
        'upcoming_matches': upcoming_matches,
        'recommended_matches': recommended_matches,
        'recommended_section': recommended_section,
    })


# ─────────────────────────────────────────
# MATCH VIEWS
# ─────────────────────────────────────────

def match_list_view(request):
    competition_type = request.GET.get('type', '')
    match_type = request.GET.get('fixture', '')

    home_matches = Match.objects.filter(
        status='upcoming',
        date__gte=timezone.now(),
        is_away_match=False
    ).select_related('home_team', 'away_team', 'competition', 'stadium').order_by('date')

    away_matches = Match.objects.filter(
        status='upcoming',
        date__gte=timezone.now(),
        is_away_match=True
    ).select_related('home_team', 'away_team', 'competition', 'stadium').order_by('date')

    if competition_type:
        home_matches = home_matches.filter(competition__competition_type=competition_type)
        away_matches = away_matches.filter(competition__competition_type=competition_type)

    return render(request, 'matches/match_list.html', {
        'upcoming_matches': home_matches,
        'away_matches': away_matches,
        'competition_type': competition_type,
    })


def match_detail_view(request, match_id):
    from .pricing import calculate_dynamic_price

    match = get_object_or_404(
        Match.objects.select_related(
            'home_team', 'away_team', 'competition', 'stadium'
        ),
        id=match_id
    )

    sections = Section.objects.filter(stadium=match.stadium)
    section_data = []

    # Get recommendation for logged-in user
    recommended_section = None
    if request.user.is_authenticated:
        try:
            from .recommendations import get_recommended_section_for_user
            recommended_section, reason = get_recommended_section_for_user(
                request.user, match=match
            )
        except Exception:
            recommended_section = None

    for section in sections:
        available = section.available_seats_for_match(match).count()
        total = section.total_seats()
        dynamic_price = calculate_dynamic_price(match, section)
        is_recommended = (
            recommended_section is not None and
            section.id == recommended_section.id
        )
        section_data.append({
            'section': section,
            'available': available,
            'total': total,
            'sold_out': available == 0,
            'occupancy_pct': int(((total - available) / total * 100)) if total > 0 else 0,
            'dynamic_price': dynamic_price,
            'is_recommended': is_recommended,
        })

    return render(request, 'matches/match_detail.html', {
        'match': match,
        'section_data': section_data,
        'recommended_section': recommended_section,
    })


# ─────────────────────────────────────────
# SEAT MAP
# ─────────────────────────────────────────

def seat_map_view(request, match_id, section_id):
    from .pricing import calculate_dynamic_price
    match = get_object_or_404(Match, id=match_id)
    section = get_object_or_404(Section, id=section_id)

    if match.date <= timezone.now():
        messages.error(request, 'Booking is closed — this match has already started.')
        return redirect('match_list')

    taken_ids = set(
        Ticket.objects.filter(
            match=match,
            status__in=['locked', 'booked', 'used'],
            seat__row__section=section
        ).values_list('seat_id', flat=True)
    )

    rows = Row.objects.filter(
        section=section
    ).prefetch_related('seats').order_by('row_number')

    dynamic_price = calculate_dynamic_price(match, section)

    return render(request, 'matches/seat_map.html', {
        'match': match,
        'section': section,
        'taken_ids': taken_ids,
        'rows': rows,
        'dynamic_price': dynamic_price,
    })


# ─────────────────────────────────────────
# SEAT LOCKING
# ─────────────────────────────────────────

@login_required
def lock_seat_view(request):
    from .pricing import calculate_dynamic_price

    if request.method != 'POST':
        return redirect('home')

    seat_id = request.POST.get('seat_id')
    match_id = request.POST.get('match_id')

    seat = get_object_or_404(Seat, id=seat_id)
    match = get_object_or_404(Match, id=match_id)
    section = seat.row.section
    
    if match.date <= timezone.now():
        messages.error(request, 'Booking is closed — this match has already started.')
        return redirect('match_list')

    with transaction.atomic():
        ticket = Ticket.objects.select_for_update().filter(
            seat=seat, match=match
        ).first()

        dynamic_price = calculate_dynamic_price(match, section)

        if ticket:
            if ticket.status in ['booked', 'used']:
                messages.error(request, 'Sorry, this seat is already booked.')
                return redirect('seat_map', match_id=match_id, section_id=section.id)
            if ticket.status == 'locked' and not ticket.is_lock_expired():
                if ticket.user != request.user:
                    messages.error(request, 'Sorry, this seat is currently reserved by another fan.')
                    return redirect('seat_map', match_id=match_id, section_id=section.id)
                request.session['ticket_id'] = ticket.id
                return redirect('booking_summary')
            ticket.user = request.user
            ticket.status = 'locked'
            ticket.lock_expires_at = timezone.now() + timedelta(minutes=15)
            ticket.final_price = dynamic_price
            ticket.save()
        else:
            ticket = Ticket.objects.create(
                seat=seat,
                match=match,
                user=request.user,
                status='locked',
                lock_expires_at=timezone.now() + timedelta(minutes=15),
                final_price=dynamic_price,
            )

    request.session['ticket_id'] = ticket.id
    messages.success(request, f'Seat {seat.seat_number} reserved! You have 15 minutes to complete your purchase.')
    return redirect('booking_summary')


# ─────────────────────────────────────────
# BOOKING SUMMARY
# ─────────────────────────────────────────

@login_required
def booking_summary_view(request):
    ticket_id = request.session.get('ticket_id')
    if not ticket_id:
        messages.error(request, 'No seat selected. Please choose a seat first.')
        return redirect('match_list')

    ticket = get_object_or_404(
        Ticket.objects.select_related('seat__row__section', 'match__home_team', 'match__away_team'),
        id=ticket_id,
        user=request.user,
        status='locked'
    )

    if ticket.is_lock_expired():
        ticket.status = 'available'
        ticket.user = None
        ticket.save()
        del request.session['ticket_id']
        messages.error(request, 'Your seat reservation expired. Please select a seat again.')
        return redirect('match_list')

    # Calculate time remaining
    time_remaining = ticket.lock_expires_at - timezone.now()
    minutes_remaining = int(time_remaining.total_seconds() // 60)
    seconds_remaining = int(time_remaining.total_seconds() % 60)

    return render(request, 'bookings/booking_summary.html', {
        'ticket': ticket,
        'stripe_public_key': settings.STRIPE_PUBLIC_KEY,
        'minutes_remaining': minutes_remaining,
        'seconds_remaining': seconds_remaining,
    })


# ─────────────────────────────────────────
# PAYMENT
# ─────────────────────────────────────────

@login_required
def payment_view(request):
    if request.method != 'POST':
        return redirect('booking_summary')

    ticket_id = request.session.get('ticket_id')
    if not ticket_id:
        return redirect('match_list')

    ticket = get_object_or_404(Ticket, id=ticket_id, user=request.user, status='locked')

    if ticket.is_lock_expired():
        ticket.status = 'available'
        ticket.user = None
        ticket.save()
        messages.error(request, 'Your reservation expired.')
        return redirect('match_list')

    try:
        # Create Stripe payment intent
        intent = stripe.PaymentIntent.create(
            amount=int(ticket.final_price * 100),  # Stripe uses cents
            currency='eur',
            metadata={
                'ticket_id': ticket.id,
                'user_id': request.user.id,
                'match': str(ticket.match),
            }
        )
        request.session['payment_intent_id'] = intent.id
        return redirect('booking_confirm')

    except stripe.error.StripeError as e:
        messages.error(request, f'Payment error: {str(e)}')
        return redirect('booking_summary')


# ─────────────────────────────────────────
# BOOKING CONFIRMATION
# ─────────────────────────────────────────

@login_required
def booking_confirm_view(request):
    ticket_id = request.session.get('ticket_id')
    payment_intent_id = request.session.get('payment_intent_id')

    if not ticket_id:
        return redirect('match_list')

    ticket = get_object_or_404(Ticket, id=ticket_id, user=request.user)

    with transaction.atomic():
        ticket.status = 'booked'
        ticket.lock_expires_at = None
        ticket.save()

        booking = Booking.objects.create(
            user=request.user,
            match=ticket.match,
            total_price=ticket.final_price,
            payment_status='paid',
            stripe_payment_intent=payment_intent_id or 'test_mode',
        )
        booking.tickets.add(ticket)

    # Clear session
    if 'ticket_id' in request.session:
        del request.session['ticket_id']
    if 'payment_intent_id' in request.session:
        del request.session['payment_intent_id']

    # Fire background tasks automatically
    from core.tasks import process_booking
    process_booking.delay(booking.id, ticket.id)

    messages.success(request, '🎉 Booking confirmed! Your ticket is being prepared.')
    return render(request, 'bookings/booking_confirm.html', {
        'booking': booking,
        'ticket': ticket,
    })


# ─────────────────────────────────────────
# BOOKING DETAIL
# ─────────────────────────────────────────

@login_required
def booking_detail_view(request, booking_id):
    booking = get_object_or_404(
        Booking.objects.prefetch_related(
            'tickets__seat__row__section',
            'tickets__seat__row',
        ).select_related(
            'match__home_team',
            'match__away_team',
            'match__competition',
            'match__stadium',
        ),
        id=booking_id,
        user=request.user
    )
    return render(request, 'bookings/booking_detail.html', {
        'booking': booking,
    })


# ─────────────────────────────────────────
# TICKET DETAIL
# ─────────────────────────────────────────

@login_required
def ticket_detail_view(request, ticket_id):
    ticket = get_object_or_404(
        Ticket.objects.select_related(
            'seat__row__section__stadium',
            'match__home_team',
            'match__away_team',
            'match__competition'
        ),
        id=ticket_id,
        user=request.user
    )
    return render(request, 'bookings/ticket_detail.html', {
    'ticket': ticket,
    'now': timezone.now(),
})

# ─────────────────────────────────────────
# WAITLIST VIEWS
# ─────────────────────────────────────────

@login_required
def join_waitlist_view(request, match_id, section_id):
    from .models import Section, Match, Waitlist
    match = get_object_or_404(Match, id=match_id)
    section = get_object_or_404(Section, id=section_id)

    # Check if seats are actually available
    available = section.available_seats_for_match(match)
    if available.exists():
        messages.info(request, 'Seats are available! Select your seat directly.')
        return redirect('seat_map', match_id=match_id, section_id=section_id)

    # Check if already on waitlist
    existing = Waitlist.objects.filter(
        user=request.user,
        match=match,
        section=section
    ).first()

    if existing:
        messages.info(request, f'You are already on the waitlist at position {existing.position}.')
        return redirect('waitlist_confirm', match_id=match_id, section_id=section_id)

    # Get next position based on non-promoted entries only
    last = Waitlist.objects.filter(
        match=match,
        section=section,
        is_promoted=False
    ).order_by('-position').first()

    next_position = (last.position + 1) if last else 1

    # Create waitlist entry
    Waitlist.objects.create(
        user=request.user,
        match=match,
        section=section,
        position=next_position,
    )

    messages.success(
        request,
        f'You joined the waitlist for {section.name}! '
        f'Your position is #{next_position}. '
        f'We will email you when a seat becomes available.'
    )
    return redirect('waitlist_confirm', match_id=match_id, section_id=section_id)


@login_required
def waitlist_confirm_view(request, match_id, section_id):
    from .models import Section, Match, Waitlist
    match = get_object_or_404(Match, id=match_id)
    section = get_object_or_404(Section, id=section_id)

    entry = Waitlist.objects.filter(
        user=request.user,
        match=match,
        section=section,
        is_promoted=False
    ).first()

    # Count only non-promoted people ahead
    people_ahead = 0
    if entry:
        people_ahead = Waitlist.objects.filter(
            match=match,
            section=section,
            position__lt=entry.position,
            is_promoted=False
        ).count()

    return render(request, 'bookings/waitlist_confirm.html', {
        'match': match,
        'section': section,
        'entry': entry,
        'people_ahead': people_ahead,
    })

# ─────────────────────────────────────────
# GROUP SEAT ALLOCATOR VIEWS
# ─────────────────────────────────────────

@login_required
def group_seat_view(request, match_id, section_id):
    from .allocator import allocate_group_seats
    from .pricing import calculate_dynamic_price

    match = get_object_or_404(Match, id=match_id)
    section = get_object_or_404(Section, id=section_id)

    # Block booking after kick-off
    if match.date <= timezone.now():
        messages.error(request, 'Booking is closed — this match has already started.')
        return redirect('match_list')

    result = None
    n_seats = None
    dynamic_price = calculate_dynamic_price(match, section)

    # Get taken seat IDs for this match and section
    taken_ids = set(
        Ticket.objects.filter(
            match=match,
            status__in=['locked', 'booked', 'used'],
            seat__row__section=section
        ).values_list('seat_id', flat=True)
    )

    # Get all rows and seats for the section
    rows = Row.objects.filter(
        section=section
    ).prefetch_related('seats').order_by('row_number')

    # Build allocated seat IDs set after allocation
    allocated_seat_ids = set()

    if request.method == 'POST':
        try:
            n_seats = int(request.POST.get('n_seats', 2))
            n_seats = max(2, min(n_seats, 30))
            result = allocate_group_seats(match, section, n_seats)

            # Collect allocated seat IDs to highlight on map
            if result and result['type'] != 'impossible':
                for group in result['groups']:
                    for seat in group['seats']:
                        allocated_seat_ids.add(seat.id)

        except (ValueError, TypeError):
            messages.error(request, 'Please enter a valid number of seats.')

    return render(request, 'matches/group_seat.html', {
        'match': match,
        'section': section,
        'result': result,
        'n_seats': n_seats,
        'dynamic_price': dynamic_price,
        'rows': rows,
        'taken_ids': taken_ids,
        'allocated_seat_ids': allocated_seat_ids,
    })


@login_required
def lock_group_seats_view(request):
    if request.method != 'POST':
        return redirect('home')

    from .allocator import allocate_group_seats
    from .pricing import calculate_dynamic_price
    from decimal import Decimal
    match_id = request.POST.get('match_id')
    section_id = request.POST.get('section_id')
    n_seats = int(request.POST.get('n_seats', 2))

    match = get_object_or_404(Match, id=match_id)
    section = get_object_or_404(Section, id=section_id)

    result = allocate_group_seats(match, section, n_seats)

    if result['type'] == 'impossible':
        messages.error(request, result['message'])
        return redirect('match_detail', match_id=match_id)

    locked_tickets = []
    with transaction.atomic():
        for group in result['groups']:
            for seat in group['seats']:
                ticket, created = Ticket.objects.select_for_update().get_or_create(
                    seat=seat,
                    match=match,
                    defaults={
                        'user': request.user,
                        'status': 'locked',
                        'lock_expires_at': timezone.now() + timedelta(minutes=15),
                        'final_price': calculate_dynamic_price(match, section),
                    }
                )
                if not created:
                    if ticket.status in ['booked', 'used']:
                        messages.error(request, f'Seat {seat.seat_number} was just taken. Please try again.')
                        for t in locked_tickets:
                            t.status = 'available'
                            t.user = None
                            t.save()
                        return redirect('group_seat', match_id=match_id, section_id=section_id)
                    ticket.user = request.user
                    ticket.status = 'locked'
                    ticket.lock_expires_at = timezone.now() + timedelta(minutes=15)
                    ticket.final_price = calculate_dynamic_price(match, section)
                    ticket.save()
                locked_tickets.append(ticket)

    request.session['group_ticket_ids'] = [t.id for t in locked_tickets]
    request.session['group_total_price'] = float(sum(t.final_price for t in locked_tickets))

    messages.success(request, f'{len(locked_tickets)} seats locked! You have 15 minutes to complete payment.')
    return redirect('group_booking_summary')


@login_required
def group_booking_summary_view(request):
    ticket_ids = request.session.get('group_ticket_ids', [])
    if not ticket_ids:
        messages.error(request, 'No seats selected.')
        return redirect('match_list')

    tickets = Ticket.objects.filter(
        id__in=ticket_ids,
        user=request.user,
        status='locked'
    ).select_related('seat__row__section', 'match__home_team', 'match__away_team')

    if not tickets.exists():
        messages.error(request, 'Your reservation expired. Please try again.')
        return redirect('match_list')

    total_price = request.session.get('group_total_price', 0)
    first_ticket = tickets.first()

    time_remaining = first_ticket.lock_expires_at - timezone.now()
    minutes_remaining = int(time_remaining.total_seconds() // 60)
    seconds_remaining = int(time_remaining.total_seconds() % 60)

    return render(request, 'bookings/group_booking_summary.html', {
        'tickets': tickets,
        'total_price': total_price,
        'match': first_ticket.match,
        'section': first_ticket.seat.row.section,
        'minutes_remaining': minutes_remaining,
        'seconds_remaining': seconds_remaining,
        'stripe_public_key': settings.STRIPE_PUBLIC_KEY,
    })


@login_required
def group_payment_view(request):
    if request.method != 'POST':
        return redirect('group_booking_summary')

    ticket_ids = request.session.get('group_ticket_ids', [])
    total_price = request.session.get('group_total_price', 0)

    if not ticket_ids:
        return redirect('match_list')

    # Save holder names for each ticket
    from core.models import Ticket
    for ticket_id in ticket_ids:
        holder_name = request.POST.get(f'holder_name_{ticket_id}', '').strip()
        if holder_name:
            try:
                ticket = Ticket.objects.get(id=ticket_id, user=request.user)
                ticket.holder_name = holder_name
                ticket.save()
            except Ticket.DoesNotExist:
                pass

    try:
        intent = stripe.PaymentIntent.create(
            amount=int(float(total_price) * 100),
            currency='eur',
            metadata={
                'ticket_ids': str(ticket_ids),
                'user_id': request.user.id,
            }
        )
        request.session['group_payment_intent_id'] = intent.id
        return redirect('group_booking_confirm')

    except stripe.error.StripeError as e:
        messages.error(request, f'Payment error: {str(e)}')
        return redirect('group_booking_summary')


@login_required
def group_booking_confirm_view(request):
    ticket_ids = request.session.get('group_ticket_ids', [])
    payment_intent_id = request.session.get('group_payment_intent_id')
    total_price = request.session.get('group_total_price', 0)

    if not ticket_ids:
        return redirect('match_list')

    tickets = Ticket.objects.filter(
        id__in=ticket_ids,
        user=request.user
    ).select_related('seat__row__section', 'match')

    with transaction.atomic():
        for ticket in tickets:
            ticket.status = 'booked'
            ticket.lock_expires_at = None
            ticket.save()

        first_ticket = tickets.first()
        booking = Booking.objects.create(
            user=request.user,
            match=first_ticket.match,
            total_price=total_price,
            payment_status='paid',
            stripe_payment_intent=payment_intent_id or 'test_mode',
        )
        for ticket in tickets:
            booking.tickets.add(ticket)

    for key in ['group_ticket_ids', 'group_total_price', 'group_payment_intent_id']:
        if key in request.session:
            del request.session[key]

    from core.tasks import process_booking
    for ticket in tickets:
        process_booking.delay(booking.id, ticket.id)

    messages.success(request, f'🎉 Group booking confirmed! {tickets.count()} tickets reserved.')
    return render(request, 'bookings/group_booking_confirm.html', {
        'booking': booking,
        'tickets': tickets,
    })

@login_required
def cancel_ticket_view(request, ticket_id):
    ticket = get_object_or_404(
        Ticket,
        id=ticket_id,
        user=request.user,
        status='booked'
    )

    # Check match hasn't happened yet
    if ticket.match.date < timezone.now():
        messages.error(request, 'Cannot cancel a ticket for a past match.')
        return redirect('ticket_detail', ticket_id=ticket_id)

    if request.method == 'POST':
        reason = request.POST.get('reason', '').strip()

        with transaction.atomic():
            # Update ticket status
            ticket.status = 'available'
            ticket.user = None
            ticket.lock_expires_at = None
            ticket.cancelled_at = timezone.now()
            ticket.cancellation_reason = reason
            ticket.holder_name = None
            ticket.save()

            # Update booking payment status
            booking = Booking.objects.filter(
                tickets=ticket,
                user=request.user
            ).first()

            if booking:
                booking.payment_status = 'refunded'
                booking.save()

        # Send cancellation email
        from core.tasks import send_cancellation_email, promote_waitlist
        send_cancellation_email.delay(ticket_id)

        # Auto-promote waitlist
        promote_waitlist.delay()

        messages.success(
            request,
            f'Ticket cancelled successfully. '
            f'Seat {ticket.seat.seat_number} has been released.'
        )
        return redirect('profile')

    # GET — show confirmation page
    return render(request, 'bookings/cancel_confirm.html', {
        'ticket': ticket,
    })