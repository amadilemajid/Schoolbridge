"""
Tests for BALANCE and RECEIPT commands with bilingual support.
Uganda production context: UGX amounts, MoMo payments, MTN/Airtel methods.
"""
from django.test import TestCase
from django.utils import timezone
from unittest.mock import patch

from messaging.services import InboundCommandProcessor, WhatsAppService
from messaging.translation_service import TranslationService
from students.models import Guardian, Student, ClassGroup
from schools.models import School, AcademicYear, AcademicTerm
from payments.models import FeeRecord, Payment


def make_school():
    return School.objects.create(
        name='Kampala Test School', slug='kampala-test', district='Kampala',
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


class BalanceCommandEnglishTests(TestCase):

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

    def _make_fee_record(self, total=450000, paid=200000):
        return FeeRecord.objects.create(
            school=self.school, student=self.student,
            academic_term=self.term, total_amount=total, amount_paid=paid
        )

    @patch.object(WhatsAppService, 'send_text_message')
    def test_balance_english_outstanding(self, mock_send):
        """English: outstanding balance shows warning icon and UGX amounts."""
        self._make_fee_record(total=450000, paid=200000)
        mock_send.return_value = ('msg_id', True)

        InboundCommandProcessor._handle_balance(wa('0701234567'), self.school)

        text = mock_send.call_args[1]['text']
        assert 'SchoolBridge Fee Balance' in text
        assert '⚠️ *John Doe*' in text
        assert 'Class: P6 East' in text
        assert 'UGX 450,000' in text
        assert 'UGX 200,000' in text
        assert 'UGX 250,000' in text   # balance
        assert 'Reply HELP for more commands.' in text

    @patch.object(WhatsAppService, 'send_text_message')
    def test_balance_english_fully_paid(self, mock_send):
        """English: fully paid shows checkmark icon."""
        self._make_fee_record(total=450000, paid=450000)
        mock_send.return_value = ('msg_id', True)

        InboundCommandProcessor._handle_balance(wa('0701234567'), self.school)

        text = mock_send.call_args[1]['text']
        assert '✅ *John Doe*' in text
        assert 'UGX 0' in text   # zero balance

    @patch.object(WhatsAppService, 'send_text_message')
    def test_balance_english_not_registered(self, mock_send):
        """English: unregistered number gets bilingual-aware message."""
        mock_send.return_value = ('msg_id', True)

        InboundCommandProcessor._handle_balance(wa('0799999999'), self.school)

        text = mock_send.call_args[1]['text']
        assert 'not registered' in text
        assert 'school office' in text

    @patch.object(WhatsAppService, 'send_text_message')
    def test_balance_english_no_fee_record(self, mock_send):
        """English: no FeeRecord for term shows clear message."""
        mock_send.return_value = ('msg_id', True)

        InboundCommandProcessor._handle_balance(wa('0701234567'), self.school)

        text = mock_send.call_args[1]['text']
        assert 'No fee record for current term' in text

    @patch.object(WhatsAppService, 'send_text_message')
    def test_balance_english_no_active_term(self, mock_send):
        """English: no current term shows clear message."""
        self.term.is_current = False
        self.term.save()
        mock_send.return_value = ('msg_id', True)

        InboundCommandProcessor._handle_balance(wa('0701234567'), self.school)

        text = mock_send.call_args[1]['text']
        assert 'No active term found' in text

    @patch.object(WhatsAppService, 'send_text_message')
    def test_balance_english_multiple_children(self, mock_send):
        """English: two children's balances in one message."""
        student2 = make_student(self.school, self.class_group, 'SCH-2024-0002', 'James', 'Okello')
        make_guardian(student2, '0701234567', 'en')
        FeeRecord.objects.create(
            school=self.school, student=self.student,
            academic_term=self.term, total_amount=450000, amount_paid=450000
        )
        FeeRecord.objects.create(
            school=self.school, student=student2,
            academic_term=self.term, total_amount=380000, amount_paid=100000
        )
        mock_send.return_value = ('msg_id', True)

        InboundCommandProcessor._handle_balance(wa('0701234567'), self.school)

        text = mock_send.call_args[1]['text']
        assert 'John Doe' in text
        assert 'James Okello' in text
        assert 'UGX 450,000' in text
        assert 'UGX 380,000' in text


class BalanceCommandLugandaTests(TestCase):

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

    @patch.object(WhatsAppService, 'send_text_message')
    def test_balance_luganda_header(self, mock_send):
        """Luganda: header uses Luganda text."""
        FeeRecord.objects.create(
            school=self.school, student=self.student,
            academic_term=self.term, total_amount=450000, amount_paid=200000
        )
        mock_send.return_value = ('msg_id', True)

        InboundCommandProcessor._handle_balance(wa('0702345678'), self.school)

        text = mock_send.call_args[1]['text']
        assert "Ensimbi z'Essomero" in text

    @patch.object(WhatsAppService, 'send_text_message')
    def test_balance_luganda_detail_labels(self, mock_send):
        """Luganda: field labels are translated."""
        FeeRecord.objects.create(
            school=self.school, student=self.student,
            academic_term=self.term, total_amount=450000, amount_paid=200000
        )
        mock_send.return_value = ('msg_id', True)

        InboundCommandProcessor._handle_balance(wa('0702345678'), self.school)

        text = mock_send.call_args[1]['text']
        assert 'Ekkiraalagana:' in text
        assert 'Zonna: UGX 450,000' in text
        assert 'Ezisasuliddwa: UGX 200,000' in text
        assert 'Ezisigaddewo: UGX 250,000' in text
        assert 'Wandiika HELP ofune ebiragiro ebirala.' in text

    @patch.object(WhatsAppService, 'send_text_message')
    def test_balance_luganda_not_registered(self, mock_send):
        """Luganda: unregistered number gets Luganda message."""
        mock_send.return_value = ('msg_id', True)

        InboundCommandProcessor._handle_balance(wa('0799999998'), self.school)

        text = mock_send.call_args[1]['text']
        # unregistered phone — no guardian so defaults to English
        assert 'not registered' in text or 'teriko' in text

    @patch.object(WhatsAppService, 'send_text_message')
    def test_balance_luganda_no_fee_record(self, mock_send):
        """Luganda: no FeeRecord shows Luganda message."""
        mock_send.return_value = ('msg_id', True)

        InboundCommandProcessor._handle_balance(wa('0702345678'), self.school)

        text = mock_send.call_args[1]['text']
        assert 'teziriwo' in text

    @patch.object(WhatsAppService, 'send_text_message')
    def test_balance_luganda_no_active_term(self, mock_send):
        """Luganda: no current term shows Luganda message."""
        self.term.is_current = False
        self.term.save()
        mock_send.return_value = ('msg_id', True)

        InboundCommandProcessor._handle_balance(wa('0702345678'), self.school)

        text = mock_send.call_args[1]['text']
        assert 'Ekiseera tekiriwo' in text


class ReceiptCommandEnglishTests(TestCase):

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
        self.fee_record = FeeRecord.objects.create(
            school=self.school, student=self.student,
            academic_term=self.term, total_amount=450000, amount_paid=200000
        )
        self.guardian = make_guardian(self.student, '0701234567', 'en')

    def _make_payment(self, amount=200000, method='mtn_momo', ref=None):
        return Payment.objects.create(
            school=self.school, student=self.student,
            fee_record=self.fee_record, method=method,
            amount=amount, status='completed', is_reversed=False,
            payment_date=timezone.now(),
            momo_reference=ref or f'REF-{amount}-{method}',
        )

    @patch.object(WhatsAppService, 'send_text_message')
    def test_receipt_english_mtn_momo(self, mock_send):
        """English: MTN MoMo payment displayed with UGX amount."""
        self._make_payment(200000, 'mtn_momo', 'MTN-REF-001')
        mock_send.return_value = ('msg_id', True)

        InboundCommandProcessor._handle_receipt(wa('0701234567'), self.school)

        text = mock_send.call_args[1]['text']
        assert 'Payment Receipts' in text
        assert 'UGX 200,000' in text
        assert 'MTN MoMo' in text

    @patch.object(WhatsAppService, 'send_text_message')
    def test_receipt_english_airtel_money(self, mock_send):
        """English: Airtel Money payment displayed correctly."""
        self._make_payment(150000, 'airtel_money', 'AIRTEL-REF-001')
        mock_send.return_value = ('msg_id', True)

        InboundCommandProcessor._handle_receipt(wa('0701234567'), self.school)

        text = mock_send.call_args[1]['text']
        assert 'UGX 150,000' in text
        assert 'Airtel Money' in text

    @patch.object(WhatsAppService, 'send_text_message')
    def test_receipt_english_cash(self, mock_send):
        """English: Cash payment displayed correctly."""
        self._make_payment(100000, 'cash', None)
        # cash has no momo_reference so set explicitly
        Payment.objects.filter(method='cash').update(momo_reference=None)
        mock_send.return_value = ('msg_id', True)

        InboundCommandProcessor._handle_receipt(wa('0701234567'), self.school)

        text = mock_send.call_args[1]['text']
        assert 'Cash' in text

    @patch.object(WhatsAppService, 'send_text_message')
    def test_receipt_english_no_payments(self, mock_send):
        """English: no payments returns clear message."""
        mock_send.return_value = ('msg_id', True)

        InboundCommandProcessor._handle_receipt(wa('0701234567'), self.school)

        text = mock_send.call_args[1]['text']
        assert 'No payments found' in text

    @patch.object(WhatsAppService, 'send_text_message')
    def test_receipt_english_filtered_by_date(self, mock_send):
        """English: date filter shows only matching payments."""
        self._make_payment(200000, 'mtn_momo', 'MTN-DATE-001')
        mock_send.return_value = ('msg_id', True)

        today = timezone.now().strftime('%Y-%m-%d')
        InboundCommandProcessor._handle_receipt(wa('0701234567'), self.school, date_str=today)

        text = mock_send.call_args[1]['text']
        assert 'UGX 200,000' in text

    @patch.object(WhatsAppService, 'send_text_message')
    def test_receipt_english_invalid_date(self, mock_send):
        """English: invalid date format returns clear error."""
        mock_send.return_value = ('msg_id', True)

        InboundCommandProcessor._handle_receipt(wa('0701234567'), self.school, date_str='32-13-2024')

        text = mock_send.call_args[1]['text']
        assert 'RECEIPT YYYY-MM-DD' in text

    @patch.object(WhatsAppService, 'send_text_message')
    def test_receipt_english_not_registered(self, mock_send):
        """English: unregistered number returns clear message."""
        mock_send.return_value = ('msg_id', True)

        InboundCommandProcessor._handle_receipt(wa('0799999999'), self.school)

        text = mock_send.call_args[1]['text']
        assert 'not registered' in text.lower() or 'Number not registered' in text

    @patch.object(WhatsAppService, 'send_text_message')
    def test_receipt_limited_to_10(self, mock_send):
        """Receipt returns at most 10 most recent payments."""
        for i in range(12):
            Payment.objects.create(
                school=self.school, student=self.student,
                fee_record=self.fee_record, method='cash',
                amount=10000, status='completed', is_reversed=False,
                payment_date=timezone.now(), momo_reference=f'CASH-{i}',
            )
        mock_send.return_value = ('msg_id', True)

        InboundCommandProcessor._handle_receipt(wa('0701234567'), self.school)

        text = mock_send.call_args[1]['text']
        # 10 bullet lines + header = 11 lines maximum
        assert text.count('UGX 10,000') == 10


class ReceiptCommandLugandaTests(TestCase):

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
        self.fee_record = FeeRecord.objects.create(
            school=self.school, student=self.student,
            academic_term=self.term, total_amount=450000, amount_paid=200000
        )
        self.guardian = make_guardian(self.student, '0702345678', 'lg')

    @patch.object(WhatsAppService, 'send_text_message')
    def test_receipt_luganda_header(self, mock_send):
        """Luganda: receipt header in Luganda."""
        Payment.objects.create(
            school=self.school, student=self.student,
            fee_record=self.fee_record, method='mtn_momo',
            amount=200000, status='completed', is_reversed=False,
            payment_date=timezone.now(), momo_reference='MTN-LG-001',
        )
        mock_send.return_value = ('msg_id', True)

        InboundCommandProcessor._handle_receipt(wa('0702345678'), self.school)

        text = mock_send.call_args[1]['text']
        assert "Ebiragiro by'Okusasula" in text
        assert 'okuyita mu MTN MoMo' in text
        assert 'UGX 200,000' in text

    @patch.object(WhatsAppService, 'send_text_message')
    def test_receipt_luganda_none_found(self, mock_send):
        """Luganda: no payments message in Luganda."""
        mock_send.return_value = ('msg_id', True)

        InboundCommandProcessor._handle_receipt(wa('0702345678'), self.school)

        text = mock_send.call_args[1]['text']
        assert 'Tewasuulwa ndala' in text

    @patch.object(WhatsAppService, 'send_text_message')
    def test_receipt_luganda_invalid_date(self, mock_send):
        """Luganda: invalid date error in Luganda."""
        mock_send.return_value = ('msg_id', True)

        InboundCommandProcessor._handle_receipt(wa('0702345678'), self.school, date_str='bad-date')

        text = mock_send.call_args[1]['text']
        assert 'RECEIPT YYYY-MM-DD' in text


class TranslationServiceBalanceReceiptTests(TestCase):
    """Unit tests for balance/receipt translation keys — no DB required."""

    def test_balance_header_english(self):
        assert 'Fee Balance' in TranslationService.get('balance_header', lang='en')

    def test_balance_header_luganda(self):
        assert "Ensimbi z'Essomero" in TranslationService.get('balance_header', lang='lg')

    def test_balance_detail_english(self):
        text = TranslationService.get(
            'balance_detail', lang='en', icon='✅',
            student_name='John Doe', class_name='P6 East',
            total=450000, paid=450000, balance=0
        )
        assert 'Class: P6 East' in text
        assert 'UGX 450,000' in text
        assert 'UGX 0' in text

    def test_balance_detail_luganda(self):
        text = TranslationService.get(
            'balance_detail', lang='lg', icon='⚠️',
            student_name='John Doe', class_name='P6 East',
            total=450000, paid=200000, balance=250000
        )
        assert 'Ekkiraalagana: P6 East' in text
        assert 'Zonna: UGX 450,000' in text
        assert 'Ezisigaddewo: UGX 250,000' in text

    def test_balance_no_record_english(self):
        text = TranslationService.get('balance_no_record', lang='en', student_name='John Doe')
        assert 'No fee record for current term' in text

    def test_balance_no_record_luganda(self):
        text = TranslationService.get('balance_no_record', lang='lg', student_name='John Doe')
        assert 'teziriwo' in text

    def test_balance_no_term_english(self):
        text = TranslationService.get('balance_no_term', lang='en', student_name='John Doe')
        assert 'No active term found' in text

    def test_balance_no_term_luganda(self):
        text = TranslationService.get('balance_no_term', lang='lg', student_name='John Doe')
        assert 'Ekiseera tekiriwo' in text

    def test_receipt_header_english(self):
        assert 'Payment Receipts' in TranslationService.get('receipt_header', lang='en')

    def test_receipt_header_luganda(self):
        assert "Ebiragiro by'Okusasula" in TranslationService.get('receipt_header', lang='lg')

    def test_receipt_line_english(self):
        text = TranslationService.get(
            'receipt_line', lang='en',
            date='03 Jun 2024', amount=200000, method='MTN MoMo'
        )
        assert 'UGX 200,000' in text
        assert 'via MTN MoMo' in text

    def test_receipt_line_luganda(self):
        text = TranslationService.get(
            'receipt_line', lang='lg',
            date='03 Jun 2024', amount=200000, method='MTN MoMo'
        )
        assert 'okuyita mu MTN MoMo' in text
        assert 'UGX 200,000' in text

    def test_receipt_none_found_english(self):
        text = TranslationService.get('receipt_none_found', lang='en', date_suffix='')
        assert 'No payments found' in text

    def test_receipt_none_found_luganda(self):
        text = TranslationService.get('receipt_none_found', lang='lg', date_suffix='')
        assert 'Tewasuulwa ndala' in text

    def test_receipt_invalid_date_english(self):
        text = TranslationService.get('receipt_invalid_date', lang='en')
        assert 'YYYY-MM-DD' in text

    def test_receipt_invalid_date_luganda(self):
        text = TranslationService.get('receipt_invalid_date', lang='lg')
        assert 'YYYY-MM-DD' in text
