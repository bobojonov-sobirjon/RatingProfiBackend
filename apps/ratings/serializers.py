from rest_framework import serializers
from drf_spectacular.utils import extend_schema_field
from .models import QuestionnaireRating


class QuestionnaireRatingCreateSerializer(serializers.Serializer):
    """
    Serializer для создания рейтинга анкеты
    """
    role = serializers.ChoiceField(
        choices=['Поставщик', 'Ремонт', 'Дизайн', 'Медиа'],
        help_text='Роль (модель): Поставщик, Ремонт, Дизайн, Медиа'
    )
    id_questionnaire = serializers.IntegerField(
        help_text='ID анкеты'
    )
    is_positive = serializers.BooleanField(
        help_text='Положительный отзыв (⭐) - true, Конструктивный (☆) - false'
    )
    is_constructive = serializers.BooleanField(
        help_text='Конструктивный отзыв (☆)'
    )
    text = serializers.CharField(
        help_text='Текст отзыва'
    )


class QuestionnaireRatingSerializer(serializers.ModelSerializer):
    """
    Serializer для рейтинга анкеты
    """
    reviewer_name = serializers.SerializerMethodField()
    reviewer_phone = serializers.SerializerMethodField()
    status_display = serializers.CharField(
        source='get_status_display',
        read_only=True
    )
    
    @extend_schema_field(str)
    def get_reviewer_name(self, obj):
        return obj.reviewer.get_full_name() if hasattr(obj.reviewer, 'get_full_name') else str(obj.reviewer)
    
    @extend_schema_field(str)
    def get_reviewer_phone(self, obj):
        return obj.reviewer.phone
    
    class Meta:
        model = QuestionnaireRating
        fields = [
            'id',
            'reviewer',
            'reviewer_name',
            'reviewer_phone',
            'role',
            'questionnaire_id',
            'is_positive',
            'is_constructive',
            'text',
            'status',
            'status_display',
            'created_at',
            'updated_at',
        ]
        read_only_fields = [
            'id',
            'reviewer',
            'status',
            'created_at',
            'updated_at',
        ]


class QuestionnaireRatingStatusUpdateSerializer(serializers.Serializer):
    """
    Serializer для обновления статуса рейтинга анкеты (admin)
    """
    status = serializers.ChoiceField(
        choices=[
            ('pending', 'На модерации'),
            ('approved', 'Подтвержден'),
            ('rejected', 'Отклонен'),
        ],
        required=True,
        help_text="Новый статус рейтинга: 'pending' (На модерации), 'approved' (Подтвержден), 'rejected' (Отклонен)"
    )
