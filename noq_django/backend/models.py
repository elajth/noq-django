from django.db import models
from django.db.models import Q
from django.core.exceptions import ValidationError

from django.contrib.auth.models import User
from django.contrib.auth import get_user_model
from datetime import datetime, timedelta
from django.utils import timezone
from enum import IntEnum

class State(IntEnum):
    PENDING = 1
    DECLINED = 2
    ACCEPTED = 3
    CHECKED_IN = 4
    IN_QUEUE = 5
    RESERVED = 6
    CONFIRMED = 7
    COMPLETED = 8
    ADVISED_AGAINST = 9

class Region(models.Model):
    name = models.CharField(max_length=80)

    class Meta:
        db_table = "regions"

    def __str__(self) -> str:
        return self.name


class Requirement(models.Model):
    description = models.CharField(max_length=255)

    def __str__(self):
        return self.description


class ClientRequirement(models.Model):
    requirements = models.ManyToManyField(Requirement)


class ProductRequirement(models.Model):
    requirements = models.ManyToManyField(Requirement)


class Client(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    first_name = models.CharField(max_length=32)
    last_name = models.CharField(max_length=32)
    gender = models.CharField(
        max_length=1, default=None, blank=True
    )  # [('N','-'),('M', 'Man'), ('F', 'Kvinna')]
    street = models.CharField(max_length=80, default="")
    postcode = models.CharField(max_length=5, default="")

    city = models.CharField(max_length=80, default="")
    country = models.CharField(max_length=25, default="")

    phone = models.CharField(max_length=20)
    email = models.CharField(max_length=40)

    unokod = models.CharField(max_length=10)
    day_of_birth = models.DateField(default=None, null=True)
    personnr_lastnr = models.CharField(max_length=4, default="")

    region = models.ForeignKey(
        Region, on_delete=models.CASCADE, null=False, blank=False
    )

    requirements = models.ForeignKey(
        ClientRequirement, on_delete=models.CASCADE, null=True, blank=True
    )

    # Datum för senaste uppdateringen av användarodellen, för att avgöra om användaren är aktiv
    last_edit = models.DateField(verbose_name="Senaste Aktivitet")

    FLAG_CHOICES = [
        ('DANGER', True),       
        ('OK', False) 
    ]
    flag = models.BooleanField(default=True)

    class Meta:
        db_table = "client"

        verbose_name_plural = "client"

    def name(self) -> str:
        return f"{self.first_name} {self.last_name}"

    def save(self, *args, **kwargs):
        if (
            "fake_data" in kwargs
        ):  # Om data är genererat av script använd istället för time.now
            self.last_edit = kwargs.pop("fake_data")
            super(Client, self).save(*args, **kwargs)
        else:
            self.last_edit = datetime.today()
            super(Client, self).save(*args, **kwargs)

    def __str__(self) -> str:
        # rsrv = ProductBooking.objects.filter(user=self).order_by("-start_date").first()

        # startdate = ""
        # if rsrv:
        #     startdate = rsrv.start_date

        return f"{self.first_name} {self.last_name}"


class Host(models.Model):
    users = models.ManyToManyField(User)
    name = models.CharField(max_length=80)
    street = models.CharField(max_length=80)
    postcode = models.CharField(max_length=5, default="")
    city = models.CharField(max_length=80, default="")
    region = models.ForeignKey(
        Region, on_delete=models.CASCADE, null=False, blank=False
    )
    blocked_clients = models.ManyToManyField(Client, blank=True)

    # Adding a many-to-many relationship with User
    caseworkers = models.ManyToManyField(User, related_name="caseworker_hosts")

    class Meta:
        db_table = "hosts"

    def __str__(self) -> str:
        return f"{self.name}, {self.city}"


class Product(models.Model):
    """
    Product är en generalisering som möjliggör att ett härbärge
    kan ha flera olika rumstyper och även annat som Lunch i gemenskap
    """
    TYPE_CHOICES = [
        ('room', 'Room'),
        ('woman-only', 'Woman Only'),
        ('washingmachine', 'Washing Machine'),
        ('hygieneproducts', 'Hygiene Products'),
        ('breakfast', 'Breakfast'),
        ('dinner', 'Dinner'),
        ('storage', 'Storage'),
    ]
    ROOM_LOCATIONS = [
        ('Sovsal', 'Sovsal'),
        ('Dubbelrum', 'Dubbelrum'),
        ('Eget rum', 'Eget rum'),
    ]

    name = models.CharField(max_length=100)
    description = models.CharField(max_length=100)
    total_places = models.IntegerField()
    host = models.ForeignKey(Host, on_delete=models.CASCADE, blank=True)
    type = models.CharField(max_length=16, choices=TYPE_CHOICES)
    room_location = models.CharField(max_length=20, choices=ROOM_LOCATIONS)  
    requirements = models.ForeignKey(
        ProductRequirement, on_delete=models.CASCADE, null=True, blank=True
    )
    bookable = models.BooleanField(default=True)

    class Meta:
        db_table = "product"

    def __str__(self) -> str:
        # available = None  # ProductAvailable.objects.filter(product=self).first()

        # if available:
        #     left = available.places_left
        #     return f"{self.description} på {self.host.name}, {self.host.city} {left} platser kvar"

        return f"{self.description} på {self.host.name}, {self.host.city}"
        # booking_count = ProductBooking.objects.filter(product=self).count()

        # return f"{self.description} ({self.total_places} platser på {self.host.name}, {self.host.city} ({booking_count} bokade)"

class BookingStatus(models.Model):
    description = models.CharField(max_length=32)

    def __str__(self):
        return self.description

class Booking(models.Model):
    """
    Booking är en bokning av en produkt av en User
    Se också regelverk vid Save()
    """
    booking_time = models.DateTimeField(
        default=timezone.now, verbose_name="Bokningstid"
    )
    start_date = models.DateField(verbose_name="Startdatum")
    end_date = models.DateField(null=True, verbose_name="Slutdatum")
    product = models.ForeignKey(
        Product, on_delete=models.CASCADE,
        blank=False, verbose_name="Plats"
    )
    user = models.ForeignKey(
        Client, on_delete=models.CASCADE,
        blank=False, verbose_name="Namn"
    )
    status = models.ForeignKey(
        BookingStatus, on_delete=models.CASCADE,
        blank=False, verbose_name="Bokningsstatus"
    )

    class Meta:
        db_table = "product_booking"

    def ready(self):
        from . import signals

    # return count of accepted, pending and checked_in bookings
    def calc_available(self):
        bookings_per_day = self.bookings_count_per_date()
        for date in bookings_per_day:
            places_left = self.product.total_places - bookings_per_day[date]

            existing_availability = Available.objects.filter(
                product=self.product, available_date=date
            ).first()

            if existing_availability:
                existing_availability.places_left = places_left
                existing_availability.save()
            else:
                product_available = Available(
                    available_date=date,
                    product=Product.objects.get(id=self.product.id),
                    places_left=places_left,
                )
                product_available.save()

    def save(self, *args, **kwargs):

        # Check that the booked date is not in the past
        if str(self.start_date) < str(datetime.today().date())\
                and self.status.id != State.COMPLETED:
            raise ValidationError(
                ("Fel: Bokningen börjar före dagens datum!"),
                code="Date error",
            )

        # Check that the booked end_date is not before the start_date
        if str(self.start_date) >= str(self.end_date):
            raise ValidationError(
                ("Fel: Bokningen slutar före start datum!"),
                code="Date error",
            )

        # Check gender for room type = "woman-only"
        product_type = self.product.type

        if product_type == "woman-only":
            if self.user.gender != "K":
                # print("woman-only", self.user.gender, "nekad")
                raise ValidationError(
                    f"Rum för kvinnor kan inte bokas av män",
                    code="woman-only",
                )

        status_list = ['completed', 'declined']
        # Check if there is another booking for the same user and date
        existing_booking = Booking.objects.filter(
            user=self.user, start_date=self.start_date
        ).exclude(status__description__in=status_list).first()

        if existing_booking and self.id != existing_booking.id:
            raise ValidationError(
                ("Har redan en bokning samma dag!"),
                code="already_booked",
            )
            
        # Get existing bookings that overlap, excluding the current booking being updated
        existing_bookings = Booking.objects.filter(
            user=self.user,
            start_date__lt=self.end_date,
            end_date__gt=self.start_date,
        ).exclude(id=self.id)  # Exclude the current booking

        # If there are overlapping bookings, raise a ValidationError
        if existing_bookings.exists():
            raise ValidationError(
                ("You already have a booking that overlaps with these dates."),
                code="overlapping_booking",
            )

        # Check if there is free places available for the booking period
        # - Booking count is only valid if booking has status pending
        # - in_queue or declined will not book a place
        # - accepted, advised_against, reserved, confirmed or checked_in already have
        #   a booked place
        if self.status.id == State.PENDING:
            bookings_per_date = self.bookings_count_per_date()
            places_are_available = all(
                count < self.product.total_places for count in bookings_per_date.values())
            if not places_are_available:
                raise ValidationError(
                    ("Fullbokat rum"),
                    params={"bookings_per_date": bookings_per_date, "nr_or_places": self.product.total_places},
                    code="full"
                )

        super().save(*args, **kwargs)

        # Uppdatera Available
        self.calc_available()

    def bookings_count_per_date(self):
        # Return count for bookings for each day of the booking
        date_delta = (self.end_date - self.start_date).days
        booking_counts = {}

        for i in range(date_delta):
            date_time = self.start_date + timedelta(days=i)
            count = Booking.objects.filter(
                Q(product=self.product)
                & Q(start_date__lte=date_time)
                & Q(end_date__gt=date_time)
                & ~Q(status=State.DECLINED)
                & ~Q(status=State.IN_QUEUE)
                & ~Q(status=State.COMPLETED)
            ).count()
            date = f"{date_time:%Y-%m-%d}"
            booking_counts[date] = count

        return booking_counts

    def __str__(self) -> str:
        return f"{self.start_date}: {self.user.first_name} {self.user.last_name} har bokat {self.product.description} på {self.product.host.name}, {self.product.host.city}"


class Available(models.Model):
    available_date = models.DateField(verbose_name="Datum")
    product = models.ForeignKey(
        Product, on_delete=models.CASCADE, blank=False, verbose_name="Bokning"
    )
    places_left = models.IntegerField(verbose_name="Platser kvar", default=0)

    class Meta:
        db_table = "product_available"

    def __str__(self) -> str:
        return f"{self.product.description} på {self.product.host.name}, {self.product.host.city} har {self.places_left} platser kvar"


class InvoiceStatus(models.Model):
    OPEN = 'open'
    PAID = 'paid'
    VOID = 'void'
    UNCOLLECTIBLE = 'uncollectible'
    
    STATUS_CHOICES = [
        (OPEN, 'Open'),
        (PAID, 'Paid'),
        (VOID, 'Void'),
        (UNCOLLECTIBLE, 'Uncollectible'),
    ]
    
    name = models.CharField(max_length=20, choices=STATUS_CHOICES, default=OPEN, unique=True)
    
    def __str__(self):
        return self.name

class Invoice(models.Model):
    host = models.ForeignKey(Host, on_delete=models.CASCADE, related_name='invoices')
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    description = models.TextField(null=True, blank=True)
    status = models.ForeignKey(InvoiceStatus, on_delete=models.PROTECT, default=1)  
    due_date = models.DateField(null=True, blank=True)
    currency = models.CharField(max_length=3, default='SEK')
    invoice_number = models.CharField(max_length=50, unique=True, blank=False)
    vat = models.DecimalField(max_digits=10, decimal_places=2, default=0.0)
    vat_rate = models.DecimalField(max_digits=5, decimal_places=2, default=0.0)
    sale_date = models.DateField(null=True, blank=True)
    seller_vat_number = models.CharField(max_length=50, null=True, blank=True)
    buyer_vat_number = models.CharField(max_length=50, null=True, blank=True)
    buyer_name = models.CharField(max_length=255, null=True, blank=True)
    buyer_address = models.TextField(null=True, blank=True)

    def __str__(self) -> str:
        return f"Invoice {self.id} for {self.host.name}"
    
    def calculate_vat(self):
        """Calculate the VAT amount based on the amount and vat_rate."""
        self.vat = (self.amount * self.vat_rate) / 100
        return self.vat
    
    def save(self, *args, **kwargs):
        self.calculate_vat()
        super().save(*args, **kwargs)

class SleepingSpace(models.Model):  
    
    BED_TYPES = [
        ('Dubbelsäng över', 'Dubbelsäng över'),
        ('Dubbelsäng under', 'Dubbelsäng under'),
        ('Singelsäng', 'Singelsäng'),
        ('Madrass', 'Madrass'),]
    STATUS_OPTIONS = [
        ('Ledig', 'Ledig'),
        ('Upptagen', 'Upptagen'),
        ('Avstängd', 'Avstängd'),
    ]
    
    bed_type = models.CharField(max_length=25, choices=BED_TYPES)
    status = models.CharField(max_length=10, choices=STATUS_OPTIONS, default='Ledig')

    class Meta:
        db_table = 'sleeping_spaces'

    def __str__(self):
        return f"{self.bed_type} ({self.status})"


class VolunteerProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    availability = models.CharField(max_length=50)
    skills = models.TextField(blank=True)
    preferred_regions = models.ManyToManyField('Region')

    def reassign_to_host(self, new_host):
        start_date = models.DateField(verbose_name="Startdatum")
        VolunteerHostAssignment.objects.create(
            volunteer=self,
            host=new_host,
            active=True,
            start_date=start_date
        )

    def __str__(self):
        return f"{self.user.username} - Volunteer Profile"


class VolunteerHostAssignment(models.Model):
    volunteer = models.ForeignKey(VolunteerProfile, on_delete=models.CASCADE, related_name="host_assignments")
    host = models.ForeignKey('Host', on_delete=models.CASCADE)
    active = models.BooleanField(default=True)
    start_date = models.DateField(verbose_name="Startdatum")
    end_date = models.DateField(null=True, verbose_name="Slutdatum")

    def deactivate(self, end_date=None):
        """Mark this assignment as inactive and set the end date."""
        self.active = False
        self.end_date = end_date
        self.save()

    def __str__(self):
        return f"{self.volunteer.user.username} assigned to {self.host.name} - {'Active' if self.active else 'Inactive'}" 
