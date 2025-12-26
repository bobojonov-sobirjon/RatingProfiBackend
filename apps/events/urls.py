from django.urls import path
from .views import (
    UpcomingEventListView,
    UpcomingEventDetailView,
    RatingPageView,
    ReviewsPageView,
)

urlpatterns = [
    path('upcoming-events/', UpcomingEventListView.as_view(), name='upcoming-event-list'),
    path('upcoming-events/<int:pk>/', UpcomingEventDetailView.as_view(), name='upcoming-event-detail'),
    path('ratings/', RatingPageView.as_view(), name='rating-page'),
    path('reviews/', ReviewsPageView.as_view(), name='reviews-page'),
]
