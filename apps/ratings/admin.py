from django.contrib import admin
from .models import QuestionnaireRating


@admin.register(QuestionnaireRating)
class QuestionnaireRatingAdmin(admin.ModelAdmin):
    list_display = [
        'id',
        'reviewer',
        'role',
        'questionnaire_id',
        'is_positive',
        'is_constructive',
        'status',
        'created_at',
    ]
    list_filter = [
        'status',
        'role',
        'is_positive',
        'is_constructive',
        'created_at',
    ]
    search_fields = [
        'reviewer__phone',
        'text',
    ]
    readonly_fields = ['created_at', 'updated_at']
    date_hierarchy = 'created_at'
    
    fieldsets = (
        ('Основная информация', {
            'fields': (
                'reviewer',
                'role',
                'questionnaire_id',
            )
        }),
        ('Рейтинг', {
            'fields': (
                'is_positive',
                'is_constructive',
                'text',
            )
        }),
        ('Статус', {
            'fields': ('status',)
        }),
        ('Временные метки', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
