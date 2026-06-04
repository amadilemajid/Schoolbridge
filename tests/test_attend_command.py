"""
Tests for Task A8: ATTEND Command with Translation Service Integration.
Validates bilingual support for attendance rate retrieval.
"""
from django.test import TestCase
from django.utils import timezone
from unittest.mock import patch, MagicMock

from messaging.services import InboundCommandProcessor, WhatsAppService
from messaging.translation_service import TranslationService
from students.models import Guardian, Student, ClassGroup
from schools.models import School, AcademicYear, AcademicTerm


class AttendCommandTests(TestCase):

    def setUp(self):
        self.school = School.objects.create(
            name='Test School', slug='test-school', district='Kampala',
            phone='0700000001', email='test@school.ug', school_type='primary'
        )
        self.year = AcademicYear.objects.create(school=self.school, year=2024, is_current=True)
        self.term = AcademicTerm.objects.create(
            school=self.school, academic_year=self.year, term_number=1,
            name='Term 1 2024', start_date=timezone.now().date(),
            end_date=timezone.now().date(), fee_deadline=timezone.now().date(),
            is_current=True
        )
        self.class_group = ClassGroup.objects.create(
            school=self.school, name='P5 Blue', level='P5'
        )
        self.student = Student.objects.create(
            school=self.school, first_name='John', last_name='Doe',
            date_of_birth=timezone.now().date(), gender='M',
            student_id='SCH-2024-0001', admission_date=timezone.now().date(),
            academic_year_admitted=2024, current_class=self.class_group
        )

    def _make_guardian(self, phone, lang='en', student=None):
        return Guardian.objects.create(
            student=student or self.student,
            first_name='Test', last_name='Guardian', relationship='Parent',
            phone=phone, is_primary=True, preferred_language=lang
        )

    def _normalised(self, phone):
        if phone.startswith('0'):
            return '+256' + phone[1:]
        return phone

    def _wa_phone(self, phone):
        """Return phone in WhatsApp format (256... no +) as passed by InboundCommandProcessor."""
        if phone.startswith('0'):
            return '256' + phone[1:]
        return phone.lstrip('+')

    @patch('attendance.services.AttendanceService.get_attendance_rate')
    @patch.object(WhatsAppService, 'send_text_message')
    def test_attend_english_good_standing(self, mock_send, mock_rate):
        """English response for student with >= 75% attendance."""
        self._make_guardian('0700000001', 'en')
        mock_rate.return_value = 92.5
        mock_send.return_value = ('msg_id', True)

        InboundCommandProcessor._handle_attend(self._wa_phone('0700000001'), self.school)

        text = mock_send.call_args[1]['text']
        assert '📅 *SchoolBridge Attendance*' in text
        assert '✅ *John Doe*' in text
        assert 'Attendance: 92.5%' in text
        assert 'Good standing' in text
        assert 'Reply HELP for more commands.' in text

    @patch('attendance.services.AttendanceService.get_attendance_rate')
    @patch.object(WhatsAppService, 'send_text_message')
    def test_attend_english_low_attendance(self, mock_send, mock_rate):
        """English response for student below 75% threshold."""
        self._make_guardian('0700000002', 'en')
        mock_rate.return_value = 60.0
        mock_send.return_value = ('msg_id', True)

        InboundCommandProcessor._handle_attend(self._wa_phone('0700000002'), self.school)

        text = mock_send.call_args[1]['text']
        assert '⚠️ *John Doe*' in text
        assert 'Attendance: 60.0%' in text
        assert 'Below 75% threshold - please contact school' in text

    @patch('attendance.services.AttendanceService.get_attendance_rate')
    @patch.object(WhatsAppService, 'send_text_message')
    def test_attend_luganda_good_standing(self, mock_send, mock_rate):
        """Luganda response uses translated labels for good attendance."""
        self._make_guardian('0700000003', 'lg')
        mock_rate.return_value = 85.0
        mock_send.return_value = ('msg_id', True)

        InboundCommandProcessor._handle_attend(self._wa_phone('0700000003'), self.school)

        text = mock_send.call_args[1]['text']
        assert '📅 *SchoolBridge Okubaawo*' in text
        assert '✅ *John Doe*' in text
        assert 'Okubaawo: 85.0%' in text
        assert 'Embeera nnungi' in text
        assert 'Wandiika HELP ofune ebiragiro ebirala.' in text

    @patch('attendance.services.AttendanceService.get_attendance_rate')
    @patch.object(WhatsAppService, 'send_text_message')
    def test_attend_luganda_low_attendance(self, mock_send, mock_rate):
        """Luganda response for student below 75% threshold."""
        self._make_guardian('0700000004', 'lg')
        mock_rate.return_value = 55.0
        mock_send.return_value = ('msg_id', True)

        InboundCommandProcessor._handle_attend(self._wa_phone('0700000004'), self.school)

        text = mock_send.call_args[1]['text']
        assert 'Wansi wa 75% - tukirira essomero' in text

    @patch('attendance.services.AttendanceService.get_attendance_rate')
    @patch.object(WhatsAppService, 'send_text_message')
    def test_attend_no_records_english(self, mock_send, mock_rate):
        """English 'no records' message when attendance rate is None."""
        self._make_guardian('0700000005', 'en')
        mock_rate.return_value = None
        mock_send.return_value = ('msg_id', True)

        InboundCommandProcessor._handle_attend(self._wa_phone('0700000005'), self.school)

        text = mock_send.call_args[1]['text']
        assert '• *John Doe*: No attendance records yet.' in text

    @patch('attendance.services.AttendanceService.get_attendance_rate')
    @patch.object(WhatsAppService, 'send_text_message')
    def test_attend_no_records_luganda(self, mock_send, mock_rate):
        """Luganda 'no records' message when attendance rate is None."""
        self._make_guardian('0700000006', 'lg')
        mock_rate.return_value = None
        mock_send.return_value = ('msg_id', True)

        InboundCommandProcessor._handle_attend(self._wa_phone('0700000006'), self.school)

        text = mock_send.call_args[1]['text']
        assert 'Ebikwata ku kubaawo tebinnaba kuteekebwa.' in text

    @patch.object(WhatsAppService, 'send_text_message')
    def test_attend_not_registered(self, mock_send):
        """Unregistered phone gets 'not registered' message."""
        mock_send.return_value = ('msg_id', True)

        InboundCommandProcessor._handle_attend('+256799999999', self.school)

        text = mock_send.call_args[1]['text']
        assert 'Your number is not registered. Contact the school office.' in text

    @patch('attendance.services.AttendanceService.get_attendance_rate')
    @patch.object(WhatsAppService, 'send_text_message')
    def test_attend_no_active_term(self, mock_send, mock_rate):
        """'No active term' message when school has no current term."""
        self.term.is_current = False
        self.term.save()
        self._make_guardian('0700000007', 'en')
        mock_send.return_value = ('msg_id', True)

        InboundCommandProcessor._handle_attend(self._wa_phone('0700000007'), self.school)

        text = mock_send.call_args[1]['text']
        assert 'No active term found.' in text
        mock_rate.assert_not_called()

    @patch('attendance.services.AttendanceService.get_attendance_rate')
    @patch.object(WhatsAppService, 'send_text_message')
    def test_attend_75_percent_boundary_is_good(self, mock_send, mock_rate):
        """Exactly 75% attendance shows 'Good standing', not warning."""
        self._make_guardian('0700000008', 'en')
        mock_rate.return_value = 75.0
        mock_send.return_value = ('msg_id', True)

        InboundCommandProcessor._handle_attend(self._wa_phone('0700000008'), self.school)

        text = mock_send.call_args[1]['text']
        assert '✅ *John Doe*' in text
        assert 'Good standing' in text


class TranslationServiceAttendTests(TestCase):
    """Unit tests for TranslationService attend keys — no DB required."""

    def test_header_english(self):
        assert TranslationService.get('attend_header', lang='en') == '📅 *SchoolBridge Attendance*\n'

    def test_header_luganda(self):
        assert TranslationService.get('attend_header', lang='lg') == '📅 *SchoolBridge Okubaawo*\n'

    def test_detail_english(self):
        text = TranslationService.get(
            'attend_detail', lang='en',
            icon='✅', student_name='John Doe', rate=92.5, status='Good standing'
        )
        assert '✅ *John Doe*' in text
        assert 'Attendance: 92.5%' in text
        assert 'Good standing' in text

    def test_detail_luganda(self):
        text = TranslationService.get(
            'attend_detail', lang='lg',
            icon='✅', student_name='John Doe', rate=85.0, status='Embeera nnungi'
        )
        assert 'Okubaawo: 85.0%' in text
        assert 'Embeera nnungi' in text

    def test_status_good_english(self):
        assert TranslationService.get('attend_status_good', lang='en') == 'Good standing'

    def test_status_good_luganda(self):
        assert TranslationService.get('attend_status_good', lang='lg') == 'Embeera nnungi'

    def test_status_low_english(self):
        assert 'Below 75%' in TranslationService.get('attend_status_low', lang='en')

    def test_status_low_luganda(self):
        assert 'Wansi wa 75%' in TranslationService.get('attend_status_low', lang='lg')

    def test_no_records_english(self):
        text = TranslationService.get('attend_no_records', lang='en', student_name='John Doe')
        assert '• *John Doe*: No attendance records yet.' in text

    def test_no_records_luganda(self):
        text = TranslationService.get('attend_no_records', lang='lg', student_name='John Doe')
        assert 'Ebikwata ku kubaawo tebinnaba kuteekebwa.' in text
