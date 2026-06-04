"""
US-C01: Reminder Escalation Engine Models.
5-level escalation system with increasing urgency.
"""
import uuid
from django.db import models
from schools.managers import TenantManager


class ReminderEscalation(models.Model):
    """
    US-C01: Escalation schedule for a student's fee record.
    One record per fee_record, with 5 escalation levels.
    """
    ESCALATION_LEVELS = [
        (1, 'Level 1 - Gentle'),
        (2, 'Level 2 - Friendly'),
        (3, 'Level 3 - Firm'),
        (4, 'Level 4 - Urgent'),
        (5, 'Level 5 - Final'),
    ]
    
    STATUS_CHOICES = [
        ('scheduled', 'Scheduled'),
        ('sent', 'Sent'),
        ('suppressed', 'Suppressed'),
        ('failed', 'Failed'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    school = models.ForeignKey('schools.School', on_delete=models.CASCADE)
    fee_record = models.ForeignKey('payments.FeeRecord', on_delete=models.CASCADE, 
                                   related_name='escalations')
    academic_term = models.ForeignKey('schools.AcademicTerm', on_delete=models.CASCADE)
    
    level = models.PositiveSmallIntegerField(choices=ESCALATION_LEVELS)
    scheduled_date = models.DateField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='scheduled')
    
    # Notification flags
    director_notified = models.BooleanField(default=False, 
                                           help_text="Level 3+ notifies Director")
    bursar_notified = models.BooleanField(default=False, 
                                         help_text="Level 4+ notifies Bursar")
    
    sent_at = models.DateTimeField(null=True, blank=True)
    suppressed_at = models.DateTimeField(null=True, blank=True)
    suppression_reason = models.CharField(max_length=100, blank=True)
    
    celery_task_id = models.CharField(max_length=100, blank=True)
    
    objects = TenantManager()
    all_objects = models.Manager()
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'reminder_escalations'
        unique_together = [('fee_record', 'level')]
        indexes = [
            models.Index(fields=['school', 'scheduled_date', 'status']),
            models.Index(fields=['status', 'scheduled_date']),
        ]
        ordering = ['scheduled_date', 'level']

    def __str__(self):
        return f"Escalation L{self.level} - {self.fee_record.student} - {self.scheduled_date}"


class ReminderEscalationLog(models.Model):
    """Audit trail for every escalation sent."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    escalation = models.ForeignKey(ReminderEscalation, on_delete=models.CASCADE, 
                                   related_name='logs')
    
    message_sent = models.TextField()
    balance_at_send = models.DecimalField(max_digits=12, decimal_places=0)
    recipient_phone = models.CharField(max_length=20)
    language = models.CharField(max_length=10)
    
    whatsapp_message_id = models.CharField(max_length=100, blank=True)
    delivery_status = models.CharField(max_length=20, default='sent')
    
    director_notified = models.BooleanField(default=False)
    bursar_notified = models.BooleanField(default=False)
    
    sent_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'reminder_escalation_logs'
        ordering = ['-sent_at']
