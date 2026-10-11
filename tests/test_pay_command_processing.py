"""
Tests for PAY command handler and MoMo request-to-pay (Task 2 - US-A03 Part 2).
Validates amount validation, guardian resolution, sibling disambiguation,
MoMo initiation, and bilingual responses.
"""
from decimal import Decimal
from django.test import TestCase
from django.utils import timezone
from unittest.mock import patch, MagicMock

from messaging.services import InboundCommandProcessor, WhatsAppService
from messaging.translation_service import TranslationService
from students.models import Guardian, Student, ClassGroup
from schools.models import School, AcademicYear, AcademicTerm
from payments.models import FeeRecord, Payment


def make_school():
    return School.objects.create(
        name='Kampala Test School', slug='kampala-pay-test', district='Kampala',
        phone='0700000000', email='admin@school.ug', school_type='primary'
    )


def make_student(school, class_group, student_id='SCH-2024-0001', first='John', last='Doe', gender='M'):
    return Student.objects.create(
        school=school, first_name=first, last_name=last,
        date_of_birth='2015-03-10', gender=gender,
        student_id=student_id, admission_date='2022-01-10',
        academic_year_admitted=2022, current_class=class_group
    )


def make_guardian(student, phone, lang='en'):
    return Guardian.objects.create(
        student=student, first_name='Sarah', last_name='Nakato',
        relationship='Mother', phone=phone,
        is_primary=True, preferred_language=lang
    )


def wa(phone):
    """Simulate WhatsApp inbound format: 256... (no +)."""
    if phone.startswith('0'):
        return '256' + phone[1:]
    return phone.lstrip('+')


class PayCommandInvalidAmountTests(TestCase):
    """Tests for PAY command amount validation."""

    def setUp(self):
        self.school = make_school()
        self.year = AcademicYear.objects.create(school=self.school, year=2024, is_current=True)
        self.term = AcademicTerm.objects.create(
            school=self.school, academic_year=self.year, term_number=1,
            name='Term 1 2024', start_date='2024-02-05', end_date='2024-05-31',
            fee_deadline='2024-03-15', is_current=True
        )
        self.class_group = ClassGroup.objects.create(school=self.school, name='P6 East', level='P6')
        self.student = make_student(self.school, self.class_group)
        self.guardian = make_guardian(self.student, '0701234567', 'en')

    @patch.object(WhatsAppService, 'send_text_message')
    def test_pay_no_amount(self, mock_send):
        """PAY without amount sends invalid amount message."""
        mock_send.return_value = ('msg_id', True)

        InboundCommandProcessor._handle_pay(wa('0701234567'), self.school, None, None)

        text = mock_send.call_args[1]['text']
        assert 'Invalid amount' in text or 'PAY <amount>' in text

    @patch.object(WhatsAppService, 'send_text_message')
    def test_pay_amount_too_low(self, mock_send):
        """PAY with amount below 1000 UGX sends error."""
        mock_send.return_value = ('msg_id', True)

        InboundCommandProcessor._handle_pay(wa('0701234567'), self.school, '500', None)

        text = mock_send.call_args[1]['text']
        assert '1,000' in text and '5,000,000' in text

    @patch.object(WhatsAppService, 'send_text_message')
    def test_pay_amount_too_high(self, mock_send):
        """PAY with amount above 5,000,000 UGX sends error."""
        mock_send.return_value = ('msg_id', True)

        InboundCommandProcessor._handle_pay(wa('0701234567'), self.school, '10000000', None)

        text = mock_send.call_args[1]['text']
        assert 'Invalid amount' in text or '5,000,000' in text

    @patch.object(WhatsAppService, 'send_text_message')
    def test_pay_non_numeric_amount(self, mock_send):
        """PAY with non-numeric amount sends error."""
        mock_send.return_value = ('msg_id', True)

        InboundCommandProcessor._handle_pay(wa('0701234567'), self.school, 'ABC', None)

        text = mock_send.call_args[1]['text']
        assert 'Invalid amount' in text or 'PAY <amount>' in text


class PayCommandNotRegisteredTests(TestCase):
    """Tests for PAY when parent is not registered."""

    def setUp(self):
        self.school = make_school()

    @patch.object(WhatsAppService, 'send_text_message')
    def test_pay_unregistered_phone(self, mock_send):
        """PAY from unregistered number sends not-registered message."""
        mock_send.return_value = ('msg_id', True)

        InboundCommandProcessor._handle_pay(wa('0799999999'), self.school, '150000', None)

        text = mock_send.call_args[1]['text']
        assert 'not registered' in text.lower()


class PayCommandSingleChildTests(TestCase):
    """Tests for PAY with a single registered child."""

    def setUp(self):
        self.school = make_school()
        self.year = AcademicYear.objects.create(school=self.school, year=2024, is_current=True)
        self.term = AcademicTerm.objects.create(
            school=self.school, academic_year=self.year, term_number=1,
            name='Term 1 2024', start_date='2024-02-05', end_date='2024-05-31',
            fee_deadline='2024-03-15', is_current=True
        )
        self.class_group = ClassGroup.objects.create(school=self.school, name='P6 East', level='P6')
        self.student = make_student(self.school, self.class_group)
        self.guardian = make_guardian(self.student, '0701234567', 'en')
        self.fee_record = FeeRecord.objects.create(
            school=self.school, student=self.student,
            academic_term=self.term, total_amount=450000, amount_paid=200000
        )

    @patch('payments.services.MoMoService.initiate_request_to_pay')
    @patch.object(WhatsAppService, 'send_text_message')
    def test_pay_single_child_success(self, mock_send, mock_rtp):
        """PAY for single child initiates MoMo and sends success."""
        mock_send.return_value = ('msg_id', True)
        mock_rtp.return_value = {'reference_id': 'test-ref', 'status': 'PENDING'}

        InboundCommandProcessor._handle_pay(wa('0701234567'), self.school, '150000', None)

        mock_rtp.assert_called_once()
        call_kwargs = mock_rtp.call_args[1]
        assert call_kwargs['amount'] == Decimal('150000')
        assert call_kwargs['student'] == self.student

        text = mock_send.call_args[1]['text']
        assert 'Payment Request Sent' in text
        assert 'John Doe' in text
        assert 'UGX 150,000' in text

    @patch.object(WhatsAppService, 'send_text_message')
    def test_pay_fully_paid_student(self, mock_send):
        """PAY for fully-paid student sends no-balance message."""
        self.fee_record.amount_paid = self.fee_record.total_amount
        self.fee_record.save()
        mock_send.return_value = ('msg_id', True)

        InboundCommandProcessor._handle_pay(wa('0701234567'), self.school, '150000', None)

        text = mock_send.call_args[1]['text']
        assert 'no outstanding balance' in text.lower() or 'No payment needed' in text

    @patch('payments.services.MoMoService.initiate_request_to_pay')
    @patch.object(WhatsAppService, 'send_text_message')
    def test_pay_momo_failure(self, mock_send, mock_rtp):
        """PAY sends failure message when MoMo API fails."""
        mock_send.return_value = ('msg_id', True)
        mock_rtp.side_effect = RuntimeError("MTN API down")

        InboundCommandProcessor._handle_pay(wa('0701234567'), self.school, '150000', None)

        text = mock_send.call_args[1]['text']
        assert 'Payment Request Failed' in text or 'could not initiate' in text.lower()


class PayCommandMultipleSiblingTests(TestCase):
    """Tests for PAY with multiple registered siblings."""

    def setUp(self):
        self.school = make_school()
        self.year = AcademicYear.objects.create(school=self.school, year=2024, is_current=True)
        self.term = AcademicTerm.objects.create(
            school=self.school, academic_year=self.year, term_number=1,
            name='Term 1 2024', start_date='2024-02-05', end_date='2024-05-31',
            fee_deadline='2024-03-15', is_current=True
        )
        self.class_group = ClassGroup.objects.create(school=self.school, name='P6 East', level='P6')
        self.student1 = make_student(self.school, self.class_group, 'SCH-2024-0001', 'Alice', 'Nakato')
        self.student2 = make_student(self.school, self.class_group, 'SCH-2024-0002', 'Bob', 'Okello')
        self.guardian1 = make_guardian(self.student1, '0701234567', 'en')
        # Same phone, different student — simulates sibling guardian records
        Guardian.objects.create(
            student=self.student2, first_name='Sarah', last_name='Nakato',
            relationship='Mother', phone='0701234567',
            is_primary=True, preferred_language='en'
        )
        FeeRecord.objects.create(
            school=self.school, student=self.student1,
            academic_term=self.term, total_amount=450000, amount_paid=200000
        )
        FeeRecord.objects.create(
            school=self.school, student=self.student2,
            academic_term=self.term, total_amount=380000, amount_paid=100000
        )

    @patch.object(WhatsAppService, 'send_text_message')
    def test_pay_multiple_siblings_no_identifier_prompts(self, mock_send):
        """PAY without identifier for multi-child guardian prompts selection."""
        mock_send.return_value = ('msg_id', True)

        InboundCommandProcessor._handle_pay(wa('0701234567'), self.school, '150000', None)

        text = mock_send.call_args[1]['text']
        assert 'Alice Nakato' in text
        assert 'Bob Okello' in text
        assert 'PAY <amount> <child name>' in text or 'specify which child' in text.lower()

    @patch('payments.services.MoMoService.initiate_request_to_pay')
    @patch.object(WhatsAppService, 'send_text_message')
    def test_pay_with_sibling_identifier_resolves(self, mock_send, mock_rtp):
        """PAY with child name identifier resolves to correct student."""
        mock_send.return_value = ('msg_id', True)
        mock_rtp.return_value = {'reference_id': 'test-ref', 'status': 'PENDING'}

        InboundCommandProcessor._handle_pay(wa('0701234567'), self.school, '150000', 'ALICE')

        mock_rtp.assert_called_once()
        call_kwargs = mock_rtp.call_args[1]
        assert call_kwargs['student'] == self.student1

    @patch.object(WhatsAppService, 'send_text_message')
    def test_pay_with_invalid_identifier(self, mock_send):
        """PAY with unmatched identifier sends error."""
        mock_send.return_value = ('msg_id', True)

        InboundCommandProcessor._handle_pay(wa('0701234567'), self.school, '150000', 'CHARLIE')

        text = mock_send.call_args[1]['text']
        assert 'CHARLIE' in text
        assert 'Could not find' in text or 'tazuuliddwa' in text


class PayCommandLugandaTests(TestCase):
    """Tests for PAY command in Luganda."""

    def setUp(self):
        self.school = make_school()
        self.year = AcademicYear.objects.create(school=self.school, year=2024, is_current=True)
        self.term = AcademicTerm.objects.create(
            school=self.school, academic_year=self.year, term_number=1,
            name='Term 1 2024', start_date='2024-02-05', end_date='2024-05-31',
            fee_deadline='2024-03-15', is_current=True
        )
        self.class_group = ClassGroup.objects.create(school=self.school, name='P6 East', level='P6')
        self.student = make_student(self.school, self.class_group)
        self.guardian = make_guardian(self.student, '0702345678', 'lg')
        FeeRecord.objects.create(
            school=self.school, student=self.student,
            academic_term=self.term, total_amount=450000, amount_paid=200000
        )

    @patch('payments.services.MoMoService.initiate_request_to_pay')
    @patch.object(WhatsAppService, 'send_text_message')
    def test_pay_luganda_success(self, mock_send, mock_rtp):
        """Luganda: PAY success shows Luganda confirmation."""
        mock_send.return_value = ('msg_id', True)
        mock_rtp.return_value = {'reference_id': 'test-ref', 'status': 'PENDING'}

        InboundCommandProcessor._handle_pay(wa('0702345678'), self.school, '150000', None)

        text = mock_send.call_args[1]['text']
        assert 'Okusaba Okusasula Kwetikkiddwa' in text
        assert 'Omuyizi: John Doe' in text

    @patch.object(WhatsAppService, 'send_text_message')
    def test_pay_luganda_invalid_amount(self, mock_send):
        """Luganda: invalid amount shows Luganda error."""
        mock_send.return_value = ('msg_id', True)

        InboundCommandProcessor._handle_pay(wa('0702345678'), self.school, '500', None)

        text = mock_send.call_args[1]['text']
        assert 'Omuwendo si mutuufu' in text


class PayTranslationKeyTests(TestCase):
    """Unit tests for PAY translation keys — no DB required."""

    def test_pay_initiated_english(self):
        text = TranslationService.get(
            'pay_initiated', lang='en', student_name='John', amount=150000
        )
        assert 'Payment Request Sent' in text
        assert 'UGX 150,000' in text

    def test_pay_initiated_luganda(self):
        text = TranslationService.get(
            'pay_initiated', lang='lg', student_name='John', amount=150000
        )
        assert 'Okusaba Okusasula Kwetikkiddwa' in text

    def test_pay_failed_english(self):
        text = TranslationService.get('pay_failed', lang='en', merchant_phone='0700000000')
        assert 'Payment Request Failed' in text
        assert '0700000000' in text

    def test_pay_invalid_amount_english(self):
        text = TranslationService.get('pay_invalid_amount', lang='en')
        assert 'Invalid amount' in text
        assert '1,000' in text
        assert '5,000,000' in text

    def test_pay_multiple_siblings_english(self):
        text = TranslationService.get(
            'pay_multiple_siblings', lang='en',
            count=2, children_list='• Alice\n• Bob', example_name='Alice'
        )
        assert '2 children registered' in text
        assert 'Alice' in text
        assert 'Bob' in text

    def test_pay_no_balance_english(self):
        text = TranslationService.get('pay_no_balance', lang='en', student_name='John')
        assert 'no outstanding balance' in text

    def test_pay_student_not_found_english(self):
        text = TranslationService.get('pay_student_not_found', lang='en', identifier='Charlie')
        assert 'Charlie' in text
        assert 'Could not find' in text
