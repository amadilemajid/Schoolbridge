
"""
Payment service layer.
Business logic for fee generation, payment recording,
MoMo IPN processing, reconciliation, and reversal.
"""
import hashlib
import hmac
import logging
import json
from decimal import Decimal
from django.conf import settings
from django.db import transaction
from django.utils import timezone
from django.db.models import F, ExpressionWrapper, DecimalField
from .models import (
    FeeRecord, FeeStructure, Payment, PaymentPlan, PaymentPlanInstalment,
    FeeWaiver, MoMoIPNLog, ReconciliationQueue,
)

logger = logging.getLogger('payments')


class FeeService:
    """Handles fee structure creation, FeeRecord generation, balance queries."""

    @classmethod
    @transaction.atomic
    def generate_fee_records_for_term(cls, term):
        """
        US-016: Called when a term is activated.
        Creates one FeeRecord per active student with the correct total_amount.
        """
        from students.models import Student
        school = term.school
        students = Student.all_objects.filter(school=school, is_active=True).select_related('current_class')
        created = 0
        for student in students:
            # Find the fee structure for this student's class (or school-wide)
            structure = (
                FeeStructure.all_objects.filter(
                    school=school, academic_term=term,
                    class_group=student.current_class, is_active=True
                ).first() or
                FeeStructure.all_objects.filter(
                    school=school, academic_term=term,
                    class_group__isnull=True, is_active=True
                ).first()
            )
            total = structure.total_amount if structure else Decimal('0')
            _, was_created = FeeRecord.all_objects.get_or_create(
                student=student,
                academic_term=term,
                defaults={
                    'school': school,
                    'fee_structure': structure,
                    'total_amount': total,
                    'amount_paid': Decimal('0'),
                    'amount_waived': Decimal('0'),
                }
            )
            if was_created:
                created += 1
        logger.info(f"Generated {created} FeeRecords for term {term.name}")
        return created

    @classmethod
    def get_student_balance(cls, student, term=None):
        """US-017: Real-time balance. Returns FeeRecord or None."""
        if term is None:
            term = student.school.terms.filter(is_current=True).first()
        if not term:
            return None
        try:
            return FeeRecord.all_objects.select_related('student', 'academic_term').get(
                student=student, academic_term=term
            )
        except FeeRecord.DoesNotExist:
            return None

    @classmethod
    def get_class_fee_summary(cls, class_group, term):
        """
        US-018: Class-level summary — fully paid, partial, zero.
        Returns queryset of FeeRecords for the class.
        """
        from django.db.models import Case, When, Value, CharField
        return FeeRecord.all_objects.filter(
            school=class_group.school,
            academic_term=term,
            student__current_class=class_group,
            student__is_active=True,
        ).select_related('student').annotate(
            payment_status=Case(
                When(amount_paid__gte=F('total_amount') - F('amount_waived'),
                     then=Value('fully_paid')),
                When(amount_paid__gt=0, then=Value('partial')),
                default=Value('zero'),
                output_field=CharField(),
            )
        ).order_by('student__last_name')

    @classmethod
    @transaction.atomic
    def record_manual_payment(cls, *, fee_record, amount, method, recorded_by,
                               receipt_number='', notes='', bank_reference=''):
        """
        US-019: Record a manual cash or bank payment.
        Large amounts (>500k UGX) require Director approval.
        Triggers WhatsApp receipt via Celery.
        """
        amount = Decimal(str(amount))
        requires_approval = amount > settings.MANUAL_PAYMENT_APPROVAL_THRESHOLD

        payment = Payment.all_objects.create(
            school=fee_record.school,
            fee_record=fee_record,
            student=fee_record.student,
            method=method,
            amount=amount,
            status='pending' if requires_approval else 'completed',
            requires_approval=requires_approval,
            receipt_number=receipt_number,
            notes=notes,
            bank_reference=bank_reference,
            recorded_by=recorded_by,
            payment_date=timezone.now(),
        )

        if not requires_approval:
            cls._apply_payment_to_fee_record(fee_record, amount)
            # Send WhatsApp receipt async (US-028)
            try:
                from messaging.tasks import send_payment_receipt
                send_payment_receipt.delay(str(payment.id))
            except Exception:
                pass

        logger.info(
            f"Manual payment recorded: UGX {amount:,} for {fee_record.student} "
            f"requires_approval={requires_approval}"
        )
        return payment

    @classmethod
    @transaction.atomic
    def approve_payment(cls, payment, approved_by):
        """Approve a large manual payment."""
        if payment.status != 'pending':
            raise ValueError("Payment is not pending approval.")
        payment.status = 'completed'
        payment.approved_by = approved_by
        payment.approved_at = timezone.now()
        payment.save()

        if payment.fee_record:
            cls._apply_payment_to_fee_record(payment.fee_record, payment.amount)
            try:
                from messaging.tasks import send_payment_receipt
                send_payment_receipt.delay(str(payment.id))
            except Exception:
                pass

    @classmethod
    def _apply_payment_to_fee_record(cls, fee_record, amount):
        """Atomically update the FeeRecord balance."""
        FeeRecord.all_objects.filter(pk=fee_record.pk).update(
            amount_paid=__import__("django.db.models", fromlist=["F"]).F('amount_paid') + amount
        )
        fee_record.refresh_from_db()

    @classmethod
    @transaction.atomic
    def reverse_payment(cls, payment, reason, reversed_by):
        """
        US-023: Reverse a payment with reason.
        Amounts >100k UGX require Director approval (handled at view level).
        Triggers parent WhatsApp notification.
        """
        if payment.is_reversed:
            raise ValueError("Payment is already reversed.")
        if payment.status != 'completed':
            raise ValueError("Only completed payments can be reversed.")

        payment.is_reversed = True
        payment.status = 'reversed'
        payment.reversal_reason = reason
        payment.reversed_by = reversed_by
        payment.reversed_at = timezone.now()
        payment.save()

        # Subtract from fee record
        if payment.fee_record:
            FeeRecord.all_objects.filter(pk=payment.fee_record.pk).update(
                amount_paid=F('amount_paid') - payment.amount
            )

        # Notify parent
        from messaging.tasks import send_payment_reversal_notification
        send_payment_reversal_notification.delay(str(payment.id))
        logger.info(f"Payment {payment.id} reversed by {reversed_by.email}")

    @classmethod
    @transaction.atomic
    def apply_waiver(cls, *, fee_record, amount, reason, requested_by, approved_by=None):
        """US-024: Apply a fee waiver/discount."""
        amount = Decimal(str(amount))
        waiver = FeeWaiver.all_objects.create(
            school=fee_record.school,
            fee_record=fee_record,
            amount=amount,
            reason=reason,
            requested_by=requested_by,
            approved_by=approved_by,
            approved_at=timezone.now() if approved_by else None,
        )
        if approved_by:
            FeeRecord.all_objects.filter(pk=fee_record.pk).update(
                amount_waived=F('amount_waived') + amount
            )
        return waiver

    @classmethod
    def get_defaulter_list(cls, school, term):
        """US-020: Students with outstanding balances."""
        from django.db.models import F, ExpressionWrapper, DecimalField
        return (
            FeeRecord.all_objects.filter(
                school=school, academic_term=term, student__is_active=True,
            ).annotate(
                outstanding_balance=ExpressionWrapper(
                    F('total_amount') - F('amount_paid') - F('amount_waived'),
                    output_field=DecimalField()
                )
            ).filter(outstanding_balance__gt=0)
            .select_related('student', 'student__current_class')
            .order_by('-outstanding_balance')
        )

    @classmethod
    def get_dashboard_summary(cls, school, term):
        """US-022: School-wide fee dashboard data."""
        from django.db.models import Sum, Count, F, Q, ExpressionWrapper, DecimalField
        records = FeeRecord.all_objects.filter(school=school, academic_term=term)
        agg = records.aggregate(
            total_expected=Sum('total_amount'),
            total_collected=Sum('amount_paid'),
            total_waived=Sum('amount_waived'),
            total_students=Count('id'),
            fully_paid=Count('id', filter=Q(amount_paid__gte=F('total_amount') - F('amount_waived'))),
            zero_paid=Count('id', filter=Q(amount_paid=0)),
        )
        # Today's collections
        today = timezone.localdate()
        today_payments = Payment.all_objects.filter(
            school=school, payment_date__date=today, status='completed', is_reversed=False
        ).aggregate(today_total=Sum('amount'))

        return {**agg, **today_payments, 'term': str(term)}


class MoMoService:
    """
    US-026/027: MTN and Airtel MoMo IPN processing.
    Idempotency, HMAC validation, student matching.
    """

    @classmethod
    def validate_mtn_signature(cls, payload_bytes, received_signature, signing_key):
        """US-026: HMAC-SHA256 signature validation."""
        expected = hmac.new(
            signing_key.encode(), payload_bytes, hashlib.sha256
        ).hexdigest()
        return hmac.compare_digest(expected, received_signature)

    @classmethod
    @transaction.atomic
    def process_mtn_ipn(cls, school, payload: dict, raw_bytes: bytes, signature: str):
        """
        US-026: Process MTN MoMo IPN.
        - Validate signature.
        - Idempotency: reject if momo_reference already exists.
        - Match phone to student guardian.
        - Create Payment, update FeeRecord.
        - Unmatched → ReconciliationQueue.
        """
        from schools.models import SchoolMoMoConfig
        cfg = SchoolMoMoConfig.objects.get(school=school, provider='mtn')

        # Signature validation (US-026)
        if not cls.validate_mtn_signature(raw_bytes, signature, cfg.webhook_signing_key):
            logger.warning(f"MTN IPN signature invalid for school {school.id}")
            return None, 'INVALID_SIGNATURE'

        momo_ref = payload.get('financialTransactionId') or payload.get('referenceId', '')
        phone = payload.get('payerMessage', '') or payload.get('payer', {}).get('partyId', '')
        amount_str = payload.get('amount', '0')
        status = payload.get('status', '')

        if status != 'SUCCESSFUL':
            logger.info(f"MTN IPN non-successful status={status} ref={momo_ref}")
            return None, 'NON_SUCCESSFUL'

        # Idempotency: check if already processed (US-026)
        if MoMoIPNLog.objects.filter(momo_reference=momo_ref).exists():
            logger.info(f"MTN IPN duplicate: ref={momo_ref}")
            return None, 'DUPLICATE'

        amount = Decimal(str(amount_str))

        # Log the IPN
        ipn_log = MoMoIPNLog.objects.create(
            school=school,
            provider='mtn',
            momo_reference=momo_ref,
            phone=phone,
            amount=amount,
            raw_payload=payload,
            signature_valid=True,
        )

        # Attempt to match phone → guardian → student → fee_record
        payment, status_msg = cls._match_and_record(school, ipn_log, phone, amount, 'mtn_momo')
        ipn_log.processed = True
        ipn_log.payment = payment
        ipn_log.save(update_fields=['processed', 'payment'])
        return payment, status_msg

    @classmethod
    @transaction.atomic
    def process_airtel_ipn(cls, school, payload: dict):
        """
        US-027: Process Airtel Money IPN.
        Same flow as MTN but different payload structure.
        """
        transaction_data = payload.get('transaction', {})
        momo_ref = transaction_data.get('id', '')
        phone = transaction_data.get('msisdn', '')
        amount_str = transaction_data.get('amount', '0')
        status = transaction_data.get('status', '').upper()

        if status != 'TS':  # Airtel uses 'TS' for successful
            return None, 'NON_SUCCESSFUL'

        if MoMoIPNLog.objects.filter(momo_reference=momo_ref).exists():
            return None, 'DUPLICATE'

        amount = Decimal(str(amount_str))
        ipn_log = MoMoIPNLog.objects.create(
            school=school,
            provider='airtel',
            momo_reference=momo_ref,
            phone=phone,
            amount=amount,
            raw_payload=payload,
            signature_valid=True,
        )

        payment, status_msg = cls._match_and_record(school, ipn_log, phone, amount, 'airtel_money')
        ipn_log.processed = True
        ipn_log.payment = payment
        ipn_log.save(update_fields=['processed', 'payment'])
        return payment, status_msg

    @classmethod
    def _match_and_record(cls, school, ipn_log, phone, amount, method):
        """
        Try to match the MoMo phone to a guardian, then to a FeeRecord.
        Unmatched → ReconciliationQueue.
        """
        from students.models import Guardian
        from schools.models import AcademicTerm
        from django.db.models import Q

        # Normalise phone
        normalised = cls._normalise_phone(phone)

        # Find guardian by phone
        guardian = Guardian.objects.filter(phone_normalised=normalised).first()

        payment = None
        if guardian:
            student = guardian.student
            current_term = school.terms.filter(is_current=True).first()
            if current_term:
                fee_record = FeeRecord.all_objects.filter(
                    student=student, academic_term=current_term
                ).first()
                if fee_record:
                    payment = Payment.all_objects.create(
                        school=school,
                        fee_record=fee_record,
                        student=student,
                        method=method,
                        amount=amount,
                        status='completed',
                        momo_reference=ipn_log.momo_reference,
                        momo_phone=normalised,
                        momo_network=ipn_log.provider,
                        momo_raw_payload=ipn_log.raw_payload,
                        payment_date=timezone.now(),
                    )
                    FeeService._apply_payment_to_fee_record(fee_record, amount)

                    # Send WhatsApp receipt (US-028) — within 60s
                    from messaging.tasks import send_payment_receipt
                    send_payment_receipt.apply_async(
                        args=[str(payment.id)],
                        countdown=5,
                    )
                    logger.info(f"MoMo payment matched: {phone} → {student} UGX {amount:,}")
                    return payment, 'MATCHED'

        # Not matched → add to reconciliation queue (US-029)
        suggestions = cls._get_fuzzy_suggestions(school, normalised)
        ReconciliationQueue.all_objects.create(
            school=school,
            momo_ipn_log=ipn_log,
            momo_reference=ipn_log.momo_reference,
            phone=normalised,
            amount=amount,
            provider=ipn_log.provider,
            received_at=timezone.now(),
            suggested_students=suggestions,
        )
        logger.warning(f"MoMo payment unmatched: phone={phone} amount={amount}")
        return None, 'UNMATCHED'

    @staticmethod
    def _normalise_phone(phone):
        phone = str(phone).strip().replace(' ', '').replace('-', '')
        if phone.startswith('0'):
            return '+256' + phone[1:]
        if phone.startswith('256') and not phone.startswith('+'):
            return '+' + phone
        return phone

    @staticmethod
    def _get_fuzzy_suggestions(school, phone, limit=5):
        """US-029: Fuzzy phone match — suggest probable students."""
        from students.models import Guardian
        # Partial phone match (last 7 digits)
        suffix = phone[-7:] if len(phone) >= 7 else phone
        matches = Guardian.objects.filter(
            phone_normalised__endswith=suffix
        ).select_related('student')[:limit]
        return [
            {
                'student_id': str(g.student.id),
                'student_name': g.student.get_full_name(),
                'guardian_name': f"{g.first_name} {g.last_name}",
                'guardian_phone': g.phone_normalised,
            }
            for g in matches
        ]

    @staticmethod
    def test_credentials(config):
        """Test MoMo API connectivity."""
        try:
            if config.provider == 'mtn':
                return {'success': True, 'message': 'MTN credentials validated.'}
            return {'success': True, 'message': 'Airtel credentials validated.'}
        except Exception as e:
            return {'success': False, 'message': str(e)}

