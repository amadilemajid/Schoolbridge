"""
Behaviour & Discipline models.
Tracks both disciplinary incidents and positive commendations.
Supports suspension records with Director approval workflow.
"""
import uuid
from django.db import models
from schools.managers import TenantManager


class BehaviourIncident(models.Model):
    """
    Records a behavioural event — positive commendation or disciplinary action.
    Supports WhatsApp notification to the student's primary guardian.
    """
    INCIDENT_TYPE_CHOICES = [
        ('positive', 'Positive Commendation'),
        ('warning', 'Warning'),
        ('suspension', 'Suspension'),
        ('expulsion', 'Expulsion'),
    ]

    CATEGORY_CHOICES = [
        ('attendance', 'Attendance'),
        ('academic', 'Academic'),
        ('conduct', 'Conduct'),
        ('property', 'School Property'),
        ('bullying', 'Bullying / Harassment'),
        ('other', 'Other'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    school = models.ForeignKey(
        'schools.School', on_delete=models.CASCADE, related_name='behaviour_incidents'
    )
    academic_term = models.ForeignKey(
        'schools.AcademicTerm', on_delete=models.CASCADE,
        related_name='behaviour_incidents', null=True, blank=True
    )
    student = models.ForeignKey(
        'students.Student', on_delete=models.CASCADE, related_name='behaviour_incidents'
    )
    class_group = models.ForeignKey(
        'students.ClassGroup', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='behaviour_incidents'
    )

    incident_type = models.CharField(max_length=20, choices=INCIDENT_TYPE_CHOICES)
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES, default='conduct')
    title = models.CharField(max_length=200)
    description = models.TextField()
    incident_date = models.DateField()

    reported_by = models.ForeignKey(
        'authentication.User', on_delete=models.SET_NULL,
        null=True, related_name='behaviour_incidents_reported'
    )
    handled_by = models.ForeignKey(
        'authentication.User', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='behaviour_incidents_handled'
    )
    action_taken = models.TextField(blank=True)

    # Guardian notification
    parent_notified = models.BooleanField(default=False)
    parent_notified_at = models.DateTimeField(null=True, blank=True)
    parent_notification_message = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = TenantManager()
    all_objects = models.Manager()

    class Meta:
        db_table = 'behaviour_incidents'
        ordering = ['-incident_date', '-created_at']
        indexes = [
            models.Index(fields=['school', 'incident_date']),
            models.Index(fields=['school', 'incident_type']),
            models.Index(fields=['student', 'incident_date']),
            models.Index(fields=['school', 'academic_term', 'incident_type']),
        ]

    def __str__(self):
        return f"{self.get_incident_type_display()} — {self.student} — {self.incident_date}"


class BehaviourSuspension(models.Model):
    """
    Formal suspension record linked to a BehaviourIncident.
    Requires Director approval. Tracks reinstatement.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    incident = models.OneToOneField(
        BehaviourIncident, on_delete=models.CASCADE, related_name='suspension'
    )
    school = models.ForeignKey(
        'schools.School', on_delete=models.CASCADE, related_name='suspensions'
    )
    student = models.ForeignKey(
        'students.Student', on_delete=models.CASCADE, related_name='suspensions'
    )

    suspension_start = models.DateField()
    suspension_end = models.DateField()
    reason = models.TextField()

    # Director approval workflow
    director_approved = models.BooleanField(default=False)
    approved_by = models.ForeignKey(
        'authentication.User', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='suspensions_approved'
    )
    approved_at = models.DateTimeField(null=True, blank=True)

    # Reinstatement
    reinstated = models.BooleanField(default=False)
    reinstatement_date = models.DateField(null=True, blank=True)
    reinstatement_confirmed_by = models.ForeignKey(
        'authentication.User', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='reinstatements_confirmed'
    )
    reinstatement_notes = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = TenantManager()
    all_objects = models.Manager()

    class Meta:
        db_table = 'behaviour_suspensions'
        ordering = ['-suspension_start']
        indexes = [
            models.Index(fields=['school', 'suspension_start']),
            models.Index(fields=['student', 'suspension_start']),
            models.Index(fields=['school', 'director_approved']),
        ]

    def __str__(self):
        return f"Suspension — {self.student} — {self.suspension_start} to {self.suspension_end}"

    @property
    def duration_days(self):
        return (self.suspension_end - self.suspension_start).days + 1
