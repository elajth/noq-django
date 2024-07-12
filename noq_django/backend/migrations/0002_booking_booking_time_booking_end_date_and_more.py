# Generated by Django 4.2.10 on 2024-07-08 16:25

from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone
from datetime import timedelta


class Migration(migrations.Migration):

    dependencies = [
        ('backend', '0001_initial'),
    ]

    def update_end_date(apps, schema_editor):
        # Set value to the new empty field Booking.end_date to one day after
        # Booking.start_date.
        Booking = apps.get_model("backend", "Booking")
        for booking in Booking.objects.all():
            if booking.end_date == "":
                end_date = booking.start_date + timedelta(days=1)
                booking.end_date = f'{end_date:"%Y-%m-%d"}'
                booking.save()

    operations = [
        migrations.AddField(
            model_name='booking',
            name='booking_time',
            field=models.DateTimeField(default=django.utils.timezone.now, verbose_name='Bokningstid'),
        ),
        migrations.AddField(
            model_name='booking',
            name='end_date',
            field=models.DateField(null=True, verbose_name='Slutdatum'),
        ),
        migrations.AlterField(
            model_name='booking',
            name='start_date',
            field=models.DateField(verbose_name='Startdatum'),
        ),
        migrations.AlterField(
            model_name='booking',
            name='status',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='backend.bookingstatus', verbose_name='Bokningsstatus'),
        ),
        migrations.RunPython(update_end_date)
    ]
