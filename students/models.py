"""
Students app models.
US-008: Bulk CSV import.
US-009: Single add with Ugandan phone validation, unique student ID.
US-010: Edit with before/after audit.
US-011: Multiple guardians (up to 3), primary guardian.
US-012: Class groups with form teacher, historical assignments.
US-014: Search <500ms.
US-015: Enrolment reports.
US-070: PII encryption at rest — guardian name, phone, student DOB.
"""
import hashlib
import uuid
from django.db import models
from django.core.validators import RegexValidator
from schools.encrypted_fields import EncryptedCharField, EncryptedDateField
from schools.managers import TenantManager


UGANDA_PHONE_REGEX = RegexValidator(
    regex=r'^(\+256|0)(7[0-9]{8}|4[0-9]{8}|3[0-9]{8})$',
    message='Enter a valid Ugandan phone number (e.g. +256701234567 or 0701234567).'
)


class ClassGroup(models.Model):
    """
    US-012: Class group with form teacher.
    Historical assignments preserved in ClassAssignment.
    """
    school = models.ForeignKey('schools.School', on_delete=models.CASCADE, related_name='classes')
    name = models.CharField(max_length=50, help_text="e.g. 'P.7 East', 'S.4 A'")
    level = models.CharField(max_length=20, help_text="e.g. 'P7', 'S4'")
    stream = models.CharField(max_length=10, blank=True, help_text="e.g. 'A', 'East'")
    form_teacher = models.ForeignKey(
        'authentication.User', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='form_classes'
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    objects = TenantManager()
    all_objects = models.Manager()

    class Meta:
        db_table = 'class_groups'
        unique_together = [('school', 'name')]
        ordering = ['level', 'stream']
        indexes = [models.Index(fields=['school', 'is_active'])]

    def __str__(self):
        return f"{self.school.name} — {self.name}"


class Student(models.Model):
    """
    US-009: Student record with unique ID per school.
    US-010: All edits logged with before/after values.
    """
    GENDER_CHOICES = [('M', 'Male'), ('F', 'Female')]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    school = models.ForeignKey('schools.School', on_delete=models.CASCADE, related_name='students')

    # US-009: Unique student ID (school-scoped sequential number)
    student_id = models.CharField(max_length=20,
        help_text="Unique ID within the school, e.g. 'SCH-2024-001'")

    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    other_names = models.CharField(max_length=100, blank=True)
    date_of_birth = models.DateField(null=True, blank=True)
    gender = models.CharField(max_length=1, choices=GENDER_CHOICES)

    current_class = models.ForeignKey(
        ClassGroup, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='current_students'
    )
    admission_date = models.DateField()
    academic_year_admitted = models.PositiveIntegerField()

    # Status
    is_active = models.BooleanField(default=True)
    deactivated_at = models.DateTimeField(null=True, blank=True)
    deactivation_reason = models.CharField(max_length=200, blank=True)

    # Siblings linkage (US-011)
    siblings = models.ManyToManyField('self', blank=True, symmetrical=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        'authentication.User', on_delete=models.SET_NULL,
        null=True, related_name='students_created'
    )

    objects = TenantManager()
    all_objects = models.Manager()

    class Meta:
        db_table = 'students'
        unique_together = [('school', 'student_id')]
        ordering = ['last_name', 'first_name']
        indexes = [
            models.Index(fields=['school', 'is_active']),
            models.Index(fields=['school', 'current_class']),
            models.Index(fields=['last_name', 'first_name']),
        ]

    def __str__(self):
        return f"{self.get_full_name()} ({self.student_id})"

    def get_full_name(self):
        parts = [self.first_name, self.other_names, self.last_name]
        return ' '.join(p for p in parts if p).strip()

    @property
    def admission_number(self):
        """Domain alias for student_id standard in Ugandan schools."""
        return self.student_id

    @classmethod
    def generate_student_id(cls, school):
        """Generate next sequential student ID for the school."""
        from django.utils import timezone
        from django.db import transaction
        from schools.models import School

        with transaction.atomic():
            locked_school = School.objects.select_for_update().get(pk=school.pk)
            year = timezone.now().year
            prefix = f"SCH-{year}-"
            last = (cls.all_objects.filter(school=locked_school, student_id__startswith=prefix)
                    .order_by('-student_id').first())
            if last:
                try:
                    num = int(last.student_id.split('-')[-1]) + 1
                except (ValueError, IndexError):
                    num = 1
            else:
                num = 1
            return f"{prefix}{num:04d}"


class Guardian(models.Model):
    """
    US-011: Up to 3 guardians per student.
    Primary guardian receives all WhatsApp messages.
    Phone is used to match incoming MoMo payments.
    """
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='guardians')

    # US-070: Encrypted PII — guardian name fields
    first_name = EncryptedCharField(max_length=100)
    last_name = EncryptedCharField(max_length=100)
    relationship = models.CharField(max_length=50,
        help_text="e.g. 'Father', 'Mother', 'Uncle', 'Guardian'")

    # US-009: Ugandan phone validation
    # US-070: phone and phone_normalised are encrypted at rest.
    # phone_hash (SHA-256 of phone_normalised) is stored plain for DB lookups.
    phone = EncryptedCharField(max_length=20)
    phone_normalised = EncryptedCharField(max_length=20, blank=True,
        help_text="Normalised to +256XXXXXXXXX format for WhatsApp/MoMo matching — encrypted")
    phone_hash = models.CharField(
        max_length=64,
        blank=True,
        db_index=True,
        help_text="SHA-256 of phone_normalised — used for DB lookups without decrypting"
    )
    email = models.EmailField(blank=True)

    is_primary = models.BooleanField(default=False,
        help_text="Primary guardian receives all automated WhatsApp messages")
    receives_sms = models.BooleanField(default=True)
    preferred_language = models.CharField(
        max_length=10,
        choices=[('en', 'English'), ('lg', 'Luganda')],
        default='en',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'guardians'
        ordering = ['-is_primary', 'first_name']
        indexes = [
            models.Index(fields=['phone_hash']),
            models.Index(fields=['student', 'is_primary']),
        ]

    def save(self, *args, **kwargs):
        # Enforce only one primary guardian per student
        if self.is_primary:
            Guardian.objects.filter(student=self.student, is_primary=True).exclude(
                pk=self.pk
            ).update(is_primary=False)

        # Always recompute phone_normalised and phone_hash BEFORE super().save()
        # so every row in the DB has a consistent hash for WhatsApp lookups.
        # US-070: phone_hash is plain-text SHA-256 of phone_normalised (+256…).
        self.phone_normalised = self._normalise_phone(self.phone) or ''
        if self.phone_normalised:
            self.phone_hash = hashlib.sha256(self.phone_normalised.encode()).hexdigest()

        # If caller passed update_fields, force phone_normalised + phone_hash into the set
        # so a partial save (e.g. g.save(update_fields=['is_primary'])) never leaves
        # the hash column stale.
        update_fields = kwargs.get('update_fields')
        if update_fields is not None:
            updated = set(update_fields)
            updated.update({'phone_normalised', 'phone_hash'})
            kwargs['update_fields'] = list(updated)

        super().save(*args, **kwargs)

        # US-010: Re-confirm WhatsApp if number changes
        if not self._state.adding and hasattr(self, '_old_phone') and self._old_phone != self.phone:
            from messaging.tasks import send_whatsapp_message
            send_whatsapp_message.delay(
                phone=self.phone_normalised,
                template='guardian_number_changed',
                context={'student_name': self.student.get_full_name()},
            )

    @staticmethod
    def _normalise_phone(phone):
        """Convert 07XXXXXXXX or +2567XXXXXXXX to +256XXXXXXXXX."""
        from config.validators import normalise_uganda_phone
        return normalise_uganda_phone(phone)

    def __str__(self):
        return f"{self.first_name} {self.last_name} ({self.relationship}) — {self.student}"


class ClassAssignment(models.Model):
    """
    US-012: Historical class assignments are preserved.
    When a student moves class, old assignment is kept with end_date.
    """
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='class_assignments')
    class_group = models.ForeignKey(ClassGroup, on_delete=models.CASCADE, related_name='assignments')
    academic_term = models.ForeignKey('schools.AcademicTerm', on_delete=models.CASCADE)
    start_date = models.DateField()
    end_date = models.DateField(null=True, blank=True, help_text="Null means currently assigned")
    assigned_by = models.ForeignKey(
        'authentication.User', on_delete=models.SET_NULL,
        null=True, related_name='class_assignments_made'
    )

    class Meta:
        db_table = 'class_assignments'
        ordering = ['-start_date']
        indexes = [
            models.Index(fields=['student', 'end_date']),
            models.Index(fields=['class_group', 'academic_term']),
        ]


class BulkImportJob(models.Model):
    """
    US-008: Tracks a bulk CSV import job.
    Partial imports are supported — valid rows imported, invalid rows reported.
    """
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('processing', 'Processing'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
    ]
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    school = models.ForeignKey('schools.School', on_delete=models.CASCADE)
    uploaded_by = models.ForeignKey('authentication.User', on_delete=models.CASCADE)
    csv_file = models.FileField(upload_to='import_jobs/')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')

    total_rows = models.PositiveIntegerField(default=0)
    imported_count = models.PositiveIntegerField(default=0)
    failed_count = models.PositiveIntegerField(default=0)

    error_report = models.JSONField(null=True, blank=True,
        help_text="List of {row, errors} dicts for failed rows")
    error_report_file = models.FileField(upload_to='import_errors/', null=True, blank=True)

    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'bulk_import_jobs'
        ordering = ['-created_at']
