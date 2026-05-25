"""
Notifications models.
US-074: Real-time in-app notifications via Django Channels (WebSocket).
US-075: Reconciliation alerts at 24hr / 48hr.
US-076: Attendance reminder to teacher at 10am.
US-077: Daily 7:30am staff digest.
"""
import uuid
from django.db import models
from schools.managers import TenantManager


class Notification(models.Model):
    """
    In-app notification for staff.
    Delivered via WebSocket (Django Channels) with 30s polling fallback.
    """
    NOTIFICATION_TYPES = [
        ('PAYMENT_RECEIVED', 'Payment Received'),
        ('PAYMENT_PLAN_REQUEST', 'Payment Plan Request'),
        ('UNMATCHED_PAYMENT_24HR', 'Unmatched Payment 24hr'),
        ('UNMATCHED_PAYMENT_48HR', 'Unmatched Payment 48hr'),
        ('LOW_ATTENDANCE_ALERT', 'Low Attendance Alert'),
        ('ATTENDANCE_REMINDER', 'Attendance Reminder'),
        ('CELERY_TASK_FAILURE', 'System Task Failure'),
        ('FEE_APPROVAL_REQUIRED', 'Fee Approval Required'),
        ('REVERSAL_APPROVAL_REQUIRED', 'Reversal Approval Required'),
        ('REPORT_CARD_GENERATED', 'Report Card Generated'),
        ('SYSTEM_ALERT', 'System Alert'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    school = models.ForeignKey(
        'schools.School', on_delete=models.CASCADE,
        null=True, blank=True, related_name='notifications'
    )
    recipient = models.ForeignKey(
        'authentication.User', on_delete=models.CASCADE,
        related_name='notifications'
    )
    notification_type = models.CharField(max_length=50, choices=NOTIFICATION_TYPES)
    title = models.CharField(max_length=200)
    message = models.TextField()
    data = models.JSONField(null=True, blank=True,
        help_text="Extra structured data, e.g. payment_id, student_id")

    is_read = models.BooleanField(default=False)
    read_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    objects = TenantManager()
    all_objects = models.Manager()

    class Meta:
        db_table = 'notifications'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['recipient', 'is_read', 'created_at']),
            models.Index(fields=['school', 'notification_type']),
        ]

    def __str__(self):
        return f"{self.notification_type} → {self.recipient.email}"

    def mark_read(self):
        from django.utils import timezone
        self.is_read = True
        self.read_at = timezone.now()
        self.save(update_fields=['is_read', 'read_at'])
