from django.db import models
from django.contrib.auth.models import AbstractUser
from django.utils import timezone


# ─────────────────────────────────────────
# USER
# ─────────────────────────────────────────

class CustomUser(AbstractUser):
    phone = models.CharField(max_length=20, blank=True, null=True)
    avatar = models.ImageField(upload_to='avatars/', blank=True, null=True)

    def __str__(self):
        return self.username


# ─────────────────────────────────────────
# STADIUM HIERARCHY
# ─────────────────────────────────────────

class Stadium(models.Model):
    name = models.CharField(max_length=100)
    city = models.CharField(max_length=100)
    capacity = models.PositiveIntegerField()

    def __str__(self):
        return self.name


class Section(models.Model):
    SECTION_CHOICES = [
        ('VIP', 'VIP'),
        ('Tribune', 'Tribune'),
        ('Curve Nord', 'Curve Nord'),
        ('Curve Sud', 'Curve Sud'),
    ]
    stadium = models.ForeignKey(Stadium, on_delete=models.CASCADE, related_name='sections')
    name = models.CharField(max_length=50, choices=SECTION_CHOICES)
    base_price = models.DecimalField(max_digits=8, decimal_places=2)
    description = models.TextField(blank=True, null=True)

    def __str__(self):
        return f"{self.stadium.name} — {self.name}"

    def total_seats(self):
        return Seat.objects.filter(row__section=self).count()

    def available_seats_for_match(self, match):
        booked = Ticket.objects.filter(
            match=match,
            seat__row__section=self,
            status__in=['locked', 'booked', 'used']
        ).values_list('seat_id', flat=True)
        return Seat.objects.filter(row__section=self, is_active=True).exclude(id__in=booked)


class Row(models.Model):
    section = models.ForeignKey(Section, on_delete=models.CASCADE, related_name='rows')
    row_number = models.PositiveIntegerField()

    class Meta:
        ordering = ['row_number']
        unique_together = ['section', 'row_number']

    def __str__(self):
        return f"{self.section.name} — Row {self.row_number}"


class Seat(models.Model):
    row = models.ForeignKey(Row, on_delete=models.CASCADE, related_name='seats')
    seat_number = models.PositiveIntegerField()
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['seat_number']
        unique_together = ['row', 'seat_number']

    def __str__(self):
        return f"{self.row.section.name} — Row {self.row.row_number} — Seat {self.seat_number}"


# ─────────────────────────────────────────
# COMPETITION & TEAMS
# ─────────────────────────────────────────

class Competition(models.Model):
    COMPETITION_TYPES = [
        ('League', 'League'),
        ('Cup', 'Cup'),
        ('Derby', 'Derby'),
    ]
    name = models.CharField(max_length=100)
    competition_type = models.CharField(max_length=20, choices=COMPETITION_TYPES)

    def get_importance_score(self):
        scores = {'Derby': 3, 'Cup': 2.5, 'League': 1}
        return scores.get(self.competition_type, 1)

    def __str__(self):
        return f"{self.name} ({self.competition_type})"


class Team(models.Model):
    name = models.CharField(max_length=100)
    logo = models.ImageField(upload_to='team_logos/', blank=True, null=True)
    city = models.CharField(max_length=100, blank=True, null=True)

    def __str__(self):
        return self.name


# ─────────────────────────────────────────
# MATCH
# ─────────────────────────────────────────

class Match(models.Model):
    STATUS_CHOICES = [
        ('upcoming', 'Upcoming'),
        ('live', 'Live'),
        ('finished', 'Finished'),
        ('cancelled', 'Cancelled'),
    ]
    home_team = models.ForeignKey(Team, on_delete=models.CASCADE, related_name='home_matches')
    away_team = models.ForeignKey(Team, on_delete=models.CASCADE, related_name='away_matches')
    competition = models.ForeignKey(Competition, on_delete=models.CASCADE, related_name='matches')
    stadium = models.ForeignKey(Stadium, on_delete=models.CASCADE, related_name='matches')
    date = models.DateTimeField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='upcoming')
    match_importance_score = models.FloatField(default=1.0)
    description = models.TextField(blank=True, null=True)
    external_ticket_url = models.URLField(blank=True, null=True, help_text='External ticket link for away matches')
    is_away_match = models.BooleanField(default=False, help_text='True if Falcons FC plays away')
    cancelled_at = models.DateTimeField(null=True, blank=True)
    cancellation_reason = models.CharField(max_length=500, blank=True, null=True)

    class Meta:
        ordering = ['date']

    def save(self, *args, **kwargs):
        self.match_importance_score = self.competition.get_importance_score()
        super().save(*args, **kwargs)

    def occupancy_rate(self):
        total = Seat.objects.filter(row__section__stadium=self.stadium, is_active=True).count()
        if total == 0:
            return 0
        booked = Ticket.objects.filter(
            match=self,
            status__in=['booked', 'used']
        ).count()
        return round(booked / total, 2)

    def __str__(self):
        return f"{self.home_team} vs {self.away_team} — {self.date.strftime('%d %b %Y')}"


# ─────────────────────────────────────────
# TICKET
# ─────────────────────────────────────────

class Ticket(models.Model):
    STATUS_CHOICES = [
        ('available', 'Available'),
        ('locked', 'Locked'),
        ('booked', 'Booked'),
        ('used', 'Used'),
    ]
    seat = models.ForeignKey(Seat, on_delete=models.CASCADE, related_name='tickets')
    match = models.ForeignKey(Match, on_delete=models.CASCADE, related_name='tickets')
    user = models.ForeignKey(CustomUser, on_delete=models.SET_NULL, null=True, blank=True, related_name='tickets')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='available')
    final_price = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    lock_expires_at = models.DateTimeField(null=True, blank=True)
    qr_code = models.ImageField(upload_to='qr_codes/', blank=True, null=True)
    pdf_ticket = models.FileField(upload_to='pdf_tickets/', blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    holder_name = models.CharField(max_length=200, blank=True, null=True)

    class Meta:
        unique_together = ['seat', 'match']

    def is_lock_expired(self):
        if self.lock_expires_at and self.status == 'locked':
            return timezone.now() > self.lock_expires_at
        return False

    def __str__(self):
        return f"Ticket — {self.match} — {self.seat} — {self.status}"


# ─────────────────────────────────────────
# BOOKING
# ─────────────────────────────────────────

class Booking(models.Model):
    PAYMENT_STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('paid', 'Paid'),
        ('failed', 'Failed'),
        ('refunded', 'Refunded'),
    ]
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='bookings')
    match = models.ForeignKey(Match, on_delete=models.CASCADE, related_name='bookings')
    tickets = models.ManyToManyField(Ticket, related_name='booking')
    total_price = models.DecimalField(max_digits=10, decimal_places=2)
    payment_status = models.CharField(max_length=20, choices=PAYMENT_STATUS_CHOICES, default='pending')
    stripe_payment_intent = models.CharField(max_length=200, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Booking #{self.id} — {self.user.username} — {self.match}"


# ─────────────────────────────────────────
# WAITLIST
# ─────────────────────────────────────────

class Waitlist(models.Model):
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='waitlist_entries')
    match = models.ForeignKey(Match, on_delete=models.CASCADE, related_name='waitlist')
    section = models.ForeignKey(Section, on_delete=models.CASCADE, related_name='waitlist')
    position = models.PositiveIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)
    is_promoted = models.BooleanField(default=False)

    class Meta:
        ordering = ['position']
        unique_together = ['user', 'match', 'section']

    def __str__(self):
        return f"Waitlist — {self.user.username} — {self.match} — {self.section.name} — Position {self.position}"