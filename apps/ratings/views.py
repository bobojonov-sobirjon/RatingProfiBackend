from rest_framework import permissions, status, views
from rest_framework.response import Response
from rest_framework.exceptions import NotFound, PermissionDenied
from drf_spectacular.utils import extend_schema

from .models import QuestionnaireRating
from .serializers import (
    QuestionnaireRatingCreateSerializer,
    QuestionnaireRatingSerializer,
    QuestionnaireRatingStatusUpdateSerializer,
)
from apps.accounts.models import DesignerQuestionnaire, RepairQuestionnaire, SupplierQuestionnaire, MediaQuestionnaire


@extend_schema(
    tags=['Questionnaire Ratings'],
    summary='Создать рейтинг для анкеты',
    description='''
    POST: Создать рейтинг для анкеты (DesignerQuestionnaire, RepairQuestionnaire, SupplierQuestionnaire, MediaQuestionnaire)
    
    Request body:
    - role: Роль (модель) - "Поставщик", "Ремонт", "Дизайн", "Медиа"
    - id_questionnaire: ID анкеты
    - is_positive: Положительный отзыв (⭐) - true, Конструктивный (☆) - false
    - is_constructive: Конструктивный отзыв (☆) - true/false
    - text: Текст отзыва
    
    Правила:
    - Каждый пользователь может оставить только 1 отзыв на каждую анкету
    - При повторной отправке будет ошибка - используйте PUT/PATCH для обновления
    - ⭐ - положительный отзыв (is_positive: true)
    - ☆ - конструктивный отзыв (is_positive: false, is_constructive: true)
    ''',
    request=QuestionnaireRatingCreateSerializer,
    responses={
        201: QuestionnaireRatingSerializer,
        400: {'description': 'Ошибка валидации'},
        404: {'description': 'Анкета не найдена'}
    }
)
class QuestionnaireRatingCreateView(views.APIView):
    """
    Создать рейтинг для анкеты
    POST /api/v1/ratings/questionnaire-ratings/
    """
    permission_classes = [permissions.IsAuthenticated]
    
    def get_questionnaire_model(self, role):
        """Role bo'yicha model class'ni olish"""
        model_map = {
            'Поставщик': SupplierQuestionnaire,
            'Ремонт': RepairQuestionnaire,
            'Дизайн': DesignerQuestionnaire,
            'Медиа': MediaQuestionnaire,
        }
        return model_map.get(role)
    
    def post(self, request):
        serializer = QuestionnaireRatingCreateSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        role = serializer.validated_data['role']
        questionnaire_id = serializer.validated_data['id_questionnaire']
        
        # Model class'ni olish
        model_class = self.get_questionnaire_model(role)
        if not model_class:
            return Response(
                {'error': f'Неверная роль: {role}'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Questionnaire'ni tekshirish
        try:
            questionnaire = model_class.objects.get(id=questionnaire_id)
        except model_class.DoesNotExist:
            raise NotFound(f'Анкета не найдена: {role} #{questionnaire_id}')
        
        # Mavjud rating'ni topish yoki yaratish
        rating, created = QuestionnaireRating.objects.get_or_create(
            reviewer=request.user,
            role=role,
            questionnaire_id=questionnaire_id,
            defaults={
                'is_positive': serializer.validated_data['is_positive'],
                'is_constructive': serializer.validated_data['is_constructive'],
                'text': serializer.validated_data['text'],
            }
        )
        
        # Agar mavjud bo'lsa, yangilash
        if not created:
            rating.is_positive = serializer.validated_data['is_positive']
            rating.is_constructive = serializer.validated_data['is_constructive']
            rating.text = serializer.validated_data['text']
            rating.status = 'pending'  # Yangilangan rating yana moderatsiyaga
            rating.save()
        
        result_serializer = QuestionnaireRatingSerializer(rating)
        return Response(result_serializer.data, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)


@extend_schema(
    tags=['Questionnaire Ratings'],
    summary='Получить все рейтинги анкет (объединенный список)',
    description='''
    GET: Получить объединенный список всех анкет с их рейтингами
    
    Возвращает список всех анкет (DesignerQuestionnaire, RepairQuestionnaire, SupplierQuestionnaire, MediaQuestionnaire)
    с агрегированными рейтингами:
    - Название организации ФИ (full_name / brand_name)
    - Группа (role)
    - Общий Рейтинг (total_rating_count)
    - Положительный Рейтинг (positive_rating_count)
    - Конструктивный Рейтинг (constructive_rating_count)
    
    Каждый элемент содержит:
    - request_name: Тип анкеты
    - id: ID анкеты
    - name: Название (full_name / brand_name)
    - group: Группа
    - total_rating_count: Общее количество отзывов
    - positive_rating_count: Количество положительных отзывов (⭐)
    - constructive_rating_count: Количество конструктивных отзывов (☆)
    ''',
    responses={
        200: {'description': 'Список всех анкет с рейтингами'}
    }
)
class QuestionnaireRatingAllView(views.APIView):
    """
    Получить все рейтинги анкет (объединенный список)
    GET /api/v1/ratings/questionnaire-ratings/all/
    """
    permission_classes = [permissions.AllowAny]
    
    def get(self, request):
        # Barcha anketalarni olish va rating'lar bilan birlashtirish
        result = []
        
        # DesignerQuestionnaire
        designers = DesignerQuestionnaire.objects.filter(status='published', is_moderation=True)
        for designer in designers:
            ratings = QuestionnaireRating.objects.filter(
                role='Дизайн',
                questionnaire_id=designer.id,
                status='approved'
            )
            result.append({
                'request_name': 'DesignerQuestionnaire',
                'id': designer.id,
                'name': designer.full_name,
                'group': 'Дизайн',
                'total_rating_count': ratings.count(),
                'positive_rating_count': ratings.filter(is_positive=True).count(),
                'constructive_rating_count': ratings.filter(is_constructive=True).count(),
            })
        
        # RepairQuestionnaire
        repairs = RepairQuestionnaire.objects.filter(status='published')
        for repair in repairs:
            ratings = QuestionnaireRating.objects.filter(
                role='Ремонт',
                questionnaire_id=repair.id,
                status='approved'
            )
            result.append({
                'request_name': 'RepairQuestionnaire',
                'id': repair.id,
                'name': repair.full_name or repair.brand_name,
                'group': 'Ремонт',
                'total_rating_count': ratings.count(),
                'positive_rating_count': ratings.filter(is_positive=True).count(),
                'constructive_rating_count': ratings.filter(is_constructive=True).count(),
            })
        
        # SupplierQuestionnaire
        suppliers = SupplierQuestionnaire.objects.filter(status='published', is_moderation=True)
        for supplier in suppliers:
            ratings = QuestionnaireRating.objects.filter(
                role='Поставщик',
                questionnaire_id=supplier.id,
                status='approved'
            )
            result.append({
                'request_name': 'SupplierQuestionnaire',
                'id': supplier.id,
                'name': supplier.full_name or supplier.brand_name,
                'group': 'Поставщик',
                'total_rating_count': ratings.count(),
                'positive_rating_count': ratings.filter(is_positive=True).count(),
                'constructive_rating_count': ratings.filter(is_constructive=True).count(),
            })
        
        # MediaQuestionnaire
        media = MediaQuestionnaire.objects.filter(status='published', is_moderation=True)
        for media_item in media:
            ratings = QuestionnaireRating.objects.filter(
                role='Медиа',
                questionnaire_id=media_item.id,
                status='approved'
            )
            result.append({
                'request_name': 'MediaQuestionnaire',
                'id': media_item.id,
                'name': media_item.full_name or media_item.brand_name,
                'group': 'Медиа',
                'total_rating_count': ratings.count(),
                'positive_rating_count': ratings.filter(is_positive=True).count(),
                'constructive_rating_count': ratings.filter(is_constructive=True).count(),
            })
        
        # Sort by total_rating_count (descending)
        result.sort(key=lambda x: x['total_rating_count'], reverse=True)
        
        return Response(result, status=status.HTTP_200_OK)


@extend_schema(
    tags=['Questionnaire Ratings'],
    summary='Получить, обновить или удалить рейтинг',
    description='''
    GET: Получить рейтинг по ID
    
    PUT/PATCH: Обновить рейтинг
    Request body:
    - is_positive: Положительный отзыв (⭐) - true, Конструктивный (☆) - false
    - is_constructive: Конструктивный отзыв (☆) - true/false
    - text: Текст отзыва
    
    DELETE: Удалить рейтинг
    
    Правила:
    - Только создатель рейтинга может его обновить или удалить
    - При обновлении статус меняется на 'pending' (на модерации)
    ''',
    responses={
        200: QuestionnaireRatingSerializer,
        204: {'description': 'Рейтинг успешно удален'},
        403: {'description': 'Нет доступа к этому рейтингу'},
        404: {'description': 'Рейтинг не найден'}
    }
)
class QuestionnaireRatingDetailView(views.APIView):
    """
    Получить, обновить или удалить рейтинг
    GET /api/v1/ratings/questionnaire-ratings/<id>/
    PUT /api/v1/ratings/questionnaire-ratings/<id>/
    PATCH /api/v1/ratings/questionnaire-ratings/<id>/
    DELETE /api/v1/ratings/questionnaire-ratings/<id>/
    """
    permission_classes = [permissions.IsAuthenticated]
    
    def get_object(self, pk):
        """Rating'ni olish va permission tekshirish"""
        try:
            rating = QuestionnaireRating.objects.get(pk=pk)
        except QuestionnaireRating.DoesNotExist:
            raise NotFound('Рейтинг не найден')
        
        # Faqat o'zi yaratgan rating'ni ko'rish/o'zgartirish/o'chirish mumkin
        if rating.reviewer != self.request.user:
            raise PermissionDenied('Вы не имеете доступа к этому рейтингу')
        
        return rating
    
    def get(self, request, pk):
        """GET: Rating'ni olish"""
        rating = self.get_object(pk)
        serializer = QuestionnaireRatingSerializer(rating)
        return Response(serializer.data, status=status.HTTP_200_OK)
    
    def put(self, request, pk):
        """PUT: Rating'ni to'liq yangilash"""
        rating = self.get_object(pk)
        
        serializer = QuestionnaireRatingCreateSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        # Role va questionnaire_id o'zgarmasligi kerak
        if serializer.validated_data.get('role') != rating.role:
            return Response(
                {'error': 'Роль нельзя изменить'},
                status=status.HTTP_400_BAD_REQUEST
            )
        if serializer.validated_data.get('id_questionnaire') != rating.questionnaire_id:
            return Response(
                {'error': 'ID анкеты нельзя изменить'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Yangilash
        rating.is_positive = serializer.validated_data['is_positive']
        rating.is_constructive = serializer.validated_data['is_constructive']
        rating.text = serializer.validated_data['text']
        rating.status = 'pending'  # Yangilangan rating yana moderatsiyaga
        rating.save()
        
        result_serializer = QuestionnaireRatingSerializer(rating)
        return Response(result_serializer.data, status=status.HTTP_200_OK)
    
    def patch(self, request, pk):
        """PATCH: Rating'ni qisman yangilash"""
        rating = self.get_object(pk)
        
        # Faqat mavjud field'larni yangilash
        if 'is_positive' in request.data:
            rating.is_positive = request.data['is_positive']
        if 'is_constructive' in request.data:
            rating.is_constructive = request.data['is_constructive']
        if 'text' in request.data:
            rating.text = request.data['text']
        
        rating.status = 'pending'  # Yangilangan rating yana moderatsiyaga
        rating.save()
        
        result_serializer = QuestionnaireRatingSerializer(rating)
        return Response(result_serializer.data, status=status.HTTP_200_OK)
    
    def delete(self, request, pk):
        """DELETE: Rating'ni o'chirish"""
        rating = self.get_object(pk)
        rating.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


@extend_schema(
    tags=['Questionnaire Ratings'],
    summary='Обновить статус рейтинга (admin)',
    description='''
    PATCH: Обновить статус рейтинга анкеты (только для администраторов)
    
    Request body:
    - status: Новый статус рейтинга
    
    Доступные значения статуса (enum):
    - "pending" - На модерации (по умолчанию, когда пользователь создает/обновляет отзыв)
    - "approved" - Подтвержден (отзыв одобрен модератором и отображается публично)
    - "rejected" - Отклонен (отзыв отклонен модератором и не отображается)
    
    Правила:
    - Только администратор (is_staff=True) может изменять статус рейтинга
    - При создании или обновлении отзыва пользователем статус автоматически устанавливается в "pending"
    - Только отзывы со статусом "approved" учитываются в рейтингах и отображаются публично
    ''',
    request=QuestionnaireRatingStatusUpdateSerializer,
    responses={
        200: QuestionnaireRatingSerializer,
        400: {'description': 'Ошибка валидации'},
        403: {'description': 'Доступ запрещен. Только администраторы могут изменять статус рейтинга'},
        404: {'description': 'Рейтинг не найден'}
    }
)
class QuestionnaireRatingStatusUpdateView(views.APIView):
    """
    Обновить статус рейтинга анкеты (admin)
    PATCH /api/v1/ratings/questionnaire-ratings/{id}/update-status/
    """
    permission_classes = [permissions.IsAuthenticated]
    
    def get_object(self, pk):
        """Rating'ni olish"""
        try:
            return QuestionnaireRating.objects.get(pk=pk)
        except QuestionnaireRating.DoesNotExist:
            raise NotFound("Рейтинг не найден")
    
    def patch(self, request, pk):
        """PATCH: Обновить статус рейтинга"""
        # Проверка прав администратора
        if not (request.user.is_staff or request.user.role == 'admin'):
            raise PermissionDenied("Только администратор может изменять статус рейтинга")
        
        rating = self.get_object(pk)
        serializer = QuestionnaireRatingStatusUpdateSerializer(data=request.data)
        
        if serializer.is_valid():
            rating.status = serializer.validated_data['status']
            rating.save()
            
            result_serializer = QuestionnaireRatingSerializer(rating)
            return Response(result_serializer.data, status=status.HTTP_200_OK)
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
