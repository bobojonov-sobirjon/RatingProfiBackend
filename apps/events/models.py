from django.db import models
from django.contrib.auth import get_user_model
from django.utils import timezone

User = get_user_model()


class UpcomingEvent(models.Model):
    """
    Ближайшие мероприятия (Upcoming Events)
    """
    EVENT_TYPE_CHOICES = [
        ('training', 'ОБУЧЕНИЕ'),
        ('presentation', 'ПРЕЗЕНТАЦИЯ'),
        ('opening', 'ОТКРЫТИЕ'),
        ('leisure', 'ДОСУГОВО-РАЗВЛЕКАТЕЛЬНАЯ'),
    ]
    
    STATUS_CHOICES = [
        ('draft', 'Черновик'),
        ('published', 'Опубликовано'),
        ('cancelled', 'Отменено'),
    ]
    
    # Афиша (Poster)
    poster = models.ImageField(
        upload_to='events/posters/',
        blank=True,
        null=True,
        verbose_name='Афиша'
    )
    
    # Название организации
    organization_name = models.CharField(
        max_length=30,
        verbose_name='Название организации'
    )
    
    # Тип мероприятия
    event_type = models.CharField(
        max_length=50,
        choices=EVENT_TYPE_CHOICES,
        verbose_name='Тип мероприятия'
    )
    
    # Анонс мероприятия
    announcement = models.TextField(
        verbose_name='Анонс мероприятия'
    )
    
    # Дата, время и место проведения мероприятия
    event_date = models.DateTimeField(
        verbose_name='Дата и время проведения мероприятия'
    )
    
    # Место проведения
    event_location = models.TextField(
        verbose_name='Место проведения мероприятия'
    )
    
    # Город (для фильтрации)
    city = models.CharField(
        max_length=100,
        verbose_name='Город'
    )
    
    # Телефон для записи
    registration_phone = models.CharField(
        max_length=20,
        verbose_name='Телефон для записи'
    )
    
    # О мероприятии
    about_event = models.TextField(
        verbose_name='О мероприятии'
    )
    
    # Статус
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='draft',
        verbose_name='Статус'
    )
    
    # Создатель
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_upcoming_events',
        verbose_name='Создал'
    )
    
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name='Дата создания'
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name='Дата обновления'
    )
    
    class Meta:
        verbose_name = 'Ближайшее мероприятие'
        verbose_name_plural = 'Ближайшие мероприятия'
        ordering = ['event_date']
        indexes = [
            models.Index(fields=['city', 'event_date']),
            models.Index(fields=['status', 'event_date']),
            models.Index(fields=['event_type', 'event_date']),
        ]
    
    def __str__(self):
        return f"{self.organization_name} - {self.get_event_type_display()} ({self.event_date})"
