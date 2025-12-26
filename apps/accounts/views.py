from rest_framework import status, permissions, views
from rest_framework.response import Response
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework.exceptions import NotFound, PermissionDenied
from rest_framework.pagination import LimitOffsetPagination
from django.contrib.auth import get_user_model, models as auth_models
from django.db import models as django_models
from django.utils import timezone
from drf_spectacular.utils import extend_schema

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
        
        # Выберете город (city)
        city = request.query_params.get('city')
        if city:
            questionnaires = questionnaires.filter(city__icontains=city)
        
        # Выберете сегмент (segments - JSONField, contains check)
        segment = request.query_params.get('segment')
        if segment:
            questionnaires = questionnaires.filter(segments__contains=[segment])
        
        # Назначение недвижимости (property_purpose - services ichida)
        property_purpose = request.query_params.get('property_purpose')
        if property_purpose:
            # residential_designer yoki commercial_designer
            questionnaires = questionnaires.filter(services__contains=[property_purpose])
        
        # Площадь объекта (object_area - service_packages_description ichida search)
        object_area = request.query_params.get('object_area')
        if object_area:
            questionnaires = questionnaires.filter(service_packages_description__icontains=object_area)
        
        # Стоимость за м2 (cost_per_sqm - service_packages_description ichida search)
        cost_per_sqm = request.query_params.get('cost_per_sqm')
        if cost_per_sqm:
            questionnaires = questionnaires.filter(service_packages_description__icontains=cost_per_sqm)
        
        # Опыт работы (experience - welcome_message ichida search yoki additional_info)
        experience = request.query_params.get('experience')
        if experience:
            questionnaires = questionnaires.filter(
                django_models.Q(welcome_message__icontains=experience) | 
                django_models.Q(additional_info__icontains=experience)
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
    
    Возвращает:
    - categories: Основные категории (group choices) - Выберете основную котегорию
    - cities: Список уникальных городов из анкет - Выберете город
    - segments: Сегменты работы - Выберете сегмент
    - property_purposes: Назначение недвижимости (residential/commercial) - Назначение недвижимости
    ''',
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
        categories = [
            {'value': choice[0], 'label': choice[1]} 
            for choice in QUESTIONNAIRE_GROUP_CHOICES
        ]
        
        # Уникальные города - Выберете город
        # Staff userlar uchun barcha, oddiy userlar uchun faqat is_moderation=True
        is_staff = request.user.is_authenticated and request.user.is_staff
        if is_staff:
            cities_query = DesignerQuestionnaire.objects.filter(is_deleted=False)
        else:
            cities_query = DesignerQuestionnaire.objects.filter(is_moderation=True, is_deleted=False)
        cities = cities_query.exclude(
            city__isnull=True
        ).exclude(
            city=''
        ).values_list('city', flat=True).distinct().order_by('city')
        cities_list = [{'value': city, 'label': city} for city in cities]
        
        # Сегменты - Выберете сегмент
        segments = [
            {'value': choice[0], 'label': choice[1]} 
            for choice in DesignerQuestionnaire.SEGMENT_CHOICES
        ]
        
        # Назначение недвижимости - Назначение недвижимости
        property_purposes = [
            {'value': 'residential_designer', 'label': 'Жилая недвижимость'},
            {'value': 'commercial_designer', 'label': 'Коммерческая недвижимость'},
        ]
        
        return Response({
            'categories': categories,
            'cities': cities_list,
            'segments': segments,
            'property_purposes': property_purposes,
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
    
    def get(self, request):
        # Staff userlar uchun barcha questionnaire'lar, oddiy userlar uchun faqat is_moderation=True
        if request.user.is_authenticated and request.user.is_staff:
            questionnaires = RepairQuestionnaire.objects.filter(is_deleted=False)
        else:
            questionnaires = RepairQuestionnaire.objects.filter(is_moderation=True, is_deleted=False)
        
        # Filtering
        # Выберете основную котегорию (group)
        group = request.query_params.get('group')
        if group:
            questionnaires = questionnaires.filter(group=group)
        
        # Выберете город (representative_cities - JSONField, contains check)
        city = request.query_params.get('city')
        if city:
            # representative_cities - массив объектов, ищем по городу в каждом объекте
            questionnaires = questionnaires.filter(representative_cities__icontains=city)
        
        # Выберете сегмент (segments - JSONField, contains check)
        segment = request.query_params.get('segment')
        if segment:
            questionnaires = questionnaires.filter(segments__contains=[segment])
        
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
class RepairQuestionnaireFilterChoicesView(views.APIView):
    """
    Получить варианты для фильтров анкет ремонтных бригад / подрядчиков
    GET /api/v1/accounts/repair-questionnaires/filter-choices/
    """
    permission_classes = [permissions.AllowAny]
    
    def get(self, request):
        from .models import RepairQuestionnaire, QUESTIONNAIRE_GROUP_CHOICES
        
        # Основные категории (group) - Выберете основную котегорию
        categories = [
            {'value': choice[0], 'label': choice[1]} 
            for choice in QUESTIONNAIRE_GROUP_CHOICES
        ]
        
        # Уникальные города из representative_cities - Выберете город
        all_cities = set()
        # Staff userlar uchun barcha, oddiy userlar uchun faqat is_moderation=True
        is_staff = request.user.is_authenticated and request.user.is_staff
        if is_staff:
            repair_query = RepairQuestionnaire.objects.filter(is_deleted=False)
        else:
            repair_query = RepairQuestionnaire.objects.filter(is_moderation=True, is_deleted=False)
        for questionnaire in repair_query.exclude(representative_cities__isnull=True).exclude(representative_cities=[]):
            if isinstance(questionnaire.representative_cities, list):
                for city_data in questionnaire.representative_cities:
                    if isinstance(city_data, dict) and 'city' in city_data:
                        all_cities.add(city_data['city'])
                    elif isinstance(city_data, str):
                        all_cities.add(city_data)
        cities_list = [{'value': city, 'label': city} for city in sorted(all_cities)]
        
        # Сегменты - Выберете сегмент
        segments = [
            {'value': choice[0], 'label': choice[1]} 
            for choice in RepairQuestionnaire.SEGMENT_CHOICES
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
    
    def get(self, request):
        # Staff userlar uchun barcha questionnaire'lar, oddiy userlar uchun faqat is_moderation=True
        if request.user.is_authenticated and request.user.is_staff:
            questionnaires = SupplierQuestionnaire.objects.all()
        else:
            questionnaires = SupplierQuestionnaire.objects.filter(is_moderation=True, is_deleted=False)
        
        # Filtering
        # Выберете основную котегорию (group)
        group = request.query_params.get('group')
        if group:
            questionnaires = questionnaires.filter(group=group)
        
        # Выберете город (representative_cities - JSONField, contains check)
        city = request.query_params.get('city')
        if city:
            # representative_cities - массив объектов, ищем по городу в каждом объекте
            questionnaires = questionnaires.filter(representative_cities__icontains=city)
        
        # Выберите сегмент (segments - JSONField, contains check)
        segment = request.query_params.get('segment')
        if segment:
            questionnaires = questionnaires.filter(segments__contains=[segment])
        
        # Наличие НДС (vat_payment)
        vat_payment = request.query_params.get('vat_payment')
        if vat_payment:
            questionnaires = questionnaires.filter(vat_payment=vat_payment)
        
        # Карточки журналов (magazine_cards)
        magazine_cards = request.query_params.get('magazine_cards')
        if magazine_cards:
            questionnaires = questionnaires.filter(magazine_cards=magazine_cards)
        
        # Скорость исполнения (delivery_terms ichida search)
        execution_speed = request.query_params.get('execution_speed')
        if execution_speed:
            questionnaires = questionnaires.filter(delivery_terms__icontains=execution_speed)
        
        # Условия сотрудничества (cooperation_terms ichida search)
        cooperation_terms = request.query_params.get('cooperation_terms')
        if cooperation_terms:
            questionnaires = questionnaires.filter(cooperation_terms__icontains=cooperation_terms)
        
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
    
    Возвращает:
    - categories: Основные категории (group choices) - Выберете основную категорию
    - cities: Список уникальных городов из representative_cities - Выберете город
    - segments: Сегменты работы - Выберите сегмент
    - vat_payments: Наличие НДС - Наличие НДС
    - magazine_cards: Карточки журналов - Карточки журналов
    - business_forms: Формы бизнеса - Форма бизнеса
    ''',
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
        from .models import SupplierQuestionnaire, QUESTIONNAIRE_GROUP_CHOICES
        
        # Основные категории (group) - Выберете основную категорию
        categories = [
            {'value': choice[0], 'label': choice[1]} 
            for choice in QUESTIONNAIRE_GROUP_CHOICES
        ]
        
        # Уникальные города из representative_cities - Выберете город
        # Staff userlar uchun barcha, oddiy userlar uchun faqat is_moderation=True
        is_staff = request.user.is_authenticated and request.user.is_staff
        if is_staff:
            supplier_query = SupplierQuestionnaire.objects.all()
        else:
            supplier_query = SupplierQuestionnaire.objects.filter(is_moderation=True, is_deleted=False)
        all_cities = set()
        for questionnaire in supplier_query.exclude(representative_cities__isnull=True).exclude(representative_cities=[]):
            if isinstance(questionnaire.representative_cities, list):
                for city_data in questionnaire.representative_cities:
                    if isinstance(city_data, dict) and 'city' in city_data:
                        all_cities.add(city_data['city'])
                    elif isinstance(city_data, str):
                        all_cities.add(city_data)
        cities_list = [{'value': city, 'label': city} for city in sorted(all_cities)]
        
        # Сегменты - Выберите сегмент
        segments = [
            {'value': choice[0], 'label': choice[1]} 
            for choice in SupplierQuestionnaire.SEGMENT_CHOICES
        ]
        
        # Наличие НДС - Наличие НДС
        vat_payments = [
            {'value': choice[0], 'label': choice[1]} 
            for choice in SupplierQuestionnaire.VAT_PAYMENT_CHOICES
        ]
        
        # Карточки журналов - Карточки журналов
        magazine_cards = [
            {'value': choice[0], 'label': choice[1]} 
            for choice in SupplierQuestionnaire.MAGAZINE_CARD_CHOICES
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
