from django.urls import path, include
from rest_framework.routers import DefaultRouter
from onboarding import views

router = DefaultRouter()
router.register('requests', views.SchoolRegistrationRequestViewSet, basename='onboarding-request')

urlpatterns = [
    path('register/', views.SchoolOnboardingRegisterView.as_view(), name='onboarding-register'),
    path('health/', views.HealthCheckView.as_view(), name='health-check'),
    path('', include(router.urls)),
]
