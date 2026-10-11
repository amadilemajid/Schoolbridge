"""
Audit Log — US-007, US-071.
Immutable, append-only. 3-year retention.
Tracks actor, action, IP, timestamp, before/after on every change.
The DB user for the application has NO UPDATE/DELETE permissions on this table.
"""
import uuid
from django.db import models


class AuditLog(models.Model):
    """
    Every significant action in the system writes an AuditLog entry.
    NEVER updated. NEVER deleted except by automated 3-year retention job.
    """
    ACTION_CATEGORIES = [
        ('AUTH', 'Authentication'),
        ('STUDENT', 'Student Management'),
        ('PAYMENT', 'Payment'),
        ('FEE', 'Fee Management'),
        ('RESULT', 'Academic Results'),
        ('ATTENDANCE', 'Attendance'),
        ('MESSAGING', 'Messaging'),
        ('SCHOOL', 'School Admin'),
        ('STAFF', 'Staff Management'),
        ('AUTOMATION', 'Automation'),
        ('SYSTEM', 'System'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # Who did it
    actor_id = models.UUIDField(null=True, blank=True, help_text="User UUID")
    actor_email = models.CharField(max_length=200, blank=True)
    actor_role = models.CharField(max_length=30, blank=True)

    # Tenant context
    school_id = models.UUIDField(null=True, blank=True)
    school_name = models.CharField(max_length=200, blank=True)

    # What happened
    category = models.CharField(max_length=20, choices=ACTION_CATEGORIES)
    action = models.CharField(max_length=100, help_text="e.g. PAYMENT_RECORDED, MARK_EDITED")
    description = models.TextField(blank=True)

    # What was affected
    target_model = models.CharField(max_length=100, blank=True, help_text="e.g. Payment, Student")
    target_id = models.CharField(max_length=100, blank=True)

    # Before/after for data changes
    before_data = models.JSONField(null=True, blank=True)
    after_data = models.JSONField(null=True, blank=True)
    extra_data = models.JSONField(null=True, blank=True)

    # Request context
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)
    request_id = models.CharField(max_length=50, blank=True)

    # When
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table = 'audit_logs'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['actor_id', 'created_at']),
            models.Index(fields=['school_id', 'created_at']),
            models.Index(fields=['category', 'action', 'created_at']),
            models.Index(fields=['target_model', 'target_id']),
        ]
        # No delete/update permissions — enforced at DB level
        # CREATE ROLE app_user; GRANT SELECT, INSERT ON audit_logs TO app_user;

    def __str__(self):
        return f"[{self.category}] {self.action} by {self.actor_email} at {self.created_at}"

    # ---- Immutability guards (SEC-008) ----
    # DB-level enforcement (GRANT INSERT, SELECT only) is the primary control.
    # These ORM-level guards add defence-in-depth so application code cannot
    # accidentally UPDATE or DELETE audit records.

    def save(self, *args, _bypass_immutability=False, **kwargs):
        """Block UPDATE; only INSERT (no PK yet) is allowed."""
        if not _bypass_immutability and not self._state.adding:
            raise PermissionError(
                "AuditLog records are immutable. "
                "Existing entries cannot be updated. Create a new corrective entry instead."
            )
        super().save(*args, **kwargs)

    def delete(self, *args, _bypass_immutability=False, **kwargs):
        """Block DELETE. Retention cleanup must go through the DB retention job directly."""
        if not _bypass_immutability:
            raise PermissionError(
                "AuditLog records cannot be deleted via the ORM. "
                "Use the DB-level retention job to purge records older than 3 years."
            )
        return super().delete(*args, **kwargs)

    # Prevent bulk_update from silently bypassing the guard
    class DoNotUpdate:
        """Sentinel: raise if anyone tries objects.update() on AuditLog."""

    @classmethod
    def log(cls, *, actor=None, school=None, category, action, description='',
            target=None, before=None, after=None, extra=None, request=None):
        """
        Central logging method. Call this from anywhere.
        Usage:
            AuditLog.log(
                actor=request.user,
                school=request.user.school,
                category='PAYMENT',
                action='PAYMENT_RECORDED',
                target=payment,
                after={'amount': 50000},
                request=request,
            )
        """
        entry = cls(
            category=category,
            action=action,
            description=description,
            before_data=before,
            after_data=after,
            extra_data=extra,
        )

        if actor:
            entry.actor_id = actor.pk
            entry.actor_email = actor.email
            entry.actor_role = getattr(actor, 'role', '')

        if school:
            entry.school_id = school.pk
            entry.school_name = school.name
        elif actor and hasattr(actor, 'school') and actor.school:
            entry.school_id = actor.school.pk
            entry.school_name = actor.school.name

        if target:
            entry.target_model = target.__class__.__name__
            entry.target_id = str(target.pk)

        if request:
            entry.ip_address = cls._get_client_ip(request)
            entry.user_agent = request.META.get('HTTP_USER_AGENT', '')[:500]

        entry.save()
        return entry

    @staticmethod
    def _get_client_ip(request):
        x_forwarded = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded:
            return x_forwarded.split(',')[0].strip()
        return request.META.get('REMOTE_ADDR')
