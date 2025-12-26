from django.contrib import admin
from .models import UpcomingEvent


@admin.register(UpcomingEvent)
class UpcomingEventAdmin(admin.ModelAdmin):
    list_display = [
        'id',
        'organization_name',
        'event_type',
        'city',
        'event_date',
        'status',
        'created_by',
        'created_at',
    ]
    list_filter = [
        'status',
        'event_type',
        'city',
        'event_date',
        'created_at',
    ]
    search_fields = [
        'organization_name',
        'announcement',
        'about_event',
        'city',
    ]
    readonly_fields = ['created_at', 'updated_at']
    date_hierarchy = 'event_date'
    
    fieldsets = (
        ('Основная информация', {
            'fields': (
                'poster',
                'organization_name',
                'event_type',
                'status',
            )
        }),
        ('Описание мероприятия', {
            'fields': (
                'announcement',
                'about_event',
            )
        }),
        ('Дата, время и место', {
            'fields': (
                'event_date',
                'event_location',
                'city',
            )
        }),
        ('Контакты', {
            'fields': (
                'registration_phone',
            )
        }),
        ('Создатель', {
            'fields': ('created_by',)
        }),
        ('Временные метки', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
