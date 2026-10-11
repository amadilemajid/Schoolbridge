import uuid
from django.db import models


class SchoolRegistrationRequest(models.Model):
    """
    US-F01: Tracks a self-onboarding registration request.
    """
    STATUS_CHOICES = [
        ('pending', 'Pending Review'),
        ('provisioning', 'Provisioning in Progress'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    school_name = models.CharField(max_length=200, unique=True)
    admin_email = models.EmailField()
    admin_first_name = models.CharField(max_length=100)
    admin_last_name = models.CharField(max_length=100)
    admin_phone = models.CharField(max_length=20)
    district = models.CharField(max_length=100)
    sub_county = models.CharField(max_length=100, blank=True)
    school_type = models.CharField(
        max_length=20,
        choices=[
            ('primary', 'Primary'),
            ('secondary', 'Secondary'),
            ('combined', 'Primary + Secondary'),
            ('vocational', 'Vocational'),
        ],
        default='primary'
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    
    # Stores configuration payload (e.g. classes, term dates, fee structures)
    payload = models.JSONField(default=dict, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'school_registration_requests'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.school_name} ({self.status})"


class SchoolProvisioningLog(models.Model):
    """
    US-F01: Logs steps of the provisioning pipeline to debug failures.
    """
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('success', 'Success'),
        ('failed', 'Failed'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    registration_request = models.ForeignKey(
        SchoolRegistrationRequest,
        on_delete=models.CASCADE,
        related_name='logs'
    )
    step_name = models.CharField(max_length=100)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    details = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'school_provisioning_logs'
        ordering = ['created_at']

    def __str__(self):
        return f"{self.registration_request.school_name} - {self.step_name} ({self.status})"
