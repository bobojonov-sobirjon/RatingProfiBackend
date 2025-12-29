"""
Скрипт для генерации фейковых данных для всех моделей
Использование: python generate_fake_data.py
"""

import os
import sys
import django
from datetime import datetime, timedelta
from random import choice, randint, sample
import random

# Настройка Django
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django.contrib.auth import get_user_model
from apps.events.models import UpcomingEvent
from apps.accounts.models import DesignerQuestionnaire, RepairQuestionnaire, SupplierQuestionnaire, MediaQuestionnaire
from apps.ratings.models import QuestionnaireRating
from django.utils import timezone

User = get_user_model()

# Русские данные для генерации
RUSSIAN_CITIES = [
    'Москва', 'Санкт-Петербург', 'Новосибирск', 'Екатеринбург', 'Казань',
    'Нижний Новгород', 'Челябинск', 'Самара', 'Омск', 'Ростов-на-Дону',
    'Уфа', 'Красноярск', 'Воронеж', 'Пермь', 'Волгоград', 'Краснодар',
    'Сочи', 'Тюмень', 'Иркутск', 'Барнаул'
]

RUSSIAN_FIRST_NAMES = [
    'Александр', 'Дмитрий', 'Максим', 'Сергей', 'Андрей', 'Алексей',
    'Артем', 'Илья', 'Кирилл', 'Михаил', 'Никита', 'Матвей',
    'Анна', 'Мария', 'Елена', 'Ольга', 'Татьяна', 'Наталья',
    'Ирина', 'Светлана', 'Екатерина', 'Юлия', 'Анастасия', 'Дарья'
]

RUSSIAN_LAST_NAMES = [
    'Иванов', 'Петров', 'Смирнов', 'Козлов', 'Волков', 'Соколов',
    'Лебедев', 'Новиков', 'Федоров', 'Морозов', 'Попов', 'Семенов',
    'Иванова', 'Петрова', 'Смирнова', 'Козлова', 'Волкова', 'Соколова'
]

RUSSIAN_MIDDLE_NAMES = [
    'Александрович', 'Дмитриевич', 'Максимович', 'Сергеевич', 'Андреевич',
    'Александровна', 'Дмитриевна', 'Максимовна', 'Сергеевна', 'Андреевна'
]

ORGANIZATION_NAMES = [
    'Студия дизайна "Элегант"', 'Мастерская интерьеров', 'Дом мечты',
    'Премиум ремонт', 'Стройка плюс', 'Идеальный интерьер',
    'Салон мебели "Комфорт"', 'Фабрика мебели "Престиж"',
    'Журнал "Современный интерьер"', 'Медиа группа "Дизайн"',
    'Студия "Архитектура"', 'Бюро дизайна "Стиль"'
]

BRAND_NAMES = [
    'Элегант', 'Престиж', 'Комфорт', 'Стиль', 'Люкс', 'Премиум',
    'Идеал', 'Мастер', 'Профи', 'Эксклюзив', 'Топ', 'Элит'
]


def generate_phone():
    """Генерация российского номера телефона"""
    return f"+7{randint(900, 999)}{randint(1000000, 9999999)}"


def generate_email(name):
    """Генерация email"""
    name_clean = name.lower().replace(' ', '').replace('ё', 'e')
    domains = ['mail.ru', 'yandex.ru', 'gmail.com', 'rambler.ru']
    return f"{name_clean}@{choice(domains)}"


def create_users(count=20):
    """Создание пользователей"""
    print(f"Создание {count} пользователей...")
    users = []
    roles = ['designer', 'repair', 'supplier', 'media']
    
    for i in range(count):
        first_name = choice(RUSSIAN_FIRST_NAMES)
        last_name = choice(RUSSIAN_LAST_NAMES)
        full_name = f"{last_name} {first_name}"
        phone = generate_phone()
        
        # Проверка на уникальность телефона
        while User.objects.filter(phone=phone).exists():
            phone = generate_phone()
        
        user = User.objects.create_user(
            phone=phone,
            password='test123456',
            full_name=full_name,
            role=choice(roles),
            city=choice(RUSSIAN_CITIES),
            is_phone_verified=True,
            is_active=True
        )
        users.append(user)
        print(f"  [OK] Создан пользователь: {full_name} ({phone})")
    
    return users


def create_upcoming_events(count=15):
    """Создание мероприятий"""
    print(f"\nСоздание {count} мероприятий...")
    events = []
    event_types = ['training', 'presentation', 'opening', 'leisure']
    statuses = ['published', 'published', 'published', 'draft']  # Больше published
    
    for i in range(count):
        event_date = timezone.now() + timedelta(days=randint(1, 90))
        
        event = UpcomingEvent.objects.create(
            organization_name=choice(ORGANIZATION_NAMES),
            event_type=choice(event_types),
            announcement=f"Приглашаем вас на мероприятие! Это будет незабываемое событие с участием ведущих специалистов индустрии. {choice(['Обучение', 'Презентация', 'Открытие', 'Досуговое мероприятие'])} пройдет в комфортной обстановке.",
            event_date=event_date,
            event_location=f"г. {choice(RUSSIAN_CITIES)}, ул. {choice(['Ленина', 'Пушкина', 'Гагарина', 'Мира'])} {randint(1, 100)}",
            city=choice(RUSSIAN_CITIES),
            registration_phone=generate_phone(),
            about_event=f"Подробная информация о мероприятии. Мы рады пригласить вас на это уникальное событие. В программе: {choice(['мастер-классы', 'презентации', 'выставки', 'встречи'])} с профессионалами индустрии.",
            status=choice(statuses),
            created_by=None
        )
        events.append(event)
        print(f"  [OK] Создано мероприятие: {event.organization_name} ({event.city})")
    
    return events


def create_designer_questionnaires(count=12):
    """Создание анкет дизайнеров"""
    print(f"\nСоздание {count} анкет дизайнеров...")
    questionnaires = []
    services_list = [
        'author_supervision', 'architecture', 'decorator', 'designer_horika',
        'residential_designer', 'commercial_designer', 'completing',
        'landscape_design', 'design', 'light_designer', 'home_stager'
    ]
    segments_list = ['horeca', 'business', 'comfort', 'premium', 'medium', 'economy']
    work_types = ['own_name', 'studio']
    
    for i in range(count):
        first_name = choice(RUSSIAN_FIRST_NAMES)
        last_name = choice(RUSSIAN_LAST_NAMES)
        middle_name = choice(RUSSIAN_MIDDLE_NAMES)
        full_name = f"{last_name} {first_name} {middle_name}"
        city = choice(RUSSIAN_CITIES)
        
        questionnaire = DesignerQuestionnaire.objects.create(
            group='design',
            status='published',
            is_moderation=True,
            full_name=full_name,
            full_name_en=f"{first_name} {last_name}",
            phone=generate_phone(),
            birth_date=datetime(1980 + randint(0, 30), randint(1, 12), randint(1, 28)).date(),
            email=generate_email(full_name),
            city=city,
            services=sample(services_list, randint(2, 5)),
            work_type=choice(work_types),
            welcome_message=f"Приветствую! Я {first_name}, профессиональный дизайнер интерьеров с опытом работы более {randint(5, 15)} лет. Специализируюсь на создании стильных и функциональных пространств.",
            work_cities=[choice(RUSSIAN_CITIES) for _ in range(randint(1, 3))],
            cooperation_terms=f"Работаю в городах: {', '.join([choice(RUSSIAN_CITIES) for _ in range(2)])}. Условия сотрудничества обсуждаются индивидуально.",
            segments=sample(segments_list, randint(2, 4)),
            unique_trade_proposal=f"Мое УТП: индивидуальный подход к каждому проекту, использование современных материалов и технологий, гарантия качества.",
            vk=f"vk.com/{full_name.lower().replace(' ', '')}",
            instagram=f"@{full_name.lower().replace(' ', '')}",
            website=f"https://www.{full_name.lower().replace(' ', '')}.ru",
            service_packages_description=f"Пакет услуг: от {randint(2000, 5000)} руб/м². Включает: проектирование, авторский надзор, комплектацию.",
            vat_payment=choice(['yes', 'no']),
            additional_info=f"Дополнительная информация о моей работе и опыте. Выполнено более {randint(50, 200)} проектов.",
            data_processing_consent=True,
            is_deleted=False
        )
        questionnaires.append(questionnaire)
        print(f"  [OK] Создана анкета дизайнера: {full_name} ({city})")
    
    return questionnaires


def create_repair_questionnaires(count=12):
    """Создание анкет ремонтных бригад"""
    print(f"\nСоздание {count} анкет ремонтных бригад...")
    questionnaires = []
    segments_list = ['horeca', 'business', 'comfort', 'premium', 'medium', 'economy']
    business_forms = ['own_business', 'franchise']
    magazine_cards = ['hi_home', 'in_home', 'no', 'other']
    
    for i in range(count):
        first_name = choice(RUSSIAN_FIRST_NAMES)
        last_name = choice(RUSSIAN_LAST_NAMES)
        full_name = f"{last_name} {first_name}"
        brand_name = f"{choice(BRAND_NAMES)} Ремонт"
        city = choice(RUSSIAN_CITIES)
        
        questionnaire = RepairQuestionnaire.objects.create(
            group='repair',
            status='published',
            is_moderation=True,
            full_name=full_name,
            phone=generate_phone(),
            brand_name=f"{brand_name} (ООО '{brand_name}')",
            email=generate_email(brand_name),
            responsible_person=f"{full_name}, директор, {generate_phone()}",
            representative_cities=[city] + [choice(RUSSIAN_CITIES) for _ in range(randint(0, 2))],
            business_form=choice(business_forms),
            work_list=f"Выполняем следующие виды работ: черновая отделка, чистовая отделка, сантехнические работы, электромонтажные работы, плиточные работы, малярные работы, установка дверей и окон.",
            welcome_message=f"Добро пожаловать! Компания '{brand_name}' - это команда профессионалов с опытом работы более {randint(5, 20)} лет. Мы гарантируем качество и соблюдение сроков.",
            cooperation_terms=f"Работаем в городах: {', '.join([choice(RUSSIAN_CITIES) for _ in range(2)])}. Условия сотрудничества: предоплата {randint(20, 50)}%.",
            project_timelines=f"Сроки выполнения: 1К квартира - {randint(30, 60)} дней, 2К - {randint(45, 90)} дней, 3К - {randint(60, 120)} дней.",
            segments=sample(segments_list, randint(2, 4)),
            vk=f"vk.com/{brand_name.lower().replace(' ', '')}",
            instagram=f"@{brand_name.lower().replace(' ', '')}",
            website=f"https://www.{brand_name.lower().replace(' ', '')}.ru",
            work_format=f"Формат работы: {choice(['Под ключ', 'Поэтапно', 'По договору'])}",
            vat_payment=choice(['yes', 'no']),
            guarantees=f"Гарантия на выполненные работы: {randint(12, 36)} месяцев.",
            designer_supplier_terms=f"Условия работы с дизайнерами: скидка {randint(5, 15)}% при рекомендации.",
            magazine_cards=choice(magazine_cards),
            additional_info=f"Дополнительная информация о компании. Выполнено более {randint(100, 500)} объектов.",
            data_processing_consent=True,
            is_deleted=False
        )
        questionnaires.append(questionnaire)
        print(f"  [OK] Создана анкета ремонтной бригады: {brand_name} ({city})")
    
    return questionnaires


def create_supplier_questionnaires(count=12):
    """Создание анкет поставщиков"""
    print(f"\nСоздание {count} анкет поставщиков...")
    questionnaires = []
    segments_list = ['horeca', 'business', 'comfort', 'premium', 'medium', 'economy']
    business_forms = ['own_business', 'franchise']
    magazine_cards = ['hi_home', 'in_home', 'no', 'other']
    
    for i in range(count):
        first_name = choice(RUSSIAN_FIRST_NAMES)
        last_name = choice(RUSSIAN_LAST_NAMES)
        full_name = f"{last_name} {first_name}"
        brand_name = f"{choice(BRAND_NAMES)} {choice(['Мебель', 'Салон', 'Фабрика'])}"
        city = choice(RUSSIAN_CITIES)
        
        questionnaire = SupplierQuestionnaire.objects.create(
            group='supplier',
            status='published',
            is_moderation=True,
            full_name=full_name,
            phone=generate_phone(),
            brand_name=f"{brand_name} (ООО '{brand_name}')",
            email=generate_email(brand_name),
            responsible_person=f"{full_name}, директор, {generate_phone()}",
            representative_cities=[city] + [choice(RUSSIAN_CITIES) for _ in range(randint(0, 3))],
            business_form=choice(business_forms),
            product_assortment=f"Ассортимент: {choice(['Мягкая мебель', 'Корпусная мебель', 'Черновые материалы', 'Чистовые материалы', 'Декор', 'Техника'])}. Более {randint(500, 2000)} наименований.",
            welcome_message=f"Добро пожаловать! '{brand_name}' - это {choice(['салон', 'фабрика', 'выставочный зал'])} с широким ассортиментом качественной продукции. Работаем более {randint(5, 25)} лет.",
            cooperation_terms=f"Работаем по всей России. Условия: доставка {randint(5, 15)} дней, скидка дизайнерам {randint(10, 30)}%.",
            segments=sample(segments_list, randint(2, 5)),
            vk=f"vk.com/{brand_name.lower().replace(' ', '')}",
            instagram=f"@{brand_name.lower().replace(' ', '')}",
            website=f"https://www.{brand_name.lower().replace(' ', '')}.ru",
            delivery_terms=f"Сроки поставки: в наличии - {randint(1, 7)} дней, под заказ - {randint(14, 90)} дней.",
            vat_payment=choice(['yes', 'no']),
            guarantees=f"Гарантия на продукцию: {randint(12, 60)} месяцев.",
            designer_contractor_terms=f"Условия для дизайнеров: скидка до {randint(10, 30)}%, карточки журналов при покупке.",
            magazine_cards=choice(magazine_cards),
            data_processing_consent=True,
            is_deleted=False
        )
        questionnaires.append(questionnaire)
        print(f"  [OK] Создана анкета поставщика: {brand_name} ({city})")
    
    return questionnaires


def create_media_questionnaires(count=12):
    """Создание анкет медиа"""
    print(f"\nСоздание {count} анкет медиа...")
    questionnaires = []
    segments_list = ['horeca', 'business', 'comfort', 'premium', 'medium', 'economy']
    business_forms = ['own_business', 'franchise']
    
    for i in range(count):
        first_name = choice(RUSSIAN_FIRST_NAMES)
        last_name = choice(RUSSIAN_LAST_NAMES)
        full_name = f"{last_name} {first_name}"
        brand_name = f"{choice(['Современный', 'Премиум', 'Элитный', 'Профессиональный'])} {choice(['Интерьер', 'Дизайн', 'Журнал', 'Медиа'])}"
        city = choice(RUSSIAN_CITIES)
        
        questionnaire = MediaQuestionnaire.objects.create(
            group='media',
            status='published',
            is_moderation=True,
            full_name=full_name,
            phone=generate_phone(),
            brand_name=brand_name,
            email=generate_email(brand_name),
            responsible_person=f"{full_name}, главный редактор, {generate_phone()}",
            representative_cities=[{
                'city': city,
                'address': f"ул. {choice(['Ленина', 'Пушкина', 'Гагарина'])} {randint(1, 100)}",
                'phone': generate_phone(),
                'district': choice(['Центральный', 'Северный', 'Южный', 'Восточный', 'Западный'])
            }],
            business_form=f"{choice(business_forms)} ({choice(['ООО', 'ИП', 'ЗАО'])})",
            activity_description=f"Мы занимаемся публикацией материалов о дизайне интерьеров, архитектуре и декоре. Предоставляем площадку для продвижения дизайнеров, поставщиков и подрядчиков.",
            welcome_message=f"Добро пожаловать! '{brand_name}' - это {choice(['журнал', 'медиа-пространство', 'онлайн-платформа'])} о дизайне интерьеров. Мы помогаем профессионалам находить друг друга.",
            cooperation_terms=f"Условия сотрудничества: публикация материалов, размещение рекламы, организация мероприятий. Стоимость обсуждается индивидуально.",
            segments=sample(segments_list, randint(2, 5)),
            vk=f"vk.com/{brand_name.lower().replace(' ', '')}",
            instagram=f"@{brand_name.lower().replace(' ', '')}",
            website=f"https://www.{brand_name.lower().replace(' ', '')}.ru",
            vat_payment=choice(['yes', 'no']),
            is_deleted=False
        )
        questionnaires.append(questionnaire)
        print(f"  [OK] Создана анкета медиа: {brand_name} ({city})")
    
    return questionnaires


def create_ratings(users, questionnaires):
    """Создание рейтингов"""
    print(f"\nСоздание рейтингов...")
    ratings = []
    roles_map = {
        DesignerQuestionnaire: 'Дизайн',
        RepairQuestionnaire: 'Ремонт',
        SupplierQuestionnaire: 'Поставщик',
        MediaQuestionnaire: 'Медиа'
    }
    
    review_texts_positive = [
        "Отличная работа! Очень доволен результатом.",
        "Профессионал своего дела. Рекомендую!",
        "Качественное выполнение работ, соблюдение сроков.",
        "Прекрасный специалист, внимательный к деталям.",
        "Очень понравилось сотрудничество. Спасибо!",
        "Высокий уровень профессионализма.",
        "Отличное качество продукции и сервиса.",
        "Рекомендую всем! Остался очень доволен."
    ]
    
    review_texts_constructive = [
        "Хорошая работа, но есть моменты для улучшения.",
        "В целом неплохо, но можно было лучше.",
        "Работа выполнена, но есть замечания по срокам.",
        "Качество хорошее, но коммуникация могла быть лучше."
    ]
    
    # Создаем рейтинги для каждого типа анкет
    for model_class, role in roles_map.items():
        qs_list = list(model_class.objects.filter(is_moderation=True, status='published')[:10])
        
        for questionnaire in qs_list:
            # Создаем 2-4 рейтинга для каждой анкеты
            num_ratings = randint(2, 4)
            selected_users = sample(users, min(num_ratings, len(users)))
            
            for user in selected_users:
                is_positive = choice([True, True, True, False])  # Больше положительных
                is_constructive = not is_positive
                
                text = choice(review_texts_positive) if is_positive else choice(review_texts_constructive)
                status_rating = choice(['approved', 'approved', 'approved', 'pending'])  # Больше approved
                
                rating, created = QuestionnaireRating.objects.get_or_create(
                    reviewer=user,
                    role=role,
                    questionnaire_id=questionnaire.id,
                    defaults={
                        'is_positive': is_positive,
                        'is_constructive': is_constructive,
                        'text': text,
                        'status': status_rating
                    }
                )
                
                if created:
                    ratings.append(rating)
                    print(f"  [OK] Создан рейтинг: {role} #{questionnaire.id} ({'положительный' if is_positive else 'конструктивный'})")
    
    return ratings


def main():
    """Главная функция"""
    print("=" * 60)
    print("ГЕНЕРАЦИЯ ФЕЙКОВЫХ ДАННЫХ ДЛЯ ВСЕХ МОДЕЛЕЙ")
    print("=" * 60)
    
    try:
        # Создание пользователей
        users = create_users(20)
        
        # Создание мероприятий
        events = create_upcoming_events(15)
        
        # Создание анкет
        designer_qs = create_designer_questionnaires(12)
        repair_qs = create_repair_questionnaires(12)
        supplier_qs = create_supplier_questionnaires(12)
        media_qs = create_media_questionnaires(12)
        
        # Создание рейтингов
        all_questionnaires = designer_qs + repair_qs + supplier_qs + media_qs
        ratings = create_ratings(users, all_questionnaires)
        
        print("\n" + "=" * 60)
        print("ГЕНЕРАЦИЯ ЗАВЕРШЕНА УСПЕШНО!")
        print("=" * 60)
        print(f"[OK] Пользователей: {len(users)}")
        print(f"[OK] Мероприятий: {len(events)}")
        print(f"[OK] Анкет дизайнеров: {len(designer_qs)}")
        print(f"[OK] Анкет ремонтных бригад: {len(repair_qs)}")
        print(f"[OK] Анкет поставщиков: {len(supplier_qs)}")
        print(f"[OK] Анкет медиа: {len(media_qs)}")
        print(f"[OK] Рейтингов: {len(ratings)}")
        print("=" * 60)
        
    except Exception as e:
        print(f"\n[ERROR] ОШИБКА: {str(e)}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0


if __name__ == '__main__':
    exit(main())
