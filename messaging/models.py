"""
Messaging app models.
US-032-040: WhatsApp automation, inbound commands, broadcasts.
US-061: SMS fallback via Africa's Talking.
"""
import uuid
from django.db import models
from schools.managers import TenantManager


class MessageTemplate(models.Model):
    """
    US-040: Configurable message templates.
    All templates must be Meta-approved before use.
    """
    TEMPLATE_TYPES = [
        ('fee_reminder', 'Fee Reminder'),
        ('payment_receipt', 'Payment Receipt'),
        ('payment_reversal', 'Payment Reversal'),
        ('report_card_ready', 'Report Card Ready'),
        ('absence_alert', 'Absence Alert'),
        ('broadcast', 'Broadcast'),
        ('balance_response', 'Balance Response'),
        ('receipt_response', 'Receipt Response'),
        ('help_response', 'Help Response'),
        ('plan_notification', 'Plan Notification'),
        ('number_changed', 'Number Changed'),
        ('daily_digest', 'Daily Digest'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    school = models.ForeignKey('schools.School', on_delete=models.CASCADE,
                               related_name='message_templates', null=True, blank=True,
                               help_text="Null = system-wide default template")
    template_type = models.CharField(max_length=30, choices=TEMPLATE_TYPES)
    name = models.CharField(max_length=100, help_text="Meta template name (approved)")
    language = models.CharField(max_length=10, default='en',
                                choices=[('en', 'English'), ('lg', 'Luganda')])
    body = models.TextField(help_text="Template body with {{variable}} placeholders")
    meta_template_name = models.CharField(max_length=512, blank=True,
        help_text="Exact name registered in Meta Business Manager")
    is_meta_approved = models.BooleanField(default=False,
        help_text="MUST be True before template is used in automated sends")
    meta_submission_status = models.CharField(max_length=30, blank=True,
        help_text="Meta review status: PENDING, APPROVED, REJECTED, PAUSED, DISABLED")
    meta_rejection_reason = models.TextField(blank=True,
        help_text="Reason provided by Meta if template is rejected")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    objects = TenantManager()
    all_objects = models.Manager()

    class Meta:
        db_table = 'message_templates'
        unique_together = [('school', 'template_type', 'language')]
        indexes = [models.Index(fields=['template_type', 'language', 'is_active'])]

    def __str__(self):
        return f"{self.template_type} ({self.language})"


class MessageLog(models.Model):
    """
    US-039: Log every outbound message — sent, delivered, read, failed.
    90-day retention. Delivery status updated via WhatsApp webhook callbacks.
    """
    CHANNEL_CHOICES = [('whatsapp', 'WhatsApp'), ('sms', 'SMS'), ('voice', 'Voice Call')]
    STATUS_CHOICES = [
        ('queued', 'Queued'),
        ('sent', 'Sent'),
        ('delivered', 'Delivered'),
        ('read', 'Read'),
        ('failed', 'Failed'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    school = models.ForeignKey('schools.School', on_delete=models.CASCADE, related_name='message_logs')
    student = models.ForeignKey('students.Student', on_delete=models.SET_NULL,
                                null=True, blank=True, related_name='message_logs')
    recipient_phone = models.CharField(max_length=20)
    channel = models.CharField(max_length=10, choices=CHANNEL_CHOICES)
    template_type = models.CharField(max_length=30, blank=True)
    message_body = models.TextField(blank=True)

    # WhatsApp-specific
    whatsapp_message_id = models.CharField(max_length=100, blank=True, db_index=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='queued')
    status_updated_at = models.DateTimeField(null=True, blank=True)

    # Fallback tracking (US-061)
    is_fallback = models.BooleanField(default=False,
        help_text="True if this SMS was sent as WhatsApp fallback")
    fallback_triggered_at = models.DateTimeField(null=True, blank=True)

    error_message = models.TextField(blank=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True,
        help_text="Timestamp when delivery was confirmed via webhook or DEBUG simulation")
    created_at = models.DateTimeField(auto_now_add=True)

    objects = TenantManager()
    all_objects = models.Manager()

    class Meta:
        db_table = 'message_logs'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['school', 'created_at']),
            models.Index(fields=['recipient_phone', 'created_at']),
            models.Index(fields=['whatsapp_message_id']),
            models.Index(fields=['status']),
            models.Index(fields=['template_type']),
            models.Index(fields=['school', 'student']),
        ]


class BroadcastMessage(models.Model):
    """
    US-035: Bulk broadcast messaging.
    Targets: by class, fee status, or custom list.
    Scheduled or immediate. Rate-limited in Celery queue.
    """
    TARGET_CHOICES = [
        ('all_parents', 'All Parents'),
        ('class', 'Specific Class'),
        ('fee_defaulters', 'Fee Defaulters'),
        ('fully_paid', 'Fully Paid Students'),
        ('custom', 'Custom List'),
    ]
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('scheduled', 'Scheduled'),
        ('sending', 'Sending'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
    ]
    CHANNEL_CHOICES = [
        ('whatsapp', 'WhatsApp'),
        ('sms', 'SMS'),
        ('voice', 'Voice Call'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    school = models.ForeignKey('schools.School', on_delete=models.CASCADE)
    title = models.CharField(max_length=200)
    message_body = models.TextField()
    channel = models.CharField(max_length=10, choices=CHANNEL_CHOICES, default='whatsapp',
        help_text="Delivery channel: whatsapp or sms")
    target_type = models.CharField(max_length=20, choices=TARGET_CHOICES)
    target_class = models.ForeignKey('students.ClassGroup', on_delete=models.SET_NULL,
                                     null=True, blank=True)
    target_term = models.ForeignKey('schools.AcademicTerm', on_delete=models.SET_NULL,
                                    null=True, blank=True)
    scheduled_at = models.DateTimeField(null=True, blank=True,
        help_text="Null = send immediately on submission")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')

    total_recipients = models.PositiveIntegerField(default=0)
    sent_count = models.PositiveIntegerField(default=0)
    delivered_count = models.PositiveIntegerField(default=0)
    failed_count = models.PositiveIntegerField(default=0)

    created_by = models.ForeignKey('authentication.User', on_delete=models.SET_NULL,
                                   null=True, related_name='broadcasts_created')
    celery_task_id = models.CharField(max_length=100, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    objects = TenantManager()
    all_objects = models.Manager()

    class Meta:
        db_table = 'broadcast_messages'
        ordering = ['-created_at']


class InboundMessage(models.Model):
    """
    US-033/034/036/052: Inbound WhatsApp commands from parents.
    BALANCE, RECEIPT, HELP, PLAN, ABSENT.
    """
    COMMAND_CHOICES = [
        ('BALANCE', 'Balance Inquiry'),
        ('RECEIPT', 'Receipt Request'),
        ('HELP', 'Help Request'),
        ('PLAN', 'Payment Plan Request'),
        ('ABSENT', 'Absence Notification'),
        ('UNKNOWN', 'Unknown Command'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    school = models.ForeignKey('schools.School', on_delete=models.SET_NULL,
                               null=True, blank=True)
    from_phone = models.CharField(max_length=20)
    raw_message = models.TextField()
    command = models.CharField(max_length=20, choices=COMMAND_CHOICES, default='UNKNOWN')
    command_args = models.JSONField(null=True, blank=True,
        help_text="Parsed arguments, e.g. {date: '2024-01-15'} for RECEIPT")
    whatsapp_message_id = models.CharField(max_length=100, unique=True)
    processed = models.BooleanField(default=False)
    response_sent = models.BooleanField(default=False)
    received_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'inbound_messages'
        indexes = [
            models.Index(fields=['from_phone']),
            models.Index(fields=['command', 'processed']),
        ]


class BroadcastMedia(models.Model):
    """
    US-B01/US-B02: Tracks uploaded media files for WhatsApp voice/document broadcasts.
    Stores the Meta WABA media_id for efficient re-use (upload once, send many).
    media_id expires after 30 days per Meta policy.
    """
    MEDIA_TYPE_CHOICES = [
        ('voice', 'Voice Note'),
        ('document', 'Document'),
        ('image', 'Image'),
    ]
    STATUS_CHOICES = [
        ('pending', 'Pending Upload'),
        ('uploaded', 'Uploaded to Meta'),
        ('expired', 'Expired'),
        ('failed', 'Upload Failed'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    school = models.ForeignKey(
        'schools.School', on_delete=models.CASCADE,
        related_name='broadcast_media'
    )
    media_file = models.FileField(
        upload_to='broadcast_media/%Y/%m/',
        help_text='Compressed media file (Opus OGG for voice, PDF for documents)'
    )
    media_type = models.CharField(max_length=10, choices=MEDIA_TYPE_CHOICES)
    original_filename = models.CharField(max_length=255, blank=True)
    file_size_bytes = models.PositiveIntegerField(default=0)
    duration_seconds = models.FloatField(
        null=True, blank=True,
        help_text='Duration in seconds for voice/audio files'
    )
    whatsapp_media_id = models.CharField(
        max_length=255, blank=True,
        help_text='Meta WABA media_id for sending without re-upload'
    )
    meta_upload_status = models.CharField(
        max_length=10, choices=STATUS_CHOICES, default='pending'
    )
    expires_at = models.DateTimeField(
        null=True, blank=True,
        help_text='Meta media_id expiry (30 days from upload)'
    )
    uploaded_by = models.ForeignKey(
        'authentication.User', on_delete=models.SET_NULL,
        null=True, related_name='uploaded_media'
    )
    description = models.TextField(
        blank=True,
        help_text='Optional description for the media (e.g. announcement title)'
    )
    created_at = models.DateTimeField(auto_now_add=True)

    objects = TenantManager()
    all_objects = models.Manager()

    class Meta:
        db_table = 'broadcast_media'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.get_media_type_display()} - {self.original_filename or self.media_file.name}"

    @property
    def is_expired(self):
        """Check if the Meta media_id has expired."""
        if not self.expires_at:
            return True
        from django.utils import timezone
        return timezone.now() >= self.expires_at

    @property
    def is_ready(self):
        """Check if media is uploaded and still valid for sending."""
        return self.meta_upload_status == 'uploaded' and not self.is_expired and self.whatsapp_media_id

