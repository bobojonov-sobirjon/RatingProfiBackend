from django.db import models
from django.contrib.auth import get_user_model

User = get_user_model()


class QuestionnaireRating(models.Model):
    """
    Рейтинг для анкет (DesignerQuestionnaire, RepairQuestionnaire, SupplierQuestionnaire, MediaQuestionnaire)
    Har bir user har bir questionnaire uchun faqat 1 ta review qoldirishi mumkin
    """
    ROLE_CHOICES = [
        ('Поставщик', 'Поставщик'),
        ('Ремонт', 'Ремонт'),
        ('Дизайн', 'Дизайн'),
        ('Медиа', 'Медиа'),
    ]
    
    STATUS_CHOICES = [
        ('pending', 'На модерации'),
        ('approved', 'Подтвержден'),
        ('rejected', 'Отклонен'),
    ]
    
    reviewer = models.ForeignKey(
        'accounts.User',
        on_delete=models.CASCADE,
        related_name='questionnaire_ratings_given',
        verbose_name='Оставивший отзыв'
    )
    
    # Role va questionnaire_id orqali questionnaire'ni aniqlash
    role = models.CharField(
        max_length=20,
        choices=ROLE_CHOICES,
        verbose_name='Роль (модель)'
    )
    questionnaire_id = models.IntegerField(
        verbose_name='ID анкеты'
    )
    
    # Rating ma'lumotlari
    is_positive = models.BooleanField(
        default=True,
        verbose_name='Положительный отзыв (⭐)'
    )
    is_constructive = models.BooleanField(
        default=False,
        verbose_name='Конструктивный отзыв (☆)'
    )
    text = models.TextField(
        verbose_name='Текст отзыва'
    )
    
    status = models.CharField(
        max_length=10,
        choices=STATUS_CHOICES,
        default='pending',
        verbose_name='Статус'
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
        verbose_name = 'Рейтинг анкеты'
        verbose_name_plural = 'Рейтинги анкет'
        ordering = ['-created_at']
        constraints = [
            models.UniqueConstraint(
                fields=['reviewer', 'role', 'questionnaire_id'],
                name='unique_rating_per_questionnaire'
            )
        ]
        indexes = [
            models.Index(fields=['role', 'questionnaire_id', 'status']),
            models.Index(fields=['reviewer', 'role', 'questionnaire_id']),
        ]
    
    def __str__(self):
        return f"{self.reviewer.phone} -> {self.role} #{self.questionnaire_id} ({'⭐' if self.is_positive else '☆'})"
    
    def get_questionnaire(self):
        """
        Role va questionnaire_id orqali questionnaire object'ni olish
        """
        from apps.accounts.models import DesignerQuestionnaire, RepairQuestionnaire, SupplierQuestionnaire, MediaQuestionnaire
        
        model_map = {
            'Поставщик': SupplierQuestionnaire,
            'Ремонт': RepairQuestionnaire,
            'Дизайн': DesignerQuestionnaire,
            'Медиа': MediaQuestionnaire,
        }
        
        model_class = model_map.get(self.role)
        if model_class:
            try:
                return model_class.objects.get(id=self.questionnaire_id)
            except model_class.DoesNotExist:
                return None
        return None
