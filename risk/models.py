"""
At-Risk Student Intelligence Engine — Models.

EPIC-E: Configurable risk thresholds, cached student risk profiles,
and weekly historical snapshots for dropout trend analysis.

Risk criteria (v1):
  - Attendance < configurable threshold (default 75%)
  - Fee payment ratio below threshold (default 50%)
  - Outstanding balance above absolute threshold (default 100,000 UGX)

Future extension hooks:
  - Behaviour incidents count
  - Academic performance average
"""
import uuid
from django.db import models
from schools.managers import TenantManager


class RiskConfiguration(models.Model):
    """
    Per-school risk thresholds and notification settings.
    One configuration per school (OneToOne).
    """
    school = models.OneToOneField(
        'schools.School', on_delete=models.CASCADE,
        related_name='risk_configuration',
    )

    # Attendance threshold — percentage below which student is flagged
    attendance_threshold = models.DecimalField(
        max_digits=5, decimal_places=2, default=75.00,
        help_text="Attendance % below which a student is flagged (e.g. 75.00)"
    )

    # Fee payment ratio — percentage of total fees paid
    fee_payment_ratio_threshold = models.DecimalField(
        max_digits=5, decimal_places=2, default=50.00,
        help_text="Fee payment % below which a student is flagged (e.g. 50.00)"
    )

    # Absolute balance threshold in UGX
    outstanding_balance_threshold = models.DecimalField(
        max_digits=12, decimal_places=0, default=100000,
        help_text="Outstanding balance (UGX) above which student is flagged"
    )

    # Grace period — don't evaluate until N school days into a term
    grace_period_days = models.PositiveSmallIntegerField(
        default=10,
        help_text="Number of recorded school days before risk evaluation activates"
    )

    # Notification settings
    enable_whatsapp_alerts = models.BooleanField(
        default=True,
        help_text="Send WhatsApp alert to Director when student enters high risk"
    )
    enable_monday_briefing = models.BooleanField(
        default=True,
        help_text="Send Monday morning at-risk briefing to Director"
    )

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'risk_configurations'
        verbose_name = 'Risk Configuration'
        verbose_name_plural = 'Risk Configurations'

    def __str__(self):
        return f"Risk Config — {self.school.name}"


class StudentRiskProfile(models.Model):
    """
    Cached risk profile for a student in the active term.
    Recalculated weekly via Celery or on-demand via dashboard trigger.
    Designed for sub-100ms dashboard queries.
    """
    RISK_LEVELS = [
        ('low', 'Low'),
        ('medium', 'Medium'),
        ('high', 'High'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    student = models.ForeignKey(
        'students.Student', on_delete=models.CASCADE,
        related_name='risk_profiles',
    )
    school = models.ForeignKey(
        'schools.School', on_delete=models.CASCADE,
        related_name='risk_profiles',
    )
    academic_term = models.ForeignKey(
        'schools.AcademicTerm', on_delete=models.CASCADE,
        related_name='risk_profiles',
    )

    # Attendance metrics
    attendance_rate = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True,
        help_text="Calculated attendance percentage, e.g. 82.50"
    )
    total_days_recorded = models.PositiveIntegerField(default=0)
    days_absent = models.PositiveIntegerField(default=0)

    # Fee metrics
    fee_payment_ratio = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True,
        help_text="Percentage of total fees paid, e.g. 45.00"
    )
    fee_balance = models.DecimalField(
        max_digits=12, decimal_places=0, default=0,
        help_text="Outstanding fee balance in UGX"
    )

    # Composite risk
    risk_score = models.PositiveSmallIntegerField(
        default=0,
        help_text="Composite risk score 0 (safe) to 100 (critical dropout risk)"
    )
    risk_level = models.CharField(
        max_length=10, choices=RISK_LEVELS, default='low',
    )
    flagged_factors = models.JSONField(
        default=list,
        help_text="List of triggered factors, e.g. ['low_attendance', 'fee_defaulter']"
    )

    # Alert throttling — prevents duplicate WhatsApp pings within a recalculation cycle
    alert_dispatched = models.BooleanField(default=False)

    last_calculated_at = models.DateTimeField(auto_now=True)

    objects = TenantManager()
    all_objects = models.Manager()

    class Meta:
        db_table = 'student_risk_profiles'
        unique_together = [('student', 'academic_term')]
        indexes = [
            models.Index(fields=['school', 'risk_level']),
            models.Index(fields=['school', 'risk_score']),
            models.Index(fields=['school', 'academic_term', 'risk_level']),
        ]

    def __str__(self):
        return f"{self.student} — {self.risk_level} ({self.risk_score})"


class StudentRiskSnapshot(models.Model):
    """
    Weekly historical snapshot of a student's risk profile.
    Used for trend analysis and dropout forecasting dashboards.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    student = models.ForeignKey(
        'students.Student', on_delete=models.CASCADE,
        related_name='risk_snapshots',
    )
    school = models.ForeignKey(
        'schools.School', on_delete=models.CASCADE,
    )
    academic_term = models.ForeignKey(
        'schools.AcademicTerm', on_delete=models.CASCADE,
    )

    attendance_rate = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True,
    )
    fee_payment_ratio = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True,
    )
    risk_score = models.PositiveSmallIntegerField(default=0)
    risk_level = models.CharField(max_length=10, default='low')
    flagged_factors = models.JSONField(default=list)

    snapshot_date = models.DateField(
        help_text="Date of the snapshot (usually Sunday evening)"
    )

    objects = TenantManager()
    all_objects = models.Manager()

    class Meta:
        db_table = 'student_risk_snapshots'
        unique_together = [('student', 'academic_term', 'snapshot_date')]
        ordering = ['-snapshot_date']
        indexes = [
            models.Index(fields=['academic_term', 'snapshot_date']),
            models.Index(fields=['student', 'snapshot_date']),
        ]

    def __str__(self):
        return f"{self.student} — {self.snapshot_date} — {self.risk_level}"
