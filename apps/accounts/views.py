from rest_framework import status, permissions, views
from rest_framework.response import Response
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework.exceptions import NotFound, PermissionDenied
from rest_framework.pagination import LimitOffsetPagination
from django.contrib.auth import get_user_model, models as auth_models
from django.db import models as django_models
from django.utils import timezone
from drf_spectacular.utils import extend_schema, OpenApiParameter

from .serializers import (
    PhoneLoginSerializer,
    VerifySMSCodeSerializer,
    AdminLoginSerializer,
    UserProfileSerializer,
    UserPublicSerializer,
    DesignerQuestionnaireSerializer,
    RepairQuestionnaireSerializer,
    SupplierQuestionnaireSerializer,
    MediaQuestionnaireSerializer,
    QuestionnaireStatusUpdateSerializer,
    GroupSerializer,
)
from .models import SMSVerificationCode, DesignerQuestionnaire, RepairQuestionnaire, SupplierQuestionnaire, MediaQuestionnaire, Report

User = get_user_model()


@extend_schema(
    tags=['Authentification'],
    request=PhoneLoginSerializer,
    responses={200: {'description': 'SMS kod yuborildi'}}
)
class SendSMSCodeView(views.APIView):
    """
    SMS kod yuborish
    POST /api/v1/accounts/login/
    {
        "phone": "+79991234567"
    }
    """
    permission_classes = [permissions.AllowAny]
    
    def post(self, request):
        serializer = PhoneLoginSerializer(data=request.data)
        if serializer.is_valid():
            sms_code = serializer.save()
            phone = serializer.validated_data['phone']
            
            # O'zbekiston raqamlari uchun SMS kodini response'ga qo'shish
            clean_phone = ''.join(filter(str.isdigit, phone))
            is_uzbekistan = clean_phone.startswith('998')
            
            response_data = {
                'message': 'SMS код отправлен',
                'phone': phone
            }
            
            # O'zbekiston raqamlari uchun SMS kodini qo'shamiz
            if is_uzbekistan:
                response_data['code'] = sms_code.code
                response_data['note'] = 'Для узбекских номеров код отправлен в ответе'
            
            return Response(response_data, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@extend_schema(
    tags=['Authentification'],
    request=VerifySMSCodeSerializer,
    responses={200: {'description': 'Muvaffaqiyatli kirildi'}}
)
class VerifySMSCodeView(views.APIView):
    """
    SMS kodni tekshirish va token olish
    POST /api/v1/accounts/verify-sms/
    {
        "phone": "+79991234567",
        "code": "1234"
    }
    """
    permission_classes = [permissions.AllowAny]
    
    def post(self, request):
        serializer = VerifySMSCodeSerializer(data=request.data)
        if serializer.is_valid():
            phone = serializer.validated_data['phone']
            
            # Foydalanuvchini topish
            try:
                user = User.objects.get(phone=phone)
                # Foydalanuvchi mavjud, yangilash
                user.is_phone_verified = True
                user.save()
            except User.DoesNotExist:
                # Foydalanuvchi mavjud emas
                return Response(
                    {'error': 'Пользователь не найден. Обратитесь к администратору для создания аккаунта.'},
                    status=status.HTTP_404_NOT_FOUND
                )
            
            # JWT token yaratish
            refresh = RefreshToken.for_user(user)
            
            return Response({
                'message': 'Успешный вход',
                'tokens': {
                    'refresh': str(refresh),
                    'access': str(refresh.access_token),
                }
            }, status=status.HTTP_200_OK)
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@extend_schema(
    tags=['Authentification'],
    summary='Вход для администратора (телефон и пароль)',
    description='''
    Вход для администратора - только для пользователей с is_staff=True
    
    Тело запроса:
    - phone: Телефонный номер
    - password: Пароль
    
    Ответ:
    - tokens: JWT access и refresh токены
    ''',
    request=AdminLoginSerializer,
    responses={
        200: {
            'description': 'Успешный вход',
            'content': {
                'application/json': {
                    'example': {
                        'message': 'Успешный вход',
                        'tokens': {
                            'access': 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...',
                            'refresh': 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...'
                        }
                    }
                }
            }
        },
        400: {'description': 'Ошибка валидации'},
        403: {'description': 'Доступ запрещен (не администратор)'}
    }
)
class AdminLoginView(views.APIView):
    """
    Admin login - phone va password bilan
    POST /api/v1/accounts/login-admin/
    {
        "phone": "+79991234567",
        "password": "admin123"
    }
    """
    permission_classes = [permissions.AllowAny]
    
    def post(self, request):
        serializer = AdminLoginSerializer(data=request.data)
        if serializer.is_valid():
            user = serializer.validated_data['user']
            
            # JWT token yaratish
            refresh = RefreshToken.for_user(user)
            
            return Response({
                'message': 'Успешный вход',
                'tokens': {
                    'refresh': str(refresh),
                    'access': str(refresh.access_token),
                }
            }, status=status.HTTP_200_OK)
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@extend_schema(
    tags=['Roles'],
    summary='Список групп (Groups) с флагом is_locked',
    description="""
    Возвращает список всех групп (`django.contrib.auth.models.Group`).

    - Для группы **"Медиа"**: `is_locked = false` для всех пользователей (авторизованных и неавторизованных)
    
    - Для остальных групп:
      - Если запрос выполняет **авторизованный пользователь**:
        - для групп, в которых он состоит (`user.groups`), поле `is_locked = true`
        - для остальных групп `is_locked = false`
      - Если `request.user` **не авторизован**:
        - для всех групп (кроме "Медиа") `is_locked = false`

    Пример ответа для неавторизованного пользователя:
    ```json
    [
      {"id": 1, "name": "designer", "is_locked": false},
      {"id": 2, "name": "repair", "is_locked": false},
      {"id": 3, "name": "Медиа", "is_locked": false}
    ]
    ```

    Пример ответа для авторизованного пользователя,
    состоящего в группе `designer`:
    ```json
    [
      {"id": 1, "name": "designer", "is_locked": true},
      {"id": 2, "name": "repair", "is_locked": false},
      {"id": 3, "name": "Медиа", "is_locked": false}
    ]
    ```
    """,
    responses={
        200: GroupSerializer(many=True),
        400: {'description': 'Ошибка валидации'}
    },
)
class UserRolesView(views.APIView):
    """
    Список групп (Groups) с флагом is_locked

    GET /api/v1/accounts/roles/
    """
    # Позволяем вызывать всем, но внутри учитываем request.user
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        groups = auth_models.Group.objects.all().order_by('id')

        user_groups_ids = set()
        if request.user and request.user.is_authenticated:
            user_groups_ids = set(request.user.groups.values_list('id', flat=True))

        data = []
        for g in groups:
            # Если группа называется "Медиа", то is_locked всегда False для всех пользователей
            if g.name == 'Медиа':
                is_locked = False
            else:
                # Для остальных групп: is_locked = True если пользователь в этой группе
                is_locked = g.id in user_groups_ids
            
            data.append({
                'id': g.id,
                'name': g.name,
                'is_locked': is_locked,
            })

        # Прямо возвращаем данные без отдельного сериализатора
        return Response(data, status=status.HTTP_200_OK)


@extend_schema(
    tags=['Accounts'],
    summary='Список пользователей',
    description='''
    GET: Получить список пользователей
    
    Возвращает список пользователей с ролями:
    - Дизайн (designer)
    - Медиа (media)
    - Поставщик (supplier)
    - Ремонт (repair)
    
    Фильтры:
    - role: Фильтр по роли (designer, repair, supplier, media)
    - city: Фильтр по городу
    - search: Поиск по имени, описанию, названию компании
    - is_active_profile: Фильтр по активным профилям (true/false)
    - ordering: Сортировка (created_at, -created_at, full_name, -full_name)
    
    По умолчанию возвращаются только пользователи с is_active_profile=True
    ''',
    responses={
        200: UserPublicSerializer(many=True)
    }
)
class UserListView(views.APIView):
    """
    Список пользователей
    GET /api/v1/accounts/users/
    """
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        """Queryset'ni olish"""
        if getattr(self, 'swagger_fake_view', False):
            return User.objects.none()
        
        # Faqat Дизайн, Медиа, Поставщик, Ремонт role'lardagi userlar
        allowed_roles = ['designer', 'repair', 'supplier', 'media']
        queryset = User.objects.filter(role__in=allowed_roles)
        
        # По умолчанию только активные профили
        is_active_profile = self.request.query_params.get('is_active_profile')
        if is_active_profile is None:
            # По умолчанию только активные
            queryset = queryset.filter(is_active_profile=True)
        elif is_active_profile.lower() == 'true':
            queryset = queryset.filter(is_active_profile=True)
        elif is_active_profile.lower() == 'false':
            queryset = queryset.filter(is_active_profile=False)
        
        # Фильтры
        role = self.request.query_params.get('role')
        if role and role in allowed_roles:
            queryset = queryset.filter(role=role)
        
        city = self.request.query_params.get('city')
        if city:
            queryset = queryset.filter(city__icontains=city)
        
        # Поиск
        search = self.request.query_params.get('search')
        if search:
            queryset = queryset.filter(
                django_models.Q(full_name__icontains=search) |
                django_models.Q(description__icontains=search) |
                django_models.Q(company_name__icontains=search)
            )
        
        # Сортировка
        ordering = self.request.query_params.get('ordering', '-created_at')
        if ordering:
            queryset = queryset.order_by(ordering)
        
        return queryset
    
    def get(self, request):
        """GET: Список пользователей"""
        queryset = self.get_queryset()
        
        # Pagination
        paginator = LimitOffsetPagination()
        paginator.default_limit = 20
        paginator.max_limit = 100
        page = paginator.paginate_queryset(queryset, request)
        
        if page is not None:
            serializer = UserPublicSerializer(page, many=True)
            return paginator.get_paginated_response(serializer.data)
        
        serializer = UserPublicSerializer(queryset, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)


@extend_schema(
    tags=['Accounts'],
    responses={
        200: UserProfileSerializer,
        400: {'description': 'Ошибка валидации'}
    }
)
class UserProfileView(views.APIView):
    """
    Foydalanuvchi profilini ko'rish va yangilash
    GET /api/v1/accounts/profile/ - profilni ko'rish
    PUT /api/v1/accounts/profile/ - profilni yangilash
    """
    permission_classes = [permissions.IsAuthenticated]
    
    def get(self, request):
        serializer = UserProfileSerializer(request.user)
        return Response(serializer.data, status=status.HTTP_200_OK)
    
    @extend_schema(
        request=UserProfileSerializer,
        responses={
            200: UserProfileSerializer,
            400: {'description': 'Ошибка валидации'}
        }
    )
    def put(self, request):
        serializer = UserProfileSerializer(request.user, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@extend_schema(
    tags=['All Questionnaires'],
    summary='Архив всех удаленных анкет',
    description='''
    GET: Получить список всех удаленных анкет (только для администраторов)
    
    Возвращает объединенный список всех удаленных анкет:
    - DesignerQuestionnaire
    - RepairQuestionnaire
    - SupplierQuestionnaire
    - MediaQuestionnaire
    
    Требуется авторизация и права администратора (is_staff=True)
    ''',
    responses={
        200: {'description': 'Список всех удаленных анкет'},
        403: {'description': 'Доступ запрещен. Только администраторы могут просматривать архив'}
    }
)
class QuestionnaireArchiveListView(views.APIView):
    """
    Архив всех удаленных анкет
    GET /api/v1/accounts/questionnaires/all/archive/ - список всех удаленных анкет
    """
    permission_classes = [permissions.IsAuthenticated]
    
    def get(self, request):
        # Faqat staff userlar archive'ni ko'rishlari mumkin
        if not request.user.is_staff:
            raise PermissionDenied("Только администратор может просматривать архив")
        
        # Получаем все удаленные анкеты
        designer_questionnaires = DesignerQuestionnaire.objects.filter(is_deleted=True)
        designer_serializer = DesignerQuestionnaireSerializer(designer_questionnaires, many=True)
        
        repair_questionnaires = RepairQuestionnaire.objects.filter(is_deleted=True)
        repair_serializer = RepairQuestionnaireSerializer(repair_questionnaires, many=True)
        
        supplier_questionnaires = SupplierQuestionnaire.objects.filter(is_deleted=True)
        supplier_serializer = SupplierQuestionnaireSerializer(supplier_questionnaires, many=True)
        
        media_questionnaires = MediaQuestionnaire.objects.filter(is_deleted=True)
        media_serializer = MediaQuestionnaireSerializer(media_questionnaires, many=True)
        
        # Объединяем результаты
        combined_data = list(designer_serializer.data) + list(repair_serializer.data) + list(supplier_serializer.data) + list(media_serializer.data)
        
        # Сортируем по дате создания (новые первыми)
        combined_data.sort(key=lambda x: x.get('created_at', ''), reverse=True)
        
        # Pagination
        paginator = LimitOffsetPagination()
        paginator.default_limit = 100
        paginator.limit_query_param = 'limit'
        paginator.offset_query_param = 'offset'
        
        limit = request.query_params.get('limit')
        offset = request.query_params.get('offset')
        
        if limit:
            try:
                limit = int(limit)
                if limit > 0:
                    paginator.default_limit = limit
            except ValueError:
                pass
        
        if offset:
            try:
                offset = int(offset)
            except ValueError:
                offset = 0
        else:
            offset = 0
        
        page = paginator.paginate_queryset(combined_data, request)
        if page is not None:
            return paginator.get_paginated_response(page)
        
        return Response(combined_data, status=status.HTTP_200_OK)


@extend_schema(
    tags=['All Questionnaires'],
    summary='Общий список всех анкет',
    description='''
    GET: Получить объединенный список всех анкет (дизайнеров, ремонтных бригад/подрядчиков, поставщиков/салонов/фабрик и медиа пространств/интерьерных журналов)
    
    Каждая запись содержит:
    - id: ID анкеты
    - request_name: Название модели для определения endpoint деталей ("DesignerQuestionnaire", "RepairQuestionnaire", "SupplierQuestionnaire" или "MediaQuestionnaire")
    - group: Группа
    - group_display: Отображаемое название группы
    - full_name: ФИО
    - и другие поля в зависимости от типа анкеты
    
    Для получения деталей используйте:
    - Если request_name = "DesignerQuestionnaire": GET /api/v1/accounts/questionnaires/{id}/
    - Если request_name = "RepairQuestionnaire": GET /api/v1/accounts/repair-questionnaires/{id}/
    - Если request_name = "SupplierQuestionnaire": GET /api/v1/accounts/supplier-questionnaires/{id}/
    - Если request_name = "MediaQuestionnaire": GET /api/v1/accounts/media-questionnaires/{id}/
    ''',
    responses={
        200: {'description': 'Список всех анкет'}
    }
)
class QuestionnaireListView(views.APIView):
    """
    Общий список всех анкет (дизайнеров, ремонтных бригад/подрядчиков, поставщиков/салонов/фабрик и медиа пространств/интерьерных журналов)
    GET /api/v1/accounts/questionnaires/all/
    """
    permission_classes = [permissions.AllowAny]
    
    def get(self, request):
        # Staff userlar uchun barcha questionnaire'lar, oddiy userlar uchun faqat is_moderation=True
        is_staff = request.user.is_authenticated and request.user.is_staff
        
        # Получаем все анкеты дизайнеров
        if is_staff:
            designer_questionnaires = DesignerQuestionnaire.objects.filter(is_deleted=False)
        else:
            designer_questionnaires = DesignerQuestionnaire.objects.filter(is_moderation=True, is_deleted=False)
        designer_serializer = DesignerQuestionnaireSerializer(designer_questionnaires, many=True)
        
        # Получаем все анкеты ремонтных бригад/подрядчиков
        if is_staff:
            repair_questionnaires = RepairQuestionnaire.objects.filter(is_deleted=False)
        else:
            repair_questionnaires = RepairQuestionnaire.objects.filter(is_moderation=True, is_deleted=False)
        repair_serializer = RepairQuestionnaireSerializer(repair_questionnaires, many=True)
        
        # Получаем все анкеты поставщиков/салонов/фабрик
        if is_staff:
            supplier_questionnaires = SupplierQuestionnaire.objects.filter(is_deleted=False)
        else:
            supplier_questionnaires = SupplierQuestionnaire.objects.filter(is_moderation=True, is_deleted=False)
        supplier_serializer = SupplierQuestionnaireSerializer(supplier_questionnaires, many=True)
        
        # Получаем все анкеты медиа пространств и интерьерных журналов
        if is_staff:
            media_questionnaires = MediaQuestionnaire.objects.filter(is_deleted=False)
        else:
            media_questionnaires = MediaQuestionnaire.objects.filter(is_moderation=True, is_deleted=False)
        media_serializer = MediaQuestionnaireSerializer(media_questionnaires, many=True)
        
        # Объединяем результаты
        combined_data = list(designer_serializer.data) + list(repair_serializer.data) + list(supplier_serializer.data) + list(media_serializer.data)
        
        # Сортируем по дате создания (новые первыми)
        combined_data.sort(key=lambda x: x.get('created_at', ''), reverse=True)
        
        # Pagination
        paginator = LimitOffsetPagination()
        paginator.default_limit = 100
        paginator.limit_query_param = 'limit'
        paginator.offset_query_param = 'offset'
        
        limit = request.query_params.get('limit')
        offset = request.query_params.get('offset')
        
        if limit:
            limit = int(limit)
            offset = int(offset) if offset else 0
            paginated_data = combined_data[offset:offset + limit]
            total_count = len(combined_data)
            
            return Response({
                'count': total_count,
                'next': f"?limit={limit}&offset={offset + limit}" if offset + limit < total_count else None,
                'previous': f"?limit={limit}&offset={offset - limit}" if offset > 0 else None,
                'results': paginated_data
            }, status=status.HTTP_200_OK)
        
        return Response(combined_data, status=status.HTTP_200_OK)


@extend_schema(
    tags=['Accounts'],
    responses={
        200: UserPublicSerializer,
        404: {'description': 'Пользователь не найден'}
    }
)
class UserPublicProfileView(views.APIView):
    """
    Boshqa foydalanuvchining profilini ko'rish (umumiy)
    GET /api/v1/accounts/users/{id}/
    """
    permission_classes = [permissions.IsAuthenticated]
    
    def get_object(self, user_id):
        try:
            return User.objects.get(id=user_id, is_active_profile=True)
        except User.DoesNotExist:
            raise NotFound("Пользователь не найден")
    
    def get(self, request, id):
        user = self.get_object(id)
        serializer = UserPublicSerializer(user)
        return Response(serializer.data, status=status.HTTP_200_OK)


@extend_schema(
    tags=['Designer Questionnaires'],
    summary='Список анкет дизайнеров',
    description='''
    GET: Получить список всех анкет дизайнеров
    
    POST: Создать новую анкету дизайнера
    
    Поля анкеты:
    - group: Группа (обязательное). Варианты:
      * designer - Дизайнер
      * architect - Архитектор
      * decorator - Декоратор
      * landscape_designer - Ландшафтный дизайнер
      * light_designer - Светодизайнер
      * interior_designer - Дизайнер интерьера
      * repair_team - Ремонтная бригада
      * contractor - Подрядчик
      * supplier - Поставщик
      * exhibition_hall - Выставочный зал
      * factory - Фабрика
    - full_name: ФИО (обязательное)
    - full_name_en: ФИ на английском (необязательное)
    - phone: Номер телефона (обязательное)
    - birth_date: Дата рождения (необязательное, формат: YYYY-MM-DD)
    - email: E-mail (обязательное)
    - city: Город проживания (обязательное)
    - services: Услуги (массив, обязательное). Варианты:
      * author_supervision - Авторский надзор
      * architecture - Архитектура
      * decorator - Декоратор
      * designer_horika - Дизайнер Хорика
      * residential_designer - Дизайнер жилой недвижимости
      * commercial_designer - Дизайнер коммерческой недвижимости
      * completing - Комплектация
      * landscape_design - Ландшафтный дизайн
      * design - Проектирование
      * light_designer - Светодизайнер
      * home_stager - Хоумстейджер
    - work_type: Тип работы (необязательное). Варианты:
      * own_name - Под собственным именем
      * studio - В студии
    - welcome_message: Приветственное сообщение о вас и вашем опыте (необязательное)
    - work_cities: Города работы (массив, необязательное)
    - cooperation_terms: Условия сотрудничества при работе с объектами в других городах или регионах (необязательное)
    - segments: Сегменты работы (массив, необязательное). Варианты:
      * horeca - HoReCa
      * business - Бизнес
      * comfort - Комфорт
      * premium - Премиум
      * medium - Средний
      * economy - Эконом
    - unique_trade_proposal: Ваше уникальное торговое предложение (УТП) (необязательное)
    - vk: VK (необязательное)
    - telegram_channel: Telegram канал (необязательное)
    - pinterest: Pinterest (необязательное)
    - instagram: Instagram (необязательное)
    - website: Ваш сайт (необязательное, URL)
    - other_contacts: Другое - дополнительные контакты (массив, необязательное)
    - service_packages_description: Подробное описание пакетов услуг с указанием стоимости (необязательное)
    - vat_payment: Возможна ли оплата с учётом НДС? (необязательное). Варианты:
      * yes - Да
      * no - Нет
    - supplier_contractor_recommendation_terms: Условия сотрудничества по рекомендациям от поставщиков или подрядчиков (необязательное)
    - additional_info: Дополнительная информация (необязательное)
    - data_processing_consent: Согласие на обработку данных (обязательное, boolean)
    - photo: Прикрепите ваше фото для личного кабинета (необязательное, файл)
    ''',
    request=DesignerQuestionnaireSerializer,
    responses={
        200: DesignerQuestionnaireSerializer(many=True),
        201: DesignerQuestionnaireSerializer,
        400: {'description': 'Ошибка валидации'}
    }
)
class DesignerQuestionnaireListView(views.APIView):
    """
    Анкеты дизайнеров - список
    GET /api/v1/accounts/questionnaires/ - список всех анкет
    POST /api/v1/accounts/questionnaires/ - создать анкету
    """
    permission_classes = [permissions.AllowAny]
    
    @extend_schema(
        summary='Получить список анкет дизайнеров',
        description='GET: Получить список всех анкет дизайнеров с фильтрацией',
        parameters=[
            OpenApiParameter(
                name='group',
                type=str,
                location=OpenApiParameter.QUERY,
                description='Выберете основную категорию (residential_designer, commercial_designer, decorator, home_stager, architect, landscape_designer, light_designer)',
                required=False,
            ),
            OpenApiParameter(
                name='city',
                type=str,
                location=OpenApiParameter.QUERY,
                description='Выберете город (поиск в city или work_cities). Специальные значения: "По всей России", "ЮФО", "Любые города онлайн"',
                required=False,
            ),
            OpenApiParameter(
                name='segment',
                type=str,
                location=OpenApiParameter.QUERY,
                description='Выберите сегмент (economy, comfort, business, premium, horeca). Можно указать несколько через запятую',
                required=False,
            ),
            OpenApiParameter(
                name='property_purpose',
                type=str,
                location=OpenApiParameter.QUERY,
                description='Назначение недвижимости (permanent_residence, for_rent, commercial, horeca)',
                required=False,
            ),
            OpenApiParameter(
                name='object_area',
                type=str,
                location=OpenApiParameter.QUERY,
                description='Площадь объекта (up_to_10m2, up_to_40m2, up_to_80m2, houses, not_important). Можно указать несколько через запятую',
                required=False,
            ),
            OpenApiParameter(
                name='cost_per_sqm',
                type=str,
                location=OpenApiParameter.QUERY,
                description='Стоимость за м2 (up_to_1500, up_to_2500, up_to_4000, over_4000, not_important)',
                required=False,
            ),
            OpenApiParameter(
                name='experience',
                type=str,
                location=OpenApiParameter.QUERY,
                description='Опыт работы (beginner, up_to_2_years, 2_5_years, 5_10_years, over_10_years)',
                required=False,
            ),
            OpenApiParameter(
                name='search',
                type=str,
                location=OpenApiParameter.QUERY,
                description='Поиск по full_name',
                required=False,
            ),
            OpenApiParameter(
                name='ordering',
                type=str,
                location=OpenApiParameter.QUERY,
                description='Сортировка (created_at, -created_at, full_name, -full_name, и т.д.)',
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
            200: DesignerQuestionnaireSerializer(many=True),
        }
    )
    def get(self, request):
        # Staff userlar uchun barcha questionnaire'lar, oddiy userlar uchun faqat is_moderation=True
        if request.user.is_authenticated and request.user.is_staff:
            questionnaires = DesignerQuestionnaire.objects.filter(is_deleted=False)
        else:
            questionnaires = DesignerQuestionnaire.objects.filter(is_moderation=True, is_deleted=False)
        
        # Filtering
        # Выберете основную котегорию (group)
        group = request.query_params.get('group')
        if group:
            questionnaires = questionnaires.filter(group=group)
        
        # Выберете город (city) - faqat a'zolar tomonidan e'lon qilingan shaharlar + maxsus variantlar
        city = request.query_params.get('city')
        if city:
            # Maxsus variantlar: "По всей России", "ЮФО", "Любые города онлайн"
            if city == "По всей России":
                # Barcha shaharlar - filter qo'llamaymiz
                pass
            elif city == "ЮФО":
                # Janubiy Federal Okrug shaharlari
                yfo_cities = ['Ростов-на-Дону', 'Краснодар', 'Сочи', 'Ставрополь', 'Волгоград', 'Астрахань']
                from django.db.models import Q
                city_q = Q()
                for yfo_city in yfo_cities:
                    city_q |= Q(city__icontains=yfo_city) | Q(work_cities__icontains=yfo_city)
                if city_q:
                    questionnaires = questionnaires.filter(city_q)
            elif city == "Любые города онлайн":
                # Online ishlaydiganlar - cooperation_terms ichida "онлайн" yoki "online" qidirish
                questionnaires = questionnaires.filter(
                    django_models.Q(cooperation_terms__icontains='онлайн') | 
                    django_models.Q(cooperation_terms__icontains='online')
                )
            else:
                # Oddiy shahar qidirish
                questionnaires = questionnaires.filter(
                    django_models.Q(city__icontains=city) | 
                    django_models.Q(work_cities__icontains=city)
                )
        
        # Выберете сегмент (segments - JSONField, contains check, ko'p tanlash mumkin)
        segment = request.query_params.get('segment')
        if segment:
            # Agar bir nechta segment kelsa, ularni ajratib olamiz
            segments_list = [s.strip() for s in segment.split(',')]
            # Har bir segment uchun filter qo'llaymiz
            from django.db.models import Q
            segment_q = Q()
            for seg in segments_list:
                segment_q |= Q(segments__contains=[seg])
            if segment_q:
                questionnaires = questionnaires.filter(segment_q)
        
        # Назначение недвижимости (property_purpose - services ichida)
        property_purpose = request.query_params.get('property_purpose')
        if property_purpose:
            # Mapping: permanent_residence -> residential_designer, for_rent -> residential_designer, commercial -> commercial_designer, horeca -> designer_horika
            purpose_mapping = {
                'permanent_residence': 'residential_designer',
                'for_rent': 'residential_designer',
                'commercial': 'commercial_designer',
                'horeca': 'designer_horika',
            }
            service_value = purpose_mapping.get(property_purpose, property_purpose)
            questionnaires = questionnaires.filter(services__contains=[service_value])
        
        # Площадь объекта (object_area - service_packages_description ichida search, ko'p tanlash mumkin)
        object_area = request.query_params.get('object_area')
        if object_area:
            # Agar bir nechta area kelsa, ularni ajratib olamiz
            areas_list = [a.strip() for a in object_area.split(',')]
            # Mapping: up_to_10m2 -> "10 м2", up_to_40m2 -> "40 м2", up_to_80m2 -> "80 м2", houses -> "дом", not_important -> skip
            area_mapping = {
                'up_to_10m2': '10 м2',
                'up_to_40m2': '40 м2',
                'up_to_80m2': '80 м2',
                'houses': 'дом',
            }
            from django.db.models import Q
            area_q = Q()
            for area in areas_list:
                if area != 'not_important':
                    search_term = area_mapping.get(area, area)
                    area_q |= Q(service_packages_description__icontains=search_term)
            if area_q:
                questionnaires = questionnaires.filter(area_q)
        
        # Стоимость за м2 (cost_per_sqm - service_packages_description ichida search)
        cost_per_sqm = request.query_params.get('cost_per_sqm')
        if cost_per_sqm and cost_per_sqm != 'not_important':
            # Mapping: up_to_1500 -> "1500", up_to_2500 -> "2500", up_to_4000 -> "4000", over_4000 -> "4000" (lekin > 4000)
            cost_mapping = {
                'up_to_1500': '1500',
                'up_to_2500': '2500',
                'up_to_4000': '4000',
                'over_4000': '4000',  # Bu uchun alohida logika kerak
            }
            search_term = cost_mapping.get(cost_per_sqm, cost_per_sqm)
            if cost_per_sqm == 'over_4000':
                # 4000 dan katta qiymatlar uchun
                questionnaires = questionnaires.filter(service_packages_description__icontains=search_term)
            else:
                questionnaires = questionnaires.filter(service_packages_description__icontains=search_term)
        
        # Опыт работы (experience - welcome_message ichida search yoki additional_info)
        experience = request.query_params.get('experience')
        if experience:
            # Mapping: beginner -> "новичок", up_to_2_years -> "2 лет", 2_5_years -> "2-5", 5_10_years -> "5-10", over_10_years -> "10 лет"
            experience_mapping = {
                'beginner': 'новичок',
                'up_to_2_years': '2 лет',
                '2_5_years': '2-5',
                '5_10_years': '5-10',
                'over_10_years': '10 лет',
            }
            search_term = experience_mapping.get(experience, experience)
            questionnaires = questionnaires.filter(
                django_models.Q(welcome_message__icontains=search_term) | 
                django_models.Q(additional_info__icontains=search_term)
            )
        
        # Search by full_name
        search = request.query_params.get('search')
        if search:
            questionnaires = questionnaires.filter(full_name__icontains=search)
        
        # Ordering
        ordering = request.query_params.get('ordering', '-created_at')
        questionnaires = questionnaires.order_by(ordering)
        
        # Pagination
        paginator = LimitOffsetPagination()
        paginator.default_limit = 100
        paginator.limit_query_param = 'limit'
        paginator.offset_query_param = 'offset'
        
        paginated_questionnaires = paginator.paginate_queryset(questionnaires, request)
        serializer = DesignerQuestionnaireSerializer(paginated_questionnaires, many=True)
        
        return paginator.get_paginated_response(serializer.data)
    
    def post(self, request):
        serializer = DesignerQuestionnaireSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@extend_schema(
    tags=['Designer Questionnaires'],
    summary='Получить варианты для фильтров анкет дизайнеров',
    description='''
    GET: Получить все доступные варианты для фильтров анкет дизайнеров
    
    Query параметры:
    - group: (необязательно) Фильтр по категории для получения городов только этой категории
    
    Возвращает:
    - categories: Основные категории - Выберете основную котегорию
      * Дизайнер жилых помещений (residential_designer)
      * Дизайнер коммерческой недвижимости (commercial_designer)
      * Декоратор (decorator)
      * Хоустейджер (home_stager)
      * Архитектор (architect)
      * Ландшафтный дизайнер (landscape_designer)
      * Светодизайнер (light_designer)
    - cities: Список уникальных городов из анкет выбранной категории + специальные варианты - Выберете город
      * По всей России
      * ЮФО
      * Любые города онлайн
      * + города, заявленные членами клуба в выбранной категории
    - segments: Сегменты работы (можно выбрать несколько) - Выберете сегмент
      * Эконом (economy)
      * Комфорт (comfort)
      * Бизнесс (business)
      * Примиум (premium)
      * Хорика (horeca)
    - property_purposes: Назначение недвижимости - Назначение недвижимости
      * Для постоянного проживания (permanent_residence)
      * Для сдачи (for_rent)
      * Коммерческая недвижимость (commercial)
      * Хорика (horeca)
    - object_areas: Площадь объекта (можно выбрать несколько) - Площадь объекта
      * до 10 м² (up_to_10m2)
      * до 40 м² (up_to_40m2)
      * до 80 м² (up_to_80m2)
      * дома (houses)
      * не важно (not_important)
    - cost_per_sqm_options: Стоимость за м2 - Стоимость за м2
      * До 1500 р (up_to_1500)
      * до 2500 р (up_to_2500)
      * до 4000 р (up_to_4000)
      * свыше 4000 р (over_4000)
      * не важно (not_important)
    - experience_options: Опыт работы - Опыт работы
      * Новичок (beginner)
      * до 2 лет (up_to_2_years)
      * 2-5 лет (2_5_years)
      * 5-10 лет (5_10_years)
      * свыше 10 лет (over_10_years)
    ''',
    parameters=[
        OpenApiParameter(
            name='group',
            type=str,
            location=OpenApiParameter.QUERY,
            description='Фильтр по категории для получения городов только этой категории (необязательно)',
            required=False,
        ),
    ],
    responses={
        200: {'description': 'Варианты для фильтров'}
    }
)
class DesignerQuestionnaireFilterChoicesView(views.APIView):
    """
    Получить варианты для фильтров анкет дизайнеров
    GET /api/v1/accounts/questionnaires/filter-choices/
    """
    permission_classes = [permissions.AllowAny]
    
    def get(self, request):
        from .models import DesignerQuestionnaire, QUESTIONNAIRE_GROUP_CHOICES
        
        # Основные категории (group) - Выберете основную котегорию
        # Yangi kategoriyalar: Дизайнер жилых помещений, Дизайнер коммерческой недвижимости, Декоратор, Хоустейджер, Архитектор, Ландшафтный дизайнер, Светодизайнер
        categories = [
            {'value': 'residential_designer', 'label': 'Дизайнер жилых помещений'},
            {'value': 'commercial_designer', 'label': 'Дизайнер коммерческой недвижимости'},
            {'value': 'decorator', 'label': 'Декоратор'},
            {'value': 'home_stager', 'label': 'Хоустейджер'},
            {'value': 'architect', 'label': 'Архитектор'},
            {'value': 'landscape_designer', 'label': 'Ландшафтный дизайнер'},
            {'value': 'light_designer', 'label': 'Светодизайнер'},
        ]
        
        # Уникальные города - Выберете город
        # Faqat a'zolar tomonidan e'lon qilingan shaharlar + maxsus variantlar
        # Staff userlar uchun barcha, oddiy userlar uchun faqat is_moderation=True
        is_staff = request.user.is_authenticated and request.user.is_staff
        if is_staff:
            cities_query = DesignerQuestionnaire.objects.filter(is_deleted=False)
        else:
            cities_query = DesignerQuestionnaire.objects.filter(is_moderation=True, is_deleted=False)
        
        # Group filter bo'lsa, faqat o'sha kategoriyadagi shaharlarni ko'rsatish
        group = request.query_params.get('group')
        if group:
            # Group bo'yicha filter qo'llaymiz
            if group == 'residential_designer':
                cities_query = cities_query.filter(services__contains=['residential_designer'])
            elif group == 'commercial_designer':
                cities_query = cities_query.filter(services__contains=['commercial_designer'])
            elif group == 'decorator':
                cities_query = cities_query.filter(services__contains=['decorator'])
            elif group == 'home_stager':
                cities_query = cities_query.filter(services__contains=['home_stager'])
            elif group == 'architect':
                cities_query = cities_query.filter(services__contains=['architecture'])
            elif group == 'landscape_designer':
                cities_query = cities_query.filter(services__contains=['landscape_design'])
            elif group == 'light_designer':
                cities_query = cities_query.filter(services__contains=['light_designer'])
        
        cities = cities_query.exclude(
            city__isnull=True
        ).exclude(
            city=''
        ).values_list('city', flat=True).distinct().order_by('city')
        cities_list = [{'value': city, 'label': city} for city in cities]
        
        # Maxsus variantlar qo'shamiz
        cities_list.insert(0, {'value': 'По всей России', 'label': 'По всей России'})
        cities_list.insert(1, {'value': 'ЮФО', 'label': 'ЮФО'})
        cities_list.insert(2, {'value': 'Любые города онлайн', 'label': 'Любые города онлайн'})
        
        # Сегменты - Выберете сегмент (ko'p tanlash mumkin)
        # Эконом, Комфорт, Бизнесс, Примиум, Хорика
        segments = [
            {'value': 'economy', 'label': 'Эконом'},
            {'value': 'comfort', 'label': 'Комфорт'},
            {'value': 'business', 'label': 'Бизнесс'},
            {'value': 'premium', 'label': 'Примиум'},
            {'value': 'horeca', 'label': 'Хорика'},
        ]
        
        # Назначение недвижимости - Назначение недвижимости
        property_purposes = [
            {'value': 'permanent_residence', 'label': 'Для постоянного проживания'},
            {'value': 'for_rent', 'label': 'Для сдачи'},
            {'value': 'commercial', 'label': 'Коммерческая недвижимость'},
            {'value': 'horeca', 'label': 'Хорика'},
        ]
        
        # Площадь объекта - Площадь объекта (ko'p tanlash mumkin)
        object_areas = [
            {'value': 'up_to_10m2', 'label': 'до 10 м²'},
            {'value': 'up_to_40m2', 'label': 'до 40 м²'},
            {'value': 'up_to_80m2', 'label': 'до 80 м²'},
            {'value': 'houses', 'label': 'дома'},
            {'value': 'not_important', 'label': 'не важно'},
        ]
        
        # Стоимость за м2 - Стоимость за м2
        cost_per_sqm_options = [
            {'value': 'up_to_1500', 'label': 'До 1500 р'},
            {'value': 'up_to_2500', 'label': 'до 2500 р'},
            {'value': 'up_to_4000', 'label': 'до 4000 р'},
            {'value': 'over_4000', 'label': 'свыше 4000 р'},
            {'value': 'not_important', 'label': 'не важно'},
        ]
        
        # Опыт работы - Опыт работы
        experience_options = [
            {'value': 'beginner', 'label': 'Новичок'},
            {'value': 'up_to_2_years', 'label': 'до 2 лет'},
            {'value': '2_5_years', 'label': '2-5 лет'},
            {'value': '5_10_years', 'label': '5-10 лет'},
            {'value': 'over_10_years', 'label': 'свыше 10 лет'},
        ]
        
        return Response({
            'categories': categories,
            'cities': cities_list,
            'segments': segments,
            'property_purposes': property_purposes,
            'object_areas': object_areas,
            'cost_per_sqm_options': cost_per_sqm_options,
            'experience_options': experience_options,
        }, status=status.HTTP_200_OK)


@extend_schema(
    tags=['Designer Questionnaires'],
    summary='Детали анкеты дизайнера',
    description='''
    GET: Получить детали анкеты дизайнера по ID
    
    PUT: Обновить анкету дизайнера (частичное обновление поддерживается)
    
    DELETE: Удалить анкету дизайнера
    
    Поля для обновления (PUT):
    - group: Группа. Варианты:
      * designer - Дизайнер
      * architect - Архитектор
      * decorator - Декоратор
      * landscape_designer - Ландшафтный дизайнер
      * light_designer - Светодизайнер
      * interior_designer - Дизайнер интерьера
      * repair_team - Ремонтная бригада
      * contractor - Подрядчик
      * supplier - Поставщик
      * exhibition_hall - Выставочный зал
      * factory - Фабрика
    - full_name: ФИО
    - full_name_en: ФИ на английском
    - phone: Номер телефона
    - birth_date: Дата рождения (формат: YYYY-MM-DD)
    - email: E-mail
    - city: Город проживания
    - services: Услуги (массив). Варианты:
      * author_supervision - Авторский надзор
      * architecture - Архитектура
      * decorator - Декоратор
      * designer_horika - Дизайнер Хорика
      * residential_designer - Дизайнер жилой недвижимости
      * commercial_designer - Дизайнер коммерческой недвижимости
      * completing - Комплектация
      * landscape_design - Ландшафтный дизайн
      * design - Проектирование
      * light_designer - Светодизайнер
      * home_stager - Хоумстейджер
    - work_type: Тип работы. Варианты:
      * own_name - Под собственным именем
      * studio - В студии
    - welcome_message: Приветственное сообщение о вас и вашем опыте
    - work_cities: Города работы (массив)
    - cooperation_terms: Условия сотрудничества при работе с объектами в других городах или регионах
    - segments: Сегменты работы (массив). Варианты:
      * horeca - HoReCa
      * business - Бизнес
      * comfort - Комфорт
      * premium - Премиум
      * medium - Средний
      * economy - Эконом
    - unique_trade_proposal: Ваше уникальное торговое предложение (УТП)
    - vk: VK
    - telegram_channel: Telegram канал
    - pinterest: Pinterest
    - instagram: Instagram
    - website: Ваш сайт (URL)
    - other_contacts: Другое - дополнительные контакты (массив)
    - service_packages_description: Подробное описание пакетов услуг с указанием стоимости
    - vat_payment: Возможна ли оплата с учётом НДС?. Варианты:
      * yes - Да
      * no - Нет
    - supplier_contractor_recommendation_terms: Условия сотрудничества по рекомендациям от поставщиков или подрядчиков
    - additional_info: Дополнительная информация
    - data_processing_consent: Согласие на обработку данных (boolean)
    - photo: Прикрепите ваше фото для личного кабинета (файл)
    ''',
    request=DesignerQuestionnaireSerializer,
    responses={
        200: DesignerQuestionnaireSerializer,
        400: {'description': 'Ошибка валидации'},
        404: {'description': 'Анкета не найдена'},
        204: {'description': 'Анкета успешно удалена'}
    }
)
class DesignerQuestionnaireDetailView(views.APIView):
    """
    Анкета дизайнера - детали, обновление, удаление
    GET /api/v1/accounts/questionnaires/{id}/ - получить анкету
    PUT /api/v1/accounts/questionnaires/{id}/ - обновить анкету
    DELETE /api/v1/accounts/questionnaires/{id}/ - удалить анкету
    """
    permission_classes = [permissions.AllowAny]
    
    def get_object(self, pk, request=None):
        try:
            # Staff userlar uchun barcha, oddiy userlar uchun faqat is_moderation=True
            is_staff = request and request.user.is_authenticated and request.user.is_staff
            if is_staff:
                return DesignerQuestionnaire.objects.get(pk=pk)
            else:
                return DesignerQuestionnaire.objects.filter(is_moderation=True).get(pk=pk)
        except DesignerQuestionnaire.DoesNotExist:
            raise NotFound("Анкета не найдена")
    
    def get(self, request, pk):
        questionnaire = self.get_object(pk, request)
        serializer = DesignerQuestionnaireSerializer(questionnaire)
        return Response(serializer.data, status=status.HTTP_200_OK)
    
    def put(self, request, pk):
        if not request.user.is_authenticated:
            raise PermissionDenied("Требуется авторизация для обновления анкеты")
        questionnaire = self.get_object(pk, request)
        serializer = DesignerQuestionnaireSerializer(questionnaire, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    def delete(self, request, pk):
        if not request.user.is_authenticated:
            raise PermissionDenied("Требуется авторизация для удаления анкеты")
        questionnaire = self.get_object(pk, request)
        questionnaire.is_deleted = True
        questionnaire.save()
        return Response({'message': 'Анкета успешно удалена'}, status=status.HTTP_200_OK)


@extend_schema(
    tags=['Repair Questionnaires'],
    summary='Список анкет ремонтных бригад / подрядчиков',
    description='''
    GET: Получить список всех анкет ремонтных бригад / подрядчиков
    
    POST: Создать новую анкету ремонтной бригады / подрядчика
    
    Поля анкеты:
    - group: Группа (обязательное). Варианты:
      * designer - Дизайнер
      * architect - Архитектор
      * decorator - Декоратор
      * landscape_designer - Ландшафтный дизайнер
      * light_designer - Светодизайнер
      * interior_designer - Дизайнер интерьера
      * repair_team - Ремонтная бригада
      * contractor - Подрядчик
      * supplier - Поставщик
      * exhibition_hall - Выставочный зал
      * factory - Фабрика
    - full_name: ФИО (обязательное)
    - brand_name: Название бренда (дополнительно в скобках укажите полное юридическое наименование компании) (обязательное)
    - email: E-mail (обязательное)
    - responsible_person: Имя, должность и контактный номер ответственного лица (обязательное)
    - representative_cities: Города представительств (массив, необязательное)
    - business_form: Форма бизнеса (необязательное). Варианты:
      * own_business - Собственный бизнес
      * franchise - Франшиза
    - work_list: Перечень работ которые можете предоставить (необязательное)
    - welcome_message: Приветственное сообщение о вашей компании (необязательное)
    - cooperation_terms: Условия сотрудничества при работе с клиентами из других городов или регионов (необязательное)
    - project_timelines: Сроки выполнения проектов в 1К, 2К и 3К квартирах средней площади (необязательное)
    - segments: Сегменты работы (массив, необязательное). Варианты:
      * horeca - HoReCa
      * business - Бизнес
      * comfort - Комфорт
      * premium - Премиум
      * medium - Средний
      * economy - Эконом
    - vk: VK (необязательное)
    - telegram_channel: Telegram канал (необязательное)
    - pinterest: Pinterest (необязательное)
    - instagram: Instagram (необязательное)
    - website: Ваш сайт (необязательное, URL)
    - other_contacts: Другое - дополнительные контакты (массив, необязательное)
    - work_format: Формат работы (необязательное)
    - vat_payment: Возможна ли оплата с учётом НДС? (необязательное). Варианты:
      * yes - Да
      * no - Нет
    - guarantees: Гарантии и их сроки (необязательное)
    - designer_supplier_terms: Условия работы с дизайнерами и/или поставщиками (необязательное)
    - magazine_cards: Выдаёте ли вы карточки журналов при рекомендации при заключении договора? (необязательное). Варианты:
      * hi_home - Hi Home
      * in_home - IN HOME
      * no - Нет
      * other - Другое
    - additional_info: Дополнительная информация (необязательное)
    - data_processing_consent: Согласие на обработку данных (обязательное, boolean)
    - company_logo: Логотип компании (shaxsiy kabinet uchun) (необязательное, файл)
    - legal_entity_card: Yuridik shaxs kartasi (shartnoma uchun) (необязательное, файл)
    ''',
    request=RepairQuestionnaireSerializer,
    responses={
        200: RepairQuestionnaireSerializer(many=True),
        201: RepairQuestionnaireSerializer,
        400: {'description': 'Ошибка валидации'}
    }
)
class RepairQuestionnaireListView(views.APIView):
    """
    Анкеты ремонтных бригад / подрядчиков - список
    GET /api/v1/accounts/repair-questionnaires/ - список всех анкет
    POST /api/v1/accounts/repair-questionnaires/ - создать анкету
    """
    permission_classes = [permissions.AllowAny]
    
    @extend_schema(
        summary='Получить список анкет ремонтных бригад / подрядчиков',
        description='GET: Получить список всех анкет ремонтных бригад / подрядчиков с фильтрацией',
        parameters=[
            OpenApiParameter(
                name='group',
                type=str,
                location=OpenApiParameter.QUERY,
                description='Выберете основную категорию (turnkey, rough_works, finishing_works, plumbing_tiles, floor, walls, rooms_turnkey, electrical, all). Можно указать несколько через запятую',
                required=False,
            ),
            OpenApiParameter(
                name='city',
                type=str,
                location=OpenApiParameter.QUERY,
                description='Выберете город (поиск в representative_cities). Специальные значения: "По всей России", "ЮФО", "Любые города онлайн"',
                required=False,
            ),
            OpenApiParameter(
                name='segment',
                type=str,
                location=OpenApiParameter.QUERY,
                description='Выберите сегмент (economy, comfort, business, premium, horeca, exclusive). Можно указать несколько через запятую',
                required=False,
            ),
            OpenApiParameter(
                name='vat_payment',
                type=str,
                location=OpenApiParameter.QUERY,
                description='Наличие НДС (hi_home, in_home, no, not_important). Можно указать несколько через запятую',
                required=False,
            ),
            OpenApiParameter(
                name='magazine_cards',
                type=str,
                location=OpenApiParameter.QUERY,
                description='Карточки журналов (hi_home, in_home, no, not_important). Можно указать несколько через запятую',
                required=False,
            ),
            OpenApiParameter(
                name='execution_speed',
                type=str,
                location=OpenApiParameter.QUERY,
                description='Скорость исполнения (advance_booking, quick_start, not_important)',
                required=False,
                enum=['advance_booking', 'quick_start', 'not_important'],
            ),
            OpenApiParameter(
                name='cooperation_terms',
                type=str,
                location=OpenApiParameter.QUERY,
                description='Условия сотрудничества (up_to_5_percent, up_to_10_percent, not_important)',
                required=False,
                enum=['up_to_5_percent', 'up_to_10_percent', 'not_important'],
            ),
            OpenApiParameter(
                name='business_form',
                type=str,
                location=OpenApiParameter.QUERY,
                description='Форма бизнеса (own_business, franchise)',
                required=False,
                enum=['own_business', 'franchise'],
            ),
            OpenApiParameter(
                name='search',
                type=str,
                location=OpenApiParameter.QUERY,
                description='Поиск по full_name или brand_name',
                required=False,
            ),
            OpenApiParameter(
                name='ordering',
                type=str,
                location=OpenApiParameter.QUERY,
                description='Сортировка (created_at, -created_at, full_name, -full_name, и т.д.)',
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
            200: RepairQuestionnaireSerializer(many=True),
        }
    )
    def get(self, request):
        # Staff userlar uchun barcha questionnaire'lar, oddiy userlar uchun faqat is_moderation=True
        if request.user.is_authenticated and request.user.is_staff:
            questionnaires = RepairQuestionnaire.objects.filter(is_deleted=False)
        else:
            questionnaires = RepairQuestionnaire.objects.filter(is_moderation=True, is_deleted=False)
        
        # Filtering
        # Выберете основную котегорию (group) - ko'p tanlash mumkin
        group = request.query_params.get('group')
        if group:
            if group == 'all':
                # "ВСЕ" - filter qo'llamaymiz
                pass
            else:
                # Ko'p tanlash mumkin - vergul bilan ajratilgan
                groups_list = [g.strip() for g in group.split(',')]
                # Mapping: turnkey -> work_list ichida "под ключ", rough_works -> "черновые", finishing_works -> "чистовые", plumbing_tiles -> "сантехника" yoki "плитка", floor -> "пол", walls -> "стены", rooms_turnkey -> "комнаты" va "ключ", electrical -> "электрика"
                from django.db.models import Q
                group_q = Q()
                for grp in groups_list:
                    if grp == 'turnkey':
                        group_q |= Q(work_list__icontains='под ключ')
                    elif grp == 'rough_works':
                        group_q |= Q(work_list__icontains='черновые')
                    elif grp == 'finishing_works':
                        group_q |= Q(work_list__icontains='чистовые')
                    elif grp == 'plumbing_tiles':
                        group_q |= Q(work_list__icontains='сантехника') | Q(work_list__icontains='плитка')
                    elif grp == 'floor':
                        group_q |= Q(work_list__icontains='пол')
                    elif grp == 'walls':
                        group_q |= Q(work_list__icontains='стены')
                    elif grp == 'rooms_turnkey':
                        group_q |= Q(work_list__icontains='комнаты') & Q(work_list__icontains='ключ')
                    elif grp == 'electrical':
                        group_q |= Q(work_list__icontains='электрика')
                if group_q:
                    questionnaires = questionnaires.filter(group_q)
        
        # Выберете город (representative_cities - JSONField, contains check) + maxsus variantlar
        city = request.query_params.get('city')
        if city:
            # Maxsus variantlar: "По всей России", "ЮФО", "Любые города онлайн"
            if city == "По всей России":
                # Barcha shaharlar - filter qo'llamaymiz
                pass
            elif city == "ЮФО":
                # Janubiy Federal Okrug shaharlari
                yfo_cities = ['Ростов-на-Дону', 'Краснодар', 'Сочи', 'Ставрополь', 'Волгоград', 'Астрахань']
                from django.db.models import Q
                city_q = Q()
                for yfo_city in yfo_cities:
                    city_q |= Q(representative_cities__icontains=yfo_city)
                if city_q:
                    questionnaires = questionnaires.filter(city_q)
            elif city == "Любые города онлайн":
                # Online ishlaydiganlar - cooperation_terms ichida "онлайн" yoki "online" qidirish
                questionnaires = questionnaires.filter(
                    django_models.Q(cooperation_terms__icontains='онлайн') | 
                    django_models.Q(cooperation_terms__icontains='online')
                )
            else:
                # Oddiy shahar qidirish
                questionnaires = questionnaires.filter(representative_cities__icontains=city)
        
        # Выберете сегмент (segments - JSONField, contains check, ko'p tanlash mumkin)
        segment = request.query_params.get('segment')
        if segment:
            # Ko'p tanlash mumkin - vergul bilan ajratilgan
            segments_list = [s.strip() for s in segment.split(',')]
            from django.db.models import Q
            segment_q = Q()
            for seg in segments_list:
                segment_q |= Q(segments__contains=[seg])
            if segment_q:
                questionnaires = questionnaires.filter(segment_q)
        
        # Наличие НДС (vat_payment) - ko'p tanlash mumkin
        vat_payment = request.query_params.get('vat_payment')
        if vat_payment:
            # Ko'p tanlash mumkin - vergul bilan ajratilgan
            vat_list = [v.strip() for v in vat_payment.split(',')]
            from django.db.models import Q
            vat_q = Q()
            for vat in vat_list:
                if vat == 'not_important':
                    # "не важно" - filter qo'llamaymiz
                    pass
                elif vat == 'hi_home':
                    # "hi_home" - vat_payment='yes' va magazine_cards='hi_home' yoki faqat vat_payment='yes'
                    vat_q |= Q(vat_payment='yes')
                elif vat == 'in_home':
                    # "in_home" - vat_payment='yes' va magazine_cards='in_home' yoki faqat vat_payment='yes'
                    vat_q |= Q(vat_payment='yes')
                elif vat == 'no':
                    vat_q |= Q(vat_payment='no')
            if vat_q:
                questionnaires = questionnaires.filter(vat_q)
        
        # Карточки журналов (magazine_cards) - ko'p tanlash mumkin
        magazine_cards = request.query_params.get('magazine_cards')
        if magazine_cards:
            # Ko'p tanlash mumkin - vergul bilan ajratilgan
            cards_list = [c.strip() for c in magazine_cards.split(',')]
            from django.db.models import Q
            cards_q = Q()
            for card in cards_list:
                if card == 'not_important':
                    # "не важно" - filter qo'llamaymiz
                    pass
                else:
                    cards_q |= Q(magazine_cards=card)
            if cards_q:
                questionnaires = questionnaires.filter(cards_q)
        
        # Скорость исполнения (execution_speed - project_timelines ichida search)
        execution_speed = request.query_params.get('execution_speed')
        if execution_speed and execution_speed != 'not_important':
            # Mapping: advance_booking -> "предварительная запись", quick_start -> "быстрый старт"
            speed_mapping = {
                'advance_booking': 'предварительная запись',
                'quick_start': 'быстрый старт',
            }
            search_term = speed_mapping.get(execution_speed, execution_speed)
            questionnaires = questionnaires.filter(project_timelines__icontains=search_term)
        
        # Условия сотрудничества (cooperation_terms ichida search)
        cooperation_terms = request.query_params.get('cooperation_terms')
        if cooperation_terms and cooperation_terms != 'not_important':
            # Mapping: up_to_5_percent -> "5%", up_to_10_percent -> "10%"
            terms_mapping = {
                'up_to_5_percent': '5%',
                'up_to_10_percent': '10%',
            }
            search_term = terms_mapping.get(cooperation_terms, cooperation_terms)
            questionnaires = questionnaires.filter(cooperation_terms__icontains=search_term)
        
        # Назначение недвижимости (property_purpose - work_list ichida search)
        property_purpose = request.query_params.get('property_purpose')
        if property_purpose:
            questionnaires = questionnaires.filter(work_list__icontains=property_purpose)
        
        # Площадь объекта (object_area - project_timelines ichida search)
        object_area = request.query_params.get('object_area')
        if object_area:
            questionnaires = questionnaires.filter(project_timelines__icontains=object_area)
        
        # Стоимость за м2 (cost_per_sqm - work_format yoki guarantees ichida search)
        cost_per_sqm = request.query_params.get('cost_per_sqm')
        if cost_per_sqm:
            questionnaires = questionnaires.filter(
                django_models.Q(work_format__icontains=cost_per_sqm) | 
                django_models.Q(guarantees__icontains=cost_per_sqm)
            )
        
        # Опыт работы (experience - welcome_message yoki additional_info ichida search)
        experience = request.query_params.get('experience')
        if experience:
            questionnaires = questionnaires.filter(
                django_models.Q(welcome_message__icontains=experience) | 
                django_models.Q(additional_info__icontains=experience)
            )
        
        # Форма бизнеса (business_form)
        business_form = request.query_params.get('business_form')
        if business_form:
            questionnaires = questionnaires.filter(business_form=business_form)
        
        # Search by full_name or brand_name
        search = request.query_params.get('search')
        if search:
            questionnaires = questionnaires.filter(
                django_models.Q(full_name__icontains=search) | 
                django_models.Q(brand_name__icontains=search)
            )
        
        # Ordering
        ordering = request.query_params.get('ordering', '-created_at')
        questionnaires = questionnaires.order_by(ordering)
        
        # Pagination
        paginator = LimitOffsetPagination()
        paginator.default_limit = 100
        paginator.limit_query_param = 'limit'
        paginator.offset_query_param = 'offset'
        
        paginated_questionnaires = paginator.paginate_queryset(questionnaires, request)
        serializer = RepairQuestionnaireSerializer(paginated_questionnaires, many=True)
        
        return paginator.get_paginated_response(serializer.data)
    
    def post(self, request):
        serializer = RepairQuestionnaireSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@extend_schema(
    tags=['Repair Questionnaires'],
    summary='Детали анкеты ремонтной бригады / подрядчика',
    description='''
    GET: Получить детали анкеты ремонтной бригады / подрядчика по ID
    
    PUT: Обновить анкету ремонтной бригады / подрядчика (частичное обновление поддерживается)
    
    DELETE: Удалить анкету ремонтной бригады / подрядчика
    
    Поля для обновления (PUT):
    - group: Группа. Варианты:
      * designer - Дизайнер
      * architect - Архитектор
      * decorator - Декоратор
      * landscape_designer - Ландшафтный дизайнер
      * light_designer - Светодизайнер
      * interior_designer - Дизайнер интерьера
      * repair_team - Ремонтная бригада
      * contractor - Подрядчик
      * supplier - Поставщик
      * exhibition_hall - Выставочный зал
      * factory - Фабрика
    - full_name: ФИО
    - brand_name: Название бренда (дополнительно в скобках укажите полное юридическое наименование компании)
    - email: E-mail
    - responsible_person: Имя, должность и контактный номер ответственного лица
    - representative_cities: Города представительств (массив)
    - business_form: Форма бизнеса. Варианты:
      * own_business - Собственный бизнес
      * franchise - Франшиза
    - work_list: Перечень работ которые можете предоставить
    - welcome_message: Приветственное сообщение о вашей компании
    - cooperation_terms: Условия сотрудничества при работе с клиентами из других городов или регионов
    - project_timelines: Сроки выполнения проектов в 1К, 2К и 3К квартирах средней площади
    - segments: Сегменты работы (массив). Варианты:
      * horeca - HoReCa
      * business - Бизнес
      * comfort - Комфорт
      * premium - Премиум
      * medium - Средний
      * economy - Эконом
    - vk: VK
    - telegram_channel: Telegram канал
    - pinterest: Pinterest
    - instagram: Instagram
    - website: Ваш сайт (URL)
    - other_contacts: Другое - дополнительные контакты (массив)
    - work_format: Формат работы
    - vat_payment: Возможна ли оплата с учётом НДС?. Варианты:
      * yes - Да
      * no - Нет
    - guarantees: Гарантии и их сроки
    - designer_supplier_terms: Условия работы с дизайнерами и/или поставщиками
    - magazine_cards: Выдаёте ли вы карточки журналов при рекомендации при заключении договора?. Варианты:
      * hi_home - Hi Home
      * in_home - IN HOME
      * no - Нет
      * other - Другое
    - additional_info: Дополнительная информация
    - data_processing_consent: Согласие на обработку данных (boolean)
    - company_logo: Логотип компании (shaxsiy kabinet uchun) (файл)
    - legal_entity_card: Yuridik shaxs kartasi (shartnoma uchun) (файл)
    ''',
    request=RepairQuestionnaireSerializer,
    responses={
        200: RepairQuestionnaireSerializer,
        400: {'description': 'Ошибка валидации'},
        404: {'description': 'Анкета не найдена'},
        204: {'description': 'Анкета успешно удалена'}
    }
)
class RepairQuestionnaireDetailView(views.APIView):
    """
    Анкета ремонтной бригады / подрядчика - детали, обновление, удаление
    GET /api/v1/accounts/repair-questionnaires/{id}/ - получить анкету
    PUT /api/v1/accounts/repair-questionnaires/{id}/ - обновить анкету
    DELETE /api/v1/accounts/repair-questionnaires/{id}/ - удалить анкету
    """
    permission_classes = [permissions.AllowAny]
    
    def get_object(self, pk, request=None):
        try:
            # Staff userlar uchun barcha, oddiy userlar uchun faqat is_moderation=True
            is_staff = request and request.user.is_authenticated and request.user.is_staff
            if is_staff:
                return RepairQuestionnaire.objects.filter(is_deleted=False).get(pk=pk)
            else:
                return RepairQuestionnaire.objects.filter(is_moderation=True, is_deleted=False).get(pk=pk)
        except RepairQuestionnaire.DoesNotExist:
            raise NotFound("Анкета не найдена")
    
    def get(self, request, pk):
        questionnaire = self.get_object(pk)
        serializer = RepairQuestionnaireSerializer(questionnaire)
        return Response(serializer.data, status=status.HTTP_200_OK)
    
    def put(self, request, pk):
        if not request.user.is_authenticated:
            raise PermissionDenied("Требуется авторизация для обновления анкеты")
        questionnaire = self.get_object(pk)
        serializer = RepairQuestionnaireSerializer(questionnaire, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    def delete(self, request, pk):
        if not request.user.is_authenticated:
            raise PermissionDenied("Требуется авторизация для удаления анкеты")
        questionnaire = self.get_object(pk, request)
        questionnaire.is_deleted = True
        questionnaire.save()
        return Response({'message': 'Анкета успешно удалена'}, status=status.HTTP_200_OK)


@extend_schema(
    tags=['Designer Questionnaires'],
    summary='Обновить статус анкеты дизайнера (admin)',
    description='''
    POST: Обновить статус анкеты дизайнера (только для администраторов)
    
    Доступные статусы:
    - pending - Ожидает модерации
    - published - Опубликовано
    - rejected - Отклонено
    - archived - В архиве
    
    Тело запроса:
    {
        "status": "published"
    }
    ''',
    request=QuestionnaireStatusUpdateSerializer,
    responses={
        200: DesignerQuestionnaireSerializer,
        400: {'description': 'Ошибка валидации'},
        403: {'description': 'Доступ запрещен. Только администраторы могут изменять статус'},
        404: {'description': 'Анкета не найдена'}
    }
)
class DesignerQuestionnaireStatusUpdateView(views.APIView):
    """
    Обновить статус анкеты дизайнера (admin)
    POST /api/v1/accounts/questionnaires/{id}/update-status/
    """
    permission_classes = [permissions.IsAuthenticated]
    
    def get_object(self, pk):
        try:
            return DesignerQuestionnaire.objects.get(pk=pk)
        except DesignerQuestionnaire.DoesNotExist:
            raise NotFound("Анкета не найдена")
    
    def post(self, request, pk):
        # Проверка прав администратора
        if not (request.user.is_staff or request.user.role == 'admin'):
            raise PermissionDenied("Только администратор может изменять статус анкеты")
        
        questionnaire = self.get_object(pk)
        serializer = QuestionnaireStatusUpdateSerializer(data=request.data)
        
        if serializer.is_valid():
            questionnaire.status = serializer.validated_data['status']
            questionnaire.save()
            
            result_serializer = DesignerQuestionnaireSerializer(questionnaire)
            return Response(result_serializer.data, status=status.HTTP_200_OK)
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@extend_schema(
    tags=['Repair Questionnaires'],
    summary='Получить варианты для фильтров анкет ремонтных бригад / подрядчиков',
    description='''
    GET: Получить все доступные варианты для фильтров анкет ремонтных бригад / подрядчиков
    
    Возвращает:
    - categories: Основные категории (group choices) - Выберете основную котегорию
    - cities: Список уникальных городов из representative_cities - Выберете город
    - segments: Сегменты работы - Выберете сегмент
    - business_forms: Формы бизнеса - Форма бизнеса
    ''',
    responses={
        200: {'description': 'Варианты для фильтров'}
    }
)
@extend_schema(
    tags=['Repair Questionnaires'],
    summary='Получить варианты для фильтров анкет ремонтных бригад / подрядчиков',
    description='''
    GET: Получить все доступные варианты для фильтров анкет ремонтных бригад / подрядчиков
    
    Query параметры:
    - group: (необязательно) Фильтр по категории для получения городов только этой категории
    
    Возвращает:
    - categories: Основные категории (можно выбрать несколько) - Выберете основную котегорию
      * ПОД КЛЮЧ (turnkey)
      * черновые работы (rough_works)
      * чистовые работы (finishing_works)
      * Сантехника и плитка (plumbing_tiles)
      * Пол (floor)
      * Стены (walls)
      * Комнаты под ключ (rooms_turnkey)
      * Электрика (electrical)
      * ВСЕ (all)
    - cities: Список уникальных городов из анкет выбранной категории + специальные варианты - Выберете город
      * По всей России
      * ЮФО
      * Любые города онлайн
      * + города, заявленные членами клуба в выбранной категории
    - segments: Сегменты работы (можно выбрать несколько) - Выберете сегмент
      * Эконом (economy)
      * Комфорт (comfort)
      * Бизнесс (business)
      * Примиум (premium)
      * Хорика (horeca)
      * Эксклюзив (exclusive)
    - vat_payments: Наличие НДС (можно выбрать несколько) - Наличие НДС
      * hi home (hi_home)
      * in home (in_home)
      * нет (no)
      * не важно (not_important)
    - magazine_cards: Карточки журналов (можно выбрать несколько) - Карточки журналов
      * hi home (hi_home)
      * in home (in_home)
      * нет (no)
      * не важно (not_important)
    - execution_speeds: Скорость исполнения - Скорость исполнения
      * Предварительная запись (advance_booking)
      * быстрый старт (quick_start)
      * не важно (not_important)
    - cooperation_terms_options: Условия сотрудничества - Условия сотрудничества
      * До 5% (up_to_5_percent)
      * До 10% (up_to_10_percent)
      * не важно (not_important)
    - business_forms: Формы бизнеса - Форма бизнеса
    ''',
    parameters=[
        OpenApiParameter(
            name='group',
            type=str,
            location=OpenApiParameter.QUERY,
            description='Фильтр по категории для получения городов только этой категории (необязательно)',
            required=False,
        ),
    ],
    responses={
        200: {'description': 'Варианты для фильтров'}
    }
)
class RepairQuestionnaireFilterChoicesView(views.APIView):
    """
    Получить варианты для фильтров анкет ремонтных бригад / подрядчиков
    GET /api/v1/accounts/repair-questionnaires/filter-choices/
    """
    permission_classes = [permissions.AllowAny]
    
    def get(self, request):
        from .models import RepairQuestionnaire, QUESTIONNAIRE_GROUP_CHOICES
        
        # Основные категории (group) - Выберете основную котегорию
        # Yangi kategoriyalar: ПОД КЛЮЧ, черновые работы, чистовые работы, Сантехника и плитка, Пол, Стены, Комнаты под ключ, Электрика, ВСЕ
        categories = [
            {'value': 'turnkey', 'label': 'ПОД КЛЮЧ'},
            {'value': 'rough_works', 'label': 'черновые работы'},
            {'value': 'finishing_works', 'label': 'чистовые работы'},
            {'value': 'plumbing_tiles', 'label': 'Сантехника и плитка'},
            {'value': 'floor', 'label': 'Пол'},
            {'value': 'walls', 'label': 'Стены'},
            {'value': 'rooms_turnkey', 'label': 'Комнаты под ключ'},
            {'value': 'electrical', 'label': 'Электрика'},
            {'value': 'all', 'label': 'ВСЕ'},
        ]
        
        # Уникальные города из representative_cities - Выберете город
        # Faqat tanlangan kategoriyadagi a'zolar tomonidan e'lon qilingan shaharlar
        all_cities = set()
        # Staff userlar uchun barcha, oddiy userlar uchun faqat is_moderation=True
        is_staff = request.user.is_authenticated and request.user.is_staff
        if is_staff:
            repair_query = RepairQuestionnaire.objects.filter(is_deleted=False)
        else:
            repair_query = RepairQuestionnaire.objects.filter(is_moderation=True, is_deleted=False)
        
        # Group filter bo'lsa, faqat o'sha kategoriyadagi shaharlarni ko'rsatish
        group = request.query_params.get('group')
        if group and group != 'all':
            # Group bo'yicha filter qo'llaymiz (work_list ichida qidirish)
            groups_list = [g.strip() for g in group.split(',')]
            from django.db.models import Q
            group_q = Q()
            for grp in groups_list:
                if grp == 'turnkey':
                    group_q |= Q(work_list__icontains='под ключ')
                elif grp == 'rough_works':
                    group_q |= Q(work_list__icontains='черновые')
                elif grp == 'finishing_works':
                    group_q |= Q(work_list__icontains='чистовые')
                elif grp == 'plumbing_tiles':
                    group_q |= Q(work_list__icontains='сантехника') | Q(work_list__icontains='плитка')
                elif grp == 'floor':
                    group_q |= Q(work_list__icontains='пол')
                elif grp == 'walls':
                    group_q |= Q(work_list__icontains='стены')
                elif grp == 'rooms_turnkey':
                    group_q |= Q(work_list__icontains='комнаты') & Q(work_list__icontains='ключ')
                elif grp == 'electrical':
                    group_q |= Q(work_list__icontains='электрика')
            if group_q:
                repair_query = repair_query.filter(group_q)
        
        for questionnaire in repair_query.exclude(representative_cities__isnull=True).exclude(representative_cities=[]):
            if isinstance(questionnaire.representative_cities, list):
                for city_data in questionnaire.representative_cities:
                    if isinstance(city_data, dict) and 'city' in city_data:
                        all_cities.add(city_data['city'])
                    elif isinstance(city_data, str):
                        all_cities.add(city_data)
        cities_list = [{'value': city, 'label': city} for city in sorted(all_cities)]
        
        # Maxsus variantlar qo'shamiz
        cities_list.insert(0, {'value': 'По всей России', 'label': 'По всей России'})
        cities_list.insert(1, {'value': 'ЮФО', 'label': 'ЮФО'})
        cities_list.insert(2, {'value': 'Любые города онлайн', 'label': 'Любые города онлайн'})
        
        # Сегменты - Выберете сегмент (ko'p tanlash mumkin)
        # Эконом, Комфорт, Бизнесс, Примиум, Хорика, Эксклюзив
        segments = [
            {'value': 'economy', 'label': 'Эконом'},
            {'value': 'comfort', 'label': 'Комфорт'},
            {'value': 'business', 'label': 'Бизнесс'},
            {'value': 'premium', 'label': 'Примиум'},
            {'value': 'horeca', 'label': 'Хорика'},
            {'value': 'exclusive', 'label': 'Эксклюзив'},
        ]
        
        # Наличие НДС - Наличие НДС (ko'p tanlash mumkin)
        vat_payments = [
            {'value': 'hi_home', 'label': 'hi home'},
            {'value': 'in_home', 'label': 'in home'},
            {'value': 'no', 'label': 'нет'},
            {'value': 'not_important', 'label': 'не важно'},
        ]
        
        # Карточки журналов - Карточки журналов (ko'p tanlash mumkin)
        magazine_cards = [
            {'value': 'hi_home', 'label': 'hi home'},
            {'value': 'in_home', 'label': 'in home'},
            {'value': 'no', 'label': 'нет'},
            {'value': 'not_important', 'label': 'не важно'},
        ]
        
        # Скорость исполнения - Скорость исполнения
        execution_speeds = [
            {'value': 'advance_booking', 'label': 'Предварительная запись'},
            {'value': 'quick_start', 'label': 'быстрый старт'},
            {'value': 'not_important', 'label': 'не важно'},
        ]
        
        # Условия сотрудничества - Условия сотрудничества
        cooperation_terms_options = [
            {'value': 'up_to_5_percent', 'label': 'До 5%'},
            {'value': 'up_to_10_percent', 'label': 'До 10%'},
            {'value': 'not_important', 'label': 'не важно'},
        ]
        
        # Формы бизнеса
        business_forms = [
            {'value': choice[0], 'label': choice[1]} 
            for choice in RepairQuestionnaire.BUSINESS_FORM_CHOICES
        ]
        
        return Response({
            'categories': categories,
            'cities': cities_list,
            'segments': segments,
            'vat_payments': vat_payments,
            'magazine_cards': magazine_cards,
            'execution_speeds': execution_speeds,
            'cooperation_terms_options': cooperation_terms_options,
            'business_forms': business_forms,
        }, status=status.HTTP_200_OK)


@extend_schema(
    tags=['Repair Questionnaires'],
    summary='Обновить статус анкеты ремонтной бригады / подрядчика (admin)',
    description='''
    POST: Обновить статус анкеты ремонтной бригады / подрядчика (только для администраторов)
    
    Доступные статусы:
    - pending - Ожидает модерации
    - published - Опубликовано
    - rejected - Отклонено
    - archived - В архиве
    
    Тело запроса:
    {
        "status": "published"
    }
    ''',
    request=QuestionnaireStatusUpdateSerializer,
    responses={
        200: RepairQuestionnaireSerializer,
        400: {'description': 'Ошибка валидации'},
        403: {'description': 'Доступ запрещен. Только администраторы могут изменять статус'},
        404: {'description': 'Анкета не найдена'}
    }
)
class RepairQuestionnaireStatusUpdateView(views.APIView):
    """
    Обновить статус анкеты ремонтной бригады / подрядчика (admin)
    POST /api/v1/accounts/repair-questionnaires/{id}/update-status/
    """
    permission_classes = [permissions.IsAuthenticated]
    
    def get_object(self, pk):
        try:
            return RepairQuestionnaire.objects.get(pk=pk)
        except RepairQuestionnaire.DoesNotExist:
            raise NotFound("Анкета не найдена")
    
    def post(self, request, pk):
        # Проверка прав администратора
        if not (request.user.is_staff or request.user.role == 'admin'):
            raise PermissionDenied("Только администратор может изменять статус анкеты")
        
        questionnaire = self.get_object(pk)
        serializer = QuestionnaireStatusUpdateSerializer(data=request.data)
        
        if serializer.is_valid():
            questionnaire.status = serializer.validated_data['status']
            questionnaire.save()
            
            result_serializer = RepairQuestionnaireSerializer(questionnaire)
            return Response(result_serializer.data, status=status.HTTP_200_OK)
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@extend_schema(
    tags=['Supplier Questionnaires'],
    summary='Список анкет поставщиков / салонов / фабрик',
    description='''
    GET: Получить список всех анкет поставщиков / салонов / фабрик
    
    Фильтры (query параметры):
    - group: Выберете основную категорию (supplier, factory, salon, и т.д.)
    - city: Выберете город (поиск в representative_cities)
    - segment: Выберите сегмент (horeca, business, comfort, premium, medium, economy)
    - vat_payment: Наличие НДС (yes, no)
    - magazine_cards: Карточки журналов (hi_home, in_home, no, other)
    - execution_speed: Скорость исполнения (поиск в delivery_terms)
    - cooperation_terms: Условия сотрудничества (поиск в cooperation_terms)
    - business_form: Форма бизнеса (own_business, franchise)
    - search: Поиск по full_name или brand_name
    - ordering: Сортировка (created_at, -created_at, full_name, -full_name, и т.д.)
    - limit: Количество результатов на странице
    - offset: Смещение для пагинации
    
    POST: Создать новую анкету поставщика / салона / фабрики
    
    Поля анкеты:
    - group: Группа (обязательное). Варианты:
      * designer - Дизайнер
      * architect - Архитектор
      * decorator - Декоратор
      * landscape_designer - Ландшафтный дизайнер
      * light_designer - Светодизайнер
      * interior_designer - Дизайнер интерьера
      * repair_team - Ремонтная бригада
      * contractor - Подрядчик
      * supplier - Поставщик
      * factory - Фабрика
      * salon - Салон
    - full_name: ФИО (обязательное)
    - brand_name: Название бренда (дополнительно в скобках укажите полное юридическое наименование компании) (обязательное)
    - email: E-mail (обязательное)
    - responsible_person: Имя, должность и контактный номер ответственного лица (обязательное)
    - representative_cities: Города представительств или салонов (массив, необязательное)
    - business_form: Форма бизнеса (необязательное). Варианты:
      * own_business - Собственный бизнес
      * franchise - Франшиза
    - product_assortment: Ассортимент продукции (необязательное)
    - welcome_message: Приветственное сообщение о вашей компании (необязательное)
    - cooperation_terms: Условия сотрудничества при работе с клиентами из других городов или регионов (необязательное)
    - segments: Сегменты работы (массив, необязательное). Варианты:
      * horeca - HoReCa
      * business - Бизнес
      * comfort - Комфорт
      * premium - Премиум
      * medium - Средний
      * economy - Эконом
    - vk: VK (необязательное)
    - telegram_channel: Telegram kanal (необязательное)
    - pinterest: Pinterest (необязательное)
    - instagram: Instagram (необязательное)
    - website: Ваш сайт (Veb-sayt) (необязательное, URL)
    - other_contacts: Другое (Boshqa) - дополнительные контакты (массив, необязательное)
    - delivery_terms: Сроки поставки и формат работы (необязательное)
    - vat_payment: Возможна ли оплата с учётом НДС? (необязательное). Варианты:
      * yes - Да
      * no - Нет
    - guarantees: Гарантии и их сроки (необязательное)
    - designer_contractor_terms: Условия работы с дизайнерами и/или подрядчиками (необязательное)
    - magazine_cards: Выдаёте ли вы карточки журналов при покупке продукции? (необязательное). Варианты:
      * hi_home - Hi Home
      * in_home - IN HOME
      * no - Нет
      * other - Другое
    - data_processing_consent: Согласие на обработку данных (обязательное, boolean)
    - company_logo: Логотип компании (shaxsiy kabinet uchun) (необязательное, файл)
    - legal_entity_card: Yuridik shaxs kartasi (shartnoma uchun) (необязательное, файл)
    ''',
    request=SupplierQuestionnaireSerializer,
    responses={
        200: SupplierQuestionnaireSerializer(many=True),
        201: SupplierQuestionnaireSerializer,
        400: {'description': 'Ошибка валидации'}
    }
)
class SupplierQuestionnaireListView(views.APIView):
    """
    Анкеты поставщиков / салонов / фабрик - список
    GET /api/v1/accounts/supplier-questionnaires/ - список всех анкет
    POST /api/v1/accounts/supplier-questionnaires/ - создать анкету
    """
    permission_classes = [permissions.AllowAny]
    
    @extend_schema(
        summary='Получить список анкет поставщиков / салонов / фабрик',
        description='GET: Получить список всех анкет поставщиков / салонов / фабрик с фильтрацией',
        parameters=[
            OpenApiParameter(
                name='group',
                type=str,
                location=OpenApiParameter.QUERY,
                description='Выберете основную категорию (rough_materials, finishing_materials, soft_furniture, cabinet_furniture, appliances, decor, all). Можно указать несколько через запятую',
                required=False,
            ),
            OpenApiParameter(
                name='city',
                type=str,
                location=OpenApiParameter.QUERY,
                description='Выберете город (поиск в representative_cities). Специальные значения: "По всей России", "ЮФО", "Любые города онлайн". Можно указать несколько через запятую',
                required=False,
            ),
            OpenApiParameter(
                name='segment',
                type=str,
                location=OpenApiParameter.QUERY,
                description='Выберите сегмент (economy, comfort, business, premium, horeca, exclusive). Можно указать несколько через запятую',
                required=False,
            ),
            OpenApiParameter(
                name='vat_payment',
                type=str,
                location=OpenApiParameter.QUERY,
                description='Наличие НДС (yes, no, not_important)',
                required=False,
                enum=['yes', 'no', 'not_important'],
            ),
            OpenApiParameter(
                name='magazine_cards',
                type=str,
                location=OpenApiParameter.QUERY,
                description='Карточки журналов (hi_home, in_home, no, not_important, + варианты из медиапространства). Можно указать несколько через запятую',
                required=False,
            ),
            OpenApiParameter(
                name='execution_speed',
                type=str,
                location=OpenApiParameter.QUERY,
                description='Скорость исполнения (in_stock, up_to_2_weeks, up_to_1_month, up_to_3_months, not_important). Можно указать несколько через запятую',
                required=False,
            ),
            OpenApiParameter(
                name='cooperation_terms',
                type=str,
                location=OpenApiParameter.QUERY,
                description='Условия сотрудничества (up_to_10_percent, up_to_20_percent, up_to_30_percent, not_important)',
                required=False,
                enum=['up_to_10_percent', 'up_to_20_percent', 'up_to_30_percent', 'not_important'],
            ),
            OpenApiParameter(
                name='business_form',
                type=str,
                location=OpenApiParameter.QUERY,
                description='Форма бизнеса (own_business, franchise)',
                required=False,
                enum=['own_business', 'franchise'],
            ),
            OpenApiParameter(
                name='search',
                type=str,
                location=OpenApiParameter.QUERY,
                description='Поиск по full_name или brand_name',
                required=False,
            ),
            OpenApiParameter(
                name='ordering',
                type=str,
                location=OpenApiParameter.QUERY,
                description='Сортировка (created_at, -created_at, full_name, -full_name, и т.д.)',
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
            200: SupplierQuestionnaireSerializer(many=True),
        }
    )
    def get(self, request):
        # Staff userlar uchun barcha questionnaire'lar (is_deleted=False), oddiy userlar uchun faqat is_moderation=True
        if request.user.is_authenticated and request.user.is_staff:
            questionnaires = SupplierQuestionnaire.objects.filter(is_deleted=False)
        else:
            questionnaires = SupplierQuestionnaire.objects.filter(is_moderation=True, is_deleted=False)
        
        # Filtering
        # Выберете основную котегорию (group) - ko'p tanlash mumkin
        group = request.query_params.get('group')
        if group:
            if group == 'all':
                # "ВСЕ" - filter qo'llamaymiz
                pass
            else:
                # Ko'p tanlash mumkin - vergul bilan ajratilgan
                groups_list = [g.strip() for g in group.split(',')]
                # Mapping: rough_materials -> product_assortment ichida "черновые", finishing_materials -> "чистовые", soft_furniture -> "мягкая мебель", cabinet_furniture -> "корпусная мебель", appliances -> "техника", decor -> "декор"
                from django.db.models import Q
                group_q = Q()
                for grp in groups_list:
                    if grp == 'rough_materials':
                        group_q |= Q(product_assortment__icontains='черновые')
                    elif grp == 'finishing_materials':
                        group_q |= Q(product_assortment__icontains='чистовые')
                    elif grp == 'soft_furniture':
                        group_q |= Q(product_assortment__icontains='мягкая мебель')
                    elif grp == 'cabinet_furniture':
                        group_q |= Q(product_assortment__icontains='корпусная мебель')
                    elif grp == 'appliances':
                        group_q |= Q(product_assortment__icontains='техника')
                    elif grp == 'decor':
                        group_q |= Q(product_assortment__icontains='декор')
                if group_q:
                    questionnaires = questionnaires.filter(group_q)
        
        # Выберете город (representative_cities - JSONField, contains check) + maxsus variantlar + ko'p tanlash
        city = request.query_params.get('city')
        if city:
            # Ko'p tanlash mumkin - vergul bilan ajratilgan
            cities_list = [c.strip() for c in city.split(',')]
            from django.db.models import Q
            city_q = Q()
            for city_item in cities_list:
                # Maxsus variantlar: "По всей России", "ЮФО", "Любые города онлайн"
                if city_item == "По всей России":
                    # Barcha shaharlar - filter qo'llamaymiz
                    pass
                elif city_item == "ЮФО":
                    # Janubiy Federal Okrug shaharlari
                    yfo_cities = ['Ростов-на-Дону', 'Краснодар', 'Сочи', 'Ставрополь', 'Волгоград', 'Астрахань']
                    for yfo_city in yfo_cities:
                        city_q |= Q(representative_cities__icontains=yfo_city)
                elif city_item == "Любые города онлайн":
                    # Online ishlaydiganlar - cooperation_terms ichida "онлайн" yoki "online" qidirish
                    city_q |= Q(cooperation_terms__icontains='онлайн') | Q(cooperation_terms__icontains='online')
                else:
                    # Oddiy shahar qidirish
                    city_q |= Q(representative_cities__icontains=city_item)
            if city_q:
                questionnaires = questionnaires.filter(city_q)
        
        # Выберите сегмент (segments - JSONField, contains check, ko'p tanlash mumkin)
        segment = request.query_params.get('segment')
        if segment:
            # Ko'p tanlash mumkin - vergul bilan ajratilgan
            segments_list = [s.strip() for s in segment.split(',')]
            from django.db.models import Q
            segment_q = Q()
            for seg in segments_list:
                segment_q |= Q(segments__contains=[seg])
            if segment_q:
                questionnaires = questionnaires.filter(segment_q)
        
        # Наличие НДС (vat_payment)
        vat_payment = request.query_params.get('vat_payment')
        if vat_payment and vat_payment != 'not_important':
            questionnaires = questionnaires.filter(vat_payment=vat_payment)
        
        # Карточки журналов (magazine_cards) - ko'p tanlash mumkin + mediaspace variantlari
        magazine_cards = request.query_params.get('magazine_cards')
        if magazine_cards:
            # Ko'p tanlash mumkin - vergul bilan ajratilgan
            cards_list = [c.strip() for c in magazine_cards.split(',')]
            from django.db.models import Q
            cards_q = Q()
            for card in cards_list:
                if card == 'not_important':
                    # "не важно" - filter qo'llamaymiz
                    pass
                else:
                    # Standard variantlar yoki mediaspace variantlari
                    cards_q |= Q(magazine_cards=card)
            if cards_q:
                questionnaires = questionnaires.filter(cards_q)
        
        # Скорость исполнения (delivery_terms ichida search, ko'p tanlash mumkin)
        execution_speed = request.query_params.get('execution_speed')
        if execution_speed:
            # Ko'p tanlash mumkin - vergul bilan ajratilgan
            speeds_list = [s.strip() for s in execution_speed.split(',')]
            from django.db.models import Q
            speed_q = Q()
            for speed in speeds_list:
                if speed != 'not_important':
                    # Mapping: in_stock -> "в наличии", up_to_2_weeks -> "2 недель", up_to_1_month -> "1 месяц", up_to_3_months -> "3 месяцев"
                    speed_mapping = {
                        'in_stock': 'в наличии',
                        'up_to_2_weeks': '2 недель',
                        'up_to_1_month': '1 месяц',
                        'up_to_3_months': '3 месяцев',
                    }
                    search_term = speed_mapping.get(speed, speed)
                    speed_q |= Q(delivery_terms__icontains=search_term)
            if speed_q:
                questionnaires = questionnaires.filter(speed_q)
        
        # Условия сотрудничества (cooperation_terms ichida search)
        cooperation_terms = request.query_params.get('cooperation_terms')
        if cooperation_terms and cooperation_terms != 'not_important':
            # Mapping: up_to_10_percent -> "10%", up_to_20_percent -> "20%", up_to_30_percent -> "30%"
            terms_mapping = {
                'up_to_10_percent': '10%',
                'up_to_20_percent': '20%',
                'up_to_30_percent': '30%',
            }
            search_term = terms_mapping.get(cooperation_terms, cooperation_terms)
            questionnaires = questionnaires.filter(cooperation_terms__icontains=search_term)
        
        # Форма бизнеса (business_form)
        business_form = request.query_params.get('business_form')
        if business_form:
            questionnaires = questionnaires.filter(business_form=business_form)
        
        # Search by full_name or brand_name
        search = request.query_params.get('search')
        if search:
            questionnaires = questionnaires.filter(
                django_models.Q(full_name__icontains=search) | 
                django_models.Q(brand_name__icontains=search)
            )
        
        # Ordering
        ordering = request.query_params.get('ordering', '-created_at')
        questionnaires = questionnaires.order_by(ordering)
        
        # Pagination
        paginator = LimitOffsetPagination()
        paginator.default_limit = 100
        paginator.limit_query_param = 'limit'
        paginator.offset_query_param = 'offset'
        
        paginated_questionnaires = paginator.paginate_queryset(questionnaires, request)
        serializer = SupplierQuestionnaireSerializer(paginated_questionnaires, many=True)
        
        return paginator.get_paginated_response(serializer.data)
    
    def post(self, request):
        serializer = SupplierQuestionnaireSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@extend_schema(
    tags=['Supplier Questionnaires'],
    summary='Детали анкеты поставщика / салона / фабрики',
    description='''
    GET: Получить детали анкеты поставщика / салона / фабрики по ID
    
    PUT: Обновить анкету поставщика / салона / фабрики (частичное обновление поддерживается)
    
    DELETE: Удалить анкету поставщика / салона / фабрики
    
    Поля для обновления (PUT):
    - group: Группа. Варианты:
      * designer - Дизайнер
      * architect - Архитектор
      * decorator - Декоратор
      * landscape_designer - Ландшафтный дизайнер
      * light_designer - Светодизайнер
      * interior_designer - Дизайнер интерьера
      * repair_team - Ремонтная бригада
      * contractor - Подрядчик
      * supplier - Поставщик
      * factory - Фабрика
      * salon - Салон
    - full_name: ФИО
    - brand_name: Название бренда (дополнительно в скобках укажите полное юридическое наименование компании)
    - email: E-mail
    - responsible_person: Имя, должность и контактный номер ответственного лица
    - representative_cities: Города представительств или салонов (массив)
    - business_form: Форма бизнеса. Варианты:
      * own_business - Собственный бизнес
      * franchise - Франшиза
    - product_assortment: Ассортимент продукции
    - welcome_message: Приветственное сообщение о вашей компании
    - cooperation_terms: Условия сотрудничества при работе с клиентами из других городов или регионов
    - segments: Сегменты работы (массив). Варианты:
      * horeca - HoReCa
      * business - Бизнес
      * comfort - Комфорт
      * premium - Премиум
      * medium - Средний
      * economy - Эконом
    - vk: VK
    - telegram_channel: Telegram kanal
    - pinterest: Pinterest
    - instagram: Instagram
    - website: Ваш сайт (Veb-sayt) (URL)
    - other_contacts: Другое (Boshqa) - дополнительные контакты (массив)
    - delivery_terms: Сроки поставки и формат работы
    - vat_payment: Возможна ли оплата с учётом НДС?. Варианты:
      * yes - Да
      * no - Нет
    - guarantees: Гарантии и их сроки
    - designer_contractor_terms: Условия работы с дизайнерами и/или подрядчиками
    - magazine_cards: Выдаёте ли вы карточки журналов при покупке продукции?. Варианты:
      * hi_home - Hi Home
      * in_home - IN HOME
      * no - Нет
      * other - Другое
    - data_processing_consent: Согласие на обработку данных (boolean)
    - company_logo: Логотип компании (shaxsiy kabinet uchun) (файл)
    - legal_entity_card: Yuridik shaxs kartasi (shartnoma uchun) (файл)
    ''',
    request=SupplierQuestionnaireSerializer,
    responses={
        200: SupplierQuestionnaireSerializer,
        400: {'description': 'Ошибка валидации'},
        404: {'description': 'Анкета не найдена'},
        204: {'description': 'Анкета успешно удалена'}
    }
)
class SupplierQuestionnaireDetailView(views.APIView):
    """
    Анкета поставщика / салона / фабрики - детали, обновление, удаление
    GET /api/v1/accounts/supplier-questionnaires/{id}/ - получить анкету
    PUT /api/v1/accounts/supplier-questionnaires/{id}/ - обновить анкету
    DELETE /api/v1/accounts/supplier-questionnaires/{id}/ - удалить анкету
    """
    permission_classes = [permissions.AllowAny]
    
    def get_object(self, pk, request=None):
        try:
            # Staff userlar uchun barcha, oddiy userlar uchun faqat is_moderation=True
            is_staff = request and request.user.is_authenticated and request.user.is_staff
            if is_staff:
                return SupplierQuestionnaire.objects.filter(is_deleted=False).get(pk=pk)
            else:
                return SupplierQuestionnaire.objects.filter(is_moderation=True, is_deleted=False).get(pk=pk)
        except SupplierQuestionnaire.DoesNotExist:
            raise NotFound("Анкета не найдена")
    
    def get(self, request, pk):
        questionnaire = self.get_object(pk, request)
        serializer = SupplierQuestionnaireSerializer(questionnaire)
        return Response(serializer.data, status=status.HTTP_200_OK)
    
    def put(self, request, pk):
        if not request.user.is_authenticated:
            raise PermissionDenied("Требуется авторизация для обновления анкеты")
        questionnaire = self.get_object(pk)
        serializer = SupplierQuestionnaireSerializer(questionnaire, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    def delete(self, request, pk):
        if not request.user.is_authenticated:
            raise PermissionDenied("Требуется авторизация для удаления анкеты")
        questionnaire = self.get_object(pk, request)
        questionnaire.is_deleted = True
        questionnaire.save()
        return Response({'message': 'Анкета успешно удалена'}, status=status.HTTP_200_OK)


@extend_schema(
    tags=['Supplier Questionnaires'],
    summary='Получить варианты для фильтров анкет поставщиков / салонов / фабрик',
    description='''
    GET: Получить все доступные варианты для фильтров анкет поставщиков / салонов / фабрик
    
    Query параметры:
    - group: (необязательно) Фильтр по категории для получения городов только этой категории
    
    Возвращает:
    - categories: Основные категории (можно выбрать несколько) - Выберете основную котегорию
      * Черновые материалы (rough_materials)
      * Чистовые материалы (finishing_materials)
      * Мягкая мебель (soft_furniture)
      * Корпусная мебель (cabinet_furniture)
      * Техника (appliances)
      * Декор (decor)
      * ВСЕ (all)
    - cities: Список уникальных городов из анкет выбранной категории + специальные варианты - Выберете город
      * По всей России
      * ЮФО
      * Любые города онлайн
      * + города, заявленные членами клуба в выбранной категории (можно выбрать несколько)
    - segments: Сегменты работы (можно выбрать несколько) - Выберете сегмент
      * Эконом (economy)
      * Комфорт (comfort)
      * Бизнесс (business)
      * Примиум (premium)
      * Хорика (horeca)
      * Эксклюзив (exclusive)
    - vat_payments: Наличие НДС - Наличие НДС
      * Да (yes)
      * Нет (no)
      * Не важно (not_important)
    - magazine_cards: Карточки журналов (можно выбрать несколько) - Карточки журналов
      * hi home (hi_home)
      * in home (in_home)
      * нет (no)
      * не важно (not_important)
      * + варианты из медиапространства (MediaQuestionnaire)
    - execution_speeds: Скорость исполнения (можно выбрать несколько) - Скорость исполнения
      * В наличии (in_stock)
      * до 2х недель (up_to_2_weeks)
      * до 1 месяца (up_to_1_month)
      * до 3х месяцев (up_to_3_months)
      * не важно (not_important)
    - cooperation_terms_options: Условия сотрудничества - Условия сотрудничества
      * до 10% (up_to_10_percent)
      * до 20% (up_to_20_percent)
      * до 30% (up_to_30_percent)
      * не важно (not_important)
    - business_forms: Формы бизнеса - Форма бизнеса
    ''',
    parameters=[
        OpenApiParameter(
            name='group',
            type=str,
            location=OpenApiParameter.QUERY,
            description='Фильтр по категории для получения городов только этой категории (необязательно)',
            required=False,
        ),
    ],
    responses={
        200: {'description': 'Варианты для фильтров'}
    }
)
class SupplierQuestionnaireFilterChoicesView(views.APIView):
    """
    Получить варианты для фильтров анкет поставщиков / салонов / фабрик
    GET /api/v1/accounts/supplier-questionnaires/filter-choices/
    """
    permission_classes = [permissions.AllowAny]
    
    def get(self, request):
        from .models import SupplierQuestionnaire, MediaQuestionnaire, QUESTIONNAIRE_GROUP_CHOICES
        
        # Основные категории (group) - Выберете основную категорию
        # Yangi kategoriyalar: Черновые материалы, Чистовые материалы, Мягкая мебель, Корпусная мебель, Техника, Декор, ВСЕ
        categories = [
            {'value': 'rough_materials', 'label': 'Черновые материалы'},
            {'value': 'finishing_materials', 'label': 'Чистовые материалы'},
            {'value': 'soft_furniture', 'label': 'Мягкая мебель'},
            {'value': 'cabinet_furniture', 'label': 'Корпусная мебель'},
            {'value': 'appliances', 'label': 'Техника'},
            {'value': 'decor', 'label': 'Декор'},
            {'value': 'all', 'label': 'ВСЕ'},
        ]
        
        # Уникальные города из representative_cities - Выберете город
        # Faqat tanlangan kategoriyadagi a'zolar tomonidan e'lon qilingan shaharlar
        # Staff userlar uchun barcha (is_deleted=False), oddiy userlar uchun faqat is_moderation=True
        is_staff = request.user.is_authenticated and request.user.is_staff
        if is_staff:
            supplier_query = SupplierQuestionnaire.objects.filter(is_deleted=False)
        else:
            supplier_query = SupplierQuestionnaire.objects.filter(is_moderation=True, is_deleted=False)
        
        # Group filter bo'lsa, faqat o'sha kategoriyadagi shaharlarni ko'rsatish
        group = request.query_params.get('group')
        if group and group != 'all':
            # Group bo'yicha filter qo'llaymiz (product_assortment ichida qidirish)
            groups_list = [g.strip() for g in group.split(',')]
            from django.db.models import Q
            group_q = Q()
            for grp in groups_list:
                if grp == 'rough_materials':
                    group_q |= Q(product_assortment__icontains='черновые')
                elif grp == 'finishing_materials':
                    group_q |= Q(product_assortment__icontains='чистовые')
                elif grp == 'soft_furniture':
                    group_q |= Q(product_assortment__icontains='мягкая мебель')
                elif grp == 'cabinet_furniture':
                    group_q |= Q(product_assortment__icontains='корпусная мебель')
                elif grp == 'appliances':
                    group_q |= Q(product_assortment__icontains='техника')
                elif grp == 'decor':
                    group_q |= Q(product_assortment__icontains='декор')
            if group_q:
                supplier_query = supplier_query.filter(group_q)
        
        all_cities = set()
        for questionnaire in supplier_query.exclude(representative_cities__isnull=True).exclude(representative_cities=[]):
            if isinstance(questionnaire.representative_cities, list):
                for city_data in questionnaire.representative_cities:
                    if isinstance(city_data, dict) and 'city' in city_data:
                        all_cities.add(city_data['city'])
                    elif isinstance(city_data, str):
                        all_cities.add(city_data)
        cities_list = [{'value': city, 'label': city} for city in sorted(all_cities)]
        
        # Maxsus variantlar qo'shamiz
        cities_list.insert(0, {'value': 'По всей России', 'label': 'По всей России'})
        cities_list.insert(1, {'value': 'ЮФО', 'label': 'ЮФО'})
        cities_list.insert(2, {'value': 'Любые города онлайн', 'label': 'Любые города онлайн'})
        
        # Сегменты - Выберите сегмент (ko'p tanlash mumkin)
        # Эконом, Комфорт, Бизнесс, Примиум, Хорика, Эксклюзив
        segments = [
            {'value': 'economy', 'label': 'Эконом'},
            {'value': 'comfort', 'label': 'Комфорт'},
            {'value': 'business', 'label': 'Бизнесс'},
            {'value': 'premium', 'label': 'Примиум'},
            {'value': 'horeca', 'label': 'Хорика'},
            {'value': 'exclusive', 'label': 'Эксклюзив'},
        ]
        
        # Наличие НДС - Наличие НДС
        vat_payments = [
            {'value': 'yes', 'label': 'Да'},
            {'value': 'no', 'label': 'Нет'},
            {'value': 'not_important', 'label': 'Не важно'},
        ]
        
        # Карточки журналов - Карточки журналов (ko'p tanlash mumkin) + mediaspace variantlari
        magazine_cards = [
            {'value': 'hi_home', 'label': 'hi home'},
            {'value': 'in_home', 'label': 'in home'},
            {'value': 'no', 'label': 'нет'},
            {'value': 'not_important', 'label': 'не важно'},
        ]
        
        # Mediaspace guruhidan variantlar qo'shamiz
        # MediaQuestionnaire modelidan brand_name larni olamiz
        if is_staff:
            media_query = MediaQuestionnaire.objects.filter(is_deleted=False, is_moderation=True)
        else:
            media_query = MediaQuestionnaire.objects.filter(is_moderation=True, is_deleted=False)
        
        # MediaQuestionnaire modelida brand_name bor
        for media in media_query:
            if media.brand_name:
                # Duplicate larni oldini olish uchun value ni unique qilamiz
                media_value = media.brand_name.lower().replace(' ', '_').replace('-', '_')
                # Agar allaqachon qo'shilgan bo'lsa, qo'shmaslik
                if not any(card['value'] == media_value for card in magazine_cards):
                    magazine_cards.append({'value': media_value, 'label': media.brand_name})
        
        # Скорость исполнения - Скорость исполнения (ko'p tanlash mumkin)
        execution_speeds = [
            {'value': 'in_stock', 'label': 'В наличии'},
            {'value': 'up_to_2_weeks', 'label': 'до 2х недель'},
            {'value': 'up_to_1_month', 'label': 'до 1 месяца'},
            {'value': 'up_to_3_months', 'label': 'до 3х месяцев'},
            {'value': 'not_important', 'label': 'не важно'},
        ]
        
        # Условия сотрудничества - Условия сотрудничества
        cooperation_terms_options = [
            {'value': 'up_to_10_percent', 'label': 'до 10%'},
            {'value': 'up_to_20_percent', 'label': 'до 20%'},
            {'value': 'up_to_30_percent', 'label': 'до 30%'},
            {'value': 'not_important', 'label': 'не важно'},
        ]
        
        # Формы бизнеса
        business_forms = [
            {'value': choice[0], 'label': choice[1]} 
            for choice in SupplierQuestionnaire.BUSINESS_FORM_CHOICES
        ]
        
        return Response({
            'categories': categories,
            'cities': cities_list,
            'segments': segments,
            'vat_payments': vat_payments,
            'magazine_cards': magazine_cards,
            'execution_speeds': execution_speeds,
            'cooperation_terms_options': cooperation_terms_options,
            'business_forms': business_forms,
        }, status=status.HTTP_200_OK)


@extend_schema(
    tags=['Supplier Questionnaires'],
    summary='Обновить статус анкеты поставщика / салона / фабрики (admin)',
    description='''
    POST: Обновить статус анкеты поставщика / салона / фабрики (только для администраторов)
    
    Доступные статусы:
    - pending - Ожидает модерации
    - published - Опубликовано
    - rejected - Отклонено
    - archived - В архиве
    
    Тело запроса:
    {
        "status": "published"
    }
    ''',
    request=QuestionnaireStatusUpdateSerializer,
    responses={
        200: SupplierQuestionnaireSerializer,
        400: {'description': 'Ошибка валидации'},
        403: {'description': 'Доступ запрещен. Только администраторы могут изменять статус'},
        404: {'description': 'Анкета не найдена'}
    }
)
class SupplierQuestionnaireStatusUpdateView(views.APIView):
    """
    Обновить статус анкеты поставщика / салона / фабрики (admin)
    POST /api/v1/accounts/supplier-questionnaires/{id}/update-status/
    """
    permission_classes = [permissions.IsAuthenticated]
    
    def get_object(self, pk):
        try:
            return SupplierQuestionnaire.objects.get(pk=pk)
        except SupplierQuestionnaire.DoesNotExist:
            raise NotFound("Анкета не найдена")
    
    def post(self, request, pk):
        # Проверка прав администратора
        if not (request.user.is_staff or request.user.role == 'admin'):
            raise PermissionDenied("Только администратор может изменять статус анкеты")
        
        questionnaire = self.get_object(pk)
        serializer = QuestionnaireStatusUpdateSerializer(data=request.data)
        
        if serializer.is_valid():
            questionnaire.status = serializer.validated_data['status']
            questionnaire.save()
            
            result_serializer = SupplierQuestionnaireSerializer(questionnaire)
            return Response(result_serializer.data, status=status.HTTP_200_OK)
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@extend_schema(
    tags=['Media Questionnaires'],
    summary='Список анкет медиа пространств и интерьерных журналов',
    description='''
    GET: Получить список всех анкет медиа пространств и интерьерных журналов
    
    POST: Создать новую анкету медиа пространства / интерьерного журнала
    
    Поля анкеты:
    - group: Группа (обязательное). Варианты:
      * designer - Дизайнер
      * architect - Архитектор
      * decorator - Декоратор
      * landscape_designer - Ландшафтный дизайнер
      * light_designer - Светодизайнер
      * interior_designer - Дизайнер интерьера
      * repair_team - Ремонтная бригада
      * contractor - Подрядчик
      * supplier - Поставщик
      * factory - Фабрика
      * salon - Салон
    - full_name: ФИО (обязательное)
    - phone: Номер телефона (необязательное)
    - brand_name: Название бренда (обязательное)
    - email: E-mail (обязательное)
    - responsible_person: Имя, должность и контактный номер ответственного лица (обязательное)
    - representative_cities: Города представительств (массив объектов: город, адрес, телефон, район) (необязательное)
    - business_form: Форма бизнеса: Собственный бизнес или франшиза? (с указанием налоговой формы) (необязательное)
    - activity_description: Опишите подробно чем именно занимаетесь и чем можете быть полезны сообществу (обязательное)
    - welcome_message: Приветственное сообщение о вашей компании (обязательное)
    - cooperation_terms: Условия сотрудничества (обязательное)
    - segments: Сегменты, которые принимаете к публикации (массив, обязательное). Варианты:
      * horeca - HoReCa
      * business - Бизнес
      * comfort - Комфорт
      * premium - Премиум
      * medium - Средний
      * economy - Эконом
    - vk: VK (необязательное)
    - telegram_channel: Telegram канал (необязательное)
    - pinterest: Pinterest (необязательное)
    - instagram: Instagram (необязательное)
    - website: Ваш сайт (необязательное, URL)
    - other_contacts: Другое - дополнительные контакты (массив, необязательное)
    - vat_payment: Возможна ли оплата с учётом НДС? (необязательное). Варианты:
      * yes - Да
      * no - Нет
    - additional_info: Дополнительная информация (необязательное)
    ''',
    request=MediaQuestionnaireSerializer,
    responses={
        200: MediaQuestionnaireSerializer(many=True),
        201: MediaQuestionnaireSerializer,
        400: {'description': 'Ошибка валидации'}
    }
)
class MediaQuestionnaireListView(views.APIView):
    """
    Анкеты медиа пространств и интерьерных журналов - список
    GET /api/v1/accounts/media-questionnaires/ - список всех анкет
    POST /api/v1/accounts/media-questionnaires/ - создать анкету
    """
    permission_classes = [permissions.AllowAny]
    
    def get(self, request):
        # Staff userlar uchun barcha questionnaire'lar, oddiy userlar uchun faqat is_moderation=True
        if request.user.is_authenticated and request.user.is_staff:
            questionnaires = MediaQuestionnaire.objects.filter(is_deleted=False).order_by('-created_at')
        else:
            questionnaires = MediaQuestionnaire.objects.filter(is_moderation=True, is_deleted=False).order_by('-created_at')
        
        # Pagination
        paginator = LimitOffsetPagination()
        paginator.default_limit = 100
        paginator.limit_query_param = 'limit'
        paginator.offset_query_param = 'offset'
        
        paginated_questionnaires = paginator.paginate_queryset(questionnaires, request)
        serializer = MediaQuestionnaireSerializer(paginated_questionnaires, many=True)
        
        return paginator.get_paginated_response(serializer.data)
    
    def post(self, request):
        serializer = MediaQuestionnaireSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@extend_schema(
    tags=['Media Questionnaires'],
    summary='Детали анкеты медиа пространства / интерьерного журнала',
    description='''
    GET: Получить детали анкеты медиа пространства / интерьерного журнала по ID
    
    PUT: Обновить анкету медиа пространства / интерьерного журнала (частичное обновление поддерживается)
    
    DELETE: Удалить анкету медиа пространства / интерьерного журнала
    
    Поля для обновления (PUT):
    - group: Группа. Варианты:
      * designer - Дизайнер
      * architect - Архитектор
      * decorator - Декоратор
      * landscape_designer - Ландшафтный дизайнер
      * light_designer - Светодизайнер
      * interior_designer - Дизайнер интерьера
      * repair_team - Ремонтная бригада
      * contractor - Подрядчик
      * supplier - Поставщик
      * factory - Фабрика
      * salon - Салон
    - full_name: ФИО
    - phone: Номер телефона
    - brand_name: Название бренда
    - email: E-mail
    - responsible_person: Имя, должность и контактный номер ответственного лица
    - representative_cities: Города представительств (массив объектов: город, адрес, телефон, район)
    - business_form: Форма бизнеса: Собственный бизнес или франшиза? (с указанием налоговой формы)
    - activity_description: Опишите подробно чем именно занимаетесь и чем можете быть полезны сообществу
    - welcome_message: Приветственное сообщение о вашей компании
    - cooperation_terms: Условия сотрудничества
    - segments: Сегменты, которые принимаете к публикации (массив). Варианты:
      * horeca - HoReCa
      * business - Бизнес
      * comfort - Комфорт
      * premium - Премиум
      * medium - Средний
      * economy - Эконом
    - vk: VK
    - telegram_channel: Telegram канал
    - pinterest: Pinterest
    - instagram: Instagram
    - website: Ваш сайт (URL)
    - other_contacts: Другое - дополнительные контакты (массив)
    - vat_payment: Возможна ли оплата с учётом НДС?. Варианты:
      * yes - Да
      * no - Нет
    - additional_info: Дополнительная информация
    ''',
    request=MediaQuestionnaireSerializer,
    responses={
        200: MediaQuestionnaireSerializer,
        400: {'description': 'Ошибка валидации'},
        404: {'description': 'Анкета не найдена'},
        204: {'description': 'Анкета успешно удалена'}
    }
)
class MediaQuestionnaireDetailView(views.APIView):
    """
    Анкета медиа пространства / интерьерного журнала - детали, обновление, удаление
    GET /api/v1/accounts/media-questionnaires/{id}/ - получить анкету
    PUT /api/v1/accounts/media-questionnaires/{id}/ - обновить анкету
    DELETE /api/v1/accounts/media-questionnaires/{id}/ - удалить анкету
    """
    permission_classes = [permissions.AllowAny]
    
    def get_object(self, pk, request=None):
        try:
            # Staff userlar uchun barcha, oddiy userlar uchun faqat is_moderation=True
            is_staff = request and request.user.is_authenticated and request.user.is_staff
            if is_staff:
                return MediaQuestionnaire.objects.filter(is_deleted=False).get(pk=pk)
            else:
                return MediaQuestionnaire.objects.filter(is_moderation=True, is_deleted=False).get(pk=pk)
        except MediaQuestionnaire.DoesNotExist:
            raise NotFound("Анкета не найдена")
    
    def get(self, request, pk):
        questionnaire = self.get_object(pk, request)
        serializer = MediaQuestionnaireSerializer(questionnaire)
        return Response(serializer.data, status=status.HTTP_200_OK)
    
    def put(self, request, pk):
        if not request.user.is_authenticated:
            raise PermissionDenied("Требуется авторизация для обновления анкеты")
        questionnaire = self.get_object(pk, request)
        serializer = MediaQuestionnaireSerializer(questionnaire, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    def delete(self, request, pk):
        if not request.user.is_authenticated:
            raise PermissionDenied("Требуется авторизация для удаления анкеты")
        questionnaire = self.get_object(pk, request)
        questionnaire.is_deleted = True
        questionnaire.save()
        return Response({'message': 'Анкета успешно удалена'}, status=status.HTTP_200_OK)


@extend_schema(
    tags=['Media Questionnaires'],
    summary='Обновить статус анкеты медиа пространства / интерьерного журнала (admin)',
    description='''
    POST: Обновить статус анкеты медиа пространства / интерьерного журнала (только для администраторов)
    
    Доступные статусы:
    - pending - Ожидает модерации
    - published - Опубликовано
    - rejected - Отклонено
    - archived - В архиве
    
    Тело запроса:
    {
        "status": "published"
    }
    ''',
    request=QuestionnaireStatusUpdateSerializer,
    responses={
        200: MediaQuestionnaireSerializer,
        400: {'description': 'Ошибка валидации'},
        403: {'description': 'Доступ запрещен. Только администраторы могут изменять статус'},
        404: {'description': 'Анкета не найдена'}
    }
)
class MediaQuestionnaireStatusUpdateView(views.APIView):
    """
    Обновить статус анкеты медиа пространства / интерьерного журнала (admin)
    POST /api/v1/accounts/media-questionnaires/{id}/update-status/
    """
    permission_classes = [permissions.IsAuthenticated]
    
    def get_object(self, pk):
        try:
            return MediaQuestionnaire.objects.get(pk=pk)
        except MediaQuestionnaire.DoesNotExist:
            raise NotFound("Анкета не найдена")
    
    def post(self, request, pk):
        # Проверка прав администратора
        if not (request.user.is_staff or request.user.role == 'admin'):
            raise PermissionDenied("Только администратор может изменять статус анкеты")
        
        questionnaire = self.get_object(pk)
        serializer = QuestionnaireStatusUpdateSerializer(data=request.data)
        
        if serializer.is_valid():
            questionnaire.status = serializer.validated_data['status']
            questionnaire.save()
            
            result_serializer = MediaQuestionnaireSerializer(questionnaire)
            return Response(result_serializer.data, status=status.HTTP_200_OK)
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


from rest_framework import permissions, status, views
from rest_framework.response import Response
from rest_framework.exceptions import NotFound, PermissionDenied
from drf_spectacular.utils import extend_schema
from datetime import date, timedelta

from .models import DesignerQuestionnaire, RepairQuestionnaire, SupplierQuestionnaire, MediaQuestionnaire, Report
from .serializers import DesignerQuestionnaireSerializer, RepairQuestionnaireSerializer, SupplierQuestionnaireSerializer, MediaQuestionnaireSerializer
from django.contrib.auth import get_user_model

User = get_user_model()


@extend_schema(
    tags=['Designer Questionnaires'],
    summary='Пройти модерацию анкеты дизайнера (admin)',
    description='''
    PATCH: Пройти модерацию анкеты дизайнера (только для администраторов)
    
    Request body: пустой (только ID в URL)
    
    Правила:
    - Только администратор (is_staff=True) может пройти модерацию
    - Перед модерацией проверяется наличие поля phone
    - Если phone заполнен:
      - Создается User с phone и role='designer' (если не существует)
      - Создается Report с start_date=сегодня и end_date=через 3 месяца (для Дизайн)
    - После успешной модерации is_moderation=True
    ''',
    responses={
        200: DesignerQuestionnaireSerializer,
        400: {'description': 'Ошибка валидации (phone не заполнен)'},
        403: {'description': 'Доступ запрещен. Только администраторы могут проходить модерацию'},
        404: {'description': 'Анкета не найдена'}
    }
)
class DesignerQuestionnaireModerationView(views.APIView):
    """
    Пройти модерацию анкеты дизайнера (admin)
    PATCH /api/v1/accounts/questionnaires/{id}/moderation/
    """
    permission_classes = [permissions.IsAuthenticated]
    
    def get_object(self, pk):
        """Анкету olish"""
        try:
            return DesignerQuestionnaire.objects.get(pk=pk)
        except DesignerQuestionnaire.DoesNotExist:
            raise NotFound("Анкета не найдена")
    
    def patch(self, request, pk):
        """PATCH: Пройти модерацию"""
        # Проверка прав администратора
        if not (request.user.is_staff or request.user.role == 'admin'):
            raise PermissionDenied("Только администратор может проходить модерацию")
        
        questionnaire = self.get_object(pk)
        
        # Проверка phone
        if not questionnaire.phone:
            return Response(
                {'error': 'Телефон не заполнен. Необходимо заполнить телефон перед модерацией.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Создание или получение User
        # Очищаем phone от + и пробелов для поиска
        clean_phone = ''.join(filter(str.isdigit, questionnaire.phone))
        user, created = User.objects.get_or_create(
            phone=clean_phone,
            defaults={
                'role': 'designer',
                'full_name': questionnaire.full_name,
                'is_phone_verified': True,
                'is_profile_completed': True,
            }
        )
        
        # Если пользователь уже существует, обновляем роль если нужно
        if not created and user.role != 'designer':
            user.role = 'designer'
            user.save()
        
        # Создание Report
        start_date = date.today()
        # Для Дизайн - 3 месяца
        end_date = start_date + timedelta(days=90)
        
        Report.objects.create(
            user=user,
            start_date=start_date,
            end_date=end_date
        )
        
        # Установка is_moderation=True
        questionnaire.is_moderation = True
        questionnaire.save()
        
        result_serializer = DesignerQuestionnaireSerializer(questionnaire)
        return Response(result_serializer.data, status=status.HTTP_200_OK)


@extend_schema(
    tags=['Repair Questionnaires'],
    summary='Пройти модерацию анкеты ремонтной бригады (admin)',
    description='''
    PATCH: Пройти модерацию анкеты ремонтной бригады (только для администраторов)
    
    Request body: пустой (только ID в URL)
    
    Правила:
    - Только администратор (is_staff=True) может пройти модерацию
    - Перед модерацией проверяется наличие поля phone
    - Если phone заполнен:
      - Создается User с phone и role='repair' (если не существует)
      - Создается Report с start_date=сегодня и end_date=через 1 год (для Ремонт)
    - После успешной модерации is_moderation=True
    ''',
    responses={
        200: RepairQuestionnaireSerializer,
        400: {'description': 'Ошибка валидации (phone не заполнен)'},
        403: {'description': 'Доступ запрещен. Только администраторы могут проходить модерацию'},
        404: {'description': 'Анкета не найдена'}
    }
)
class RepairQuestionnaireModerationView(views.APIView):
    """
    Пройти модерацию анкеты ремонтной бригады (admin)
    PATCH /api/v1/accounts/repair-questionnaires/{id}/moderation/
    """
    permission_classes = [permissions.IsAuthenticated]
    
    def get_object(self, pk):
        """Анкету olish"""
        try:
            return RepairQuestionnaire.objects.get(pk=pk)
        except RepairQuestionnaire.DoesNotExist:
            raise NotFound("Анкета не найдена")
    
    def patch(self, request, pk):
        """PATCH: Пройти модерацию"""
        # Проверка прав администратора
        if not (request.user.is_staff or request.user.role == 'admin'):
            raise PermissionDenied("Только администратор может проходить модерацию")
        
        questionnaire = self.get_object(pk)
        
        # Проверка phone
        if not questionnaire.phone:
            return Response(
                {'error': 'Телефон не заполнен. Необходимо заполнить телефон перед модерацией.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Создание или получение User
        user, created = User.objects.get_or_create(
            phone=questionnaire.phone,
            defaults={
                'role': 'repair',
                'full_name': questionnaire.full_name,
                'is_phone_verified': True,
                'is_profile_completed': True,
            }
        )
        
        # Если пользователь уже существует, обновляем роль если нужно
        if not created and user.role != 'repair':
            user.role = 'repair'
            user.save()
        
        # Создание Report
        start_date = date.today()
        # Для Ремонт - 1 год
        end_date = start_date + timedelta(days=365)
        
        Report.objects.create(
            user=user,
            start_date=start_date,
            end_date=end_date
        )
        
        # Установка is_moderation=True
        questionnaire.is_moderation = True
        questionnaire.save()
        
        result_serializer = RepairQuestionnaireSerializer(questionnaire)
        return Response(result_serializer.data, status=status.HTTP_200_OK)


@extend_schema(
    tags=['Supplier Questionnaires'],
    summary='Пройти модерацию анкеты поставщика (admin)',
    description='''
    PATCH: Пройти модерацию анкеты поставщика (только для администраторов)
    
    Request body: пустой (только ID в URL)
    
    Правила:
    - Только администратор (is_staff=True) может пройти модерацию
    - Перед модерацией проверяется наличие поля phone
    - Если phone заполнен:
      - Создается User с phone и role='supplier' (если не существует)
      - Создается Report с start_date=сегодня и end_date=через 1 год (для Поставщик)
    - После успешной модерации is_moderation=True
    ''',
    responses={
        200: SupplierQuestionnaireSerializer,
        400: {'description': 'Ошибка валидации (phone не заполнен)'},
        403: {'description': 'Доступ запрещен. Только администраторы могут проходить модерацию'},
        404: {'description': 'Анкета не найдена'}
    }
)
class SupplierQuestionnaireModerationView(views.APIView):
    """
    Пройти модерацию анкеты поставщика (admin)
    PATCH /api/v1/accounts/supplier-questionnaires/{id}/moderation/
    """
    permission_classes = [permissions.IsAuthenticated]
    
    def get_object(self, pk):
        """Анкету olish"""
        try:
            return SupplierQuestionnaire.objects.get(pk=pk)
        except SupplierQuestionnaire.DoesNotExist:
            raise NotFound("Анкета не найдена")
    
    def patch(self, request, pk):
        """PATCH: Пройти модерацию"""
        # Проверка прав администратора
        if not (request.user.is_staff or request.user.role == 'admin'):
            raise PermissionDenied("Только администратор может проходить модерацию")
        
        questionnaire = self.get_object(pk)
        
        # Проверка phone
        if not questionnaire.phone:
            return Response(
                {'error': 'Телефон не заполнен. Необходимо заполнить телефон перед модерацией.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Создание или получение User
        # Очищаем phone от + и пробелов для поиска
        clean_phone = ''.join(filter(str.isdigit, questionnaire.phone))
        user, created = User.objects.get_or_create(
            phone=clean_phone,
            defaults={
                'role': 'supplier',
                'full_name': questionnaire.full_name,
                'is_phone_verified': True,
                'is_profile_completed': True,
            }
        )
        
        # Если пользователь уже существует, обновляем роль если нужно
        if not created and user.role != 'supplier':
            user.role = 'supplier'
            user.save()
        
        # Создание Report
        start_date = date.today()
        # Для Поставщик - 1 год
        end_date = start_date + timedelta(days=365)
        
        Report.objects.create(
            user=user,
            start_date=start_date,
            end_date=end_date
        )
        
        # Установка is_moderation=True
        questionnaire.is_moderation = True
        questionnaire.save()
        
        result_serializer = SupplierQuestionnaireSerializer(questionnaire)
        return Response(result_serializer.data, status=status.HTTP_200_OK)


@extend_schema(
    tags=['Media Questionnaires'],
    summary='Пройти модерацию анкеты медиа (admin)',
    description='''
    PATCH: Пройти модерацию анкеты медиа (только для администраторов)
    
    Request body: пустой (только ID в URL)
    
    Правила:
    - Только администратор (is_staff=True) может пройти модерацию
    - Перед модерацией проверяется наличие поля phone
    - Если phone заполнен:
      - Создается User с phone и role='media' (если не существует)
      - Создается Report с start_date=сегодня и end_date=через 1 год (для Медиа)
    - После успешной модерации is_moderation=True
    ''',
    responses={
        200: MediaQuestionnaireSerializer,
        400: {'description': 'Ошибка валидации (phone не заполнен)'},
        403: {'description': 'Доступ запрещен. Только администраторы могут проходить модерацию'},
        404: {'description': 'Анкета не найдена'}
    }
)
class MediaQuestionnaireModerationView(views.APIView):
    """
    Пройти модерацию анкеты медиа (admin)
    PATCH /api/v1/accounts/media-questionnaires/{id}/moderation/
    """
    permission_classes = [permissions.IsAuthenticated]
    
    def get_object(self, pk):
        """Анкету olish"""
        try:
            return MediaQuestionnaire.objects.get(pk=pk)
        except MediaQuestionnaire.DoesNotExist:
            raise NotFound("Анкета не найдена")
    
    def patch(self, request, pk):
        """PATCH: Пройти модерацию"""
        # Проверка прав администратора
        if not (request.user.is_staff or request.user.role == 'admin'):
            raise PermissionDenied("Только администратор может проходить модерацию")
        
        questionnaire = self.get_object(pk)
        
        # Проверка phone
        if not questionnaire.phone:
            return Response(
                {'error': 'Телефон не заполнен. Необходимо заполнить телефон перед модерацией.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Создание или получение User
        # Очищаем phone от + и пробелов для поиска
        clean_phone = ''.join(filter(str.isdigit, questionnaire.phone))
        user, created = User.objects.get_or_create(
            phone=clean_phone,
            defaults={
                'role': 'media',
                'full_name': questionnaire.full_name,
                'is_phone_verified': True,
                'is_profile_completed': True,
            }
        )
        
        # Если пользователь уже существует, обновляем роль если нужно
        if not created and user.role != 'media':
            user.role = 'media'
            user.save()
        
        # Создание Report
        start_date = date.today()
        # Для Медиа - 1 год
        end_date = start_date + timedelta(days=365)
        
        Report.objects.create(
            user=user,
            start_date=start_date,
            end_date=end_date
        )
        
        # Установка is_moderation=True
        questionnaire.is_moderation = True
        questionnaire.save()
        
        result_serializer = MediaQuestionnaireSerializer(questionnaire)
        return Response(result_serializer.data, status=status.HTTP_200_OK)
