"""
Phase 3 Remediation Tests -- Financial Safety
=============================================
Covers:
  RISK-P3A  select_for_update row lock in _apply_payment_to_fee_record
  RISK-P3A  select_for_update row lock in reverse_payment
  RISK-P3B  select_for_update in ReconciliationQueueViewSet.match
  RISK-P3C  AuditLog entry written by apply_waiver
"""
import pytest
from decimal import Decimal
from datetime import date
from unittest.mock import patch, MagicMock

from django.db import connection
from django.utils import timezone


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def financial_setup(db):
    """Create a complete financial hierarchy for payment tests."""
    from schools.models import School, AcademicYear, AcademicTerm
    from students.models import Student, ClassGroup
    from payments.models import FeeStructure, FeeStructureItem, FeeRecord

    school = School.objects.create(
        name='P3 Test School', slug='p3-test-school', district='Kampala',
        sub_county='Central', phone='+256700000777', email='p3@school.ug',
        school_type='primary', is_active=True
    )
    year = AcademicYear.objects.create(school=school, year=2026, is_current=True)
    term = AcademicTerm.objects.create(
        school=school, academic_year=year, term_number=1,
        name='P3 Term 1 2026', start_date=date(2026, 1, 6),
        end_date=date(2026, 4, 4), fee_deadline=date(2026, 1, 20),
        is_current=True, is_active=False
    )
    cg = ClassGroup.all_objects.create(school=school, name='P3.1', level='P1')

    structure = FeeStructure.objects.create(
        school=school, academic_term=term, class_group=cg,
        name='P3 Fee Structure', is_active=True,
        created_by=None
    )
    FeeStructureItem.objects.create(
        fee_structure=structure, name='Tuition',
        amount=Decimal('300000'), is_mandatory=True
    )

    student = Student.all_objects.create(
        school=school, student_id='P3-STU-001', first_name='Alice',
        last_name='Test', gender='F', current_class=cg,
        admission_date=date(2026, 1, 6), academic_year_admitted=2026,
        is_active=True
    )

    fee_record = FeeRecord.all_objects.create(
        school=school, student=student, academic_term=term,
        fee_structure=structure,
        total_amount=Decimal('300000'),
        amount_paid=Decimal('0'),
        amount_waived=Decimal('0'),
    )

    from authentication.models import User
    bursar = User.objects.create_user(
        email='p3-bursar@school.ug', password='testpass123',
        role='bursar', school=school, is_active=True
    )
    director = User.objects.create_user(
        email='p3-director@school.ug', password='testpass123',
        role='director', school=school, is_active=True
    )

    return {
        'school': school, 'term': term, 'cg': cg,
        'student': student, 'fee_record': fee_record,
        'bursar': bursar, 'director': director,
    }


# ---------------------------------------------------------------------------
# RISK-P3A: _apply_payment_to_fee_record uses select_for_update
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestApplyPaymentRowLock:

    def test_single_payment_credits_correctly(self, financial_setup):
        """A single payment correctly increments amount_paid."""
        from payments.services import FeeService
        from payments.models import FeeRecord
        from django.db import transaction

        fr = financial_setup['fee_record']
        with transaction.atomic():
            FeeService._apply_payment_to_fee_record(fr, Decimal('100000'))

        fr.refresh_from_db()
        assert fr.amount_paid == Decimal('100000')

    def test_select_for_update_is_called(self, financial_setup):
        """_apply_payment_to_fee_record must call select_for_update() on FeeRecord."""
        from payments.services import FeeService
        from payments.models import FeeRecord
        from django.db import transaction

        fr = financial_setup['fee_record']
        original_sfu = FeeRecord.all_objects.select_for_update

        called = []
        def tracking_sfu(*args, **kwargs):
            called.append(True)
            return original_sfu(*args, **kwargs)

        with transaction.atomic(), \
             patch.object(FeeRecord.all_objects, 'select_for_update', side_effect=tracking_sfu):
            FeeService._apply_payment_to_fee_record(fr, Decimal('50000'))

        assert called, "select_for_update() was not called in _apply_payment_to_fee_record"

    def test_two_sequential_payments_accumulate_correctly(self, financial_setup):
        """Two sequential payments sum correctly (no F()-expression corruption)."""
        from payments.services import FeeService
        from django.db import transaction

        fr = financial_setup['fee_record']
        with transaction.atomic():
            FeeService._apply_payment_to_fee_record(fr, Decimal('100000'))
        fr.refresh_from_db()
        with transaction.atomic():
            FeeService._apply_payment_to_fee_record(fr, Decimal('80000'))
        fr.refresh_from_db()

        assert fr.amount_paid == Decimal('180000')


# ---------------------------------------------------------------------------
# RISK-P3A: reverse_payment uses select_for_update
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestReversePaymentRowLock:

    def _make_payment(self, financial_setup, amount=Decimal('150000')):
        from payments.models import Payment
        from payments.services import FeeService
        from django.db import transaction

        fr = financial_setup['fee_record']
        with transaction.atomic():
            FeeService._apply_payment_to_fee_record(fr, amount)

        payment = Payment.all_objects.create(
            school=financial_setup['school'],
            fee_record=fr,
            student=financial_setup['student'],
            method='cash',
            amount=amount,
            status='completed',
            recorded_by=financial_setup['bursar'],
            payment_date=timezone.now(),
        )
        return payment, fr

    def test_reversal_decrements_fee_record(self, financial_setup):
        """A reversed payment subtracts its amount from amount_paid."""
        from payments.services import FeeService

        payment, fr = self._make_payment(financial_setup)
        with patch('messaging.tasks.send_payment_reversal_notification.delay'):
            FeeService.reverse_payment(payment, reason='Test reversal', reversed_by=financial_setup['director'])

        fr.refresh_from_db()
        assert fr.amount_paid == Decimal('0')

    def test_double_reversal_raises_value_error(self, financial_setup):
        """Calling reverse_payment twice on the same payment must raise ValueError."""
        from payments.services import FeeService

        payment, fr = self._make_payment(financial_setup)
        with patch('messaging.tasks.send_payment_reversal_notification.delay'):
            FeeService.reverse_payment(payment, reason='First reversal', reversed_by=financial_setup['director'])

        with pytest.raises(ValueError, match='already reversed'):
            with patch('messaging.tasks.send_payment_reversal_notification.delay'):
                FeeService.reverse_payment(payment, reason='Second reversal', reversed_by=financial_setup['director'])

    def test_select_for_update_called_in_reverse_payment(self, financial_setup):
        """reverse_payment must lock the Payment row via select_for_update()."""
        from payments.services import FeeService
        from payments.models import Payment

        payment, _ = self._make_payment(financial_setup)
        called = []
        original_sfu = Payment.all_objects.select_for_update

        def tracking_sfu(*args, **kwargs):
            called.append(True)
            return original_sfu(*args, **kwargs)

        with patch('messaging.tasks.send_payment_reversal_notification.delay'), \
             patch.object(Payment.all_objects, 'select_for_update', side_effect=tracking_sfu):
            FeeService.reverse_payment(payment, 'check', reversed_by=financial_setup['director'])

        assert called, "select_for_update() was not called in reverse_payment"


# ---------------------------------------------------------------------------
# RISK-P3B: ReconciliationQueue.match uses select_for_update
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestReconciliationMatchLock:

    def _make_queue_item(self, financial_setup):
        from payments.models import MoMoIPNLog, ReconciliationQueue

        school = financial_setup['school']
        ipn = MoMoIPNLog.objects.create(
            school=school,
            provider='mtn',
            momo_reference=f'TEST-REF-{timezone.now().timestamp()}',
            phone='+256770000001',
            amount=Decimal('150000'),
            raw_payload={'test': True},
            signature_valid=True,
            processed=False,
        )
        item = ReconciliationQueue.all_objects.create(
            school=school,
            momo_ipn_log=ipn,
            momo_reference=ipn.momo_reference,
            phone=ipn.phone,
            amount=ipn.amount,
            provider='mtn',
            received_at=timezone.now(),
            status='pending',
        )
        return item

    def test_match_applies_payment_and_marks_matched(self, financial_setup):
        """A valid match request creates a Payment and marks the queue item matched."""
        from payments.models import Payment, ReconciliationQueue
        from rest_framework.test import APIClient

        item = self._make_queue_item(financial_setup)
        fr = financial_setup['fee_record']
        client = APIClient()
        client.force_authenticate(user=financial_setup['bursar'])

        resp = client.post(
            f'/api/v1/payments/reconciliation/{item.pk}/match/',
            {'fee_record_id': str(fr.pk)},
            format='json',
        )
        assert resp.status_code == 200, resp.data

        item.refresh_from_db()
        assert item.status == 'matched'
        assert Payment.all_objects.filter(momo_reference=item.momo_reference).count() == 1

    def test_already_matched_item_returns_400(self, financial_setup):
        """Attempting to match an already-matched queue item returns 400."""
        from rest_framework.test import APIClient

        item = self._make_queue_item(financial_setup)
        fr = financial_setup['fee_record']
        client = APIClient()
        client.force_authenticate(user=financial_setup['bursar'])

        # First match
        client.post(
            f'/api/v1/payments/reconciliation/{item.pk}/match/',
            {'fee_record_id': str(fr.pk)},
            format='json',
        )
        # Second match attempt
        resp = client.post(
            f'/api/v1/payments/reconciliation/{item.pk}/match/',
            {'fee_record_id': str(fr.pk)},
            format='json',
        )
        assert resp.status_code == 400

    def test_select_for_update_called_in_match(self, financial_setup):
        """ReconciliationQueueViewSet.match must call select_for_update()."""
        from payments.models import ReconciliationQueue
        from rest_framework.test import APIClient

        item = self._make_queue_item(financial_setup)
        fr = financial_setup['fee_record']
        called = []
        original_sfu = ReconciliationQueue.objects.select_for_update

        def tracking_sfu(*args, **kwargs):
            called.append(True)
            return original_sfu(*args, **kwargs)

        client = APIClient()
        client.force_authenticate(user=financial_setup['bursar'])
        with patch.object(ReconciliationQueue.objects, 'select_for_update', side_effect=tracking_sfu):
            client.post(
                f'/api/v1/payments/reconciliation/{item.pk}/match/',
                {'fee_record_id': str(fr.pk)},
                format='json',
            )

        assert called, "select_for_update() was not called in ReconciliationQueueViewSet.match"


# ---------------------------------------------------------------------------
# RISK-P3C: apply_waiver writes an AuditLog entry
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestWaiverAuditLog:

    def test_waiver_creates_audit_log_entry(self, financial_setup):
        """apply_waiver must create an AuditLog entry with WAIVER_APPLIED action."""
        from payments.services import FeeService
        from audit.models import AuditLog

        fr = financial_setup['fee_record']
        before_count = AuditLog.objects.filter(action='WAIVER_APPLIED').count()

        FeeService.apply_waiver(
            fee_record=fr,
            amount=Decimal('50000'),
            reason='Scholarship',
            requested_by=financial_setup['bursar'],
            approved_by=financial_setup['director'],
        )

        after_count = AuditLog.objects.filter(action='WAIVER_APPLIED').count()
        assert after_count == before_count + 1

    def test_waiver_audit_log_has_before_after_data(self, financial_setup):
        """The AuditLog entry must contain before/after amount_waived values."""
        from payments.services import FeeService
        from audit.models import AuditLog

        fr = financial_setup['fee_record']
        FeeService.apply_waiver(
            fee_record=fr,
            amount=Decimal('75000'),
            reason='Hardship',
            requested_by=financial_setup['bursar'],
            approved_by=financial_setup['director'],
        )

        entry = AuditLog.objects.filter(action='WAIVER_APPLIED').latest('created_at')
        assert entry.before_data is not None
        assert entry.after_data is not None
        assert entry.before_data['amount_waived'] == '0'
        assert entry.after_data['waiver_amount'] == '75000'
        assert entry.after_data['approved'] is True

    def test_waiver_increments_amount_waived_correctly(self, financial_setup):
        """Approved waiver must update FeeRecord.amount_waived correctly."""
        from payments.services import FeeService

        fr = financial_setup['fee_record']
        FeeService.apply_waiver(
            fee_record=fr,
            amount=Decimal('50000'),
            reason='First waiver',
            requested_by=financial_setup['bursar'],
            approved_by=financial_setup['director'],
        )
        FeeService.apply_waiver(
            fee_record=fr,
            amount=Decimal('30000'),
            reason='Second waiver',
            requested_by=financial_setup['bursar'],
            approved_by=financial_setup['director'],
        )

        fr.refresh_from_db()
        assert fr.amount_waived == Decimal('80000')

    def test_unapproved_waiver_does_not_update_balance(self, financial_setup):
        """Unapproved waiver creates a FeeWaiver record but must NOT update amount_waived."""
        from payments.services import FeeService

        fr = financial_setup['fee_record']
        FeeService.apply_waiver(
            fee_record=fr,
            amount=Decimal('50000'),
            reason='Pending approval',
            requested_by=financial_setup['bursar'],
            approved_by=None,
        )

        fr.refresh_from_db()
        assert fr.amount_waived == Decimal('0')

    def test_waiver_audit_log_has_correct_category(self, financial_setup):
        """AuditLog entry must be categorised as FEE."""
        from payments.services import FeeService
        from audit.models import AuditLog

        fr = financial_setup['fee_record']
        FeeService.apply_waiver(
            fee_record=fr,
            amount=Decimal('20000'),
            reason='Category check',
            requested_by=financial_setup['bursar'],
            approved_by=financial_setup['director'],
        )

        entry = AuditLog.objects.filter(action='WAIVER_APPLIED').latest('created_at')
        assert entry.category == 'FEE'
