from rest_framework import permissions, status, views
from rest_framework.response import Response
from rest_framework.exceptions import PermissionDenied, NotFound
from rest_framework.pagination import LimitOffsetPagination
from django.utils import timezone
from django.db import models as django_models
from datetime import datetime
from drf_spectacular.utils import extend_schema

from .models import UpcomingEvent
from .serializers import UpcomingEventSerializer


@extend_schema(
    tags=['Upcoming Events'],
    summary='Получить список ближайших мероприятий',
    description='''
    GET: Получить список ближайших мероприятий
    
    Фильтры:
    - city: Фильтр по городу
    - event_type: Фильтр по типу мероприятия (training, presentation, opening, leisure)
    - status: Фильтр по статусу (draft, published, cancelled)
    - search: Поиск по названию организации, анонсу, описанию
    - ordering: Сортировка (event_date, -event_date, created_at, -created_at)
    
    По умолчанию возвращаются только опубликованные мероприятия (status=published)
    ''',
    responses={
        200: UpcomingEventSerializer(many=True)
    }
)
class UpcomingEventListView(views.APIView):
    """
    Список ближайших мероприятий
    GET /api/v1/events/upcoming-events/
    POST /api/v1/events/upcoming-events/
    """
    permission_classes = [permissions.AllowAny]
    
    def get_queryset(self):
        """Queryset'ni olish"""
        if getattr(self, 'swagger_fake_view', False):
            return UpcomingEvent.objects.none()
        
        queryset = UpcomingEvent.objects.all()
        
        # По умолчанию только опубликованные
        if not self.request.user.is_authenticated or not self.request.user.is_staff:
            queryset = queryset.filter(status='published')
        
        # Фильтры
        city = self.request.query_params.get('city')
        if city:
            queryset = queryset.filter(city__icontains=city)
        
        event_type = self.request.query_params.get('event_type')
        if event_type:
            queryset = queryset.filter(event_type=event_type)
        
        status = self.request.query_params.get('status')
        if status and (self.request.user.is_authenticated and self.request.user.is_staff):
            queryset = queryset.filter(status=status)
        
        # Поиск
        search = self.request.query_params.get('search')
        if search:
            queryset = queryset.filter(
                django_models.Q(organization_name__icontains=search) |
                django_models.Q(announcement__icontains=search) |
                django_models.Q(about_event__icontains=search)
            )
        
        # Сортировка
        ordering = self.request.query_params.get('ordering', 'event_date')
        if ordering:
            queryset = queryset.order_by(ordering)
        
        return queryset
    
    def get(self, request):
        """GET: Список мероприятий"""
        queryset = self.get_queryset()
        
        # Pagination
        paginator = LimitOffsetPagination()
        paginator.default_limit = 20
        paginator.max_limit = 100
        page = paginator.paginate_queryset(queryset, request)
        
        if page is not None:
            serializer = UpcomingEventSerializer(page, many=True)
            return paginator.get_paginated_response(serializer.data)
        
        serializer = UpcomingEventSerializer(queryset, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)
    
    @extend_schema(
        summary='Создать мероприятие',
        description='''
        POST: Создать новое мероприятие
        
        Требуется аутентификация.
        ''',
        request=UpcomingEventSerializer,
        responses={
            201: UpcomingEventSerializer,
            400: {'description': 'Ошибка валидации'}
        }
    )
    def post(self, request):
        """POST: Создать мероприятие"""
        serializer = UpcomingEventSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save(created_by=request.user if request.user.is_authenticated else None)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@extend_schema(
    tags=['Upcoming Events'],
    summary='Получить, обновить или удалить мероприятие',
    description='''
    GET: Получить мероприятие по ID
    
    PUT/PATCH: Обновить мероприятие
    - Только создатель или администратор может обновить
    
    DELETE: Удалить мероприятие
    - Только создатель или администратор может удалить
    ''',
    responses={
        200: UpcomingEventSerializer,
        204: {'description': 'Мероприятие успешно удалено'},
        403: {'description': 'Нет доступа'},
        404: {'description': 'Мероприятие не найдено'}
    }
)
class UpcomingEventDetailView(views.APIView):
    """
    Детали мероприятия
    GET /api/v1/events/upcoming-events/<id>/
    PUT /api/v1/events/upcoming-events/<id>/
    PATCH /api/v1/events/upcoming-events/<id>/
    DELETE /api/v1/events/upcoming-events/<id>/
    """
    permission_classes = [permissions.AllowAny]
    
    def get_object(self, pk):
        """Мероприятие'ni olish"""
        try:
            event = UpcomingEvent.objects.get(pk=pk)
        except UpcomingEvent.DoesNotExist:
            raise NotFound('Мероприятие не найдено')
        
        # Неопубликованные мероприятия видны только создателю или администратору
        if event.status != 'published':
            if not self.request.user.is_authenticated or (event.created_by != self.request.user and not self.request.user.is_staff):
                raise PermissionDenied('Нет доступа к этому мероприятию')
        
        return event
    
    def get(self, request, pk):
        """GET: Получить мероприятие"""
        event = self.get_object(pk)
        serializer = UpcomingEventSerializer(event)
        return Response(serializer.data, status=status.HTTP_200_OK)
    
    @extend_schema(
        summary='Обновить мероприятие',
        request=UpcomingEventSerializer,
        responses={
            200: UpcomingEventSerializer,
            400: {'description': 'Ошибка валидации'},
            403: {'description': 'Нет доступа'}
        }
    )
    def put(self, request, pk):
        """PUT: Полностью обновить мероприятие"""
        event = self.get_object(pk)
        
        # Проверка прав
        if not request.user.is_authenticated or (event.created_by != request.user and not request.user.is_staff):
            raise PermissionDenied('Вы не можете обновить это мероприятие')
        
        serializer = UpcomingEventSerializer(event, data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    @extend_schema(
        summary='Частично обновить мероприятие',
        request=UpcomingEventSerializer,
        responses={
            200: UpcomingEventSerializer,
            400: {'description': 'Ошибка валидации'},
            403: {'description': 'Нет доступа'}
        }
    )
    def patch(self, request, pk):
        """PATCH: Частично обновить мероприятие"""
        event = self.get_object(pk)
        
        # Проверка прав
        if not request.user.is_authenticated or (event.created_by != request.user and not request.user.is_staff):
            raise PermissionDenied('Вы не можете обновить это мероприятие')
        
        serializer = UpcomingEventSerializer(event, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    @extend_schema(
        summary='Удалить мероприятие',
        responses={
            204: {'description': 'Мероприятие успешно удалено'},
            403: {'description': 'Нет доступа'}
        }
    )
    def delete(self, request, pk):
        """DELETE: Удалить мероприятие"""
        event = self.get_object(pk)
        
        # Проверка прав
        if not request.user.is_authenticated or (event.created_by != request.user and not request.user.is_staff):
            raise PermissionDenied('Вы не можете удалить это мероприятие')
        
        event.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


@extend_schema(
    tags=['Ratings'],
    summary='Получить рейтинги для административной панели',
    description='''
    GET: Получить список всех рейтингов для административной панели
    
    Возвращает список всех анкет (DesignerQuestionnaire, RepairQuestionnaire, SupplierQuestionnaire, MediaQuestionnaire)
    с агрегированными рейтингами:
    - Название организации ФИ (full_name / brand_name)
    - Группа (role)
    - Общий Рейтинг (total_rating_count)
    - Положительный Рейтинг (positive_rating_count)
    - Конструктивный Рейтинг (constructive_rating_count)
    
    Фильтры:
    - group: Фильтр по группе (Дизайн, Ремонт, Поставщик, Медиа)
    - search: Поиск по названию организации, ФИО
    - ordering: Сортировка (total_rating_count, -total_rating_count, positive_rating_count, -positive_rating_count)
    
    Требуется аутентификация.
    ''',
    responses={
        200: {'description': 'Список всех анкет с рейтингами'}
    }
)
class RatingPageView(views.APIView):
    """
    Рейтинги для административной панели
    GET /api/v1/events/ratings/
    """
    permission_classes = [permissions.IsAuthenticated]
    
    def get(self, request):
        from apps.ratings.models import QuestionnaireRating
        from apps.accounts.models import DesignerQuestionnaire, RepairQuestionnaire, SupplierQuestionnaire, MediaQuestionnaire
        
        # Barcha anketalarni olish va rating'lar bilan birlashtirish
        result = []
        
        # Фильтры
        group_filter = request.query_params.get('group')
        search = request.query_params.get('search')
        ordering = request.query_params.get('ordering', '-total_rating_count')
        
        # DesignerQuestionnaire
        designers = DesignerQuestionnaire.objects.filter(status='published', is_moderation=True)
        if group_filter and group_filter != 'Дизайн':
            designers = designers.none()
        if search:
            designers = designers.filter(
                django_models.Q(full_name__icontains=search) |
                django_models.Q(brand_name__icontains=search)
            )
        
        from apps.ratings.models import QuestionnaireRating
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
        repairs = RepairQuestionnaire.objects.filter(status='published', is_moderation=True)
        if group_filter and group_filter != 'Ремонт':
            repairs = repairs.none()
        if search:
            repairs = repairs.filter(
                django_models.Q(full_name__icontains=search) |
                django_models.Q(brand_name__icontains=search)
            )
        
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
        if group_filter and group_filter != 'Поставщик':
            suppliers = suppliers.none()
        if search:
            suppliers = suppliers.filter(
                django_models.Q(full_name__icontains=search) |
                django_models.Q(brand_name__icontains=search)
            )
        
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
        if group_filter and group_filter != 'Медиа':
            media = media.none()
        if search:
            media = media.filter(
                django_models.Q(full_name__icontains=search) |
                django_models.Q(brand_name__icontains=search)
            )
        
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
        
        # Сортировка
        reverse_order = ordering.startswith('-')
        sort_key = ordering.lstrip('-')
        
        if sort_key == 'total_rating_count':
            result.sort(key=lambda x: x['total_rating_count'], reverse=reverse_order)
        elif sort_key == 'positive_rating_count':
            result.sort(key=lambda x: x['positive_rating_count'], reverse=reverse_order)
        elif sort_key == 'constructive_rating_count':
            result.sort(key=lambda x: x['constructive_rating_count'], reverse=reverse_order)
        else:
            result.sort(key=lambda x: x['total_rating_count'], reverse=True)
        
        # Pagination
        paginator = LimitOffsetPagination()
        paginator.default_limit = 20
        paginator.max_limit = 100
        page = paginator.paginate_queryset(result, request)
        
        if page is not None:
            return paginator.get_paginated_response(page)
        
        return Response(result, status=status.HTTP_200_OK)


@extend_schema(
    tags=['Reviews'],
    summary='Получить отзывы для административной панели',
    description='''
    GET: Получить список всех отзывов для административной панели
    
    Возвращает список всех отзывов (QuestionnaireRating) с информацией:
    - ID отзыва
    - Оставивший отзыв (reviewer)
    - Роль (role)
    - ID анкеты (questionnaire_id)
    - Название организации/ФИО
    - Тип отзыва (is_positive, is_constructive)
    - Текст отзыва
    - Статус (pending, approved, rejected)
    - Дата создания
    
    Фильтры:
    - status: Фильтр по статусу (pending, approved, rejected)
    - role: Фильтр по роли (Поставщик, Ремонт, Дизайн, Медиа)
    - search: Поиск по тексту отзыва, имени рецензента
    - ordering: Сортировка (created_at, -created_at)
    
    Требуется аутентификация.
    ''',
    responses={
        200: {'description': 'Список всех отзывов'}
    }
)
class ReviewsPageView(views.APIView):
    """
    Отзывы для административной панели
    GET /api/v1/events/reviews/
    """
    permission_classes = [permissions.IsAuthenticated]
    
    def get(self, request):
        from apps.ratings.models import QuestionnaireRating
        from apps.ratings.serializers import QuestionnaireRatingSerializer
        queryset = QuestionnaireRating.objects.all()
        
        # Фильтры
        status_filter = request.query_params.get('status')
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        
        role_filter = request.query_params.get('role')
        if role_filter:
            queryset = queryset.filter(role=role_filter)
        
        # Поиск
        search = request.query_params.get('search')
        if search:
            queryset = queryset.filter(
                django_models.Q(text__icontains=search) |
                django_models.Q(reviewer__phone__icontains=search)
            )
        
        # Сортировка
        ordering = request.query_params.get('ordering', '-created_at')
        if ordering:
            queryset = queryset.order_by(ordering)
        
        # Pagination
        paginator = LimitOffsetPagination()
        paginator.default_limit = 20
        paginator.max_limit = 100
        page = paginator.paginate_queryset(queryset, request)
        
        if page is not None:
            serializer = QuestionnaireRatingSerializer(page, many=True)
            return paginator.get_paginated_response(serializer.data)
        
        serializer = QuestionnaireRatingSerializer(queryset, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)
