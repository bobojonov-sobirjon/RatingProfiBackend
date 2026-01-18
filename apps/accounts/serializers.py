from rest_framework import serializers
from drf_spectacular.utils import extend_schema_field, OpenApiTypes
from drf_spectacular.types import OpenApiTypes
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
from .models import SMSVerificationCode, DesignerQuestionnaire, RepairQuestionnaire, SupplierQuestionnaire, MediaQuestionnaire
from .utils import send_sms_via_smsaero, generate_sms_code

User = get_user_model()


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
    (Boshqa foydalanuvchilar ko'rish uchun)
    """
    role_display = serializers.CharField(
        source='get_role_display',
        read_only=True
    )
    
    groups = serializers.SerializerMethodField()
    
    def get_groups(self, obj):
        return obj.groups.values_list('name', flat=True)
    
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
            multiple_choice_fields = ['services', 'segments']
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
                    if isinstance(file_value, str):
                        # Agar bo'sh string yoki 'null' string bo'lsa, None ga o'zgartirish
                        if not file_value.strip() or file_value.strip().lower() == 'null':
                            if hasattr(data, '_mutable') and not data._mutable:
                                data._mutable = True
                            data[field] = None
                    # Agar file obyekt bo'lsa (InMemoryUploadedFile, TemporaryUploadedFile), hech narsa qilmaymiz
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
                'cooperation_terms', 'project_timelines', 'segments', 'vk',
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
            # Multiple choice fields - segments, magazine_cards
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
                    if isinstance(file_value, str):
                        # Agar bo'sh string yoki 'null' string bo'lsa, None ga o'zgartirish
                        if not file_value.strip() or file_value.strip().lower() == 'null':
                            if hasattr(data, '_mutable') and not data._mutable:
                                data._mutable = True
                            data[field] = None
                    # Agar file obyekt bo'lsa (InMemoryUploadedFile, TemporaryUploadedFile), hech narsa qilmaymiz
        
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
                'welcome_message', 'cooperation_terms', 'segments', 'vk',
                'telegram_channel', 'pinterest', 'instagram', 'website', 'other_contacts',
                'delivery_terms', 'vat_payment', 'guarantees', 'designer_contractor_terms',
                'magazine_cards', 'data_processing_consent', 'company_logo', 'group',
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
                    if isinstance(file_value, str):
                        # Agar bo'sh string yoki 'null' string bo'lsa, None ga o'zgartirish
                        if not file_value.strip() or file_value.strip().lower() == 'null':
                            if hasattr(data, '_mutable') and not data._mutable:
                                data._mutable = True
                            data[field] = None
                    # Agar file obyekt bo'lsa (InMemoryUploadedFile, TemporaryUploadedFile), hech narsa qilmaymiz
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
                    if isinstance(file_value, str):
                        # Agar bo'sh string yoki 'null' string bo'lsa, None ga o'zgartirish
                        if not file_value.strip() or file_value.strip().lower() == 'null':
                            if hasattr(data, '_mutable') and not data._mutable:
                                data._mutable = True
                            data[field] = None
                    # Agar file obyekt bo'lsa (InMemoryUploadedFile, TemporaryUploadedFile), hech narsa qilmaymiz
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


