from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import User, SMSVerificationCode, DesignerQuestionnaire, RepairQuestionnaire, SupplierQuestionnaire, MediaQuestionnaire, Report


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = [
        'phone',
        'full_name',
        'get_groups_display',
        'is_phone_verified',
        'is_profile_completed',
        'is_active_profile',
        'is_active',
        'created_at',
    ]
    
    def get_groups_display(self, obj):
        """Groups name'larini ko'rsatish"""
        groups = obj.groups.all()
        if groups.exists():
            return ', '.join([group.name for group in groups])
        return '-'
    get_groups_display.short_description = 'Группы'
    list_filter = [
        'role',
        'is_phone_verified',
        'is_profile_completed',
        'is_active_profile',
        'is_active',
        'is_staff',
        'created_at',
    ]
    search_fields = ['phone', 'full_name', 'email']
    readonly_fields = ['created_at', 'updated_at', 'last_login', 'date_joined']
    
    fieldsets = (
        (None, {'fields': ('phone', 'password')}),
        ('Личные данные', {
            'fields': (
                'full_name',
                'email',
                'photo',
                'description',
                'city',
                'address',
                'website',
            )
        }),
        ('Роль и права', {
            'fields': (
                'role',
                'is_active',
                'is_staff',
                'is_superuser',
                'groups',
                'user_permissions',
            )
        }),
        ('Состояние профиля', {
            'fields': (
                'is_phone_verified',
                'is_profile_completed',
                'is_active_profile',
            )
        }),
        ('Данные компании', {
            'fields': (
                'company_name',
                'inn',
                'product_categories',
                'brands',
                'team_name',
                'work_types',
            ),
            'classes': ('collapse',)
        }),
        ('Социальные сети', {
            'fields': ('telegram', 'instagram', 'vk'),
            'classes': ('collapse',)
        }),
        ('Сотрудничество', {
            'fields': ('cooperation_terms',),
            'classes': ('collapse',)
        }),
        ('QR и шаринг', {
            'fields': ('qr_code', 'share_url'),
            'classes': ('collapse',)
        }),
        ('Даты и время', {
            'fields': ('created_at', 'updated_at', 'last_login', 'date_joined'),
            'classes': ('collapse',)
        }),
    )
    
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('phone', 'password1', 'password2', 'role'),
        }),
    )
    
    ordering = ['-created_at']


@admin.register(SMSVerificationCode)
class SMSVerificationCodeAdmin(admin.ModelAdmin):
    list_display = [
        'phone',
        'code',
        'is_used',
        'created_at',
        'expires_at',
    ]
    list_filter = ['is_used', 'created_at']
    search_fields = ['phone', 'code']
    readonly_fields = ['created_at', 'expires_at']
    date_hierarchy = 'created_at'


@admin.register(DesignerQuestionnaire)
class DesignerQuestionnaireAdmin(admin.ModelAdmin):
    list_display = [
        'full_name',
        'phone',
        'email',
        'city',
        'status',
        'work_type',
        'is_moderation',
        'created_at',
    ]
    list_filter = [
        'status',
        'work_type',
        'city',
        'created_at',
    ]
    search_fields = [
        'full_name',
        'full_name_en',
        'phone',
        'email',
        'city',
    ]
    readonly_fields = ['created_at', 'updated_at']
    date_hierarchy = 'created_at'
    
    fieldsets = (
        ('Основная информация', {
            'fields': (
                'group',
                'status',
                'full_name',
                'full_name_en',
                'phone',
                'birth_date',
                'email',
                'city',
            )
        }),
        ('Услуги', {
            'fields': ('services',)
        }),
        ('Работа', {
            'fields': (
                'work_type',
                'welcome_message',
                'work_cities',
            )
        }),
        ('Сотрудничество', {
            'fields': (
                'cooperation_terms',
                'segments',
            )
        }),
        ('Уникальное торговое предложение', {
            'fields': ('unique_trade_proposal',)
        }),
        ('Социальные сети и контакты', {
            'fields': (
                'vk',
                'telegram_channel',
                'pinterest',
                'instagram',
                'website',
                'other_contacts',
            )
        }),
        ('Пакеты услуг и условия', {
            'fields': (
                'service_packages_description',
                'vat_payment',
                'supplier_contractor_recommendation_terms',
            )
        }),
        ('Дополнительная информация', {
            'fields': ('additional_info',)
        }),
        ('Согласие и фото', {
            'fields': (
                'data_processing_consent',
                'photo',
            )
        }),
        ('Временные метки', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(RepairQuestionnaire)
class RepairQuestionnaireAdmin(admin.ModelAdmin):
    list_display = [
        'full_name',
        'brand_name',
        'email',
        'status',
        'business_form',
        'is_moderation',
        'created_at',
    ]
    list_filter = [
        'status',
        'business_form',
        'created_at',
    ]
    search_fields = [
        'full_name',
        'brand_name',
        'email',
        'responsible_person',
    ]
    readonly_fields = ['created_at', 'updated_at']
    date_hierarchy = 'created_at'
    
    fieldsets = (
        ('Основная информация', {
            'fields': (
                'group',
                'status',
                'full_name',
                'brand_name',
                'email',
                'responsible_person',
                'representative_cities',
            )
        }),
        ('Бизнес', {
            'fields': (
                'business_form',
                'work_list',
            )
        }),
        ('Сообщения', {
            'fields': (
                'welcome_message',
                'cooperation_terms',
            )
        }),
        ('Проекты', {
            'fields': (
                'project_timelines',
                'segments',
            )
        }),
        ('Социальные сети и контакты', {
            'fields': (
                'vk',
                'telegram_channel',
                'pinterest',
                'instagram',
                'website',
                'other_contacts',
            )
        }),
        ('Условия работы', {
            'fields': (
                'work_format',
                'vat_payment',
                'guarantees',
                'designer_supplier_terms',
            )
        }),
        ('Карточки журналов', {
            'fields': ('magazine_cards',)
        }),
        ('Дополнительная информация', {
            'fields': ('additional_info',)
        }),
        ('Согласие и документы', {
            'fields': (
                'data_processing_consent',
                'company_logo',
            )
        }),
        ('Временные метки', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(SupplierQuestionnaire)
class SupplierQuestionnaireAdmin(admin.ModelAdmin):
    list_display = [
        'full_name',
        'brand_name',
        'email',
        'status',
        'business_form',
        'is_moderation',
        'created_at',
    ]
    list_filter = [
        'status',
        'business_form',
        'group',
        'created_at',
    ]
    search_fields = [
        'full_name',
        'brand_name',
        'email',
        'responsible_person',
    ]
    readonly_fields = ['created_at', 'updated_at']
    date_hierarchy = 'created_at'
    
    fieldsets = (
        ('Основная информация', {
            'fields': (
                'group',
                'status',
                'full_name',
                'brand_name',
                'email',
                'responsible_person',
                'representative_cities',
            )
        }),
        ('Бизнес', {
            'fields': (
                'business_form',
                'product_assortment',
            )
        }),
        ('Сообщения', {
            'fields': (
                'welcome_message',
                'cooperation_terms',
            )
        }),
        ('Социальные сети и контакты', {
            'fields': (
                'vk',
                'telegram_channel',
                'pinterest',
                'instagram',
                'website',
                'other_contacts',
            )
        }),
        ('Условия работы', {
            'fields': (
                'delivery_terms',
                'vat_payment',
                'guarantees',
                'designer_contractor_terms',
            )
        }),
        ('Карточки журналов', {
            'fields': ('magazine_cards',)
        }),
        ('Согласие и документы', {
            'fields': (
                'data_processing_consent',
                'company_logo',
            )
        }),
        ('Сегменты', {
            'fields': ('segments',)
        }),
        ('Временные метки', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(MediaQuestionnaire)
class MediaQuestionnaireAdmin(admin.ModelAdmin):
    list_display = [
        'full_name',
        'brand_name',
        'email',
        'status',
        'is_moderation',
        'created_at',
    ]
    list_filter = [
        'status',
        'group',
        'created_at',
    ]
    search_fields = [
        'full_name',
        'brand_name',
        'email',
        'responsible_person',
    ]
    readonly_fields = ['created_at', 'updated_at']
    date_hierarchy = 'created_at'
    
    fieldsets = (
        ('Основная информация', {
            'fields': (
                'group',
                'status',
                'full_name',
                'phone',
                'brand_name',
                'email',
                'responsible_person',
                'representative_cities',
            )
        }),
        ('Бизнес и деятельность', {
            'fields': (
                'business_form',
                'activity_description',
            )
        }),
        ('Сообщения', {
            'fields': (
                'welcome_message',
                'cooperation_terms',
            )
        }),
        ('Сегменты', {
            'fields': ('segments',)
        }),
        ('Социальные сети и контакты', {
            'fields': (
                'vk',
                'telegram_channel',
                'pinterest',
                'instagram',
                'website',
                'other_contacts',
            )
        }),
        ('Условия работы', {
            'fields': (
                'vat_payment',
            )
        }),
        ('Дополнительная информация', {
            'fields': ('additional_info',)
        }),
        ('Логотип компании', {
            'fields': ('company_logo',)
        }),
        ('Временные метки', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


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
