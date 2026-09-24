import os
import qrcode
import logging
from io import BytesIO
from celery import shared_task
from django.core.files.base import ContentFile
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.utils import timezone
from django.conf import settings

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────
# TASK 1 — Release expired seat locks
# Runs every 2 minutes via Celery Beat
# ─────────────────────────────────────────

@shared_task(name='core.tasks.release_expired_locks')
def release_expired_locks():
    from core.models import Ticket
    expired = Ticket.objects.filter(
        status='locked',
        lock_expires_at__lt=timezone.now()
    )
    count = expired.count()
    expired.update(
        status='available',
        user=None,
        lock_expires_at=None,
        final_price=None,
    )
    if count > 0:
        logger.info(f'Released {count} expired seat locks.')
    return f'Released {count} expired locks.'


# ─────────────────────────────────────────
# TASK 2 — Auto-promote waitlist
# Runs every 5 minutes via Celery Beat
# ─────────────────────────────────────────

@shared_task(name='core.tasks.promote_waitlist')
def promote_waitlist():
    from core.models import Waitlist

    promoted_count = 0
    pending = Waitlist.objects.filter(
        is_promoted=False
    ).select_related('user', 'match', 'section').order_by('position')

    for entry in pending:
        available = entry.section.available_seats_for_match(entry.match)
        if available.exists():
            entry.is_promoted = True
            entry.save()

            # Recalculate positions for remaining entries
            remaining = Waitlist.objects.filter(
                match=entry.match,
                section=entry.section,
                is_promoted=False
            ).order_by('position')

            for i, remaining_entry in enumerate(remaining, start=1):
                if remaining_entry.position != i:
                    remaining_entry.position = i
                    remaining_entry.save()

            send_waitlist_promotion_email.delay(entry.id)
            promoted_count += 1
            logger.info(
                f'Promoted {entry.user.username} for '
                f'{entry.match} — {entry.section.name}'
            )

    return f'Promoted {promoted_count} waitlist entries.'


# ─────────────────────────────────────────
# TASK 3 — Send booking confirmation email
# Triggered on booking confirmation
# ─────────────────────────────────────────

@shared_task(name='core.tasks.send_booking_confirmation_email')
def send_booking_confirmation_email(booking_id):
    from core.models import Booking
    try:
        booking = Booking.objects.select_related(
            'user', 'match__home_team', 'match__away_team',
            'match__stadium'
        ).prefetch_related('tickets__seat__row__section').get(id=booking_id)

        subject = f'Booking Confirmed — {booking.match}'
        message = render_to_string('emails/booking_confirmation.html', {
            'booking': booking,
            'user': booking.user,
        })

        send_mail(
            subject=subject,
            message='',
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[booking.user.email],
            html_message=message,
            fail_silently=False,
        )
        logger.info(f'Confirmation email sent for booking #{booking_id}')
        return f'Email sent for booking #{booking_id}'

    except Exception as e:
        logger.error(f'Failed to send confirmation email: {e}')
        return f'Failed: {e}'


# ─────────────────────────────────────────
# TASK 4 — Send waitlist promotion email
# Triggered when fan is promoted
# ─────────────────────────────────────────

@shared_task(name='core.tasks.send_waitlist_promotion_email')
def send_waitlist_promotion_email(waitlist_entry_id):
    from core.models import Waitlist
    try:
        entry = Waitlist.objects.select_related(
            'user', 'match__home_team', 'match__away_team', 'section'
        ).get(id=waitlist_entry_id)

        subject = f'Good news! A seat is available — {entry.match}'
        message = render_to_string('emails/waitlist_promotion.html', {
            'entry': entry,
            'user': entry.user,
        })

        send_mail(
            subject=subject,
            message='',
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[entry.user.email],
            html_message=message,
            fail_silently=False,
        )
        logger.info(f'Waitlist promotion email sent to {entry.user.username}')
        return f'Waitlist email sent to {entry.user.email}'

    except Exception as e:
        logger.error(f'Failed to send waitlist email: {e}')
        return f'Failed: {e}'


# ─────────────────────────────────────────
# TASK 5 — Generate QR code for ticket
# Triggered on booking confirmation
# ─────────────────────────────────────────

@shared_task(name='core.tasks.generate_qr_code')
def generate_qr_code(ticket_id):
    from core.models import Ticket
    try:
        ticket = Ticket.objects.select_related(
            'seat__row__section', 'match', 'user'
        ).get(id=ticket_id)

        holder = ticket.holder_name or ticket.user.get_full_name() or ticket.user.username

        qr_data = (
            f'FALCONS-FC-TICKET\n'
            f'ID: {ticket.id}\n'
            f'Match: {ticket.match}\n'
            f'Section: {ticket.seat.row.section.name}\n'
            f'Row: {ticket.seat.row.row_number}\n'
            f'Seat: {ticket.seat.seat_number}\n'
            f'Fan: {holder}\n'
            f'Price: EUR {ticket.final_price}'
        )

        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_H,
            box_size=10,
            border=4,
        )
        qr.add_data(qr_data)
        qr.make(fit=True)

        img = qr.make_image(fill_color='black', back_color='white')
        buffer = BytesIO()
        img.save(buffer, format='PNG')
        buffer.seek(0)

        filename = f'ticket_{ticket_id}_qr.png'
        ticket.qr_code.save(filename, ContentFile(buffer.read()), save=True)

        logger.info(f'QR code generated for ticket #{ticket_id}')
        return f'QR generated for ticket #{ticket_id}'

    except Exception as e:
        logger.error(f'Failed to generate QR code: {e}')
        return f'Failed: {e}'


# ─────────────────────────────────────────
# TASK 6 — Generate PDF ticket
# Triggered after QR code is ready
# ─────────────────────────────────────────

@shared_task(name='core.tasks.generate_pdf_ticket')
def generate_pdf_ticket(ticket_id):
    from core.models import Ticket
    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors
    from reportlab.lib.units import mm
    from reportlab.pdfgen import canvas
    from reportlab.lib.utils import ImageReader

    try:
        ticket = Ticket.objects.select_related(
            'seat__row__section__stadium',
            'match__home_team',
            'match__away_team',
            'match__competition',
            'user'
        ).get(id=ticket_id)

        buffer = BytesIO()
        c = canvas.Canvas(buffer, pagesize=A4)
        w, h = A4

        # ── BACKGROUND ──────────────────────────────────
        c.setFillColor(colors.HexColor('#0D1B2E'))
        c.rect(0, 0, w, h, fill=1, stroke=0)

        # ── TOP ACCENT BAR ───────────────────────────────
        c.setFillColor(colors.HexColor('#1B3A6B'))
        c.rect(0, h - 18*mm, w, 18*mm, fill=1, stroke=0)

        # ── BLUE HEADER SECTION ──────────────────────────
        c.setFillColor(colors.HexColor('#1B3A6B'))
        c.rect(0, h - 90*mm, w, 72*mm, fill=1, stroke=0)

        # Subtle highlight gradient effect (top edge)
        c.setFillColor(colors.HexColor('#2952A3'))
        c.rect(0, h - 22*mm, w, 4*mm, fill=1, stroke=0)

        # ── CLUB NAME ────────────────────────────────────
        c.setFillColor(colors.HexColor('#E8E8E8'))
        c.setFont('Helvetica-Bold', 32)
        c.drawCentredString(w/2, h - 42*mm, 'FALCONS FC')

        c.setFillColor(colors.HexColor('#4A90D9'))
        c.setFont('Helvetica', 11)
        c.drawCentredString(w/2, h - 52*mm, 'OFFICIAL MATCH TICKET')

        # Divider line under header
        c.setStrokeColor(colors.HexColor('#4A90D9'))
        c.setLineWidth(1)
        c.line(20*mm, h - 58*mm, w - 20*mm, h - 58*mm)

        # ── MATCH NAME ───────────────────────────────────
        c.setFillColor(colors.HexColor('#E8E8E8'))
        c.setFont('Helvetica-Bold', 18)
        c.drawCentredString(
            w/2, h - 70*mm,
            f'{ticket.match.home_team.name} vs {ticket.match.away_team.name}'
        )

        c.setFillColor(colors.HexColor('#8BA3C1'))
        c.setFont('Helvetica', 11)
        c.drawCentredString(w/2, h - 78*mm, ticket.match.competition.name)

        # ── MAIN TICKET BODY ─────────────────────────────
        # White card area
        c.setFillColor(colors.HexColor('#111D2E'))
        c.setStrokeColor(colors.HexColor('#1E3A5F'))
        c.setLineWidth(1)
        c.roundRect(15*mm, 30*mm, w - 30*mm, h - 110*mm, 8, fill=1, stroke=1)

        # ── MATCH DETAILS ROW ────────────────────────────
        detail_y = h - 108*mm
        details = [
            ('DATE', ticket.match.date.strftime('%d %b %Y')),
            ('KICK-OFF', ticket.match.date.strftime('%H:%M')),
            ('STADIUM', ticket.match.stadium.name),
            ('CITY', ticket.match.stadium.city),
        ]

        col_w = (w - 30*mm) / 4
        for i, (label, value) in enumerate(details):
            x = 15*mm + i * col_w + col_w/2

            # Label
            c.setFillColor(colors.HexColor('#8BA3C1'))
            c.setFont('Helvetica', 7)
            c.drawCentredString(x, detail_y, label)

            # Value
            c.setFillColor(colors.HexColor('#E8E8E8'))
            c.setFont('Helvetica-Bold', 11)
            c.drawCentredString(x, detail_y - 7*mm, value)

        # ── PERFORATED DIVIDER ───────────────────────────
        perf_y = h - 128*mm
        c.setStrokeColor(colors.HexColor('#1E3A5F'))
        c.setLineWidth(1)
        c.setDash(4, 4)
        c.line(20*mm, perf_y, w - 20*mm, perf_y)
        c.setDash()

        # Perforation circles
        c.setFillColor(colors.HexColor('#0D1B2E'))
        c.circle(15*mm, perf_y, 4*mm, fill=1, stroke=0)
        c.circle(w - 15*mm, perf_y, 4*mm, fill=1, stroke=0)

        # ── SEAT INFO BOXES ───────────────────────────────
        seat_y = h - 148*mm
        seat_items = [
            ('SECTION', ticket.seat.row.section.name),
            ('ROW', str(ticket.seat.row.row_number)),
            ('SEAT', str(ticket.seat.seat_number)),
            ('PRICE', f'EUR {ticket.final_price}'),
        ]

        box_w = (w - 50*mm) / 4
        for i, (label, value) in enumerate(seat_items):
            x = 25*mm + i * (box_w + 3*mm)

            # Box background
            c.setFillColor(colors.HexColor('#0D1B2E'))
            c.setStrokeColor(colors.HexColor('#1E3A5F'))
            c.setLineWidth(1)
            c.roundRect(x, seat_y - 14*mm, box_w, 28*mm, 4, fill=1, stroke=1)

            # Label
            c.setFillColor(colors.HexColor('#8BA3C1'))
            c.setFont('Helvetica', 7)
            c.drawCentredString(x + box_w/2, seat_y + 8*mm, label)

            # Value
            c.setFillColor(colors.HexColor('#4A90D9'))
            c.setFont('Helvetica-Bold', 14)
            c.drawCentredString(x + box_w/2, seat_y - 5*mm, value)

        # ── TICKET HOLDER ─────────────────────────────────
        holder_y = h - 175*mm
        c.setFillColor(colors.HexColor('#8BA3C1'))
        c.setFont('Helvetica', 8)
        c.drawString(25*mm, holder_y, 'TICKET HOLDER')

        c.setFillColor(colors.HexColor('#E8E8E8'))
        c.setFont('Helvetica-Bold', 13)
        c.drawString(25*mm, holder_y - 7*mm,
                     ticket.holder_name or ticket.user.get_full_name() or ticket.user.username)

        c.setFillColor(colors.HexColor('#8BA3C1'))
        c.setFont('Helvetica', 10)
        c.drawString(25*mm, holder_y - 14*mm, ticket.user.email)

        # ── BOOKING REF ───────────────────────────────────
        c.setFillColor(colors.HexColor('#8BA3C1'))
        c.setFont('Helvetica', 8)
        c.drawString(25*mm, holder_y - 24*mm, f'BOOKING REF: #{ticket.id}')

        # ── QR CODE ───────────────────────────────────────
        ticket.refresh_from_db()
        if ticket.qr_code:
            try:
                qr_path = ticket.qr_code.path
                if os.path.exists(qr_path):
                    # QR white background
                    c.setFillColor(colors.white)
                    c.roundRect(w - 68*mm, holder_y - 30*mm, 48*mm, 48*mm, 4, fill=1, stroke=0)
                    qr_img = ImageReader(qr_path)
                    c.drawImage(
                        qr_img,
                        w - 66*mm, holder_y - 28*mm,
                        width=44*mm, height=44*mm
                    )
                    c.setFillColor(colors.HexColor('#8BA3C1'))
                    c.setFont('Helvetica', 7)
                    c.drawCentredString(w - 44*mm, holder_y - 35*mm, 'Scan at entrance')
            except Exception as qr_error:
                logger.warning(f'Could not embed QR: {qr_error}')

        # ── BLUE BOTTOM BAR ───────────────────────────────
        c.setFillColor(colors.HexColor('#1B3A6B'))
        c.rect(0, 0, w, 22*mm, fill=1, stroke=0)

        # Bottom accent line
        c.setFillColor(colors.HexColor('#4A90D9'))
        c.rect(0, 21*mm, w, 1.5*mm, fill=1, stroke=0)

        # Footer text
        c.setFillColor(colors.HexColor('#8BA3C1'))
        c.setFont('Helvetica', 8)
        c.drawCentredString(
            w/2, 13*mm,
            'This ticket is non-transferable. Present QR code at stadium entrance.'
        )
        c.setFillColor(colors.HexColor('#4A90D9'))
        c.setFont('Helvetica-Bold', 8)
        c.drawCentredString(w/2, 7*mm, 'FALCONS FC — FALCONS ARENA, MESSINA')

        c.save()
        buffer.seek(0)

        filename = f'ticket_{ticket_id}.pdf'
        ticket.pdf_ticket.save(filename, ContentFile(buffer.read()), save=True)

        logger.info(f'PDF generated for ticket #{ticket_id}')
        return f'PDF generated for ticket #{ticket_id}'

    except Exception as e:
        logger.error(f'Failed to generate PDF: {e}')
        return f'Failed: {e}'

# ─────────────────────────────────────────
# TASK 7 — Recalculate ML prices (hourly)
# Placeholder — Sprint 4 plugs in here
# ─────────────────────────────────────────

@shared_task(name='core.tasks.recalculate_prices')
def recalculate_prices():
    from core.models import Match, Section, Ticket
    updated = 0
    matches = Match.objects.filter(status='upcoming').select_related(
        'competition', 'stadium'
    )
    for match in matches:
        sections = Section.objects.filter(stadium=match.stadium)
        for section in sections:
            total = section.total_seats()
            if total == 0:
                continue
            booked = Ticket.objects.filter(
                match=match,
                seat__row__section=section,
                status__in=['booked', 'used']
            ).count()
            occupancy = booked / total
            demand_score = min(occupancy * match.match_importance_score, 1.0)
            dynamic_price = round(
                float(section.base_price) * (1 + demand_score), 2
            )
            updated += 1
    logger.info(f'Price recalculation complete — {updated} section/match pairs updated.')
    return f'Recalculated {updated} prices.'


# ─────────────────────────────────────────
# TASK 8 — Process booking (chain of tasks)
# Triggered after booking confirmation
# ─────────────────────────────────────────

@shared_task(name='core.tasks.process_booking')
def process_booking(booking_id, ticket_id):
    from celery import chain
    from datetime import timedelta
    workflow = chain(
        generate_qr_code.si(ticket_id),
        generate_pdf_ticket.si(ticket_id).set(countdown=2),
        send_booking_confirmation_email.si(booking_id).set(countdown=3),
    )
    workflow.delay()
    logger.info(f'Booking processing chain started for booking #{booking_id}')
    return f'Processing chain started for booking #{booking_id}'


@shared_task(name='core.tasks.expire_past_matches')
def expire_past_matches():
    from core.models import Match
    expired = Match.objects.filter(
        status='upcoming',
        date__lt=timezone.now()
    )
    count = expired.count()
    expired.update(status='finished')
    if count > 0:
        logger.info(f'Marked {count} matches as finished.')
    return f'Expired {count} matches.'

@shared_task(name='core.tasks.send_cancellation_email')
def send_cancellation_email(ticket_id):
    from core.models import Ticket
    try:
        ticket = Ticket.objects.select_related(
            'user', 'match__home_team', 'match__away_team',
            'match__stadium', 'seat__row__section'
        ).get(id=ticket_id)

        subject = f'Booking Cancelled — {ticket.match}'
        message = render_to_string('emails/cancellation.html', {
            'ticket': ticket,
            'user': ticket.user,
        })

        send_mail(
            subject=subject,
            message='',
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[ticket.user.email],
            html_message=message,
            fail_silently=False,
        )
        logger.info(f'Cancellation email sent for ticket #{ticket_id}')
        return f'Cancellation email sent for ticket #{ticket_id}'

    except Exception as e:
        logger.error(f'Failed to send cancellation email: {e}')
        return f'Failed: {e}'