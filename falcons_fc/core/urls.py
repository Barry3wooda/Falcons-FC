from django.urls import path
from . import views

urlpatterns = [
    # ── Home ──────────────────────────────────────
    path('', views.home_view, name='home'),

    # ── Auth ──────────────────────────────────────
    path('auth/register/', views.register_view, name='register'),
    path('auth/login/', views.CustomLoginView.as_view(), name='login'),
    path('auth/logout/', views.logout_view, name='logout'),
    path('auth/profile/', views.profile_view, name='profile'),

    # ── Matches ───────────────────────────────────
    path('matches/', views.match_list_view, name='match_list'),
    path('matches/<int:match_id>/', views.match_detail_view, name='match_detail'),

    # ── Seat Map ──────────────────────────────────
    path('matches/<int:match_id>/seats/<int:section_id>/', views.seat_map_view, name='seat_map'),

    # ── Booking ───────────────────────────────────
    path('booking/lock/', views.lock_seat_view, name='lock_seat'),
    path('booking/summary/', views.booking_summary_view, name='booking_summary'),
    path('booking/payment/', views.payment_view, name='payment'),
    path('booking/confirm/', views.booking_confirm_view, name='booking_confirm'),
    path('booking/<int:booking_id>/', views.booking_detail_view, name='booking_detail'),

    # ── Ticket ────────────────────────────────────
    path('ticket/<int:ticket_id>/', views.ticket_detail_view, name='ticket_detail'),
    # ── Waitlist ──────────────────────────────────
    path('waitlist/join/<int:match_id>/<int:section_id>/', views.join_waitlist_view, name='join_waitlist'),
    path('waitlist/confirm/<int:match_id>/<int:section_id>/', views.waitlist_confirm_view, name='waitlist_confirm'),
    # ── Group Seat Allocator ───────────────────────────────
    path('matches/<int:match_id>/group/<int:section_id>/', views.group_seat_view, name='group_seat'),
    path('booking/group/lock/', views.lock_group_seats_view, name='lock_group_seats'),
    path('booking/group/summary/', views.group_booking_summary_view, name='group_booking_summary'),
    path('booking/group/payment/', views.group_payment_view, name='group_payment'),
    path('booking/group/confirm/', views.group_booking_confirm_view, name='group_booking_confirm'),
    path('ticket/<int:ticket_id>/cancel/', views.cancel_ticket_view, name='cancel_ticket'),
]