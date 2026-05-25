"""
Authentication serializers — login, registration, password reset.
"""
import secrets
import datetime
from django.conf import settings
from django.contrib.auth import authenticate
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.utils import timezone
from rest_framework import serializers
from rest_framework_simplejwt.tokens import RefreshToken
from .models import User, PasswordHistory, PasswordResetToken


class UserRegistrationSerializer(serializers.ModelSerializer):
    """Create a new staff member in the school. Director only."""
    password = serializers.CharField(write_only=True, min_length=8)
    confirm_password = serializers.CharField(write_only=True)

    class Meta:
        model = User
        fields = [
            'id', 'email', 'first_name', 'last_name', 'phone',
            'role', 'password', 'confirm_password',
        ]
        read_only_fields = ['id']

    def validate_role(self, value):
        request = self.context.get('request')
        # Only system_admin can create other system_admins
        if value == 'system_admin' and (not request or request.user.role != 'system_admin'):
            raise serializers.ValidationError("You cannot assign the system_admin role.")
        return value

    def validate(self, data):
        if data['password'] != data.pop('confirm_password'):
            raise serializers.ValidationError({'confirm_password': 'Passwords do not match.'})
        try:
            validate_password(data['password'])
        except DjangoValidationError as e:
            raise serializers.ValidationError({'password': list(e.messages)})
        return data

    def create(self, validated_data):
        password = validated_data.pop('password')
        school = self.context['request'].user.school
        user = User.objects.create_user(
            password=password, school=school, **validated_data
        )
        PasswordHistory.record(user, password)
        return user


class UserSerializer(serializers.ModelSerializer):
    school_name = serializers.CharField(source='school.name', read_only=True)

    class Meta:
        model = User
        fields = [
            'id', 'email', 'first_name', 'last_name', 'phone',
            'role', 'school', 'school_name', 'is_active',
            'date_joined', 'last_login',
        ]
        read_only_fields = ['id', 'date_joined', 'last_login', 'school']


class LoginSerializer(serializers.Serializer):
    """
    US-002: Login with lockout after 5 failed attempts (15 min).
    Returns JWT access + refresh tokens on success.
    """
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)

    def validate(self, data):
        email = data['email'].lower().strip()
        password = data['password']

        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            raise serializers.ValidationError('Invalid email or password.')

        # US-002: Check lockout before attempting authentication
        if user.is_locked:
            remaining = (user.locked_until - timezone.now()).seconds // 60
            raise serializers.ValidationError(
                f'Account locked due to too many failed attempts. '
                f'Try again in {remaining} minutes.'
            )

        if not user.check_password(password):
            user.record_failed_login()
            attempts_left = settings.LOGIN_MAX_ATTEMPTS - user.failed_login_count
            if attempts_left <= 0:
                raise serializers.ValidationError(
                    f'Account locked for {settings.LOGIN_LOCKOUT_MINUTES} minutes.'
                )
            raise serializers.ValidationError(
                f'Invalid email or password. {max(0, attempts_left)} attempt(s) remaining.'
            )

        if not user.is_active:
            raise serializers.ValidationError('Account has been deactivated. Contact your school admin.')

        user.record_successful_login()
        data['user'] = user
        return data

    def create_tokens(self, user):
        refresh = RefreshToken.for_user(user)
        refresh['role'] = user.role
        refresh['school_id'] = str(user.school_id) if user.school_id else None
        return {
            'access': str(refresh.access_token),
            'refresh': str(refresh),
            'user': UserSerializer(user).data,
        }


class PasswordResetRequestSerializer(serializers.Serializer):
    """US-004: Request password reset email."""
    email = serializers.EmailField()

    def validate_email(self, value):
        return value.lower().strip()


class PasswordResetConfirmSerializer(serializers.Serializer):
    """US-004: Confirm reset with token + new password."""
    token = serializers.CharField()
    password = serializers.CharField(write_only=True, min_length=8)
    confirm_password = serializers.CharField(write_only=True)

    def validate(self, data):
        if data['password'] != data['confirm_password']:
            raise serializers.ValidationError({'confirm_password': 'Passwords do not match.'})

        try:
            reset_token = PasswordResetToken.objects.select_related('user').get(token=data['token'])
        except PasswordResetToken.DoesNotExist:
            raise serializers.ValidationError({'token': 'Invalid or expired reset token.'})

        if not reset_token.is_valid:
            raise serializers.ValidationError({'token': 'This reset link has expired or already been used.'})

        # Validate password rules including history (US-004)
        try:
            validate_password(data['password'], user=reset_token.user)
        except DjangoValidationError as e:
            raise serializers.ValidationError({'password': list(e.messages)})

        data['reset_token'] = reset_token
        return data


class ChangePasswordSerializer(serializers.Serializer):
    old_password = serializers.CharField(write_only=True)
    new_password = serializers.CharField(write_only=True, min_length=8)
    confirm_password = serializers.CharField(write_only=True)

    def validate(self, data):
        user = self.context['request'].user
        if not user.check_password(data['old_password']):
            raise serializers.ValidationError({'old_password': 'Incorrect current password.'})
        if data['new_password'] != data['confirm_password']:
            raise serializers.ValidationError({'confirm_password': 'New passwords do not match.'})
        try:
            validate_password(data['new_password'], user=user)
        except DjangoValidationError as e:
            raise serializers.ValidationError({'new_password': list(e.messages)})
        return data
