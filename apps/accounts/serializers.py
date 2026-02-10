from rest_framework import serializers
from drf_spectacular.utils import extend_schema_field, OpenApiTypes
from drf_spectacular.types import OpenApiTypes
from django.db.models import Q
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.conf import settings
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from django.urls import reverse
from django.utils.crypto import get_random_string
from django.utils import timezone
from datetime import timedelta
from django.core.files.uploadedfile import InMemoryUploadedFile, TemporaryUploadedFile
from .models import (
    SMSVerificationCode,
    DesignerQuestionnaire,
    RepairQuestionnaire,
    SupplierQuestionnaire,
    MediaQuestionnaire,
    QUESTIONNAIRE_GROUP_CHOICES,
)
from .utils import send_sms_via_smsaero, generate_sms_code

User = get_user_model()


def _choice_display_to_key_list(data, field_name, choices_tuples):
    """Convert list field values from display names to keys (PUT: frontend sends display names)."""
    if field_name not in data and not (hasattr(data, 'getlist') and data.getlist(field_name)):
        return
    rev = {str(label): key for key, label in choices_tuples}
    if hasattr(data, 'getlist'):
        vals = data.getlist(field_name)
    else:
        v = data.get(field_name)
        vals = v if isinstance(v, list) else ([v] if v is not None and v != '' else [])
    if not vals:
        return
    converted = [rev.get(str(item).strip(), item) for item in vals]
    if hasattr(data, '_mutable') and not data._mutable:
        data._mutable = True
    if hasattr(data, 'setlist'):
        data.setlist(field_name, converted)
    else:
        data[field_name] = converted


def _choice_display_to_key_single(data, field_name, choices_tuples):
    """Convert single choice field from display name to key (PUT: frontend sends display name)."""
    if hasattr(data, 'getlist'):
        v = data.getlist(field_name)
        val = v[0] if v else None
    else:
        val = data.get(field_name)
    if val is None or (isinstance(val, str) and val.strip() == ''):
        return
    rev = {str(label): key for key, label in choices_tuples}
    converted = rev.get(str(val).strip(), val)
    if hasattr(data, '_mutable') and not data._mutable:
        data._mutable = True
    data[field_name] = converted


class RegisterSerializer(serializers.Serializer):
    """
    Registratsiya - telefon, email, parol, first_name, last_name, groups
    """
    phone = serializers.CharField(
        max_length=20,
        required=True,
        help_text="Телефонный номер (например: +79991234567)"
    )
    email = serializers.EmailField(
        required=True,
        help_text="Email адрес"
    )
    password = serializers.CharField(
        write_only=True,
        required=True,
        min_length=8,
        help_text="Пароль (минимум 8 символов)"
    )
    first_name = serializers.CharField(
        max_length=150,
        required=False,
        allow_blank=True,
        help_text="Имя"
    )
    last_name = serializers.CharField(
        max_length=150,
        required=False,
        allow_blank=True,
        help_text="Фамилия"
    )
    groups = serializers.PrimaryKeyRelatedField(
        many=True,
        queryset=Group.objects.all(),
        required=False,
        help_text="Список ID групп (массив чисел)"
    )
    
    def validate_phone(self, value):
        """Telefon raqamini tozalash va tekshirish"""
        clean_phone = ''.join(filter(str.isdigit, value))
        
        if len(clean_phone) < 9:
            raise serializers.ValidationError("Телефонный номер слишком короткий")
        if len(clean_phone) > 15:
            raise serializers.ValidationError("Телефонный номер слишком длинный")
        
        # Telefon raqami allaqachon mavjudligini tekshirish
        if User.objects.filter(phone=clean_phone).exists():
            raise serializers.ValidationError("Пользователь с таким телефоном уже существует")
        
        return clean_phone
    
    def validate_email(self, value):
        """Email allaqachon mavjudligini tekshirish"""
        if User.objects.filter(email=value).exists():
            raise serializers.ValidationError("Пользователь с таким email уже существует")
        return value
    
    def validate_groups(self, value):
        """Groups tekshirish"""
        if value:
            # Har bir group mavjudligini tekshirish
            group_ids = [g.id for g in value]
            existing_groups = Group.objects.filter(id__in=group_ids)
            if existing_groups.count() != len(group_ids):
                raise serializers.ValidationError("Одна или несколько групп не найдены")
        return value
    
    def create(self, validated_data):
        phone = validated_data['phone']
        email = validated_data['email']
        password = validated_data['password']
        first_name = validated_data.get('first_name', '')
        last_name = validated_data.get('last_name', '')
        groups = validated_data.get('groups', [])
        
        # User yaratish
        user = User.objects.create_user(
            phone=phone,
            email=email,
            password=password,
            first_name=first_name,
            last_name=last_name,
            is_phone_verified=False,  # SMS kod kiritilgandan keyin True bo'ladi
        )
        
        # Groups qo'shish
        if groups:
            user.groups.set(groups)
        
        # SMS kod yuborish
        code = generate_sms_code()
        SMSVerificationCode.objects.filter(
            phone=phone,
            is_used=False
        ).update(is_used=True)
        
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
        
        return sms_code


class LoginSerializer(serializers.Serializer):
    """
    Login - telefon/email + parol
    """
    login = serializers.CharField(
        required=True,
        help_text="Телефон или email"
    )
    password = serializers.CharField(
        write_only=True,
        required=True,
        help_text="Пароль"
    )
    
    def validate(self, attrs):
        login = attrs['login']
        password = attrs['password']
        
        # Telefon yoki email bo'yicha user topish
        clean_login = login.strip()
        
        # Email formatini tekshirish
        is_email = '@' in clean_login
        
        if is_email:
            try:
                user = User.objects.get(email=clean_login)
            except User.DoesNotExist:
                raise serializers.ValidationError({
                    'login': 'Пользователь с таким email не найден'
                })
        else:
            # Telefon formatini tozalash
            clean_phone = ''.join(filter(str.isdigit, clean_login))
            try:
                user = User.objects.get(phone=clean_phone)
            except User.DoesNotExist:
                raise serializers.ValidationError({
                    'login': 'Пользователь с таким телефоном не найден'
                })
        
        # Parolni tekshirish
        if not user.check_password(password):
            raise serializers.ValidationError({
                'password': 'Неверный пароль'
            })
        
        if not user.is_active:
            raise serializers.ValidationError({
                'login': 'Аккаунт деактивирован'
            })
        
        attrs['user'] = user
        return attrs


class CheckPhoneSerializer(serializers.Serializer):
    """
    Telefon raqamini tekshirish va SMS yuborish
    """
    phone = serializers.CharField(
        max_length=20,
        required=True,
        help_text="Телефонный номер"
    )
    
    def validate_phone(self, value):
        """Telefon raqamini tozalash va tekshirish"""
        clean_phone = ''.join(filter(str.isdigit, value))
        if not clean_phone:
            raise serializers.ValidationError("Неверный формат телефона")
        return clean_phone


class VerifyLoginCodeSerializer(serializers.Serializer):
    """
    SMS kodni tekshirish va telefonni tasdiqlash
    """
    phone = serializers.CharField(
        max_length=20,
        required=True,
        help_text="Телефонный номер"
    )
    code = serializers.CharField(
        max_length=6,
        required=True,
        help_text="SMS код"
    )
    
    def validate_phone(self, value):
        """Telefon raqamini tozalash"""
        clean_phone = ''.join(filter(str.isdigit, value))
        if not clean_phone:
            raise serializers.ValidationError("Неверный формат телефона")
        return clean_phone
    
    def validate(self, attrs):
        phone = attrs['phone']
        code = attrs['code']
        
        # User topish
        try:
            user = User.objects.get(phone=phone)
        except User.DoesNotExist:
            raise serializers.ValidationError({
                'phone': 'Пользователь с таким телефоном не найден'
            })
        
        # SMS kodni tekshirish
        try:
            sms_code = SMSVerificationCode.objects.get(
                phone=phone,
                code=code,
                is_used=False
            )
        except SMSVerificationCode.DoesNotExist:
            raise serializers.ValidationError({
                'code': 'Неверный код или код уже использован'
            })
        
        # Kod muddati tugaganligini tekshirish
        if not sms_code.is_valid():
            raise serializers.ValidationError({
                'code': 'Код истек. Запросите новый код.'
            })
        
        # Kodni ishlatilgan deb belgilash
        sms_code.is_used = True
        sms_code.save()
        
        # Telefonni tasdiqlash
        user.is_phone_verified = True
        user.save()
        
        attrs['user'] = user
        return attrs


class NewPhoneLoginSerializer(serializers.Serializer):
    """
    Yangi login - telefon + parol (parol bo'sh bo'lishi mumkin)
    """
    phone = serializers.CharField(
        max_length=20,
        required=True,
        help_text="Телефонный номер"
    )
    password = serializers.CharField(
        write_only=True,
        required=False,
        allow_blank=True,
        help_text="Пароль (может быть пустым для новых пользователей)"
    )
    
    def validate_phone(self, value):
        """Telefon raqamini tozalash"""
        clean_phone = ''.join(filter(str.isdigit, value))
        if not clean_phone:
            raise serializers.ValidationError("Неверный формат телефона")
        return clean_phone
    
    def validate(self, attrs):
        phone = attrs['phone']
        password = attrs.get('password', '')
        
        # User topish
        try:
            user = User.objects.get(phone=phone)
        except User.DoesNotExist:
            raise serializers.ValidationError({
                'phone': 'Пользователь с таким телефоном не найден'
            })
        
        # User aktivligini tekshirish
        if not user.is_active:
            raise serializers.ValidationError({
                'phone': 'Аккаунт деактивирован'
            })
        
        # Agar user parol o'rnatgan bo'lsa, parol talab qilinadi
        if user.has_usable_password():
            if not password:
                raise serializers.ValidationError({
                    'password': 'Пароль обязателен для этого пользователя'
                })
            # Parolni tekshirish
            if not user.check_password(password):
                raise serializers.ValidationError({
                    'password': 'Неверный пароль'
                })
        # Agar parol o'rnatilmagan bo'lsa (yangi user), parol bo'sh bo'lishi mumkin
        
        attrs['user'] = user
        return attrs


class ForgotPasswordSerializer(serializers.Serializer):
    """
    Parolni unutish - email orqali
    """
    email = serializers.EmailField(
        required=True,
        help_text="Email адрес"
    )


class ResetPasswordSerializer(serializers.Serializer):
    """
    Parolni tiklash - token + yangi parol
    """
    token = serializers.CharField(
        required=True,
        help_text="Токен для сброса пароля"
    )
    new_password = serializers.CharField(
        write_only=True,
        required=True,
        min_length=8,
        help_text="Новый пароль (минимум 8 символов)"
    )


class ChangePasswordSerializer(serializers.Serializer):
    """
    Parolni o'zgartirish - eski + yangi parol
    """
    old_password = serializers.CharField(
        write_only=True,
        required=True,
        help_text="Старый пароль"
    )
    new_password = serializers.CharField(
        write_only=True,
        required=True,
        min_length=8,
        help_text="Новый пароль (минимум 8 символов)"
    )
    
    def validate_old_password(self, value):
        """Eski parolni tekshirish"""
        user = self.context['request'].user
        if not user.check_password(value):
            raise serializers.ValidationError("Неверный старый пароль")
        return value


class ChangePhoneNumberSerializer(serializers.Serializer):
    """
    Telefon raqamini o'zgartirish - yangi raqam
    """
    new_phone = serializers.CharField(
        max_length=20,
        required=True,
        help_text="Новый телефонный номер"
    )
    
    def validate_new_phone(self, value):
        """Yangi telefon raqamini tozalash va tekshirish"""
        clean_phone = ''.join(filter(str.isdigit, value))
        
        if len(clean_phone) < 9:
            raise serializers.ValidationError("Телефонный номер слишком короткий")
        if len(clean_phone) > 15:
            raise serializers.ValidationError("Телефонный номер слишком длинный")
        
        # Yangi telefon raqami allaqachon mavjudligini tekshirish
        if User.objects.filter(phone=clean_phone).exists():
            raise serializers.ValidationError("Пользователь с таким телефоном уже существует")
        
        return clean_phone


class VerifyPhoneCodeSerializer(serializers.Serializer):
    """
    SMS kodni tasdiqlash - telefon va kod
    """
    phone = serializers.CharField(
        max_length=20,
        required=True,
        help_text="Телефонный номер"
    )
    code = serializers.CharField(
        max_length=6,
        required=True,
        help_text="SMS код"
    )
    
    def validate_phone(self, value):
        """Telefon raqamini tozalash"""
        return ''.join(filter(str.isdigit, value))


class VerifyPhoneChangeSerializer(serializers.Serializer):
    """
    Telefon raqamini o'zgartirish - SMS kodni tasdiqlash
    """
    new_phone = serializers.CharField(
        max_length=20,
        required=True,
        help_text="Новый телефонный номер"
    )
    code = serializers.CharField(
        max_length=6,
        required=True,
        help_text="SMS код"
    )


class PhoneLoginSerializer(serializers.Serializer):
    """
    Telefon raqami orqali login - SMS kod yuborish
    """
    phone = serializers.CharField(
        max_length=20,
        required=True,
        help_text="Телефонный номер (например: +79991234567)"
    )
    
    def validate_phone(self, value):
        """Telefon raqamini tozalash va tekshirish"""
        # Faqat raqamlarni qoldirish
        clean_phone = ''.join(filter(str.isdigit, value))
        
        # Minimal uzunlik tekshiruvi
        if len(clean_phone) < 9:
            raise serializers.ValidationError("Телефонный номер слишком короткий")
        
        # Maksimal uzunlik tekshiruvi (998... yoki 7... formatida)
        if len(clean_phone) > 15:
            raise serializers.ValidationError("Телефонный номер слишком длинный")
        
        return clean_phone
    
    def create(self, validated_data):
        phone = validated_data['phone']
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
        
        # O'zbekiston raqamlari uchun SMS service'ga so'rov yuborilmaydi
        clean_phone = ''.join(filter(str.isdigit, phone))
        is_uzbekistan = clean_phone.startswith('998')
        
        if is_uzbekistan:
            # O'zbekiston raqamlari uchun SMS service'ga so'rov yuborilmaydi
            # Kod to'g'ridan-to'g'ri response'ga qo'shiladi
            return sms_code
        
        # Boshqa raqamlar uchun SMS yuborish
        try:
            result = send_sms_via_smsaero(phone, code)
        except Exception as e:
            # Production rejimida xatolikni ko'rsatamiz
            error_msg = str(e)
            if '400' in error_msg or 'Bad Request' in error_msg:
                error_msg = "Ошибка отправки SMS. Проверьте настройки SMS Aero (email, API key, sign) и формат телефона."
            elif '401' in error_msg or 'Unauthorized' in error_msg:
                error_msg = "Ошибка авторизации SMS Aero. Проверьте email и API key в .env файле."
            elif '403' in error_msg or 'Forbidden' in error_msg:
                error_msg = "Доступ запрещен. Проверьте права доступа к SMS Aero API."
            
            raise serializers.ValidationError({
                'phone': error_msg
            })
        
        return sms_code


class VerifySMSCodeSerializer(serializers.Serializer):
    """
    SMS kodni tekshirish va token olish
    """
    phone = serializers.CharField(
        max_length=20,
        required=True
    )
    code = serializers.CharField(
        max_length=6,
        required=True
    )
    
    def validate(self, attrs):
        phone = attrs['phone']
        code = attrs['code']
        
        # Faqat raqamlarni qoldirish
        phone = ''.join(filter(str.isdigit, phone))
        
        # Kodni topish
        try:
            sms_code = SMSVerificationCode.objects.get(
                phone=phone,
                code=code,
                is_used=False
            )
        except SMSVerificationCode.DoesNotExist:
            raise serializers.ValidationError({
                'code': 'Неверный код'
            })
        
        # Kod amal qiladimi tekshirish
        if not sms_code.is_valid():
            raise serializers.ValidationError({
                'code': 'Срок действия кода истек'
            })
        
        # Kodni ishlatilgan deb belgilash
        sms_code.is_used = True
        sms_code.save()
        
        attrs['sms_code'] = sms_code
        return attrs


class AdminLoginSerializer(serializers.Serializer):
    """
    Admin login serializer - phone va password bilan
    """
    phone = serializers.CharField(
        max_length=20,
        required=True,
        help_text='Телефонный номер'
    )
    password = serializers.CharField(
        write_only=True,
        required=True,
        help_text='Пароль'
    )
    
    def validate(self, attrs):
        phone = attrs['phone']
        password = attrs['password']
        
        # Faqat raqamlarni qoldirish
        clean_phone = ''.join(filter(str.isdigit, phone))
        
        # User'ni topish
        try:
            user = User.objects.get(phone=clean_phone)
        except User.DoesNotExist:
            raise serializers.ValidationError({
                'phone': 'Пользователь не найден'
            })
        
        # is_staff tekshiruvi
        if not user.is_staff:
            raise serializers.ValidationError({
                'phone': 'Доступ запрещен. Только администраторы могут войти через этот метод.'
            })
        
        # Password tekshiruvi
        if not user.check_password(password):
            raise serializers.ValidationError({
                'password': 'Неверный пароль'
            })
        
        # User aktivligini tekshirish
        if not user.is_active:
            raise serializers.ValidationError({
                'phone': 'Аккаунт деактивирован'
            })
        
        attrs['user'] = user
        return attrs


class UserProfileSerializer(serializers.ModelSerializer):
    """
    Foydalanuvchi profil serializer
    Faqat: first_name, last_name, phone, email, photo
    """
    photo = serializers.ImageField(
        required=False,
        allow_null=True,
        help_text="Фото пользователя"
    )

    groups = serializers.SerializerMethodField()
    
    def get_groups(self, obj):
        return obj.groups.values_list('name', flat=True)
    
    class Meta:
        model = User
        fields = [
            'first_name',
            'last_name',
            'phone',
            'email',
            'photo',
            'groups',
        ]
        read_only_fields = [
            'phone',  # Telefon raqamini o'zgartirish alohida API orqali
        ]


class UserPublicSerializer(serializers.ModelSerializer):
    """
    Umumiy ko'rinish uchun foydalanuvchi serializer
    (Boshqa foydalanuvchilar ko'rish uchun).
    company_name: agar null bo'lsa — full_name yoki anketadagi ism/brand_name chiqadi.
    """
    role_display = serializers.CharField(
        source='get_role_display',
        read_only=True
    )
    
    groups = serializers.SerializerMethodField()
    company_name = serializers.SerializerMethodField()
    
    def get_groups(self, obj):
        return obj.groups.values_list('name', flat=True)
    
    def _norm_phone(self, s):
        """Faqat raqamlar — anketada telefon turli formatda bo'lishi mumkin."""
        return ''.join(c for c in (s or '') if c.isdigit())

    def _find_questionnaire_for_user(self, obj, phone_digits, email_lower):
        """
        User guruhiga qarab BITTА anketani topadi.
        Дизайн → DesignerQuestionnaire (full_name);
        Ремонт/Поставщик/Медиа → o'sha model (brand_name).
        Qidirish: telefon faqat raqamda yoki email.
        """
        group_to_model = [
            ('Дизайн', DesignerQuestionnaire, 'full_name'),
            ('Ремонт', RepairQuestionnaire, 'brand_name'),
            ('Поставщик', SupplierQuestionnaire, 'brand_name'),
            ('Медиа', MediaQuestionnaire, 'brand_name'),
        ]
        group_names = list(obj.groups.values_list('name', flat=True))

        def match_questionnaire(q):
            if phone_digits and self._norm_phone(getattr(q, 'phone', None)) == phone_digits:
                return True
            if email_lower and getattr(q, 'email', None):
                if (q.email or '').strip().lower() == email_lower:
                    return True
            return False

        def get_value(q, attr):
            if attr == 'full_name':
                return (getattr(q, 'full_name') or getattr(q, 'full_name_en', None) or '').strip()
            return (getattr(q, attr, None) or '').strip()

        def query_model(model):
            qs = model.objects.filter(is_deleted=False)
            if email_lower:
                qs = qs.filter(Q(email__iexact=email_lower))
            if phone_digits and len(phone_digits) >= 9:
                qs = qs.filter(Q(phone__icontains=phone_digits[-9:]) | Q(phone=phone_digits) | Q(phone__icontains=phone_digits))
            return qs

        # Avval user guruhiga mos anketani qidirish (faqat shu guruh)
        for group_name, model, attr in group_to_model:
            if group_name not in group_names:
                continue
            for q in query_model(model):
                if match_questionnaire(q):
                    val = get_value(q, attr)
                    if val:
                        return val
                    # Repair/Supplier/Media da full_name frontend dan kelmaydi — doim brand_name
                    if attr == 'brand_name':
                        return val or None

        # Topilmasa barcha anketalarda qidirish (fallback)
        for _gr, model, attr in group_to_model:
            for q in query_model(model):
                if match_questionnaire(q):
                    val = get_value(q, attr)
                    if val:
                        return val
                    if attr == 'brand_name':
                        return val or None
        return None

    @extend_schema_field(OpenApiTypes.STR)
    def get_company_name(self, obj):
        """
        company_name: profil → full_name → user guruhiga tegishli anketa.
        Дизайн → full_name; Ремонт/Поставщик/Медиа → doim brand_name.
        """
        if obj.company_name:
            return obj.company_name
        if obj.full_name:
            return obj.full_name
        phone = (getattr(obj, 'phone', None) or '').strip()
        email = (getattr(obj, 'email', None) or '').strip().lower() or None
        phone_digits = self._norm_phone(phone) if phone else None
        if not phone_digits and not email:
            return None
        return self._find_questionnaire_for_user(obj, phone_digits, email)
    
    class Meta:
        model = User
        fields = [
            'id',
            'full_name',
            'photo',
            'groups',
            'phone',
            'email',
            'description',
            'city',
            'website',
            'telegram',
            'instagram',
            'vk',
            'company_name',
            'team_name',
            'role',
            'role_display',
            'share_url',
        ]
        read_only_fields = [
            'id',
            'user_name',
            'user_phone',
            'user_role',
            'user_role_display',
            'share_url',
        ]


class DesignerQuestionnaireSerializer(serializers.ModelSerializer):
    """
    Анкета дизайнера serializer
    """
    request_name = serializers.SerializerMethodField()
    group_display = serializers.CharField(
        source='get_group_display',
        read_only=True
    )
    work_type_display = serializers.CharField(
        source='get_work_type_display',
        read_only=True
    )
    vat_payment_display = serializers.CharField(
        source='get_vat_payment_display',
        read_only=True
    )
    about_company = serializers.SerializerMethodField()
    terms_of_cooperation = serializers.SerializerMethodField()
    rating_count = serializers.SerializerMethodField()
    rating_list = serializers.SerializerMethodField()
    reviews_list = serializers.SerializerMethodField()
    
    @extend_schema_field(str)
    def get_request_name(self, obj):
        # group ga qarab to'g'ri request_name qaytaramiz
        if obj.group == 'media':
            return 'MediaQuestionnaire'
        elif obj.group == 'supplier':
            return 'SupplierQuestionnaire'
        elif obj.group == 'repair':
            return 'RepairQuestionnaire'
        return 'DesignerQuestionnaire'
    
    @extend_schema_field(dict)
    def get_rating_count(self, obj):
        """Rating count: total, positive, constructive"""
        # Context'dan cache'dan olish (agar mavjud bo'lsa)
        ratings_cache = self.context.get('ratings_cache', {})
        key = f"Дизайн_{obj.id}"
        if key in ratings_cache:
            stats = ratings_cache[key]
            return {
                'total': stats['total_positive'],
                'positive': stats['total_positive'],
                'constructive': stats['total_constructive'],
            }
        
        # Agar context yo'q bo'lsa, eski usul (fallback)
        from apps.ratings.models import QuestionnaireRating
        ratings = QuestionnaireRating.objects.filter(
            role='Дизайн',
            questionnaire_id=obj.id,
            status='approved'
        )
        positive_count = ratings.filter(is_positive=True).count()
        return {
            'total': positive_count,
            'positive': positive_count,
            'constructive': ratings.filter(is_constructive=True).count(),
        }
    
    @extend_schema_field(list)
    def get_rating_list(self, obj):
        """Rating list - barcha approved rating'lar"""
        # Context'dan cache'dan olish (agar mavjud bo'lsa)
        ratings_list_cache = self.context.get('ratings_list_cache', {})
        rating_serializer = self.context.get('rating_serializer')
        key = f"Дизайн_{obj.id}"
        if key in ratings_list_cache and rating_serializer:
            ratings = sorted(ratings_list_cache[key], key=lambda x: x.created_at, reverse=True)
            # skip_questionnaire=True qo'yamiz, chunki recursive muammo bo'lmasligi uchun
            context = self.context.copy()
            context['skip_questionnaire'] = True
            return rating_serializer(ratings, many=True, context=context).data
        
        # Agar context yo'q bo'lsa, eski usul (fallback)
        from apps.ratings.models import QuestionnaireRating
        from apps.ratings.serializers import QuestionnaireRatingSerializer
        ratings = QuestionnaireRating.objects.filter(
            role='Дизайн',
            questionnaire_id=obj.id,
            status='approved'
        ).order_by('-created_at')
        context = {'skip_questionnaire': True}
        return QuestionnaireRatingSerializer(ratings, many=True, context=context).data
    
    @extend_schema_field(list)
    def get_reviews_list(self, obj):
        """Reviews list - faqat approved review'lar (pending va rejected tashqari)"""
        # Context'dan cache'dan olish (agar mavjud bo'lsa)
        ratings_list_cache = self.context.get('ratings_list_cache', {})
        rating_serializer = self.context.get('rating_serializer')
        key = f"Дизайн_{obj.id}"
        if key in ratings_list_cache and rating_serializer:
            reviews = sorted(ratings_list_cache[key], key=lambda x: x.created_at, reverse=True)
            # skip_questionnaire=True qo'yamiz, chunki recursive muammo bo'lmasligi uchun
            context = self.context.copy()
            context['skip_questionnaire'] = True
            return rating_serializer(reviews, many=True, context=context).data
        
        # Agar context yo'q bo'lsa, eski usul (fallback)
        from apps.ratings.models import QuestionnaireRating
        from apps.ratings.serializers import QuestionnaireRatingSerializer
        reviews = QuestionnaireRating.objects.filter(
            role='Дизайн',
            questionnaire_id=obj.id,
            status='approved'  # Faqat approved review'lar
        ).order_by('-created_at')
        context = {'skip_questionnaire': True}
        return QuestionnaireRatingSerializer(reviews, many=True, context=context).data
    
    @extend_schema_field(list)
    def get_about_company(self, obj):
        """
        О компании: ПРИВЕТСТВЕННОЕ СООБЩЕНИЕ ОТ ДИЗАЙНЕРА,
        СКОЛЬКО ЛЕТ В ПРОФЕССИИ, ГЕОГРАФИЯ, КАКИЕ ПАКЕТЫ УСЛУГ ПРЕДОСТАВЛЯЕТ И ИХ СТОИМОСТЬ,
        Акции и УТП, Социальные сети, ВИДЕО
        """
        about_company_data = []
        
        # ПРИВЕТСТВЕННОЕ СООБЩЕНИЕ ОТ ДИЗАЙНЕРА
        if obj.welcome_message:
            about_company_data.append({
                'type': 'welcome_message',
                'label': 'ПРИВЕТСТВЕННОЕ СООБЩЕНИЕ ОТ ДИЗАЙНЕРА',
                'value': obj.welcome_message
            })
        
        # СКОЛЬКО ЛЕТ В ПРОФЕССИИ, ГЕОГРАФИЯ
        geography_info = {}
        if obj.welcome_message:
            # welcome_message ichida yil va geografiya bo'lishi mumkin
            geography_info['description'] = obj.welcome_message
        if obj.work_cities:
            geography_info['work_cities'] = obj.work_cities
        if obj.city:
            geography_info['city'] = obj.city
        
        if geography_info:
            about_company_data.append({
                'type': 'experience_geography',
                'label': 'СКОЛЬКО ЛЕТ В ПРОФЕССИИ, ГЕОГРАФИЯ',
                'value': geography_info
            })
        
        # КАКИЕ ПАКЕТЫ УСЛУГ ПРЕДОСТАВЛЯЕТ И ИХ СТОИМОСТЬ
        if obj.service_packages_description:
            about_company_data.append({
                'type': 'service_packages',
                'label': 'КАКИЕ ПАКЕТЫ УСЛУГ ПРЕДОСТАВЛЯЕТ И ИХ СТОИМОСТЬ',
                'value': obj.service_packages_description
            })
        
        # Акции и УТП (+ условия договора и гарантии)
        if obj.unique_trade_proposal:
            about_company_data.append({
                'type': 'promotions_utp',
                'label': 'Акции и УТП (+ условия договора и гарантии)',
                'value': obj.unique_trade_proposal
            })
        
        # Социальные сети
        social_networks = {}
        if obj.vk:
            social_networks['vk'] = obj.vk
        if obj.telegram_channel:
            social_networks['telegram_channel'] = obj.telegram_channel
        if obj.pinterest:
            social_networks['pinterest'] = obj.pinterest
        if obj.instagram:
            social_networks['instagram'] = obj.instagram
        if obj.website:
            social_networks['website'] = obj.website
        if obj.other_contacts:
            social_networks['other_contacts'] = obj.other_contacts
        
        if social_networks:
            about_company_data.append({
                'type': 'social_networks',
                'label': 'Социальные сети',
                'value': social_networks
            })
        
        # ВИДЕО (видео контент) - bu field modelda yo'q, lekin keyinroq qo'shilishi mumkin
        # Hozircha bo'sh qoldiramiz
        
        return about_company_data
    
    @extend_schema_field(list)
    def get_terms_of_cooperation(self, obj):
        """
        Условия сотрудничества: В какие периоды осуществляется выполнение проекта 1к, 2 к, 3 к,
        НДС - да / нет, Гарантии, Условия работы с другими городами,
        Условия работы с учетом рекомендации
        """
        terms_data = []
        
        # В какие периоды осуществляется выполнение проекта 1к, 2 к, 3 к или по видам пакетов
        if obj.service_packages_description:
            terms_data.append({
                'type': 'project_periods',
                'label': 'В какие периоды осуществляется выполнение проекта 1к, 2 к, 3 к или по видам пакетов',
                'value': obj.service_packages_description
            })
        
        # НДС - да / нет
        if obj.vat_payment:
            terms_data.append({
                'type': 'vat_payment',
                'label': 'НДС',
                'value': obj.get_vat_payment_display(),
                'raw_value': obj.vat_payment
            })
        
        # Гарантии (unique_trade_proposal ichida yoki alohida)
        if obj.unique_trade_proposal:
            terms_data.append({
                'type': 'guarantees',
                'label': 'Гарантии',
                'value': obj.unique_trade_proposal
            })
        
        # Условия работы с другими городами
        if obj.cooperation_terms:
            terms_data.append({
                'type': 'other_cities_terms',
                'label': 'Условия работы с другими городами',
                'value': obj.cooperation_terms
            })
        
        # Условия работы с учетом рекомендации
        if obj.supplier_contractor_recommendation_terms:
            terms_data.append({
                'type': 'recommendation_terms',
                'label': 'Условия работы с учетом рекомендации (описание позиций и % от продажи) когда выплачивается процент',
                'value': obj.supplier_contractor_recommendation_terms
            })
        
        return terms_data
    
    status_display = serializers.CharField(
        source='get_status_display',
        read_only=True
    )
    
    # Multiple choice fields for Swagger - ListField without child validation
    services = serializers.ListField(
        child=serializers.CharField(),
        required=False,
        allow_empty=True,
        help_text="Список услуг (multiple choice). Пример: ['author_supervision', 'architecture']"
    )
    
    segments = serializers.ListField(
        child=serializers.CharField(),
        required=False,
        allow_empty=True,
        help_text="Список сегментов (multiple choice). Пример: ['horeca', 'business', 'premium']"
    )
    
    categories = serializers.ListField(
        child=serializers.CharField(),
        required=False,
        allow_empty=True,
        help_text="Категории (multiple choice). Пример: ['residential_designer', 'decorator']"
    )
    
    purpose_of_property = serializers.ListField(
        child=serializers.CharField(),
        required=False,
        allow_empty=True,
        help_text="Назначение недвижимости (multiple choice). Пример: ['permanent_residence', 'commercial']"
    )
    
    area_of_object = serializers.CharField(required=False, allow_null=True, allow_blank=True, help_text="Площадь объекта: до 10 м2, до 40 м 2, до 80 м 2, дома")
    cost_per_m2 = serializers.CharField(required=False, allow_null=True, allow_blank=True, help_text="Стоимость за м²: До 1500 р, до 2500р, до 4000 р, свыше 4000 р")
    experience = serializers.CharField(required=False, allow_null=True, allow_blank=True, help_text="Опыт работы: Новичок, До 2 лет, 2-5 лет, 5-10 лет, Свыше 10 лет")
    
    def to_representation(self, instance):
        """Convert choice keys to display names in response"""
        data = super().to_representation(instance)
        
        # Convert services keys to display names
        if 'services' in data and data['services'] is not None:
            choices_dict = dict(DesignerQuestionnaire.SERVICES_CHOICES)
            data['services'] = [choices_dict.get(service, service) for service in data['services']]
        
        # Convert segments keys to display names
        if 'segments' in data and data['segments'] is not None:
            choices_dict = dict(DesignerQuestionnaire.SEGMENT_CHOICES)
            data['segments'] = [choices_dict.get(segment, segment) for segment in data['segments']]
        
        # Convert categories keys to display names
        if 'categories' in data and data['categories'] is not None:
            choices_dict = dict(DesignerQuestionnaire.CATEGORY_CHOICES)
            data['categories'] = [choices_dict.get(c, c) for c in data['categories']]
        
        # Convert purpose_of_property keys to display names
        if 'purpose_of_property' in data and data['purpose_of_property'] is not None:
            choices_dict = dict(DesignerQuestionnaire.PURPOSE_OF_PROPERTY_CHOICES)
            data['purpose_of_property'] = [choices_dict.get(p, p) for p in data['purpose_of_property']]
        
        # Convert work_type key to display name
        if 'work_type' in data and data['work_type'] is not None:
            data['work_type'] = instance.get_work_type_display()
        
        # experience, area_of_object, cost_per_m2 — уже строки (текстовие варианты), возвращаем как есть
        
        # Convert vat_payment key to display name
        if 'vat_payment' in data and data['vat_payment'] is not None:
            data['vat_payment'] = instance.get_vat_payment_display()
        
        # Convert status key to display name
        if 'status' in data and data['status'] is not None:
            data['status'] = instance.get_status_display()
        
        # Convert group key to display name
        if 'group' in data and data['group'] is not None:
            data['group'] = instance.get_group_display()
        
        return data
    
    # JSONField fields - work_cities, other_contacts
    # ListField ishlatamiz, chunki JSONField form-data bilan muammo qilmoqda
    work_cities = serializers.ListField(
        child=serializers.CharField(),
        required=False,
        allow_empty=True,
        help_text="Города работы (JSON array). Пример: ['Ташкент', 'Самарканд']"
    )
    other_contacts = serializers.ListField(
        child=serializers.CharField(),
        required=False,
        allow_empty=True,
        help_text="Другие контакты (JSON array). Пример: ['contact1', 'contact2']"
    )
    
    class Meta:
        model = DesignerQuestionnaire
        fields = [
            'id',
            'request_name',
            'group',
            'group_display',
            'status',
            'status_display',
            'full_name',
            'full_name_en',
            'phone',
            'birth_date',
            'email',
            'city',
            'services',
            'work_type',
            'work_type_display',
            'segments',
            'unique_trade_proposal',
            'vk',
            'telegram_channel',
            'pinterest',
            'instagram',
            'website',
            'work_cities',
            'other_contacts',
            'service_packages_description',
            'vat_payment',
            'vat_payment_display',
            'supplier_contractor_recommendation_terms',
            'additional_info',
            'about_company',
            'terms_of_cooperation',
            'rating_count',
            'rating_list',
            'reviews_list',
            'data_processing_consent',
            'photo',
            'categories',
            'purpose_of_property',
            'area_of_object',
            'cost_per_m2',
            'experience',
            'created_at',
            'updated_at',
        ]
        read_only_fields = [
            'id',
            'status',
            'created_at',
            'updated_at',
        ]
        extra_kwargs = {
            field: {'required': False} for field in [
                'full_name', 'full_name_en', 'phone', 'birth_date', 'email', 'city',
                'services', 'work_type', 'segments', 'unique_trade_proposal',
                'categories', 'purpose_of_property', 'area_of_object', 'cost_per_m2', 'experience',
                'vk', 'telegram_channel', 'pinterest', 'instagram', 'website',
                'other_contacts', 'service_packages_description', 'vat_payment',
                'supplier_contractor_recommendation_terms', 'additional_info',
                'data_processing_consent', 'photo', 'work_cities', 'cooperation_terms',
                'welcome_message', 'group'
            ]
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # PUT request uchun barcha fieldlarni required=False qilish
        if self.partial:
            for field_name, field in self.fields.items():
                if field_name not in self.Meta.read_only_fields:
                    field.required = False
    
    def to_internal_value(self, data):
        """Parse JSON fields from form-data"""
        # Form-data orqali kelganda, JSON maydonlar string sifatida keladi
        if hasattr(data, 'get'):
            # Multiple choice fields - vergul bilan ajratilgan stringlar
            multiple_choice_fields = ['services', 'segments', 'categories', 'purpose_of_property']
            for field in multiple_choice_fields:
                if field in data:
                    value = data.get(field)
                    # Agar allaqachon list bo'lsa, hech narsa qilmaymiz
                    if isinstance(value, list):
                        continue
                    if isinstance(value, str):
                        # Agar string bo'lsa, JSON parse qilishga harakat qilamiz
                        try:
                            import json
                            # QueryDict bo'lsa, mutable copy olish kerak
                            if hasattr(data, '_mutable') and not data._mutable:
                                data._mutable = True
                            parsed = json.loads(value)
                            # Agar list bo'lsa, to'g'ridan-to'g'ri o'rnatamiz
                            if isinstance(parsed, list):
                                # List elementlarini string ga o'zgartirish (CharField uchun)
                                parsed_list = [str(item) for item in parsed if item is not None]
                                # QueryDict da listni o'rnatish uchun setlist yoki __setitem__ ishlatamiz
                                if hasattr(data, '_mutable') and not data._mutable:
                                    data._mutable = True
                                if hasattr(data, 'setlist'):
                                    data.setlist(field, parsed_list)
                                else:
                                    data[field] = parsed_list
                            else:
                                # Agar list bo'lmasa, listga o'zgartiramiz
                                parsed_list = [str(parsed)] if parsed else []
                                if hasattr(data, '_mutable') and not data._mutable:
                                    data._mutable = True
                                if hasattr(data, 'setlist'):
                                    data.setlist(field, parsed_list)
                                else:
                                    data[field] = parsed_list
                        except (json.JSONDecodeError, ValueError):
                            # Agar JSON parse qilib bo'lmasa, vergul bilan ajratilgan string bo'lishi mumkin
                            # Masalan: "business,comfort" -> ["business", "comfort"]
                            if hasattr(data, '_mutable') and not data._mutable:
                                data._mutable = True
                            # Vergul bilan ajratilgan stringlarni listga o'zgartirish
                            if value.strip():
                                # Bo'sh bo'lmagan stringlarni listga o'zgartirish
                                parsed_list = [item.strip() for item in value.split(',') if item.strip()]
                                if hasattr(data, '_mutable') and not data._mutable:
                                    data._mutable = True
                                if hasattr(data, 'setlist'):
                                    data.setlist(field, parsed_list)
                                else:
                                    data[field] = parsed_list
                            else:
                                if hasattr(data, '_mutable') and not data._mutable:
                                    data._mutable = True
                                if hasattr(data, 'setlist'):
                                    data.setlist(field, [])
                                else:
                                    data[field] = []
            
            # ListField fields - work_cities, other_contacts (endi ListField ishlatamiz)
            list_fields = ['work_cities', 'other_contacts']
            for field in list_fields:
                if field in data:
                    value = data.get(field)
                    # Agar allaqachon list bo'lsa, hech narsa qilmaymiz
                    if isinstance(value, list):
                        continue
                    if isinstance(value, str):
                        # Agar string bo'lsa, JSON parse qilishga harakat qilamiz
                        try:
                            import json
                            # QueryDict bo'lsa, mutable copy olish kerak
                            if hasattr(data, '_mutable') and not data._mutable:
                                data._mutable = True
                            parsed = json.loads(value)
                            # Agar list bo'lsa, to'g'ridan-to'g'ri o'rnatamiz
                            if isinstance(parsed, list):
                                parsed_list = [str(item) for item in parsed if item is not None]
                                if hasattr(data, '_mutable') and not data._mutable:
                                    data._mutable = True
                                if hasattr(data, 'setlist'):
                                    data.setlist(field, parsed_list)
                                else:
                                    data[field] = parsed_list
                            else:
                                # Agar list bo'lmasa, listga o'zgartiramiz
                                parsed_list = [str(parsed)] if parsed else []
                                if hasattr(data, '_mutable') and not data._mutable:
                                    data._mutable = True
                                if hasattr(data, 'setlist'):
                                    data.setlist(field, parsed_list)
                                else:
                                    data[field] = parsed_list
                        except (json.JSONDecodeError, ValueError):
                            # Agar JSON parse qilib bo'lmasa, bo'sh list qaytaramiz
                            if hasattr(data, '_mutable') and not data._mutable:
                                data._mutable = True
                            if hasattr(data, 'setlist'):
                                data.setlist(field, [])
                            else:
                                data[field] = []
                    elif value is None or value == '':
                        # Agar None yoki bo'sh string bo'lsa, bo'sh list qaytaramiz
                        if hasattr(data, '_mutable') and not data._mutable:
                            data._mutable = True
                        if hasattr(data, 'setlist'):
                            data.setlist(field, [])
                        else:
                            data[field] = []
            
            # Website field uchun bo'sh stringlarni None ga o'zgartirish
            if 'website' in data:
                website_value = data.get('website')
                if isinstance(website_value, str) and not website_value.strip():
                    if hasattr(data, '_mutable') and not data._mutable:
                        data._mutable = True
                    data['website'] = None
            
            # File fields (photo, company_logo, legal_entity_card) uchun bo'sh stringlarni None ga o'zgartirish
            # Faqat string bo'lsa tekshiramiz, file obyektlarni o'zgartirmaymiz
            file_fields = ['photo', 'company_logo', 'legal_entity_card']
            for field in file_fields:
                if field in data:
                    file_value = data.get(field)
                    # Faqat string bo'lsa tekshiramiz (file obyektlarni o'zgartirmaymiz)
                    # File obyektlarni tekshirish uchun isinstance yoki hasattr ishlatamiz
                    if isinstance(file_value, str):
                        # Agar bo'sh string yoki 'null' string bo'lsa, None ga o'zgartirish
                        if not file_value.strip() or file_value.strip().lower() == 'null':
                            if hasattr(data, '_mutable') and not data._mutable:
                                data._mutable = True
                            data[field] = None
                    # Agar file obyekt bo'lsa (InMemoryUploadedFile, TemporaryUploadedFile), hech narsa qilmaymiz
                    # File obyektlarni o'zgartirmaymiz, chunki DRF ularni to'g'ri handle qiladi
                    elif isinstance(file_value, (InMemoryUploadedFile, TemporaryUploadedFile)):
                        # File obyektni o'zgartirmaymiz, to'g'ridan-to'g'ri o'tkazib yuboramiz
                        pass
            
            # PUT: frontend display name yuboradi, key ga aylantirish
            _choice_display_to_key_list(data, 'services', DesignerQuestionnaire.SERVICES_CHOICES)
            _choice_display_to_key_list(data, 'segments', DesignerQuestionnaire.SEGMENT_CHOICES)
            _choice_display_to_key_list(data, 'categories', DesignerQuestionnaire.CATEGORY_CHOICES)
            _choice_display_to_key_list(data, 'purpose_of_property', DesignerQuestionnaire.PURPOSE_OF_PROPERTY_CHOICES)
            _choice_display_to_key_single(data, 'work_type', DesignerQuestionnaire.WORK_TYPE_CHOICES)
            _choice_display_to_key_single(data, 'area_of_object', DesignerQuestionnaire.AREA_OF_OBJECT_CHOICES)
            _choice_display_to_key_single(data, 'cost_per_m2', DesignerQuestionnaire.COST_PER_M2_CHOICES)
            _choice_display_to_key_single(data, 'experience', DesignerQuestionnaire.EXPERIENCE_CHOICES)
            _choice_display_to_key_single(data, 'vat_payment', DesignerQuestionnaire.VAT_PAYMENT_CHOICES)
            _choice_display_to_key_single(data, 'status', DesignerQuestionnaire.STATUS_CHOICES)
            _choice_display_to_key_single(data, 'group', QUESTIONNAIRE_GROUP_CHOICES)
        return super().to_internal_value(data)
    
    def validate_services(self, value):
        """Проверка услуг"""
        if not isinstance(value, list):
            return []
        valid_services = [choice[0] for choice in DesignerQuestionnaire.SERVICES_CHOICES]
        for service in value:
            if service not in valid_services:
                raise serializers.ValidationError(f"Неверная услуга: {service}")
        return value
    
    def validate_segments(self, value):
        """Проверка сегментов"""
        if not isinstance(value, list):
            return []
        valid_segments = [choice[0] for choice in DesignerQuestionnaire.SEGMENT_CHOICES]
        for segment in value:
            if segment not in valid_segments:
                raise serializers.ValidationError(f"Неверный сегмент: {segment}")
        return value
    
    def validate_work_cities(self, value):
        """Проверка work_cities"""
        if not isinstance(value, list):
            return []
        return value
    
    def validate_other_contacts(self, value):
        """Проверка other_contacts"""
        if not isinstance(value, list):
            return []
        return value


class RepairQuestionnaireSerializer(serializers.ModelSerializer):
    """
    Анкета ремонтной бригады / подрядчика serializer
    """
    request_name = serializers.SerializerMethodField()
    group_display = serializers.CharField(
        source='get_group_display',
        read_only=True
    )
    business_form_display = serializers.CharField(
        source='get_business_form_display',
        read_only=True
    )
    vat_payment_display = serializers.CharField(
        source='get_vat_payment_display',
        read_only=True
    )
    magazine_cards_display = serializers.SerializerMethodField()
    about_company = serializers.SerializerMethodField()
    terms_of_cooperation = serializers.SerializerMethodField()
    rating_count = serializers.SerializerMethodField()
    rating_list = serializers.SerializerMethodField()
    reviews_list = serializers.SerializerMethodField()
    
    @extend_schema_field(str)
    def get_request_name(self, obj):
        # group ga qarab to'g'ri request_name qaytaramiz
        if obj.group == 'supplier':
            return 'SupplierQuestionnaire'
        elif obj.group == 'media':
            return 'MediaQuestionnaire'
        elif obj.group == 'design':
            return 'DesignerQuestionnaire'
        return 'RepairQuestionnaire'
    
    @extend_schema_field(str)
    def get_magazine_cards_display(self, obj):
        """Convert magazine_cards list to display string"""
        if not obj.magazine_cards:
            return ""
        # List bo'lsa, har bir elementni display qilamiz
        choices_dict = dict(RepairQuestionnaire.MAGAZINE_CARD_CHOICES)
        displays = [choices_dict.get(card, card) for card in obj.magazine_cards]
        return ", ".join(displays)
    
    @extend_schema_field(dict)
    def get_rating_count(self, obj):
        """Rating count: total, positive, constructive"""
        # Context'dan cache'dan olish (agar mavjud bo'lsa)
        ratings_cache = self.context.get('ratings_cache', {})
        key = f"Ремонт_{obj.id}"
        if key in ratings_cache:
            stats = ratings_cache[key]
            return {
                'total': stats['total_positive'],
                'positive': stats['total_positive'],
                'constructive': stats['total_constructive'],
            }
        
        # Agar context yo'q bo'lsa, eski usul (fallback)
        from apps.ratings.models import QuestionnaireRating
        ratings = QuestionnaireRating.objects.filter(
            role='Ремонт',
            questionnaire_id=obj.id,
            status='approved'
        )
        positive_count = ratings.filter(is_positive=True).count()
        return {
            'total': positive_count,
            'positive': positive_count,
            'constructive': ratings.filter(is_constructive=True).count(),
        }
    
    @extend_schema_field(list)
    def get_rating_list(self, obj):
        """Rating list - barcha approved rating'lar"""
        # Context'dan cache'dan olish (agar mavjud bo'lsa)
        ratings_list_cache = self.context.get('ratings_list_cache', {})
        rating_serializer = self.context.get('rating_serializer')
        key = f"Ремонт_{obj.id}"
        if key in ratings_list_cache and rating_serializer:
            ratings = sorted(ratings_list_cache[key], key=lambda x: x.created_at, reverse=True)
            # skip_questionnaire=True qo'yamiz, chunki recursive muammo bo'lmasligi uchun
            context = self.context.copy()
            context['skip_questionnaire'] = True
            return rating_serializer(ratings, many=True, context=context).data
        
        # Agar context yo'q bo'lsa, eski usul (fallback)
        from apps.ratings.models import QuestionnaireRating
        from apps.ratings.serializers import QuestionnaireRatingSerializer
        ratings = QuestionnaireRating.objects.filter(
            role='Ремонт',
            questionnaire_id=obj.id,
            status='approved'
        ).order_by('-created_at')
        context = {'skip_questionnaire': True}
        return QuestionnaireRatingSerializer(ratings, many=True, context=context).data
    
    @extend_schema_field(list)
    def get_reviews_list(self, obj):
        """Reviews list - faqat approved review'lar (pending va rejected tashqari)"""
        # Context'dan cache'dan olish (agar mavjud bo'lsa)
        ratings_list_cache = self.context.get('ratings_list_cache', {})
        rating_serializer = self.context.get('rating_serializer')
        key = f"Ремонт_{obj.id}"
        if key in ratings_list_cache and rating_serializer:
            reviews = sorted(ratings_list_cache[key], key=lambda x: x.created_at, reverse=True)
            # skip_questionnaire=True qo'yamiz, chunki recursive muammo bo'lmasligi uchun
            context = self.context.copy()
            context['skip_questionnaire'] = True
            return rating_serializer(reviews, many=True, context=context).data
        
        # Agar context yo'q bo'lsa, eski usul (fallback)
        from apps.ratings.models import QuestionnaireRating
        from apps.ratings.serializers import QuestionnaireRatingSerializer
        reviews = QuestionnaireRating.objects.filter(
            role='Ремонт',
            questionnaire_id=obj.id,
            status='approved'  # Faqat approved review'lar
        ).order_by('-created_at')
        context = {'skip_questionnaire': True}
        return QuestionnaireRatingSerializer(reviews, many=True, context=context).data
    
    @extend_schema_field(list)
    def get_about_company(self, obj):
        """
        О компании: ОПИСАНИЕ КОМПАНИИ, СКОЛЬКО НА РЫНКЕ, ЧТО ПРОДАЕТ,
        Акции и УТП, Адреса офисов и их контакты, Социальные сети, О НАС (видео контент)
        """
        about_company_data = []
        
        # ОПИСАНИЕ КОМПАНИИ, СКОЛЬКО НА РЫНКЕ, ЧТО ПРОДАЕТ
        if obj.welcome_message:
            about_company_data.append({
                'type': 'company_description',
                'label': 'ОПИСАНИЕ КОМПАНИИ, СКОЛЬКО НА РЫНКЕ, ЧТО ПРОДАЕТ',
                'value': obj.welcome_message
            })
        
        # Подробно перечень услуг которые предоставляет компания
        if obj.work_list:
            about_company_data.append({
                'type': 'services_list',
                'label': 'Перечень услуг которые предоставляет компания',
                'value': obj.work_list
            })
        
        # Акции и УТП (unique_trade_proposal - agar bo'lsa)
        # Bu field modelda yo'q, lekin welcome_message ichida bo'lishi mumkin
        # Yoki keyinroq qo'shilishi mumkin
        
        # Адреса офисов и их контакты
        if obj.representative_cities:
            about_company_data.append({
                'type': 'office_addresses',
                'label': 'Адреса офисов и их контакты',
                'value': obj.representative_cities
            })
        
        # Социальные сети
        social_networks = {}
        if obj.vk:
            social_networks['vk'] = obj.vk
        if obj.telegram_channel:
            social_networks['telegram_channel'] = obj.telegram_channel
        if obj.pinterest:
            social_networks['pinterest'] = obj.pinterest
        if obj.instagram:
            social_networks['instagram'] = obj.instagram
        if obj.website:
            social_networks['website'] = obj.website
        if obj.other_contacts:
            social_networks['other_contacts'] = obj.other_contacts
        
        if social_networks:
            about_company_data.append({
                'type': 'social_networks',
                'label': 'Социальные сети',
                'value': social_networks
            })
        
        # О НАС (видео контент) - bu field modelda yo'q, lekin keyinroq qo'shilishi mumkin
        # Hozircha bo'sh qoldiramiz
        
        return about_company_data
    
    @extend_schema_field(list)
    def get_terms_of_cooperation(self, obj):
        """
        Условия сотрудничества: В какие периоды осуществляется ремонт 1к, 2 к, 3 к,
        НДС - да / нет, Гарантии, Карточки журнала, Условия работы с дизайнерами и прорабами
        """
        terms_data = []
        
        # В какие периоды осуществляется ремонт 1к, 2 к, 3 к
        if obj.project_timelines:
            terms_data.append({
                'type': 'repair_periods',
                'label': 'В какие периоды осуществляется ремонт 1к, 2 к, 3 к',
                'value': obj.project_timelines
            })
        
        # НДС - да / нет
        if obj.vat_payment:
            terms_data.append({
                'type': 'vat_payment',
                'label': 'НДС',
                'value': obj.get_vat_payment_display(),
                'raw_value': obj.vat_payment
            })
        
        # Гарантии
        if obj.guarantees:
            terms_data.append({
                'type': 'guarantees',
                'label': 'Гарантии',
                'value': obj.guarantees
            })
        
        # Карточки журнала
        if obj.magazine_cards:
            # List bo'lsa, har bir elementni display qilamiz
            choices_dict = dict(RepairQuestionnaire.MAGAZINE_CARD_CHOICES)
            displays = [choices_dict.get(card, card) for card in obj.magazine_cards]
            terms_data.append({
                'type': 'magazine_cards',
                'label': 'Карточки журнала',
                'value': ", ".join(displays),
                'raw_value': obj.magazine_cards
            })
        
        # Условия работы с дизайнерами и прорабами
        if obj.designer_supplier_terms:
            terms_data.append({
                'type': 'designer_supplier_terms',
                'label': 'Условия работы с дизайнерами и прорабами',
                'value': obj.designer_supplier_terms
            })
        
        return terms_data
    
    status_display = serializers.CharField(
        source='get_status_display',
        read_only=True
    )
    
    # Multiple choice fields for Swagger - ListField without child validation
    segments = serializers.ListField(
        child=serializers.CharField(),
        required=False,
        allow_empty=True,
        help_text="Список сегментов (multiple choice). Пример: ['horeca', 'business', 'premium']"
    )
    
    magazine_cards = serializers.ListField(
        child=serializers.CharField(),
        required=False,
        allow_empty=True,
        help_text="Список карточек журналов (multiple choice). Пример: ['hi_home', 'in_home']"
    )
    
    categories = serializers.ListField(
        child=serializers.CharField(),
        required=False,
        allow_empty=True,
        help_text="Категории (multiple choice). Пример: ['repair_team', 'contractor']"
    )
    
    speed_of_execution = serializers.CharField(required=False, allow_null=True, allow_blank=True, help_text="Скорость исполнения: advance_booking, quick_start, not_important")
    
    def to_representation(self, instance):
        """Convert choice keys to display names in response"""
        data = super().to_representation(instance)
        
        # Convert segments keys to display names
        if 'segments' in data and data['segments'] is not None:
            choices_dict = dict(RepairQuestionnaire.SEGMENT_CHOICES)
            data['segments'] = [choices_dict.get(segment, segment) for segment in data['segments']]
        
        # Convert categories keys to display names
        if 'categories' in data and data['categories'] is not None:
            choices_dict = dict(RepairQuestionnaire.CATEGORY_CHOICES)
            data['categories'] = [choices_dict.get(c, c) for c in data['categories']]
        
        # Convert business_form key to display name
        if 'business_form' in data and data['business_form'] is not None:
            data['business_form'] = instance.get_business_form_display()
        
        # Convert speed_of_execution key to display name
        if 'speed_of_execution' in data and data['speed_of_execution'] is not None:
            data['speed_of_execution'] = instance.get_speed_of_execution_display() if hasattr(instance, 'get_speed_of_execution_display') else data['speed_of_execution']
        
        # Convert magazine_cards keys to display names
        if 'magazine_cards' in data and data['magazine_cards'] is not None:
            choices_dict = dict(RepairQuestionnaire.MAGAZINE_CARD_CHOICES)
            data['magazine_cards'] = [choices_dict.get(card, card) for card in data['magazine_cards']]
        
        # Convert vat_payment key to display name
        if 'vat_payment' in data and data['vat_payment'] is not None:
            data['vat_payment'] = instance.get_vat_payment_display()
        
        # Convert status key to display name
        if 'status' in data and data['status'] is not None:
            data['status'] = instance.get_status_display()
        
        # Convert group key to display name
        if 'group' in data and data['group'] is not None:
            data['group'] = instance.get_group_display()
        
        return data
    
    # JSONField fields - representative_cities, other_contacts
    # ListField ishlatamiz, chunki JSONField form-data bilan muammo qilmoqda
    representative_cities = serializers.ListField(
        child=serializers.CharField(),
        required=False,
        allow_empty=True,
        help_text="Города представительств (JSON array). Пример: ['Ташкент', 'Самарканд']"
    )
    other_contacts = serializers.ListField(
        child=serializers.CharField(),
        required=False,
        allow_empty=True,
        help_text="Другие контакты (JSON array). Пример: ['contact1', 'contact2']"
    )
    
    class Meta:
        model = RepairQuestionnaire
        fields = [
            'id',
            'request_name',
            'group',
            'group_display',
            'status',
            'status_display',
            'full_name',
            'phone',
            'brand_name',
            'email',
            'responsible_person',
            'representative_cities',
            'business_form',
            'business_form_display',
            'work_list',
            'welcome_message',
            'cooperation_terms',
            'project_timelines',
            'segments',
            'vk',
            'telegram_channel',
            'pinterest',
            'instagram',
            'website',
            'other_contacts',
            'work_format',
            'vat_payment',
            'vat_payment_display',
            'guarantees',
            'designer_supplier_terms',
            'magazine_cards',
            'magazine_cards_display',
            'categories',
            'speed_of_execution',
            'additional_info',
            'about_company',
            'terms_of_cooperation',
            'rating_count',
            'rating_list',
            'reviews_list',
            'data_processing_consent',
            'company_logo',
            'created_at',
            'updated_at',
        ]
        read_only_fields = [
            'id',
            'status',
            'created_at',
            'updated_at',
        ]
        extra_kwargs = {
            field: {'required': False} for field in [
                'full_name', 'phone', 'brand_name', 'email', 'responsible_person',
                'representative_cities', 'business_form', 'work_list', 'welcome_message',
                'cooperation_terms', 'project_timelines', 'segments', 'categories', 'speed_of_execution', 'vk',
                'telegram_channel', 'pinterest', 'instagram', 'website', 'other_contacts',
                'work_format', 'vat_payment', 'guarantees', 'designer_supplier_terms',
                'magazine_cards', 'additional_info', 'data_processing_consent',
                'company_logo', 'group', 'about_company', 'terms_of_cooperation'
            ]
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # PUT request uchun barcha fieldlarni required=False qilish
        if self.partial:
            for field_name, field in self.fields.items():
                if field_name not in self.Meta.read_only_fields:
                    field.required = False
    
    def to_internal_value(self, data):
        """Parse JSON fields from form-data"""
        # Form-data orqali kelganda, JSON maydonlar string sifatida keladi
        if hasattr(data, 'get'):
            # Multiple choice fields - segments, magazine_cards, categories
            multiple_choice_fields = ['segments', 'magazine_cards', 'categories']
            for field in multiple_choice_fields:
                if field in data:
                    value = data.get(field)
                    # Agar allaqachon list bo'lsa, hech narsa qilmaymiz
                    if isinstance(value, list):
                        continue
                    if isinstance(value, str):
                        # Agar string bo'lsa, JSON parse qilishga harakat qilamiz
                        try:
                            import json
                            # QueryDict bo'lsa, mutable copy olish kerak
                            if hasattr(data, '_mutable') and not data._mutable:
                                data._mutable = True
                            parsed = json.loads(value)
                            # Agar list bo'lsa, to'g'ridan-to'g'ri o'rnatamiz
                            if isinstance(parsed, list):
                                # List elementlarini string ga o'zgartirish (CharField uchun)
                                parsed_list = [str(item) for item in parsed if item is not None]
                                # QueryDict da listni o'rnatish uchun setlist yoki __setitem__ ishlatamiz
                                if hasattr(data, '_mutable') and not data._mutable:
                                    data._mutable = True
                                if hasattr(data, 'setlist'):
                                    data.setlist(field, parsed_list)
                                else:
                                    data[field] = parsed_list
                            else:
                                # Agar list bo'lmasa, listga o'zgartiramiz
                                parsed_list = [str(parsed)] if parsed else []
                                if hasattr(data, '_mutable') and not data._mutable:
                                    data._mutable = True
                                if hasattr(data, 'setlist'):
                                    data.setlist(field, parsed_list)
                                else:
                                    data[field] = parsed_list
                        except (json.JSONDecodeError, ValueError):
                            # Agar JSON parse qilib bo'lmasa, vergul bilan ajratilgan string bo'lishi mumkin
                            # Masalan: "business,comfort" -> ["business", "comfort"]
                            if hasattr(data, '_mutable') and not data._mutable:
                                data._mutable = True
                            # Vergul bilan ajratilgan stringlarni listga o'zgartirish
                            if value.strip():
                                # Bo'sh bo'lmagan stringlarni listga o'zgartirish
                                parsed_list = [item.strip() for item in value.split(',') if item.strip()]
                                if hasattr(data, '_mutable') and not data._mutable:
                                    data._mutable = True
                                if hasattr(data, 'setlist'):
                                    data.setlist(field, parsed_list)
                                else:
                                    data[field] = parsed_list
                            else:
                                if hasattr(data, '_mutable') and not data._mutable:
                                    data._mutable = True
                                if hasattr(data, 'setlist'):
                                    data.setlist(field, [])
                                else:
                                    data[field] = []
            
            # ListField fields - representative_cities, other_contacts (endi ListField ishlatamiz)
            list_fields = ['representative_cities', 'other_contacts']
            for field in list_fields:
                if field in data:
                    value = data.get(field)
                    # Agar allaqachon list bo'lsa, hech narsa qilmaymiz
                    if isinstance(value, list):
                        continue
                    if isinstance(value, str):
                        # Agar string bo'lsa, JSON parse qilishga harakat qilamiz
                        try:
                            import json
                            # QueryDict bo'lsa, mutable copy olish kerak
                            if hasattr(data, '_mutable') and not data._mutable:
                                data._mutable = True
                            parsed = json.loads(value)
                            # Agar list bo'lsa, to'g'ridan-to'g'ri o'rnatamiz
                            if isinstance(parsed, list):
                                parsed_list = [str(item) for item in parsed if item is not None]
                                if hasattr(data, '_mutable') and not data._mutable:
                                    data._mutable = True
                                if hasattr(data, 'setlist'):
                                    data.setlist(field, parsed_list)
                                else:
                                    data[field] = parsed_list
                            else:
                                # Agar list bo'lmasa, listga o'zgartiramiz
                                parsed_list = [str(parsed)] if parsed else []
                                if hasattr(data, '_mutable') and not data._mutable:
                                    data._mutable = True
                                if hasattr(data, 'setlist'):
                                    data.setlist(field, parsed_list)
                                else:
                                    data[field] = parsed_list
                        except (json.JSONDecodeError, ValueError):
                            # Agar JSON parse qilib bo'lmasa, bo'sh list qaytaramiz
                            if hasattr(data, '_mutable') and not data._mutable:
                                data._mutable = True
                            if hasattr(data, 'setlist'):
                                data.setlist(field, [])
                            else:
                                data[field] = []
                    elif value is None or value == '':
                        # Agar None yoki bo'sh string bo'lsa, bo'sh list qaytaramiz
                        if hasattr(data, '_mutable') and not data._mutable:
                            data._mutable = True
                        if hasattr(data, 'setlist'):
                            data.setlist(field, [])
                        else:
                            data[field] = []
            # Website field uchun bo'sh stringlarni None ga o'zgartirish
            if 'website' in data:
                website_value = data.get('website')
                if isinstance(website_value, str) and not website_value.strip():
                    if hasattr(data, '_mutable') and not data._mutable:
                        data._mutable = True
                    data['website'] = None
            
            # File fields (photo, company_logo, legal_entity_card) uchun bo'sh stringlarni None ga o'zgartirish
            # Faqat string bo'lsa tekshiramiz, file obyektlarni o'zgartirmaymiz
            file_fields = ['photo', 'company_logo', 'legal_entity_card']
            for field in file_fields:
                if field in data:
                    file_value = data.get(field)
                    # Faqat string bo'lsa tekshiramiz (file obyektlarni o'zgartirmaymiz)
                    # File obyektlarni tekshirish uchun isinstance yoki hasattr ishlatamiz
                    if isinstance(file_value, str):
                        # Agar bo'sh string yoki 'null' string bo'lsa, None ga o'zgartirish
                        if not file_value.strip() or file_value.strip().lower() == 'null':
                            if hasattr(data, '_mutable') and not data._mutable:
                                data._mutable = True
                            data[field] = None
                    # Agar file obyekt bo'lsa (InMemoryUploadedFile, TemporaryUploadedFile), hech narsa qilmaymiz
                    # File obyektlarni o'zgartirmaymiz, chunki DRF ularni to'g'ri handle qiladi
                    elif isinstance(file_value, (InMemoryUploadedFile, TemporaryUploadedFile)):
                        # File obyektni o'zgartirmaymiz, to'g'ridan-to'g'ri o'tkazib yuboramiz
                        pass
            
            # PUT: frontend display name yuboradi, key ga aylantirish
            _choice_display_to_key_list(data, 'segments', RepairQuestionnaire.SEGMENT_CHOICES)
            _choice_display_to_key_list(data, 'magazine_cards', RepairQuestionnaire.MAGAZINE_CARD_CHOICES)
            _choice_display_to_key_list(data, 'categories', RepairQuestionnaire.CATEGORY_CHOICES)
            _choice_display_to_key_single(data, 'business_form', RepairQuestionnaire.BUSINESS_FORM_CHOICES)
            _choice_display_to_key_single(data, 'speed_of_execution', RepairQuestionnaire.SPEED_OF_EXECUTION_CHOICES)
            _choice_display_to_key_single(data, 'vat_payment', RepairQuestionnaire.VAT_PAYMENT_CHOICES)
            _choice_display_to_key_single(data, 'status', RepairQuestionnaire.STATUS_CHOICES)
            _choice_display_to_key_single(data, 'group', QUESTIONNAIRE_GROUP_CHOICES)
        
        return super().to_internal_value(data)
    
    def validate_segments(self, value):
        """Проверка сегментов"""
        if not isinstance(value, list):
            return []
        valid_segments = [choice[0] for choice in RepairQuestionnaire.SEGMENT_CHOICES]
        for segment in value:
            if segment not in valid_segments:
                raise serializers.ValidationError(f"Неверный сегмент: {segment}")
        return value
    
    def validate_magazine_cards(self, value):
        """Проверка magazine_cards - multiple choice"""
        if not isinstance(value, list):
            return []
        valid_cards = [choice[0] for choice in RepairQuestionnaire.MAGAZINE_CARD_CHOICES]
        for card in value:
            if card not in valid_cards:
                raise serializers.ValidationError(f"Неверная карточка журнала: {card}")
        return value
    
    def validate_representative_cities(self, value):
        """Проверка representative_cities"""
        if not isinstance(value, list):
            return []
        return value
    
    def validate_other_contacts(self, value):
        """Проверка other_contacts"""
        if not isinstance(value, list):
            return []
        return value


class SupplierQuestionnaireSerializer(serializers.ModelSerializer):
    """
    Анкета поставщика / салона / фабрики serializer
    """
    request_name = serializers.SerializerMethodField()
    group_display = serializers.CharField(
        source='get_group_display',
        read_only=True
    )
    business_form_display = serializers.CharField(
        source='get_business_form_display',
        read_only=True
    )
    vat_payment_display = serializers.CharField(
        source='get_vat_payment_display',
        read_only=True
    )
    magazine_cards_display = serializers.SerializerMethodField()
    about_company = serializers.SerializerMethodField()
    terms_of_cooperation = serializers.SerializerMethodField()
    rating_count = serializers.SerializerMethodField()
    rating_list = serializers.SerializerMethodField()
    reviews_list = serializers.SerializerMethodField()
    
    @extend_schema_field(str)
    def get_request_name(self, obj):
        # group ga qarab to'g'ri request_name qaytaramiz
        if obj.group == 'repair':
            return 'RepairQuestionnaire'
        elif obj.group == 'media':
            return 'MediaQuestionnaire'
        elif obj.group == 'design':
            return 'DesignerQuestionnaire'
        return 'SupplierQuestionnaire'
    
    @extend_schema_field(str)
    def get_magazine_cards_display(self, obj):
        """Convert magazine_cards list to display string"""
        if not obj.magazine_cards:
            return ""
        # List bo'lsa, har bir elementni display qilamiz
        choices_dict = dict(SupplierQuestionnaire.MAGAZINE_CARD_CHOICES)
        displays = [choices_dict.get(card, card) for card in obj.magazine_cards]
        return ", ".join(displays)
    
    @extend_schema_field(dict)
    def get_rating_count(self, obj):
        """Rating count: total, positive, constructive"""
        # Context'dan cache'dan olish (agar mavjud bo'lsa)
        ratings_cache = self.context.get('ratings_cache', {})
        key = f"Поставщик_{obj.id}"
        if key in ratings_cache:
            stats = ratings_cache[key]
            return {
                'total': stats['total_positive'],
                'positive': stats['total_positive'],
                'constructive': stats['total_constructive'],
            }
        
        # Agar context yo'q bo'lsa, eski usul (fallback)
        from apps.ratings.models import QuestionnaireRating
        ratings = QuestionnaireRating.objects.filter(
            role='Поставщик',
            questionnaire_id=obj.id,
            status='approved'
        )
        positive_count = ratings.filter(is_positive=True).count()
        return {
            'total': positive_count,
            'positive': positive_count,
            'constructive': ratings.filter(is_constructive=True).count(),
        }
    
    @extend_schema_field(list)
    def get_rating_list(self, obj):
        """Rating list - barcha approved rating'lar"""
        # Context'dan cache'dan olish (agar mavjud bo'lsa)
        ratings_list_cache = self.context.get('ratings_list_cache', {})
        rating_serializer = self.context.get('rating_serializer')
        key = f"Поставщик_{obj.id}"
        if key in ratings_list_cache and rating_serializer:
            ratings = sorted(ratings_list_cache[key], key=lambda x: x.created_at, reverse=True)
            # skip_questionnaire=True qo'yamiz, chunki recursive muammo bo'lmasligi uchun
            context = self.context.copy()
            context['skip_questionnaire'] = True
            return rating_serializer(ratings, many=True, context=context).data
        
        # Agar context yo'q bo'lsa, eski usul (fallback)
        from apps.ratings.models import QuestionnaireRating
        from apps.ratings.serializers import QuestionnaireRatingSerializer
        ratings = QuestionnaireRating.objects.filter(
            role='Поставщик',
            questionnaire_id=obj.id,
            status='approved'
        ).order_by('-created_at')
        context = {'skip_questionnaire': True}
        return QuestionnaireRatingSerializer(ratings, many=True, context=context).data
    
    @extend_schema_field(list)
    def get_reviews_list(self, obj):
        """Reviews list - faqat approved review'lar (pending va rejected tashqari)"""
        # Context'dan cache'dan olish (agar mavjud bo'lsa)
        ratings_list_cache = self.context.get('ratings_list_cache', {})
        rating_serializer = self.context.get('rating_serializer')
        key = f"Поставщик_{obj.id}"
        if key in ratings_list_cache and rating_serializer:
            reviews = sorted(ratings_list_cache[key], key=lambda x: x.created_at, reverse=True)
            # skip_questionnaire=True qo'yamiz, chunki recursive muammo bo'lmasligi uchun
            context = self.context.copy()
            context['skip_questionnaire'] = True
            return rating_serializer(reviews, many=True, context=context).data
        
        # Agar context yo'q bo'lsa, eski usul (fallback)
        from apps.ratings.models import QuestionnaireRating
        from apps.ratings.serializers import QuestionnaireRatingSerializer
        reviews = QuestionnaireRating.objects.filter(
            role='Поставщик',
            questionnaire_id=obj.id,
            status='approved'  # Faqat approved review'lar
        ).order_by('-created_at')
        context = {'skip_questionnaire': True}
        return QuestionnaireRatingSerializer(reviews, many=True, context=context).data
    
    @extend_schema_field(list)
    def get_about_company(self, obj):
        """
        О компании: ОПИСАНИЕ КОМПАНИИ, СКОЛЬКО НА РЫНКЕ, ЧТО ПРОДАЕТ,
        Акции и УТП, Адреса офисов и их контакты, Социальные сети, О НАС (видео контент)
        """
        about_company_data = []
        
        # ОПИСАНИЕ КОМПАНИИ, СКОЛЬКО НА РЫНКЕ, ЧТО ПРОДАЕТ
        if obj.welcome_message:
            about_company_data.append({
                'type': 'company_description',
                'label': 'ОПИСАНИЕ КОМПАНИИ, СКОЛЬКО НА РЫНКЕ, ЧТО ПРОДАЕТ',
                'value': obj.welcome_message
            })
        
        # Подробно перечень позиций возможных к приобретению
        if obj.product_assortment:
            about_company_data.append({
                'type': 'product_assortment',
                'label': 'Перечень позиций возможных к приобретению',
                'value': obj.product_assortment
            })
        
        # Акции и УТП (unique_trade_proposal - agar bo'lsa)
        # Bu field modelda yo'q, lekin welcome_message ichida bo'lishi mumkin
        # Yoki keyinroq qo'shilishi mumkin
        
        # Адреса офисов и их контакты
        if obj.representative_cities:
            about_company_data.append({
                'type': 'office_addresses',
                'label': 'Адреса офисов и их контакты',
                'value': obj.representative_cities
            })
        
        # Социальные сети
        social_networks = {}
        if obj.vk:
            social_networks['vk'] = obj.vk
        if obj.telegram_channel:
            social_networks['telegram_channel'] = obj.telegram_channel
        if obj.pinterest:
            social_networks['pinterest'] = obj.pinterest
        if obj.instagram:
            social_networks['instagram'] = obj.instagram
        if obj.website:
            social_networks['website'] = obj.website
        if obj.other_contacts:
            social_networks['other_contacts'] = obj.other_contacts
        
        if social_networks:
            about_company_data.append({
                'type': 'social_networks',
                'label': 'Социальные сети',
                'value': social_networks
            })
        
        # О НАС (видео контент) - bu field modelda yo'q, lekin keyinroq qo'shilishi mumkin
        # Hozircha bo'sh qoldiramiz
        
        return about_company_data
    
    @extend_schema_field(list)
    def get_terms_of_cooperation(self, obj):
        """
        Условия сотрудничества: В какие периоды осуществляется поставка товара,
        НДС - да / нет, Гарантии, Карточки журнала, Условия работы с дизайнерами и прорабами
        """
        terms_data = []
        
        # В какие периоды осуществляется поставка товара
        if obj.delivery_terms:
            terms_data.append({
                'type': 'delivery_periods',
                'label': 'В какие периоды осуществляется поставка товара',
                'value': obj.delivery_terms
            })
        
        # НДС - да / нет
        if obj.vat_payment:
            terms_data.append({
                'type': 'vat_payment',
                'label': 'НДС',
                'value': obj.get_vat_payment_display(),
                'raw_value': obj.vat_payment
            })
        
        # Гарантии
        if obj.guarantees:
            terms_data.append({
                'type': 'guarantees',
                'label': 'Гарантии',
                'value': obj.guarantees
            })
        
        # Карточки журнала
        if obj.magazine_cards:
            # List bo'lsa, har bir elementni display qilamiz
            choices_dict = dict(SupplierQuestionnaire.MAGAZINE_CARD_CHOICES)
            displays = [choices_dict.get(card, card) for card in obj.magazine_cards]
            terms_data.append({
                'type': 'magazine_cards',
                'label': 'Карточки журнала',
                'value': ", ".join(displays),
                'raw_value': obj.magazine_cards
            })
        
        # Условия работы с дизайнерами и прорабами
        if obj.designer_contractor_terms:
            terms_data.append({
                'type': 'designer_contractor_terms',
                'label': 'Условия работы с дизайнерами и прорабами',
                'value': obj.designer_contractor_terms
            })
        
        return terms_data
    
    status_display = serializers.CharField(
        source='get_status_display',
        read_only=True
    )
    
    # Multiple choice fields for Swagger
    segments = serializers.ListField(
        child=serializers.CharField(),
        required=False,
        allow_empty=True,
        help_text="Список сегментов (multiple choice). Пример: ['horeca', 'business', 'premium']"
    )
    
    magazine_cards = serializers.ListField(
        child=serializers.CharField(),
        required=False,
        allow_empty=True,
        help_text="Список карточек журналов (multiple choice). Пример: ['hi_home', 'in_home']"
    )
    
    categories = serializers.ListField(
        child=serializers.CharField(),
        required=False,
        allow_empty=True,
        help_text="Категории (multiple choice). Пример: ['supplier', 'exhibition_hall']"
    )
    
    speed_of_execution = serializers.CharField(required=False, allow_null=True, allow_blank=True, help_text="Скорость исполнения: in_stock, up_to_2_weeks, up_to_1_month, up_to_3_months, not_important")
    
    def to_representation(self, instance):
        """Convert choice keys to display names in response"""
        data = super().to_representation(instance)
        
        # Convert segments keys to display names
        if 'segments' in data and data['segments'] is not None:
            choices_dict = dict(SupplierQuestionnaire.SEGMENT_CHOICES)
            data['segments'] = [choices_dict.get(segment, segment) for segment in data['segments']]
        
        # Convert categories keys to display names
        if 'categories' in data and data['categories'] is not None:
            choices_dict = dict(SupplierQuestionnaire.CATEGORY_CHOICES)
            data['categories'] = [choices_dict.get(c, c) for c in data['categories']]
        
        # Convert business_form key to display name
        if 'business_form' in data and data['business_form'] is not None:
            data['business_form'] = instance.get_business_form_display()
        
        # Convert speed_of_execution key to display name
        if 'speed_of_execution' in data and data['speed_of_execution'] is not None:
            data['speed_of_execution'] = instance.get_speed_of_execution_display() if hasattr(instance, 'get_speed_of_execution_display') else data['speed_of_execution']
        
        # Convert magazine_cards keys to display names
        if 'magazine_cards' in data and data['magazine_cards'] is not None:
            choices_dict = dict(SupplierQuestionnaire.MAGAZINE_CARD_CHOICES)
            data['magazine_cards'] = [choices_dict.get(card, card) for card in data['magazine_cards']]
        
        # Convert vat_payment key to display name
        if 'vat_payment' in data and data['vat_payment'] is not None:
            data['vat_payment'] = instance.get_vat_payment_display()
        
        # Convert status key to display name
        if 'status' in data and data['status'] is not None:
            data['status'] = instance.get_status_display()
        
        # Convert group key to display name
        if 'group' in data and data['group'] is not None:
            data['group'] = instance.get_group_display()
        
        return data
    
    # JSONField fields - representative_cities, other_contacts
    # ListField ishlatamiz, chunki JSONField form-data bilan muammo qilmoqda
    representative_cities = serializers.ListField(
        child=serializers.CharField(),
        required=False,
        allow_empty=True,
        help_text="Города представительств (JSON array). Пример: ['Ташкент', 'Самарканд']"
    )
    other_contacts = serializers.ListField(
        child=serializers.CharField(),
        required=False,
        allow_empty=True,
        help_text="Другие контакты (JSON array). Пример: ['contact1', 'contact2']"
    )
    
    class Meta:
        model = SupplierQuestionnaire
        fields = [
            'id',
            'request_name',
            'group',
            'group_display',
            'status',
            'status_display',
            'full_name',
            'phone',
            'brand_name',
            'email',
            'responsible_person',
            'representative_cities',
            'business_form',
            'business_form_display',
            'product_assortment',
            'welcome_message',
            'cooperation_terms',
            'segments',
            'vk',
            'telegram_channel',
            'pinterest',
            'instagram',
            'website',
            'other_contacts',
            'delivery_terms',
            'vat_payment',
            'vat_payment_display',
            'guarantees',
            'designer_contractor_terms',
            'magazine_cards',
            'magazine_cards_display',
            'categories',
            'rough_materials',
            'finishing_materials',
            'upholstered_furniture',
            'cabinet_furniture',
            'technique',
            'decor',
            'speed_of_execution',
            'about_company',
            'terms_of_cooperation',
            'rating_count',
            'rating_list',
            'reviews_list',
            'data_processing_consent',
            'company_logo',
            'created_at',
            'updated_at',
        ]
        read_only_fields = [
            'id',
            'status',
            'created_at',
            'updated_at',
        ]
        extra_kwargs = {
            field: {'required': False} for field in [
                'full_name', 'phone', 'brand_name', 'email', 'responsible_person',
                'representative_cities', 'business_form', 'product_assortment',
                'welcome_message', 'cooperation_terms', 'segments', 'categories', 'speed_of_execution', 'vk',
                'telegram_channel', 'pinterest', 'instagram', 'website', 'other_contacts',
                'delivery_terms', 'vat_payment', 'guarantees', 'designer_contractor_terms',
                'magazine_cards', 'data_processing_consent', 'company_logo', 'group',
                'rough_materials', 'finishing_materials', 'upholstered_furniture',
                'cabinet_furniture', 'technique', 'decor',
                'about_company', 'terms_of_cooperation'
            ]
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # PUT request uchun barcha fieldlarni required=False qilish
        if self.partial:
            for field_name, field in self.fields.items():
                if field_name not in self.Meta.read_only_fields:
                    field.required = False
    
    def to_internal_value(self, data):
        """Parse JSON fields from form-data"""
        # Form-data orqali kelganda, JSON maydonlar string sifatida keladi
        if hasattr(data, 'get'):
            # Multiple choice fields - vergul bilan ajratilgan stringlar
            multiple_choice_fields = ['segments', 'magazine_cards']
            for field in multiple_choice_fields:
                if field in data:
                    value = data.get(field)
                    # Agar allaqachon list bo'lsa, hech narsa qilmaymiz
                    if isinstance(value, list):
                        continue
                    if isinstance(value, str):
                        # Agar string bo'lsa, JSON parse qilishga harakat qilamiz
                        try:
                            import json
                            # QueryDict bo'lsa, mutable copy olish kerak
                            if hasattr(data, '_mutable') and not data._mutable:
                                data._mutable = True
                            parsed = json.loads(value)
                            # Agar list bo'lsa, to'g'ridan-to'g'ri o'rnatamiz
                            if isinstance(parsed, list):
                                # List elementlarini string ga o'zgartirish (CharField uchun)
                                parsed_list = [str(item) for item in parsed if item is not None]
                                # QueryDict da listni o'rnatish uchun setlist yoki __setitem__ ishlatamiz
                                if hasattr(data, '_mutable') and not data._mutable:
                                    data._mutable = True
                                if hasattr(data, 'setlist'):
                                    data.setlist(field, parsed_list)
                                else:
                                    data[field] = parsed_list
                            else:
                                # Agar list bo'lmasa, listga o'zgartiramiz
                                parsed_list = [str(parsed)] if parsed else []
                                if hasattr(data, '_mutable') and not data._mutable:
                                    data._mutable = True
                                if hasattr(data, 'setlist'):
                                    data.setlist(field, parsed_list)
                                else:
                                    data[field] = parsed_list
                        except (json.JSONDecodeError, ValueError):
                            # Agar JSON parse qilib bo'lmasa, vergul bilan ajratilgan string bo'lishi mumkin
                            # Masalan: "business,comfort" -> ["business", "comfort"]
                            if hasattr(data, '_mutable') and not data._mutable:
                                data._mutable = True
                            # Vergul bilan ajratilgan stringlarni listga o'zgartirish
                            if value.strip():
                                # Bo'sh bo'lmagan stringlarni listga o'zgartirish
                                parsed_list = [item.strip() for item in value.split(',') if item.strip()]
                                if hasattr(data, '_mutable') and not data._mutable:
                                    data._mutable = True
                                if hasattr(data, 'setlist'):
                                    data.setlist(field, parsed_list)
                                else:
                                    data[field] = parsed_list
                            else:
                                if hasattr(data, '_mutable') and not data._mutable:
                                    data._mutable = True
                                if hasattr(data, 'setlist'):
                                    data.setlist(field, [])
                                else:
                                    data[field] = []
            
            # ListField fields - representative_cities, other_contacts (endi ListField ishlatamiz)
            list_fields = ['representative_cities', 'other_contacts']
            for field in list_fields:
                if field in data:
                    value = data.get(field)
                    # Agar allaqachon list bo'lsa, hech narsa qilmaymiz
                    if isinstance(value, list):
                        continue
                    if isinstance(value, str):
                        # Agar string bo'lsa, JSON parse qilishga harakat qilamiz
                        try:
                            import json
                            # QueryDict bo'lsa, mutable copy olish kerak
                            if hasattr(data, '_mutable') and not data._mutable:
                                data._mutable = True
                            parsed = json.loads(value)
                            # Agar list bo'lsa, to'g'ridan-to'g'ri o'rnatamiz
                            if isinstance(parsed, list):
                                parsed_list = [str(item) for item in parsed if item is not None]
                                if hasattr(data, '_mutable') and not data._mutable:
                                    data._mutable = True
                                if hasattr(data, 'setlist'):
                                    data.setlist(field, parsed_list)
                                else:
                                    data[field] = parsed_list
                            else:
                                # Agar list bo'lmasa, listga o'zgartiramiz
                                parsed_list = [str(parsed)] if parsed else []
                                if hasattr(data, '_mutable') and not data._mutable:
                                    data._mutable = True
                                if hasattr(data, 'setlist'):
                                    data.setlist(field, parsed_list)
                                else:
                                    data[field] = parsed_list
                        except (json.JSONDecodeError, ValueError):
                            # Agar JSON parse qilib bo'lmasa, bo'sh list qaytaramiz
                            if hasattr(data, '_mutable') and not data._mutable:
                                data._mutable = True
                            if hasattr(data, 'setlist'):
                                data.setlist(field, [])
                            else:
                                data[field] = []
                    elif value is None or value == '':
                        # Agar None yoki bo'sh string bo'lsa, bo'sh list qaytaramiz
                        if hasattr(data, '_mutable') and not data._mutable:
                            data._mutable = True
                        if hasattr(data, 'setlist'):
                            data.setlist(field, [])
                        else:
                            data[field] = []
            
            # Supplier: secondary filter JSON fields (rough_materials, finishing_materials, ...)
            if self.Meta.model.__name__ == 'SupplierQuestionnaire':
                for field in ['rough_materials', 'finishing_materials', 'upholstered_furniture', 'cabinet_furniture', 'technique', 'decor']:
                    if field in data:
                        value = data.get(field)
                        if isinstance(value, list):
                            parsed_list = []
                            for item in value:
                                if item is None:
                                    continue
                                if isinstance(item, dict) and 'name' in item:
                                    parsed_list.append(str(item['name']))
                                else:
                                    parsed_list.append(str(item))
                            if hasattr(data, '_mutable') and not data._mutable:
                                data._mutable = True
                            if hasattr(data, 'setlist'):
                                data.setlist(field, parsed_list)
                            else:
                                data[field] = parsed_list
                        elif isinstance(value, str):
                            try:
                                import json
                                parsed = json.loads(value)
                                if isinstance(parsed, list):
                                    parsed_list = [str(it.get('name', it) if isinstance(it, dict) else it) for it in parsed if it is not None]
                                else:
                                    parsed_list = []
                                if hasattr(data, '_mutable') and not data._mutable:
                                    data._mutable = True
                                data[field] = parsed_list
                            except (json.JSONDecodeError, ValueError):
                                if hasattr(data, '_mutable') and not data._mutable:
                                    data._mutable = True
                                data[field] = []
                        elif value is None or value == '':
                            if hasattr(data, '_mutable') and not data._mutable:
                                data._mutable = True
                            data[field] = []
            
            # Website field uchun bo'sh stringlarni None ga o'zgartirish
            if 'website' in data:
                website_value = data.get('website')
                if isinstance(website_value, str) and not website_value.strip():
                    if hasattr(data, '_mutable') and not data._mutable:
                        data._mutable = True
                    data['website'] = None
            
            # File fields (photo, company_logo, legal_entity_card) uchun bo'sh stringlarni None ga o'zgartirish
            # Faqat string bo'lsa tekshiramiz, file obyektlarni o'zgartirmaymiz
            file_fields = ['photo', 'company_logo', 'legal_entity_card']
            for field in file_fields:
                if field in data:
                    file_value = data.get(field)
                    # Faqat string bo'lsa tekshiramiz (file obyektlarni o'zgartirmaymiz)
                    # File obyektlarni tekshirish uchun isinstance yoki hasattr ishlatamiz
                    if isinstance(file_value, str):
                        # Agar bo'sh string yoki 'null' string bo'lsa, None ga o'zgartirish
                        if not file_value.strip() or file_value.strip().lower() == 'null':
                            if hasattr(data, '_mutable') and not data._mutable:
                                data._mutable = True
                            data[field] = None
                    # Agar file obyekt bo'lsa (InMemoryUploadedFile, TemporaryUploadedFile), hech narsa qilmaymiz
                    # File obyektlarni o'zgartirmaymiz, chunki DRF ularni to'g'ri handle qiladi
                    elif isinstance(file_value, (InMemoryUploadedFile, TemporaryUploadedFile)):
                        # File obyektni o'zgartirmaymiz, to'g'ridan-to'g'ri o'tkazib yuboramiz
                        pass
            
            # PUT: frontend display name yuboradi, key ga aylantirish
            _choice_display_to_key_list(data, 'segments', SupplierQuestionnaire.SEGMENT_CHOICES)
            _choice_display_to_key_list(data, 'magazine_cards', SupplierQuestionnaire.MAGAZINE_CARD_CHOICES)
            _choice_display_to_key_list(data, 'categories', SupplierQuestionnaire.CATEGORY_CHOICES)
            _choice_display_to_key_single(data, 'business_form', SupplierQuestionnaire.BUSINESS_FORM_CHOICES)
            _choice_display_to_key_single(data, 'speed_of_execution', SupplierQuestionnaire.SPEED_OF_EXECUTION_CHOICES)
            _choice_display_to_key_single(data, 'vat_payment', SupplierQuestionnaire.VAT_PAYMENT_CHOICES)
            _choice_display_to_key_single(data, 'status', SupplierQuestionnaire.STATUS_CHOICES)
            _choice_display_to_key_single(data, 'group', QUESTIONNAIRE_GROUP_CHOICES)
        return super().to_internal_value(data)
    
    def validate_segments(self, value):
        """Проверка сегментов"""
        if not isinstance(value, list):
            return []
        valid_segments = [choice[0] for choice in SupplierQuestionnaire.SEGMENT_CHOICES]
        for segment in value:
            if segment not in valid_segments:
                raise serializers.ValidationError(f"Неверный сегмент: {segment}")
        return value
    
    def validate_magazine_cards(self, value):
        """Проверка magazine_cards - multiple choice"""
        if not isinstance(value, list):
            return []
        valid_cards = [choice[0] for choice in SupplierQuestionnaire.MAGAZINE_CARD_CHOICES]
        for card in value:
            if card not in valid_cards:
                raise serializers.ValidationError(f"Неверная карточка журнала: {card}")
        return value
    
    def validate_representative_cities(self, value):
        """Проверка representative_cities"""
        if not isinstance(value, list):
            return []
        return value
    
    def validate_other_contacts(self, value):
        """Проверка other_contacts"""
        if not isinstance(value, list):
            return []
        return value


class MediaQuestionnaireSerializer(serializers.ModelSerializer):
    """
    Анкета медиа пространства и интерьерных журналов serializer
    """
    request_name = serializers.SerializerMethodField()
    group_display = serializers.CharField(
        source='get_group_display',
        read_only=True
    )
    vat_payment_display = serializers.CharField(
        source='get_vat_payment_display',
        read_only=True
    )
    rating_count = serializers.SerializerMethodField()
    rating_list = serializers.SerializerMethodField()
    reviews_list = serializers.SerializerMethodField()
    
    @extend_schema_field(str)
    def get_request_name(self, obj):
        # group ga qarab to'g'ri request_name qaytaramiz
        if obj.group == 'supplier':
            return 'SupplierQuestionnaire'
        elif obj.group == 'repair':
            return 'RepairQuestionnaire'
        elif obj.group == 'design':
            return 'DesignerQuestionnaire'
        return 'MediaQuestionnaire'
    
    @extend_schema_field(dict)
    def get_rating_count(self, obj):
        """Rating count: total, positive, constructive"""
        # Context'dan cache'dan olish (agar mavjud bo'lsa)
        ratings_cache = self.context.get('ratings_cache', {})
        key = f"Медиа_{obj.id}"
        if key in ratings_cache:
            stats = ratings_cache[key]
            return {
                'total': stats['total_positive'],
                'positive': stats['total_positive'],
                'constructive': stats['total_constructive'],
            }
        
        # Agar context yo'q bo'lsa, eski usul (fallback)
        from apps.ratings.models import QuestionnaireRating
        ratings = QuestionnaireRating.objects.filter(
            role='Медиа',
            questionnaire_id=obj.id,
            status='approved'
        )
        positive_count = ratings.filter(is_positive=True).count()
        return {
            'total': positive_count,
            'positive': positive_count,
            'constructive': ratings.filter(is_constructive=True).count(),
        }
    
    @extend_schema_field(list)
    def get_rating_list(self, obj):
        """Rating list - barcha approved rating'lar"""
        # Context'dan cache'dan olish (agar mavjud bo'lsa)
        ratings_list_cache = self.context.get('ratings_list_cache', {})
        rating_serializer = self.context.get('rating_serializer')
        key = f"Медиа_{obj.id}"
        if key in ratings_list_cache and rating_serializer:
            ratings = sorted(ratings_list_cache[key], key=lambda x: x.created_at, reverse=True)
            # skip_questionnaire=True qo'yamiz, chunki recursive muammo bo'lmasligi uchun
            context = self.context.copy()
            context['skip_questionnaire'] = True
            return rating_serializer(ratings, many=True, context=context).data
        
        # Agar context yo'q bo'lsa, eski usul (fallback)
        from apps.ratings.models import QuestionnaireRating
        from apps.ratings.serializers import QuestionnaireRatingSerializer
        ratings = QuestionnaireRating.objects.filter(
            role='Медиа',
            questionnaire_id=obj.id,
            status='approved'
        ).order_by('-created_at')
        context = {'skip_questionnaire': True}
        return QuestionnaireRatingSerializer(ratings, many=True, context=context).data
    
    @extend_schema_field(list)
    def get_reviews_list(self, obj):
        """Reviews list - faqat approved review'lar (pending va rejected tashqari)"""
        # Context'dan cache'dan olish (agar mavjud bo'lsa)
        ratings_list_cache = self.context.get('ratings_list_cache', {})
        rating_serializer = self.context.get('rating_serializer')
        key = f"Медиа_{obj.id}"
        if key in ratings_list_cache and rating_serializer:
            reviews = sorted(ratings_list_cache[key], key=lambda x: x.created_at, reverse=True)
            # skip_questionnaire=True qo'yamiz, chunki recursive muammo bo'lmasligi uchun
            context = self.context.copy()
            context['skip_questionnaire'] = True
            return rating_serializer(reviews, many=True, context=context).data
        
        # Agar context yo'q bo'lsa, eski usul (fallback)
        from apps.ratings.models import QuestionnaireRating
        from apps.ratings.serializers import QuestionnaireRatingSerializer
        reviews = QuestionnaireRating.objects.filter(
            role='Медиа',
            questionnaire_id=obj.id,
            status='approved'  # Faqat approved review'lar
        ).order_by('-created_at')
        context = {'skip_questionnaire': True}
        return QuestionnaireRatingSerializer(reviews, many=True, context=context).data
    
    status_display = serializers.CharField(
        source='get_status_display',
        read_only=True
    )
    
    # Multiple choice fields for Swagger
    segments = serializers.ListField(
        child=serializers.CharField(),
        required=False,
        allow_empty=True,
        help_text="Список сегментов (multiple choice). Пример: ['horeca', 'business', 'premium']"
    )
    
    def to_representation(self, instance):
        """Convert choice keys to display names in response"""
        data = super().to_representation(instance)
        
        # Convert segments keys to display names
        if 'segments' in data and data['segments'] is not None:
            choices_dict = dict(MediaQuestionnaire.SEGMENT_CHOICES)
            data['segments'] = [choices_dict.get(segment, segment) for segment in data['segments']]
        
        # Convert vat_payment key to display name
        if 'vat_payment' in data and data['vat_payment'] is not None:
            data['vat_payment'] = instance.get_vat_payment_display()
        
        # Convert status key to display name
        if 'status' in data and data['status'] is not None:
            data['status'] = instance.get_status_display()
        
        # Convert group key to display name
        if 'group' in data and data['group'] is not None:
            data['group'] = instance.get_group_display()
        
        return data
    
    # JSONField fields - representative_cities, other_contacts
    # ListField ishlatamiz, chunki JSONField form-data bilan muammo qilmoqda
    representative_cities = serializers.ListField(
        child=serializers.CharField(),
        required=False,
        allow_empty=True,
        help_text="Города представительств (JSON array). Пример: ['Ташкент', 'Самарканд']"
    )
    other_contacts = serializers.ListField(
        child=serializers.CharField(),
        required=False,
        allow_empty=True,
        help_text="Другие контакты (JSON array). Пример: ['contact1', 'contact2']"
    )
    
    class Meta:
        model = MediaQuestionnaire
        fields = [
            'id',
            'request_name',
            'group',
            'group_display',
            'status',
            'status_display',
            'full_name',
            'phone',
            'brand_name',
            'email',
            'responsible_person',
            'representative_cities',
            'business_form',
            'activity_description',
            'welcome_message',
            'cooperation_terms',
            'segments',
            'vk',
            'telegram_channel',
            'pinterest',
            'instagram',
            'website',
            'other_contacts',
            'vat_payment',
            'vat_payment_display',
            'rating_count',
            'rating_list',
            'reviews_list',
            'additional_info',
            'company_logo',
            'created_at',
            'updated_at',
        ]
        read_only_fields = [
            'id',
            'status',
            'created_at',
            'updated_at',
        ]
        extra_kwargs = {
            field: {'required': False} for field in [
                'full_name', 'phone', 'brand_name', 'email', 'responsible_person',
                'representative_cities', 'business_form', 'activity_description',
                'welcome_message', 'cooperation_terms', 'segments', 'vk',
                'telegram_channel', 'pinterest', 'instagram', 'website', 'other_contacts',
                'vat_payment', 'additional_info', 'company_logo', 'group'
            ]
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # PUT request uchun barcha fieldlarni required=False qilish
        if self.partial:
            for field_name, field in self.fields.items():
                if field_name not in self.Meta.read_only_fields:
                    field.required = False
    
    def to_internal_value(self, data):
        """Parse JSON fields from form-data"""
        # Form-data orqali kelganda, JSON maydonlar string sifatida keladi
        # QueryDict yoki dict bo'lishi mumkin
        if hasattr(data, 'get'):
            # Multiple choice fields - vergul bilan ajratilgan stringlar
            multiple_choice_fields = ['segments']
            for field in multiple_choice_fields:
                if field in data:
                    value = data.get(field)
                    # Agar allaqachon list bo'lsa, hech narsa qilmaymiz
                    if isinstance(value, list):
                        continue
                    if isinstance(value, str):
                        # Agar string bo'lsa, JSON parse qilishga harakat qilamiz
                        try:
                            import json
                            # QueryDict bo'lsa, mutable copy olish kerak
                            if hasattr(data, '_mutable') and not data._mutable:
                                data._mutable = True
                            parsed = json.loads(value)
                            # Agar list bo'lsa, to'g'ridan-to'g'ri o'rnatamiz
                            if isinstance(parsed, list):
                                # List elementlarini string ga o'zgartirish (CharField uchun)
                                parsed_list = [str(item) for item in parsed if item is not None]
                                # QueryDict da listni o'rnatish uchun setlist yoki __setitem__ ishlatamiz
                                if hasattr(data, '_mutable') and not data._mutable:
                                    data._mutable = True
                                if hasattr(data, 'setlist'):
                                    data.setlist(field, parsed_list)
                                else:
                                    data[field] = parsed_list
                            else:
                                # Agar list bo'lmasa, listga o'zgartiramiz
                                parsed_list = [str(parsed)] if parsed else []
                                if hasattr(data, '_mutable') and not data._mutable:
                                    data._mutable = True
                                if hasattr(data, 'setlist'):
                                    data.setlist(field, parsed_list)
                                else:
                                    data[field] = parsed_list
                        except (json.JSONDecodeError, ValueError):
                            # Agar JSON parse qilib bo'lmasa, vergul bilan ajratilgan string bo'lishi mumkin
                            # Masalan: "business,comfort" -> ["business", "comfort"]
                            if hasattr(data, '_mutable') and not data._mutable:
                                data._mutable = True
                            # Vergul bilan ajratilgan stringlarni listga o'zgartirish
                            if value.strip():
                                # Bo'sh bo'lmagan stringlarni listga o'zgartirish
                                parsed_list = [item.strip() for item in value.split(',') if item.strip()]
                                if hasattr(data, '_mutable') and not data._mutable:
                                    data._mutable = True
                                if hasattr(data, 'setlist'):
                                    data.setlist(field, parsed_list)
                                else:
                                    data[field] = parsed_list
                            else:
                                if hasattr(data, '_mutable') and not data._mutable:
                                    data._mutable = True
                                if hasattr(data, 'setlist'):
                                    data.setlist(field, [])
                                else:
                                    data[field] = []
            
            # ListField fields - representative_cities, other_contacts (endi ListField ishlatamiz)
            list_fields = ['representative_cities', 'other_contacts']
            for field in list_fields:
                if field in data:
                    value = data.get(field)
                    # Agar allaqachon list bo'lsa, hech narsa qilmaymiz
                    if isinstance(value, list):
                        continue
                    if isinstance(value, str):
                        # Agar string bo'lsa, JSON parse qilishga harakat qilamiz
                        try:
                            import json
                            # QueryDict bo'lsa, mutable copy olish kerak
                            if hasattr(data, '_mutable') and not data._mutable:
                                data._mutable = True
                            parsed = json.loads(value)
                            # Agar list bo'lsa, to'g'ridan-to'g'ri o'rnatamiz
                            if isinstance(parsed, list):
                                parsed_list = [str(item) for item in parsed if item is not None]
                                if hasattr(data, '_mutable') and not data._mutable:
                                    data._mutable = True
                                if hasattr(data, 'setlist'):
                                    data.setlist(field, parsed_list)
                                else:
                                    data[field] = parsed_list
                            else:
                                # Agar list bo'lmasa, listga o'zgartiramiz
                                parsed_list = [str(parsed)] if parsed else []
                                if hasattr(data, '_mutable') and not data._mutable:
                                    data._mutable = True
                                if hasattr(data, 'setlist'):
                                    data.setlist(field, parsed_list)
                                else:
                                    data[field] = parsed_list
                        except (json.JSONDecodeError, ValueError):
                            # Agar JSON parse qilib bo'lmasa, bo'sh list qaytaramiz
                            if hasattr(data, '_mutable') and not data._mutable:
                                data._mutable = True
                            if hasattr(data, 'setlist'):
                                data.setlist(field, [])
                            else:
                                data[field] = []
                    elif value is None or value == '':
                        # Agar None yoki bo'sh string bo'lsa, bo'sh list qaytaramiz
                        if hasattr(data, '_mutable') and not data._mutable:
                            data._mutable = True
                        if hasattr(data, 'setlist'):
                            data.setlist(field, [])
                        else:
                            data[field] = []
            
            # Website field uchun bo'sh stringlarni None ga o'zgartirish
            if 'website' in data:
                website_value = data.get('website')
                if isinstance(website_value, str) and not website_value.strip():
                    if hasattr(data, '_mutable') and not data._mutable:
                        data._mutable = True
                    data['website'] = None
            
            # File fields (photo, company_logo, legal_entity_card) uchun bo'sh stringlarni None ga o'zgartirish
            # Faqat string bo'lsa tekshiramiz, file obyektlarni o'zgartirmaymiz
            file_fields = ['photo', 'company_logo', 'legal_entity_card']
            for field in file_fields:
                if field in data:
                    file_value = data.get(field)
                    # Faqat string bo'lsa tekshiramiz (file obyektlarni o'zgartirmaymiz)
                    # File obyektlarni tekshirish uchun isinstance yoki hasattr ishlatamiz
                    if isinstance(file_value, str):
                        # Agar bo'sh string yoki 'null' string bo'lsa, None ga o'zgartirish
                        if not file_value.strip() or file_value.strip().lower() == 'null':
                            if hasattr(data, '_mutable') and not data._mutable:
                                data._mutable = True
                            data[field] = None
                    # Agar file obyekt bo'lsa (InMemoryUploadedFile, TemporaryUploadedFile), hech narsa qilmaymiz
                    # File obyektlarni o'zgartirmaymiz, chunki DRF ularni to'g'ri handle qiladi
                    elif isinstance(file_value, (InMemoryUploadedFile, TemporaryUploadedFile)):
                        # File obyektni o'zgartirmaymiz, to'g'ridan-to'g'ri o'tkazib yuboramiz
                        pass
            
            # PUT: frontend display name yuboradi, key ga aylantirish
            _choice_display_to_key_list(data, 'segments', MediaQuestionnaire.SEGMENT_CHOICES)
            _choice_display_to_key_single(data, 'vat_payment', MediaQuestionnaire.VAT_PAYMENT_CHOICES)
            _choice_display_to_key_single(data, 'status', MediaQuestionnaire.STATUS_CHOICES)
            _choice_display_to_key_single(data, 'group', QUESTIONNAIRE_GROUP_CHOICES)
        return super().to_internal_value(data)
    
    def validate_segments(self, value):
        """Проверка сегментов"""
        if not isinstance(value, list):
            return []
        valid_segments = [choice[0] for choice in MediaQuestionnaire.SEGMENT_CHOICES]
        for segment in value:
            if segment not in valid_segments:
                raise serializers.ValidationError(f"Неверный сегмент: {segment}")
        return value
    
    def validate_representative_cities(self, value):
        """Проверка representative_cities"""
        if not isinstance(value, list):
            return []
        return value
    
    def validate_other_contacts(self, value):
        """Проверка other_contacts"""
        if not isinstance(value, list):
            return []
        return value


class QuestionnaireStatusUpdateSerializer(serializers.Serializer):
    """
    Serializer для обновления статуса анкеты (admin)
    """
    status = serializers.ChoiceField(
        choices=[
            ('pending', 'Ожидает модерации'),
            ('published', 'Опубликовано'),
            ('rejected', 'Отклонено'),
            ('archived', 'В архиве'),
        ],
        required=True,
        help_text="Новый статус анкеты"
    )


class GroupSerializer(serializers.Serializer):
    """
    Serializer для описания группы (django.contrib.auth.models.Group)
    с дополнительным полем is_locked для Swagger.
    """
    id = serializers.IntegerField(read_only=True, help_text="ID группы")
    name = serializers.CharField(read_only=True, help_text="Название группы")
    is_locked = serializers.BooleanField(
        read_only=True,
        help_text="True, если пользователь состоит в этой группе"
    )


