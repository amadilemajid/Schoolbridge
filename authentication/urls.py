from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    LoginView, LogoutView, TokenRefreshView,
    PasswordResetRequestView, PasswordResetConfirmView,
    ChangePasswordView, StaffViewSet, MeView,
)

router = DefaultRouter()
router.register('staff', StaffViewSet, basename='staff')
router.register('users', StaffViewSet, basename='users')

urlpatterns = [
    path('login/', LoginView.as_view(), name='login'),
    path('token/', LoginView.as_view(), name='token'),
    path('logout/', LogoutView.as_view(), name='logout'),
    path('token/refresh/', TokenRefreshView.as_view(), name='token-refresh'),
    path('password/reset/', PasswordResetRequestView.as_view(), name='password-reset-request'),
    path('password-reset/', PasswordResetRequestView.as_view(), name='password-reset-request-alias'),
    path('password/reset/confirm/', PasswordResetConfirmView.as_view(), name='password-reset-confirm'),
    path('password-reset/confirm/', PasswordResetConfirmView.as_view(), name='password-reset-confirm-alias'),
    path('password/change/', ChangePasswordView.as_view(), name='password-change'),
    path('me/', MeView.as_view(), name='me'),
    path('', include(router.urls)),
]
