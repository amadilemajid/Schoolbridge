"""
US-C03: One-time Payment Link Generation.
Generates secure, expirable payment links for MoMo payments.
"""
import uuid
import secrets
from django.db import models
from django.utils import timezone
from datetime import timedelta
from schools.managers import TenantManager


class PaymentLink(models.Model):
    """
    US-C03: One-time payment links for fee collection.
    Expires after 72 hours or first use.
    """
    STATUS_CHOICES = [
        ('active', 'Active'),
        ('used', 'Used'),
        ('expired', 'Expired'),
        ('cancelled', 'Cancelled'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    school = models.ForeignKey('schools.School', on_delete=models.CASCADE)
    fee_record = models.ForeignKey('payments.FeeRecord', on_delete=models.CASCADE,
                                   related_name='payment_links')
    student = models.ForeignKey('students.Student', on_delete=models.CASCADE)
    
    # Secure token for URL
    token = models.CharField(max_length=64, unique=True, db_index=True)
    
    # Payment details
    amount = models.DecimalField(max_digits=12, decimal_places=0,
                                help_text="Amount this link is for")
    description = models.CharField(max_length=200, default='School Fees Payment')
    
    # Status tracking
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')
    expires_at = models.DateTimeField()
    
    # Usage tracking
    accessed_count = models.PositiveIntegerField(default=0)
    payment = models.ForeignKey('payments.Payment', on_delete=models.SET_NULL,
                               null=True, blank=True,
                               help_text="Payment made via this link")
    used_at = models.DateTimeField(null=True, blank=True)
    
    # Guardian info
    recipient_phone = models.CharField(max_length=20)
    recipient_name = models.CharField(max_length=100)
    
    # Creation tracking
    created_by = models.ForeignKey('authentication.User', on_delete=models.SET_NULL,
                                  null=True, related_name='payment_links_created')
    created_at = models.DateTimeField(auto_now_add=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    cancelled_by = models.ForeignKey('authentication.User', on_delete=models.SET_NULL,
                                    null=True, blank=True, related_name='payment_links_cancelled')

    objects = TenantManager()
    all_objects = models.Manager()

    class Meta:
        db_table = 'payment_links'
        indexes = [
            models.Index(fields=['token']),
            models.Index(fields=['school', 'status']),
            models.Index(fields=['expires_at', 'status']),
        ]
        ordering = ['-created_at']

    def __str__(self):
        return f"PaymentLink {self.token[:8]}... - {self.student} - UGX {self.amount:,}"

    @property
    def is_expired(self):
        """Check if link has expired."""
        return timezone.now() > self.expires_at

    @property
    def is_usable(self):
        """Check if link can still be used."""
        return (
            self.status == 'active' and
            not self.is_expired and
            not self.payment_id
        )

    @property
    def full_url(self):
        """Generate full payment URL."""
        from django.conf import settings
        base_url = getattr(settings, 'PAYMENT_LINK_BASE_URL', 'https://pay.schoolbridge.ug')
        return f"{base_url}/pay/{self.token}"

    def mark_used(self, payment):
        """Mark link as used after successful payment."""
        self.status = 'used'
        self.payment = payment
        self.used_at = timezone.now()
        self.save(update_fields=['status', 'payment', 'used_at'])

    def mark_expired(self):
        """Mark link as expired."""
        if self.status == 'active':
            self.status = 'expired'
            self.save(update_fields=['status'])

    def increment_access(self):
        """Track link access for analytics."""
        self.accessed_count += 1
        self.save(update_fields=['accessed_count'])
