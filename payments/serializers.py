"""
Payments serializers — full validation for all payment-related data.
"""
from decimal import Decimal
from django.db import transaction
from rest_framework import serializers
from django.conf import settings
from .models import (
    FeeStructure, FeeStructureItem, FeeRecord, Payment,
    PaymentPlan, PaymentPlanInstalment, FeeWaiver, ReconciliationQueue,
    PaymentLink,
)


class FeeStructureItemSerializer(serializers.ModelSerializer):
    amount = serializers.DecimalField(max_digits=12, decimal_places=2, coerce_to_string=True)

    class Meta:
        model = FeeStructureItem
        fields = ['id', 'name', 'amount', 'is_mandatory', 'description']

    def validate_amount(self, value):
        from decimal import Decimal, ROUND_HALF_UP
        if value <= 0:
            raise serializers.ValidationError("Amount must be greater than 0.")
        return value.quantize(Decimal('1'), rounding=ROUND_HALF_UP)


class FeeStructureSerializer(serializers.ModelSerializer):
    items = FeeStructureItemSerializer(many=True)
    total_amount = serializers.DecimalField(max_digits=12, decimal_places=0, read_only=True)
    class_name = serializers.CharField(source='class_group.name', read_only=True, allow_null=True)
    term_name = serializers.CharField(source='academic_term.name', read_only=True, allow_null=True)

    class Meta:
        model = FeeStructure
        fields = [
            'id', 'academic_term', 'class_group', 'class_name', 'term_name',
            'name', 'is_active', 'items', 'total_amount', 'requires_approval',
            'approved_by', 'approved_at', 'created_at',
        ]
        read_only_fields = ['id', 'requires_approval', 'approved_by', 'approved_at', 'created_at']

    def validate_items(self, value):
        if not value:
            raise serializers.ValidationError("At least one fee item is required.")
        for item in value:
            if item.get('amount', 0) <= 0:
                raise serializers.ValidationError(f"Amount for '{item.get('name')}' must be > 0.")
        return value

    @transaction.atomic
    def create(self, validated_data):
        items_data = validated_data.pop('items')
        fee_structure = FeeStructure.all_objects.create(**validated_data)
        for item in items_data:
            FeeStructureItem.objects.create(fee_structure=fee_structure, **item)
        return fee_structure

    @transaction.atomic
    def update(self, instance, validated_data):
        items_data = validated_data.pop('items', None)
        # If term is already active, flag as needing Director approval (US-016)
        if instance.academic_term.is_active:
            validated_data['requires_approval'] = True
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        if items_data is not None:
            instance.items.all().delete()
            for item in items_data:
                FeeStructureItem.objects.create(fee_structure=instance, **item)
        return instance


class FeeRecordSerializer(serializers.ModelSerializer):
    student_name = serializers.CharField(source='student.get_full_name', read_only=True)
    student_id_code = serializers.CharField(source='student.student_id', read_only=True)
    class_name = serializers.CharField(source='student.current_class.name', read_only=True)
    balance = serializers.DecimalField(max_digits=12, decimal_places=0, read_only=True)
    is_fully_paid = serializers.BooleanField(read_only=True)
    payment_percentage = serializers.IntegerField(read_only=True)
    # Human-readable term info for the frontend (reconciliation modal uses term_label / academic_year)
    term_label = serializers.SerializerMethodField()
    academic_year = serializers.SerializerMethodField()
    has_payment_plan = serializers.SerializerMethodField()
    payment_plan_installments = serializers.SerializerMethodField()
    has_pending_waiver = serializers.SerializerMethodField()
    pending_waiver_amount = serializers.SerializerMethodField()
    pending_waiver_id = serializers.SerializerMethodField()
    pending_waiver_reason = serializers.SerializerMethodField()
    has_pending_payment = serializers.SerializerMethodField()
    pending_payment_amount = serializers.SerializerMethodField()
    pending_payment_id = serializers.SerializerMethodField()
    last_payment_date = serializers.SerializerMethodField()
    clearance_date = serializers.SerializerMethodField()
    escalation_level = serializers.SerializerMethodField()

    class Meta:
        model = FeeRecord
        fields = [
            'id', 'student', 'student_name', 'student_id_code', 'class_name',
            'academic_term', 'term_label', 'academic_year',
            'total_amount', 'amount_paid', 'amount_waived',
            'balance', 'is_fully_paid', 'payment_percentage',
            'has_payment_plan', 'payment_plan_installments',
            'has_pending_waiver', 'pending_waiver_amount', 'pending_waiver_id', 'pending_waiver_reason',
            'has_pending_payment', 'pending_payment_amount', 'pending_payment_id',
            'last_payment_date', 'clearance_date', 'escalation_level',
            'updated_at',
        ]
        read_only_fields = fields

    def get_term_label(self, obj):
        try:
            term = obj.academic_term
            if term:
                return str(term)
        except Exception:
            pass
        return None

    def get_academic_year(self, obj):
        try:
            term = obj.academic_term
            if term and hasattr(term, 'academic_year'):
                return str(term.academic_year)
            if term and hasattr(term, 'year'):
                return str(term.year)
        except Exception:
            pass
        return None

    def get_has_payment_plan(self, obj):
        try:
            return hasattr(obj, 'payment_plan') and obj.payment_plan is not None and obj.payment_plan.status == 'active'
        except Exception:
            return False

    def get_payment_plan_installments(self, obj):
        try:
            if hasattr(obj, 'payment_plan') and obj.payment_plan is not None:
                return obj.payment_plan.instalments.count()
        except Exception:
            pass
        return 0

    def get_has_pending_waiver(self, obj):
        try:
            return obj.waivers.filter(status='pending').exists()
        except Exception:
            return False

    def get_pending_waiver_amount(self, obj):
        try:
            w = obj.waivers.filter(status='pending').first()
            return w.amount if w else 0
        except Exception:
            return 0

    def get_pending_waiver_id(self, obj):
        try:
            w = obj.waivers.filter(status='pending').first()
            return str(w.id) if w else None
        except Exception:
            return None

    def get_pending_waiver_reason(self, obj):
        try:
            w = obj.waivers.filter(status='pending').first()
            return w.reason if w else ''
        except Exception:
            return ''

    def get_has_pending_payment(self, obj):
        try:
            return obj.payments.filter(status='pending', requires_approval=True).exists()
        except Exception:
            return False

    def get_pending_payment_amount(self, obj):
        try:
            p = obj.payments.filter(status='pending', requires_approval=True).first()
            return p.amount if p else 0
        except Exception:
            return 0

    def get_pending_payment_id(self, obj):
        try:
            p = obj.payments.filter(status='pending', requires_approval=True).first()
            return str(p.id) if p else None
        except Exception:
            return None

    def get_last_payment_date(self, obj):
        try:
            last_p = obj.payments.filter(status='completed', is_reversed=False).order_by('-payment_date').first()
            if last_p and last_p.payment_date:
                return last_p.payment_date.strftime('%d %b %Y')
        except Exception:
            pass
        return None

    def get_clearance_date(self, obj):
        try:
            if obj.is_fully_paid or (obj.balance is not None and obj.balance <= 0):
                last_p = obj.payments.filter(status='completed', is_reversed=False).order_by('-payment_date').first()
                if last_p and last_p.payment_date:
                    return last_p.payment_date.strftime('%d %b %Y')
                last_w = obj.waivers.filter(status='approved').order_by('-approved_at').first()
                if last_w and last_w.approved_at:
                    return last_w.approved_at.strftime('%d %b %Y')
                if obj.updated_at:
                    return obj.updated_at.strftime('%d %b %Y')
        except Exception:
            pass
        return None

    def get_escalation_level(self, obj):
        try:
            if obj.is_fully_paid or (obj.balance is not None and obj.balance <= 0):
                return 0

            # 1. Check explicitly scheduled or sent ReminderEscalations for this fee record
            esc = obj.escalations.filter(status__in=['sent', 'scheduled']).order_by('-level').first()
            if esc and esc.level:
                return esc.level

            # 2. Dynamic timeline calculation based on academic term fee_deadline
            term = obj.academic_term
            if term and term.fee_deadline:
                from django.utils import timezone
                today = timezone.localdate()
                days_diff = (term.fee_deadline - today).days

                if days_diff <= 1:
                    return 5
                elif days_diff <= 3:
                    return 4
                elif days_diff <= 7:
                    return 3
                elif days_diff <= 14:
                    return 2
                elif days_diff <= 21:
                    return 1
        except Exception:
            pass
        return 0


class PaymentSerializer(serializers.ModelSerializer):
    student_name = serializers.CharField(source='student.get_full_name', read_only=True)
    student_id_code = serializers.CharField(source='student.student_id', read_only=True)
    class_name = serializers.CharField(source='student.current_class.name', read_only=True)
    recorded_by_name = serializers.CharField(source='recorded_by.get_full_name', read_only=True)
    payer_name = serializers.SerializerMethodField()

    class Meta:
        model = Payment
        fields = [
            'id', 'student', 'student_name', 'student_id_code', 'class_name',
            'fee_record', 'method', 'amount',
            'status', 'momo_reference', 'momo_phone', 'momo_network',
            'receipt_number', 'notes', 'payer_name', 'bank_reference',
            'requires_approval', 'approved_by', 'approved_at',
            'is_reversed', 'reversal_reason', 'reversed_at',
            'recorded_by', 'recorded_by_name', 'payment_date', 'created_at',
        ]
        read_only_fields = [
            'id', 'status', 'momo_reference', 'momo_phone', 'momo_network',
            'requires_approval', 'approved_by', 'approved_at',
            'is_reversed', 'reversed_at', 'created_at',
        ]

    def get_payer_name(self, obj):
        if not obj.notes:
            return ''
        if 'Payer:' in obj.notes:
            import re
            m = re.search(r'Payer:\s*([^|\n]+)', obj.notes, re.IGNORECASE)
            if m:
                return m.group(1).strip()
        return obj.notes.strip()


class PaymentCreateSerializer(serializers.Serializer):
    """For creating a manual payment."""
    fee_record_id = serializers.CharField(required=False, allow_blank=True)
    fee_record = serializers.CharField(required=False, allow_blank=True)
    amount = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal('1'))
    method = serializers.ChoiceField(choices=['cash', 'bank', 'mtn_momo', 'airtel_money', 'momo'], default='cash')
    receipt_number = serializers.CharField(required=False, allow_blank=True, default='')
    payer_name = serializers.CharField(required=False, allow_blank=True, default='')
    notes = serializers.CharField(required=False, allow_blank=True, default='')
    bank_reference = serializers.CharField(required=False, allow_blank=True, default='')
    send_receipt = serializers.BooleanField(required=False, default=True)

    def validate_amount(self, value):
        if value <= 0:
            raise serializers.ValidationError("Amount must be greater than 0.")
        return int(round(value))

    def validate(self, data):
        fid = data.get('fee_record_id') or data.get('fee_record')
        if not fid:
            raise serializers.ValidationError({'fee_record_id': 'Fee record ID is required.'})
        data['fee_record_id'] = fid
        return data


class FeeReversalSerializer(serializers.Serializer):
    reason = serializers.CharField(min_length=10,
        error_messages={'min_length': 'Reversal reason must be at least 10 characters.'})


class PaymentPlanInstalmentSerializer(serializers.ModelSerializer):
    amount = serializers.DecimalField(source='amount_due', max_digits=12, decimal_places=0, min_value=Decimal('1'))
    paid_date = serializers.DateTimeField(source='paid_at', read_only=True)
    instalment_number = serializers.IntegerField(required=False)

    class Meta:
        model = PaymentPlanInstalment
        fields = ['id', 'instalment_number', 'amount', 'due_date', 'paid_date', 'status']
        read_only_fields = ['id', 'paid_date', 'status']


class PaymentPlanSerializer(serializers.ModelSerializer):
    instalments = PaymentPlanInstalmentSerializer(many=True)

    class Meta:
        model = PaymentPlan
        fields = [
            'id', 'fee_record', 'total_amount', 'status',
            'notes', 'instalments', 'created_at',
        ]
        read_only_fields = ['id', 'status', 'created_at']

    def validate_instalments(self, value):
        from django.utils import timezone
        if not (2 <= len(value) <= 4):
            raise serializers.ValidationError("Payment plan must have between 2 and 4 instalments.")

        today = timezone.now().date()
        for idx, item in enumerate(value, start=1):
            amt = item.get('amount_due')
            if amt is None or amt <= 0:
                raise serializers.ValidationError(f"Instalment #{idx} amount must be greater than UGX 0.")
            
            due_date = item.get('due_date')
            if not due_date:
                raise serializers.ValidationError(f"Instalment #{idx} must have a valid due date.")
            if due_date < today:
                raise serializers.ValidationError(f"Instalment #{idx} due date ({due_date}) cannot be in the past.")

        # Validate date sequence (chronological order)
        for i in range(1, len(value)):
            prev_date = value[i - 1].get('due_date')
            curr_date = value[i].get('due_date')
            if prev_date and curr_date and curr_date <= prev_date:
                raise serializers.ValidationError(
                    f"Instalment #{i + 1} due date ({curr_date}) must be strictly after Instalment #{i} due date ({prev_date})."
                )

        return value

    def validate(self, data):
        fee_record = data.get('fee_record')
        total = data.get('total_amount', 0)
        
        if total <= 0:
            raise serializers.ValidationError({'total_amount': 'Plan total amount must be greater than UGX 0.'})

        # Validate against fee record balance
        if fee_record:
            if fee_record.balance <= 0:
                raise serializers.ValidationError({'fee_record': 'This student account is already fully cleared. No payment plan can be created.'})
            if total > fee_record.balance:
                raise serializers.ValidationError({
                    'total_amount': f'Plan total amount (UGX {total:,}) cannot exceed the outstanding balance (UGX {fee_record.balance:,}).'
                })

        # Validate duplicate active plan
        if self.instance is None and fee_record:
            existing = PaymentPlan.all_objects.filter(fee_record=fee_record, status='active').first()
            if existing:
                raise serializers.ValidationError({
                    'fee_record': 'An active payment plan already exists for this fee record. Please complete or cancel the existing plan before creating a new one.'
                })

        instalments = data.get('instalments', [])
        instalment_sum = sum(i.get('amount_due', 0) for i in instalments)
        if abs(instalment_sum - total) > 1:  # Allow 1 UGX rounding difference
            raise serializers.ValidationError(
                f"Sum of instalment amounts (UGX {instalment_sum:,}) must equal the total planned balance (UGX {total:,})."
            )
        return data

    def create(self, validated_data):
        from django.db import transaction
        instalments_data = validated_data.pop('instalments')
        if 'student' not in validated_data and 'fee_record' in validated_data:
            validated_data['student'] = validated_data['fee_record'].student
        with transaction.atomic():
            # Delete or supersede any old completed/cancelled plan if creating a new active one
            PaymentPlan.all_objects.filter(fee_record=validated_data['fee_record'], status__in=['completed', 'cancelled']).delete()
            plan = PaymentPlan.all_objects.create(**validated_data)
            for i, inst in enumerate(instalments_data, start=1):
                inst_number = inst.pop('instalment_number', None) or i
                PaymentPlanInstalment.objects.create(
                    payment_plan=plan,
                    instalment_number=inst_number,
                    **inst,
                )
        return plan


class FeeWaiverSerializer(serializers.ModelSerializer):
    fee_record_id = serializers.CharField(write_only=True)
    amount = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal('1'))
    student_name = serializers.CharField(source='fee_record.student.get_full_name', read_only=True)
    student_id_code = serializers.CharField(source='fee_record.student.student_id', read_only=True)
    requested_by_name = serializers.CharField(source='requested_by.get_full_name', read_only=True)
    approved_by_name = serializers.CharField(source='approved_by.get_full_name', read_only=True)
    rejected_by_name = serializers.CharField(source='rejected_by.get_full_name', read_only=True)

    class Meta:
        model = FeeWaiver
        fields = [
            'id', 'fee_record_id', 'fee_record', 'student_name', 'student_id_code',
            'amount', 'reason', 'status',
            'requested_by', 'requested_by_name',
            'approved_by', 'approved_by_name', 'approved_at',
            'rejection_reason', 'rejected_by', 'rejected_by_name', 'rejected_at',
            'created_at',
        ]
        read_only_fields = [
            'id', 'fee_record', 'status', 'requested_by', 'approved_by',
            'approved_at', 'rejection_reason', 'rejected_by', 'rejected_at', 'created_at',
        ]

    def validate_amount(self, value):
        if value <= 0:
            raise serializers.ValidationError("Waiver amount must be greater than 0.")
        return int(round(value))


class FeeWaiverRejectSerializer(serializers.Serializer):
    reason = serializers.CharField(
        min_length=5,
        error_messages={'min_length': 'Rejection reason must be at least 5 characters.'}
    )


class ReconciliationIgnoreSerializer(serializers.Serializer):
    reason = serializers.CharField(
        min_length=5,
        error_messages={'min_length': 'Reason for ignoring payment must be at least 5 characters.'}
    )


class ReconciliationQueueSerializer(serializers.ModelSerializer):
    transaction_reference = serializers.CharField(source='momo_reference', read_only=True)
    matched_by_name = serializers.SerializerMethodField()
    matched_student_name = serializers.SerializerMethodField()
    matched_student_id_code = serializers.SerializerMethodField()
    matched_student_class = serializers.SerializerMethodField()
    receipt_number = serializers.SerializerMethodField()
    academic_term = serializers.SerializerMethodField()
    narration = serializers.SerializerMethodField()

    class Meta:
        model = ReconciliationQueue
        fields = [
            'id', 'momo_reference', 'transaction_reference', 'phone', 'amount', 'provider',
            'status', 'ignore_reason', 'suggested_students', 'received_at',
            'matched_at', 'matched_by', 'matched_by_name', 'matched_student_name',
            'matched_student_id_code', 'matched_student_class', 'receipt_number',
            'academic_term', 'alert_24hr_sent', 'alert_48hr_sent', 'narration',
        ]
        read_only_fields = fields

    def get_matched_by_name(self, obj):
        if obj.matched_by:
            return f"{obj.matched_by.first_name} {obj.matched_by.last_name}".strip()
        return None

    def get_matched_student_name(self, obj):
        if obj.matched_to_payment and obj.matched_to_payment.student:
            s = obj.matched_to_payment.student
            return f"{s.first_name} {s.last_name}".strip()
        return None

    def get_matched_student_id_code(self, obj):
        if obj.matched_to_payment and obj.matched_to_payment.student:
            return obj.matched_to_payment.student.student_id
        return None

    def get_matched_student_class(self, obj):
        if obj.matched_to_payment and obj.matched_to_payment.student:
            s = obj.matched_to_payment.student
            if s.current_class:
                return s.current_class.name
        return None

    def get_receipt_number(self, obj):
        if obj.matched_to_payment and obj.matched_to_payment.receipt_number:
            return obj.matched_to_payment.receipt_number
        return obj.momo_reference

    def get_academic_term(self, obj):
        if obj.matched_to_payment and obj.matched_to_payment.fee_record:
            fr = obj.matched_to_payment.fee_record
            if fr.academic_term:
                return fr.academic_term.name
        return None

    def get_narration(self, obj):
        """
        Extract payer-supplied note from the raw MoMo IPN payload.
        Handles both normalised keys ('narration') and common statement column
        variations ('narrative', 'note', 'description', etc.) case-insensitively.
        """
        try:
            payload = obj.momo_ipn_log.raw_payload or {}
            # Exact key lookup first
            for key in ('narration', 'narrative', 'note', 'description', 'reason',
                        'payment_reason', 'message', 'remarks', 'annotation',
                        'Narration', 'Narrative', 'Note', 'Description', 'Reason',
                        'Message', 'Remarks', 'PaymentReason'):
                val = payload.get(key)
                if val and isinstance(val, str) and val.strip():
                    return val.strip()
            # Case-insensitive / substring match across all payload keys
            for k, v in payload.items():
                if isinstance(v, str) and v.strip() and any(x in k.lower() for x in ('narrat', 'desc', 'note', 'reason', 'remark', 'message')):
                    return v.strip()
        except Exception:
            pass
        return None



class GeneratePaymentLinkSerializer(serializers.Serializer):
    student_id = serializers.CharField(required=False, allow_blank=True)
    fee_record_id = serializers.CharField(required=False, allow_blank=True)
    amount = serializers.DecimalField(max_digits=12, decimal_places=0, required=False, allow_null=True)
    description = serializers.CharField(max_length=200, required=False, default='Term Fee Payment Link')
    expiry_hours = serializers.IntegerField(required=False, default=72)


class PaymentLinkSerializer(serializers.ModelSerializer):
    student_name = serializers.CharField(source='student.get_full_name', read_only=True)
    student_code = serializers.CharField(source='student.student_id', read_only=True)
    payment_url = serializers.CharField(source='full_url', read_only=True)

    class Meta:
        model = PaymentLink
        fields = [
            'id', 'token', 'amount', 'description', 'status', 'expires_at',
            'accessed_count', 'payment', 'used_at', 'recipient_phone',
            'recipient_name', 'student', 'student_name', 'student_code',
            'fee_record', 'payment_url', 'created_at',
        ]
        read_only_fields = fields

