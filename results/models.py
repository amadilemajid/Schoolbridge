"""
Results/Academic models.
US-041: Marks entry, locked on submission.
US-042: Auto-compute totals, class average, rank.
US-043: UNEB PLE (P7) report card.
US-044: UNEB UCE (S4) report card.
US-045: UNEB UACE (S6) report card.
"""
import uuid
from django.db import models
from schools.managers import TenantManager


class Subject(models.Model):
    school = models.ForeignKey('schools.School', on_delete=models.CASCADE, related_name='subjects')
    name = models.CharField(max_length=100)
    code = models.CharField(max_length=10, blank=True)
    class_levels = models.CharField(max_length=200, blank=True,
        help_text="Comma-separated class levels this subject applies to, e.g. 'P7,S4'")
    is_active = models.BooleanField(default=True)

    objects = TenantManager()
    all_objects = models.Manager()

    class Meta:
        db_table = 'subjects'
        unique_together = [('school', 'name')]


class Assessment(models.Model):
    """An assessment (exam, test, project) within a term for a class+subject."""
    ASSESSMENT_TYPES = [
        ('bot', 'Beginning of Term'),
        ('mot', 'Middle of Term'),
        ('eot', 'End of Term Exam'),
        ('coursework', 'Coursework'),
        ('project', 'Project'),
    ]
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    school = models.ForeignKey('schools.School', on_delete=models.CASCADE)
    academic_term = models.ForeignKey('schools.AcademicTerm', on_delete=models.CASCADE)
    class_group = models.ForeignKey('students.ClassGroup', on_delete=models.CASCADE)
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE)
    name = models.CharField(max_length=100)
    assessment_type = models.CharField(max_length=20, choices=ASSESSMENT_TYPES)
    max_marks = models.PositiveSmallIntegerField(default=100)
    weight = models.DecimalField(max_digits=5, decimal_places=2, default=1.0,
        help_text="Weight in final total computation (e.g. 0.3 for 30%)")

    # Locking (US-041)
    is_locked = models.BooleanField(default=False,
        help_text="Locked after submission. Director can unlock.")
    locked_at = models.DateTimeField(null=True, blank=True)
    locked_by = models.ForeignKey('authentication.User', on_delete=models.SET_NULL,
                                  null=True, blank=True, related_name='locked_assessments')

    objects = TenantManager()
    all_objects = models.Manager()

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'assessments'
        indexes = [
            models.Index(fields=['school', 'academic_term', 'class_group']),
        ]


class AssessmentMark(models.Model):
    """Individual student mark for an assessment."""
    assessment = models.ForeignKey(Assessment, on_delete=models.CASCADE, related_name='marks')
    student = models.ForeignKey('students.Student', on_delete=models.CASCADE, related_name='marks')
    marks_obtained = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    is_absent = models.BooleanField(default=False)
    comment = models.CharField(max_length=200, blank=True)
    entered_by = models.ForeignKey('authentication.User', on_delete=models.SET_NULL,
                                   null=True, related_name='marks_entered')
    entered_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'assessment_marks'
        unique_together = [('assessment', 'student')]
        indexes = [models.Index(fields=['assessment', 'student'])]

    def clean(self):
        from django.core.exceptions import ValidationError
        if self.marks_obtained is not None:
            if self.marks_obtained < 0:
                raise ValidationError("Marks cannot be negative.")
            if self.marks_obtained > self.assessment.max_marks:
                raise ValidationError(
                    f"Marks ({self.marks_obtained}) exceed maximum ({self.assessment.max_marks})."
                )


class TermResult(models.Model):
    """
    US-042: Computed term result per student per term.
    Stores total, average, rank, grade.
    Regenerated whenever marks are updated.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    school = models.ForeignKey('schools.School', on_delete=models.CASCADE)
    student = models.ForeignKey('students.Student', on_delete=models.CASCADE, related_name='term_results')
    academic_term = models.ForeignKey('schools.AcademicTerm', on_delete=models.CASCADE)
    class_group = models.ForeignKey('students.ClassGroup', on_delete=models.CASCADE)

    total_marks = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    average_marks = models.DecimalField(max_digits=6, decimal_places=2, default=0)
    class_rank = models.PositiveSmallIntegerField(null=True, blank=True)
    total_students = models.PositiveSmallIntegerField(default=0)
    class_average = models.DecimalField(max_digits=6, decimal_places=2, default=0)

    # UNEB grades
    division = models.CharField(max_length=5, blank=True)
    aggregate = models.PositiveSmallIntegerField(null=True, blank=True)

    # Report card
    report_card_pdf = models.FileField(upload_to='report_cards/', null=True, blank=True)
    report_card_url = models.URLField(blank=True,
        help_text="Signed S3 URL for parent access (30-day expiry)")
    report_card_generated_at = models.DateTimeField(null=True, blank=True)
    parent_notified = models.BooleanField(default=False)

    objects = TenantManager()
    all_objects = models.Manager()

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'term_results'
        unique_together = [('student', 'academic_term')]
        indexes = [
            models.Index(fields=['school', 'academic_term', 'class_group']),
        ]
