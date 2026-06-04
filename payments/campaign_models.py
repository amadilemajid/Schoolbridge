"""
US-C04: Defaulter Campaign Models.
Targeted messaging campaigns for fee defaulters with segmentation.
"""
import uuid
from django.db import models
from django.utils import timezone
from schools.managers import TenantManager


class DefaulterCampaign(models.Model):
    """
    US-C04: Targeted campaign for fee defaulters.
    Segments students by balance thresholds and sends personalized reminders.
    """
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('scheduled', 'Scheduled'),
        ('running', 'Running'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
    ]
    
    SEGMENT_CHOICES = [
        ('all', 'All Defaulters'),
        ('high_balance', 'High Balance (>500k)'),
        ('medium_balance', 'Medium Balance (200k-500k)'),
        ('low_balance', 'Low Balance (<200k)'),
        ('zero_payment', 'Zero Payment Made'),
        ('partial_payment', 'Partial Payment Made'),
        ('specific_class', 'Specific Class'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    school = models.ForeignKey('schools.School', on_delete=models.CASCADE)
    academic_term = models.ForeignKey('schools.AcademicTerm', on_delete=models.CASCADE)
    
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    
    # Segmentation
    segment_type = models.CharField(max_length=30, choices=SEGMENT_CHOICES, default='all')
    min_balance = models.DecimalField(max_digits=12, decimal_places=0, null=True, blank=True,
                                     help_text="Minimum balance filter (UGX)")
    max_balance = models.DecimalField(max_digits=12, decimal_places=0, null=True, blank=True,
                                     help_text="Maximum balance filter (UGX)")
    target_classes = models.ManyToManyField('students.ClassGroup', blank=True,
                                           help_text="Target specific classes")
    
    # Message content
    message_template_en = models.TextField(help_text="English message template")
    message_template_lg = models.TextField(blank=True, help_text="Luganda message template")
    
    # Scheduling
    scheduled_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    
    # Execution tracking
    target_count = models.PositiveIntegerField(default=0, 
                                               help_text="Number of students targeted")
    sent_count = models.PositiveIntegerField(default=0)
    delivered_count = models.PositiveIntegerField(default=0)
    failed_count = models.PositiveIntegerField(default=0)
    
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    
    # Analytics
    total_balance_targeted = models.DecimalField(max_digits=15, decimal_places=0, default=0,
                                                 help_text="Sum of all targeted balances")
    payments_received = models.DecimalField(max_digits=15, decimal_places=0, default=0,
                                           help_text="Payments received during campaign")
    
    created_by = models.ForeignKey('authentication.User', on_delete=models.SET_NULL,
                                  null=True, related_name='campaigns_created')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = TenantManager()
    all_objects = models.Manager()

    class Meta:
        db_table = 'defaulter_campaigns'
        indexes = [
            models.Index(fields=['school', 'status']),
            models.Index(fields=['scheduled_at', 'status']),
        ]
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.name} ({self.get_segment_type_display()})"

    @property
    def success_rate(self):
        """Calculate delivery success rate."""
        if self.sent_count == 0:
            return 0
        return round((self.delivered_count / self.sent_count) * 100, 1)

    @property
    def collection_rate(self):
        """Calculate payment collection during campaign."""
        if self.total_balance_targeted == 0:
            return 0
        return round((self.payments_received / self.total_balance_targeted) * 100, 1)


class DefaulterCampaignTarget(models.Model):
    """Individual targets within a campaign."""
    campaign = models.ForeignKey(DefaulterCampaign, on_delete=models.CASCADE,
                                related_name='targets')
    fee_record = models.ForeignKey('payments.FeeRecord', on_delete=models.CASCADE)
    student = models.ForeignKey('students.Student', on_delete=models.CASCADE)
    guardian_phone = models.CharField(max_length=20)
    
    balance_at_send = models.DecimalField(max_digits=12, decimal_places=0)
    message_sent = models.TextField()
    language = models.CharField(max_length=10)
    
    # Delivery tracking
    whatsapp_message_id = models.CharField(max_length=100, blank=True)
    status = models.CharField(max_length=20, default='pending',
                             choices=[
                                 ('pending', 'Pending'),
                                 ('sent', 'Sent'),
                                 ('delivered', 'Delivered'),
                                 ('read', 'Read'),
                                 ('failed', 'Failed'),
                             ])
    
    sent_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    
    # Response tracking
    payment_made = models.BooleanField(default=False)
    payment_amount = models.DecimalField(max_digits=12, decimal_places=0, null=True, blank=True)
    payment_date = models.DateTimeField(null=True, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'defaulter_campaign_targets'
        unique_together = [('campaign', 'fee_record')]
        indexes = [
            models.Index(fields=['campaign', 'status']),
            models.Index(fields=['guardian_phone']),
        ]
