from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient
from rest_framework import status
from django.contrib.auth import get_user_model
from django.utils import timezone
from datetime import timedelta

from .models import UpcomingEvent

User = get_user_model()


class UpcomingEventTests(TestCase):
    """Тесты для ближайших мероприятий"""
    
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            phone='+79991234567',
            role='designer'
        )
        self.admin_user = User.objects.create_user(
            phone='+79991234568',
            role='admin',
            is_staff=True
        )
        self.list_url = reverse('upcoming-event-list')
        self.detail_url = lambda pk: reverse('upcoming-event-detail', args=[pk])
    
    def test_create_event_authenticated(self):
        """Тест создания мероприятия авторизованным пользователем"""
        self.client.force_authenticate(user=self.user)
        data = {
            'organization_name': 'Test Organization',
            'event_type': 'training',
            'announcement': 'Test announcement',
            'event_date': (timezone.now() + timedelta(days=7)).isoformat(),
            'event_location': 'Test Location',
            'city': 'Moscow',
            'registration_phone': '+79991234567',
            'about_event': 'Test about event',
            'status': 'draft'
        }
        response = self.client.post(self.list_url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(UpcomingEvent.objects.count(), 1)
        event = UpcomingEvent.objects.first()
        self.assertEqual(event.created_by, self.user)
    
    def test_create_event_unauthenticated(self):
        """Тест создания мероприятия неавторизованным пользователем"""
        data = {
            'organization_name': 'Test Organization',
            'event_type': 'training',
            'announcement': 'Test announcement',
            'event_date': (timezone.now() + timedelta(days=7)).isoformat(),
            'event_location': 'Test Location',
            'city': 'Moscow',
            'registration_phone': '+79991234567',
            'about_event': 'Test about event',
            'status': 'draft'
        }
        response = self.client.post(self.list_url, data, format='json')
        # AllowAny permission, но created_by будет None
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        event = UpcomingEvent.objects.first()
        self.assertIsNone(event.created_by)
    
    def test_get_event_list_published_only(self):
        """Тест получения списка только опубликованных мероприятий"""
        # Создаем опубликованное мероприятие
        event1 = UpcomingEvent.objects.create(
            organization_name='Published Event',
            event_type='training',
            announcement='Test',
            event_date=timezone.now() + timedelta(days=7),
            event_location='Location',
            city='Moscow',
            registration_phone='+79991234567',
            about_event='About',
            status='published'
        )
        # Создаем черновик
        event2 = UpcomingEvent.objects.create(
            organization_name='Draft Event',
            event_type='training',
            announcement='Test',
            event_date=timezone.now() + timedelta(days=7),
            event_location='Location',
            city='Moscow',
            registration_phone='+79991234567',
            about_event='About',
            status='draft'
        )
        
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # Неавторизованный пользователь видит только опубликованные
        if isinstance(response.data, list):
            event_ids = [item['id'] for item in response.data]
        else:
            event_ids = [item['id'] for item in response.data.get('results', [])]
        self.assertIn(event1.id, event_ids)
        self.assertNotIn(event2.id, event_ids)
    
    def test_get_event_list_staff_sees_all(self):
        """Тест получения списка всех мероприятий для администратора"""
        # Создаем опубликованное мероприятие
        event1 = UpcomingEvent.objects.create(
            organization_name='Published Event',
            event_type='training',
            announcement='Test',
            event_date=timezone.now() + timedelta(days=7),
            event_location='Location',
            city='Moscow',
            registration_phone='+79991234567',
            about_event='About',
            status='published'
        )
        # Создаем черновик
        event2 = UpcomingEvent.objects.create(
            organization_name='Draft Event',
            event_type='training',
            announcement='Test',
            event_date=timezone.now() + timedelta(days=7),
            event_location='Location',
            city='Moscow',
            registration_phone='+79991234567',
            about_event='About',
            status='draft'
        )
        
        self.client.force_authenticate(user=self.admin_user)
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # Администратор видит все мероприятия
        if isinstance(response.data, list):
            event_ids = [item['id'] for item in response.data]
        else:
            event_ids = [item['id'] for item in response.data.get('results', [])]
        self.assertIn(event1.id, event_ids)
        self.assertIn(event2.id, event_ids)
    
    def test_get_event_detail_published(self):
        """Тест получения деталей опубликованного мероприятия"""
        event = UpcomingEvent.objects.create(
            organization_name='Test Event',
            event_type='training',
            announcement='Test',
            event_date=timezone.now() + timedelta(days=7),
            event_location='Location',
            city='Moscow',
            registration_phone='+79991234567',
            about_event='About',
            status='published'
        )
        
        response = self.client.get(self.detail_url(event.id))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['organization_name'], 'Test Event')
    
    def test_get_event_detail_draft_unauthorized(self):
        """Тест получения деталей черновика неавторизованным пользователем"""
        event = UpcomingEvent.objects.create(
            organization_name='Draft Event',
            event_type='training',
            announcement='Test',
            event_date=timezone.now() + timedelta(days=7),
            event_location='Location',
            city='Moscow',
            registration_phone='+79991234567',
            about_event='About',
            status='draft',
            created_by=self.user
        )
        
        response = self.client.get(self.detail_url(event.id))
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
    
    def test_get_event_detail_draft_creator(self):
        """Тест получения деталей черновика создателем"""
        event = UpcomingEvent.objects.create(
            organization_name='Draft Event',
            event_type='training',
            announcement='Test',
            event_date=timezone.now() + timedelta(days=7),
            event_location='Location',
            city='Moscow',
            registration_phone='+79991234567',
            about_event='About',
            status='draft',
            created_by=self.user
        )
        
        self.client.force_authenticate(user=self.user)
        response = self.client.get(self.detail_url(event.id))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
    
    def test_update_event_creator(self):
        """Тест обновления мероприятия создателем"""
        event = UpcomingEvent.objects.create(
            organization_name='Test Event',
            event_type='training',
            announcement='Test',
            event_date=timezone.now() + timedelta(days=7),
            event_location='Location',
            city='Moscow',
            registration_phone='+79991234567',
            about_event='About',
            status='published',
            created_by=self.user
        )
        
        self.client.force_authenticate(user=self.user)
        data = {'organization_name': 'Updated Event'}
        response = self.client.patch(self.detail_url(event.id), data, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        event.refresh_from_db()
        self.assertEqual(event.organization_name, 'Updated Event')
    
    def test_update_event_not_creator(self):
        """Тест обновления мероприятия не создателем"""
        other_user = User.objects.create_user(
            phone='+79991234569',
            role='designer'
        )
        event = UpcomingEvent.objects.create(
            organization_name='Test Event',
            event_type='training',
            announcement='Test',
            event_date=timezone.now() + timedelta(days=7),
            event_location='Location',
            city='Moscow',
            registration_phone='+79991234567',
            about_event='About',
            status='published',
            created_by=self.user
        )
        
        self.client.force_authenticate(user=other_user)
        data = {'organization_name': 'Updated Event'}
        response = self.client.patch(self.detail_url(event.id), data, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
    
    def test_update_event_admin(self):
        """Тест обновления мероприятия администратором"""
        event = UpcomingEvent.objects.create(
            organization_name='Test Event',
            event_type='training',
            announcement='Test',
            event_date=timezone.now() + timedelta(days=7),
            event_location='Location',
            city='Moscow',
            registration_phone='+79991234567',
            about_event='About',
            status='published',
            created_by=self.user
        )
        
        self.client.force_authenticate(user=self.admin_user)
        data = {'organization_name': 'Updated Event'}
        response = self.client.patch(self.detail_url(event.id), data, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        event.refresh_from_db()
        self.assertEqual(event.organization_name, 'Updated Event')
    
    def test_delete_event_creator(self):
        """Тест удаления мероприятия создателем"""
        event = UpcomingEvent.objects.create(
            organization_name='Test Event',
            event_type='training',
            announcement='Test',
            event_date=timezone.now() + timedelta(days=7),
            event_location='Location',
            city='Moscow',
            registration_phone='+79991234567',
            about_event='About',
            status='published',
            created_by=self.user
        )
        
        self.client.force_authenticate(user=self.user)
        response = self.client.delete(self.detail_url(event.id))
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertEqual(UpcomingEvent.objects.count(), 0)
    
    def test_filter_by_city(self):
        """Тест фильтрации по городу"""
        UpcomingEvent.objects.create(
            organization_name='Moscow Event',
            event_type='training',
            announcement='Test',
            event_date=timezone.now() + timedelta(days=7),
            event_location='Location',
            city='Moscow',
            registration_phone='+79991234567',
            about_event='About',
            status='published'
        )
        UpcomingEvent.objects.create(
            organization_name='SPB Event',
            event_type='training',
            announcement='Test',
            event_date=timezone.now() + timedelta(days=7),
            event_location='Location',
            city='Saint Petersburg',
            registration_phone='+79991234567',
            about_event='About',
            status='published'
        )
        
        response = self.client.get(self.list_url, {'city': 'Moscow'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        if isinstance(response.data, list):
            cities = [item['city'] for item in response.data]
        else:
            cities = [item['city'] for item in response.data.get('results', [])]
        self.assertIn('Moscow', cities)
        self.assertNotIn('Saint Petersburg', cities)
    
    def test_filter_by_event_type(self):
        """Тест фильтрации по типу мероприятия"""
        UpcomingEvent.objects.create(
            organization_name='Training Event',
            event_type='training',
            announcement='Test',
            event_date=timezone.now() + timedelta(days=7),
            event_location='Location',
            city='Moscow',
            registration_phone='+79991234567',
            about_event='About',
            status='published'
        )
        UpcomingEvent.objects.create(
            organization_name='Presentation Event',
            event_type='presentation',
            announcement='Test',
            event_date=timezone.now() + timedelta(days=7),
            event_location='Location',
            city='Moscow',
            registration_phone='+79991234567',
            about_event='About',
            status='published'
        )
        
        response = self.client.get(self.list_url, {'event_type': 'training'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        if isinstance(response.data, list):
            event_types = [item['event_type'] for item in response.data]
        else:
            event_types = [item['event_type'] for item in response.data.get('results', [])]
        self.assertIn('training', event_types)
        self.assertNotIn('presentation', event_types)
    
    def test_search(self):
        """Тест поиска"""
        UpcomingEvent.objects.create(
            organization_name='Design School',
            event_type='training',
            announcement='Test',
            event_date=timezone.now() + timedelta(days=7),
            event_location='Location',
            city='Moscow',
            registration_phone='+79991234567',
            about_event='About',
            status='published'
        )
        UpcomingEvent.objects.create(
            organization_name='Other Event',
            event_type='training',
            announcement='Test',
            event_date=timezone.now() + timedelta(days=7),
            event_location='Location',
            city='Moscow',
            registration_phone='+79991234567',
            about_event='About',
            status='published'
        )
        
        response = self.client.get(self.list_url, {'search': 'Design'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        if isinstance(response.data, list):
            names = [item['organization_name'] for item in response.data]
        else:
            names = [item['organization_name'] for item in response.data.get('results', [])]
        self.assertIn('Design School', names)
        self.assertNotIn('Other Event', names)
    
    def test_ordering(self):
        """Тест сортировки"""
        event1 = UpcomingEvent.objects.create(
            organization_name='Event 1',
            event_type='training',
            announcement='Test',
            event_date=timezone.now() + timedelta(days=7),
            event_location='Location',
            city='Moscow',
            registration_phone='+79991234567',
            about_event='About',
            status='published'
        )
        event2 = UpcomingEvent.objects.create(
            organization_name='Event 2',
            event_type='training',
            announcement='Test',
            event_date=timezone.now() + timedelta(days=14),
            event_location='Location',
            city='Moscow',
            registration_phone='+79991234567',
            about_event='About',
            status='published'
        )
        
        response = self.client.get(self.list_url, {'ordering': 'event_date'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        if isinstance(response.data, list):
            event_ids = [item['id'] for item in response.data]
        else:
            event_ids = [item['id'] for item in response.data.get('results', [])]
        # Первое событие должно быть раньше
        self.assertEqual(event_ids[0], event1.id)
        self.assertEqual(event_ids[1], event2.id)


class RatingPageViewTests(TestCase):
    """Тесты для страницы рейтингов"""
    
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            phone='+79991234567',
            role='designer'
        )
        self.rating_url = reverse('rating-page')
    
    def test_get_ratings_authenticated(self):
        """Тест получения рейтингов авторизованным пользователем"""
        self.client.force_authenticate(user=self.user)
        response = self.client.get(self.rating_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # Должен вернуться список (может быть пустым)
        self.assertIsInstance(response.data, (list, dict))
    
    def test_get_ratings_unauthenticated(self):
        """Тест получения рейтингов неавторизованным пользователем"""
        response = self.client.get(self.rating_url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
    
    def test_get_ratings_with_questionnaires(self):
        """Тест получения рейтингов с анкетами"""
        from apps.accounts.models import DesignerQuestionnaire
        
        questionnaire = DesignerQuestionnaire.objects.create(
            full_name='Test Designer',
            phone='+79991234567',
            email='test@example.com',
            city='Moscow',
            group='design',
            status='published',
            is_moderation=True
        )
        
        self.client.force_authenticate(user=self.user)
        response = self.client.get(self.rating_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # Должна быть хотя бы одна анкета
        if isinstance(response.data, list):
            self.assertGreaterEqual(len(response.data), 1)
        else:
            self.assertGreaterEqual(len(response.data.get('results', [])), 1)


class ReviewsPageViewTests(TestCase):
    """Тесты для страницы отзывов"""
    
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            phone='+79991234567',
            role='designer'
        )
        self.reviews_url = reverse('reviews-page')
    
    def test_get_reviews_authenticated(self):
        """Тест получения отзывов авторизованным пользователем"""
        self.client.force_authenticate(user=self.user)
        response = self.client.get(self.reviews_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # Должен вернуться список (может быть пустым)
        self.assertIsInstance(response.data, (list, dict))
    
    def test_get_reviews_unauthenticated(self):
        """Тест получения отзывов неавторизованным пользователем"""
        response = self.client.get(self.reviews_url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
    
    def test_filter_reviews_by_status(self):
        """Тест фильтрации отзывов по статусу"""
        from apps.ratings.models import QuestionnaireRating
        from apps.accounts.models import DesignerQuestionnaire
        
        questionnaire1 = DesignerQuestionnaire.objects.create(
            full_name='Test Designer 1',
            phone='+79991234567',
            email='test1@example.com',
            city='Moscow',
            group='design',
            status='published',
            is_moderation=True
        )
        questionnaire2 = DesignerQuestionnaire.objects.create(
            full_name='Test Designer 2',
            phone='+79991234568',
            email='test2@example.com',
            city='Moscow',
            group='design',
            status='published',
            is_moderation=True
        )
        
        rating1 = QuestionnaireRating.objects.create(
            reviewer=self.user,
            role='Дизайн',
            questionnaire_id=questionnaire1.id,
            is_positive=True,
            text='Great!',
            status='approved'
        )
        rating2 = QuestionnaireRating.objects.create(
            reviewer=self.user,
            role='Дизайн',
            questionnaire_id=questionnaire2.id,
            is_positive=False,
            text='Not good',
            status='pending'
        )
        
        self.client.force_authenticate(user=self.user)
        response = self.client.get(self.reviews_url, {'status': 'approved'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        if isinstance(response.data, list):
            statuses = [item['status'] for item in response.data]
        else:
            statuses = [item['status'] for item in response.data.get('results', [])]
        self.assertIn('approved', statuses)
        self.assertNotIn('pending', statuses)
