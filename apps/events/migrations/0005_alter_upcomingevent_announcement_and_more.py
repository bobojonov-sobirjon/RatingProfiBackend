# Generated manually: Truncate organization_name data before altering field

from django.db import migrations, models


def truncate_organization_names(apps, schema_editor):
    """Truncate organization_name to 30 characters before altering field"""
    UpcomingEvent = apps.get_model('events', 'UpcomingEvent')
    for event in UpcomingEvent.objects.all():
        if len(event.organization_name) > 30:
            event.organization_name = event.organization_name[:30]
            event.save(update_fields=['organization_name'])


def reverse_truncate_organization_names(apps, schema_editor):
    """Reverse operation - no need to restore truncated data"""
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('events', '0004_remove_event_events_even_city_4dc7bf_idx_and_more'),
    ]

    operations = [
        # Step 1: Truncate existing data
        migrations.RunPython(
            truncate_organization_names,
            reverse_truncate_organization_names
        ),
        # Step 2: Alter fields
        migrations.AlterField(
            model_name='upcomingevent',
            name='announcement',
            field=models.TextField(blank=True, null=True, verbose_name='Анонс мероприятия'),
        ),
        migrations.AlterField(
            model_name='upcomingevent',
            name='organization_name',
            field=models.CharField(max_length=30, verbose_name='Название организации'),
        ),
    ]
