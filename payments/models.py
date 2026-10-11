"""
Payments app models.
US-016: Fee structure per term/class.
US-017: Real-time student fee balance.
US-018: Class-level fee summary.
US-019: Manual payment recording.
US-020: Defaulter list.
US-021: Payment plans with instalments.
US-022: School-wide fee dashboard.
US-023: Payment reversal with approval.
US-024: Fee waiver/discount.
US-026/027: MoMo IPN (MTN + Airtel) with idempotency.
US-029: Reconciliation queue.
US-070: MoMo IPN logs with hash-based idempotency.
"""
import hashlib
import uuid
from django.db import models
from django.conf import settings
from schools.managers import TenantManager


class FeeStructure(models.Model):
    """
    US-016: Fee structure per term/class.
    Can be cloned across terms. Changes after term start require Director approval.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    school = models.ForeignKey('schools.School', on_delete=models.CASCADE, related_name='fee_structures')
    academic_term = models.ForeignKey('schools.AcademicTerm', on_delete=models.CASCADE, related_name='fee_structures')
    class_group = models.ForeignKey('students.ClassGroup', on_delete=models.CASCADE,
                                    related_name='fee_structures', null=True, blank=True,
                                    help_text="Null = applies to all classes in the term")
    name = models.CharField(max_length=100, help_text="e.g. 'P7 Term 1 2024 Fees'")
    is_active = models.BooleanField(default=True)

    # Approval workflow (US-016)
    requires_approval = models.BooleanField(default=False,
        help_text="Set True when structure is changed after term has started")
    approved_by = models.ForeignKey('authentication.User', on_delete=models.SET_NULL,
                                    null=True, blank=True, related_name='approved_fee_structures')
    approved_at = models.DateTimeField(null=True, blank=True)

    objects = TenantManager()
    all_objects = models.Manager()

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey('authentication.User', on_delete=models.SET_NULL,
                                   null=True, related_name='fee_structures_created')

    class Meta:
        db_table = 'fee_structures'
        unique_together = [('school', 'academic_term', 'class_group')]
        indexes = [models.Index(fields=['school', 'academic_term', 'is_active'])]

    @property
    def total_amount(self):
        return self.items.aggregate(total=models.Sum('amount'))['total'] or 0

    def recalculate_fee_records(self):
        self.feerecord_set.all().update(total_amount=self.total_amount)

    def __str__(self):
        return f"{self.name}"


class FeeStructureItem(models.Model):
    """Individual fee line items within a structure (tuition, lunch, uniform, etc.)."""
    fee_structure = models.ForeignKey(FeeStructure, on_delete=models.CASCADE, related_name='items')
    name = models.CharField(max_length=100, help_text="e.g. 'Tuition', 'Lunch', 'Activity'")
    amount = models.DecimalField(max_digits=12, decimal_places=0,
                                 help_text="Amount in UGX (whole shillings)")
    is_mandatory = models.BooleanField(default=True)
    description = models.TextField(blank=True)

    class Meta:
        db_table = 'fee_structure_items'
        ordering = ['-is_mandatory', 'name']

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        self.fee_structure.recalculate_fee_records()

    def delete(self, *args, **kwargs):
        fee_structure = self.fee_structure
        super().delete(*args, **kwargs)
        fee_structure.recalculate_fee_records()

    def __str__(self):
        return f"{self.name}: UGX {self.amount:,}"


class FeeRecord(models.Model):
    """
    US-016: Auto-generated per student when a term is activated.
    Tracks the total owed, paid, balance for a student in a term.
    One record per student per term.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    school = models.ForeignKey('schools.School', on_delete=models.CASCADE)
    student = models.ForeignKey('students.Student', on_delete=models.CASCADE, related_name='fee_records')
    academic_term = models.ForeignKey('schools.AcademicTerm', on_delete=models.CASCADE, related_name='fee_records')
    fee_structure = models.ForeignKey(FeeStructure, on_delete=models.SET_NULL, null=True)

    total_amount = models.DecimalField(max_digits=12, decimal_places=0, default=0,
                                       help_text="Total fees owed for this term (UGX)")
    amount_paid = models.DecimalField(max_digits=12, decimal_places=0, default=0)
    amount_waived = models.DecimalField(max_digits=12, decimal_places=0, default=0)

    objects = TenantManager()
    all_objects = models.Manager()

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'fee_records'
        unique_together = [('student', 'academic_term')]
        indexes = [
            models.Index(fields=['school', 'academic_term']),
            models.Index(fields=['student', 'academic_term']),
        ]

    @property
    def balance(self):
        return self.total_amount - self.amount_paid - self.amount_waived

    @property
    def is_fully_paid(self):
        return self.balance <= 0

    @property
    def payment_percentage(self):
        if self.total_amount == 0:
            return 100
        return min(100, int((self.amount_paid / self.total_amount) * 100))

    def save(self, *args, **kwargs):
        if self.fee_structure:
            self.total_amount = self.fee_structure.total_amount
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.student} — Term {self.academic_term} — Balance: {self.balance:,}"


class Payment(models.Model):
    """
    US-019: Manual cash/bank payment.
    US-026/027: MoMo IPN payment (MTN + Airtel).
    Idempotency: momo_reference is unique — duplicate IPNs are rejected.
    """
    PAYMENT_METHODS = [
        ('cash', 'Cash'),
        ('bank', 'Bank Transfer'),
        ('mtn_momo', 'MTN MoMo'),
        ('airtel_money', 'Airtel Money'),
        ('momo', 'Mobile Money'),
    ]
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('completed', 'Completed'),
        ('reversed', 'Reversed'),
        ('failed', 'Failed'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    school = models.ForeignKey('schools.School', on_delete=models.CASCADE)
    fee_record = models.ForeignKey(FeeRecord, on_delete=models.CASCADE,
                                   related_name='payments', null=True, blank=True,
                                   help_text="Null if not yet matched (reconciliation queue)")
    student = models.ForeignKey('students.Student', on_delete=models.SET_NULL,
                                null=True, blank=True, related_name='payments')

    method = models.CharField(max_length=20, choices=PAYMENT_METHODS)
    amount = models.DecimalField(max_digits=12, decimal_places=0)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='completed')

    # MoMo fields (US-026, US-027)
    momo_reference = models.CharField(max_length=100, blank=True, unique=True,
                                       null=True, db_index=True,
                                       help_text="MoMo transaction reference — idempotency key")
    momo_phone = models.CharField(max_length=20, blank=True,
                                   help_text="Phone number that sent the MoMo payment")
    momo_network = models.CharField(max_length=10, blank=True,
                                    help_text="'mtn' or 'airtel'")
    momo_raw_payload = models.JSONField(null=True, blank=True,
                                        help_text="Raw IPN webhook payload for audit")

    # Manual payment fields (US-019)
    receipt_number = models.CharField(max_length=50, blank=True)
    notes = models.TextField(blank=True)
    bank_reference = models.CharField(max_length=100, blank=True)

    # Approval workflow for large amounts (US-019)
    requires_approval = models.BooleanField(default=False)
    approved_by = models.ForeignKey('authentication.User', on_delete=models.SET_NULL,
                                    null=True, blank=True, related_name='approved_payments')
    approved_at = models.DateTimeField(null=True, blank=True)

    # Reversal (US-023)
    is_reversed = models.BooleanField(default=False)
    reversal_reason = models.TextField(blank=True)
    reversed_by = models.ForeignKey('authentication.User', on_delete=models.SET_NULL,
                                    null=True, blank=True, related_name='reversed_payments')
    reversed_at = models.DateTimeField(null=True, blank=True)

    recorded_by = models.ForeignKey('authentication.User', on_delete=models.SET_NULL,
                                    null=True, related_name='payments_recorded')
    payment_date = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)

    objects = TenantManager()
    all_objects = models.Manager()

    class Meta:
        db_table = 'payments'
        ordering = ['-payment_date']
        indexes = [
            models.Index(fields=['school', 'payment_date']),
            models.Index(fields=['momo_reference']),
            models.Index(fields=['momo_phone']),
            models.Index(fields=['status']),
            models.Index(fields=['fee_record']),
            models.Index(fields=['school', 'student']),
        ]

    def __str__(self):
        return f"UGX {self.amount:,} via {self.get_method_display()} on {self.payment_date.date()}"


class PaymentPlan(models.Model):
    """
    US-021/US-C05: Payment plans with instalments.
    Parent receives immediate WhatsApp confirmation and reminders on each due date.
    """
    STATUS_CHOICES = [
        ('active', 'Active'),
        ('completed', 'Completed'),
        ('defaulted', 'Defaulted'),
        ('cancelled', 'Cancelled'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    school = models.ForeignKey('schools.School', on_delete=models.CASCADE)
    fee_record = models.OneToOneField(FeeRecord, on_delete=models.CASCADE, related_name='payment_plan')
    student = models.ForeignKey('students.Student', on_delete=models.CASCADE, related_name='payment_plans')
    total_amount = models.DecimalField(max_digits=12, decimal_places=0)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey('authentication.User', on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    objects = TenantManager()
    all_objects = models.Manager()

    class Meta:
        db_table = 'payment_plans'


class PaymentPlanInstalment(models.Model):
    """Individual instalment within a payment plan. US-C05: Automatic WhatsApp reminders on due date."""
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('partial', 'Partially Paid'),
        ('paid', 'Paid'),
        ('overdue', 'Overdue'),
        ('waived', 'Waived'),
    ]

    payment_plan = models.ForeignKey(PaymentPlan, on_delete=models.CASCADE, related_name='instalments')
    instalment_number = models.PositiveSmallIntegerField()
    amount_due = models.DecimalField(max_digits=12, decimal_places=0)
    amount_paid = models.DecimalField(max_digits=12, decimal_places=0, default=0)
    due_date = models.DateField()
    paid_at = models.DateTimeField(null=True, blank=True)
    payment = models.ForeignKey(Payment, on_delete=models.SET_NULL, null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    
    # US-C05: Reminder tracking
    reminder_sent = models.BooleanField(default=False)
    reminder_sent_at = models.DateTimeField(null=True, blank=True)
    reminder_task_id = models.CharField(max_length=100, blank=True,
                                         help_text="Celery task ID for scheduled reminder")

    class Meta:
        db_table = 'payment_plan_instalments'
        unique_together = [('payment_plan', 'instalment_number')]
        ordering = ['instalment_number']


class FeeWaiver(models.Model):
    """US-024: Fee waiver/discount with reason. Director approval required."""
    STATUS_CHOICES = [
        ('pending', 'Pending Approval'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    school = models.ForeignKey('schools.School', on_delete=models.CASCADE)
    fee_record = models.ForeignKey(FeeRecord, on_delete=models.CASCADE, related_name='waivers')
    amount = models.DecimalField(max_digits=12, decimal_places=0)
    reason = models.TextField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    
    # Approver details
    approved_by = models.ForeignKey('authentication.User', on_delete=models.SET_NULL,
                                    null=True, blank=True, related_name='approved_waivers')
    approved_at = models.DateTimeField(null=True, blank=True)
    
    # Rejecter details
    rejection_reason = models.TextField(blank=True)
    rejected_by = models.ForeignKey('authentication.User', on_delete=models.SET_NULL,
                                    null=True, blank=True, related_name='rejected_waivers')
    rejected_at = models.DateTimeField(null=True, blank=True)

    requested_by = models.ForeignKey('authentication.User', on_delete=models.SET_NULL,
                                     null=True, related_name='requested_waivers')
    created_at = models.DateTimeField(auto_now_add=True)

    objects = TenantManager()
    all_objects = models.Manager()

    class Meta:
        db_table = 'fee_waivers'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['school', 'status']),
            models.Index(fields=['school', 'approved_at']),
        ]


class MoMoIPNLog(models.Model):
    """
    US-026/027: Log every raw IPN webhook received.
    US-070: momo_reference_hash stores SHA-256 of the reference for
            idempotency checks so the reference can be encrypted later.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    school = models.ForeignKey('schools.School', on_delete=models.CASCADE)
    provider = models.CharField(max_length=10, choices=[('mtn', 'MTN'), ('airtel', 'Airtel')])
    momo_reference = models.CharField(max_length=100, unique=True)
    momo_reference_hash = models.CharField(
        max_length=64,
        db_index=True,
        blank=True,
        help_text="SHA-256 of momo_reference — used for idempotency lookups"
    )
    phone = models.CharField(max_length=20)
    amount = models.DecimalField(max_digits=12, decimal_places=0)
    raw_payload = models.JSONField()
    signature_valid = models.BooleanField(default=False)
    processed = models.BooleanField(default=False)
    payment = models.ForeignKey(Payment, on_delete=models.SET_NULL, null=True, blank=True)
    error = models.TextField(blank=True)
    received_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'momo_ipn_logs'
        indexes = [
            models.Index(fields=['momo_reference']),
            models.Index(fields=['momo_reference_hash']),
            models.Index(fields=['phone']),
            models.Index(fields=['processed']),
        ]

    def save(self, *args, **kwargs):
        # US-070: always keep hash in sync with the reference
        if self.momo_reference:
            self.momo_reference_hash = hashlib.sha256(
                self.momo_reference.encode()
            ).hexdigest()
        super().save(*args, **kwargs)


class ReconciliationQueue(models.Model):
    """
    US-029: Unmatched MoMo payments waiting for manual assignment.
    Fuzzy phone match suggestions shown to Bursar.
    Alert after 24hr unmatched (US-075), escalate to Director at 48hr.
    """
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('matched', 'Matched'),
        ('ignored', 'Ignored'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    school = models.ForeignKey('schools.School', on_delete=models.CASCADE)
    momo_ipn_log = models.OneToOneField(MoMoIPNLog, on_delete=models.CASCADE)
    momo_reference = models.CharField(max_length=100)
    phone = models.CharField(max_length=20)
    amount = models.DecimalField(max_digits=12, decimal_places=0)
    provider = models.CharField(max_length=10)

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    matched_to_payment = models.ForeignKey(Payment, on_delete=models.SET_NULL,
                                           null=True, blank=True)
    matched_by = models.ForeignKey('authentication.User', on_delete=models.SET_NULL,
                                   null=True, blank=True, related_name='reconciliations_done')
    matched_at = models.DateTimeField(null=True, blank=True)
    ignore_reason = models.TextField(blank=True)

    # Fuzzy match suggestions computed when item enters queue
    suggested_students = models.JSONField(null=True, blank=True,
                                          help_text="List of {student_id, name, phone, score} suggestions")

    alert_24hr_sent = models.BooleanField(default=False)
    alert_48hr_sent = models.BooleanField(default=False)
    received_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)

    objects = TenantManager()
    all_objects = models.Manager()

    class Meta:
        db_table = 'reconciliation_queue'
        ordering = ['-received_at']
        indexes = [
            models.Index(fields=['school', 'status']),
            models.Index(fields=['received_at']),
        ]


class AirtelTokenCache(models.Model):
    """
    US-027: Airtel OAuth token cached in DB + Redis.
    Celery task refreshes every 50 min (TTL=60min).
    """
    school = models.OneToOneField('schools.School', on_delete=models.CASCADE,
                                  related_name='airtel_token')
    access_token = models.TextField()
    expires_at = models.DateTimeField()
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'airtel_token_cache'

    def is_valid(self):
        from django.utils import timezone
        return self.expires_at > timezone.now()


# Epic-C: Smart Fee Collection Intelligence Models
from .escalation_models import ReminderEscalation, ReminderEscalationLog
from .payment_link_models import PaymentLink
from .campaign_models import DefaulterCampaign, DefaulterCampaignTarget
