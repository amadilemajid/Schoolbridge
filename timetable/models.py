"""
Structured Timetable Backend — Models.

EPIC-D: Versioned class timetables with period-level granularity,
teacher assignments, substitution tracking, and WhatsApp integration.

Coexists with the existing schools.Timetable free-text model — this
provides structured data that can be synced to that format.
"""
import uuid
from django.db import models
from schools.managers import TenantManager


class TimetableVersion(models.Model):
    """
    Versioned timetable for a class group within an academic term.
    Only one active version per class/term at any time.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    school = models.ForeignKey(
        'schools.School', on_delete=models.CASCADE,
        related_name='timetable_versions',
    )
    class_group = models.ForeignKey(
        'students.ClassGroup', on_delete=models.CASCADE,
        related_name='timetable_versions',
    )
    academic_term = models.ForeignKey(
        'schools.AcademicTerm', on_delete=models.CASCADE,
        related_name='timetable_versions',
    )

    version_number = models.PositiveSmallIntegerField(default=1)
    is_active = models.BooleanField(default=True)
    effective_from = models.DateField(
        help_text="Date from which this timetable version takes effect"
    )
    notes = models.TextField(
        blank=True,
        help_text="Reason for creating a new version, e.g. 'Teacher rotation'"
    )

    created_by = models.ForeignKey(
        'authentication.User', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='timetable_versions_created',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    objects = TenantManager()
    all_objects = models.Manager()

    class Meta:
        db_table = 'timetable_versions'
        unique_together = [('class_group', 'academic_term', 'version_number')]
        ordering = ['-version_number']
        indexes = [
            models.Index(fields=['school', 'class_group', 'is_active']),
        ]

    def save(self, *args, **kwargs):
        # Deactivate other versions for same class/term when activating
        if self.is_active:
            TimetableVersion.all_objects.filter(
                class_group=self.class_group,
                academic_term=self.academic_term,
                is_active=True,
            ).exclude(pk=self.pk).update(is_active=False)
        super().save(*args, **kwargs)

    def __str__(self):
        return (
            f"{self.class_group.name} — v{self.version_number} "
            f"({self.academic_term.name})"
        )


class TimetableSlot(models.Model):
    """
    A single period/slot within a timetable version.
    Represents one lesson, break, assembly, etc. on a specific day.
    """
    DAY_CHOICES = [
        (0, 'Monday'),
        (1, 'Tuesday'),
        (2, 'Wednesday'),
        (3, 'Thursday'),
        (4, 'Friday'),
    ]

    SLOT_TYPE_CHOICES = [
        ('lesson', 'Lesson'),
        ('break', 'Break'),
        ('assembly', 'Assembly'),
        ('lunch', 'Lunch'),
        ('study', 'Study Period'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    timetable_version = models.ForeignKey(
        TimetableVersion, on_delete=models.CASCADE,
        related_name='slots',
    )
    school = models.ForeignKey(
        'schools.School', on_delete=models.CASCADE,
    )

    day_of_week = models.PositiveSmallIntegerField(choices=DAY_CHOICES)
    period_number = models.PositiveSmallIntegerField(
        help_text="Period number within the day (1, 2, 3...)"
    )
    start_time = models.TimeField()
    end_time = models.TimeField()

    # Subject linkage
    subject = models.ForeignKey(
        'results.Subject', on_delete=models.SET_NULL,
        null=True, blank=True,
        help_text="Linked subject (for lesson slots)"
    )
    subject_name = models.CharField(
        max_length=100, blank=True,
        help_text="Display name fallback when subject FK is not set"
    )

    # Teacher assignment
    teacher = models.ForeignKey(
        'authentication.User', on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='timetable_slots',
    )

    room = models.CharField(max_length=50, blank=True)
    slot_type = models.CharField(
        max_length=10, choices=SLOT_TYPE_CHOICES, default='lesson',
    )

    objects = TenantManager()
    all_objects = models.Manager()

    class Meta:
        db_table = 'timetable_slots'
        unique_together = [('timetable_version', 'day_of_week', 'period_number')]
        ordering = ['day_of_week', 'period_number']
        indexes = [
            models.Index(fields=['teacher', 'day_of_week']),
            models.Index(fields=['school', 'day_of_week']),
        ]

    @property
    def display_subject(self):
        """Return the subject name for display."""
        if self.subject:
            return self.subject.name
        return self.subject_name or self.get_slot_type_display()

    def __str__(self):
        day = self.get_day_of_week_display()
        return (
            f"{day} P{self.period_number} "
            f"{self.start_time.strftime('%H:%M')}-{self.end_time.strftime('%H:%M')} "
            f"— {self.display_subject}"
        )


class SubstitutionRecord(models.Model):
    """
    Teacher substitution tracking for a specific slot on a specific date.
    One substitution per slot per date.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    school = models.ForeignKey(
        'schools.School', on_delete=models.CASCADE,
    )
    timetable_slot = models.ForeignKey(
        TimetableSlot, on_delete=models.CASCADE,
        related_name='substitutions',
    )
    date = models.DateField()

    original_teacher = models.ForeignKey(
        'authentication.User', on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='original_substitutions',
    )
    substitute_teacher = models.ForeignKey(
        'authentication.User', on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='substitute_assignments',
    )
    reason = models.CharField(max_length=200)

    created_by = models.ForeignKey(
        'authentication.User', on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='substitutions_created',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    objects = TenantManager()
    all_objects = models.Manager()

    class Meta:
        db_table = 'substitution_records'
        unique_together = [('timetable_slot', 'date')]
        ordering = ['-date']
        indexes = [
            models.Index(fields=['school', 'date']),
            models.Index(fields=['substitute_teacher', 'date']),
        ]

    def __str__(self):
        return (
            f"{self.date} — {self.timetable_slot} "
            f"(Sub: {self.substitute_teacher})"
        )
