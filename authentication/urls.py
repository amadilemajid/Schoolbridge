from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    LoginView, LogoutView, TokenRefreshView,
    PasswordResetRequestView, PasswordResetConfirmView,
    ChangePasswordView, StaffViewSet, MeView,
)

router = DefaultRouter()
router.register('staff', StaffViewSet, basename='staff')

urlpatterns = [
    path('login/', LoginView.as_view(), name='login'),
    path('logout/', LogoutView.as_view(), name='logout'),
    path('token/refresh/', TokenRefreshView.as_view(), name='token-refresh'),
    path('password/reset/', PasswordResetRequestView.as_view(), name='password-reset-request'),
    path('password/reset/confirm/', PasswordResetConfirmView.as_view(), name='password-reset-confirm'),
    path('password/change/', ChangePasswordView.as_view(), name='password-change'),
    path('me/', MeView.as_view(), name='me'),
    path('', include(router.urls)),
]
