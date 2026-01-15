from rest_framework import permissions, status, views
from rest_framework.response import Response
from rest_framework.exceptions import PermissionDenied, NotFound
from rest_framework.pagination import LimitOffsetPagination
from django.utils import timezone
from django.db import models as django_models
from datetime import datetime
from drf_spectacular.utils import extend_schema, OpenApiParameter

from .models import UpcomingEvent
from .serializers import UpcomingEventSerializer


@extend_schema(
    tags=['Upcoming Events'],
    summary='Получить список ближайших мероприятий',
    description='''
    GET: Получить список ближайших мероприятий
    
    Фильтры:
    - city: Фильтр по городу (обязательно для получения событий)
    - event_date: Фильтр по дате события (формат: YYYY-MM-DD или YYYY-MM-DDTHH:MM:SS)
    - available_dates: Если true, возвращает только список дат с мероприятиями для выбранного города (требуется city)
    - event_type: Фильтр по типу мероприятия (training, presentation, opening, leisure)
    - status: Фильтр по статусу (draft, published, cancelled) - только для администраторов
    - search: Поиск по названию организации, анонсу, описанию
    - ordering: Сортировка (event_date, -event_date, created_at, -created_at)
    
    По умолчанию возвращаются только опубликованные мероприятия (status=published)
    
    Процесс фильтрации:
    1. Сначала выберите город (city)
    2. Для получения списка дат с мероприятиями: ?city=Москва&available_dates=true
    3. Затем выберите дату (event_date) для получения событий в этом городе на эту дату
    ''',
    parameters=[
        OpenApiParameter(
            name='city',
            type=str,
            location=OpenApiParameter.QUERY,
            description='Выберете город (обязательно для фильтрации)',
            required=False,
        ),
        OpenApiParameter(
            name='event_date',
            type=str,
            location=OpenApiParameter.QUERY,
            description='Дата события (формат: YYYY-MM-DD). После выбора города, выберите дату для получения событий',
            required=False,
        ),
        OpenApiParameter(
            name='event_type',
            type=str,
            location=OpenApiParameter.QUERY,
            description='Тип мероприятия (training, presentation, opening, leisure)',
            required=False,
            enum=['training', 'presentation', 'opening', 'leisure'],
        ),
        OpenApiParameter(
            name='status',
            type=str,
            location=OpenApiParameter.QUERY,
            description='Статус мероприятия (draft, published, cancelled) - только для администраторов',
            required=False,
            enum=['draft', 'published', 'cancelled'],
        ),
        OpenApiParameter(
            name='search',
            type=str,
            location=OpenApiParameter.QUERY,
            description='Поиск по названию организации, анонсу, описанию',
            required=False,
        ),
        OpenApiParameter(
            name='ordering',
            type=str,
            location=OpenApiParameter.QUERY,
            description='Сортировка (event_date, -event_date, created_at, -created_at)',
            required=False,
        ),
        OpenApiParameter(
            name='limit',
            type=int,
            location=OpenApiParameter.QUERY,
            description='Количество результатов на странице',
            required=False,
        ),
        OpenApiParameter(
            name='offset',
            type=int,
            location=OpenApiParameter.QUERY,
            description='Смещение для пагинации',
            required=False,
        ),
    ],
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
        # Выберете город (city) - birinchi bosqich
        city = self.request.query_params.get('city')
        if city:
            queryset = queryset.filter(city__icontains=city)
        
        # Выберете дату (event_date) - ikkinchi bosqich, shahar tanlangandan keyin
        event_date = self.request.query_params.get('event_date')
        if event_date:
            try:
                # Format: YYYY-MM-DD yoki YYYY-MM-DDTHH:MM:SS
                if 'T' in event_date:
                    date_obj = datetime.fromisoformat(event_date.replace('Z', '+00:00'))
                else:
                    date_obj = datetime.strptime(event_date, '%Y-%m-%d')
                
                # Kun bo'yicha filter (sana va vaqtni hisobga olgan holda)
                start_of_day = timezone.make_aware(datetime.combine(date_obj.date(), datetime.min.time()))
                end_of_day = timezone.make_aware(datetime.combine(date_obj.date(), datetime.max.time()))
                queryset = queryset.filter(event_date__gte=start_of_day, event_date__lte=end_of_day)
            except ValueError:
                # Noto'g'ri format bo'lsa, filter qo'llamaymiz
                pass
        
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
        
        # Сортировка - по умолчанию новые сначала (по id или created_at)
        ordering = self.request.query_params.get('ordering')
        if ordering:
            queryset = queryset.order_by(ordering)
        else:
            # По умолчанию: новые сначала (по убыванию id)
            queryset = queryset.order_by('-id')
        
        return queryset
    
    @extend_schema(
        summary='Получить список ближайших мероприятий',
        description='GET: Получить список ближайших мероприятий с фильтрацией',
        parameters=[
            OpenApiParameter(
                name='city',
                type=str,
                location=OpenApiParameter.QUERY,
                description='Выберете город (обязательно для фильтрации)',
                required=False,
            ),
            OpenApiParameter(
                name='event_date',
                type=str,
                location=OpenApiParameter.QUERY,
                description='Дата события (формат: YYYY-MM-DD). После выбора города, выберите дату для получения событий',
                required=False,
            ),
            OpenApiParameter(
                name='event_type',
                type=str,
                location=OpenApiParameter.QUERY,
                description='Тип мероприятия (training, presentation, opening, leisure)',
                required=False,
                enum=['training', 'presentation', 'opening', 'leisure'],
            ),
            OpenApiParameter(
                name='status',
                type=str,
                location=OpenApiParameter.QUERY,
                description='Статус мероприятия (draft, published, cancelled) - только для администраторов',
                required=False,
                enum=['draft', 'published', 'cancelled'],
            ),
            OpenApiParameter(
                name='search',
                type=str,
                location=OpenApiParameter.QUERY,
                description='Поиск по названию организации, анонсу, описанию',
                required=False,
            ),
            OpenApiParameter(
                name='ordering',
                type=str,
                location=OpenApiParameter.QUERY,
                description='Сортировка (event_date, -event_date, created_at, -created_at)',
                required=False,
            ),
            OpenApiParameter(
                name='limit',
                type=int,
                location=OpenApiParameter.QUERY,
                description='Количество результатов на странице',
                required=False,
            ),
            OpenApiParameter(
                name='offset',
                type=int,
                location=OpenApiParameter.QUERY,
                description='Смещение для пагинации',
                required=False,
            ),
            OpenApiParameter(
                name='available_dates',
                type=bool,
                location=OpenApiParameter.QUERY,
                description='Если true, возвращает только список дат с мероприятиями для выбранного города (формат: {"city": "Москва", "dates": [{"date": "2025-05-03", "event_count": 2}]})',
                required=False,
            ),
        ],
        responses={
            200: UpcomingEventSerializer(many=True),
        }
    )
    def get(self, request):
        """GET: Список мероприятий"""
        # Agar available_dates=true bo'lsa, faqat sanalarni qaytarish
        available_dates = request.query_params.get('available_dates', '').lower() == 'true'
        if available_dates:
            city = request.query_params.get('city')
            if not city:
                return Response(
                    {'error': 'Город не указан. Укажите параметр city'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Queryset - faqat published eventlar
            queryset = UpcomingEvent.objects.filter(status='published', city__icontains=city)
            
            # Kelajakdagi eventlar (bugundan keyingi)
            queryset = queryset.filter(event_date__gte=timezone.now())
            
            # Sanalar bo'yicha guruhlash
            from django.db.models import Count
            from django.db.models.functions import TruncDate
            
            # Har bir sana uchun eventlar sonini hisoblash
            dates_data = queryset.annotate(
                date_only=TruncDate('event_date')
            ).values('date_only').annotate(
                event_count=Count('id')
            ).order_by('date_only')
            
            # Format: [{'date': '2025-05-03', 'event_count': 2}, ...]
            dates_list = [
                {
                    'date': item['date_only'].strftime('%Y-%m-%d'),
                    'event_count': item['event_count']
                }
                for item in dates_data
            ]
            
            return Response({
                'city': city,
                'dates': dates_list
            }, status=status.HTTP_200_OK)
        
        # Oddiy list view
        queryset = self.get_queryset()
        
        # Pagination
        paginator = LimitOffsetPagination()
        paginator.default_limit = 20
        paginator.max_limit = 100
        page = paginator.paginate_queryset(queryset, request)
        
        if page is not None:
            serializer = UpcomingEventSerializer(page, many=True, context={'request': request})
            return paginator.get_paginated_response(serializer.data)
        
        serializer = UpcomingEventSerializer(queryset, many=True, context={'request': request})
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
        serializer = UpcomingEventSerializer(data=request.data, context={'request': request})
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
        serializer = UpcomingEventSerializer(event, context={'request': request})
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
        
        serializer = UpcomingEventSerializer(event, data=request.data, context={'request': request})
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
        
        serializer = UpcomingEventSerializer(event, data=request.data, partial=True, context={'request': request})
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
    - ordering: Сортировка (total_rating_count, -total_rating_count, positive_rating_count, -positive_rating_count, constructive_rating_count, -constructive_rating_count)
    
    Требуется аутентификация.
    ''',
    parameters=[
        OpenApiParameter(
            name='group',
            type=str,
            location=OpenApiParameter.QUERY,
            description='Фильтр по группе. Доступные значения: Дизайн, Ремонт, Поставщик, Медиа',
            required=False,
        ),
        OpenApiParameter(
            name='search',
            type=str,
            location=OpenApiParameter.QUERY,
            description='Поиск по названию организации или ФИО (частичное совпадение)',
            required=False,
        ),
        OpenApiParameter(
            name='ordering',
            type=str,
            location=OpenApiParameter.QUERY,
            description='Сортировка. Доступные значения: total_rating_count, -total_rating_count, positive_rating_count, -positive_rating_count, constructive_rating_count, -constructive_rating_count. По умолчанию: -total_rating_count',
            required=False,
        ),
    ],
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
        from django.db.models import Count, Q
        
        # Фильтры
        group_filter = request.query_params.get('group')
        search = request.query_params.get('search')
        ordering = request.query_params.get('ordering', '-total_rating_count')
        
        # Barcha approved rating'larni bir marta olish va cache qilish
        all_ratings = QuestionnaireRating.objects.filter(status='approved').select_related('reviewer')
        ratings_list = list(all_ratings)
        
        # Rating'larni role va questionnaire_id bo'yicha guruhlash
        ratings_cache = {}
        ratings_list_cache = {}  # rating_list va reviews_list uchun
        for rating in ratings_list:
            key = f"{rating.role}_{rating.questionnaire_id}"
            if key not in ratings_cache:
                ratings_cache[key] = {
                    'total_positive': 0,
                    'total_constructive': 0,
                }
                ratings_list_cache[key] = []
            if rating.is_positive:
                ratings_cache[key]['total_positive'] += 1
            if rating.is_constructive:
                ratings_cache[key]['total_constructive'] += 1
            # Rating list uchun
            ratings_list_cache[key].append(rating)
        
        result = []
        
        # DesignerQuestionnaire
        designers = DesignerQuestionnaire.objects.filter(status='published', is_moderation=True)
        if group_filter and group_filter != 'Дизайн':
            designers = designers.none()
        if search:
            designers = designers.filter(
                django_models.Q(full_name__icontains=search) |
                django_models.Q(brand_name__icontains=search)
            )
        
        designers_list = list(designers)
        
        for designer in designers_list:
            key = f"Дизайн_{designer.id}"
            rating_stats = ratings_cache.get(key, {'total_positive': 0, 'total_constructive': 0})
            
            # Faqat kerakli field'lar
            result.append({
                'request_name': 'DesignerQuestionnaire',
                'id': designer.id,
                'name': designer.full_name,
                'group': 'Дизайн',
                'total_rating_count': rating_stats['total_positive'],
                'positive_rating_count': rating_stats['total_positive'],
                'constructive_rating_count': rating_stats['total_constructive'],
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
        
        repairs_list = list(repairs)
        
        for repair in repairs_list:
            key = f"Ремонт_{repair.id}"
            rating_stats = ratings_cache.get(key, {'total_positive': 0, 'total_constructive': 0})
            
            # Faqat kerakli field'lar
            result.append({
                'request_name': 'RepairQuestionnaire',
                'id': repair.id,
                'name': repair.full_name or repair.brand_name,
                'group': 'Ремонт',
                'total_rating_count': rating_stats['total_positive'],
                'positive_rating_count': rating_stats['total_positive'],
                'constructive_rating_count': rating_stats['total_constructive'],
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
        
        suppliers_list = list(suppliers)
        
        for supplier in suppliers_list:
            key = f"Поставщик_{supplier.id}"
            rating_stats = ratings_cache.get(key, {'total_positive': 0, 'total_constructive': 0})
            
            # Faqat kerakli field'lar
            result.append({
                'request_name': 'SupplierQuestionnaire',
                'id': supplier.id,
                'name': supplier.full_name or supplier.brand_name,
                'group': 'Поставщик',
                'total_rating_count': rating_stats['total_positive'],
                'positive_rating_count': rating_stats['total_positive'],
                'constructive_rating_count': rating_stats['total_constructive'],
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
        
        media_list = list(media)
        
        for media_item in media_list:
            key = f"Медиа_{media_item.id}"
            rating_stats = ratings_cache.get(key, {'total_positive': 0, 'total_constructive': 0})
            
            # Faqat kerakli field'lar
            result.append({
                'request_name': 'MediaQuestionnaire',
                'id': media_item.id,
                'name': media_item.full_name or media_item.brand_name,
                'group': 'Медиа',
                'total_rating_count': rating_stats['total_positive'],
                'positive_rating_count': rating_stats['total_positive'],
                'constructive_rating_count': rating_stats['total_constructive'],
            })
        
        # Сортировка
        reverse_order = ordering.startswith('-')
        sort_key = ordering.lstrip('-')
        
        if sort_key == 'total_rating_count':
            result.sort(key=lambda x: x.get('total_rating_count', 0), reverse=reverse_order)
        elif sort_key == 'positive_rating_count':
            result.sort(key=lambda x: x.get('positive_rating_count', 0), reverse=reverse_order)
        elif sort_key == 'constructive_rating_count':
            result.sort(key=lambda x: x.get('constructive_rating_count', 0), reverse=reverse_order)
        else:
            result.sort(key=lambda x: x.get('total_rating_count', 0), reverse=True)
        
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
        
        # Сортировка: pending review'lar doim tepada
        from django.db.models import Case, When, IntegerField
        queryset = queryset.annotate(
            status_priority=Case(
                When(status='pending', then=0),
                default=1,
                output_field=IntegerField()
            )
        )
        
        ordering = request.query_params.get('ordering', '-created_at')
        if ordering:
            # Avval status_priority bo'yicha (pending=0, qolganlari=1), keyin ordering bo'yicha
            queryset = queryset.order_by('status_priority', ordering)
        else:
            # Agar ordering ko'rsatilmagan bo'lsa, faqat status_priority va created_at bo'yicha
            queryset = queryset.order_by('status_priority', '-created_at')
        
        # Pagination
        paginator = LimitOffsetPagination()
        paginator.default_limit = 20
        paginator.max_limit = 100
        page = paginator.paginate_queryset(queryset, request)
        
        if page is not None:
            serializer = QuestionnaireRatingSerializer(page, many=True, context={'request': request})
            return paginator.get_paginated_response(serializer.data)
        
        serializer = QuestionnaireRatingSerializer(queryset, many=True, context={'request': request})
        return Response(serializer.data, status=status.HTTP_200_OK)


@extend_schema(
    tags=['Reports'],
    summary='Получить аналитику и отчеты',
    description='''
    GET: Получить аналитику и отчеты по платформе
    
    Query параметры:
    - start_date: Начало периода (формат: YYYY-MM-DD). Если не указан, используется начало текущего месяца
    - end_date: Конец периода (формат: YYYY-MM-DD). Если не указан, используется текущая дата
    
    Возвращает:
    - period_stats: Статистика за выбранный период по группам
      * total: Общее количество пользователей за период
      * supplier: Количество поставщиков за период
      * repair: Количество группы ремонт за период
      * design: Количество группы Дизайн за период
      * media: Количество группы медиа за период
    
    - monthly_trends: График по месяцам - количество вошедших пользователей в определенных группах каждый месяц
      * Массив объектов с полями:
        * month: Месяц (формат: YYYY-MM)
        * supplier: Количество поставщиков
        * repair: Количество группы ремонт
        * design: Количество группы Дизайн
        * media: Количество группы медиа
        * total: Общее количество
    
    - current_totals: Показывает количество человек на платформе на текущий момент всегда
      * total: Общее количество участников
      * supplier: Поставщик
      * repair: Ремонт
      * design: Дизайн
      * media: Медиа
    
    Использование:
    1. Укажите период (start_date, end_date) для получения статистики за период
    2. monthly_trends показывает данные за последние 12 месяцев
    3. current_totals показывает актуальные данные на текущий момент
    ''',
    parameters=[
        OpenApiParameter(
            name='start_date',
            type=str,
            location=OpenApiParameter.QUERY,
            description='Начало периода (формат: YYYY-MM-DD)',
            required=False,
        ),
        OpenApiParameter(
            name='end_date',
            type=str,
            location=OpenApiParameter.QUERY,
            description='Конец периода (формат: YYYY-MM-DD)',
            required=False,
        ),
    ],
    responses={
        200: {'description': 'Аналитика и отчеты'},
        400: {'description': 'Ошибка валидации дат'}
    }
)
class ReportsAnalyticsView(views.APIView):
    """
    Получить аналитику и отчеты
    GET /api/v1/events/reports/
    """
    permission_classes = [permissions.IsAuthenticated]
    
    def get(self, request):
        from django.contrib.auth import get_user_model
        from datetime import datetime, timedelta
        from django.db.models import Count
        from django.db.models.functions import TruncMonth
        
        User = get_user_model()
        
        # Парсинг дат
        start_date_str = request.query_params.get('start_date')
        end_date_str = request.query_params.get('end_date')
        
        try:
            if start_date_str:
                start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
                start_datetime = timezone.make_aware(datetime.combine(start_date, datetime.min.time()))
            else:
                # По умолчанию - начало текущего месяца
                today = timezone.now().date()
                start_date = today.replace(day=1)
                start_datetime = timezone.make_aware(datetime.combine(start_date, datetime.min.time()))
            
            if end_date_str:
                end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
                end_datetime = timezone.make_aware(datetime.combine(end_date, datetime.max.time()))
            else:
                # По умолчанию - текущая дата
                end_datetime = timezone.now()
                end_date = end_datetime.date()
            
            # Agar start_date > end_date bo'lsa, ularni almashtirish
            if start_date > end_date:
                start_date, end_date = end_date, start_date
                start_datetime, end_datetime = end_datetime, start_datetime
        except ValueError:
            return Response(
                {'error': 'Неверный формат даты. Используйте формат YYYY-MM-DD'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # 1. Статистика за выбранный период (period_stats) - groups bo'yicha
        # Faqat groups'ga tegishli user'lar (Дизайн, Ремонт, Поставщик, Медиа)
        allowed_groups = ['Дизайн', 'Ремонт', 'Поставщик', 'Медиа']
        period_users = User.objects.filter(
            created_at__gte=start_datetime,
            created_at__lte=end_datetime,
            groups__name__in=allowed_groups
        ).prefetch_related('groups').distinct()
        
        period_stats = {
            'total': period_users.count(),
            'supplier': period_users.filter(groups__name='Поставщик').distinct().count(),
            'repair': period_users.filter(groups__name='Ремонт').distinct().count(),
            'design': period_users.filter(groups__name='Дизайн').distinct().count(),
            'media': period_users.filter(groups__name='Медиа').distinct().count(),
        }
        
        # 2. График по месяцам (monthly_trends) - groups bo'yicha
        # Faqat groups'ga tegishli user'lar (Дизайн, Ремонт, Поставщик, Медиа)
        allowed_groups = ['Дизайн', 'Ремонт', 'Поставщик', 'Медиа']
        if start_date_str and end_date_str:
            # Faqat berilgan period uchun
            monthly_data = User.objects.filter(
                created_at__gte=start_datetime,
                created_at__lte=end_datetime,
                groups__name__in=allowed_groups
            ).prefetch_related('groups').distinct().annotate(
                month=TruncMonth('created_at')
            ).values('month', 'id').order_by('month')
        else:
            # Oxirgi 12 oy uchun
            twelve_months_ago = timezone.now() - timedelta(days=365)
            monthly_data = User.objects.filter(
                created_at__gte=twelve_months_ago,
                groups__name__in=allowed_groups
            ).prefetch_related('groups').distinct().annotate(
            month=TruncMonth('created_at')
            ).values('month', 'id').order_by('month')
        
        # Формируем структуру для графика
        monthly_dict = {}
        for user_data in monthly_data:
            # YYYY-MM-DD formatida (oyning birinchi kuni)
            month_str = user_data['month'].strftime('%Y-%m-01')
            if month_str not in monthly_dict:
                monthly_dict[month_str] = {
                    'month': month_str,
                    'supplier': 0,
                    'repair': 0,
                    'design': 0,
                    'media': 0,
                    'total': 0
                }
            
            # User'ning groups'larini olish
            try:
                user = User.objects.get(id=user_data['id'])
                user_groups = list(user.groups.values_list('name', flat=True))
                
                if 'Поставщик' in user_groups:
                    monthly_dict[month_str]['supplier'] += 1
                if 'Ремонт' in user_groups:
                    monthly_dict[month_str]['repair'] += 1
                if 'Дизайн' in user_groups:
                    monthly_dict[month_str]['design'] += 1
                if 'Медиа' in user_groups:
                    monthly_dict[month_str]['media'] += 1
            except User.DoesNotExist:
                continue
        
        # Вычисляем total для каждого месяца
        for month_str in monthly_dict:
            monthly_dict[month_str]['total'] = (
                monthly_dict[month_str]['supplier'] +
                monthly_dict[month_str]['repair'] +
                monthly_dict[month_str]['design'] +
                monthly_dict[month_str]['media']
            )
        
        # Преобразуем в список и сортируем
        monthly_trends = sorted(monthly_dict.values(), key=lambda x: x['month'])
        
        # 2.1. График по дням (daily_trends) - agar start_date va end_date berilsa
        daily_trends = []
        if start_date_str and end_date_str:
            from django.db.models.functions import TruncDate
            
            # Har bir kun uchun ma'lumot olish - faqat groups'ga tegishli user'lar
            allowed_groups = ['Дизайн', 'Ремонт', 'Поставщик', 'Медиа']
            daily_data = User.objects.filter(
                created_at__gte=start_datetime,
                created_at__lte=end_datetime,
                groups__name__in=allowed_groups
            ).prefetch_related('groups').distinct().annotate(
                day=TruncDate('created_at')
            ).values('day', 'id').order_by('day')
            
            # Avval barcha kunlar uchun bo'sh dict yaratish
            daily_dict = {}
            current_date = start_date
            while current_date <= end_date:
                day_str = current_date.strftime('%Y-%m-%d')
                daily_dict[day_str] = {
                    'date': day_str,
                    'supplier': 0,
                    'repair': 0,
                    'design': 0,
                    'media': 0,
                    'total': 0
                }
                current_date += timedelta(days=1)
            
            # Keyin user'lar ma'lumotlarini qo'shish
            for user_data in daily_data:
                day_str = user_data['day'].strftime('%Y-%m-%d')
                
                # Agar kun dict'da bo'lmasa, yaratish (ehtimol timezone muammosi)
                if day_str not in daily_dict:
                    daily_dict[day_str] = {
                        'date': day_str,
                        'supplier': 0,
                        'repair': 0,
                        'design': 0,
                        'media': 0,
                        'total': 0
                    }
                
                # User'ning groups'larini olish
                try:
                    user = User.objects.get(id=user_data['id'])
                    user_groups = list(user.groups.values_list('name', flat=True))
                    
                    if 'Поставщик' in user_groups:
                        daily_dict[day_str]['supplier'] += 1
                    if 'Ремонт' in user_groups:
                        daily_dict[day_str]['repair'] += 1
                    if 'Дизайн' in user_groups:
                        daily_dict[day_str]['design'] += 1
                    if 'Медиа' in user_groups:
                        daily_dict[day_str]['media'] += 1
                except User.DoesNotExist:
                    continue
            
            # Вычисляем total для каждого дня
            for day_str in daily_dict:
                daily_dict[day_str]['total'] = (
                    daily_dict[day_str]['supplier'] +
                    daily_dict[day_str]['repair'] +
                    daily_dict[day_str]['design'] +
                    daily_dict[day_str]['media']
                )
            
            # Преобразуем в список и сортируем
            daily_trends = sorted(daily_dict.values(), key=lambda x: x['date'])
        
        # 3. Текущие общие показатели (current_totals) - всегда актуальные данные - groups bo'yicha
        # Faqat groups'ga tegishli user'lar (Дизайн, Ремонт, Поставщик, Медиа)
        allowed_groups = ['Дизайн', 'Ремонт', 'Поставщик', 'Медиа']
        all_users = User.objects.filter(groups__name__in=allowed_groups).prefetch_related('groups').distinct()
        current_totals = {
            'total': all_users.count(),
            'supplier': all_users.filter(groups__name='Поставщик').distinct().count(),
            'repair': all_users.filter(groups__name='Ремонт').distinct().count(),
            'design': all_users.filter(groups__name='Дизайн').distinct().count(),
            'media': all_users.filter(groups__name='Медиа').distinct().count(),
        }
        
        response_data = {
            'period_stats': period_stats,
            'monthly_trends': monthly_trends,
            'current_totals': current_totals,
            'period': {
                'start_date': start_date_str or start_date.strftime('%Y-%m-%d'),
                'end_date': end_date_str or end_date.strftime('%Y-%m-%d')
            }
        }
        
        # Agar daily_trends bo'lsa, qo'shamiz
        if daily_trends:
            response_data['daily_trends'] = daily_trends
        
        return Response(response_data, status=status.HTTP_200_OK)


@extend_schema(
    tags=['Reports'],
    summary='Получить все отчеты',
    description='''
    GET: Получить список всех отчетов (Report model)
    
    Возвращает список всех отчетов с информацией:
    - name: Название организации ФИ (full_name пользователя)
    - group: Группа (role display: Дизайнер, Ремонт, Поставщик, Медиа)
    - start_date: Дата начала периода (формат: DD.MM.YYYY)
    - next_payment_date: Следующая оплата / Дата окончания периода (формат: DD.MM.YYYY)
    
    Фильтры:
    - user_id: Фильтр по ID пользователя
    - start_date: Фильтр по дате начала (формат: YYYY-MM-DD)
    - end_date: Фильтр по дате окончания (формат: YYYY-MM-DD)
    - search: Поиск по телефону или имени пользователя
    
    Требуется аутентификация.
    ''',
    parameters=[
        OpenApiParameter(
            name='user_id',
            type=int,
            location=OpenApiParameter.QUERY,
            description='Фильтр по ID пользователя',
            required=False,
        ),
        OpenApiParameter(
            name='start_date',
            type=str,
            location=OpenApiParameter.QUERY,
            description='Фильтр по дате начала (формат: YYYY-MM-DD)',
            required=False,
        ),
        OpenApiParameter(
            name='end_date',
            type=str,
            location=OpenApiParameter.QUERY,
            description='Фильтр по дате окончания (формат: YYYY-MM-DD)',
            required=False,
        ),
        OpenApiParameter(
            name='search',
            type=str,
            location=OpenApiParameter.QUERY,
            description='Поиск по телефону пользователя',
            required=False,
        ),
        OpenApiParameter(
            name='ordering',
            type=str,
            location=OpenApiParameter.QUERY,
            description='Сортировка (created_at, -created_at, start_date, -start_date)',
            required=False,
        ),
        OpenApiParameter(
            name='limit',
            type=int,
            location=OpenApiParameter.QUERY,
            description='Количество результатов на странице',
            required=False,
        ),
        OpenApiParameter(
            name='offset',
            type=int,
            location=OpenApiParameter.QUERY,
            description='Смещение для пагинации',
            required=False,
        ),
    ],
    responses={
        200: {'description': 'Список всех отчетов'},
        400: {'description': 'Ошибка валидации'}
    }
)
class AllReportsView(views.APIView):
    """
    Получить все отчеты
    GET /api/v1/events/reports/all/
    """
    permission_classes = [permissions.IsAuthenticated]
    
    def get(self, request):
        from apps.accounts.models import Report
        from django.contrib.auth import get_user_model
        from datetime import datetime
        
        User = get_user_model()
        
        # Фильтры
        user_id = request.query_params.get('user_id')
        start_date_str = request.query_params.get('start_date')
        end_date_str = request.query_params.get('end_date')
        search = request.query_params.get('search')
        ordering = request.query_params.get('ordering', '-created_at')
        
        # Queryset
        queryset = Report.objects.select_related('user').all()
        
        # Фильтр по user_id
        if user_id:
            try:
                queryset = queryset.filter(user_id=int(user_id))
            except ValueError:
                return Response(
                    {'error': 'Неверный формат user_id'},
                    status=status.HTTP_400_BAD_REQUEST
                )
        
        # Фильтр по start_date
        if start_date_str:
            try:
                start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
                queryset = queryset.filter(start_date=start_date)
            except ValueError:
                return Response(
                    {'error': 'Неверный формат даты. Используйте формат YYYY-MM-DD'},
                    status=status.HTTP_400_BAD_REQUEST
                )
        
        # Фильтр по end_date
        if end_date_str:
            try:
                end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
                queryset = queryset.filter(end_date=end_date)
            except ValueError:
                return Response(
                    {'error': 'Неверный формат даты. Используйте формат YYYY-MM-DD'},
                    status=status.HTTP_400_BAD_REQUEST
                )
        
        # Поиск по телефону или имени
        if search:
            queryset = queryset.filter(
                django_models.Q(user__phone__icontains=search) |
                django_models.Q(user__full_name__icontains=search)
            )
        
        # Сортировка
        valid_ordering = ['created_at', '-created_at', 'start_date', '-start_date', 
                         'end_date', '-end_date', 'updated_at', '-updated_at']
        if ordering in valid_ordering:
            queryset = queryset.order_by(ordering)
        else:
            queryset = queryset.order_by('-created_at')
        
        # Пагинация
        paginator = LimitOffsetPagination()
        paginated_queryset = paginator.paginate_queryset(queryset, request)
        
        # Сериализация
        results = []
        for report in paginated_queryset:
            # Group ni user.groups dan olish
            user_groups = report.user.groups.all()
            if user_groups.exists():
                # Birinchi group nomini olish
                group = user_groups.first().name
            else:
                # Agar groups bo'lmasa, role'dan olish (fallback)
                role_display_map = {
                    'designer': 'Дизайнер',
                    'repair': 'Ремонт',
                    'supplier': 'Поставщик',
                    'media': 'Медиа'
                }
                group = role_display_map.get(report.user.role, report.user.role or 'Не указано')
            
            # Full name olish
            name = report.user.full_name or report.user.phone or 'Не указано'
            
            results.append({
                'name': name,
                'group': group,
                'start_date': report.start_date.strftime('%d.%m.%Y'),
                'next_payment_date': report.end_date.strftime('%d.%m.%Y'),
            })
        
        return paginator.get_paginated_response(results)
