from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import (
    CustomUser, Stadium, Section, Row, Seat,
    Competition, Team, Match, Ticket, Booking, Waitlist
)


# ─────────────────────────────────────────
# USER
# ─────────────────────────────────────────

@admin.register(CustomUser)
class CustomUserAdmin(UserAdmin):
    list_display = ('username', 'email', 'phone', 'is_staff', 'is_active', 'date_joined')
    list_filter = ('is_staff', 'is_active')
    search_fields = ('username', 'email', 'phone')
    fieldsets = UserAdmin.fieldsets + (
        ('Additional Info', {'fields': ('phone', 'avatar')}),
    )


# ─────────────────────────────────────────
# STADIUM HIERARCHY
# ─────────────────────────────────────────

class SectionInline(admin.TabularInline):
    model = Section
    extra = 0
    fields = ('name', 'base_price', 'description')


@admin.register(Stadium)
class StadiumAdmin(admin.ModelAdmin):
    list_display = ('name', 'city', 'capacity')
    search_fields = ('name', 'city')
    inlines = [SectionInline]


class RowInline(admin.TabularInline):
    model = Row
    extra = 0
    fields = ('row_number',)


@admin.register(Section)
class SectionAdmin(admin.ModelAdmin):
    list_display = ('name', 'stadium', 'base_price', 'total_seats')
    list_filter = ('stadium', 'name')
    search_fields = ('name',)
    inlines = [RowInline]

    def total_seats(self, obj):
        return obj.total_seats()
    total_seats.short_description = 'Total Seats'


class SeatInline(admin.TabularInline):
    model = Seat
    extra = 0
    fields = ('seat_number', 'is_active')


@admin.register(Row)
class RowAdmin(admin.ModelAdmin):
    list_display = ('__str__', 'section', 'row_number')
    list_filter = ('section__stadium', 'section')
    inlines = [SeatInline]


@admin.register(Seat)
class SeatAdmin(admin.ModelAdmin):
    list_display = ('__str__', 'row', 'seat_number', 'is_active')
    list_filter = ('is_active', 'row__section__stadium', 'row__section')
    search_fields = ('seat_number',)


# ─────────────────────────────────────────
# COMPETITION & TEAMS
# ─────────────────────────────────────────

@admin.register(Competition)
class CompetitionAdmin(admin.ModelAdmin):
    list_display = ('name', 'competition_type', 'get_importance_score')
    list_filter = ('competition_type',)
    search_fields = ('name',)

    def get_importance_score(self, obj):
        return obj.get_importance_score()
    get_importance_score.short_description = 'Importance Score'


@admin.register(Team)
class TeamAdmin(admin.ModelAdmin):
    list_display = ('name', 'city')
    search_fields = ('name', 'city')


# ─────────────────────────────────────────
# MATCH
# ─────────────────────────────────────────

@admin.register(Match)
class MatchAdmin(admin.ModelAdmin):
    list_display = ('__str__', 'competition', 'date', 'status', 'match_importance_score', 'occupancy_rate')
    list_filter = ('status', 'competition', 'stadium')
    search_fields = ('home_team__name', 'away_team__name')
    date_hierarchy = 'date'
    readonly_fields = ('match_importance_score',)

    def occupancy_rate(self, obj):
        rate = obj.occupancy_rate()
        return f"{int(rate * 100)}%"
    occupancy_rate.short_description = 'Occupancy'


# ─────────────────────────────────────────
# TICKET
# ─────────────────────────────────────────

@admin.register(Ticket)
class TicketAdmin(admin.ModelAdmin):
    list_display = ('__str__', 'user', 'status', 'final_price', 'lock_expires_at', 'is_lock_expired')
    list_filter = ('status', 'match__competition', 'seat__row__section')
    search_fields = ('user__username', 'match__home_team__name', 'match__away_team__name')
    readonly_fields = ('created_at', 'updated_at', 'is_lock_expired')

    def is_lock_expired(self, obj):
        return obj.is_lock_expired()
    is_lock_expired.boolean = True
    is_lock_expired.short_description = 'Lock Expired?'


# ─────────────────────────────────────────
# BOOKING
# ─────────────────────────────────────────

@admin.register(Booking)
class BookingAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'match', 'total_price', 'payment_status', 'created_at')
    list_filter = ('payment_status', 'match__competition')
    search_fields = ('user__username', 'match__home_team__name')
    readonly_fields = ('created_at',)
    filter_horizontal = ('tickets',)


# ─────────────────────────────────────────
# WAITLIST
# ─────────────────────────────────────────

@admin.register(Waitlist)
class WaitlistAdmin(admin.ModelAdmin):
    list_display = ('user', 'match', 'section', 'position', 'is_promoted', 'created_at')
    list_filter = ('is_promoted', 'section', 'match')
    search_fields = ('user__username',)
    readonly_fields = ('created_at',)