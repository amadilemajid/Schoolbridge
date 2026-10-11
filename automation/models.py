"""
automation/models.py

ScheduledReminder: one record per (fee_record, reminder_days) pair.
Stores the Celery task_id so it can be revoked when term deadlines shift.
"""
import uuid
from django.db import models


class ScheduledReminder(models.Model):
    """
    RISK-P4B: Tracks the Celery task_id for each scheduled fee reminder.

    When reschedule_term_reminders fires, we look up every existing
    ScheduledReminder for the term, revoke the old Celery tasks, and
    replace them with freshly scheduled tasks. This prevents duplicate
    WhatsApp reminders when a fee deadline changes.

    unique_together on (fee_record, reminder_days) ensures at-most-one
    pending Celery task per reminder window per student.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    school = models.ForeignKey(
        'schools.School', on_delete=models.CASCADE, related_name='scheduled_reminders'
    )
    academic_term = models.ForeignKey(
        'schools.AcademicTerm', on_delete=models.CASCADE, related_name='scheduled_reminders'
    )
    fee_record = models.ForeignKey(
        'payments.FeeRecord', on_delete=models.CASCADE, related_name='scheduled_reminders'
    )
    reminder_days = models.PositiveSmallIntegerField(
        help_text="Days before deadline this reminder fires (14, 7, 3, 1)"
    )
    celery_task_id = models.CharField(
        max_length=255,
        help_text="Celery AsyncResult ID used to revoke the task on reschedule"
    )
    eta = models.DateTimeField(help_text="Scheduled fire time (EAT)")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'automation_scheduled_reminders'
        unique_together = [('fee_record', 'reminder_days')]
        indexes = [
            models.Index(fields=['academic_term']),
            models.Index(fields=['school', 'academic_term']),
        ]

    def __str__(self):
        return (
            f"Reminder {self.reminder_days}d — {self.fee_record} "
            f"[task={self.celery_task_id[:8]}]"
        )
