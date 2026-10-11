"""
Homework app models.
Tracks teacher-assigned homework, student submission status, and grading.
"""
import uuid
from django.db import models
from schools.managers import TenantManager


class HomeworkAssignment(models.Model):
    """
    A homework assignment created by a teacher for a class/subject.
    Published assignments trigger WhatsApp notifications to guardians.
    """
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('published', 'Published'),
        ('closed', 'Closed'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    school = models.ForeignKey(
        'schools.School', on_delete=models.CASCADE, related_name='homework_assignments'
    )
    academic_term = models.ForeignKey(
        'schools.AcademicTerm', on_delete=models.CASCADE, related_name='homework_assignments'
    )
    class_group = models.ForeignKey(
        'students.ClassGroup', on_delete=models.CASCADE, related_name='homework_assignments'
    )
    subject = models.ForeignKey(
        'results.Subject', on_delete=models.CASCADE, related_name='homework_assignments',
        null=True, blank=True
    )

    title = models.CharField(max_length=200)
    description = models.TextField(blank=True, help_text='Full instructions for students')
    assigned_date = models.DateField()
    due_date = models.DateField()

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    is_graded = models.BooleanField(default=False, help_text='Whether marks will be recorded')
    max_marks = models.PositiveSmallIntegerField(
        null=True, blank=True, help_text='Maximum marks if graded'
    )

    assigned_by = models.ForeignKey(
        'authentication.User', on_delete=models.SET_NULL,
        null=True, related_name='homework_assigned'
    )
    # WhatsApp notification tracking
    guardian_notified = models.BooleanField(default=False)
    guardian_notified_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = TenantManager()
    all_objects = models.Manager()

    class Meta:
        db_table = 'homework_assignments'
        ordering = ['-due_date']
        indexes = [
            models.Index(fields=['school', 'academic_term', 'status']),
            models.Index(fields=['school', 'class_group', 'due_date']),
            models.Index(fields=['assigned_by']),
        ]

    def __str__(self):
        return f"{self.title} — {self.class_group} — Due: {self.due_date}"

    @property
    def is_overdue(self):
        from django.utils import timezone
        return self.due_date < timezone.localdate() and self.status == 'published'

    @property
    def submission_count(self):
        return self.submissions.count()

    @property
    def completion_rate(self):
        total = self.class_group.current_students.filter(is_active=True).count()
        if total == 0:
            return 0
        submitted = self.submissions.count()
        return round((submitted / total) * 100, 1)


class HomeworkSubmission(models.Model):
    """
    Records a student's submission for a homework assignment.
    Tracks marks if the assignment is graded.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    assignment = models.ForeignKey(
        HomeworkAssignment, on_delete=models.CASCADE, related_name='submissions'
    )
    student = models.ForeignKey(
        'students.Student', on_delete=models.CASCADE, related_name='homework_submissions'
    )
    school = models.ForeignKey(
        'schools.School', on_delete=models.CASCADE, related_name='homework_submissions'
    )

    submitted_at = models.DateTimeField(auto_now_add=True)
    is_late = models.BooleanField(default=False)

    # Grading (optional)
    marks_awarded = models.PositiveSmallIntegerField(null=True, blank=True)
    feedback = models.TextField(blank=True)
    graded_by = models.ForeignKey(
        'authentication.User', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='homework_graded'
    )
    graded_at = models.DateTimeField(null=True, blank=True)

    objects = TenantManager()
    all_objects = models.Manager()

    class Meta:
        db_table = 'homework_submissions'
        unique_together = [('assignment', 'student')]
        ordering = ['submitted_at']
        indexes = [
            models.Index(fields=['school', 'assignment']),
            models.Index(fields=['student', 'submitted_at']),
        ]

    def __str__(self):
        return f"{self.student} — {self.assignment.title}"
