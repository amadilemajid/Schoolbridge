"""
Attendance models.
US-049: Daily attendance, 7am-12pm window, locks at 12pm.
US-050: Summary with % rate per student.
US-051: Auto-alert Director below 75%.
US-052: Parent pre-absence via ABSENT command.
US-053: Attendance vs fee cross-reference.
"""
import uuid
from django.db import models
from schools.managers import TenantManager


class AttendanceRecord(models.Model):
    """One record per student per school day."""
    STATUS_CHOICES = [
        ('present', 'Present'),
        ('absent', 'Absent'),
        ('excused', 'Excused'),
        ('late', 'Late'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    school = models.ForeignKey('schools.School', on_delete=models.CASCADE)
    student = models.ForeignKey('students.Student', on_delete=models.CASCADE, related_name='attendance_records')
    class_group = models.ForeignKey('students.ClassGroup', on_delete=models.CASCADE)
    academic_term = models.ForeignKey('schools.AcademicTerm', on_delete=models.CASCADE)
    date = models.DateField()
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='present')
    marked_by = models.ForeignKey('authentication.User', on_delete=models.SET_NULL,
                                  null=True, related_name='attendance_marked')
    notes = models.CharField(max_length=200, blank=True)

    # Pre-excused absence from parent WhatsApp ABSENT command (US-052)
    pre_excused = models.BooleanField(default=False)
    pre_excused_reason = models.CharField(max_length=200, blank=True)
    pre_excused_at = models.DateTimeField(null=True, blank=True)

    # Alert tracking (US-051)
    alert_sent = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    objects = TenantManager()
    all_objects = models.Manager()

    class Meta:
        db_table = 'attendance_records'
        unique_together = [('student', 'date')]
        ordering = ['-date']
        indexes = [
            models.Index(fields=['school', 'date']),
            models.Index(fields=['student', 'date']),
            models.Index(fields=['class_group', 'date']),
        ]

    def __str__(self):
        return f"{self.student} — {self.date} — {self.status}"
