"""
Authentication views.
US-002: Login with lockout.
US-003: Role-based staff management.
US-004: Password reset (one-time link, 60 min expiry).
US-005: Refresh token rotation.
US-006: Account deactivation (sessions invalidated).
US-007: All auth events audit-logged.
"""
import secrets
import datetime
from django.conf import settings
from django.core.mail import send_mail
from django.utils import timezone
from django.template.loader import render_to_string
from rest_framework import generics, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.exceptions import TokenError
from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import serializers as drf_serializers

from .models import User, PasswordHistory, PasswordResetToken
from .serializers import (
    LoginSerializer, UserRegistrationSerializer, UserSerializer,
    PasswordResetRequestSerializer, PasswordResetConfirmSerializer,
    ChangePasswordSerializer,
)
from audit.mixins import AuditMixin
from schools.permissions import IsDirector, IsSchoolStaff
import logging

logger = logging.getLogger('schoolbridge')


class LoginView(AuditMixin, generics.GenericAPIView):
    """US-002: JWT login with lockout."""
    permission_classes = [AllowAny]
    serializer_class = LoginSerializer
    throttle_scope = 'anon'  # 10/min for auth endpoints (US-072)

    @extend_schema(
        request=LoginSerializer,
        responses={200: UserSerializer},
        tags=['Authentication'],
    )

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data['user']
        tokens = serializer.create_tokens(user)
        self.log_auth_event('LOGIN_SUCCESS', user, request)
        return Response(tokens, status=status.HTTP_200_OK)


class LogoutView(AuditMixin, generics.GenericAPIView):
    """US-005: Blacklist refresh token on logout."""
    permission_classes = [IsAuthenticated]

    @extend_schema(
        request=inline_serializer(
            name='LogoutRequest',
            fields={'refresh': drf_serializers.CharField()},
        ),
        responses={200: inline_serializer(name='LogoutResponse', fields={'message': drf_serializers.CharField()})},
        tags=['Authentication'],
    )

    def post(self, request):
        refresh_token = request.data.get('refresh')
        if not refresh_token:
            return Response({'error': 'Refresh token required.'}, status=400)
        try:
            token = RefreshToken(refresh_token)
            token.blacklist()
            self.log_auth_event('LOGOUT', request.user, request)
        except TokenError:
            pass  # Already blacklisted or invalid — treat as logged out
        return Response({'message': 'Logged out successfully.'})


class TokenRefreshView(generics.GenericAPIView):
    """US-005: Rotate refresh token on each use."""
    permission_classes = [AllowAny]

    @extend_schema(
        request=inline_serializer(
            name='TokenRefreshRequest',
            fields={'refresh': drf_serializers.CharField()},
        ),
        responses={200: inline_serializer(
            name='TokenRefreshResponse',
            fields={
                'access': drf_serializers.CharField(),
                'refresh': drf_serializers.CharField(),
            },
        )},
        tags=['Authentication'],
    )

    def post(self, request):
        refresh_token = request.data.get('refresh')
        if not refresh_token:
            return Response({'error': 'Refresh token required.'}, status=400)
        try:
            token = RefreshToken(refresh_token)
            # Rotation: old token blacklisted, new tokens issued
            access = str(token.access_token)
            token.blacklist()
            user_id = token.payload.get('user_id')
            user = User.objects.get(id=user_id, is_active=True)
            new_refresh = RefreshToken.for_user(user)
            new_refresh['role'] = user.role
            new_refresh['school_id'] = str(user.school_id) if user.school_id else None
            return Response({
                'access': str(new_refresh.access_token),
                'refresh': str(new_refresh),
            })
        except (TokenError, User.DoesNotExist) as e:
            return Response({'error': 'Invalid or expired refresh token.'}, status=401)


class PasswordResetRequestView(generics.GenericAPIView):
    """US-004: Send secure one-time reset link (60 min expiry)."""
    permission_classes = [AllowAny]
    serializer_class = PasswordResetRequestSerializer
    throttle_scope = 'anon'

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data['email']

        # Always return 200 — never reveal if email exists (security)
        try:
            user = User.objects.get(email=email, is_active=True)
            # Invalidate any existing tokens
            PasswordResetToken.objects.filter(user=user, used_at__isnull=True).delete()
            token = PasswordResetToken.objects.create(
                user=user,
                token=secrets.token_urlsafe(48),
                expires_at=timezone.now() + datetime.timedelta(minutes=60),
            )
            reset_url = f"{settings.FRONTEND_URL}/reset-password?token={token.token}"
            send_mail(
                subject='SchoolBridge — Password Reset Request',
                message=f'Click this link to reset your password (expires in 60 minutes):\n\n{reset_url}',
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[email],
                fail_silently=True,
            )
            logger.info(f"Password reset requested for {email}")
        except User.DoesNotExist:
            pass  # Silent — security

        return Response({'message': 'If an account exists with this email, a reset link has been sent.'})


class PasswordResetConfirmView(AuditMixin, generics.GenericAPIView):
    """US-004: Consume reset token, set new password."""
    permission_classes = [AllowAny]
    serializer_class = PasswordResetConfirmSerializer

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        reset_token = serializer.validated_data['reset_token']
        new_password = serializer.validated_data['password']
        user = reset_token.user

        user.set_password(new_password)
        user.save()

        # Record in password history (US-004)
        PasswordHistory.record(user, new_password)

        # Mark token as used (one-time only)
        reset_token.mark_used()

        # Invalidate all active sessions (US-005)
        from rest_framework_simplejwt.token_blacklist.models import OutstandingToken
        OutstandingToken.objects.filter(user=user).delete()

        self.log_auth_event('PASSWORD_RESET', user, request)
        return Response({'message': 'Password reset successful. Please log in with your new password.'})


class ChangePasswordView(AuditMixin, generics.GenericAPIView):
    """Authenticated password change."""
    permission_classes = [IsAuthenticated]
    serializer_class = ChangePasswordSerializer

    def post(self, request):
        serializer = self.get_serializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)

        new_password = serializer.validated_data['new_password']
        user = request.user
        user.set_password(new_password)
        user.save()
        PasswordHistory.record(user, new_password)

        # Invalidate all other sessions (US-005)
        refresh_token = request.data.get('current_refresh')
        if refresh_token:
            from rest_framework_simplejwt.token_blacklist.models import OutstandingToken
            OutstandingToken.objects.filter(user=user).exclude(token=refresh_token).delete()

        self.log_auth_event('PASSWORD_CHANGED', user, request)
        return Response({'message': 'Password changed successfully.'})


class StaffViewSet(AuditMixin, viewsets.ModelViewSet):
    """
    US-003: Staff management (Director only).
    US-006: Account deactivation — active sessions invalidated within 60s.
    """
    permission_classes = [IsDirector]
    serializer_class = UserSerializer

    def get_queryset(self):
        return User.objects.filter(
            school=self.request.user.school
        ).exclude(role='system_admin').order_by('last_name', 'first_name')

    def get_serializer_class(self):
        if self.action == 'create':
            return UserRegistrationSerializer
        return UserSerializer

    def perform_create(self, serializer):
        user = serializer.save()
        self.log_action('STAFF_CREATED', user, {
            'email': user.email, 'role': user.role
        })

    @action(detail=True, methods=['post'], permission_classes=[IsDirector])
    def deactivate(self, request, pk=None):
        """US-006: Deactivate account; invalidate all tokens immediately."""
        user = self.get_object()
        if user == request.user:
            return Response({'error': 'You cannot deactivate your own account.'}, status=400)

        user.is_active = False
        user.deactivated_at = timezone.now()
        user.deactivated_by = request.user
        user.save(update_fields=['is_active', 'deactivated_at', 'deactivated_by'])

        # US-006: Invalidate ALL active tokens for this user immediately
        from rest_framework_simplejwt.token_blacklist.models import OutstandingToken
        OutstandingToken.objects.filter(user=user).delete()

        self.log_action('STAFF_DEACTIVATED', user, {
            'email': user.email, 'deactivated_by': str(request.user.id)
        })
        return Response({'message': f'{user.get_full_name()} has been deactivated.'})

    @action(detail=True, methods=['post'], permission_classes=[IsDirector])
    def reactivate(self, request, pk=None):
        user = self.get_object()
        user.is_active = True
        user.deactivated_at = None
        user.deactivated_by = None
        user.save(update_fields=['is_active', 'deactivated_at', 'deactivated_by'])
        self.log_action('STAFF_REACTIVATED', user, {'email': user.email})
        return Response({'message': f'{user.get_full_name()} has been reactivated.'})

    @action(detail=True, methods=['patch'], permission_classes=[IsDirector])
    def change_role(self, request, pk=None):
        """US-003: All role changes must be audit-logged."""
        user = self.get_object()
        new_role = request.data.get('role')
        allowed_roles = [r[0] for r in User.ROLE_CHOICES if r[0] != 'system_admin']
        if new_role not in allowed_roles:
            return Response({'error': f'Invalid role. Choose from: {allowed_roles}'}, status=400)
        old_role = user.role
        user.role = new_role
        user.save(update_fields=['role'])
        self.log_action('ROLE_CHANGED', user, {
            'email': user.email, 'old_role': old_role, 'new_role': new_role
        })
        return Response({'message': f'Role updated to {new_role}.'})


class MeView(generics.RetrieveUpdateAPIView):
    """Current user profile."""
    permission_classes = [IsAuthenticated]
    serializer_class = UserSerializer

    def get_object(self):
        return self.request.user
