from django.urls import path
from .views import (
    QuestionnaireRatingCreateView,
    QuestionnaireRatingAllView,
    QuestionnaireRatingDetailView,
    QuestionnaireRatingStatusUpdateView,
)

urlpatterns = [
    path('questionnaire-ratings/', QuestionnaireRatingCreateView.as_view(), name='questionnaire-rating-create'),
    path('questionnaire-ratings/all/', QuestionnaireRatingAllView.as_view(), name='questionnaire-rating-all'),
    path('questionnaire-ratings/<int:pk>/', QuestionnaireRatingDetailView.as_view(), name='questionnaire-rating-detail'),
    path('questionnaire-ratings/<int:pk>/update-status/', QuestionnaireRatingStatusUpdateView.as_view(), name='questionnaire-rating-status-update'),
]
