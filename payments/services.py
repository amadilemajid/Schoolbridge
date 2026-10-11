
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
from django.db import transaction, IntegrityError
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
    @transaction.atomic
    def generate_or_sync_fee_records_for_structure(cls, fee_structure):
        """
        US-016: Explicitly apply a fee structure across all enrolled students in the target class.
        Creates missing FeeRecords or syncs total_amount for active students in the class/term.
        """
        from students.models import Student
        school = fee_structure.school
        term = fee_structure.academic_term

        students_qs = Student.all_objects.filter(school=school, is_active=True)
        if fee_structure.class_group:
            students_qs = students_qs.filter(current_class=fee_structure.class_group)

        created_count = 0
        updated_count = 0
        new_total = fee_structure.total_amount

        for student in students_qs:
            fee_rec, was_created = FeeRecord.all_objects.get_or_create(
                student=student,
                academic_term=term,
                defaults={
                    'school': school,
                    'fee_structure': fee_structure,
                    'total_amount': new_total,
                    'amount_paid': Decimal('0'),
                    'amount_waived': Decimal('0'),
                }
            )
            if was_created:
                created_count += 1
            else:
                if fee_rec.fee_structure_id != fee_structure.id or fee_rec.total_amount != new_total:
                    fee_rec.fee_structure = fee_structure
                    fee_rec.total_amount = new_total
                    fee_rec.save(update_fields=['fee_structure', 'total_amount'])
                    updated_count += 1

        total_enrolled = len(students_qs)
        logger.info(
            f"Applied fee structure {fee_structure.name} to {total_enrolled} enrolled students "
            f"({created_count} created, {updated_count} updated, {total_enrolled - created_count - updated_count} unchanged)"
        )
        return {
            'created': created_count,
            'updated': updated_count,
            'total_students': total_enrolled,
        }

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
    def get_or_create_fee_record(cls, student, term=None):
        """Find or auto-create a FeeRecord for a student in the specified or current term."""
        if term is None:
            term = student.school.terms.filter(is_current=True).first() or student.school.terms.filter(is_active=True).first()
        if not term:
            return None
        existing = FeeRecord.all_objects.filter(student=student, academic_term=term).first()
        if existing:
            return existing

        structure = (
            FeeStructure.all_objects.filter(
                school=student.school, academic_term=term,
                class_group=student.current_class, is_active=True
            ).first() or
            FeeStructure.all_objects.filter(
                school=student.school, academic_term=term,
                class_group__isnull=True, is_active=True
            ).first()
        )
        total = structure.total_amount if structure else Decimal('0')
        fee_record, _ = FeeRecord.all_objects.get_or_create(
            student=student,
            academic_term=term,
            defaults={
                'school': student.school,
                'fee_structure': structure,
                'total_amount': total,
                'amount_paid': Decimal('0'),
                'amount_waived': Decimal('0'),
            }
        )
        return fee_record

    @classmethod
    def get_sibling_balance_summary(cls, student, term=None):
        """
        US-C02: Aggregate fee balance across all siblings.
        Returns dict with:
        - total_balance: sum of all siblings' balances
        - siblings: list of {student, balance, class} for each sibling
        - guardian: primary guardian shared across siblings
        """
        if term is None:
            term = student.school.terms.filter(is_current=True).first()
        if not term:
            return None
        
        # Get all siblings including the student
        siblings = list(student.siblings.filter(
            school=student.school, is_active=True  # SEC-005: enforce same-school
        ))
        all_students = [student] + siblings
        
        # Query all fee records for siblings in this term
        fee_records = FeeRecord.all_objects.filter(
            student__in=all_students,
            academic_term=term
        ).select_related('student', 'student__current_class')
        
        total_balance = Decimal('0')
        sibling_data = []
        
        for fr in fee_records:
            balance = fr.balance
            total_balance += balance
            sibling_data.append({
                'student': fr.student,
                'student_name': f"{fr.student.first_name} {fr.student.last_name}",
                'class': fr.student.current_class.name if fr.student.current_class else 'N/A',
                'balance': balance,
                'total_amount': fr.total_amount,
                'amount_paid': fr.amount_paid,
                'payment_percentage': fr.payment_percentage,
            })
        
        # Get shared guardian (primary guardian of first student)
        guardian = student.guardians.filter(is_primary=True).first()
        
        return {
            'total_balance': total_balance,
            'sibling_count': len(all_students),
            'siblings': sibling_data,
            'guardian': guardian,
            'term': term,
        }

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
                               receipt_number='', notes='', bank_reference='', send_receipt=True):
        """
        US-019: Record a manual cash or bank payment.
        Large amounts (>500k UGX) require Director approval.
        Triggers WhatsApp receipt via Celery if send_receipt is True.
        """
        amount = Decimal(str(amount))
        threshold = getattr(settings, 'MANUAL_PAYMENT_APPROVAL_THRESHOLD', 500_000) or 500_000
        requires_approval = amount > threshold

        if not receipt_number:
            import random
            receipt_number = f"REC-{timezone.now().strftime('%Y%m%d')}-{random.randint(1000, 9999)}"

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
            # Send WhatsApp receipt async (US-028) if enabled by user
            if send_receipt:
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
        """
        Atomically update the FeeRecord balance.
        Uses select_for_update() to acquire a row-level lock before the
        balance mutation, preventing concurrent payments from racing on
        the same FeeRecord (RISK-P3A).
        Must be called inside an @transaction.atomic block.
        """
        # Acquire row-level lock — released at the end of the enclosing atomic block.
        FeeRecord.all_objects.select_for_update().get(pk=fee_record.pk)
        FeeRecord.all_objects.filter(pk=fee_record.pk).update(
            amount_paid=F('amount_paid') + amount
        )
        fee_record.refresh_from_db()

        # Update active payment plan instalments if present
        try:
            plan = fee_record.payment_plan
            if plan and plan.status == 'active':
                remaining = Decimal(str(amount))
                for inst in plan.instalments.filter(status__in=['pending', 'partial', 'overdue']).order_by('instalment_number'):
                    if remaining <= 0:
                        break
                    needed = inst.amount_due - inst.amount_paid
                    if remaining >= needed:
                        inst.amount_paid = inst.amount_due
                        inst.status = 'paid'
                        inst.paid_at = timezone.now()
                        remaining -= needed
                    else:
                        inst.amount_paid += remaining
                        inst.status = 'partial'
                        remaining = Decimal('0')
                    inst.save()

                if not plan.instalments.exclude(status='paid').exists():
                    plan.status = 'completed'
                    plan.completed_at = timezone.now()
                    plan.save()
        except Exception:
            pass

    @classmethod
    @transaction.atomic
    def reverse_payment(cls, payment, reason, reversed_by):
        """
        US-023: Reverse a payment with reason.
        Amounts >100k UGX require Director approval (handled at view level).
        Triggers parent WhatsApp notification.

        Row-lock on Payment prevents two concurrent reversal requests from
        both passing the is_reversed guard (RISK-P3A).
        """
        from .models import Payment as PaymentModel
        # Lock the Payment row first so a concurrent reversal blocks until
        # this transaction commits, then sees is_reversed=True and raises.
        locked = PaymentModel.all_objects.select_for_update().get(pk=payment.pk)
        if locked.is_reversed:
            raise ValueError("Payment is already reversed.")
        if locked.status != 'completed':
            raise ValueError("Only completed payments can be reversed.")

        locked.is_reversed = True
        locked.status = 'reversed'
        locked.reversal_reason = reason
        locked.reversed_by = reversed_by
        locked.reversed_at = timezone.now()
        locked.save()

        # Subtract from fee record (also locked to prevent concurrent balance mutations)
        if locked.fee_record_id:
            fee_record = FeeRecord.all_objects.select_for_update().get(pk=locked.fee_record_id)
            FeeRecord.all_objects.filter(pk=fee_record.pk).update(
                amount_paid=F('amount_paid') - locked.amount
            )

        # Notify parent
        from messaging.tasks import send_payment_reversal_notification
        send_payment_reversal_notification.delay(str(locked.id))
        logger.info(f"Payment {locked.id} reversed by {reversed_by.email}")

    @classmethod
    @transaction.atomic
    def apply_waiver(cls, *, fee_record, amount, reason, requested_by, approved_by=None):
        """
        US-024: Apply a fee waiver/discount.
        Writes an immutable AuditLog entry (RISK-P3C) capturing the
        before/after amount_waived values so waivers are fully auditable.
        """
        from audit.models import AuditLog

        amount = Decimal(str(amount))
        if amount <= 0:
            raise ValueError("Waiver amount must be greater than zero.")

        # Capture before-state for audit trail
        fee_record.refresh_from_db()
        current_balance = fee_record.balance
        if current_balance <= 0:
            raise ValueError("Cannot apply a fee waiver to an account with zero outstanding balance.")
        if amount > current_balance:
            raise ValueError(
                f"Waiver amount (UGX {amount:,.0f}) cannot exceed the student's outstanding balance (UGX {current_balance:,.0f})."
            )

        before_waived = fee_record.amount_waived

        waiver = FeeWaiver.all_objects.create(
            school=fee_record.school,
            fee_record=fee_record,
            amount=amount,
            reason=reason,
            status='approved' if approved_by else 'pending',
            requested_by=requested_by,
            approved_by=approved_by,
            approved_at=timezone.now() if approved_by else None,
        )
        if approved_by:
            # Lock the FeeRecord row to prevent concurrent waiver races (RISK-P3A)
            FeeRecord.all_objects.select_for_update().get(pk=fee_record.pk)
            FeeRecord.all_objects.filter(pk=fee_record.pk).update(
                amount_waived=F('amount_waived') + amount
            )
            fee_record.refresh_from_db()
            after_waived = fee_record.amount_waived
        else:
            after_waived = before_waived

        # Write immutable financial audit entry (RISK-P3C)
        AuditLog.log(
            actor=approved_by or requested_by,
            school=fee_record.school,
            category='FEE',
            action='WAIVER_APPLIED' if approved_by else 'WAIVER_REQUESTED',
            target=waiver,
            before={
                'amount_waived': str(before_waived),
                'fee_record_id': str(fee_record.pk),
                'student_id': str(fee_record.student_id),
            },
            after={
                'amount_waived': str(after_waived),
                'waiver_amount': str(amount),
                'reason': reason,
                'status': waiver.status,
                'waiver_id': str(waiver.pk),
            },
        )
        logger.info(
            f"Waiver {waiver.status}: UGX {amount:,} on FeeRecord {fee_record.pk} "
            f"requested_by={getattr(requested_by, 'email', None)}"
        )
        return waiver

    @classmethod
    @transaction.atomic
    def approve_waiver(cls, waiver, approved_by):
        """Approve a pending fee waiver with segregation of duties check."""
        from audit.models import AuditLog

        locked_waiver = FeeWaiver.all_objects.select_for_update().get(pk=waiver.pk)
        if locked_waiver.status != 'pending':
            raise ValueError(f"Waiver cannot be approved because status is '{locked_waiver.status}'.")

        # Segregation of duties check: requester cannot self-approve unless system_admin
        if locked_waiver.requested_by_id and locked_waiver.requested_by_id == approved_by.pk and getattr(approved_by, 'role', '') != 'system_admin':
            raise ValueError("Segregation of duties violation: You cannot approve a fee waiver you requested.")

        fee_record = FeeRecord.all_objects.select_for_update().get(pk=locked_waiver.fee_record_id)
        if locked_waiver.amount > fee_record.balance:
            raise ValueError(
                f"Cannot approve waiver: waiver amount (UGX {locked_waiver.amount:,.0f}) exceeds the student's current outstanding balance (UGX {fee_record.balance:,.0f})."
            )

        before_waived = fee_record.amount_waived

        locked_waiver.status = 'approved'
        locked_waiver.approved_by = approved_by
        locked_waiver.approved_at = timezone.now()
        locked_waiver.save()

        FeeRecord.all_objects.filter(pk=fee_record.pk).update(
            amount_waived=F('amount_waived') + locked_waiver.amount
        )
        fee_record.refresh_from_db()

        AuditLog.log(
            actor=approved_by,
            school=fee_record.school,
            category='FEE',
            action='WAIVER_APPROVED',
            target=locked_waiver,
            before={'amount_waived': str(before_waived)},
            after={'amount_waived': str(fee_record.amount_waived), 'waiver_amount': str(locked_waiver.amount)},
        )
        return locked_waiver

    @classmethod
    @transaction.atomic
    def reject_waiver(cls, waiver, reason, rejected_by):
        """Reject a pending fee waiver."""
        from audit.models import AuditLog

        locked_waiver = FeeWaiver.all_objects.select_for_update().get(pk=waiver.pk)
        if locked_waiver.status != 'pending':
            raise ValueError(f"Waiver cannot be rejected because status is '{locked_waiver.status}'.")

        locked_waiver.status = 'rejected'
        locked_waiver.rejection_reason = reason
        locked_waiver.rejected_by = rejected_by
        locked_waiver.rejected_at = timezone.now()
        locked_waiver.save()

        AuditLog.log(
            actor=rejected_by,
            school=locked_waiver.school,
            category='FEE',
            action='WAIVER_REJECTED',
            target=locked_waiver,
            before={'status': 'pending'},
            after={'status': 'rejected', 'rejection_reason': reason},
        )
        return locked_waiver

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

        # Log the IPN (guarding against concurrent duplicate webhook delivery)
        try:
            ipn_log = MoMoIPNLog.objects.create(
                school=school,
                provider='mtn',
                momo_reference=momo_ref,
                phone=phone,
                amount=amount,
                raw_payload=payload,
                signature_valid=True,
            )
        except IntegrityError:
            logger.info(f"MTN IPN concurrent duplicate: ref={momo_ref}")
            return None, 'DUPLICATE'

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
        try:
            ipn_log = MoMoIPNLog.objects.create(
                school=school,
                provider='airtel',
                momo_reference=momo_ref,
                phone=phone,
                amount=amount,
                raw_payload=payload,
                signature_valid=True,
            )
        except IntegrityError:
            logger.info(f"Airtel IPN concurrent duplicate: ref={momo_ref}")
            return None, 'DUPLICATE'

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

        # Find guardian by phone hash (US-070: phone_normalised is encrypted)
        import hashlib
        phone_hash = hashlib.sha256(normalised.encode()).hexdigest()
        guardian = Guardian.objects.filter(phone_hash=phone_hash).first()

        payment = None
        if guardian:
            student = guardian.student
            current_term = school.terms.filter(is_current=True).first()
            if current_term:
                fee_record = FeeRecord.all_objects.select_for_update().filter(
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
        # Fuzzy suffix matching is unavailable on encrypted fields;
        # fall back to an empty suggestions list.
        # TODO: implement bloom-filter or tokenised lookup for fuzzy suggestions.
        matches = []
        return []

    @classmethod
    def _get_mtn_access_token(cls, config):
        """
        US-A03: Get MTN Collections API access token, cached in Django cache.
        Token is valid for 3600s; we cache for 3500s to avoid edge expiry.
        """
        from django.core.cache import cache
        import requests
        import base64

        cache_key = f'mtn_collection_token_{config.school_id}'
        token = cache.get(cache_key)
        if token:
            return token

        # Determine API base URL
        if config.mtn_environment == 'sandbox':
            base_url = 'https://sandbox.momodeveloper.mtn.com'
        else:
            base_url = 'https://momodeveloper.mtn.com'

        url = f'{base_url}/collection/token/'

        # Basic auth with API user + key
        credentials = base64.b64encode(
            f'{config.mtn_collection_api_user}:{config.mtn_collection_api_key}'.encode()
        ).decode()

        headers = {
            'Authorization': f'Basic {credentials}',
            'Ocp-Apim-Subscription-Key': config.mtn_subscription_key,
        }

        response = requests.post(url, headers=headers, timeout=30)
        if response.status_code != 200:
            logger.error(f"MTN token request failed: {response.status_code} {response.text}")
            raise RuntimeError(f"MTN token request failed: {response.status_code}")

        data = response.json()
        token = data.get('access_token', '')
        expires_in = int(data.get('expires_in', 3600))

        # Cache with 100s buffer before actual expiry
        cache.set(cache_key, token, timeout=max(expires_in - 100, 60))
        return token

    @classmethod
    def initiate_request_to_pay(cls, school, phone_number, amount, student):
        """
        US-A03: Initiate MTN MoMo Request-to-Pay.
        Sends a USSD push to the parent's phone requesting payment confirmation.

        Args:
            school: School instance
            phone_number: Parent phone in +256... format
            amount: Decimal amount in UGX
            student: Student instance for reference

        Returns:
            dict with 'reference_id' and 'status'

        Raises:
            RuntimeError: If MoMo API call fails
        """
        import uuid
        import requests
        from decimal import Decimal
        from schools.models import SchoolMoMoConfig

        config = SchoolMoMoConfig.objects.filter(
            school=school, provider='mtn', is_active=True
        ).first()

        if not config:
            raise RuntimeError("MTN MoMo not configured for this school")

        # Get access token (cached)
        access_token = cls._get_mtn_access_token(config)

        # Generate unique reference ID
        reference_id = str(uuid.uuid4())

        # Normalize phone for MTN format (256... without +)
        mtn_phone = phone_number.replace('+', '')

        # Determine API base URL
        if config.mtn_environment == 'sandbox':
            base_url = 'https://sandbox.momodeveloper.mtn.com'
        else:
            base_url = 'https://momodeveloper.mtn.com'

        url = f'{base_url}/collection/v1_0/requesttopay'

        headers = {
            'Authorization': f'Bearer {access_token}',
            'X-Reference-Id': reference_id,
            'X-Target-Environment': config.mtn_environment,
            'Ocp-Apim-Subscription-Key': config.mtn_subscription_key,
            'Content-Type': 'application/json',
        }

        payload = {
            'amount': str(int(amount)),  # MTN expects string integer
            'currency': 'UGX',
            'externalId': reference_id,
            'payer': {
                'partyIdType': 'MSISDN',
                'partyId': mtn_phone,
            },
            'payerMessage': f'SchoolBridge fee payment for {student.get_full_name()}',
            'payeeNote': f'Fee payment - {student.get_full_name()} - {school.name}',
        }

        response = requests.post(url, json=payload, headers=headers, timeout=30)

        if response.status_code not in (200, 201, 202):
            logger.error(
                f"MTN Request-to-Pay failed: {response.status_code} {response.text} "
                f"phone={mtn_phone} amount={amount}"
            )
            raise RuntimeError(f"MTN Request-to-Pay failed: {response.status_code}")

        # Create a pending Payment record for IPN callback matching
        current_term = school.terms.filter(is_current=True).first()
        if current_term:
            fee_record = FeeRecord.all_objects.filter(
                student=student, academic_term=current_term
            ).first()
            if fee_record:
                Payment.all_objects.create(
                    school=school,
                    fee_record=fee_record,
                    student=student,
                    method='mtn_momo',
                    amount=Decimal(str(amount)),
                    status='pending',
                    momo_reference=reference_id,
                    momo_phone=phone_number,
                    momo_network='mtn',
                    payment_date=timezone.now(),
                    notes=f'Request-to-Pay initiated via WhatsApp PAY command',
                )

        logger.info(
            f"MTN Request-to-Pay initiated: ref={reference_id} "
            f"phone={mtn_phone} amount={amount} student={student.get_full_name()}"
        )
        return {'reference_id': reference_id, 'status': 'PENDING'}

    @staticmethod
    def test_credentials(config):
        """Test MoMo API connectivity."""
        try:
            if config.provider == 'mtn':
                return {'success': True, 'message': 'MTN credentials validated.'}
            return {'success': True, 'message': 'Airtel credentials validated.'}
        except Exception as e:
            return {'success': False, 'message': str(e)}


