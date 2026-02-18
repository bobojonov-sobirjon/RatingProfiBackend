from django.db import models
from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.contrib.auth import get_user_model
from django.utils import timezone
from datetime import timedelta


class UserManager(BaseUserManager):
    """
    Custom user manager where phone is the unique identifier
    """
    def create_user(self, phone, password=None, **extra_fields):
        """Создание и сохранение обычного пользователя с телефоном и паролем."""
        if not phone:
            raise ValueError('Необходимо указать телефон')
        user = self.model(phone=phone, username=phone, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, phone, password=None, **extra_fields):
        """Создание и сохранение суперпользователя с телефоном и паролем."""
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('is_active', True)
        extra_fields.setdefault('role', 'admin')

        if extra_fields.get('is_staff') is not True:
            raise ValueError('Суперпользователь должен иметь is_staff=True.')
        if extra_fields.get('is_superuser') is not True:
            raise ValueError('Суперпользователь должен иметь is_superuser=True.')

        return self.create_user(phone, password, **extra_fields)


class User(AbstractUser):
    """
    Asosiy foydalanuvchi modeli
    """
    USER_ROLES = [
        ('designer', 'Дизайнер/Архитектор'),
        ('repair', 'Ремонтная группа/Подрядчик'),
        ('supplier', 'Поставщик/Выставочный зал/Фабрика'),
        ('media', 'Журнал по дизайну интерьера / Медиа'),
        ('admin', 'Администратор'),
    ]
    
    phone = models.CharField(
        max_length=20,
        unique=True,
        verbose_name='Телефон'
    )
    role = models.CharField(
        max_length=20,
        choices=USER_ROLES,
        verbose_name='Роль пользователя'
    )
    is_phone_verified = models.BooleanField(
        default=False,
        verbose_name='Телефон подтвержден'
    )
    is_profile_completed = models.BooleanField(
        default=False,
        verbose_name='Профиль заполнен'
    )
    is_active_profile = models.BooleanField(
        default=False,
        verbose_name='Профиль активен (прошел модерацию)'
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name='Дата создания'
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name='Дата обновления'
    )
    
    # Профиль информация
    full_name = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        verbose_name='Полное имя'
    )
    photo = models.ImageField(
        upload_to='users/photos/',
        blank=True,
        null=True,
        verbose_name='Фото'
    )
    description = models.TextField(
        blank=True,
        null=True,
        verbose_name='Описание'
    )
    city = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        verbose_name='Город'
    )
    address = models.TextField(
        blank=True,
        null=True,
        verbose_name='Адрес'
    )
    website = models.URLField(
        blank=True,
        null=True,
        verbose_name='Веб-сайт'
    )
    
    # Социальные сети
    telegram = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        verbose_name='Telegram'
    )
    instagram = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        verbose_name='Instagram'
    )
    vk = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        verbose_name='VKontakte'
    )
    
    # Для поставщиков
    company_name = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        verbose_name='Название компании'
    )
    inn = models.CharField(
        max_length=20,
        blank=True,
        null=True,
        verbose_name='ИНН'
    )
    product_categories = models.JSONField(
        default=list,
        blank=True,
        verbose_name='Категории товаров'
    )
    brands = models.JSONField(
        default=list,
        blank=True,
        verbose_name='Бренды'
    )
    
    # Для ремонтной группы
    team_name = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        verbose_name='Название команды'
    )
    work_types = models.JSONField(
        default=list,
        blank=True,
        verbose_name='Виды работ'
    )
    
    # Условия сотрудничества
    cooperation_terms = models.TextField(
        blank=True,
        null=True,
        verbose_name='Условия сотрудничества'
    )
    
    # QR код и шаринг
    qr_code = models.ImageField(
        upload_to='users/qr_codes/',
        blank=True,
        null=True,
        verbose_name='QR код'
    )
    share_url = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        verbose_name='URL для шаринга'
    )
    
    objects = UserManager()
    
    USERNAME_FIELD = 'phone'
    REQUIRED_FIELDS = []
    
    class Meta:
        verbose_name = 'Пользователь'
        verbose_name_plural = 'Пользователи'
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.phone} - {self.get_role_display()}"


class SMSVerificationCode(models.Model):
    """
    SMS код подтверждения
    """
    phone = models.CharField(
        max_length=20,
        verbose_name='Телефон'
    )
    code = models.CharField(
        max_length=6,
        verbose_name='Код'
    )
    is_used = models.BooleanField(
        default=False,
        verbose_name='Использован'
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name='Дата создания'
    )
    expires_at = models.DateTimeField(
        verbose_name='Срок действия'
    )
    
    class Meta:
        verbose_name = 'SMS код подтверждения'
        verbose_name_plural = 'SMS коды подтверждения'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['phone', 'code', 'is_used']),
        ]
    
    def __str__(self):
        return f"{self.phone} - {self.code}"
    
    def save(self, *args, **kwargs):
        if not self.expires_at:
            self.expires_at = timezone.now() + timedelta(minutes=5)
        super().save(*args, **kwargs)
    
    def is_valid(self):
        """Проверка действительности кода"""
        return (
            not self.is_used and
            timezone.now() < self.expires_at
        )


# Общие choices для всех анкет
QUESTIONNAIRE_GROUP_CHOICES = [
    ('supplier', 'Поставщик'),
    ('repair', 'Ремонт'),
    ('design', 'Дизайн'),
    ('media', 'Медиа'),
]

# Role mapping для API
ROLE_TO_MODEL_MAPPING = {
    'Поставщик': 'SupplierQuestionnaire',
    'Ремонт': 'RepairQuestionnaire',
    'Дизайн': 'DesignerQuestionnaire',
    'Медиа': 'MediaQuestionnaire',
}


class DesignerQuestionnaire(models.Model):
    """
    Анкета дизайнера
    """
    CATEGORY_CHOICES = [
        ('residential_designer', 'Дизайнер жилых помещений'),
        ('commercial_designer', 'Дизайнер коммерческой недвижимости'),
        ('decorator', 'Декоратор'),
        ('home_stager', 'Хоумстейджер'),
        ('architect', 'Архитектор'),
        ('landscape_designer', 'Ландшафтный дизайнер'),
        ('light_designer', 'Светодизайнер'),
    ]
    
    PURPOSE_OF_PROPERTY_CHOICES = [
        ('permanent_residence', 'Для постоянного проживания'),
        ('for_rent', 'Для сдачи'),
        ('commercial', 'Коммерческая недвижимость'),
        ('horeca', 'HoReCa'),
    ]
    
    # Площадь объекта — текстовие варианты (не число)
    AREA_OF_OBJECT_CHOICES = [
        ('до 10 м2', 'до 10 м2'),
        ('до 40 м2', 'до 40 м2'),
        ('до 80 м2', 'до 80 м2'),
        ('дома', 'дома'),
    ]
    
    # Стоимость за м² — текстовие варианты (не число)
    COST_PER_M2_CHOICES = [
        ('До 1500 р', 'До 1500 р'),
        ('до 2500р', 'до 2500р'),
        ('до 4000 р', 'до 4000 р'),
        ('свыше 4000 р', 'свыше 4000 р'),
    ]
    
    # Опыт работы — текстовие варианты (не число)
    EXPERIENCE_CHOICES = [
        ('Новичок', 'Новичок'),
        ('До 2 лет', 'До 2 лет'),
        ('2-5 лет', '2-5 лет'),
        ('5-10 лет', '5-10 лет'),
        ('Свыше 10 лет', 'Свыше 10 лет'),
    ]
    
    SERVICES_CHOICES = [
        ('author_supervision', 'Авторский надзор'),
        ('architecture', 'Архитектура'),
        ('decorator', 'Декоратор'),
        ('designer_horika', 'Направление HoReCa'),
        ('residential_designer', 'Дизайнер жилой недвижимости'),
        ('commercial_designer', 'Дизайнер коммерческой недвижимости'),
        ('completing', 'Комплектация'),
        ('landscape_design', 'Ландшафтный дизайн'),
        ('design', 'Проектирование'),
        ('light_designer', 'Светодизайнер'),
        ('home_stager', 'Хоумстейджер'),
    ]
    
    WORK_TYPE_CHOICES = [
        ('own_name', 'Под собственным именем'),
        ('studio', 'В студии'),
    ]
    
    SEGMENT_CHOICES = [
        ('horeca', 'HoReCa'),
        ('business', 'Бизнес'),
        ('comfort', 'Комфорт'),
        ('premium', 'Премиум'),
        ('medium', 'Средний'),
        ('economy', 'Эконом'),
    ]
    
    STATUS_CHOICES = [
        ('pending', 'Ожидает модерации'),
        ('published', 'Опубликовано'),
        ('rejected', 'Отклонено'),
        ('archived', 'В архиве'),
    ]
    
    VAT_PAYMENT_CHOICES = [
        ('yes', 'Да'),
        ('no', 'Нет'),
    ]
    
    # Группа
    group = models.CharField(
        max_length=50,
        choices=QUESTIONNAIRE_GROUP_CHOICES,
        default='designer',
        verbose_name='Группа'
    )
    
    # Статус модерации
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='pending',
        verbose_name='Статус'
    )
    
    # Модерация пройдена
    is_moderation = models.BooleanField(
        default=False,
        verbose_name='Модерация пройдена'
    )
    
    # Основная информация
    full_name = models.CharField(
        max_length=255,
        verbose_name='ФИО'
    )
    full_name_en = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        verbose_name='ФИ на английском'
    )
    phone = models.CharField(
        max_length=20,
        verbose_name='Номер телефона'
    )
    birth_date = models.DateField(
        blank=True,
        null=True,
        verbose_name='Дата рождения'
    )
    email = models.EmailField(
        verbose_name='E-mail'
    )
    city = models.CharField(
        max_length=100,
        verbose_name='Город проживания'
    )
    
    # Услуги (multiple choice)
    services = models.JSONField(
        default=list,
        verbose_name='Услуги'
    )
    
    # Тип работы
    work_type = models.CharField(
        max_length=20,
        choices=WORK_TYPE_CHOICES,
        blank=True,
        null=True,
        verbose_name='Тип работы'
    )
    
    # Приветственное сообщение
    welcome_message = models.TextField(
        blank=True,
        null=True,
        verbose_name='Приветственное сообщение о вас и вашем опыте'
    )
    
    # Города работы
    work_cities = models.JSONField(
        default=list,
        blank=True,
        verbose_name='Города работы'
    )
    
    # Условия сотрудничества
    cooperation_terms = models.TextField(
        blank=True,
        null=True,
        verbose_name='Условия сотрудничества при работе с объектами в других городах или регионах'
    )
    
    # Сегменты (multiple choice)
    segments = models.JSONField(
        default=list,
        blank=True,
        verbose_name='Сегменты работы'
    )
    
    # Ваше уникальное торговое предложение (УТП)
    unique_trade_proposal = models.TextField(
        blank=True,
        null=True,
        verbose_name='Ваше уникальное торговое предложение (УТП)'
    )
    
    # Ссылки на социальные сети и другие каналы связи
    vk = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        verbose_name='VK'
    )
    telegram_channel = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        verbose_name='Telegram канал'
    )
    pinterest = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        verbose_name='Pinterest'
    )
    instagram = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        verbose_name='Instagram'
    )
    website = models.URLField(
        blank=True,
        null=True,
        verbose_name='Ваш сайт'
    )
    other_contacts = models.JSONField(
        default=list,
        blank=True,
        verbose_name='Другое - дополнительные контакты'
    )
    
    # Подробное описание пакетов услуг с указанием стоимости
    service_packages_description = models.TextField(
        blank=True,
        null=True,
        verbose_name='Подробное описание пакетов услуг с указанием стоимости'
    )
    
    # Возможна ли оплата с учётом НДС?
    vat_payment = models.CharField(
        max_length=10,
        choices=VAT_PAYMENT_CHOICES,
        blank=True,
        null=True,
        verbose_name='Возможна ли оплата с учётом НДС?'
    )
    
    # Условия сотрудничества по рекомендациям от поставщиков или подрядчиков
    supplier_contractor_recommendation_terms = models.TextField(
        blank=True,
        null=True,
        verbose_name='Условия сотрудничества по рекомендациям от поставщиков или подрядчиков'
    )
    
    # Дополнительная информация
    additional_info = models.TextField(
        blank=True,
        null=True,
        verbose_name='Дополнительная информация'
    )
    
    # Согласие на обработку данных
    data_processing_consent = models.BooleanField(
        default=False,
        verbose_name='Согласие на обработку данных'
    )
    
    # Прикрепите ваше фото для личного кабинета
    photo = models.ImageField(
        upload_to='designers/photos/',
        blank=True,
        null=True,
        verbose_name='Прикрепите ваше фото для личного кабинета'
    )
    
    # Категории (multiple choice)
    categories = models.JSONField(
        default=list,
        blank=True,
        verbose_name='Категории'
    )
    
    # Назначение недвижимости (multiple choice)
    purpose_of_property = models.JSONField(
        default=list,
        blank=True,
        verbose_name='Назначение недвижимости'
    )
    
    # Площадь объекта (JSONField: list, до 10 м2, до 40 м2, до 80 м2, дома)
    area_of_object = models.JSONField(
        default=list,
        blank=True,
        verbose_name='Площадь объекта'
    )
    
    # Стоимость за м² — текстовие варианты (До 1500 р, до 2500р, до 4000 р, свыше 4000 р)
    cost_per_m2 = models.CharField(
        max_length=50,
        blank=True,
        null=True,
        choices=COST_PER_M2_CHOICES,
        verbose_name='Стоимость за м²'
    )
    
    # Опыт работы — текстовие варианты (Новичок, До 2 лет, 2-5 лет, 5-10 лет, Свыше 10 лет)
    experience = models.CharField(
        max_length=50,
        blank=True,
        null=True,
        choices=EXPERIENCE_CHOICES,
        verbose_name='Опыт работы'
    )
    
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name='Дата создания'
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name='Дата обновления'
    )
    
    # Удалено (soft delete)
    is_deleted = models.BooleanField(
        default=False,
        verbose_name='Удалено'
    )
    
    class Meta:
        verbose_name = 'Анкета дизайнера'
        verbose_name_plural = 'Анкеты дизайнеров'
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.full_name} - {self.city}"


class RepairQuestionnaire(models.Model):
    """
    Анкета ремонтной бригады / подрядчика
    """
    BUSINESS_FORM_CHOICES = [
        ('own_business', 'Собственный бизнес'),
        ('franchise', 'Франшиза'),
    ]
    
    SEGMENT_CHOICES = [
        ('horeca', 'HoReCa'),
        ('business', 'Бизнес'),
        ('comfort', 'Комфорт'),
        ('premium', 'Премиум'),
        ('medium', 'Средний'),
        ('economy', 'Эконом'),
    ]
    
    STATUS_CHOICES = [
        ('pending', 'Ожидает модерации'),
        ('published', 'Опубликовано'),
        ('rejected', 'Отклонено'),
        ('archived', 'В архиве'),
    ]
    
    VAT_PAYMENT_CHOICES = [
        ('yes', 'Да'),
        ('no', 'Нет'),
    ]
    
    MAGAZINE_CARD_CHOICES = [
        ('hi_home', 'Hi Home'),
        ('in_home', 'IN HOME'),
        ('no', 'Нет'),
        ('other', 'Другое'),
    ]
    
    CATEGORY_CHOICES = [
        ('repair_team', 'Ремонтная бригада'),
        ('contractor', 'Подрядчик'),
        ('finishing', 'Отделочные работы'),
        ('electrical', 'Электромонтаж'),
        ('plumbing', 'Сантехника'),
        ('other', 'Другое'),
    ]
    
    SPEED_OF_EXECUTION_CHOICES = [
        ('advance_booking', 'Предварительная запись'),
        ('quick_start', 'Быстрый старт'),
        ('not_important', 'Не важно'),
    ]
    
    # Группа
    group = models.CharField(
        max_length=50,
        choices=QUESTIONNAIRE_GROUP_CHOICES,
        default='repair_team',
        verbose_name='Группа'
    )
    
    # Статус модерации
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='pending',
        verbose_name='Статус'
    )
    
    # Модерация пройдена
    is_moderation = models.BooleanField(
        default=False,
        verbose_name='Модерация пройдена'
    )
    
    # Основная информация
    full_name = models.CharField(
        max_length=255,
        verbose_name='ФИО'
    )
    phone = models.CharField(
        max_length=20,
        blank=True,
        null=True,
        verbose_name='Номер телефона'
    )
    brand_name = models.CharField(
        max_length=255,
        verbose_name='Название бренда (дополнительно в скобках укажите полное юридическое наименование компании)'
    )
    phone = models.CharField(
        max_length=20,
        blank=True,
        null=True,
        verbose_name='Телефон'
    )
    email = models.EmailField(
        verbose_name='E-mail'
    )
    responsible_person = models.TextField(
        verbose_name='Имя, должность и контактный номер ответственного лица'
    )
    representative_cities = models.JSONField(
        default=list,
        blank=True,
        verbose_name='Города представительств'
    )
    
    # Форма бизнеса
    business_form = models.CharField(
        max_length=20,
        choices=BUSINESS_FORM_CHOICES,
        blank=True,
        null=True,
        verbose_name='Форма бизнеса'
    )
    
    # Работы и услуги
    work_list = models.TextField(
        blank=True,
        null=True,
        verbose_name='Перечень работ которые можете предоставить'
    )
    
    # Приветственное сообщение
    welcome_message = models.TextField(
        blank=True,
        null=True,
        verbose_name='Приветственное сообщение о вашей компании'
    )
    
    # Условия сотрудничества
    cooperation_terms = models.TextField(
        blank=True,
        null=True,
        verbose_name='Условия сотрудничества при работе с клиентами из других городов или регионов'
    )
    
    # Сроки выполнения проектов
    project_timelines = models.TextField(
        blank=True,
        null=True,
        verbose_name='Сроки выполнения проектов в 1К, 2К и 3К квартирах средней площади'
    )
    
    # Сегменты (multiple choice)
    segments = models.JSONField(
        default=list,
        blank=True,
        verbose_name='Сегменты работы'
    )
    
    # Ссылки на социальные сети и другие каналы связи
    vk = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        verbose_name='VK'
    )
    telegram_channel = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        verbose_name='Telegram канал'
    )
    pinterest = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        verbose_name='Pinterest'
    )
    instagram = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        verbose_name='Instagram'
    )
    website = models.URLField(
        blank=True,
        null=True,
        verbose_name='Ваш сайт'
    )
    other_contacts = models.JSONField(
        default=list,
        blank=True,
        verbose_name='Другое - дополнительные контакты'
    )
    
    # Формат работы
    work_format = models.TextField(
        blank=True,
        null=True,
        verbose_name='Формат работы'
    )
    
    # Возможна ли оплата с учётом НДС?
    vat_payment = models.CharField(
        max_length=10,
        choices=VAT_PAYMENT_CHOICES,
        blank=True,
        null=True,
        verbose_name='Возможна ли оплата с учётом НДС?'
    )
    
    # Гарантии и их сроки
    guarantees = models.TextField(
        blank=True,
        null=True,
        verbose_name='Гарантии и их сроки'
    )
    
    # Условия работы с дизайнерами и/или поставщиками
    designer_supplier_terms = models.TextField(
        blank=True,
        null=True,
        verbose_name='Условия работы с дизайнерами и/или поставщиками'
    )
    
    # Выдаёте ли вы карточки журналов при рекомендации при заключении договора? (multiple choice)
    magazine_cards = models.JSONField(
        default=list,
        blank=True,
        verbose_name='Выдаёте ли вы карточки журналов при рекомендации при заключении договора?'
    )
    
    # Категории (multiple choice)
    categories = models.JSONField(
        default=list,
        blank=True,
        verbose_name='Категории'
    )
    
    # Скорость исполнения (JSONField: list of keys from SPEED_OF_EXECUTION_CHOICES)
    speed_of_execution = models.JSONField(
        default=list,
        blank=True,
        verbose_name='Скорость исполнения'
    )
    
    # Дополнительная информация
    additional_info = models.TextField(
        blank=True,
        null=True,
        verbose_name='Дополнительная информация'
    )
    
    # Согласие на обработку данных
    data_processing_consent = models.BooleanField(
        default=False,
        verbose_name='Согласие на обработку данных'
    )
    
    # Логотип компании и юридическая карта
    company_logo = models.ImageField(
        upload_to='repairs/logos/',
        blank=True,
        null=True,
        verbose_name='Логотип компании (shaxsiy kabinet uchun)'
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name='Дата создания'
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name='Дата обновления'
    )
    
    # Удалено (soft delete)
    is_deleted = models.BooleanField(
        default=False,
        verbose_name='Удалено'
    )
    
    class Meta:
        verbose_name = 'Анкета ремонтной бригады / подрядчика'
        verbose_name_plural = 'Анкеты ремонтных бригад / подрядчиков'
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.full_name} - {self.brand_name}"


class SupplierQuestionnaire(models.Model):
    """
    Анкета поставщика / салона / фабрики
    """
    BUSINESS_FORM_CHOICES = [
        ('own_business', 'Собственный бизнес'),
        ('franchise', 'Франшиза'),
    ]
    
    SEGMENT_CHOICES = [
        ('horeca', 'HoReCa'),
        ('business', 'Бизнес'),
        ('comfort', 'Комфорт'),
        ('premium', 'Премиум'),
        ('medium', 'Средний'),
        ('economy', 'Эконом'),
    ]
    
    STATUS_CHOICES = [
        ('pending', 'Ожидает модерации'),
        ('published', 'Опубликовано'),
        ('rejected', 'Отклонено'),
        ('archived', 'В архиве'),
    ]
    
    VAT_PAYMENT_CHOICES = [
        ('yes', 'Да'),
        ('no', 'Нет'),
    ]
    
    MAGAZINE_CARD_CHOICES = [
        ('hi_home', 'Hi Home'),
        ('in_home', 'IN HOME'),
        ('no', 'Нет'),
        ('other', 'Другое'),
    ]
    
    CATEGORY_CHOICES = [
        ('supplier', 'Поставщик'),
        ('exhibition_hall', 'Выставочный зал'),
        ('factory', 'Фабрика'),
        ('salon', 'Салон'),
        ('other', 'Другое'),
    ]
    
    SPEED_OF_EXECUTION_CHOICES = [
        ('in_stock', 'В наличии'),
        ('up_to_2_weeks', 'до 2х недель'),
        ('up_to_1_month', 'до 1 месяца'),
        ('up_to_3_months', 'до 3х месяцев'),
        ('not_important', 'Не важно'),
    ]
    
    # Группа
    group = models.CharField(
        max_length=50,
        choices=QUESTIONNAIRE_GROUP_CHOICES,
        default='supplier',
        verbose_name='Группа'
    )
    
    # Статус модерации
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='pending',
        verbose_name='Статус'
    )
    
    # Модерация пройдена
    is_moderation = models.BooleanField(
        default=False,
        verbose_name='Модерация пройдена'
    )
    
    # Основная информация
    full_name = models.CharField(
        max_length=255,
        verbose_name='ФИО'
    )
    phone = models.CharField(
        max_length=20,
        blank=True,
        null=True,
        verbose_name='Номер телефона'
    )
    brand_name = models.CharField(
        max_length=255,
        verbose_name='Название бренда (дополнительно в скобках укажите полное юридическое наименование компании)'
    )
    email = models.EmailField(
        verbose_name='E-mail'
    )
    responsible_person = models.TextField(
        verbose_name='Имя, должность и контактный номер ответственного лица'
    )
    representative_cities = models.JSONField(
        default=list,
        blank=True,
        verbose_name='Города представительств или салонов'
    )
    
    # Форма бизнеса
    business_form = models.CharField(
        max_length=20,
        choices=BUSINESS_FORM_CHOICES,
        blank=True,
        null=True,
        verbose_name='Форма бизнеса'
    )
    
    # Ассортимент продукции
    product_assortment = models.TextField(
        blank=True,
        null=True,
        verbose_name='Ассортимент продукции'
    )
    
    # Приветственное сообщение
    welcome_message = models.TextField(
        blank=True,
        null=True,
        verbose_name='Приветственное сообщение о вашей компании'
    )
    
    # Условия сотрудничества
    cooperation_terms = models.TextField(
        blank=True,
        null=True,
        verbose_name='Условия сотрудничества при работе с клиентами из других городов или регионов'
    )
    
    # Сегменты (multiple choice)
    segments = models.JSONField(
        default=list,
        blank=True,
        verbose_name='Сегменты работы'
    )
    
    # Ссылки на социальные сети и другие каналы связи
    vk = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        verbose_name='VK'
    )
    telegram_channel = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        verbose_name='Telegram kanal'
    )
    pinterest = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        verbose_name='Pinterest'
    )
    instagram = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        verbose_name='Instagram'
    )
    website = models.URLField(
        blank=True,
        null=True,
        verbose_name='Ваш сайт (Veb-sayt)'
    )
    other_contacts = models.JSONField(
        default=list,
        blank=True,
        verbose_name='Другое (Boshqa) - дополнительные контакты'
    )
    
    # Сроки поставки и формат работы (TextField - string)
    delivery_terms = models.TextField(
        blank=True,
        null=True,
        verbose_name='Сроки поставки и формат работы'
    )
    
    # Возможна ли оплата с учётом НДС?
    vat_payment = models.CharField(
        max_length=10,
        choices=VAT_PAYMENT_CHOICES,
        blank=True,
        null=True,
        verbose_name='Возможна ли оплата с учётом НДС?'
    )
    
    # Гарантии и их сроки
    guarantees = models.TextField(
        blank=True,
        null=True,
        verbose_name='Гарантии и их сроки'
    )
    
    # Условия работы с дизайнерами и/или подрядчиками
    designer_contractor_terms = models.TextField(
        blank=True,
        null=True,
        verbose_name='Условия работы с дизайнерами и/или подрядчиками'
    )
    
    # Выдаёте ли вы карточки журналов при покупке продукции? (multiple choice)
    magazine_cards = models.JSONField(
        default=list,
        blank=True,
        verbose_name='Выдаёте ли вы карточки журналов при покупке продукции?'
    )
    
    # Категории (multiple choice)
    categories = models.JSONField(
        default=list,
        blank=True,
        verbose_name='Категории'
    )
    
    # Дополнительные категории ассортимента (JSONField, null=True, blank=True)
    rough_materials = models.JSONField(
        default=list,
        blank=True,
        null=True,
        verbose_name='Черновые материалы'
    )
    finishing_materials = models.JSONField(
        default=list,
        blank=True,
        null=True,
        verbose_name='Чистовые материалы'
    )
    upholstered_furniture = models.JSONField(
        default=list,
        blank=True,
        null=True,
        verbose_name='Мягкая мебель'
    )
    cabinet_furniture = models.JSONField(
        default=list,
        blank=True,
        null=True,
        verbose_name='Корпусная мебель'
    )
    technique = models.JSONField(
        default=list,
        blank=True,
        null=True,
        verbose_name='Техника'
    )
    decor = models.JSONField(
        default=list,
        blank=True,
        null=True,
        verbose_name='Декор'
    )
    
    # Скорость исполнения / сроки поставки (JSONField: list of keys from SPEED_OF_EXECUTION_CHOICES)
    speed_of_execution = models.JSONField(
        default=list,
        blank=True,
        verbose_name='Скорость исполнения'
    )
    
    # Согласие на обработку данных
    data_processing_consent = models.BooleanField(
        default=False,
        verbose_name='Согласие на обработку данных'
    )
    
    # Логотип компании и юридическая карта
    company_logo = models.ImageField(
        upload_to='suppliers/logos/',
        blank=True,
        null=True,
        verbose_name='Логотип компании (shaxsiy kabinet uchun)'
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name='Дата создания'
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name='Дата обновления'
    )
    
    # Удалено (soft delete)
    is_deleted = models.BooleanField(
        default=False,
        verbose_name='Удалено'
    )
    
    class Meta:
        verbose_name = 'Анкета поставщика / салона / фабрики'
        verbose_name_plural = 'Анкеты поставщиков / салонов / фабрик'
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.full_name} - {self.brand_name}"


class MediaQuestionnaire(models.Model):
    """
    Анкета медиа пространства и интерьерных журналов
    """
    BUSINESS_FORM_CHOICES = [
        ('own_business', 'Собственный бизнес'),
        ('franchise', 'Франшиза'),
    ]
    
    SEGMENT_CHOICES = [
        ('horeca', 'HoReCa'),
        ('business', 'Бизнес'),
        ('comfort', 'Комфорт'),
        ('premium', 'Премиум'),
        ('medium', 'Средний'),
        ('economy', 'Эконом'),
    ]
    
    STATUS_CHOICES = [
        ('pending', 'Ожидает модерации'),
        ('published', 'Опубликовано'),
        ('rejected', 'Отклонено'),
        ('archived', 'В архиве'),
    ]
    
    VAT_PAYMENT_CHOICES = [
        ('yes', 'Да'),
        ('no', 'Нет'),
    ]
    
    # Группа
    group = models.CharField(
        max_length=50,
        choices=QUESTIONNAIRE_GROUP_CHOICES,
        default='supplier',
        verbose_name='Группа'
    )
    
    # Статус модерации
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='pending',
        verbose_name='Статус'
    )
    
    # Модерация пройдена
    is_moderation = models.BooleanField(
        default=False,
        verbose_name='Модерация пройдена'
    )
    
    # Основная информация
    full_name = models.CharField(
        max_length=255,
        verbose_name='ФИО'
    )
    phone = models.CharField(
        max_length=20,
        blank=True,
        null=True,
        verbose_name='Номер телефона'
    )
    brand_name = models.CharField(
        max_length=255,
        verbose_name='Название бренда'
    )
    phone = models.CharField(
        max_length=20,
        blank=True,
        null=True,
        verbose_name='Телефон'
    )
    email = models.EmailField(
        verbose_name='E-mail'
    )
    responsible_person = models.TextField(
        verbose_name='Имя, должность и контактный номер ответственного лица'
    )
    representative_cities = models.JSONField(
        default=list,
        blank=True,
        verbose_name='Города представительств (массив объектов: город, адрес, телефон, район)'
    )
    
    # Форма бизнеса
    business_form = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        verbose_name='Форма бизнеса: Собственный бизнес или франшиза? (с указанием налоговой формы)'
    )
    
    # Описание деятельности
    activity_description = models.TextField(
        verbose_name='Опишите подробно чем именно занимаетесь и чем можете быть полезны сообществу'
    )
    
    # Приветственное сообщение
    welcome_message = models.TextField(
        verbose_name='Приветственное сообщение о вашей компании'
    )
    
    # Условия сотрудничества
    cooperation_terms = models.TextField(
        verbose_name='Условия сотрудничества'
    )
    
    # Сегменты (multiple choice)
    segments = models.JSONField(
        default=list,
        verbose_name='Сегменты, которые принимаете к публикации'
    )
    
    # Ссылки на социальные сети и другие каналы связи
    vk = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        verbose_name='VK'
    )
    telegram_channel = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        verbose_name='Telegram канал'
    )
    pinterest = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        verbose_name='Pinterest'
    )
    instagram = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        verbose_name='Instagram'
    )
    website = models.URLField(
        blank=True,
        null=True,
        verbose_name='Ваш сайт'
    )
    other_contacts = models.JSONField(
        default=list,
        blank=True,
        verbose_name='Другое - дополнительные контакты'
    )
    
    # Возможна ли оплата с учётом НДС?
    vat_payment = models.CharField(
        max_length=10,
        choices=VAT_PAYMENT_CHOICES,
        blank=True,
        null=True,
        verbose_name='Возможна ли оплата с учётом НДС?'
    )
    
    # Дополнительная информация
    additional_info = models.TextField(
        blank=True,
        null=True,
        verbose_name='Дополнительная информация'
    )
    
    # Логотип компании
    company_logo = models.ImageField(
        upload_to='media/logos/',
        blank=True,
        null=True,
        verbose_name='Логотип компании (shaxsiy kabinet uchun)'
    )
    
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name='Дата создания'
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name='Дата обновления'
    )
    
    # Удалено (soft delete)
    is_deleted = models.BooleanField(
        default=False,
        verbose_name='Удалено'
    )
    
    class Meta:
        verbose_name = 'Анкета медиа пространства и интерьерных журналов'
        verbose_name_plural = 'Анкеты медиа пространств и интерьерных журналов'
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.full_name} - {self.brand_name}"


class Report(models.Model):
    """
    Отчет о подписке пользователя
    """
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='reports',
        verbose_name='Пользователь'
    )
    start_date = models.DateField(
        verbose_name='Дата начала'
    )
    end_date = models.DateField(
        verbose_name='Дата окончания'
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name='Дата создания'
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name='Дата обновления'
    )
    
    class Meta:
        verbose_name = 'Отчет'
        verbose_name_plural = 'Отчеты'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', 'start_date', 'end_date']),
        ]
    
    def __str__(self):
        return f"{self.user.phone} - {self.start_date} to {self.end_date}"


