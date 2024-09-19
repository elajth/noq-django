from django.db.models import Q
from ninja import NinjaAPI, Schema, ModelSchema, Router
from ninja.errors import HttpError
from django.http import JsonResponse
from datetime import datetime, timedelta, date

from backend.models import (
    Client,
    Host,
    Region,
    Product,
    Booking,
    Available,
    Product,
    BookingStatus,
    State,
    Invoice,
    InvoiceStatus,
)

from .api_schemas import (
    UserShelterStayCountSchema,
    RegionSchema,
    UserSchema,
    UserPostSchema,
    HostSchema,
    HostPostSchema,
    HostPatchSchema,
    ProductSchema,
    BookingSchema,
    BookingPostSchema,
    BookingCounterSchema,
    AvailableSchema,
    AvailablePerDateSchema,
    InvoiceCreateSchema,
    InvoiceResponseSchema,
    UserStaySummarySchema,
)

from backend.auth import group_auth

from typing import List, Dict, Optional
from django.shortcuts import get_object_or_404
from datetime import date, timedelta
router = Router(auth=lambda request: group_auth(request, "caseworker"))  # request defineras vid call, gruppnamnet är statiskt

# api/caseworker/ returns the host information
@router.get("/", response=str, tags=["caseworker-frontpage"])
def get_caseworker_data(request):
    try:
        host = Host.objects.get(users=request.user)
        return host
    except:
        raise HttpError(200, "User is not a caseworker.")
@router.get("/bookings/pending", response=List[BookingSchema], tags=["caseworker-manage-requests"])
def get_pending_bookings(request, limiter: Optional[int] = None):  # Limiter example /pending?limiter=10 for 10 results, empty returns all
    hosts = Host.objects.filter(users=request.user)
    bookings = []
    for host in hosts:
        host_bookings = Booking.objects.filter(product__host=host, status__description='pending')
        for booking in host_bookings:
            bookings.append(booking)

    if limiter is not None and limiter > 0:
        return bookings[:limiter]

    return bookings


@router.patch("/bookings/{booking_id}/accept", response=BookingSchema, tags=["caseworker-manage-requests"])
def appoint_pending_booking(request, booking_id: int):
    hosts = Host.objects.filter(users=request.user)
    booking = get_object_or_404(Booking, id=booking_id, product__host__in=hosts, status__description='pending')

    try:
        booking.status = BookingStatus.objects.get(description='accepted')
        booking.save()
        return booking
    except BookingStatus.DoesNotExist:
        raise HttpError(404, detail="Booking status does not exist.")


@router.patch("/bookings/{booking_id}/decline", response=BookingSchema, tags=["caseworker-manage-requests"])
def decline_pending_booking(request, booking_id: int):
    hosts = Host.objects.filter(users=request.user)
    booking = get_object_or_404(Booking, id=booking_id, product__host__in=hosts, status__description='pending')

    try:
        booking.status = BookingStatus.objects.get(description='declined')
        booking.save()
        return booking
    except BookingStatus.DoesNotExist:
        raise HttpError(404, detail="Booking status does not exist.")



@router.get("/guests/nights/count/{user_id}/{start_date}/{end_date}", response=UserShelterStayCountSchema, tags=["caseworker-frontpage"])
def get_user_shelter_stay_count(request, user_id: int, start_date: str, end_date: str):
    try:
        start_date = date.fromisoformat(start_date)
        end_date = date.fromisoformat(end_date)

        user_bookings = Booking.objects.filter(
            user_id=user_id,
            start_date__lte=end_date,
            end_date__gte=start_date
        ).select_related(
            'product__host__region'
        ).values(
            'user_id',
            'product__host__id',
            'product__host__name',
            'product__host__street',
            'product__host__postcode',
            'product__host__city',
            'product__host__region__name',
            'product__host__region__id',
            'start_date',
            'end_date'
        )

        total_nights = 0
        user_stay_counts = []

        for booking in user_bookings:
            nights = (min(booking['end_date'], end_date) - max(booking['start_date'], start_date)).days
            if nights > 0:
                total_nights += nights

                host_data = {
                    'id': booking['product__host__id'],
                    'name': booking['product__host__name'],
                    'street': booking['product__host__street'],
                    'postcode': booking['product__host__postcode'],
                    'city': booking['product__host__city'],
                    'region': {
                        'id': booking['product__host__region__id'],
                        'name': booking['product__host__region__name']
                    }
                }
                host = HostSchema(**host_data)

                user_stay_counts.append(
                    UserStaySummarySchema(
                        total_nights=nights,
                        start_date=booking['start_date'].isoformat(),
                        end_date=booking['end_date'].isoformat(),
                        host=host
                    )
                )

        response_data = UserShelterStayCountSchema(
            user_id=user_id,
            user_stay_counts=user_stay_counts
        )

        return response_data

    except ValueError as ve:
        return JsonResponse({'detail': "Invalid date format."}, status=400)

    except Exception as e:
        return JsonResponse({'detail': "An internal error occurred. Please try again later."}, status=500)
