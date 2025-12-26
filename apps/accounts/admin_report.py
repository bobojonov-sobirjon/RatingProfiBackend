@admin.register(Report)
class ReportAdmin(admin.ModelAdmin):
    list_display = [
        'id',
        'user',
        'start_date',
        'end_date',
        'created_at',
    ]
    list_filter = [
        'start_date',
        'end_date',
        'created_at',
    ]
    search_fields = [
        'user__phone',
        'user__full_name',
    ]
    readonly_fields = ['created_at', 'updated_at']
    date_hierarchy = 'start_date'
    
    fieldsets = (
        ('Основная информация', {
            'fields': (
                'user',
                'start_date',
                'end_date',
            )
        }),
        ('Временные метки', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
