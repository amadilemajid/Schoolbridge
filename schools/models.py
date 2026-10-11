"""
Schools app — Multi-tenant foundation (US-001, US-013).
Every other model has a ForeignKey to School. This is the tenant boundary.
Row-level security is enforced at the middleware + query level.
"""
import uuid
from django.db import models
from django.utils import timezone


class School(models.Model):
    """
    US-001: Each school is an isolated tenant.
    school_id scopes ALL queries via TenantMiddleware.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=200, unique=True)
    slug = models.SlugField(max_length=200, unique=True)

    # Location
    district = models.CharField(max_length=100)
    sub_county = models.CharField(max_length=100, blank=True)
    address = models.TextField(blank=True)

    # Contact
    phone = models.CharField(max_length=20)
    email = models.EmailField()
    whatsapp_number = models.CharField(max_length=20, blank=True,
        help_text="School's WhatsApp number parents message for BALANCE/RECEIPT/HELP")

    # School metadata
    school_type = models.CharField(max_length=20, choices=[
        ('primary', 'Primary'),
        ('secondary', 'Secondary'),
        ('combined', 'Primary + Secondary'),
        ('vocational', 'Vocational'),
    ])
    registration_number = models.CharField(max_length=50, blank=True,
        help_text="Ministry of Education registration number")
    logo = models.ImageField(upload_to='school_logos/', blank=True, null=True)

    # Status
    is_active = models.BooleanField(default=True)
    onboarded_at = models.DateTimeField(auto_now_add=True)
    onboarded_by = models.CharField(max_length=100, blank=True,
        help_text="System admin who created this school")

    # Settings
    default_language = models.CharField(max_length=10, default='en',
        choices=[('en', 'English'), ('lg', 'Luganda')])
    timezone = models.CharField(max_length=50, default='Africa/Kampala')

    class Meta:
        db_table = 'schools'
        ordering = ['name']
        indexes = [
            models.Index(fields=['slug']),
            models.Index(fields=['is_active']),
        ]

    def __str__(self):
        return self.name


class AcademicYear(models.Model):
    """Year container — terms belong to a year."""
    school = models.ForeignKey(School, on_delete=models.CASCADE, related_name='academic_years')
    year = models.PositiveIntegerField()
    is_current = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'academic_years'
        unique_together = [('school', 'year')]
        indexes = [models.Index(fields=['school', 'is_current'])]

    def save(self, *args, **kwargs):
        if self.is_current:
            # Only one current year per school
            AcademicYear.objects.filter(school=self.school, is_current=True).update(is_current=False)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.school.name} — {self.year}"


class AcademicTerm(models.Model):
    """
    US-013: Term calendar drives ALL Celery scheduling.
    Holiday periods suppress all automated messaging.
    Changing term dates must reschedule all pending tasks.
    """
    TERM_NUMBERS = [(1, 'Term 1'), (2, 'Term 2'), (3, 'Term 3')]

    school = models.ForeignKey(School, on_delete=models.CASCADE, related_name='terms')
    academic_year = models.ForeignKey(AcademicYear, on_delete=models.CASCADE, related_name='terms')
    term_number = models.PositiveSmallIntegerField(choices=TERM_NUMBERS)
    name = models.CharField(max_length=50)

    start_date = models.DateField()
    end_date = models.DateField()
    fee_deadline = models.DateField(help_text="Fee payment deadline; drives reminder schedule (US-032)")

    is_current = models.BooleanField(default=False)
    is_active = models.BooleanField(default=False,
        help_text="When activated, FeeRecords are auto-generated for all students")
    activated_at = models.DateTimeField(null=True, blank=True)
    activated_by = models.ForeignKey(
        'authentication.User', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='activated_terms'
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'academic_terms'
        unique_together = [('school', 'academic_year', 'term_number')]
        ordering = ['start_date']
        indexes = [
            models.Index(fields=['school', 'is_current']),
            models.Index(fields=['school', 'is_active']),
            models.Index(fields=['fee_deadline']),
        ]

    def save(self, *args, **kwargs):
        if self.is_current:
            AcademicTerm.objects.filter(school=self.school, is_current=True).update(is_current=False)
        is_new = self._state.adding
        old_fee_deadline = None
        is_activating = False
        if self.is_active:
            if is_new:
                is_activating = True
            else:
                try:
                    old = AcademicTerm.objects.get(pk=self.pk)
                    old_fee_deadline = old.fee_deadline
                    if not old.is_active:
                        is_activating = True
                except AcademicTerm.DoesNotExist:
                    is_activating = True
        else:
            if not is_new:
                try:
                    old = AcademicTerm.objects.get(pk=self.pk)
                    old_fee_deadline = old.fee_deadline
                except AcademicTerm.DoesNotExist:
                    pass

        super().save(*args, **kwargs)
        
        if is_activating:
            from payments.services import FeeService
            FeeService.generate_fee_records_for_term(self)

        # US-013: Reschedule all pending Celery tasks if term dates change
        if not is_new and old_fee_deadline and old_fee_deadline != self.fee_deadline:
            from automation.tasks import reschedule_term_reminders
            reschedule_term_reminders.delay(str(self.pk))

    def is_school_day(self, date=None):
        """
        US-063: Central check used by all message tasks.
        Returns True if the date falls within an active school day.
        """
        from automation.services import CalendarService
        return CalendarService.is_school_day(self.school, date or timezone.localdate())

    def __str__(self):
        return f"{self.school.name} — {self.name}"


class HolidayPeriod(models.Model):
    """
    US-063: Holiday periods suppress ALL automated messaging.
    """
    school = models.ForeignKey(School, on_delete=models.CASCADE, related_name='holidays')
    name = models.CharField(max_length=100, help_text="e.g. 'End of Term 1 Holiday'")
    start_date = models.DateField()
    end_date = models.DateField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'holiday_periods'
        ordering = ['start_date']
        indexes = [models.Index(fields=['school', 'start_date', 'end_date'])]

    def __str__(self):
        return f"{self.school.name} — {self.name} ({self.start_date} to {self.end_date})"


class SchoolMoMoConfig(models.Model):
    """
    US-031: Per-school MoMo credentials, encrypted at rest.
    Credentials NEVER returned in API responses in plain text.
    Each school gets a unique webhook signing key.
    """
    PROVIDER_CHOICES = [('mtn', 'MTN MoMo'), ('airtel', 'Airtel Money')]

    school = models.ForeignKey(School, on_delete=models.CASCADE, related_name='momo_configs')
    provider = models.CharField(max_length=10, choices=PROVIDER_CHOICES)

    # MTN fields
    mtn_collection_api_user = models.TextField(blank=True)    # Encrypted
    mtn_collection_api_key = models.TextField(blank=True)     # Encrypted
    mtn_subscription_key = models.TextField(blank=True)        # Encrypted
    mtn_environment = models.CharField(max_length=20, default='production',
        choices=[('sandbox', 'Sandbox'), ('production', 'Production')])

    # Airtel fields
    airtel_client_id = models.TextField(blank=True)            # Encrypted
    airtel_client_secret = models.TextField(blank=True)        # Encrypted
    airtel_environment = models.CharField(max_length=20, default='production')

    # Webhook security — unique signing key per school
    webhook_signing_key = models.CharField(max_length=64,
        help_text="HMAC-SHA256 signing key for this school's webhook endpoint")

    # Merchant account
    merchant_name = models.CharField(max_length=200)
    merchant_phone = models.CharField(max_length=20,
        help_text="The school's MoMo merchant number parents pay into")

    is_active = models.BooleanField(default=True)
    last_tested_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'school_momo_configs'
        unique_together = [('school', 'provider')]

    def __str__(self):
        return f"{self.school.name} — {self.get_provider_display()}"


class MessagingPause(models.Model):
    """
    US-064: Director-initiated pause of all automated reminders.
    Tasks scheduled during pause period are dropped (not queued).
    Director receives summary of dropped tasks when pause ends.
    Emergency broadcasts bypass suppression.
    """
    school = models.ForeignKey(School, on_delete=models.CASCADE, related_name='messaging_pauses')
    start_date = models.DateField()
    end_date = models.DateField()
    reason = models.TextField(help_text='Reason for pausing, e.g. examination period')
    is_active = models.BooleanField(default=True)
    dropped_tasks_count = models.PositiveIntegerField(default=0)
    dropped_tasks_summary = models.JSONField(
        null=True, blank=True,
        help_text='Summary of tasks dropped during pause period'
    )
    created_by = models.ForeignKey(
        'authentication.User', on_delete=models.SET_NULL,
        null=True, related_name='messaging_pauses_created'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    ended_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'messaging_pauses'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['school', 'is_active']),
            models.Index(fields=['school', 'start_date', 'end_date']),
        ]

    def __str__(self):
        return f"{self.school.name} — Pause {self.start_date} to {self.end_date}"


class Timetable(models.Model):
    """Class timetable content published for guardian self-service commands."""
    school = models.ForeignKey(School, on_delete=models.CASCADE, related_name='timetables')
    class_group = models.ForeignKey('students.ClassGroup', on_delete=models.CASCADE, related_name='timetables')
    title = models.CharField(max_length=120, blank=True, default='')
    content = models.TextField(help_text='Formatted timetable text that can be sent over WhatsApp.')
    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(
        'authentication.User', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='timetables_created'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'timetables'
        ordering = ['class_group__name', '-updated_at']
        indexes = [
            models.Index(fields=['school', 'is_active']),
            models.Index(fields=['class_group', 'is_active']),
        ]

    def save(self, *args, **kwargs):
        if self.class_group and self.school_id and self.class_group.school_id != self.school_id:
            raise ValueError('Class group must belong to the same school as the timetable.')
        if self.is_active:
            Timetable.objects.filter(
                school=self.school,
                class_group=self.class_group,
                is_active=True,
            ).exclude(pk=self.pk).update(is_active=False)
        super().save(*args, **kwargs)

    def __str__(self):
        title = f" - {self.title}" if self.title else ''
        return f"{self.school.name} — {self.class_group.name}{title}"
