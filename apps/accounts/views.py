from rest_framework import status, permissions, views
from rest_framework.response import Response
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework.exceptions import NotFound, PermissionDenied
from rest_framework.pagination import LimitOffsetPagination
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from django.contrib.auth import get_user_model, models as auth_models
from django.db import models as django_models
from django.utils import timezone
from django.core.mail import send_mail
from django.conf import settings
from django.urls import reverse
from django.utils.crypto import get_random_string
from datetime import date, timedelta
import unicodedata
from drf_spectacular.utils import extend_schema, OpenApiParameter
from django.contrib.auth.models import Group

from .serializers import (
    AdminLoginSerializer,
    LoginSerializer,
    CheckPhoneSerializer,
    VerifyLoginCodeSerializer,
    NewPhoneLoginSerializer,
    ForgotPasswordSerializer,
    ResetPasswordSerializer,
    ChangePasswordSerializer,
    ChangePhoneNumberSerializer,
    VerifyPhoneChangeSerializer,
    VerifyPhoneCodeSerializer,
    UserProfileSerializer,
    UserPublicSerializer,
    DesignerQuestionnaireSerializer,
    RepairQuestionnaireSerializer,
    SupplierQuestionnaireSerializer,
    MediaQuestionnaireSerializer,
    QuestionnaireStatusUpdateSerializer,
    GroupSerializer,
)
from .models import (
    SMSVerificationCode,
    DesignerQuestionnaire,
    RepairQuestionnaire,
    SupplierQuestionnaire,
    MediaQuestionnaire,
    Report,
    QUESTIONNAIRE_GROUP_CHOICES,
)
from .utils import send_sms_via_smsaero, generate_sms_code

User = get_user_model()

# Filter: frontend value (display) yuboradi, bazada key saqlanadi — display -> key
SEGMENT_DISPLAY_TO_KEY = {str(label): key for key, label in DesignerQuestionnaire.SEGMENT_CHOICES}


def _choices_display_to_keys(values_list, choices_tuples):
    """Frontend value (display) yuboradi — key ga o'giramiz. choices_tuples = [(key, display), ...]"""
    if not values_list:
        return values_list
    display_to_key = {str(label): key for key, label in choices_tuples}
    return [display_to_key.get(v.strip(), v.strip()) for v in values_list]


def _normalize_category_label(s):
    """URL/frontend dan kelgan category ni lug'at bilan solishtirish uchun normalizatsiya (bo'shliq, Unicode)."""
    if not s or not isinstance(s, str):
        return s
    s = s.strip().replace('\xa0', ' ')
    return unicodedata.normalize('NFC', s)


def _q_categories_contains_any(variants):
    """categories (JSONField) da berilgan variantlardan biri bo'lsa match. Katta/kichik harf variantlari uchun."""
    if not variants:
        return Q(pk__in=[])  # hech narsa match qilmasin
    from django.db.models import Q
    q = Q()
    for v in variants:
        if v:
            q |= Q(categories__contains=[v])
    return q


# Password reset tokenlarni saqlash uchun dict (production'da cache yoki DB ishlatish kerak)
PASSWORD_RESET_TOKENS = {}


@extend_schema(
    tags=['Authentification'],
    summary='Проверка телефона и отправка SMS',
    description='''
    POST: Проверка телефона для входа. Работает только для зарегистрированных пользователей.
    
    Request body:
    - phone: Телефонный номер
    
    Если пользователь с таким телефоном не найден в системе — возвращается ошибка (SMS не отправляется).
    Если пользователь найден и is_phone_verified = False — отправляется SMS код.
    ''',
    request=CheckPhoneSerializer,
    responses={
        200: {'description': 'Успешная проверка'},
        400: {'description': 'Ошибка валидации'}
    }
)
class CheckPhoneView(views.APIView):
    """
    Telefon raqamini tekshirish va SMS yuborish
    POST /api/v1/accounts/login/check-phone/
    """
    permission_classes = [permissions.AllowAny]
    
    def post(self, request):
        serializer = CheckPhoneSerializer(data=request.data)
        if serializer.is_valid():
            phone = serializer.validated_data['phone']
            
            # Login faqat CustomUser da mavjud bo'lgan telefon uchun. Yangi user yaratilmaydi.
            try:
                user = User.objects.get(phone=phone)
            except User.DoesNotExist:
                return Response(
                    {'phone': ['Номер телефона не найден / Доступ не подтверждён']},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Agar is_phone_verified False bo'lsa, SMS yuborish (faqat mavjud user uchun)
            if not user.is_phone_verified:
                # SMS kod yaratish
                code = generate_sms_code()
                
                # Eski kodlarni bekor qilish
                SMSVerificationCode.objects.filter(
                    phone=phone,
                    is_used=False
                ).update(is_used=True)
                
                # Yangi kod yaratish
                sms_code = SMSVerificationCode.objects.create(
                    phone=phone,
                    code=code
                )
                
                # SMS yuborish
                clean_phone = ''.join(filter(str.isdigit, phone))
                is_uzbekistan = clean_phone.startswith('998')
                
                if not is_uzbekistan:
                    try:
                        send_sms_via_smsaero(phone, code)
                    except Exception:
                        pass  # SMS yuborishda xatolik bo'lsa ham davom etamiz
                
                return Response({
                    'phone': phone,
                    'is_phone_verified': False
                }, status=status.HTTP_200_OK)
            else:
                # Telefon allaqachon tasdiqlangan
                return Response({
                    'phone': phone,
                    'is_phone_verified': True
                }, status=status.HTTP_200_OK)
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@extend_schema(
    tags=['Authentification'],
    summary='Проверка SMS кода',
    description='''
    POST: Проверка SMS кода и подтверждение телефона
    
    Request body:
    - phone: Телефонный номер
    - code: SMS код
    
    После успешной проверки is_phone_verified = True.
    ''',
    request=VerifyLoginCodeSerializer,
    responses={
        200: {'description': 'Код подтвержден'},
        400: {'description': 'Ошибка валидации'}
    }
)
class VerifyLoginCodeView(views.APIView):
    """
    SMS kodni tekshirish va telefonni tasdiqlash
    POST /api/v1/accounts/login/verify-code/
    """
    permission_classes = [permissions.AllowAny]
    
    def post(self, request):
        serializer = VerifyLoginCodeSerializer(data=request.data)
        if serializer.is_valid():
            user = serializer.validated_data['user']
            
            return Response({
                'phone': user.phone,
                'is_phone_verified': user.is_phone_verified
            }, status=status.HTTP_200_OK)
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@extend_schema(
    tags=['Authentification'],
    summary='Вход на платформу (телефон + пароль)',
    description='''
    POST: Вход на платформу
    
    Request body:
    - phone: Телефонный номер
    - password: Пароль (может быть пустым для новых пользователей)
    
    Возвращает access_token и refresh_token.
    ''',
    request=NewPhoneLoginSerializer,
    responses={
        200: {'description': 'Успешный вход'},
        400: {'description': 'Ошибка валидации'}
    }
)
class LoginView(views.APIView):
    """
    Login - telefon + parol (parol bo'sh bo'lishi mumkin)
    POST /api/v1/accounts/login/
    """
    permission_classes = [permissions.AllowAny]
    
    def post(self, request):
        serializer = NewPhoneLoginSerializer(data=request.data)
        if serializer.is_valid():
            user = serializer.validated_data['user']
            
            # JWT token yaratish
            refresh = RefreshToken.for_user(user)
            
            return Response({
                'access_token': str(refresh.access_token),
                'refresh_token': str(refresh),
            }, status=status.HTTP_200_OK)
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@extend_schema(
    tags=['Authentification'],
    summary='Забыл пароль - отправка ссылки на email',
    description='''
    POST: Запрос на сброс пароля
    
    Request body:
    - email: Email адрес
    
    На указанный email отправляется ссылка для сброса пароля.
    ''',
    request=ForgotPasswordSerializer,
    responses={
        200: {'description': 'Ссылка для сброса пароля отправлена на email'},
        400: {'description': 'Ошибка валидации'}
    }
)
class ForgotPasswordView(views.APIView):
    """
    Parolni unutish - email orqali
    POST /api/v1/accounts/forgot-password/
    """
    permission_classes = [permissions.AllowAny]
    
    def post(self, request):
        serializer = ForgotPasswordSerializer(data=request.data)
        if serializer.is_valid():
            email = serializer.validated_data['email']
            
            try:
                user = User.objects.get(email=email)
            except User.DoesNotExist:
                # Xavfsizlik uchun har doim muvaffaqiyatli javob qaytaramiz
                return Response({
                    'message': 'Если пользователь с таким email существует, ссылка для сброса пароля отправлена.'
                }, status=status.HTTP_200_OK)
            
            # Token yaratish
            token = get_random_string(length=64)
            PASSWORD_RESET_TOKENS[token] = {
                'user_id': user.id,
                'expires_at': timezone.now() + timedelta(hours=24)
            }
            
            # Email yuborish
            # Frontend URL ni olish (agar mavjud bo'lsa)
            frontend_url = getattr(settings, 'FRONTEND_URL', None)
            if frontend_url:
                reset_url = f"{frontend_url}/reset-password?token={token}"
            else:
                reset_url = f"{request.scheme}://{request.get_host()}/api/v1/accounts/reset-password/?token={token}"
            
            email_sent = False
            email_error = None
            
            try:
                send_mail(
                    subject='Сброс пароля - Rating Profi',
                    message=f'Для сброса пароля перейдите по ссылке: {reset_url}',
                    from_email=settings.DEFAULT_FROM_EMAIL if hasattr(settings, 'DEFAULT_FROM_EMAIL') else 'noreply@ratingprofi.ru',
                    recipient_list=[email],
                    fail_silently=False,
                )
                email_sent = True
            except Exception as e:
                email_error = str(e)
                # DEBUG rejimida ham email yuborishga harakat qilamiz, lekin xatolik bo'lsa token qaytaramiz
            
            # DEBUG rejimida email yuborilgan yoki xatolik bo'lsa ham token qaytaramiz
            if settings.DEBUG:
                if email_sent:
                    return Response({
                        'message': 'Ссылка для сброса пароля отправлена на email.',
                    }, status=status.HTTP_200_OK)
                else:
                    return Response({
                        'message': f'Email не отправлен (ошибка: {email_error}).',
                    }, status=status.HTTP_200_OK)
            
            # Production rejimida
            if not email_sent:
                return Response({
                    'error': f'Ошибка отправки email: {email_error}'
                }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
            
            return Response({
                'message': 'Ссылка для сброса пароля отправлена на email'
            }, status=status.HTTP_200_OK)
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@extend_schema(
    tags=['Authentification'],
    summary='Сброс пароля по токену',
    description='''
    POST: Сброс пароля по токену из email ссылки
    
    Query параметры:
    - token: Токен из email ссылки (можно передать в URL или в body)
    
    Request body:
    - token: Токен из email ссылки (если не передан в URL)
    - new_password: Новый пароль (минимум 8 символов)
    ''',
    parameters=[
        OpenApiParameter(
            name='token',
            type=str,
            location=OpenApiParameter.QUERY,
            description='Токен из email ссылки',
            required=False,
        ),
    ],
    request=ResetPasswordSerializer,
    responses={
        200: {'description': 'Пароль успешно изменен'},
        400: {'description': 'Ошибка валидации (неверный или истекший токен)'}
    }
)
class ResetPasswordView(views.APIView):
    """
    Parolni tiklash - token orqali
    POST /api/v1/accounts/reset-password/?token=xxx
    yoki
    POST /api/v1/accounts/reset-password/
    {
        "token": "xxx",
        "new_password": "newpass123"
    }
    """
    permission_classes = [permissions.AllowAny]
    
    def post(self, request):
        # Token ni query parametrdan yoki body'dan olish
        token = request.query_params.get('token') or request.data.get('token')
        
        if not token:
            return Response({
                'error': 'Токен не указан'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Serializer data
        data = request.data.copy()
        if 'token' not in data:
            data['token'] = token
        
        serializer = ResetPasswordSerializer(data=data)
        if serializer.is_valid():
            token = serializer.validated_data['token']
            new_password = serializer.validated_data['new_password']
            
            # Token tekshirish
            if token not in PASSWORD_RESET_TOKENS:
                return Response({
                    'error': 'Неверный или истекший токен'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            token_data = PASSWORD_RESET_TOKENS[token]
            
            # Token muddati tekshirish
            if timezone.now() > token_data['expires_at']:
                del PASSWORD_RESET_TOKENS[token]
                return Response({
                    'error': 'Токен истек. Запросите новый.'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            # User topish va parolni o'zgartirish
            try:
                user = User.objects.get(id=token_data['user_id'])
            except User.DoesNotExist:
                del PASSWORD_RESET_TOKENS[token]
                return Response({
                    'error': 'Пользователь не найден'
                }, status=status.HTTP_404_NOT_FOUND)
            
            # Parolni o'zgartirish
            user.set_password(new_password)
            user.save()
            
            # Tokenni o'chirish
            del PASSWORD_RESET_TOKENS[token]
            
            return Response({
                'message': 'Пароль успешно изменен'
            }, status=status.HTTP_200_OK)
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@extend_schema(
    tags=['Authentification'],
    summary='Изменить пароль',
    description='''
    POST: Изменить пароль (требуется аутентификация)
    
    Request body:
    - old_password: Старый пароль
    - new_password: Новый пароль (минимум 8 символов)
    ''',
    request=ChangePasswordSerializer,
    responses={
        200: {'description': 'Пароль успешно изменен'},
        400: {'description': 'Ошибка валидации'}
    }
)
class ChangePasswordView(views.APIView):
    """
    Parolni o'zgartirish - eski + yangi parol
    POST /api/v1/accounts/change-password/
    """
    permission_classes = [permissions.IsAuthenticated]
    
    def post(self, request):
        serializer = ChangePasswordSerializer(data=request.data, context={'request': request})
        if serializer.is_valid():
            user = request.user
            new_password = serializer.validated_data['new_password']
            
            # Parolni o'zgartirish
            user.set_password(new_password)
            user.save()
            
            return Response({
                'message': 'Пароль успешно изменен'
            }, status=status.HTTP_200_OK)
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@extend_schema(
    tags=['Authentification'],
    summary='Изменить номер телефона - запрос SMS кода',
    description='''
    POST: Запрос на изменение номера телефона
    
    Request body:
    - new_phone: Новый телефонный номер
    
    На новый номер отправляется SMS код для подтверждения.
    ''',
    request=ChangePhoneNumberSerializer,
    responses={
        200: {'description': 'SMS код отправлен на новый номер'},
        400: {'description': 'Ошибка валидации'}
    }
)
class ChangePhoneNumberView(views.APIView):
    """
    Telefon raqamini o'zgartirish - yangi raqamga SMS kod yuborish
    POST /api/v1/accounts/change-phone/
    """
    permission_classes = [permissions.IsAuthenticated]
    
    def post(self, request):
        serializer = ChangePhoneNumberSerializer(data=request.data)
        if serializer.is_valid():
            new_phone = serializer.validated_data['new_phone']
            
            # SMS kod yuborish
            code = generate_sms_code()
            SMSVerificationCode.objects.filter(
                phone=new_phone,
                is_used=False
            ).update(is_used=True)
            
            sms_code = SMSVerificationCode.objects.create(
                phone=new_phone,
                code=code
            )
            
            # SMS yuborish
            clean_phone = ''.join(filter(str.isdigit, new_phone))
            is_uzbekistan = clean_phone.startswith('998')
            
            response_data = {
                'message': 'SMS код отправлен на новый номер телефона',
                'new_phone': new_phone
            }
            
            if not is_uzbekistan:
                try:
                    send_sms_via_smsaero(new_phone, code)
                except Exception:
                    pass
            else:
                response_data['code'] = sms_code.code
                response_data['note'] = 'Для узбекских номеров код отправлен в ответе'
            
            return Response(response_data, status=status.HTTP_200_OK)
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@extend_schema(
    tags=['Authentification'],
    summary='Подтверждение изменения номера телефона',
    description='''
    POST: Подтверждение изменения номера телефона SMS кодом
    
    Request body:
    - new_phone: Новый телефонный номер
    - code: SMS код
    
    После подтверждения номер телефона изменяется.
    ''',
    request=VerifyPhoneChangeSerializer,
    responses={
        200: {'description': 'Номер телефона успешно изменен'},
        400: {'description': 'Ошибка валидации'}
    }
)
class VerifyPhoneChangeView(views.APIView):
    """
    Telefon raqamini o'zgartirish - SMS kodni tasdiqlash
    POST /api/v1/accounts/verify-phone-change/
    """
    permission_classes = [permissions.IsAuthenticated]
    
    def post(self, request):
        serializer = VerifyPhoneChangeSerializer(data=request.data)
        if serializer.is_valid():
            new_phone = serializer.validated_data['new_phone']
            code = serializer.validated_data['code']
            
            # SMS kodni tekshirish
            clean_phone = ''.join(filter(str.isdigit, new_phone))
            
            try:
                sms_code = SMSVerificationCode.objects.get(
                    phone=clean_phone,
                    code=code,
                    is_used=False
                )
            except SMSVerificationCode.DoesNotExist:
                return Response({
                    'error': 'Неверный код'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            # Kod amal qiladimi tekshirish
            if not sms_code.is_valid():
                return Response({
                    'error': 'Срок действия кода истек'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            # Kodni ishlatilgan deb belgilash
            sms_code.is_used = True
            sms_code.save()
            
            # Telefon raqamini o'zgartirish
            user = request.user
            old_phone = user.phone
            user.phone = clean_phone
            user.username = clean_phone  # username ham o'zgartirish kerak
            user.is_phone_verified = True
            user.save()
            
            return Response({
                'message': 'Номер телефона успешно изменен',
                'old_phone': old_phone,
                'new_phone': clean_phone
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
    - group: Фильтр по группе (Дизайн, Ремонт, Поставщик, Медиа) - русские названия
    - city: Фильтр по городу
    - search: Поиск по имени, описанию, названию компании
    - is_active_profile: Фильтр по активным профилям (true/false)
    - ordering: Сортировка (created_at, -created_at, full_name, -full_name)
    
    По умолчанию возвращаются только пользователи с is_active_profile=True
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
            name='city',
            type=str,
            location=OpenApiParameter.QUERY,
            description='Фильтр по городу (частичное совпадение)',
            required=False,
        ),
        OpenApiParameter(
            name='search',
            type=str,
            location=OpenApiParameter.QUERY,
            description='Поиск по имени, описанию, названию компании (частичное совпадение)',
            required=False,
        ),
        OpenApiParameter(
            name='is_active_profile',
            type=bool,
            location=OpenApiParameter.QUERY,
            description='Фильтр по активным профилям (true/false). По умолчанию: true',
            required=False,
        ),
        OpenApiParameter(
            name='ordering',
            type=str,
            location=OpenApiParameter.QUERY,
            description='Сортировка. Доступные значения: created_at, -created_at, full_name, -full_name. По умолчанию: -created_at',
            required=False,
        ),
    ],
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
        allowed_roles = ['Дизайн', 'Ремонт', 'Поставщик', 'Медиа']
        queryset = User.objects.filter(groups__name__in=allowed_roles).distinct()
        
        # Фильтр по is_active_profile (если указан)
        is_active_profile = self.request.query_params.get('is_active_profile')
        if is_active_profile is not None:
            if is_active_profile.lower() == 'true':
                queryset = queryset.filter(is_active_profile=True)
            elif is_active_profile.lower() == 'false':
                queryset = queryset.filter(is_active_profile=False)
        
        # Фильтр по группе
        group_filter = self.request.query_params.get('group')
        if group_filter and group_filter in allowed_roles:
            queryset = queryset.filter(groups__name=group_filter).distinct()
        
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
            serializer = UserPublicSerializer(page, many=True, context={'request': request})
            return paginator.get_paginated_response(serializer.data)
        
        serializer = UserPublicSerializer(queryset, many=True, context={'request': request})
        return Response(serializer.data, status=status.HTTP_200_OK)


@extend_schema(
    tags=['Accounts'],
    summary='Профиль пользователя',
    description='''
    GET: Получить профиль текущего пользователя
    PUT: Обновить профиль текущего пользователя
    
    Поля:
    - first_name: Имя
    - last_name: Фамилия
    - phone: Телефон (только для чтения)
    - email: Email
    - photo: Фото (ImageField, multipart/form-data)
    ''',
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
        summary='Обновить профиль',
        description='''
        Обновить профиль пользователя.
        
        Для загрузки фото используйте multipart/form-data.
        ''',
        request={
            'multipart/form-data': UserProfileSerializer,
            'application/json': UserProfileSerializer,
        },
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
    
    Пагинация:
    - limit: Количество результатов на странице (по умолчанию: 20, максимум: 100)
    - offset: Смещение для пагинации (по умолчанию: 0)
    ''',
    parameters=[
        OpenApiParameter(
            name='limit',
            type=int,
            location=OpenApiParameter.QUERY,
            description='Количество результатов на странице (по умолчанию: 20, максимум: 100)',
            required=False,
        ),
        OpenApiParameter(
            name='id',
            type=int,
            location=OpenApiParameter.QUERY,
            description='Фильтр по ID анкеты',
            required=False,
        ),
        OpenApiParameter(
            name='phone',
            type=str,
            location=OpenApiParameter.QUERY,
            description='Фильтр по телефону (поиск по частичному совпадению)',
            required=False,
        ),
        OpenApiParameter(
            name='organization_name',
            type=str,
            location=OpenApiParameter.QUERY,
            description='Фильтр по названию организации / бренда (brand_name, поиск по частичному совпадению)',
            required=False,
        ),
        OpenApiParameter(
            name='full_name',
            type=str,
            location=OpenApiParameter.QUERY,
            description='Фильтр по ФИО человека (full_name, поиск по частичному совпадению)',
            required=False,
        ),
        OpenApiParameter(
            name='offset',
            type=int,
            location=OpenApiParameter.QUERY,
            description='Смещение для пагинации (по умолчанию: 0)',
            required=False,
        ),
    ],
    responses={
        200: {'description': 'Список всех удаленных анкет с пагинацией'},
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
        
        # Фильтры (ID, phone, organization_name, full_name)
        # Faqat DesignerQuestionnaire, RepairQuestionnaire, SupplierQuestionnaire bo'yicha filter
        filter_id = request.query_params.get('id')
        filter_phone = request.query_params.get('phone', '').strip()
        filter_org_name = request.query_params.get('organization_name', '').strip()
        filter_full_name = request.query_params.get('full_name', '').strip()
        
        if filter_id or filter_phone or filter_org_name or filter_full_name:
            filtered_data = []
            for item in combined_data:
                # Faqat DesignerQuestionnaire, RepairQuestionnaire, SupplierQuestionnaire ni filter qilamiz
                request_name = item.get('request_name', '')
                if request_name not in ['DesignerQuestionnaire', 'RepairQuestionnaire', 'SupplierQuestionnaire']:
                    # MediaQuestionnaire ni o'tkazib yuboramiz (filter qilmaymiz)
                    filtered_data.append(item)
                    continue
                
                # ID filter
                if filter_id:
                    try:
                        if item.get('id') != int(filter_id):
                            continue
                    except (ValueError, TypeError):
                        continue
                
                # Phone filter
                if filter_phone:
                    phone = item.get('phone', '') or ''
                    if filter_phone.lower() not in phone.lower():
                        continue
                
                # Organization name filter (brand_name)
                if filter_org_name:
                    brand_name = item.get('brand_name', '') or ''
                    full_name_check = item.get('full_name', '') or ''
                    # brand_name yoki full_name da qidirish
                    if (filter_org_name.lower() not in brand_name.lower() and 
                        filter_org_name.lower() not in full_name_check.lower()):
                        continue
                
                # Full name filter
                if filter_full_name:
                    full_name = item.get('full_name', '') or ''
                    if filter_full_name.lower() not in full_name.lower():
                        continue
                
                filtered_data.append(item)
            combined_data = filtered_data
        
        # Сортируем по дате создания (новые первыми)
        combined_data.sort(key=lambda x: x.get('created_at', ''), reverse=True)
        
        # Pagination
        paginator = LimitOffsetPagination()
        paginator.default_limit = 20
        paginator.max_limit = 100
        
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
    
    Фильтры (применяются только к DesignerQuestionnaire, RepairQuestionnaire, SupplierQuestionnaire):
    - id: Фильтр по ID анкеты
    - phone: Фильтр по телефону (поиск по частичному совпадению)
    - organization_name: Фильтр по названию организации / бренда (brand_name, поиск по частичному совпадению)
    - full_name: Фильтр по ФИО человека (full_name, поиск по частичному совпадению)
    
    Пагинация:
    - limit: Количество результатов на странице (по умолчанию: 20, максимум: 100)
    - offset: Смещение для пагинации (по умолчанию: 0)
    ''',
    parameters=[
        OpenApiParameter(
            name='id',
            type=int,
            location=OpenApiParameter.QUERY,
            description='Фильтр по ID анкеты',
            required=False,
        ),
        OpenApiParameter(
            name='phone',
            type=str,
            location=OpenApiParameter.QUERY,
            description='Фильтр по телефону (поиск по частичному совпадению)',
            required=False,
        ),
        OpenApiParameter(
            name='organization_name',
            type=str,
            location=OpenApiParameter.QUERY,
            description='Фильтр по названию организации / бренда (brand_name, поиск по частичному совпадению)',
            required=False,
        ),
        OpenApiParameter(
            name='full_name',
            type=str,
            location=OpenApiParameter.QUERY,
            description='Фильтр по ФИО человека (full_name, поиск по частичному совпадению)',
            required=False,
        ),
        OpenApiParameter(
            name='limit',
            type=int,
            location=OpenApiParameter.QUERY,
            description='Количество результатов на странице (по умолчанию: 20, максимум: 100)',
            required=False,
        ),
        OpenApiParameter(
            name='offset',
            type=int,
            location=OpenApiParameter.QUERY,
            description='Смещение для пагинации (по умолчанию: 0)',
            required=False,
        ),
    ],
    responses={
        200: {'description': 'Список всех анкет с пагинацией'}
    }
)
class QuestionnaireListView(views.APIView):
    """
    Общий список всех анкет (дизайнеров, ремонтных бригад/подрядчиков, поставщиков/салонов/фабрик и медиа пространств/интерьерных журналов)
    GET /api/v1/accounts/questionnaires/all/
    """
    permission_classes = [permissions.IsAuthenticated]
    
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
        
        # Фильтры (ID, phone, organization_name, full_name)
        # Faqat DesignerQuestionnaire, RepairQuestionnaire, SupplierQuestionnaire bo'yicha filter
        filter_id = request.query_params.get('id')
        filter_phone = request.query_params.get('phone', '').strip()
        filter_org_name = request.query_params.get('organization_name', '').strip()
        filter_full_name = request.query_params.get('full_name', '').strip()
        
        if filter_id or filter_phone or filter_org_name or filter_full_name:
            filtered_data = []
            for item in combined_data:
                # Faqat DesignerQuestionnaire, RepairQuestionnaire, SupplierQuestionnaire ni filter qilamiz
                request_name = item.get('request_name', '')
                if request_name not in ['DesignerQuestionnaire', 'RepairQuestionnaire', 'SupplierQuestionnaire']:
                    # MediaQuestionnaire ni o'tkazib yuboramiz (filter qilmaymiz)
                    filtered_data.append(item)
                    continue
                
                # ID filter
                if filter_id:
                    try:
                        if item.get('id') != int(filter_id):
                            continue
                    except (ValueError, TypeError):
                        continue
                
                # Phone filter
                if filter_phone:
                    phone = item.get('phone', '') or ''
                    if filter_phone.lower() not in phone.lower():
                        continue
                
                # Organization name filter (brand_name)
                if filter_org_name:
                    brand_name = item.get('brand_name', '') or ''
                    full_name_check = item.get('full_name', '') or ''
                    # brand_name yoki full_name da qidirish
                    if (filter_org_name.lower() not in brand_name.lower() and 
                        filter_org_name.lower() not in full_name_check.lower()):
                        continue
                
                # Full name filter
                if filter_full_name:
                    full_name = item.get('full_name', '') or ''
                    if filter_full_name.lower() not in full_name.lower():
                        continue
                
                filtered_data.append(item)
            combined_data = filtered_data
        
        # Сортируем по дате создания (новые первыми)
        combined_data.sort(key=lambda x: x.get('created_at', ''), reverse=True)
        
        # Pagination
        paginator = LimitOffsetPagination()
        paginator.default_limit = 20
        paginator.max_limit = 100
        
        page = paginator.paginate_queryset(combined_data, request)
        if page is not None:
            return paginator.get_paginated_response(page)
        
        return Response(combined_data, status=status.HTTP_200_OK)


@extend_schema(
    tags=['All Questionnaires'],
    summary='Мои анкеты (по телефону и email текущего пользователя)',
    description='''
    GET: Получить объединенный список всех анкет (дизайнеров, ремонтных бригад/подрядчиков, поставщиков/салонов/фабрик и медиа пространств/интерьерных журналов),
    которые принадлежат текущему авторизованному пользователю по его телефону и/или email.
    
    Фильтрация происходит автоматически по:
    - phone: телефону текущего пользователя (request.user.phone)
    - email: email текущего пользователя (request.user.email)
    
    Если у пользователя указаны оба поля (phone и email), попадают анкеты, где совпадает хотя бы одно из полей.
    
    Пагинация:
    - limit: Количество результатов на странице (по умолчанию: 20, максимум: 100)
    - offset: Смещение для пагинации (по умолчанию: 0)
    
    Ответ: такой же формат, как у /questionnaires/all/
    ''',
    parameters=[
        OpenApiParameter(
            name='limit',
            type=int,
            location=OpenApiParameter.QUERY,
            description='Количество результатов на странице (по умолчанию: 20, максимум: 100)',
            required=False,
        ),
        OpenApiParameter(
            name='offset',
            type=int,
            location=OpenApiParameter.QUERY,
            description='Смещение для пагинации (по умолчанию: 0)',
            required=False,
        ),
    ],
    responses={
        200: {'description': 'Список анкет текущего пользователя'},
        401: {'description': 'Требуется авторизация'}
    }
)
class MyQuestionnairesView(views.APIView):
    """
    Мои анкеты - список всех анкет текущего пользователя по его телефону и/или email
    GET /api/v1/accounts/questionnaires/my-questionnaires/
    """
    permission_classes = [permissions.IsAuthenticated]
    
    def get(self, request):
        user = request.user
        phone = (user.phone or '').strip()
        email = (user.email or '').strip()
        
        if not phone and not email:
            return Response(
                {'detail': 'У пользователя не указан ни телефон, ни email'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        from django.db.models import Q
        
        contact_q = Q()
        if phone:
            # Telefon raqamini tozalash (faqat raqamlar)
            clean_phone = ''.join(filter(str.isdigit, phone))
            if clean_phone:
                contact_q |= Q(phone__icontains=clean_phone)
        if email:
            contact_q |= Q(email__iexact=email)
        
        # Всегда берем только не удаленные анкеты, без учета модерации,
        # чтобы пользователь видел свои заявки независимо от статуса.
        designer_qs = DesignerQuestionnaire.objects.filter(is_deleted=False).filter(contact_q)
        repair_qs = RepairQuestionnaire.objects.filter(is_deleted=False).filter(contact_q)
        supplier_qs = SupplierQuestionnaire.objects.filter(is_deleted=False).filter(contact_q)
        media_qs = MediaQuestionnaire.objects.filter(is_deleted=False).filter(contact_q)
        
        designer_serializer = DesignerQuestionnaireSerializer(designer_qs, many=True, context={'request': request})
        repair_serializer = RepairQuestionnaireSerializer(repair_qs, many=True, context={'request': request})
        supplier_serializer = SupplierQuestionnaireSerializer(supplier_qs, many=True, context={'request': request})
        media_serializer = MediaQuestionnaireSerializer(media_qs, many=True, context={'request': request})
        
        combined_data = (
            list(designer_serializer.data) +
            list(repair_serializer.data) +
            list(supplier_serializer.data) +
            list(media_serializer.data)
        )
        
        # Сортируем по дате создания (новые первыми)
        combined_data.sort(key=lambda x: x.get('created_at', ''), reverse=True)
        
        # Pagination
        paginator = LimitOffsetPagination()
        paginator.default_limit = 20
        paginator.max_limit = 100
        
        page = paginator.paginate_queryset(combined_data, request)
        if page is not None:
            return paginator.get_paginated_response(page)
        
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
      * designer_horika - Дизайнер HoReCa
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
    - categories: Категории (массив, необязательное). Варианты: residential_designer, commercial_designer, decorator, home_stager, architect, landscape_designer, light_designer
    - purpose_of_property: Назначение недвижимости (массив, необязательное). Варианты: permanent_residence, for_rent, commercial, horeca
    - area_of_object: Площадь объекта (текст: до 10 м2, до 40 м 2, до 80 м 2, дома)
    - cost_per_m2: Стоимость за м² (текст: До 1500 р, до 2500р, до 4000 р, свыше 4000 р)
    - experience: Опыт работы (текст: Новичок, До 2 лет, 2-5 лет, 5-10 лет, Свыше 10 лет)
    
    GET возвращает те же поля; PUT принимает те же поля для обновления.
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
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    
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
                name='category',
                type=str,
                location=OpenApiParameter.QUERY,
                description='Синоним categories. Категории (label из filter-choices: Дизайнер жилых помещений, Декоратор и т.д.). Несколько через запятую.',
                required=False,
            ),
            OpenApiParameter(
                name='categories',
                type=str,
                location=OpenApiParameter.QUERY,
                description='Категории (FilterChoices categories). Несколько через запятую. Фильтр по полю categories (JSONField)',
                required=False,
            ),
            OpenApiParameter(
                name='city',
                type=str,
                location=OpenApiParameter.QUERY,
                description='Город(а). Несколько через запятую = AND. Только анкеты, у которых есть ВСЕ выбранные города (city или work_cities). Значения из filter-choices/cities.',
                required=False,
            ),
            OpenApiParameter(
                name='segment',
                type=str,
                location=OpenApiParameter.QUERY,
                description='Сегмент: key (horeca, business, comfort, premium, medium, economy) или value (HoReCa, Бизнес, Комфорт и т.д.). Несколько через запятую.',
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
        # Filtering (frontend value yuboradi — key ga o'giramiz)
        # Выберете основную котегорию (group) — несколько через запятую, OR
        group = request.query_params.get('group')
        if group:
            groups_list = [g.strip() for g in group.split(',') if g.strip()]
            groups_list = _choices_display_to_keys(groups_list, QUESTIONNAIRE_GROUP_CHOICES)
            if groups_list:
                from django.db.models import Q
                group_q = Q()
                for g in groups_list:
                    group_q |= Q(group=g)
                questionnaires = questionnaires.filter(group_q)
        
        # Категории (categories) — frontend value, key ga o'giramiz. category = синоним categories
        categories_param = request.query_params.get('categories') or request.query_params.get('category')
        if categories_param:
            categories_list = [c.strip() for c in categories_param.split(',')]
            categories_list = _choices_display_to_keys(categories_list, DesignerQuestionnaire.CATEGORY_CHOICES)
            from django.db.models import Q
            cat_q = Q()
            for cat in categories_list:
                cat_q |= Q(categories__contains=[cat])
            if cat_q:
                questionnaires = questionnaires.filter(cat_q)
        
        # Выберете город (city). Несколько через запятую = AND: только те, у кого есть ВСЕ выбранные города
        city = request.query_params.get('city')
        if city:
            cities_list = [c.strip() for c in city.split(',') if c.strip()]
            if cities_list:
                from django.db.models import Q
                # Специальные значения: если только "По всей России" — не фильтруем
                normal_cities = [c for c in cities_list if c not in ("По всей России", "ЮФО", "Любые города онлайн")]
                if "По всей России" in cities_list and not normal_cities:
                    pass
                elif "ЮФО" in cities_list and not normal_cities:
                    yfo_cities = ['Ростов-на-Дону', 'Краснодар', 'Сочи', 'Ставрополь', 'Волгоград', 'Астрахань']
                    city_q = Q()
                    for yfo_city in yfo_cities:
                        city_q |= Q(city__icontains=yfo_city) | Q(work_cities__icontains=yfo_city)
                    if city_q:
                        questionnaires = questionnaires.filter(city_q)
                elif "Любые города онлайн" in cities_list and not normal_cities:
                    questionnaires = questionnaires.filter(
                        django_models.Q(cooperation_terms__icontains='онлайн') |
                        django_models.Q(cooperation_terms__icontains='online')
                    )
                else:
                    # AND: анкета должна содержать каждый из выбранных городов (city или work_cities)
                    for city_item in normal_cities:
                        questionnaires = questionnaires.filter(
                            Q(city__icontains=city_item) | Q(work_cities__icontains=city_item)
                        )
        
        # Сегмент — frontend value (HoReCa), key (horeca) ga o'giramiz
        segment = request.query_params.get('segment')
        if segment:
            segments_list = [s.strip() for s in segment.split(',')]
            segments_list = _choices_display_to_keys(segments_list, DesignerQuestionnaire.SEGMENT_CHOICES)
            from django.db.models import Q
            segment_q = Q()
            for seg in segments_list:
                segment_q |= Q(segments__contains=[seg])
            if segment_q:
                questionnaires = questionnaires.filter(segment_q)
        
        # Назначение недвижимости (property_purpose) — frontend value, key ga o'giramiz
        property_purpose = request.query_params.get('property_purpose')
        if property_purpose:
            purposes_list = [p.strip() for p in property_purpose.split(',')]
            purposes_list = _choices_display_to_keys(purposes_list, DesignerQuestionnaire.PURPOSE_OF_PROPERTY_CHOICES)
            from django.db.models import Q
            purpose_q = Q()
            for p in purposes_list:
                if p != 'not_important':
                    purpose_q |= Q(purpose_of_property__contains=[p])
            if purpose_q:
                questionnaires = questionnaires.filter(purpose_q)
        
        # Площадь объекта (object_area → area_of_object CharField, текстовие варианты)
        object_area = request.query_params.get('object_area')
        if object_area:
            areas_list = [a.strip() for a in object_area.split(',')]
            from django.db.models import Q
            area_q = Q()
            area_values = ['до 10 м2', 'до 40 м 2', 'до 80 м 2', 'дома']
            for area in areas_list:
                if area == 'not_important':
                    continue
                if area in area_values:
                    area_q |= Q(area_of_object=area)
                else:
                    area_q |= Q(service_packages_description__icontains=area)
            if area_q:
                questionnaires = questionnaires.filter(area_q)
        
        # Стоимость за м2 (cost_per_sqm) — несколько через запятую, OR
        cost_per_sqm = request.query_params.get('cost_per_sqm')
        if cost_per_sqm:
            cost_list = [c.strip() for c in cost_per_sqm.split(',') if c.strip()]
            cost_values = ['До 1500 р', 'до 2500р', 'до 4000 р', 'свыше 4000 р']
            from django.db.models import Q
            cost_q = Q()
            for c in cost_list:
                if c == 'not_important':
                    continue
                if c in cost_values:
                    cost_q |= Q(cost_per_m2=c)
                else:
                    cost_q |= Q(service_packages_description__icontains=c)
            if cost_q:
                questionnaires = questionnaires.filter(cost_q)
        
        # Опыт работы (experience) — несколько через запятую, OR
        experience = request.query_params.get('experience')
        if experience:
            exp_list = [e.strip() for e in experience.split(',') if e.strip()]
            exp_values = ['Новичок', 'До 2 лет', '2-5 лет', '5-10 лет', 'Свыше 10 лет']
            from django.db.models import Q
            exp_q = Q()
            for e in exp_list:
                if e == 'not_important':
                    continue
                if e in exp_values:
                    exp_q |= Q(experience=e)
                else:
                    exp_q |= Q(welcome_message__icontains=e) | Q(additional_info__icontains=e)
            if exp_q:
                questionnaires = questionnaires.filter(exp_q)
        
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
        serializer = DesignerQuestionnaireSerializer(paginated_questionnaires, many=True, context={'request': request})
        
        return paginator.get_paginated_response(serializer.data)
    
    def post(self, request):
        # Phone tekshirish - bir xil phone bilan ikkinchi marta create qilish mumkin emas
        phone = request.data.get('phone')
        if phone:
            from .models import DesignerQuestionnaire
            # Agar allaqachon shu phone bilan questionnaire yaratilgan bo'lsa
            existing_questionnaire = DesignerQuestionnaire.objects.filter(
                phone=phone,
                is_deleted=False
            ).first()
            
            if existing_questionnaire:
                return Response({
                    'phone': ['Анкета с таким номером телефона уже существует. Один номер телефона может быть использован только один раз.']
                }, status=status.HTTP_400_BAD_REQUEST)
        
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
    - cities: Уникальные города из анкет выбранной категории (только из DesignerQuestionnaire) - Выберете город
    - segments: Сегменты работы (можно выбрать несколько) - Выберете сегмент
      * Эконом (economy)
      * Комфорт (comfort)
      * Бизнесс (business)
      * Примиум (premium)
      * HoReCa (horeca)
    - property_purposes: Назначение недвижимости - Назначение недвижимости
      * Для постоянного проживания (permanent_residence)
      * Для сдачи (for_rent)
      * Коммерческая недвижимость (commercial)
      * HoReCa (horeca)
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
        # Barcha shaharlar (is_deleted=False faqat)
        cities_query = DesignerQuestionnaire.objects.filter(is_deleted=False)
        
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
        # Faqat questionnaire modellarida mavjud shaharlar (maxsus variantlar olib tashlandi)
        
        # Сегменты - Выберете сегмент (ko'p tanlash mumkin)
        # Model'dan olinadi: economy, comfort, business, premium, horeca, medium
        segments = [
            {'value': choice[0], 'label': choice[1].capitalize()} 
            for choice in DesignerQuestionnaire.SEGMENT_CHOICES
        ]
        
        # Назначение недвижимости - Назначение недвижимости
        property_purposes = [
            {'value': 'permanent_residence', 'label': 'Для постоянного проживания'},
            {'value': 'for_rent', 'label': 'Для сдачи'},
            {'value': 'commercial', 'label': 'Коммерческая недвижимость'},
            {'value': 'horeca', 'label': 'HoReCa'},
        ]
        
        # Площадь объекта — текстовие варианты (value = то, что хранится в БД и принимает PUT)
        object_areas = [
            {'value': 'до 10 м2', 'label': 'до 10 м2'},
            {'value': 'до 40 м 2', 'label': 'до 40 м 2'},
            {'value': 'до 80 м 2', 'label': 'до 80 м 2'},
            {'value': 'дома', 'label': 'дома'},
            {'value': 'not_important', 'label': 'Не важно'},
        ]
        
        # Стоимость за м2 — текстовие варианты
        cost_per_sqm_options = [
            {'value': 'До 1500 р', 'label': 'До 1500 р'},
            {'value': 'до 2500р', 'label': 'до 2500р'},
            {'value': 'до 4000 р', 'label': 'до 4000 р'},
            {'value': 'свыше 4000 р', 'label': 'свыше 4000 р'},
            {'value': 'not_important', 'label': 'Не важно'},
        ]
        
        # Опыт работы — текстовие варианты
        experience_options = [
            {'value': 'Новичок', 'label': 'Новичок'},
            {'value': 'До 2 лет', 'label': 'До 2 лет'},
            {'value': '2-5 лет', 'label': '2-5 лет'},
            {'value': '5-10 лет', 'label': '5-10 лет'},
            {'value': 'Свыше 10 лет', 'label': 'Свыше 10 лет'},
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
    - phone: Номер телефона (необязательное)
    - birth_date: Дата рождения (формат: YYYY-MM-DD)
    - email: E-mail
    - city: Город проживания
    - services: Услуги (массив). Варианты:
      * author_supervision - Авторский надзор
      * architecture - Архитектура
      * decorator - Декоратор
      * designer_horika - Дизайнер HoReCa
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
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    
    def get_object(self, pk, request=None):
        try:
            # Staff userlar uchun barcha, oddiy userlar uchun faqat is_moderation=True
            is_staff = request and request.user.is_authenticated and request.user.is_staff
            if is_staff:
                return DesignerQuestionnaire.objects.filter(is_deleted=False).get(pk=pk)
            else:
                return DesignerQuestionnaire.objects.filter(is_moderation=True, is_deleted=False).get(pk=pk)
        except DesignerQuestionnaire.DoesNotExist:
            raise NotFound("Анкета не найдена")
    
    def get(self, request, pk):
        questionnaire = self.get_object(pk, request)
        serializer = DesignerQuestionnaireSerializer(questionnaire, context={'request': request})
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
    tags=['Designer Questionnaires'],
    summary='Архивировать анкету дизайнера',
    description='''
    PATCH: Архивировать анкету дизайнера (is_deleted=True)
    
    Требуется авторизация и права администратора (is_staff=True)
    ''',
    responses={
        200: {'description': 'Анкета успешно архивирована'},
        403: {'description': 'Доступ запрещен. Только администраторы могут архивировать анкеты'},
        404: {'description': 'Анкета не найдена'}
    }
)
class DesignerQuestionnaireArchiveView(views.APIView):
    """
    Архивировать анкету дизайнера
    PATCH /api/v1/accounts/questionnaires/{id}/archive/
    """
    permission_classes = [permissions.IsAuthenticated]
    
    def patch(self, request, pk):
        if not request.user.is_staff:
            raise PermissionDenied("Только администратор может архивировать анкету")
        try:
            questionnaire = DesignerQuestionnaire.objects.get(pk=pk)
        except DesignerQuestionnaire.DoesNotExist:
            raise NotFound("Анкета не найдена")
        
        questionnaire.is_deleted = True
        questionnaire.save()
        serializer = DesignerQuestionnaireSerializer(questionnaire, context={'request': request})
        return Response(serializer.data, status=status.HTTP_200_OK)


@extend_schema(
    tags=['Designer Questionnaires'],
    summary='Восстановить анкету дизайнера из архива',
    description='''
    PATCH: Восстановить анкету дизайнера из архива (is_deleted=False)
    
    Требуется авторизация и права администратора (is_staff=True)
    ''',
    responses={
        200: {'description': 'Анкета успешно восстановлена из архива'},
        403: {'description': 'Доступ запрещен. Только администраторы могут восстанавливать анкеты'},
        404: {'description': 'Анкета не найдена'}
    }
)
class DesignerQuestionnaireRestoreView(views.APIView):
    """
    Восстановить анкету дизайнера из архива
    PATCH /api/v1/accounts/questionnaires/{id}/restore/
    """
    permission_classes = [permissions.IsAuthenticated]
    
    def patch(self, request, pk):
        if not request.user.is_staff:
            raise PermissionDenied("Только администратор может восстанавливать анкету")
        try:
            questionnaire = DesignerQuestionnaire.objects.get(pk=pk)
        except DesignerQuestionnaire.DoesNotExist:
            raise NotFound("Анкета не найдена")
        
        questionnaire.is_deleted = False
        questionnaire.save()
        serializer = DesignerQuestionnaireSerializer(questionnaire, context={'request': request})
        return Response(serializer.data, status=status.HTTP_200_OK)


@extend_schema(
    tags=['Designer Questionnaires'],
    summary='Удалить анкету дизайнера (полное удаление)',
    description='''
    DELETE: Полностью удалить анкету дизайнера из базы данных
    
    ⚠️ ВНИМАНИЕ: Это действие необратимо! Анкета будет полностью удалена из базы данных.
    
    Требуется:
    - Авторизация и права администратора (is_staff=True)
    - Подтверждение действия через параметр confirm=true в query string или в теле запроса
    
    Пример запроса:
    DELETE /api/v1/accounts/questionnaires/{id}/delete/?confirm=true
    или
    DELETE /api/v1/accounts/questionnaires/{id}/delete/
    Body: {"confirm": true}
    ''',
    parameters=[
        OpenApiParameter(
            name='confirm',
            type=bool,
            location=OpenApiParameter.QUERY,
            description='Подтверждение удаления (обязательно: true)',
            required=True,
        ),
    ],
    responses={
        204: {'description': 'Анкета успешно удалена'},
        400: {'description': 'Требуется подтверждение удаления (confirm=true)'},
        403: {'description': 'Доступ запрещен. Только администраторы могут удалять анкеты'},
        404: {'description': 'Анкета не найдена'}
    }
)
class DesignerQuestionnaireDeleteView(views.APIView):
    """
    Полностью удалить анкету дизайнера из базы данных
    DELETE /api/v1/accounts/questionnaires/{id}/delete/
    """
    permission_classes = [permissions.IsAuthenticated]
    
    def delete(self, request, pk):
        if not request.user.is_staff:
            raise PermissionDenied("Только администратор может удалять анкету")
        
        # Проверка подтверждения
        confirm = request.query_params.get('confirm', 'false').lower() == 'true'
        if not confirm:
            # Проверяем в теле запроса
            if hasattr(request, 'data') and isinstance(request.data, dict):
                confirm = request.data.get('confirm', False)
                if isinstance(confirm, str):
                    confirm = confirm.lower() == 'true'
                else:
                    confirm = bool(confirm)
        
        if not confirm:
            return Response(
                {'error': 'Требуется подтверждение удаления. Добавьте параметр confirm=true в query string или в теле запроса.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            questionnaire = DesignerQuestionnaire.objects.get(pk=pk)
        except DesignerQuestionnaire.DoesNotExist:
            raise NotFound("Анкета не найдена")
        
        # Полное удаление из базы данных
        questionnaire.delete()
        return Response(
            {'message': 'Анкета успешно удалена из базы данных'},
            status=status.HTTP_204_NO_CONTENT
        )


@extend_schema(
    tags=['Repair Questionnaires'],
    summary='Архивировать анкету ремонтной бригады / подрядчика',
    description='''
    PATCH: Архивировать анкету ремонтной бригады / подрядчика (is_deleted=True)
    
    Требуется авторизация и права администратора (is_staff=True)
    ''',
    responses={
        200: {'description': 'Анкета успешно архивирована'},
        403: {'description': 'Доступ запрещен. Только администраторы могут архивировать анкеты'},
        404: {'description': 'Анкета не найдена'}
    }
)
class RepairQuestionnaireArchiveView(views.APIView):
    """
    Архивировать анкету ремонтной бригады / подрядчика
    PATCH /api/v1/accounts/repair-questionnaires/{id}/archive/
    """
    permission_classes = [permissions.IsAuthenticated]
    
    def patch(self, request, pk):
        if not request.user.is_staff:
            raise PermissionDenied("Только администратор может архивировать анкету")
        try:
            questionnaire = RepairQuestionnaire.objects.get(pk=pk)
        except RepairQuestionnaire.DoesNotExist:
            raise NotFound("Анкета не найдена")
        
        questionnaire.is_deleted = True
        questionnaire.save()
        serializer = RepairQuestionnaireSerializer(questionnaire, context={'request': request})
        return Response(serializer.data, status=status.HTTP_200_OK)


@extend_schema(
    tags=['Repair Questionnaires'],
    summary='Восстановить анкету ремонтной бригады / подрядчика из архива',
    description='''
    PATCH: Восстановить анкету ремонтной бригады / подрядчика из архива (is_deleted=False)
    
    Требуется авторизация и права администратора (is_staff=True)
    ''',
    responses={
        200: {'description': 'Анкета успешно восстановлена из архива'},
        403: {'description': 'Доступ запрещен. Только администраторы могут восстанавливать анкеты'},
        404: {'description': 'Анкета не найдена'}
    }
)
class RepairQuestionnaireRestoreView(views.APIView):
    """
    Восстановить анкету ремонтной бригады / подрядчика из архива
    PATCH /api/v1/accounts/repair-questionnaires/{id}/restore/
    """
    permission_classes = [permissions.IsAuthenticated]
    
    def patch(self, request, pk):
        if not request.user.is_staff:
            raise PermissionDenied("Только администратор может восстанавливать анкету")
        try:
            questionnaire = RepairQuestionnaire.objects.get(pk=pk)
        except RepairQuestionnaire.DoesNotExist:
            raise NotFound("Анкета не найдена")
        
        questionnaire.is_deleted = False
        questionnaire.save()
        serializer = RepairQuestionnaireSerializer(questionnaire, context={'request': request})
        return Response(serializer.data, status=status.HTTP_200_OK)


@extend_schema(
    tags=['Repair Questionnaires'],
    summary='Удалить анкету ремонтной бригады / подрядчика (полное удаление)',
    description='''
    DELETE: Полностью удалить анкету ремонтной бригады / подрядчика из базы данных
    
    ⚠️ ВНИМАНИЕ: Это действие необратимо! Анкета будет полностью удалена из базы данных.
    
    Требуется:
    - Авторизация и права администратора (is_staff=True)
    - Подтверждение действия через параметр confirm=true в query string или в теле запроса
    
    Пример запроса:
    DELETE /api/v1/accounts/repair-questionnaires/{id}/delete/?confirm=true
    или
    DELETE /api/v1/accounts/repair-questionnaires/{id}/delete/
    Body: {"confirm": true}
    ''',
    parameters=[
        OpenApiParameter(
            name='confirm',
            type=bool,
            location=OpenApiParameter.QUERY,
            description='Подтверждение удаления (обязательно: true)',
            required=True,
        ),
    ],
    responses={
        204: {'description': 'Анкета успешно удалена'},
        400: {'description': 'Требуется подтверждение удаления (confirm=true)'},
        403: {'description': 'Доступ запрещен. Только администраторы могут удалять анкеты'},
        404: {'description': 'Анкета не найдена'}
    }
)
class RepairQuestionnaireDeleteView(views.APIView):
    """
    Полностью удалить анкету ремонтной бригады / подрядчика из базы данных
    DELETE /api/v1/accounts/repair-questionnaires/{id}/delete/
    """
    permission_classes = [permissions.IsAuthenticated]
    
    def delete(self, request, pk):
        if not request.user.is_staff:
            raise PermissionDenied("Только администратор может удалять анкету")
        
        # Проверка подтверждения
        confirm = request.query_params.get('confirm', 'false').lower() == 'true'
        if not confirm:
            # Проверяем в теле запроса
            if hasattr(request, 'data') and isinstance(request.data, dict):
                confirm = request.data.get('confirm', False)
                if isinstance(confirm, str):
                    confirm = confirm.lower() == 'true'
                else:
                    confirm = bool(confirm)
        
        if not confirm:
            return Response(
                {'error': 'Требуется подтверждение удаления. Добавьте параметр confirm=true в query string или в теле запроса.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            questionnaire = RepairQuestionnaire.objects.get(pk=pk)
        except RepairQuestionnaire.DoesNotExist:
            raise NotFound("Анкета не найдена")
        
        # Полное удаление из базы данных
        questionnaire.delete()
        return Response(
            {'message': 'Анкета успешно удалена из базы данных'},
            status=status.HTTP_204_NO_CONTENT
        )


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
    - phone: Номер телефона (необязательное)
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
    - categories: Категории (массив, необязательное). Варианты: repair_team, contractor, finishing, electrical, plumbing, other
    - speed_of_execution: Скорость исполнения (необязательное). Варианты: advance_booking, quick_start, not_important
    - additional_info: Дополнительная информация (необязательное)
    - data_processing_consent: Согласие на обработку данных (обязательное, boolean)
    - company_logo: Логотип компании (shaxsiy kabinet uchun) (необязательное, файл)
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
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    
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
                name='category',
                type=str,
                location=OpenApiParameter.QUERY,
                description='Фильтр по основной категории по label из filter-choices: "Черновые работы", "ПОД КЛЮЧ", "Чистовые работы", "Сантехника и плитка", "Пол", "Стены", "Комнаты под ключ", "Электрика". Несколько через запятую. Синоним: categories.',
                required=False,
            ),
            OpenApiParameter(
                name='categories',
                type=str,
                location=OpenApiParameter.QUERY,
                description='То же, что category. Фильтр по основной категории (label) или по полю categories (Ремонтная бригада, Подрядчик и т.д.).',
                required=False,
            ),
            OpenApiParameter(
                name='city',
                type=str,
                location=OpenApiParameter.QUERY,
                description='Город(а). Несколько через запятую = AND. Только анкеты, у которых есть ВСЕ выбранные города (representative_cities). Значения из filter-choices/cities.',
                required=False,
            ),
            OpenApiParameter(
                name='segment',
                type=str,
                location=OpenApiParameter.QUERY,
                description='Сегмент: key (horeca, business, comfort, premium, medium, economy) или value (HoReCa, Бизнес и т.д.). Несколько через запятую.',
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
        
        # Категории (categories) — frontend value. "Черновые работы", "ПОД КЛЮЧ" va boshqalar aslida group (asosiy kategoriya);
        # agar category/categories shu label'lardan bo'lsa, group filterni (work_list) qo'llaymiz; qolganlari CATEGORY_CHOICES bo'yicha
        REPAIR_GROUP_LABEL_TO_KEY = {
            'ПОД КЛЮЧ': 'turnkey',
            'Черновые работы': 'rough_works',
            'Чистовые работы': 'finishing_works',
            'Сантехника и плитка': 'plumbing_tiles',
            'Пол': 'floor',
            'Стены': 'walls',
            'Комнаты под ключ': 'rooms_turnkey',
            'Электрика': 'electrical',
            'ВСЕ': 'all',
        }
        categories_param = request.query_params.get('categories') or request.query_params.get('category')
        if categories_param:
            from django.db.models import Q
            raw_list = [c.strip() for c in categories_param.split(',') if c.strip()]
            group_keys_from_category = []
            category_values = []
            for v in raw_list:
                v_norm = _normalize_category_label(v)
                matched_key = None
                for label, gk in REPAIR_GROUP_LABEL_TO_KEY.items():
                    if _normalize_category_label(label).lower() == v_norm.lower():
                        matched_key = gk
                        break
                if matched_key is not None:
                    if matched_key != 'all':
                        group_keys_from_category.append(matched_key)
                else:
                    category_values.append(v)
            # Group filterni qo'llash: work_list YOKI categories (JSONField); categories da istalgan katta/kichik harf (Capitalize ham)
            if group_keys_from_category:
                group_q = Q()
                for grp in group_keys_from_category:
                    if grp == 'turnkey':
                        group_q |= (
                            Q(work_list__icontains='под ключ') |
                            _q_categories_contains_any(['ПОД КЛЮЧ', 'под ключ', 'Под ключ'])
                        )
                    elif grp == 'rough_works':
                        group_q |= (
                            Q(work_list__icontains='черновые') |
                            _q_categories_contains_any(['черновые работы', 'Черновые работы', 'Черновые Работы', 'ЧЕРНОВЫЕ РАБОТЫ'])
                        )
                    elif grp == 'finishing_works':
                        group_q |= (
                            Q(work_list__icontains='чистовые') |
                            _q_categories_contains_any(['чистовые работы', 'Чистовые работы', 'Чистовые Работы', 'ЧИСТОВЫЕ РАБОТЫ'])
                        )
                    elif grp == 'plumbing_tiles':
                        group_q |= (
                            Q(work_list__icontains='сантехника') | Q(work_list__icontains='плитка') |
                            _q_categories_contains_any(['Сантехника и плитка', 'сантехника и плитка', 'САНТЕХНИКА И ПЛИТКА'])
                        )
                    elif grp == 'floor':
                        group_q |= (
                            Q(work_list__icontains='пол') |
                            _q_categories_contains_any(['Пол', 'пол', 'ПОЛ'])
                        )
                    elif grp == 'walls':
                        group_q |= (
                            Q(work_list__icontains='стены') |
                            _q_categories_contains_any(['Стены', 'стены', 'СТЕНЫ'])
                        )
                    elif grp == 'rooms_turnkey':
                        group_q |= (
                            (Q(work_list__icontains='комнаты') & Q(work_list__icontains='ключ')) |
                            _q_categories_contains_any(['Комнаты под ключ', 'комнаты под ключ', 'КОМНАТЫ ПОД КЛЮЧ'])
                        )
                    elif grp == 'electrical':
                        group_q |= (
                            Q(work_list__icontains='электрика') |
                            _q_categories_contains_any(['Электрика', 'электрика', 'ЭЛЕКТРИКА'])
                        )
                if group_q:
                    questionnaires = questionnaires.filter(group_q)
            # Oddiy category (CATEGORY_CHOICES: Ремонтная бригада, Подрядчик, ...)
            if category_values:
                categories_list = _choices_display_to_keys(category_values, RepairQuestionnaire.CATEGORY_CHOICES)
                cat_q = Q()
                for cat in categories_list:
                    cat_q |= Q(categories__contains=[cat])
                if cat_q:
                    questionnaires = questionnaires.filter(cat_q)
        
        # Выберете город (representative_cities). Несколько через запятую = AND
        city = request.query_params.get('city')
        if city:
            cities_list = [c.strip() for c in city.split(',') if c.strip()]
            if cities_list:
                from django.db.models import Q
                normal_cities = [c for c in cities_list if c not in ("По всей России", "ЮФО", "Любые города онлайн")]
                if "По всей России" in cities_list and not normal_cities:
                    pass
                elif "ЮФО" in cities_list and not normal_cities:
                    yfo_cities = ['Ростов-на-Дону', 'Краснодар', 'Сочи', 'Ставрополь', 'Волгоград', 'Астрахань']
                    city_q = Q()
                    for yfo_city in yfo_cities:
                        city_q |= Q(representative_cities__icontains=yfo_city)
                    if city_q:
                        questionnaires = questionnaires.filter(city_q)
                elif "Любые города онлайн" in cities_list and not normal_cities:
                    questionnaires = questionnaires.filter(
                        django_models.Q(cooperation_terms__icontains='онлайн') |
                        django_models.Q(cooperation_terms__icontains='online')
                    )
                else:
                    for city_item in normal_cities:
                        questionnaires = questionnaires.filter(representative_cities__icontains=city_item)
        
        # Сегмент — frontend value (HoReCa), key (horeca) ga o'giramiz
        segment = request.query_params.get('segment')
        if segment:
            segments_list = [s.strip() for s in segment.split(',')]
            segments_list = _choices_display_to_keys(segments_list, RepairQuestionnaire.SEGMENT_CHOICES)
            from django.db.models import Q
            segment_q = Q()
            for seg in segments_list:
                segment_q |= Q(segments__contains=[seg])
            if segment_q:
                questionnaires = questionnaires.filter(segment_q)
        
        # Наличие НДС (vat_payment) — frontend value (Да/Нет), key (yes/no) ga o'giramiz
        vat_payment = request.query_params.get('vat_payment')
        if vat_payment:
            vat_list = [v.strip() for v in vat_payment.split(',')]
            vat_list = _choices_display_to_keys(vat_list, RepairQuestionnaire.VAT_PAYMENT_CHOICES)
            from django.db.models import Q
            vat_q = Q()
            for vat in vat_list:
                if vat == 'not_important':
                    pass
                elif vat in ('yes', 'no'):
                    vat_q |= Q(vat_payment=vat)
            if vat_q:
                questionnaires = questionnaires.filter(vat_q)
        
        # Карточки журналов (magazine_cards) — frontend value, key ga o'giramiz
        magazine_cards = request.query_params.get('magazine_cards')
        if magazine_cards:
            cards_list = [c.strip() for c in magazine_cards.split(',')]
            cards_list = _choices_display_to_keys(cards_list, RepairQuestionnaire.MAGAZINE_CARD_CHOICES)
            from django.db.models import Q
            cards_q = Q()
            for card in cards_list:
                if card == 'not_important':
                    pass
                else:
                    cards_q |= Q(magazine_cards__contains=[card])
            if cards_q:
                questionnaires = questionnaires.filter(cards_q)
        
        # Скорость исполнения (execution_speed) — frontend value, key ga o'giramiz
        execution_speed = request.query_params.get('execution_speed')
        if execution_speed:
            speeds_list = [s.strip() for s in execution_speed.split(',') if s.strip()]
            speeds_list = _choices_display_to_keys(speeds_list, RepairQuestionnaire.SPEED_OF_EXECUTION_CHOICES)
            from django.db.models import Q
            speed_q = Q()
            for s in speeds_list:
                if s != 'not_important':
                    speed_q |= Q(speed_of_execution=s)
            if speed_q:
                questionnaires = questionnaires.filter(speed_q)
        
        # Условия сотрудничества (cooperation_terms) — несколько через запятую, OR
        cooperation_terms = request.query_params.get('cooperation_terms')
        if cooperation_terms:
            terms_list = [t.strip() for t in cooperation_terms.split(',') if t.strip()]
            terms_mapping = {'up_to_5_percent': '5%', 'up_to_10_percent': '10%'}
            from django.db.models import Q
            terms_q = Q()
            for t in terms_list:
                if t != 'not_important':
                    search_term = terms_mapping.get(t, t)
                    terms_q |= Q(cooperation_terms__icontains=search_term)
            if terms_q:
                questionnaires = questionnaires.filter(terms_q)
        
        # Назначение недвижимости (property_purpose) — несколько через запятую, OR
        property_purpose = request.query_params.get('property_purpose')
        if property_purpose:
            purposes_list = [p.strip() for p in property_purpose.split(',') if p.strip()]
            from django.db.models import Q
            purpose_q = Q()
            for p in purposes_list:
                purpose_q |= Q(work_list__icontains=p)
            if purpose_q:
                questionnaires = questionnaires.filter(purpose_q)
        
        # Площадь объекта (object_area) — несколько через запятую, OR
        object_area = request.query_params.get('object_area')
        if object_area:
            areas_list = [a.strip() for a in object_area.split(',') if a.strip()]
            from django.db.models import Q
            area_q = Q()
            for a in areas_list:
                area_q |= Q(project_timelines__icontains=a)
            if area_q:
                questionnaires = questionnaires.filter(area_q)
        
        # Стоимость за м2 (cost_per_sqm) — несколько через запятую, OR
        cost_per_sqm = request.query_params.get('cost_per_sqm')
        if cost_per_sqm:
            cost_list = [c.strip() for c in cost_per_sqm.split(',') if c.strip()]
            from django.db.models import Q
            cost_q = Q()
            for c in cost_list:
                cost_q |= Q(work_format__icontains=c) | Q(guarantees__icontains=c)
            if cost_q:
                questionnaires = questionnaires.filter(cost_q)
        
        # Опыт работы (experience) — несколько через запятую, OR
        experience = request.query_params.get('experience')
        if experience:
            exp_list = [e.strip() for e in experience.split(',') if e.strip()]
            from django.db.models import Q
            exp_q = Q()
            for e in exp_list:
                exp_q |= Q(welcome_message__icontains=e) | Q(additional_info__icontains=e)
            if exp_q:
                questionnaires = questionnaires.filter(exp_q)
        
        # Форма бизнеса (business_form) — frontend value, key ga o'giramiz
        business_form = request.query_params.get('business_form')
        if business_form:
            forms_list = [f.strip() for f in business_form.split(',') if f.strip()]
            forms_list = _choices_display_to_keys(forms_list, RepairQuestionnaire.BUSINESS_FORM_CHOICES)
            if forms_list:
                from django.db.models import Q
                form_q = Q()
                for f in forms_list:
                    form_q |= Q(business_form=f)
                questionnaires = questionnaires.filter(form_q)
        
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
        serializer = RepairQuestionnaireSerializer(paginated_questionnaires, many=True, context={'request': request})
        
        return paginator.get_paginated_response(serializer.data)
    
    def post(self, request):
        # Phone tekshirish - bir xil phone bilan ikkinchi marta create qilish mumkin emas
        phone = request.data.get('phone')
        if phone:
            from .models import RepairQuestionnaire
            # Agar allaqachon shu phone bilan questionnaire yaratilgan bo'lsa
            existing_questionnaire = RepairQuestionnaire.objects.filter(
                phone=phone,
                is_deleted=False
            ).first()
            
            if existing_questionnaire:
                return Response({
                    'phone': ['Анкета с таким номером телефона уже существует. Один номер телефона может быть использован только один раз.']
                }, status=status.HTTP_400_BAD_REQUEST)
        
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
    - phone: Номер телефона
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
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    
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
        questionnaire = self.get_object(pk, request)
        serializer = RepairQuestionnaireSerializer(questionnaire, context={'request': request})
        return Response(serializer.data, status=status.HTTP_200_OK)
    
    def put(self, request, pk):
        if not request.user.is_authenticated:
            raise PermissionDenied("Требуется авторизация для обновления анкеты")
        questionnaire = self.get_object(pk, request)
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
            
            result_serializer = DesignerQuestionnaireSerializer(questionnaire, context={'request': request})
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
    - cities: Уникальные города из анкет выбранной категории (только из RepairQuestionnaire representative_cities) - Выберете город
    - segments: Сегменты работы (можно выбрать несколько) - Выберете сегмент
      * Эконом (economy)
      * Комфорт (comfort)
      * Бизнесс (business)
      * Примиум (premium)
      * HoReCa (horeca)
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
            {'value': 'rough_works', 'label': 'Черновые работы'},
            {'value': 'finishing_works', 'label': 'Чистовые работы'},
            {'value': 'plumbing_tiles', 'label': 'Сантехника и плитка'},
            {'value': 'floor', 'label': 'Пол'},
            {'value': 'walls', 'label': 'Стены'},
            {'value': 'rooms_turnkey', 'label': 'Комнаты под ключ'},
            {'value': 'electrical', 'label': 'Электрика'},
            {'value': 'all', 'label': 'ВСЕ'},
        ]
        
        # Уникальные города из representative_cities - Выберете город
        # Barcha shaharlar (is_deleted=False faqat)
        all_cities = set()
        repair_query = RepairQuestionnaire.objects.filter(is_deleted=False)
        
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
        # Faqat RepairQuestionnaire representative_cities dagi shaharlar (maxsus variantlar olib tashlandi)
        
        # Сегменты - Выберете сегмент (ko'p tanlash mumkin)
        # Model'dan olinadi: economy, comfort, business, premium, horeca, medium
        segments = [
            {'value': choice[0], 'label': choice[1].capitalize()} 
            for choice in RepairQuestionnaire.SEGMENT_CHOICES
        ]
        
        # Наличие НДС - Наличие НДС (ko'p tanlash mumkin)
        # Model'dan olinadi: yes, no
        vat_payments = [
            {'value': 'yes', 'label': 'Да'},
            {'value': 'no', 'label': 'Нет'},
            {'value': 'not_important', 'label': 'Не важно'},
        ]
        
        # Карточки журналов - Карточки журналов (faqat model'dagi choices)
        from .models import RepairQuestionnaire
        magazine_cards = [
            {'value': choice[0], 'label': choice[1]} 
            for choice in RepairQuestionnaire.MAGAZINE_CARD_CHOICES
            if choice[0] != 'other'  # "other" ni olib tashlaymiz
        ]
        
        # Скорость исполнения - Скорость исполнения
        execution_speeds = [
            {'value': 'advance_booking', 'label': 'Предварительная запись'},
            {'value': 'quick_start', 'label': 'Быстрый старт'},
            {'value': 'not_important', 'label': 'Не важно'},
        ]
        
        # Условия сотрудничества - Условия сотрудничества
        cooperation_terms_options = [
            {'value': 'up_to_5_percent', 'label': 'До 5%'},
            {'value': 'up_to_10_percent', 'label': 'До 10%'},
            {'value': 'not_important', 'label': 'Не важно'},
        ]
        
        return Response({
            'categories': categories,
            'cities': cities_list,
            'segments': segments,
            'vat_payments': vat_payments,
            'magazine_cards': magazine_cards,
            'execution_speeds': execution_speeds,
            'cooperation_terms_options': cooperation_terms_options,
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
            
            result_serializer = RepairQuestionnaireSerializer(questionnaire, context={'request': request})
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
    - phone: Номер телефона (необязательное)
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
    - categories: Категории (массив, необязательное). Варианты: supplier, exhibition_hall, factory, salon, other
    - speed_of_execution: Скорость исполнения / сроки поставки (необязательное). Варианты: in_stock, up_to_2_weeks, up_to_1_month, up_to_3_months, not_important
    - data_processing_consent: Согласие на обработку данных (обязательное, boolean)
    - company_logo: Логотип компании (shaxsiy kabinet uchun) (необязательное, файл)
    
    Массивы (representative_cities, other_contacts, rough_materials, finishing_materials, upholstered_furniture, cabinet_furniture, technique, decor):
    - В Swagger выберите body type "application/json" и отправляйте массивы как JSON: "rough_materials": ["электрика", "су"].
    - При form-data можно: один раз ключ с JSON-строкой "[\"электрика\",\"су\"]" или через запятую "электрика,су".
    
    GET и PUT принимают/возвращают те же поля.
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
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    
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
                name='category',
                type=str,
                location=OpenApiParameter.QUERY,
                description='Фильтр по основной категории по label из filter-choices: "Черновые материалы", "Чистовые материалы", "Мягкая мебель", "Корпусная мебель", "Техника", "Декор". Несколько через запятую. Синоним: categories.',
                required=False,
            ),
            OpenApiParameter(
                name='categories',
                type=str,
                location=OpenApiParameter.QUERY,
                description='То же, что category. Фильтр по основной категории (label) или по полю categories (Поставщик, Фабрика и т.д.).',
                required=False,
            ),
            OpenApiParameter(
                name='city',
                type=str,
                location=OpenApiParameter.QUERY,
                description='Город(а). Несколько через запятую = AND. Только анкеты, у которых есть ВСЕ выбранные города (representative_cities). Значения из filter-choices/cities.',
                required=False,
            ),
            OpenApiParameter(
                name='segment',
                type=str,
                location=OpenApiParameter.QUERY,
                description='Сегмент: key (horeca, business, comfort, premium, medium, economy) или value (HoReCa, Бизнес и т.д.). Несколько через запятую.',
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
            OpenApiParameter(name='rough_materials', type=str, location=OpenApiParameter.QUERY, description='Черновые материалы: несколько через запятую (OR)', required=False),
            OpenApiParameter(name='finishing_materials', type=str, location=OpenApiParameter.QUERY, description='Чистовые материалы: несколько через запятую (OR)', required=False),
            OpenApiParameter(name='upholstered_furniture', type=str, location=OpenApiParameter.QUERY, description='Мягкая мебель: несколько через запятую (OR)', required=False),
            OpenApiParameter(name='cabinet_furniture', type=str, location=OpenApiParameter.QUERY, description='Корпусная мебель: несколько через запятую (OR)', required=False),
            OpenApiParameter(name='technique', type=str, location=OpenApiParameter.QUERY, description='Техника: несколько через запятую (OR)', required=False),
            OpenApiParameter(name='decor', type=str, location=OpenApiParameter.QUERY, description='Декор: несколько через запятую (OR)', required=False),
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
        
        # Категории (categories) — frontend value. "Черновые материалы", "Мягкая мебель" va boshqalar aslida group (asosiy kategoriя);
        # agar category/categories shu label'lardan bo'lsa, group filterni (product_assortment) qo'llaymiz; qolganlari CATEGORY_CHOICES bo'yicha
        SUPPLIER_GROUP_LABEL_TO_KEY = {
            'Черновые материалы': 'rough_materials',
            'Чистовые материалы': 'finishing_materials',
            'Мягкая мебель': 'soft_furniture',
            'Корпусная мебель': 'cabinet_furniture',
            'Техника': 'appliances',
            'Декор': 'decor',
            'ВСЕ': 'all',
        }
        categories_param = request.query_params.get('categories') or request.query_params.get('category')
        if categories_param:
            from django.db.models import Q
            raw_list = [c.strip() for c in categories_param.split(',') if c.strip()]
            group_keys_from_category = []
            category_values = []
            for v in raw_list:
                v_norm = _normalize_category_label(v)
                matched_key = None
                for label, gk in SUPPLIER_GROUP_LABEL_TO_KEY.items():
                    if _normalize_category_label(label).lower() == v_norm.lower():
                        matched_key = gk
                        break
                if matched_key is not None:
                    if matched_key != 'all':
                        group_keys_from_category.append(matched_key)
                else:
                    category_values.append(v)
            if group_keys_from_category:
                group_q = Q()
                for grp in group_keys_from_category:
                    if grp == 'rough_materials':
                        group_q |= (
                            Q(product_assortment__icontains='черновые') |
                            _q_categories_contains_any(['Черновые материалы', 'черновые материалы', 'Черновые Материалы', 'ЧЕРНОВЫЕ МАТЕРИАЛЫ'])
                        )
                    elif grp == 'finishing_materials':
                        group_q |= (
                            Q(product_assortment__icontains='чистовые') |
                            _q_categories_contains_any(['Чистовые материалы', 'чистовые материалы', 'Чистовые Материалы', 'ЧИСТОВЫЕ МАТЕРИАЛЫ'])
                        )
                    elif grp == 'soft_furniture':
                        group_q |= (
                            Q(product_assortment__icontains='мягкая мебель') |
                            _q_categories_contains_any(['Мягкая мебель', 'мягкая мебель', 'Мягкая Мебель', 'МЯГКАЯ МЕБЕЛЬ'])
                        )
                    elif grp == 'cabinet_furniture':
                        group_q |= (
                            Q(product_assortment__icontains='корпусная мебель') |
                            _q_categories_contains_any(['Корпусная мебель', 'корпусная мебель', 'Корпусная Мебель', 'КОРПУСНАЯ МЕБЕЛЬ'])
                        )
                    elif grp == 'appliances':
                        group_q |= (
                            Q(product_assortment__icontains='техника') |
                            _q_categories_contains_any(['Техника', 'техника', 'ТЕХНИКА'])
                        )
                    elif grp == 'decor':
                        group_q |= (
                            Q(product_assortment__icontains='декор') |
                            _q_categories_contains_any(['Декор', 'декор', 'ДЕКОР'])
                        )
                if group_q:
                    questionnaires = questionnaires.filter(group_q)
            if category_values:
                categories_list = _choices_display_to_keys(category_values, SupplierQuestionnaire.CATEGORY_CHOICES)
                cat_q = Q()
                for cat in categories_list:
                    cat_q |= Q(categories__contains=[cat])
                if cat_q:
                    questionnaires = questionnaires.filter(cat_q)
        
        # Выберете город (representative_cities). Несколько через запятую = AND
        city = request.query_params.get('city')
        if city:
            cities_list = [c.strip() for c in city.split(',') if c.strip()]
            if cities_list:
                from django.db.models import Q
                normal_cities = [c for c in cities_list if c not in ("По всей России", "ЮФО", "Любые города онлайн")]
                if "По всей России" in cities_list and not normal_cities:
                    pass
                elif "ЮФО" in cities_list and not normal_cities:
                    yfo_cities = ['Ростов-на-Дону', 'Краснодар', 'Сочи', 'Ставрополь', 'Волгоград', 'Астрахань']
                    city_q = Q()
                    for yfo_city in yfo_cities:
                        city_q |= Q(representative_cities__icontains=yfo_city)
                    if city_q:
                        questionnaires = questionnaires.filter(city_q)
                elif "Любые города онлайн" in cities_list and not normal_cities:
                    questionnaires = questionnaires.filter(
                        Q(cooperation_terms__icontains='онлайн') | Q(cooperation_terms__icontains='online')
                    )
                else:
                    for city_item in normal_cities:
                        questionnaires = questionnaires.filter(representative_cities__icontains=city_item)
        
        # Сегмент — frontend value (HoReCa), key (horeca) ga o'giramiz
        segment = request.query_params.get('segment')
        if segment:
            segments_list = [s.strip() for s in segment.split(',')]
            segments_list = _choices_display_to_keys(segments_list, SupplierQuestionnaire.SEGMENT_CHOICES)
            from django.db.models import Q
            segment_q = Q()
            for seg in segments_list:
                segment_q |= Q(segments__contains=[seg])
            if segment_q:
                questionnaires = questionnaires.filter(segment_q)
        
        # Наличие НДС (vat_payment) — frontend value (Да/Нет), key (yes/no) ga o'giramiz
        vat_payment = request.query_params.get('vat_payment')
        if vat_payment:
            vat_list = [v.strip() for v in vat_payment.split(',') if v.strip()]
            vat_list = _choices_display_to_keys(vat_list, SupplierQuestionnaire.VAT_PAYMENT_CHOICES)
            from django.db.models import Q
            vat_q = Q()
            for v in vat_list:
                if v != 'not_important' and v in ('yes', 'no'):
                    vat_q |= Q(vat_payment=v)
            if vat_q:
                questionnaires = questionnaires.filter(vat_q)
        
        # Карточки журналов (magazine_cards) — frontend value, key ga o'giramiz
        magazine_cards = request.query_params.get('magazine_cards')
        if magazine_cards:
            cards_list = [c.strip() for c in magazine_cards.split(',')]
            cards_list = _choices_display_to_keys(cards_list, SupplierQuestionnaire.MAGAZINE_CARD_CHOICES)
            from django.db.models import Q
            cards_q = Q()
            for card in cards_list:
                if card == 'not_important':
                    pass
                else:
                    cards_q |= Q(magazine_cards__contains=[card])
            if cards_q:
                questionnaires = questionnaires.filter(cards_q)
        
        # Скорость исполнения (execution_speed) — frontend value, key ga o'giramiz
        execution_speed = request.query_params.get('execution_speed')
        if execution_speed:
            speeds_list = [s.strip() for s in execution_speed.split(',')]
            speeds_list = _choices_display_to_keys(speeds_list, SupplierQuestionnaire.SPEED_OF_EXECUTION_CHOICES)
            from django.db.models import Q
            speed_q = Q()
            for speed in speeds_list:
                if speed != 'not_important':
                    speed_q |= Q(speed_of_execution=speed)
            if speed_q:
                questionnaires = questionnaires.filter(speed_q)
        
        # Условия сотрудничества (cooperation_terms) — несколько через запятую, OR
        cooperation_terms = request.query_params.get('cooperation_terms')
        if cooperation_terms:
            terms_list = [t.strip() for t in cooperation_terms.split(',') if t.strip()]
            terms_mapping = {'up_to_10_percent': '10%', 'up_to_20_percent': '20%', 'up_to_30_percent': '30%'}
            from django.db.models import Q
            terms_q = Q()
            for t in terms_list:
                if t != 'not_important':
                    search_term = terms_mapping.get(t, t)
                    terms_q |= Q(cooperation_terms__icontains=search_term)
            if terms_q:
                questionnaires = questionnaires.filter(terms_q)
        
        # Форма бизнеса (business_form) — frontend value, key ga o'giramiz
        business_form = request.query_params.get('business_form')
        if business_form:
            forms_list = [f.strip() for f in business_form.split(',') if f.strip()]
            forms_list = _choices_display_to_keys(forms_list, SupplierQuestionnaire.BUSINESS_FORM_CHOICES)
            if forms_list:
                from django.db.models import Q
                form_q = Q()
                for f in forms_list:
                    form_q |= Q(business_form=f)
                questionnaires = questionnaires.filter(form_q)
        
        # Search by full_name or brand_name
        search = request.query_params.get('search')
        if search:
            questionnaires = questionnaires.filter(
                django_models.Q(full_name__icontains=search) | 
                django_models.Q(brand_name__icontains=search)
            )
        
        # Secondary filter fields (multiple values = OR)
        for param_name, field_name in [
            ('rough_materials', 'rough_materials'),
            ('finishing_materials', 'finishing_materials'),
            ('upholstered_furniture', 'upholstered_furniture'),
            ('cabinet_furniture', 'cabinet_furniture'),
            ('technique', 'technique'),
            ('decor', 'decor'),
        ]:
            param = request.query_params.get(param_name)
            if param:
                values = [v.strip() for v in param.split(',') if v.strip()]
                if values:
                    q_sec = django_models.Q()
                    for v in values:
                        q_sec |= django_models.Q(**{f'{field_name}__contains': [v]})
                    questionnaires = questionnaires.filter(q_sec)
        
        # Ordering
        ordering = request.query_params.get('ordering', '-created_at')
        questionnaires = questionnaires.order_by(ordering)
        
        # Pagination
        paginator = LimitOffsetPagination()
        paginator.default_limit = 100
        paginator.limit_query_param = 'limit'
        paginator.offset_query_param = 'offset'
        
        paginated_questionnaires = paginator.paginate_queryset(questionnaires, request)
        serializer = SupplierQuestionnaireSerializer(paginated_questionnaires, many=True, context={'request': request})
        
        return paginator.get_paginated_response(serializer.data)
    
    def post(self, request):
        # Phone tekshirish - bir xil phone bilan ikkinchi marta create qilish mumkin emas
        phone = request.data.get('phone')
        if phone:
            from .models import SupplierQuestionnaire
            # Agar allaqachon shu phone bilan questionnaire yaratilgan bo'lsa
            existing_questionnaire = SupplierQuestionnaire.objects.filter(
                phone=phone,
                is_deleted=False
            ).first()
            
            if existing_questionnaire:
                return Response({
                    'phone': ['Анкета с таким номером телефона уже существует. Один номер телефона может быть использован только один раз.']
                }, status=status.HTTP_400_BAD_REQUEST)
        
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
    - phone: Номер телефона
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
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    
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
        serializer = SupplierQuestionnaireSerializer(questionnaire, context={'request': request})
        return Response(serializer.data, status=status.HTTP_200_OK)
    
    def put(self, request, pk):
        if not request.user.is_authenticated:
            raise PermissionDenied("Требуется авторизация для обновления анкеты")
        questionnaire = self.get_object(pk, request)
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
    summary='Архивировать анкету поставщика / салона / фабрики',
    description='''
    PATCH: Архивировать анкету поставщика / салона / фабрики (is_deleted=True)
    
    Требуется авторизация и права администратора (is_staff=True)
    ''',
    responses={
        200: {'description': 'Анкета успешно архивирована'},
        403: {'description': 'Доступ запрещен. Только администраторы могут архивировать анкеты'},
        404: {'description': 'Анкета не найдена'}
    }
)
class SupplierQuestionnaireArchiveView(views.APIView):
    """
    Архивировать анкету поставщика / салона / фабрики
    PATCH /api/v1/accounts/supplier-questionnaires/{id}/archive/
    """
    permission_classes = [permissions.IsAuthenticated]
    
    def patch(self, request, pk):
        if not request.user.is_staff:
            raise PermissionDenied("Только администратор может архивировать анкету")
        try:
            questionnaire = SupplierQuestionnaire.objects.get(pk=pk)
        except SupplierQuestionnaire.DoesNotExist:
            raise NotFound("Анкета не найдена")
        
        questionnaire.is_deleted = True
        questionnaire.save()
        serializer = SupplierQuestionnaireSerializer(questionnaire, context={'request': request})
        return Response(serializer.data, status=status.HTTP_200_OK)


@extend_schema(
    tags=['Supplier Questionnaires'],
    summary='Восстановить анкету поставщика / салона / фабрики из архива',
    description='''
    PATCH: Восстановить анкету поставщика / салона / фабрики из архива (is_deleted=False)
    
    Требуется авторизация и права администратора (is_staff=True)
    ''',
    responses={
        200: {'description': 'Анкета успешно восстановлена из архива'},
        403: {'description': 'Доступ запрещен. Только администраторы могут восстанавливать анкеты'},
        404: {'description': 'Анкета не найдена'}
    }
)
class SupplierQuestionnaireRestoreView(views.APIView):
    """
    Восстановить анкету поставщика / салона / фабрики из архива
    PATCH /api/v1/accounts/supplier-questionnaires/{id}/restore/
    """
    permission_classes = [permissions.IsAuthenticated]
    
    def patch(self, request, pk):
        if not request.user.is_staff:
            raise PermissionDenied("Только администратор может восстанавливать анкету")
        try:
            questionnaire = SupplierQuestionnaire.objects.get(pk=pk)
        except SupplierQuestionnaire.DoesNotExist:
            raise NotFound("Анкета не найдена")
        
        questionnaire.is_deleted = False
        questionnaire.save()
        serializer = SupplierQuestionnaireSerializer(questionnaire, context={'request': request})
        return Response(serializer.data, status=status.HTTP_200_OK)


@extend_schema(
    tags=['Supplier Questionnaires'],
    summary='Удалить анкету поставщика / салона / фабрики (полное удаление)',
    description='''
    DELETE: Полностью удалить анкету поставщика / салона / фабрики из базы данных
    
    ⚠️ ВНИМАНИЕ: Это действие необратимо! Анкета будет полностью удалена из базы данных.
    
    Требуется:
    - Авторизация и права администратора (is_staff=True)
    - Подтверждение действия через параметр confirm=true в query string или в теле запроса
    
    Пример запроса:
    DELETE /api/v1/accounts/supplier-questionnaires/{id}/delete/?confirm=true
    или
    DELETE /api/v1/accounts/supplier-questionnaires/{id}/delete/
    Body: {"confirm": true}
    ''',
    parameters=[
        OpenApiParameter(
            name='confirm',
            type=bool,
            location=OpenApiParameter.QUERY,
            description='Подтверждение удаления (обязательно: true)',
            required=True,
        ),
    ],
    responses={
        204: {'description': 'Анкета успешно удалена'},
        400: {'description': 'Требуется подтверждение удаления (confirm=true)'},
        403: {'description': 'Доступ запрещен. Только администраторы могут удалять анкеты'},
        404: {'description': 'Анкета не найдена'}
    }
)
class SupplierQuestionnaireDeleteView(views.APIView):
    """
    Полностью удалить анкету поставщика / салона / фабрики из базы данных
    DELETE /api/v1/accounts/supplier-questionnaires/{id}/delete/
    """
    permission_classes = [permissions.IsAuthenticated]
    
    def delete(self, request, pk):
        if not request.user.is_staff:
            raise PermissionDenied("Только администратор может удалять анкету")
        
        # Проверка подтверждения
        confirm = request.query_params.get('confirm', 'false').lower() == 'true'
        if not confirm:
            # Проверяем в теле запроса
            if hasattr(request, 'data') and isinstance(request.data, dict):
                confirm = request.data.get('confirm', False)
                if isinstance(confirm, str):
                    confirm = confirm.lower() == 'true'
                else:
                    confirm = bool(confirm)
        
        if not confirm:
            return Response(
                {'error': 'Требуется подтверждение удаления. Добавьте параметр confirm=true в query string или в теле запроса.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            questionnaire = SupplierQuestionnaire.objects.get(pk=pk)
        except SupplierQuestionnaire.DoesNotExist:
            raise NotFound("Анкета не найдена")
        
        # Полное удаление из базы данных
        questionnaire.delete()
        return Response(
            {'message': 'Анкета успешно удалена из базы данных'},
            status=status.HTTP_204_NO_CONTENT
        )


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
    - cities: Уникальные города из анкет выбранной категории (только из SupplierQuestionnaire representative_cities) - Выберете город
    - segments: Сегменты работы (можно выбрать несколько) - Выберете сегмент
      * Эконом (economy)
      * Комфорт (comfort)
      * Бизнесс (business)
      * Примиум (premium)
      * HoReCa (horeca)
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
        # Barcha shaharlar (is_deleted=False faqat)
        is_staff = request.user.is_authenticated and request.user.is_staff
        supplier_query = SupplierQuestionnaire.objects.filter(is_deleted=False)
        
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
        # Faqat SupplierQuestionnaire representative_cities dagi shaharlar (maxsus variantlar olib tashlandi)
        
        # Сегменты - Выберите сегмент (ko'p tanlash mumkin)
        # Model'dan olinadi: economy, comfort, business, premium, horeca, medium
        segments = [
            {'value': choice[0], 'label': choice[1].capitalize()} 
            for choice in SupplierQuestionnaire.SEGMENT_CHOICES
        ]
        
        # Наличие НДС - Наличие НДС
        vat_payments = [
            {'value': 'yes', 'label': 'Да'},
            {'value': 'no', 'label': 'Нет'},
            {'value': 'not_important', 'label': 'Не важно'},
        ]
        
        # Карточки журналов - Карточки журналов (faqat model'dagi choices)
        from .models import SupplierQuestionnaire
        magazine_cards = [
            {'value': choice[0], 'label': choice[1]} 
            for choice in SupplierQuestionnaire.MAGAZINE_CARD_CHOICES
            if choice[0] != 'other'  # "other" ni olib tashlaymiz
        ]
        
        # Скорость исполнения - Скорость исполнения (ko'p tanlash mumkin)
        execution_speeds = [
            {'value': 'in_stock', 'label': 'В наличии'},
            {'value': 'up_to_2_weeks', 'label': 'До 2х недель'},
            {'value': 'up_to_1_month', 'label': 'До 1 месяца'},
            {'value': 'up_to_3_months', 'label': 'До 3х месяцев'},
            {'value': 'not_important', 'label': 'Не важно'},
        ]
        
        # Условия сотрудничества - Условия сотрудничества
        cooperation_terms_options = [
            {'value': 'up_to_10_percent', 'label': 'До 10%'},
            {'value': 'up_to_20_percent', 'label': 'До 20%'},
            {'value': 'up_to_30_percent', 'label': 'До 30%'},
            {'value': 'not_important', 'label': 'Не важно'},
        ]
        
        return Response({
            'categories': categories,
            'cities': cities_list,
            'segments': segments,
            'vat_payments': vat_payments,
            'magazine_cards': magazine_cards,
            'execution_speeds': execution_speeds,
            'cooperation_terms_options': cooperation_terms_options,
        }, status=status.HTTP_200_OK)


# Дополнительный фильтр для каждой из основных категорий (статичные значения для secondory_filter_data_supplier)
SUPPLIER_SECONDARY_FILTER_DATA = {
    'rough_materials': [
        {'name': 'виды материалов'}, {'name': 'электрика'}, {'name': 'су'}, {'name': 'пол'},
        {'name': 'стены'}, {'name': 'потолок'}, {'name': 'прочее'},
    ],
    'finishing_materials': [
        {'name': 'категория товара'}, {'name': 'сантехника'}, {'name': 'пол'}, {'name': 'потолок'},
        {'name': 'стены'}, {'name': 'декоративные элементы'}, {'name': 'двери'}, {'name': 'камень'},
        {'name': 'электрика'}, {'name': 'стеновые панели'},
    ],
    'upholstered_furniture': [
        {'name': 'готовая'}, {'name': 'под заказ'}, {'name': 'мебель по эскизам'}, {'name': 'стулья'},
        {'name': 'спальни'}, {'name': 'детские'}, {'name': 'гостинные'}, {'name': 'хорика'},
        {'name': 'уличная мебель'}, {'name': 'матрасы и подушки'},
    ],
    'cabinet_furniture': [
        {'name': 'готовая'}, {'name': 'под заказ'}, {'name': 'мебель по эскизам'}, {'name': 'столы и стулья'},
        {'name': 'шкафы и гардеробные'}, {'name': 'хорика'}, {'name': 'уличная мебель'},
    ],
    'technique': [
        {'name': 'под заказ'}, {'name': 'есть склад'}, {'name': 'кухня'}, {'name': 'кондиционер'},
        {'name': 'умный дом'}, {'name': 'свет'},
    ],
    'decor': [
        {'name': 'ковры'}, {'name': 'посуда'}, {'name': 'картины'}, {'name': 'элементы интерьера'},
        {'name': 'дизайнерские объекты'}, {'name': 'лепнина'}, {'name': 'Элементы декора по индивидуальным эскизам'},
    ],
}

# categories query param: frontend yuboradi (Черновые материалы, Чистовые материалы, ...) -> response key
SUPPLIER_CATEGORY_NAME_TO_KEY = {
    'Черновые материалы': 'rough_materials',
    'Чистовые материалы': 'finishing_materials',
    'Мягкая мебель': 'upholstered_furniture',
    'Корпусная мебель': 'cabinet_furniture',
    'Техника': 'technique',
    'Декор': 'decor',
}


@extend_schema(
    tags=['Supplier Questionnaires'],
    summary='Дополнительный фильтр для каждой из основных категорий',
    description='Возвращает статичный список значений для полей: rough_materials, finishing_materials, upholstered_furniture, cabinet_furniture, technique, decor. Формат: каждая категория — массив объектов с полем "name". Query: categories — несколько через запятую (напр. Чистовые материалы, Черновые материалы), faqat shu kategoriyalar qaytadi.',
    parameters=[
        OpenApiParameter(
            name='categories',
            type=str,
            location=OpenApiParameter.QUERY,
            description='Категории через запятую: Черновые материалы, Чистовые материалы, Мягкая мебель, Корпусная мебель, Техника, Декор. Bo\'sh bo\'lsa — hammasi qaytadi.',
            required=False,
        ),
    ],
    responses={200: {'description': 'rough_materials, finishing_materials, ... (categories bo\'yicha filtr)'}},
)
class SecondoryFilterDataSupplierView(views.APIView):
    """
    Дополнительный фильтр для каждой из основных категорий поставщика.
    GET /api/v1/accounts/supplier-questionnaires/secondory-filter-data/
    ?categories=Чистовые материалы,Черновые материалы — faqat finishing_materials va rough_materials qaytadi.
    """
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        categories_param = request.query_params.get('categories', '').strip()
        if not categories_param:
            return Response(SUPPLIER_SECONDARY_FILTER_DATA, status=status.HTTP_200_OK)
        categories_list = [c.strip() for c in categories_param.split(',') if c.strip()]
        keys = []
        for name in categories_list:
            key = SUPPLIER_CATEGORY_NAME_TO_KEY.get(name)
            if key and key not in keys:
                keys.append(key)
        if not keys:
            return Response(SUPPLIER_SECONDARY_FILTER_DATA, status=status.HTTP_200_OK)
        data = {k: SUPPLIER_SECONDARY_FILTER_DATA[k] for k in keys if k in SUPPLIER_SECONDARY_FILTER_DATA}
        return Response(data, status=status.HTTP_200_OK)


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
            
            result_serializer = SupplierQuestionnaireSerializer(questionnaire, context={'request': request})
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
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    
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
        serializer = MediaQuestionnaireSerializer(paginated_questionnaires, many=True, context={'request': request})
        
        return paginator.get_paginated_response(serializer.data)
    
    def post(self, request):
        # Phone tekshirish - bir xil phone bilan ikkinchi marta create qilish mumkin emas
        phone = request.data.get('phone')
        if phone:
            from .models import MediaQuestionnaire
            # Agar allaqachon shu phone bilan questionnaire yaratilgan bo'lsa
            existing_questionnaire = MediaQuestionnaire.objects.filter(
                phone=phone,
                is_deleted=False
            ).first()
            
            if existing_questionnaire:
                return Response({
                    'phone': ['Анкета с таким номером телефона уже существует. Один номер телефона может быть использован только один раз.']
                }, status=status.HTTP_400_BAD_REQUEST)
        
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
    - company_logo: Логотип компании (shaxsiy kabinet uchun) (файл)
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
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    
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
        serializer = MediaQuestionnaireSerializer(questionnaire, context={'request': request})
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
    summary='Архивировать анкету медиа пространства / интерьерного журнала',
    description='''
    PATCH: Архивировать анкету медиа пространства / интерьерного журнала (is_deleted=True)
    
    Требуется авторизация и права администратора (is_staff=True)
    ''',
    responses={
        200: {'description': 'Анкета успешно архивирована'},
        403: {'description': 'Доступ запрещен. Только администраторы могут архивировать анкеты'},
        404: {'description': 'Анкета не найдена'}
    }
)
class MediaQuestionnaireArchiveView(views.APIView):
    """
    Архивировать анкету медиа пространства / интерьерного журнала
    PATCH /api/v1/accounts/media-questionnaires/{id}/archive/
    """
    permission_classes = [permissions.IsAuthenticated]
    
    def patch(self, request, pk):
        if not request.user.is_staff:
            raise PermissionDenied("Только администратор может архивировать анкету")
        try:
            questionnaire = MediaQuestionnaire.objects.get(pk=pk)
        except MediaQuestionnaire.DoesNotExist:
            raise NotFound("Анкета не найдена")
        
        questionnaire.is_deleted = True
        questionnaire.save()
        serializer = MediaQuestionnaireSerializer(questionnaire, context={'request': request})
        return Response(serializer.data, status=status.HTTP_200_OK)


@extend_schema(
    tags=['Media Questionnaires'],
    summary='Восстановить анкету медиа пространства / интерьерного журнала из архива',
    description='''
    PATCH: Восстановить анкету медиа пространства / интерьерного журнала из архива (is_deleted=False)
    
    Требуется авторизация и права администратора (is_staff=True)
    ''',
    responses={
        200: {'description': 'Анкета успешно восстановлена из архива'},
        403: {'description': 'Доступ запрещен. Только администраторы могут восстанавливать анкеты'},
        404: {'description': 'Анкета не найдена'}
    }
)
class MediaQuestionnaireRestoreView(views.APIView):
    """
    Восстановить анкету медиа пространства / интерьерного журнала из архива
    PATCH /api/v1/accounts/media-questionnaires/{id}/restore/
    """
    permission_classes = [permissions.IsAuthenticated]
    
    def patch(self, request, pk):
        if not request.user.is_staff:
            raise PermissionDenied("Только администратор может восстанавливать анкету")
        try:
            questionnaire = MediaQuestionnaire.objects.get(pk=pk)
        except MediaQuestionnaire.DoesNotExist:
            raise NotFound("Анкета не найдена")
        
        questionnaire.is_deleted = False
        questionnaire.save()
        serializer = MediaQuestionnaireSerializer(questionnaire, context={'request': request})
        return Response(serializer.data, status=status.HTTP_200_OK)


@extend_schema(
    tags=['Media Questionnaires'],
    summary='Удалить анкету медиа пространства / интерьерного журнала (полное удаление)',
    description='''
    DELETE: Полностью удалить анкету медиа пространства / интерьерного журнала из базы данных
    
    ⚠️ ВНИМАНИЕ: Это действие необратимо! Анкета будет полностью удалена из базы данных.
    
    Требуется:
    - Авторизация и права администратора (is_staff=True)
    - Подтверждение действия через параметр confirm=true в query string или в теле запроса
    
    Пример запроса:
    DELETE /api/v1/accounts/media-questionnaires/{id}/delete/?confirm=true
    или
    DELETE /api/v1/accounts/media-questionnaires/{id}/delete/
    Body: {"confirm": true}
    ''',
    parameters=[
        OpenApiParameter(
            name='confirm',
            type=bool,
            location=OpenApiParameter.QUERY,
            description='Подтверждение удаления (обязательно: true)',
            required=True,
        ),
    ],
    responses={
        204: {'description': 'Анкета успешно удалена'},
        400: {'description': 'Требуется подтверждение удаления (confirm=true)'},
        403: {'description': 'Доступ запрещен. Только администраторы могут удалять анкеты'},
        404: {'description': 'Анкета не найдена'}
    }
)
class MediaQuestionnaireDeleteView(views.APIView):
    """
    Полностью удалить анкету медиа пространства / интерьерного журнала из базы данных
    DELETE /api/v1/accounts/media-questionnaires/{id}/delete/
    """
    permission_classes = [permissions.IsAuthenticated]
    
    def delete(self, request, pk):
        if not request.user.is_staff:
            raise PermissionDenied("Только администратор может удалять анкету")
        
        # Проверка подтверждения
        confirm = request.query_params.get('confirm', 'false').lower() == 'true'
        if not confirm:
            # Проверяем в теле запроса
            if hasattr(request, 'data') and isinstance(request.data, dict):
                confirm = request.data.get('confirm', False)
                if isinstance(confirm, str):
                    confirm = confirm.lower() == 'true'
                else:
                    confirm = bool(confirm)
        
        if not confirm:
            return Response(
                {'error': 'Требуется подтверждение удаления. Добавьте параметр confirm=true в query string или в теле запроса.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            questionnaire = MediaQuestionnaire.objects.get(pk=pk)
        except MediaQuestionnaire.DoesNotExist:
            raise NotFound("Анкета не найдена")
        
        # Полное удаление из базы данных
        questionnaire.delete()
        return Response(
            {'message': 'Анкета успешно удалена из базы данных'},
            status=status.HTTP_204_NO_CONTENT
        )


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
            
            result_serializer = MediaQuestionnaireSerializer(questionnaire, context={'request': request})
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
        
        # Проверка email и phone
        if not questionnaire.email:
            return Response(
                {'error': 'Email не заполнен. Необходимо заполнить email перед модерацией.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        if not questionnaire.phone:
            return Response(
                {'error': 'Телефон не заполнен. Необходимо заполнить телефон перед модерацией.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Очищаем phone от + и пробелов для поиска
        clean_phone = ''.join(filter(str.isdigit, questionnaire.phone))
        
        # Проверка существования пользователя с таким email ИЛИ phone
        existing_user_by_email = User.objects.filter(email=questionnaire.email).first()
        existing_user_by_phone = User.objects.filter(phone=clean_phone).first()
        
        # Если пользователь существует, используем его, иначе создаем нового
        if existing_user_by_email:
            user = existing_user_by_email
        elif existing_user_by_phone:
            user = existing_user_by_phone
        else:
            # Создаем нового пользователя через create_user с email
            user = User.objects.create_user(
                phone=clean_phone,
                email=questionnaire.email,
                password=None,  # Пароль не требуется для модерации
                full_name=questionnaire.full_name,
                is_phone_verified=False,  # Email bilan yaratilgani uchun phone verified emas
                is_profile_completed=True,
            )
            group, _ = Group.objects.get_or_create(name='Дизайн')
            user.groups.add(group)
        
        # Создание Report (если еще не существует для этого пользователя)
        start_date = date.today()
        # Для Дизайн - 3 месяца
        end_date = start_date + timedelta(days=90)
        
        # Проверяем, есть ли уже активный Report для этого пользователя
        existing_report = Report.objects.filter(
            user=user,
            start_date=start_date
        ).first()
        
        if not existing_report:
            Report.objects.create(
                user=user,
                start_date=start_date,
                end_date=end_date
            )
        
        # Установка is_moderation=True
        questionnaire.is_moderation = True
        questionnaire.save()
        
        result_serializer = DesignerQuestionnaireSerializer(questionnaire, context={'request': request})
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
        
        # Проверка email и phone
        if not questionnaire.email:
            return Response(
                {'error': 'Email не заполнен. Необходимо заполнить email перед модерацией.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        if not questionnaire.phone:
            return Response(
                {'error': 'Телефон не заполнен. Необходимо заполнить телефон перед модерацией.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Очищаем phone от + и пробелов для поиска
        clean_phone = ''.join(filter(str.isdigit, questionnaire.phone))
        
        # Проверка существования пользователя с таким email ИЛИ phone
        existing_user_by_email = User.objects.filter(email=questionnaire.email).first()
        existing_user_by_phone = User.objects.filter(phone=clean_phone).first()
        
        # Если пользователь существует, используем его, иначе создаем нового
        if existing_user_by_email:
            user = existing_user_by_email
        elif existing_user_by_phone:
            user = existing_user_by_phone
        else:
            # Создаем нового пользователя через create_user с email
            user = User.objects.create_user(
                phone=clean_phone,
                email=questionnaire.email,
                password=None,  # Пароль не требуется для модерации
                full_name=questionnaire.full_name,
                is_phone_verified=False,  # Email bilan yaratilgani uchun phone verified emas
                is_profile_completed=True,
            )
            group, _ = Group.objects.get_or_create(name='Ремонт')
            user.groups.add(group)
        
        # Создание Report (если еще не существует для этого пользователя)
        start_date = date.today()
        # Для Ремонт - 1 год
        end_date = start_date + timedelta(days=365)
        
        # Проверяем, есть ли уже активный Report для этого пользователя
        existing_report = Report.objects.filter(
            user=user,
            start_date=start_date
        ).first()
        
        if not existing_report:
            Report.objects.create(
                user=user,
                start_date=start_date,
                end_date=end_date
            )
        
        # Установка is_moderation=True
        questionnaire.is_moderation = True
        questionnaire.save()
        
        result_serializer = RepairQuestionnaireSerializer(questionnaire, context={'request': request})
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
        
        # Проверка email и phone
        if not questionnaire.email:
            return Response(
                {'error': 'Email не заполнен. Необходимо заполнить email перед модерацией.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        if not questionnaire.phone:
            return Response(
                {'error': 'Телефон не заполнен. Необходимо заполнить телефон перед модерацией.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Очищаем phone от + и пробелов для поиска
        clean_phone = ''.join(filter(str.isdigit, questionnaire.phone))
        
        # Проверка существования пользователя с таким email ИЛИ phone
        existing_user_by_email = User.objects.filter(email=questionnaire.email).first()
        existing_user_by_phone = User.objects.filter(phone=clean_phone).first()
        
        # Если пользователь существует, используем его, иначе создаем нового
        if existing_user_by_email:
            user = existing_user_by_email
        elif existing_user_by_phone:
            user = existing_user_by_phone
        else:
            # Создаем нового пользователя через create_user с email
            user = User.objects.create_user(
                phone=clean_phone,
                email=questionnaire.email,
                password=None,  # Пароль не требуется для модерации
                full_name=questionnaire.full_name,
                is_phone_verified=False,  # Email bilan yaratilgani uchun phone verified emas
                is_profile_completed=True,
            )
            group, _ = Group.objects.get_or_create(name='Поставщик')
            user.groups.add(group)
        
        # Создание Report (если еще не существует для этого пользователя)
        start_date = date.today()
        # Для Поставщик - 1 год
        end_date = start_date + timedelta(days=365)
        
        # Проверяем, есть ли уже активный Report для этого пользователя
        existing_report = Report.objects.filter(
            user=user,
            start_date=start_date
        ).first()
        
        if not existing_report:
            Report.objects.create(
                user=user,
                start_date=start_date,
                end_date=end_date
            )
        
        # Установка is_moderation=True
        questionnaire.is_moderation = True
        questionnaire.save()
        
        result_serializer = SupplierQuestionnaireSerializer(questionnaire, context={'request': request})
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
        
        # Проверка email и phone
        if not questionnaire.email:
            return Response(
                {'error': 'Email не заполнен. Необходимо заполнить email перед модерацией.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        if not questionnaire.phone:
            return Response(
                {'error': 'Телефон не заполнен. Необходимо заполнить телефон перед модерацией.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Очищаем phone от + и пробелов для поиска
        clean_phone = ''.join(filter(str.isdigit, questionnaire.phone))
        
        # Проверка существования пользователя с таким email ИЛИ phone
        existing_user_by_email = User.objects.filter(email=questionnaire.email).first()
        existing_user_by_phone = User.objects.filter(phone=clean_phone).first()
        
        # Если пользователь существует, используем его, иначе создаем нового
        if existing_user_by_email:
            user = existing_user_by_email
        elif existing_user_by_phone:
            user = existing_user_by_phone
        else:
            # Создаем нового пользователя через create_user с email
            user = User.objects.create_user(
                phone=clean_phone,
                email=questionnaire.email,
                password=None,  # Пароль не требуется для модерации
                full_name=questionnaire.full_name,
                is_phone_verified=False,  # Email bilan yaratilgani uchun phone verified emas
                is_profile_completed=True,
            )
            group, _ = Group.objects.get_or_create(name='Медиа')
            user.groups.add(group)
        
        # Создание Report (если еще не существует для этого пользователя)
        start_date = date.today()
        # Для Медиа - 1 год
        end_date = start_date + timedelta(days=365)
        
        # Проверяем, есть ли уже активный Report для этого пользователя
        existing_report = Report.objects.filter(
            user=user,
            start_date=start_date
        ).first()
        
        if not existing_report:
            Report.objects.create(
                user=user,
                start_date=start_date,
                end_date=end_date
            )
        
        # Установка is_moderation=True
        questionnaire.is_moderation = True
        questionnaire.save()
        
        result_serializer = MediaQuestionnaireSerializer(questionnaire, context={'request': request})
        return Response(result_serializer.data, status=status.HTTP_200_OK)
