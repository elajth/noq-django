from django.db.models import Q
from ninja import NinjaAPI, Schema, ModelSchema, Router
from ninja.errors import HttpError
from ninja.responses import Response
from django.db import transaction
from datetime import datetime, timedelta, date
from django.http import JsonResponse
from backend.auth import group_auth
from django.contrib.auth.models import User
from django.core.paginator import Paginator
from django.contrib.auth.models import User, Group
from typing import List, Dict, Optional
from django.shortcuts import get_object_or_404
from django.db import transaction, IntegrityError
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
    BookingUpdateSchema,
    ProductSchemaWithPlacesLeft,
    UserStaySummarySchema,
    UserShelterStayCountSchema,
    UserInfoSchema
)


router = Router(auth=lambda request: group_auth(request, "caseworker"))  # request defineras vid call, gruppnamnet är statiskt

@router.get("/bookings/pending", response=List[BookingSchema], tags=["caseworker-manage-requests"])
def get_pending_bookings(request, limiter: Optional[int] = None):  # Limiter example /pending?limiter=10 for 10 results, empty returns all
    hosts = Host.objects.filter(caseworkers=request.user)
    bookings = []
    for host in hosts:
        host_bookings = Booking.objects.filter(product__host=host, status__description='pending')
        for booking in host_bookings:
            bookings.append(booking)

    if limiter is not None and limiter > 0:
        return bookings[:limiter]

    return bookings


@router.patch("/bookings/batch/accept", response={200: dict, 400: dict}, tags=["caseworker-manage-requests"])
def batch_appoint_pending_booking(request, booking_ids: list[BookingUpdateSchema]):
    hosts = Host.objects.filter(caseworkers=request.user)
    # Use a transaction to ensure all or nothing behavior
    with transaction.atomic():
        errors = []
        for item in booking_ids:
            booking_id = item.booking_id
            booking = get_object_or_404(Booking, id=booking_id, product__host__in=hosts, status__description='pending')
            try:
                booking.status = BookingStatus.objects.get(description='accepted')
                booking.save()
            except Exception as e:
                # Collect errors for any failed updates
                errors.append({'booking': item.booking_id, 'error': str(e)})
        if errors:
            return 400, {'message': 'Some updates failed', 'errors': errors}

    return 200, {'message': 'Batch update successful'}


@router.patch("/bookings/{booking_id}/accept", response=BookingSchema, tags=["caseworker-manage-requests"])
def appoint_pending_booking(request, booking_id: int):
    hosts = Host.objects.filter(caseworkers=request.user)
    booking = get_object_or_404(Booking, id=booking_id, product__host__in=hosts, status__description='pending')

    try:
        booking.status = BookingStatus.objects.get(description='accepted')
        booking.save()
        return booking
    except BookingStatus.DoesNotExist:
        raise HttpError(404, detail="Booking status does not exist.")


@router.patch("/bookings/{booking_id}/decline", response=BookingSchema, tags=["caseworker-manage-requests"])
def decline_pending_booking(request, booking_id: int):
    hosts = Host.objects.filter(caseworkers=request.user)
    booking = get_object_or_404(Booking, id=booking_id, product__host__in=hosts, status__description='pending')

    try:
        booking.status = BookingStatus.objects.get(description='advised_against')
        booking.save()
        return booking
    except BookingStatus.DoesNotExist:
        raise HttpError(404, "Booking status does not exist.")


# This API can be used to undo previous decision for accept or decline
# Bookings that have status checked_in can't be changed.
@router.patch("/bookings/{booking_id}/setpending", response=BookingSchema, tags=["caseworker-manage-requests"])
def set_booking_pending(request, booking_id: int):
    hosts = Host.objects.filter(caseworkers=request.user)
    valid_statuses = ['accepted', 'declined']
    booking = get_object_or_404(Booking, id=booking_id, product__host__in=hosts, status__description__in=valid_statuses)

    try:
        booking.status = BookingStatus.objects.get(description='pending')
        booking.save()
        return booking
    except BookingStatus.DoesNotExist:
        raise HttpError(404, "Booking status does not exist.")
    

@router.get("/available_all", response=List[ProductSchemaWithPlacesLeft], tags=["caseworker-available"])
def get_available_places_all(request):
    # Retrieve all hosts the caseworker is responsible for
    hosts = Host.objects.filter(caseworkers=request.user)  # Assuming caseworkers are linked to Hosts via the 'users' relationship
    
    if not hosts.exists():
        # No hosts associated with the caseworker, return a 404 error
        raise HttpError(404, "No hosts associated with this caseworker.")
    
    available_products = []
    
    # Loop through each host and get the products
    for host in hosts:
        products = Product.objects.filter(host=host)
        
        # Loop through each product and check available places
        for product in products:
            # Find availability for the product
            available = Available.objects.filter(product=product).first()
            
            # Calculate the number of places left
            places_left = available.places_left if available else product.total_places
            
            # Append the product with the remaining places to the list
            available_products.append(
                ProductSchemaWithPlacesLeft(
                    id=product.id,
                    name=product.name,
                    description=product.description,
                    total_places=product.total_places,
                    host=product.host,  
                    type=product.type,
                    places_left=places_left
                )
            )
    
    # Return the full list of available products across all hosts
    return available_products


@router.get("/guests/nights/count/{user_id}/{start_date}/{end_date}", response={400: dict, 200: UserShelterStayCountSchema}, tags=["caseworker-statistics"])
def get_user_shelter_stay_count(request, user_id: int, start_date: str, end_date: str, page: int = 1, per_page: int = 20):
    try:

        client = Client.objects.get(user=User.objects.filter(id=user_id).first())

        if not client:
            return JsonResponse( {"error": "Användare finns inte."}, status=400)
        
        start_date = date.fromisoformat(start_date)
        end_date = date.fromisoformat(end_date)

        user = User.objects.get(id=user_id)

        user_bookings = Booking.objects.filter(
            user_id=client,
            start_date__lte=end_date,
            end_date__gte=start_date
        ).select_related(
            'product__host__region'
        ).only(
            'start_date', 'end_date', 'product__host__id', 'product__host__name',
            'product__host__street', 'product__host__postcode', 'product__host__city', 'product__host__region__id',
            'product__host__region__name'
        )

        paginator = Paginator(user_bookings, per_page)
        user_stay_counts_page = paginator.get_page(page)

        total_nights = 0
        user_stay_counts = []

        for booking in user_stay_counts_page:
            nights = (min(booking.end_date, end_date) - max(booking.start_date, start_date)).days
            if nights > 0:
                total_nights += nights

                host = booking.product.host  
                host_data = {
                    'id': host.id,
                    'name': host.name,
                    'street': host.street,
                    'postcode': host.postcode,
                    'city': host.city,
                    'region': {
                        'id': host.region.id,
                        'name': host.region.name
                    },
                }

                user_stay_counts.append(
                    UserStaySummarySchema(
                        total_nights=nights,
                        start_date=booking.start_date.isoformat(),
                        end_date=booking.end_date.isoformat(),
                        host=host_data
                    )
                )

        response_data = {
            "user_id": user_id,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "total_nights": total_nights,
            "user_stay_counts": user_stay_counts,
            "total_pages": paginator.num_pages,
            "current_page": user_stay_counts_page.number,
        }

        return response_data

    except ValueError as ve:
        return JsonResponse({'detail': "Something went wrong"}, status=400)

    except Exception as e:
        return JsonResponse({'detail': "An internal error occurred. Please try again later."}, status=500)


@router.get("/guests/nights/count/{start_date}/{end_date}", response=List[UserShelterStayCountSchema], tags=["caseworker-statistics"])
def get_shelter_stay_count(request, start_date: str, end_date: str, page: int = 1, per_page: int = 20):
    try:
        start_date = date.fromisoformat(start_date)
        end_date = date.fromisoformat(end_date)

        bookings = Booking.objects.filter(
            start_date__gte=start_date, end_date__lte=end_date).select_related('user', 'user__user', 'product__host')

        # Group data by user in a dictionary
        user_data = {}
        for booking in bookings:
            client = booking.user
            user_id = client.user.id
            host = booking.product.host
            host_data = {
                'id': host.id,
                'name': host.name,
                'street': host.street,
                'postcode': host.postcode,
                'city': host.city,
                'region': {
                    'id': host.region.id,
                    'name': host.region.name
                },
            }

            # Calculate total nights
            total_nights = (min(booking.end_date, end_date) - max(booking.start_date, start_date)).days

            # Initialize user data if not present
            if user_id not in user_data:
                user_data[user_id] = {
                    "user_id": user_id,
                    "first_name": client.first_name,
                    "last_name": client.last_name,
                    "user_stay_counts": []
                }

            # Append each stay summary for the user
            user_data[user_id]["user_stay_counts"].append({
                "total_nights": total_nights,
                "start_date": booking.start_date,
                "end_date": booking.end_date,
                "host": host_data
            })

        # Convert the grouped dictionary to a list for pagination
        grouped_data = list(user_data.values())

        paginator = Paginator(grouped_data, per_page)
        user_stay_counts_page = paginator.get_page(page)

        return user_stay_counts_page.object_list

    except ValueError as ve:
        return JsonResponse({'detail': "Something went wrong"}, status=400)

    except Exception as e:
        return JsonResponse({'detail': "An internal error occurred. Please try again later."}, status=500)


"""
Get information about a user with user ID
"""
@router.get("/user/{user_id}", response=UserInfoSchema, tags=["caseworker-user-management"])
def get_user_information(request, user_id: int):

    user = get_object_or_404(User, id=user_id)  
    
    client = get_object_or_404(Client, user=user)  
    
    user_data = UserInfoSchema(
        first_name=client.first_name,
        last_name=client.last_name,
        email=client.email,
        username=user.username,
        phone=client.phone,
        gender=client.gender,
        street=client.street,
        postcode=client.postcode,
        city=client.city,
        region=client.region.id if client.region else None, 
        country=client.country,
        day_of_birth=client.day_of_birth.isoformat() if client.day_of_birth else None,
        requirements=client.requirements,
        unokod=client.unokod,
        # personnr_lastnr=client.personnr_lastnr
    )

    return user_data

""" 
Get information about USERS 
"""
@router.get("/users", response=List[UserInfoSchema], tags=["caseworker-user-management"])
def get_all_users(request):
    clients= Client.objects.all()
    user_data_list = [
        UserInfoSchema(
            first_name=client.first_name,
            last_name=client.last_name,
            email=client.email,
            username=client.user.username,
            phone=client.phone,
            gender=client.gender,
            street=client.street,
            postcode=client.postcode,
            city=client.city,
            region=client.region.id if client.region else None, 
            country=client.country,
            day_of_birth=client.day_of_birth.isoformat() if client.day_of_birth else None,
            requirements=client.requirements,
            unokod=client.unokod,
        )
        for client in clients
    ]

    return user_data_list



"""
Register a new user and client in the system.
"""
@router.post("/user/register", response={201: dict, 400: dict}, tags=["caseworker-user-management"])
def register_user(request, user_data: UserInfoSchema):

    if not user_data.email or not user_data.email.strip():
        return 400, {"error": "e-post måste anges och får inte vara tom."}

    if not user_data.password or not user_data.password.strip():
        return 400, {"error": "Lösenord måste anges och får inte vara tomt."}
    
    if not user_data.day_of_birth:
        return 400, {"error": "Födelsedag måste anges med korrekt format, xxxx-xx-xx"}
    
    if not user_data.region:
        return 400, {"error": "Region måste anges."}
    
    if Client.objects.filter(email=user_data.email).exists():
        return 400, {"error": "Användare med denna e-postadress finns redan."}

    try:
        # för att säkerställa att antingen allt lyckas eller rullas tillbaka om något misslyckas.
        with transaction.atomic():  

            region_obj = Region.objects.filter(id=user_data.region).first()
            if not region_obj:
                raise ValueError("Regionen finns inte i databasen.")

            userClient = User.objects.create_user(
                email=user_data.email,
                username=user_data.email,
                password=user_data.password,
                first_name=user_data.first_name,
                last_name=user_data.last_name
            )

            group_obj, created = Group.objects.get_or_create(name="user")
            userClient.groups.add(group_obj)

            user = Client(
                user=userClient,
                first_name=user_data.first_name,
                last_name=user_data.last_name,
                region=region_obj,
                phone=user_data.phone,
                email=user_data.email,
                gender=user_data.gender, 
                street=user_data.street,
                postcode=user_data.postcode,  
                city=user_data.city,
                country=user_data.country,
                day_of_birth=user_data.day_of_birth,
                requirements= user_data.requirements,
                unokod= user_data.unokod,
                # personnr_lastnr=user_data.personnr_lastnr or "",
            )

            user.save()

    except IntegrityError as e:
         # Om något går fel under transaktionen, rulla tillbaka allt
        return 400, {"error": "Något gick fel: En användare eller klient kunde inte skapas."}
    except ValueError as e:
        return 400, {"error": "Något gick fel."}
    except Exception as e:
        return 400, {"error": "Något gick fel."}

    return 201, {"success": "Användare registrerad!", "user_id": userClient.id}


"""
Deletes a user from the system using their ID. 
The function verifies the user's existence and group membership before proceeding with the deletion.
"""
@router.delete("/delete/user/{id}", response={200: dict, 400: dict, 500: dict}, tags=["caseworker-user-management"])
def delete_user(request, id: int):
    try:
        user = User.objects.filter(id=id).first()

        if not user:
            return JsonResponse( {"error": "Användare finns inte."}, status=400)

        if not user.groups.filter(name="user").exists():
            return 400, {"error": "Användaren tillhör inte gruppen 'user'."}

        user.delete()
        
        return 200, {"message": "Användaren har tagits bort."}

    except Exception as e:        
        return 500, {"error": "Ett internt fel inträffade, vänligen försök igen senare."}


"""
Updates the user and client information based on the provided payload. 
This function checks if the user belongs to the 'user' group and updates their details accordingly.
"""
@router.put("/update/user/{user_id}", response={200: UserInfoSchema, 400: dict, 404: dict}, tags=["caseworker-user-management"])
def update_user(request, user_id: int, payload: UserInfoSchema):
    try:
        user = User.objects.filter(id=user_id).first()

        if not user:
            return JsonResponse({"error": "Användare finns inte."}, status=404)

        if not user.groups.filter(name="user").exists():
            return JsonResponse({"error": "Användaren tillhör inte gruppen 'user'."}, status=400)

        try:
            client = Client.objects.get(user=user)
        except Client.DoesNotExist:
            return JsonResponse({"error": "Kunden som är kopplad till användaren finns inte."}, status=404)

        # Mapping of payload fields to the corresponding model fields
        updates = {
            'email': payload.email,
            'first_name': payload.first_name,
            'last_name': payload.last_name,
            'phone': payload.phone,
            'gender': payload.gender,
            'street': payload.street,
            'postcode': payload.postcode,
            'city': payload.city,
            'country': payload.country,
            'region_id': payload.region,
            'day_of_birth': payload.day_of_birth,
            'requirements': payload.requirements,
            'unokod': payload.unokod,
            # 'personnr_lastnr': payload.personnr_lastnr
        }

        # Using transaction.atomic to ensure all updates happen in a single transaction
        with transaction.atomic():
            # Update fields if they have changed
            for field, value in updates.items():
                if value is not None:
                    if hasattr(client, field) and getattr(client, field) != value:
                        setattr(client, field, value)

                    # Also update the corresponding user field if it exists
                    if field in ['email', 'first_name', 'last_name']:
                        setattr(user, field, value)

            # Save Changes
            user.save()
            client.save()

        return JsonResponse(payload.dict(), status=200)

    except Exception as e:
        return JsonResponse({"error": "Ett internt fel inträffade, vänligen försök igen senare."}, status=400)
