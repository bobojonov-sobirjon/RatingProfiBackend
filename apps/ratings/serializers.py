from rest_framework import serializers
from drf_spectacular.utils import extend_schema_field
from .models import QuestionnaireRating
from apps.accounts.serializers import (
    DesignerQuestionnaireSerializer,
    RepairQuestionnaireSerializer,
    SupplierQuestionnaireSerializer,
    MediaQuestionnaireSerializer,
)


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
    questionnaire = serializers.SerializerMethodField()
    
    @extend_schema_field(str)
    def get_reviewer_name(self, obj):
        return obj.reviewer.get_full_name() if hasattr(obj.reviewer, 'get_full_name') else str(obj.reviewer)
    
    @extend_schema_field(str)
    def get_reviewer_phone(self, obj):
        return obj.reviewer.phone
    
    @extend_schema_field(dict)
    def get_questionnaire(self, obj):
        """Role va questionnaire_id bo'yicha to'liq questionnaire ma'lumotlarini olish"""
        # Agar skip_questionnaire=True bo'lsa, questionnaire'ni qaytarmaymiz (recursive muammoni oldini olish uchun)
        if self.context.get('skip_questionnaire', False):
            return None
        
        from apps.accounts.models import (
            DesignerQuestionnaire,
            RepairQuestionnaire,
            SupplierQuestionnaire,
            MediaQuestionnaire,
        )
        
        try:
            if obj.role == 'Дизайн':
                questionnaire = DesignerQuestionnaire.objects.get(id=obj.questionnaire_id)
                return DesignerQuestionnaireSerializer(questionnaire).data
            elif obj.role == 'Ремонт':
                questionnaire = RepairQuestionnaire.objects.get(id=obj.questionnaire_id)
                return RepairQuestionnaireSerializer(questionnaire).data
            elif obj.role == 'Поставщик':
                questionnaire = SupplierQuestionnaire.objects.get(id=obj.questionnaire_id)
                return SupplierQuestionnaireSerializer(questionnaire).data
            elif obj.role == 'Медиа':
                questionnaire = MediaQuestionnaire.objects.get(id=obj.questionnaire_id)
                return MediaQuestionnaireSerializer(questionnaire).data
            else:
                return None
        except Exception:
            return None
    
    class Meta:
        model = QuestionnaireRating
        fields = [
            'id',
            'reviewer',
            'reviewer_name',
            'reviewer_phone',
            'role',
            'questionnaire_id',
            'questionnaire',
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
