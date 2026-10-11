"""
Payment flow tests — the most critical test suite.
Tests: MoMo IPN idempotency, fee balance update, receipt dispatch,
       payment reversal, reconciliation matching, rate limits.
"""
import json
import hashlib
import hmac
from decimal import Decimal
from unittest.mock import patch, MagicMock
from django.test import TestCase, Client, override_settings
from django.contrib.auth import get_user_model
from schools.models import School, AcademicTerm, AcademicYear, SchoolMoMoConfig
from students.models import Student, Guardian, ClassGroup
from payments.models import FeeStructure, FeeRecord, Payment, ReconciliationQueue, MoMoIPNLog
from payments.services import FeeService, MoMoService
import uuid
from django.utils import timezone

User = get_user_model()


def make_school(name="Test School"):
    school = School.objects.create(
        name=name, slug=name.lower().replace(' ', '-'),
        district='Kampala', phone='+256701234567',
        email='test@school.ug', school_type='primary',
    )
    return school


def make_term(school):
    year = AcademicYear.objects.create(school=school, year=2024, is_current=True)
    return AcademicTerm.objects.create(
        school=school, academic_year=year, term_number=1,
        name='Term 1 2024', start_date='2024-02-05',
        end_date='2024-05-31', fee_deadline='2024-03-15',
        is_current=True, is_active=True,
    )


class FeeServiceTest(TestCase):
    def setUp(self):
        self.school = make_school()
        self.term = make_term(self.school)
        self.class_group = ClassGroup.all_objects.create(
            school=self.school, name='P.7', level='P7'
        )
        self.student = Student.all_objects.create(
            school=self.school, student_id='SCH-2024-0001',
            first_name='John', last_name='Mukasa',
            gender='M', admission_date='2024-02-05',
            academic_year_admitted=2024, current_class=self.class_group,
        )
        self.guardian = Guardian.objects.create(
            student=self.student, first_name='Sarah', last_name='Mukasa',
            relationship='Mother', phone='0701234567',
            phone_normalised='+256701234567', is_primary=True,
        )
        self.fee_structure = FeeStructure.all_objects.create(
            school=self.school, academic_term=self.term,
            name='P7 Fees', created_by=None,
        )
        from payments.models import FeeStructureItem
        FeeStructureItem.objects.create(
            fee_structure=self.fee_structure,
            name='Tuition', amount=Decimal('300000'), is_mandatory=True,
        )
        self.fee_record = FeeRecord.all_objects.create(
            school=self.school, student=self.student,
            academic_term=self.term, fee_structure=self.fee_structure,
            total_amount=Decimal('300000'), amount_paid=Decimal('0'),
        )

    def test_fee_balance_correct(self):
        """Balance = total - paid - waived."""
        self.assertEqual(self.fee_record.balance, Decimal('300000'))
        self.assertFalse(self.fee_record.is_fully_paid)

    def test_manual_payment_updates_balance(self):
        """Recording a payment reduces balance."""
        director = User.objects.create_user(
            email='director@school.ug', password='pass', role='director',
            school=self.school, first_name='Dir', last_name='Ector',
        )
        with patch('messaging.tasks.send_payment_receipt.delay'):
            payment = FeeService.record_manual_payment(
                fee_record=self.fee_record,
                amount=Decimal('150000'),
                method='cash',
                recorded_by=director,
            )
        self.fee_record.refresh_from_db()
        self.assertEqual(self.fee_record.amount_paid, Decimal('150000'))
        self.assertEqual(self.fee_record.balance, Decimal('150000'))
        self.assertEqual(payment.status, 'completed')

    @override_settings(MANUAL_PAYMENT_APPROVAL_THRESHOLD=500_000)
    def test_payment_above_threshold_requires_approval(self):
        """Payments > 500k UGX require Director approval."""
        director = User.objects.create_user(
            email='dir2@school.ug', password='pass', role='director',
            school=self.school, first_name='Dir', last_name='Two',
        )
        with patch('messaging.tasks.send_payment_receipt.delay'):
            payment = FeeService.record_manual_payment(
                fee_record=self.fee_record,
                amount=Decimal('600000'),
                method='bank',
                recorded_by=director,
            )
        self.assertEqual(payment.status, 'pending')
        self.assertTrue(payment.requires_approval)
        # Balance should NOT be updated until approved
        self.fee_record.refresh_from_db()
        self.assertEqual(self.fee_record.amount_paid, Decimal('0'))

    def test_payment_on_cleared_account_rejected_by_api(self):
        """Payments against a cleared account (balance=0) are rejected with 400 Bad Request."""
        from rest_framework.test import APIRequestFactory, force_authenticate
        from payments.views import PaymentViewSet

        # Fully clear the fee record
        self.fee_record.amount_paid = Decimal('300000')
        self.fee_record.save()
        self.assertEqual(self.fee_record.balance, Decimal('0'))

        bursar = User.objects.create_user(
            email='bursar_clear@school.ug', password='pass', role='bursar',
            school=self.school, first_name='Bursar', last_name='Clear',
        )

        factory = APIRequestFactory()
        req = factory.post('/api/v1/payments/payments/', {
            'fee_record_id': str(self.fee_record.id),
            'amount': 50000,
            'method': 'cash',
        }, format='json')
        force_authenticate(req, user=bursar)
        view = PaymentViewSet.as_view({'post': 'create'})
        res = view(req)

        self.assertEqual(res.status_code, 400)
        self.assertIn('Actions for CLEARED accounts are locked', str(res.data))

    def test_full_payment_marks_paid(self):
        """After full payment, is_fully_paid = True."""
        director = User.objects.create_user(
            email='dir3@school.ug', password='pass', role='director',
            school=self.school, first_name='Dir', last_name='Three',
        )
        with patch('messaging.tasks.send_payment_receipt.delay'):
            FeeService.record_manual_payment(
                fee_record=self.fee_record,
                amount=Decimal('300000'),
                method='cash',
                recorded_by=director,
            )
        self.fee_record.refresh_from_db()
        self.assertTrue(self.fee_record.is_fully_paid)

    def test_payment_reversal(self):
        """Reversing a payment restores the balance."""
        director = User.objects.create_user(
            email='dir4@school.ug', password='pass', role='director',
            school=self.school, first_name='Dir', last_name='Four',
        )
        with patch('messaging.tasks.send_payment_receipt.delay'):
            payment = FeeService.record_manual_payment(
                fee_record=self.fee_record, amount=Decimal('100000'),
                method='cash', recorded_by=director,
            )
        self.fee_record.refresh_from_db()
        self.assertEqual(self.fee_record.amount_paid, Decimal('100000'))

        with patch('messaging.tasks.send_payment_reversal_notification.delay'):
            FeeService.reverse_payment(payment, "Test reversal", director)

        self.fee_record.refresh_from_db()
        self.assertEqual(self.fee_record.amount_paid, Decimal('0'))
        payment.refresh_from_db()
        self.assertTrue(payment.is_reversed)


class MoMoIPNTest(TestCase):
    def setUp(self):
        self.school = make_school("MoMo School")
        self.term = make_term(self.school)
        self.class_group = ClassGroup.all_objects.create(
            school=self.school, name='S.4', level='S4'
        )
        self.student = Student.all_objects.create(
            school=self.school, student_id='SCH-2024-0002',
            first_name='Alice', last_name='Nakato',
            gender='F', admission_date='2024-02-05',
            academic_year_admitted=2024, current_class=self.class_group,
        )
        self.guardian = Guardian.objects.create(
            student=self.student, first_name='Bob', last_name='Nakato',
            relationship='Father', phone='0712345678',
            phone_normalised='+256712345678', is_primary=True,
        )
        self.fee_record = FeeRecord.all_objects.create(
            school=self.school, student=self.student,
            academic_term=self.term, total_amount=Decimal('500000'),
            amount_paid=Decimal('0'),
        )
        self.momo_config = SchoolMoMoConfig.objects.create(
            school=self.school, provider='mtn',
            merchant_name='MoMo School', merchant_phone='+256700000000',
            webhook_signing_key='test_signing_key_abc123',
        )

    def _make_mtn_payload(self, reference, phone='+256712345678', amount='200000'):
        return {
            'financialTransactionId': reference,
            'payer': {'partyId': phone},
            'amount': amount,
            'currency': 'UGX',
            'status': 'SUCCESSFUL',
        }

    def _make_signature(self, payload_bytes, key='test_signing_key_abc123'):
        return hmac.new(key.encode(), payload_bytes, hashlib.sha256).hexdigest()

    def test_mtn_ipn_matched_and_applied(self):
        """Valid MoMo IPN matched to student and balance updated."""
        ref = 'TXN' + str(uuid.uuid4())[:8].upper()
        payload = self._make_mtn_payload(ref)
        payload_bytes = json.dumps(payload).encode()
        sig = self._make_signature(payload_bytes)

        with patch('messaging.tasks.send_payment_receipt.apply_async'):
            payment, status_msg = MoMoService.process_mtn_ipn(
                school=self.school, payload=payload,
                raw_bytes=payload_bytes, signature=sig,
            )

        self.assertEqual(status_msg, 'MATCHED')
        self.assertIsNotNone(payment)
        self.fee_record.refresh_from_db()
        self.assertEqual(self.fee_record.amount_paid, Decimal('200000'))

    def test_mtn_ipn_duplicate_rejected(self):
        """Duplicate IPN with same reference is rejected (idempotency)."""
        ref = 'TXN' + str(uuid.uuid4())[:8].upper()
        payload = self._make_mtn_payload(ref)
        payload_bytes = json.dumps(payload).encode()
        sig = self._make_signature(payload_bytes)

        with patch('messaging.tasks.send_payment_receipt.apply_async'):
            MoMoService.process_mtn_ipn(self.school, payload, payload_bytes, sig)
            payment2, status2 = MoMoService.process_mtn_ipn(self.school, payload, payload_bytes, sig)

        self.assertEqual(status2, 'DUPLICATE')
        self.assertIsNone(payment2)
        # Balance only updated once
        self.fee_record.refresh_from_db()
        self.assertEqual(self.fee_record.amount_paid, Decimal('200000'))

    def test_mtn_ipn_invalid_signature_rejected(self):
        """IPN with invalid HMAC signature is rejected with 401."""
        ref = 'TXN' + str(uuid.uuid4())[:8].upper()
        payload = self._make_mtn_payload(ref)
        payload_bytes = json.dumps(payload).encode()

        payment, status_msg = MoMoService.process_mtn_ipn(
            self.school, payload, payload_bytes, 'invalid_signature'
        )

        self.assertEqual(status_msg, 'INVALID_SIGNATURE')
        self.assertIsNone(payment)

    def test_unmatched_momo_goes_to_reconciliation_queue(self):
        """MoMo from unknown phone goes to reconciliation queue."""
        ref = 'TXN' + str(uuid.uuid4())[:8].upper()
        payload = self._make_mtn_payload(ref, phone='+256799999999')
        payload_bytes = json.dumps(payload).encode()
        sig = self._make_signature(payload_bytes)

        payment, status_msg = MoMoService.process_mtn_ipn(
            self.school, payload, payload_bytes, sig
        )

        self.assertEqual(status_msg, 'UNMATCHED')
        self.assertIsNone(payment)
        self.assertTrue(
            ReconciliationQueue.all_objects.filter(
                school=self.school, momo_reference=ref
            ).exists()
        )


class MultiTenantIsolationTest(TestCase):
    """
    US-001: Critical — schools MUST NOT see each other's data.
    """
    def setUp(self):
        self.school_a = make_school("School Alpha")
        self.school_b = make_school("School Beta")
        self.term_a = make_term(self.school_a)
        self.class_a = ClassGroup.all_objects.create(
            school=self.school_a, name='P7', level='P7'
        )
        self.student_a = Student.all_objects.create(
            school=self.school_a, student_id='A-001',
            first_name='Student', last_name='Alpha',
            gender='M', admission_date='2024-02-05',
            academic_year_admitted=2024, current_class=self.class_a,
        )
        self.user_a = User.objects.create_user(
            email='director@schoolalpha.ug', password='pass',
            role='director', school=self.school_a,
            first_name='Dir', last_name='Alpha',
        )

    def test_tenant_manager_isolates_students(self):
        """TenantManager only returns students for the current school."""
        from schools.middleware import set_current_school, clear_current_school
        set_current_school(self.school_a)
        try:
            students = Student.objects.all()
            for s in students:
                self.assertEqual(s.school_id, self.school_a.id,
                                 "Student from another school appeared in query!")
        finally:
            clear_current_school()

    def test_no_cross_school_fee_records(self):
        """FeeRecords from school_b never appear in school_a queries."""
        from schools.middleware import set_current_school, clear_current_school
        term_b = make_term(self.school_b)
        class_b = ClassGroup.all_objects.create(
            school=self.school_b, name='P7', level='P7'
        )
        student_b = Student.all_objects.create(
            school=self.school_b, student_id='B-001',
            first_name='Student', last_name='Beta',
            gender='F', admission_date='2024-02-05',
            academic_year_admitted=2024, current_class=class_b,
        )
        FeeRecord.all_objects.create(
            school=self.school_b, student=student_b,
            academic_term=term_b, total_amount=Decimal('200000'),
        )

        set_current_school(self.school_a)
        try:
            fee_records = FeeRecord.objects.all()
            for fr in fee_records:
                self.assertEqual(fr.school_id, self.school_a.id,
                                 "Fee record from another school appeared!")
        finally:
            clear_current_school()


class FeeWaiverWorkflowTest(TestCase):
    """
    US-024: Complete waiver workflow across all students and roles.
    Verifies segregation of duties, role permissions, and balance updates.
    """
    def setUp(self):
        self.school = make_school("Waiver Academy")
        self.term = make_term(self.school)
        self.class_group = ClassGroup.all_objects.create(
            school=self.school, name='S.4 A', level='S4'
        )
        self.student_a = Student.all_objects.create(
            school=self.school, student_id='WA-001',
            first_name='Faith', last_name='Mukasa',
            gender='F', admission_date='2024-02-05',
            academic_year_admitted=2024, current_class=self.class_group,
        )
        self.student_b = Student.all_objects.create(
            school=self.school, student_id='WA-002',
            first_name='Peter', last_name='Mukasa',
            gender='M', admission_date='2024-02-05',
            academic_year_admitted=2024, current_class=self.class_group,
        )
        self.fee_record_a = FeeRecord.all_objects.create(
            school=self.school, student=self.student_a,
            academic_term=self.term,
            total_amount=Decimal('500000'), amount_paid=Decimal('100000'),
        )
        self.fee_record_b = FeeRecord.all_objects.create(
            school=self.school, student=self.student_b,
            academic_term=self.term,
            total_amount=Decimal('400000'), amount_paid=Decimal('0'),
        )
        self.bursar = User.objects.create_user(
            email='bursar@waiver.ug', password='pass', role='bursar',
            school=self.school, first_name='James', last_name='Bursar',
        )
        self.director = User.objects.create_user(
            email='director@waiver.ug', password='pass', role='director',
            school=self.school, first_name='Sarah', last_name='Director',
        )

    def test_bursar_creates_waiver_is_pending(self):
        """Bursar submits a waiver request -> status is pending."""
        from rest_framework.test import APIRequestFactory, force_authenticate
        from payments.views import FeeWaiverViewSet

        factory = APIRequestFactory()
        req = factory.post('/api/v1/payments/waivers/', {
            'fee_record_id': str(self.fee_record_a.id),
            'amount': 100000,
            'reason': 'Academic Scholarship',
        }, format='json')
        force_authenticate(req, user=self.bursar)
        view = FeeWaiverViewSet.as_view({'post': 'create'})
        res = view(req)

        self.assertEqual(res.status_code, 201)
        self.assertEqual(res.data['status'], 'pending')
        self.fee_record_a.refresh_from_db()
        self.assertEqual(self.fee_record_a.amount_waived, Decimal('0'))
        self.assertEqual(self.fee_record_a.balance, Decimal('400000'))

    def test_bursar_cannot_approve_waiver_403(self):
        """Bursar attempting to approve any waiver is rejected with HTTP 403."""
        from rest_framework.test import APIRequestFactory, force_authenticate
        from payments.views import FeeWaiverViewSet
        from payments.models import FeeWaiver

        waiver = FeeWaiver.all_objects.create(
            school=self.school, fee_record=self.fee_record_a,
            amount=Decimal('100000'), reason='Test',
            status='pending', requested_by=self.bursar,
        )

        factory = APIRequestFactory()
        req = factory.post(f'/api/v1/payments/waivers/{waiver.id}/approve/')
        force_authenticate(req, user=self.bursar)
        view = FeeWaiverViewSet.as_view({'post': 'approve'})
        res = view(req, pk=str(waiver.id))

        self.assertEqual(res.status_code, 403)
        waiver.refresh_from_db()
        self.assertEqual(waiver.status, 'pending')

    def test_director_approves_waiver_success(self):
        """Director approves a pending waiver -> status approved, balance reduced."""
        from rest_framework.test import APIRequestFactory, force_authenticate
        from payments.views import FeeWaiverViewSet
        from payments.models import FeeWaiver

        waiver = FeeWaiver.all_objects.create(
            school=self.school, fee_record=self.fee_record_a,
            amount=Decimal('100000'), reason='Academic Scholarship',
            status='pending', requested_by=self.bursar,
        )

        factory = APIRequestFactory()
        req = factory.post(f'/api/v1/payments/waivers/{waiver.id}/approve/')
        force_authenticate(req, user=self.director)
        view = FeeWaiverViewSet.as_view({'post': 'approve'})
        res = view(req, pk=str(waiver.id))

        self.assertEqual(res.status_code, 200)
        waiver.refresh_from_db()
        self.assertEqual(waiver.status, 'approved')
        self.fee_record_a.refresh_from_db()
        self.assertEqual(self.fee_record_a.amount_waived, Decimal('100000'))
        self.assertEqual(self.fee_record_a.balance, Decimal('300000'))

    def test_director_direct_grant_waiver_auto_approved(self):
        """Director grants waiver directly -> status approved immediately."""
        from rest_framework.test import APIRequestFactory, force_authenticate
        from payments.views import FeeWaiverViewSet

        factory = APIRequestFactory()
        req = factory.post('/api/v1/payments/waivers/', {
            'fee_record_id': str(self.fee_record_b.id),
            'amount': 80000,
            'reason': 'Director Special Bursary',
        }, format='json')
        force_authenticate(req, user=self.director)
        view = FeeWaiverViewSet.as_view({'post': 'create'})
        res = view(req)

        self.assertEqual(res.status_code, 201)
        self.assertEqual(res.data['status'], 'approved')
        self.fee_record_b.refresh_from_db()
        self.assertEqual(self.fee_record_b.amount_waived, Decimal('80000'))
        self.assertEqual(self.fee_record_b.balance, Decimal('320000'))

    def test_director_rejects_waiver(self):
        """Director rejects a pending waiver with reason -> status rejected, balance untouched."""
        from rest_framework.test import APIRequestFactory, force_authenticate
        from payments.views import FeeWaiverViewSet
        from payments.models import FeeWaiver

        waiver = FeeWaiver.all_objects.create(
            school=self.school, fee_record=self.fee_record_a,
            amount=Decimal('100000'), reason='Test',
            status='pending', requested_by=self.bursar,
        )

        factory = APIRequestFactory()
        req = factory.post(f'/api/v1/payments/waivers/{waiver.id}/reject/', {
            'reason': 'Ineligible for this academic term',
        }, format='json')
        force_authenticate(req, user=self.director)
        view = FeeWaiverViewSet.as_view({'post': 'reject'})
        res = view(req, pk=str(waiver.id))

        self.assertEqual(res.status_code, 200)
        waiver.refresh_from_db()
        self.assertEqual(waiver.status, 'rejected')
        self.assertEqual(waiver.rejection_reason, 'Ineligible for this academic term')
        self.fee_record_a.refresh_from_db()
        self.assertEqual(self.fee_record_a.amount_waived, Decimal('0'))
        self.assertEqual(self.fee_record_a.balance, Decimal('400000'))

    def test_fee_record_serializer_exposes_pending_waiver(self):
        """FeeRecordSerializer dynamically reflects has_pending_waiver for all students."""
        from payments.serializers import FeeRecordSerializer
        from payments.models import FeeWaiver

        FeeWaiver.all_objects.create(
            school=self.school, fee_record=self.fee_record_a,
            amount=Decimal('100000'), reason='Pending Scholarship',
            status='pending', requested_by=self.bursar,
        )

        serializer_a = FeeRecordSerializer(self.fee_record_a)
        self.assertTrue(serializer_a.data['has_pending_waiver'])
        self.assertEqual(serializer_a.data['pending_waiver_amount'], 100000)

        serializer_b = FeeRecordSerializer(self.fee_record_b)
        self.assertFalse(serializer_b.data['has_pending_waiver'])
        self.assertEqual(serializer_b.data['pending_waiver_amount'], 0)

