from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient
from rest_framework import status
from django.contrib.auth import get_user_model

from .models import QuestionnaireRating
from apps.accounts.models import DesignerQuestionnaire, RepairQuestionnaire, SupplierQuestionnaire, MediaQuestionnaire

User = get_user_model()


class QuestionnaireRatingCreateTests(TestCase):
    """Тесты для создания рейтингов"""
    
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            phone='+79991234567',
            role='designer'
        )
        self.create_url = reverse('questionnaire-rating-create')
    
    def test_create_rating_designer(self):
        """Тест создания рейтинга для дизайнера"""
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
        data = {
            'role': 'Дизайн',
            'id_questionnaire': questionnaire.id,
            'is_positive': True,
            'is_constructive': False,
            'text': 'Great designer!'
        }
        response = self.client.post(self.create_url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(QuestionnaireRating.objects.count(), 1)
        rating = QuestionnaireRating.objects.first()
        self.assertEqual(rating.reviewer, self.user)
        self.assertEqual(rating.role, 'Дизайн')
        self.assertEqual(rating.questionnaire_id, questionnaire.id)
        self.assertTrue(rating.is_positive)
        self.assertEqual(rating.status, 'pending')
    
    def test_create_rating_repair(self):
        """Тест создания рейтинга для ремонтной бригады"""
        questionnaire = RepairQuestionnaire.objects.create(
            full_name='Test Repair',
            phone='+79991234567',
            brand_name='Test Brand',
            email='test@example.com',
            responsible_person='Test Person',
            group='repair',
            status='published',
            is_moderation=True
        )
        
        self.client.force_authenticate(user=self.user)
        data = {
            'role': 'Ремонт',
            'id_questionnaire': questionnaire.id,
            'is_positive': False,
            'is_constructive': True,
            'text': 'Constructive feedback'
        }
        response = self.client.post(self.create_url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        rating = QuestionnaireRating.objects.first()
        self.assertFalse(rating.is_positive)
        self.assertTrue(rating.is_constructive)
    
    def test_create_rating_duplicate(self):
        """Тест создания дублирующего рейтинга (должен обновиться)"""
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
        data = {
            'role': 'Дизайн',
            'id_questionnaire': questionnaire.id,
            'is_positive': True,
            'is_constructive': False,
            'text': 'First review'
        }
        response1 = self.client.post(self.create_url, data, format='json')
        self.assertEqual(response1.status_code, status.HTTP_201_CREATED)
        
        # Второй запрос должен обновить существующий рейтинг
        data['text'] = 'Updated review'
        response2 = self.client.post(self.create_url, data, format='json')
        self.assertEqual(response2.status_code, status.HTTP_200_OK)
        self.assertEqual(QuestionnaireRating.objects.count(), 1)
        rating = QuestionnaireRating.objects.first()
        self.assertEqual(rating.text, 'Updated review')
        self.assertEqual(rating.status, 'pending')  # Статус сбрасывается на pending
    
    def test_create_rating_unauthenticated(self):
        """Тест создания рейтинга неавторизованным пользователем"""
        questionnaire = DesignerQuestionnaire.objects.create(
            full_name='Test Designer',
            phone='+79991234567',
            email='test@example.com',
            city='Moscow',
            group='design',
            status='published',
            is_moderation=True
        )
        
        data = {
            'role': 'Дизайн',
            'id_questionnaire': questionnaire.id,
            'is_positive': True,
            'is_constructive': False,
            'text': 'Great designer!'
        }
        response = self.client.post(self.create_url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
    
    def test_create_rating_questionnaire_not_found(self):
        """Тест создания рейтинга для несуществующей анкеты"""
        self.client.force_authenticate(user=self.user)
        data = {
            'role': 'Дизайн',
            'id_questionnaire': 99999,
            'is_positive': True,
            'is_constructive': False,
            'text': 'Great designer!'
        }
        response = self.client.post(self.create_url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


class QuestionnaireRatingDetailTests(TestCase):
    """Тесты для деталей рейтинга"""
    
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            phone='+79991234567',
            role='designer'
        )
        self.other_user = User.objects.create_user(
            phone='+79991234568',
            role='designer'
        )
        self.questionnaire = DesignerQuestionnaire.objects.create(
            full_name='Test Designer',
            phone='+79991234567',
            email='test@example.com',
            city='Moscow',
            group='design',
            status='published',
            is_moderation=True
        )
        self.rating = QuestionnaireRating.objects.create(
            reviewer=self.user,
            role='Дизайн',
            questionnaire_id=self.questionnaire.id,
            is_positive=True,
            is_constructive=False,
            text='Great designer!',
            status='pending'
        )
        self.detail_url = lambda pk: reverse('questionnaire-rating-detail', args=[pk])
    
    def test_get_rating_owner(self):
        """Тест получения рейтинга владельцем"""
        self.client.force_authenticate(user=self.user)
        response = self.client.get(self.detail_url(self.rating.id))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['text'], 'Great designer!')
    
    def test_get_rating_not_owner(self):
        """Тест получения рейтинга не владельцем"""
        self.client.force_authenticate(user=self.other_user)
        response = self.client.get(self.detail_url(self.rating.id))
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
    
    def test_update_rating_owner(self):
        """Тест обновления рейтинга владельцем"""
        self.client.force_authenticate(user=self.user)
        data = {
            'text': 'Updated review',
            'is_positive': False,
            'is_constructive': True
        }
        response = self.client.patch(self.detail_url(self.rating.id), data, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.rating.refresh_from_db()
        self.assertEqual(self.rating.text, 'Updated review')
        self.assertFalse(self.rating.is_positive)
        self.assertTrue(self.rating.is_constructive)
        self.assertEqual(self.rating.status, 'pending')  # Статус сбрасывается на pending
    
    def test_update_rating_not_owner(self):
        """Тест обновления рейтинга не владельцем"""
        self.client.force_authenticate(user=self.other_user)
        data = {'text': 'Updated review'}
        response = self.client.patch(self.detail_url(self.rating.id), data, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
    
    def test_delete_rating_owner(self):
        """Тест удаления рейтинга владельцем"""
        self.client.force_authenticate(user=self.user)
        response = self.client.delete(self.detail_url(self.rating.id))
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertEqual(QuestionnaireRating.objects.count(), 0)
    
    def test_delete_rating_not_owner(self):
        """Тест удаления рейтинга не владельцем"""
        self.client.force_authenticate(user=self.other_user)
        response = self.client.delete(self.detail_url(self.rating.id))
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class QuestionnaireRatingAllViewTests(TestCase):
    """Тесты для списка всех рейтингов"""
    
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            phone='+79991234567',
            role='designer'
        )
        self.all_url = reverse('questionnaire-rating-all')
    
    def test_get_all_ratings_unauthenticated(self):
        """Тест получения всех рейтингов неавторизованным пользователем"""
        response = self.client.get(self.all_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIsInstance(response.data, list)
    
    def test_get_all_ratings_with_questionnaires(self):
        """Тест получения всех рейтингов с анкетами"""
        questionnaire = DesignerQuestionnaire.objects.create(
            full_name='Test Designer',
            phone='+79991234567',
            email='test@example.com',
            city='Moscow',
            group='design',
            status='published',
            is_moderation=True
        )
        
        QuestionnaireRating.objects.create(
            reviewer=self.user,
            role='Дизайн',
            questionnaire_id=questionnaire.id,
            is_positive=True,
            is_constructive=False,
            text='Great!',
            status='approved'
        )
        
        response = self.client.get(self.all_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertGreaterEqual(len(response.data), 1)
        # Проверяем структуру данных
        item = response.data[0]
        self.assertIn('request_name', item)
        self.assertIn('id', item)
        self.assertIn('name', item)
        self.assertIn('group', item)
        self.assertIn('total_rating_count', item)
        self.assertIn('positive_rating_count', item)
        self.assertIn('constructive_rating_count', item)
    
    def test_get_all_ratings_only_approved(self):
        """Тест получения только approved рейтингов"""
        questionnaire = DesignerQuestionnaire.objects.create(
            full_name='Test Designer',
            phone='+79991234567',
            email='test@example.com',
            city='Moscow',
            group='design',
            status='published',
            is_moderation=True
        )
        
        # Создаем approved рейтинг
        QuestionnaireRating.objects.create(
            reviewer=self.user,
            role='Дизайн',
            questionnaire_id=questionnaire.id,
            is_positive=True,
            text='Approved review',
            status='approved'
        )
        
        # Создаем pending рейтинг с другим пользователем (чтобы избежать unique constraint)
        other_user = User.objects.create_user(
            phone='+79991234568',
            role='designer'
        )
        QuestionnaireRating.objects.create(
            reviewer=other_user,
            role='Дизайн',
            questionnaire_id=questionnaire.id,
            is_positive=True,
            text='Pending review',
            status='pending'
        )
        
        response = self.client.get(self.all_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # Должен быть только approved рейтинг
        item = response.data[0]
        self.assertEqual(item['total_rating_count'], 1)
        self.assertEqual(item['positive_rating_count'], 1)


class QuestionnaireRatingStatusUpdateTests(TestCase):
    """Тесты для обновления статуса рейтинга"""
    
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
        self.questionnaire = DesignerQuestionnaire.objects.create(
            full_name='Test Designer',
            phone='+79991234567',
            email='test@example.com',
            city='Moscow',
            group='design',
            status='published',
            is_moderation=True
        )
        self.rating = QuestionnaireRating.objects.create(
            reviewer=self.user,
            role='Дизайн',
            questionnaire_id=self.questionnaire.id,
            is_positive=True,
            is_constructive=False,
            text='Great designer!',
            status='pending'
        )
        self.status_url = lambda pk: reverse('questionnaire-rating-status-update', args=[pk])
    
    def test_update_status_admin(self):
        """Тест обновления статуса администратором"""
        self.client.force_authenticate(user=self.admin_user)
        data = {'status': 'approved'}
        response = self.client.patch(self.status_url(self.rating.id), data, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.rating.refresh_from_db()
        self.assertEqual(self.rating.status, 'approved')
    
    def test_update_status_not_admin(self):
        """Тест обновления статуса не администратором"""
        self.client.force_authenticate(user=self.user)
        data = {'status': 'approved'}
        response = self.client.patch(self.status_url(self.rating.id), data, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
    
    def test_update_status_invalid(self):
        """Тест обновления статуса невалидным значением"""
        self.client.force_authenticate(user=self.admin_user)
        data = {'status': 'invalid'}
        response = self.client.patch(self.status_url(self.rating.id), data, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
    
    def test_update_status_all_statuses(self):
        """Тест обновления всех возможных статусов"""
        self.client.force_authenticate(user=self.admin_user)
        
        # pending -> approved
        data = {'status': 'approved'}
        response = self.client.patch(self.status_url(self.rating.id), data, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.rating.refresh_from_db()
        self.assertEqual(self.rating.status, 'approved')
        
        # approved -> rejected
        data = {'status': 'rejected'}
        response = self.client.patch(self.status_url(self.rating.id), data, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.rating.refresh_from_db()
        self.assertEqual(self.rating.status, 'rejected')
        
        # rejected -> pending
        data = {'status': 'pending'}
        response = self.client.patch(self.status_url(self.rating.id), data, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.rating.refresh_from_db()
        self.assertEqual(self.rating.status, 'pending')
