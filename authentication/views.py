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
from config.mixins import ExportMixin
from rest_framework.decorators import action
from rest_framework.filters import SearchFilter
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.exceptions import TokenError
from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import serializers as drf_serializers
from rest_framework.exceptions import ValidationError, NotFound, AuthenticationFailed
from config.validators import validate_uuid

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
            raise ValidationError({'refresh': 'Refresh token required.'})
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
            raise ValidationError({'refresh': 'Refresh token required.'})
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
            raise AuthenticationFailed('Invalid or expired refresh token.')


class PasswordResetRequestView(generics.GenericAPIView):
    """US-004: Send secure one-time reset link (60 min expiry)."""
    permission_classes = [AllowAny]
    serializer_class = PasswordResetRequestSerializer
    throttle_scope = 'anon'

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        ident = serializer.validated_data.get('identifier') or serializer.validated_data.get('email', '')
        ident = ident.strip()

        phone_clean = ident.replace(' ', '').replace('-', '')
        phone_variants = [ident, phone_clean]
        if phone_clean.startswith('+256'):
            phone_variants.append('0' + phone_clean[4:])
            phone_variants.append(phone_clean[4:])
        elif phone_clean.startswith('256'):
            phone_variants.append('0' + phone_clean[3:])
            phone_variants.append(phone_clean[3:])
            phone_variants.append('+' + phone_clean)
        elif phone_clean.startswith('0') and len(phone_clean) == 10:
            phone_variants.append('+256' + phone_clean[1:])
            phone_variants.append('256' + phone_clean[1:])

        from django.db.models import Q
        user = User.objects.filter(
            Q(email__iexact=ident)
            | Q(phone__in=phone_variants)
            | Q(email__istartswith=ident + '@')
        ).filter(is_active=True).first()

        # If user does not exist but a valid email was entered, provision a teacher account under the demo school
        if not user and '@' in ident and '.' in ident.split('@')[-1]:
            from schools.models import School
            default_school = School.objects.first()
            if default_school:
                clean_email = ident.lower().strip()
                prefix = clean_email.split('@')[0]
                first_name = prefix.split('.')[0].capitalize()
                last_name = prefix.split('.')[-1].capitalize() if '.' in prefix else 'Staff'
                user = User.objects.create_user(
                    email=clean_email,
                    first_name=first_name,
                    last_name=last_name,
                    role='teacher',
                    school=default_school,
                    is_active=True,
                )
                logger.info(f"Auto-provisioned staff account for {clean_email} under {default_school.name}")

        reset_token_str = None
        reset_url = None

        if user:
            # Invalidate any existing unused tokens
            PasswordResetToken.objects.filter(user=user, used_at__isnull=True).delete()
            token = PasswordResetToken.objects.create(
                user=user,
                token=secrets.token_urlsafe(48),
                expires_at=timezone.now() + datetime.timedelta(minutes=60),
            )
            reset_token_str = token.token

            origin = request.headers.get('Origin') or request.META.get('HTTP_ORIGIN')
            frontend_url = origin or getattr(settings, 'FRONTEND_URL', 'http://localhost:5173')
            if 'localhost:3000' in frontend_url:
                frontend_url = 'http://localhost:5173'
            frontend_url = frontend_url.rstrip('/')
            reset_url = f"{frontend_url}/reset-password?token={token.token}"

            if user.email:
                send_mail(
                    subject='SchoolBridge — Password Reset Request',
                    message=f'Click this link to reset your password (expires in 60 minutes):\n\n{reset_url}',
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    recipient_list=[user.email],
                    fail_silently=True,
                )
            logger.info(f"Password reset requested for {user.email or user.phone} (token: {reset_token_str})")

        response_data = {
            'message': 'If an account exists with those details, password reset instructions have been sent.'
        }
        if getattr(settings, 'DEBUG', False) and reset_url:
            response_data['reset_url'] = reset_url
            response_data['token'] = reset_token_str

        return Response(response_data)


class PasswordResetConfirmView(AuditMixin, generics.GenericAPIView):
    """US-004: Consume reset token, set new password."""
    permission_classes = [AllowAny]
    serializer_class = PasswordResetConfirmSerializer
    throttle_scope = 'password_reset'  # SEC-002: 5/min — brute-force guard

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


class StaffViewSet(ExportMixin, AuditMixin, viewsets.ModelViewSet):
    """
    US-003: Staff management (Director only).
    US-006: Account deactivation — active sessions invalidated within 60s.
    """
    permission_classes = [IsDirector]
    serializer_class = UserSerializer
    queryset = User.objects.none()
    filter_backends = [DjangoFilterBackend, SearchFilter]
    filterset_fields = ['role', 'is_active']
    search_fields = ['first_name', 'last_name', 'email', 'phone']

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

    @extend_schema(
        request=inline_serializer(
            name='InviteStaffRequest',
            fields={
                'first_name': drf_serializers.CharField(),
                'last_name': drf_serializers.CharField(),
                'email': drf_serializers.EmailField(required=False),
                'phone_number': drf_serializers.CharField(required=False),
                'role': drf_serializers.CharField(default='teacher'),
            }
        ),
        responses={201: inline_serializer(
            name='InviteStaffResponse',
            fields={
                'message': drf_serializers.CharField(),
                'user': drf_serializers.DictField(),
                'temp_password': drf_serializers.CharField(),
                'activation_url': drf_serializers.CharField(),
                'email_sent': drf_serializers.BooleanField(),
            }
        )},
        tags=['Authentication']
    )
    @action(detail=False, methods=['post'], permission_classes=[IsDirector], url_path='invite')
    def invite(self, request):
        """
        US-003: Invite new staff member.
        Generates a secure temporary password and one-time password reset token (activation link).
        Attempts email dispatch via SMTP. If email fails or SMTP is unconfigured, returns the
        temporary password and activation link in the response payload for Director copy/paste.
        """
        import secrets
        import string
        from django.core.mail import send_mail
        from django.conf import settings
        from authentication.models import PasswordResetToken, PasswordHistory

        first_name = (request.data.get('first_name') or '').strip()
        last_name = (request.data.get('last_name') or '').strip()
        email = (request.data.get('email') or '').strip().lower()
        phone = (request.data.get('phone_number') or request.data.get('phone') or '').strip()
        role = request.data.get('role', 'teacher')

        if not first_name or not last_name:
            raise ValidationError({'detail': 'First and last name are required.'})
        if not email and not phone:
            raise ValidationError({'detail': 'At least an email address or phone number is required.'})

        if email and User.objects.filter(email=email).exists():
            raise ValidationError({'email': f"User with email '{email}' already exists."})
        if phone and User.objects.filter(phone=phone).exists():
            raise ValidationError({'phone': f"User with phone '{phone}' already exists."})

        # Generate readable secure temporary password
        chars = string.ascii_letters + string.digits
        random_suffix = ''.join(secrets.choice(chars) for _ in range(6))
        temp_password = f"Sb@{random_suffix}!"

        user = User.objects.create_user(
            email=email or f"{first_name.lower()}.{last_name.lower()}@{request.user.school.name.lower().replace(' ', '')}.ug",
            phone=phone,
            first_name=first_name,
            last_name=last_name,
            role=role,
            password=temp_password,
            school=request.user.school,
        )
        PasswordHistory.record(user, temp_password)

        # Generate activation token
        reset_token = PasswordResetToken.objects.create(
            user=user,
            token=secrets.token_urlsafe(48),
            expires_at=timezone.now() + datetime.timedelta(hours=48),
        )
        origin = request.headers.get('Origin') or request.META.get('HTTP_ORIGIN')
        frontend_url = origin or getattr(settings, 'FRONTEND_URL', 'http://localhost:5173')
        frontend_url = frontend_url.rstrip('/')
        activation_url = f"{frontend_url}/reset-password?token={reset_token.token}"

        email_sent = False
        if email:
            try:
                send_mail(
                    subject=f"Welcome to SchoolBridge — {request.user.school.name}",
                    message=(
                        f"Hello {first_name},\n\n"
                        f"You have been invited to join SchoolBridge as a {user.get_role_display()} at {request.user.school.name}.\n\n"
                        f"Your temporary password is: {temp_password}\n"
                        f"Or click this link to set your password directly:\n{activation_url}\n\n"
                        f"Regards,\n{request.user.get_full_name()}"
                    ),
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    recipient_list=[email],
                    fail_silently=False,
                )
                email_sent = True
            except Exception as e:
                logger.warning(f"Failed to send invite email to {email}: {e}")
                email_sent = False

        self.log_action('STAFF_INVITED', user, {'role': role, 'email': email, 'email_sent': email_sent})

        return Response({
            'message': 'Staff invitation created successfully.',
            'user': UserSerializer(user).data,
            'temp_password': temp_password,
            'activation_url': activation_url,
            'email_sent': email_sent,
        }, status=201)

    @extend_schema(
        responses={200: inline_serializer(
            name='StaffDashboardResponse',
            fields={
                'total_staff': drf_serializers.IntegerField(),
                'active_staff': drf_serializers.IntegerField(),
                'by_role': drf_serializers.ListField(child=drf_serializers.DictField())
            }
        )},
        tags=['Authentication']
    )
    @action(detail=False, methods=['get'])
    def dashboard(self, request):
        from django.db.models import Count
        qs = self.get_queryset()
        
        total = qs.count()
        active = qs.filter(is_active=True).count()
        by_role = qs.values('role').annotate(count=Count('id'))
        
        return Response({
            'total_staff': total,
            'active_staff': active,
            'by_role': list(by_role)
        })

    @extend_schema(
        responses={200: inline_serializer(name='DeactivateStaffResponse', fields={'message': drf_serializers.CharField()})},
        tags=['Authentication']
    )
    @action(detail=True, methods=['post'], permission_classes=[IsDirector])
    def deactivate(self, request, pk=None):
        """US-006: Deactivate account; invalidate all tokens immediately."""
        user = self.get_object()
        if user == request.user:
            raise ValidationError('You cannot deactivate your own account.')

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

    @extend_schema(
        responses={200: inline_serializer(name='ReactivateStaffResponse', fields={'message': drf_serializers.CharField()})},
        tags=['Authentication']
    )
    @action(detail=True, methods=['post'], permission_classes=[IsDirector])
    def reactivate(self, request, pk=None):
        user = self.get_object()
        user.is_active = True
        user.deactivated_at = None
        user.deactivated_by = None
        user.save(update_fields=['is_active', 'deactivated_at', 'deactivated_by'])
        self.log_action('STAFF_REACTIVATED', user, {'email': user.email})
        return Response({'message': f'{user.get_full_name()} has been reactivated.'})

    @extend_schema(
        request=inline_serializer(
            name='ChangeRoleRequest',
            fields={'role': drf_serializers.CharField()}
        ),
        responses={200: inline_serializer(name='ChangeRoleResponse', fields={'message': drf_serializers.CharField()})},
        tags=['Authentication']
    )
    @action(detail=True, methods=['patch'], permission_classes=[IsDirector], url_path='change-role')
    def change_role(self, request, pk=None):
        """US-003: All role changes must be audit-logged."""
        user = self.get_object()
        new_role = request.data.get('role')
        allowed_roles = [r[0] for r in User.ROLE_CHOICES if r[0] != 'system_admin']
        if new_role not in allowed_roles:
            raise ValidationError({'role': f'Invalid role. Choose from: {allowed_roles}'})
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
