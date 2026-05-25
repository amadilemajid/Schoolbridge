"""
Authentication models.
US-002: JWT with lockout after 5 failed attempts.
US-003: Role-based access — Director, Bursar, Teacher, SystemAdmin.
US-004: Password history (must differ from last 3).
US-006: Immediate deactivation with session invalidation.
US-007: Full audit log of all auth events.
"""
import uuid
from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin, BaseUserManager
from django.db import models
from django.utils import timezone


class UserManager(BaseUserManager):
    def create_user(self, email, password=None, **extra):
        if not email:
            raise ValueError('Email is required')
        email = self.normalize_email(email)
        user = self.model(email=email, **extra)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra):
        extra.setdefault('role', 'system_admin')
        extra.setdefault('is_staff', True)
        extra.setdefault('is_superuser', True)
        return self.create_user(email, password, **extra)


class User(AbstractBaseUser, PermissionsMixin):
    """
    Custom user model. Email is the username.
    Every user belongs to exactly one school (except system_admin).
    """
    ROLE_CHOICES = [
        ('system_admin', 'System Admin'),
        ('director', 'School Director'),
        ('bursar', 'Bursar'),
        ('teacher', 'Teacher'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField(unique=True)
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    phone = models.CharField(max_length=20, blank=True)

    school = models.ForeignKey(
        'schools.School',
        on_delete=models.CASCADE,
        null=True, blank=True,
        related_name='staff',
    )
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='teacher')

    # Account status (US-006)
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    deactivated_at = models.DateTimeField(null=True, blank=True)
    deactivated_by = models.ForeignKey(
        'self', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='deactivated_users'
    )

    # Login lockout (US-002)
    failed_login_count = models.PositiveSmallIntegerField(default=0)
    locked_until = models.DateTimeField(null=True, blank=True)

    date_joined = models.DateTimeField(default=timezone.now)
    last_login = models.DateTimeField(null=True, blank=True)

    objects = UserManager()

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['first_name', 'last_name']

    class Meta:
        db_table = 'auth_users'
        indexes = [
            models.Index(fields=['email']),
            models.Index(fields=['school', 'role']),
            models.Index(fields=['school', 'is_active']),
        ]

    def __str__(self):
        return f"{self.get_full_name()} <{self.email}>"

    def get_full_name(self):
        return f"{self.first_name} {self.last_name}".strip()

    @property
    def is_locked(self):
        """US-002: Account locked after 5 failed attempts for 15 minutes."""
        if self.locked_until and timezone.now() < self.locked_until:
            return True
        return False

    def record_failed_login(self):
        from django.conf import settings
        from django.utils import timezone
        import datetime
        self.failed_login_count += 1
        if self.failed_login_count >= settings.LOGIN_MAX_ATTEMPTS:
            self.locked_until = timezone.now() + datetime.timedelta(
                minutes=settings.LOGIN_LOCKOUT_MINUTES
            )
        self.save(update_fields=['failed_login_count', 'locked_until'])

    def record_successful_login(self):
        self.failed_login_count = 0
        self.locked_until = None
        self.last_login = timezone.now()
        self.save(update_fields=['failed_login_count', 'locked_until', 'last_login'])


class PasswordHistory(models.Model):
    """
    US-004: Track last 3 passwords. New password must differ from all of them.
    """
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='password_history')
    hashed_password = models.CharField(max_length=128)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'password_history'
        ordering = ['-created_at']

    @classmethod
    def record(cls, user, raw_password):
        """Store a new password hash and keep only the last 3."""
        from django.contrib.auth.hashers import make_password
        cls.objects.create(user=user, hashed_password=make_password(raw_password))
        # Keep only last 3
        old_ids = cls.objects.filter(user=user).order_by('-created_at').values_list('id', flat=True)[3:]
        cls.objects.filter(id__in=list(old_ids)).delete()

    @classmethod
    def is_reused(cls, user, raw_password):
        """Return True if raw_password matches any of the last 3 stored hashes."""
        from django.contrib.auth.hashers import check_password
        for record in cls.objects.filter(user=user).order_by('-created_at')[:3]:
            if check_password(raw_password, record.hashed_password):
                return True
        return False


class PasswordResetToken(models.Model):
    """
    US-004: Secure one-time email link. Expires in 60 minutes.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='reset_tokens')
    token = models.CharField(max_length=64, unique=True)
    expires_at = models.DateTimeField()
    used_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'password_reset_tokens'
        indexes = [models.Index(fields=['token'])]

    @property
    def is_valid(self):
        return self.used_at is None and timezone.now() < self.expires_at

    def mark_used(self):
        self.used_at = timezone.now()
        self.save(update_fields=['used_at'])
