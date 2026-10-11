"""
Tests for Task A6: RESULTS Command with Translation Service Integration.
Validates bilingual support for exam results retrieval.
"""
from django.test import TestCase
from django.utils import timezone
from unittest.mock import patch

from messaging.services import InboundCommandProcessor, WhatsAppService
from messaging.translation_service import TranslationService
from students.models import Guardian, Student, ClassGroup
from schools.models import School, AcademicYear, AcademicTerm
from results.models import TermResult


class ResultsCommandTests(TestCase):

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

    def _make_result(self, student=None, total=450, avg=75.0, rank=5, total_s=40, div='II'):
        s = student or self.student
        return TermResult.objects.create(
            school=self.school, student=s, academic_term=self.term,
            class_group=s.current_class or self.class_group,
            total_marks=total, average_marks=avg,
            class_rank=rank, total_students=total_s,
            division=div if div is not None else '',
            is_published=True
        )

    def _make_guardian(self, phone, lang='en', student=None):
        return Guardian.objects.create(
            student=student or self.student,
            first_name='Test', last_name='Guardian', relationship='Parent',
            phone=phone, is_primary=True, preferred_language=lang
        )

    def _normalised(self, phone):
        """Return phone as stored by Guardian.save() (+256...) for query matching."""
        if phone.startswith('0'):
            return '+256' + phone[1:]
        return phone

    def _wa_phone(self, phone):
        """Return phone in WhatsApp format (256... no +) as passed by InboundCommandProcessor."""
        if phone.startswith('0'):
            return '256' + phone[1:]
        return phone.lstrip('+')

    @patch.object(WhatsAppService, 'send_text_message')
    def test_results_english_with_data(self, mock_send):
        """English response includes correct labels and values."""
        self._make_guardian('0700000001', 'en')
        self._make_result()
        mock_send.return_value = ('msg_id', True)

        InboundCommandProcessor._handle_results(
            self._wa_phone('0700000001'), self.school
        )

        text = mock_send.call_args[1]['text']
        assert 'SchoolBridge Results' in text
        assert 'John Doe' in text
        assert 'Term 1 2024' in text
        assert '450' in text
        assert '75.0' in text
        assert '5' in text
        assert '40' in text
        assert 'II' in text
        assert 'Reply HELP for more commands.' in text

    @patch.object(WhatsAppService, 'send_text_message')
    def test_results_luganda_with_data(self, mock_send):
        """Luganda response uses correct translated labels."""
        self._make_guardian('0700000002', 'lg')
        self._make_result()
        mock_send.return_value = ('msg_id', True)

        InboundCommandProcessor._handle_results(
            self._wa_phone('0700000002'), self.school
        )

        text = mock_send.call_args[1]['text']
        assert 'Ebivudde' in text
        assert 'John Doe' in text
        assert 'Term 1 2024' in text
        assert '450' in text
        assert '75.0' in text
        assert 'Wandiika HELP ofune ebiragiro ebirala.' in text

    @patch.object(WhatsAppService, 'send_text_message')
    def test_results_no_data_english(self, mock_send):
        """English 'no results' message returned when no TermResult exists."""
        self._make_guardian('0700000003', 'en')
        mock_send.return_value = ('msg_id', True)

        InboundCommandProcessor._handle_results(
            self._wa_phone('0700000003'), self.school
        )

        text = mock_send.call_args[1]['text']
        assert 'No results available yet' in text

    @patch.object(WhatsAppService, 'send_text_message')
    def test_results_no_data_luganda(self, mock_send):
        """Luganda 'no results' message returned when no TermResult exists."""
        self._make_guardian('0700000004', 'lg')
        mock_send.return_value = ('msg_id', True)

        InboundCommandProcessor._handle_results(
            self._wa_phone('0700000004'), self.school
        )

        text = mock_send.call_args[1]['text']
        assert 'tebinnaba kufulumizibwa' in text

    @patch.object(WhatsAppService, 'send_text_message')
    def test_results_not_registered(self, mock_send):
        """Unregistered phone gets 'not registered' message."""
        mock_send.return_value = ('msg_id', True)

        InboundCommandProcessor._handle_results('+256799999999', self.school)

        text = mock_send.call_args[1]['text']
        assert 'Your number is not registered. Contact the school office.' in text

    @patch.object(WhatsAppService, 'send_text_message')
    def test_results_multiple_children(self, mock_send):
        """Both children's results appear in one message."""
        self._make_guardian('0700000005', 'en')
        student2 = Student.objects.create(
            school=self.school, first_name='Jane', last_name='Doe',
            date_of_birth=timezone.now().date(), gender='F',
            student_id='SCH-2024-0002', admission_date=timezone.now().date(),
            academic_year_admitted=2024, current_class=self.class_group
        )
        Guardian.objects.create(
            student=student2, first_name='Test', last_name='Guardian',
            relationship='Parent', phone='0700000005',
            is_primary=False, preferred_language='en'
        )
        self._make_result()
        self._make_result(student=student2, total=380, avg=63.3, rank=15, div='III')
        mock_send.return_value = ('msg_id', True)

        InboundCommandProcessor._handle_results(
            self._wa_phone('0700000005'), self.school
        )

        text = mock_send.call_args[1]['text']
        assert 'John Doe' in text
        assert 'Jane Doe' in text

    @patch.object(WhatsAppService, 'send_text_message')
    def test_results_division_empty_shows_na(self, mock_send):
        """Empty division string displayed as 'N/A' (DB CharField is NOT NULL)."""
        self._make_guardian('0700000006', 'en')
        self._make_result(div='')  # empty string = no division assigned
        mock_send.return_value = ('msg_id', True)

        InboundCommandProcessor._handle_results(
            self._wa_phone('0700000006'), self.school
        )

        text = mock_send.call_args[1]['text']
        assert 'N/A' in text

    @patch.object(WhatsAppService, 'send_text_message')
    def test_results_latest_term_only(self, mock_send):
        """Only the latest term result is shown, not older ones."""
        self._make_guardian('0700000007', 'en')
        old_term = AcademicTerm.objects.create(
            school=self.school, academic_year=self.year, term_number=2,
            name='Term 2 2023', start_date='2023-05-01',
            end_date='2023-08-31', fee_deadline='2023-05-15'
        )
        self._make_result()
        TermResult.objects.create(
            school=self.school, student=self.student,
            academic_term=old_term, class_group=self.class_group,
            total_marks=200, average_marks=33.3,
            class_rank=35, total_students=40, division='U'
        )
        mock_send.return_value = ('msg_id', True)

        InboundCommandProcessor._handle_results(
            self._wa_phone('0700000007'), self.school
        )

        text = mock_send.call_args[1]['text']
        assert 'Term 2 2023' not in text
        assert 'Term 1 2024' in text

class TranslationServiceResultsTests(TestCase):
    """Unit tests for TranslationService results keys — no DB required."""

    def test_header_english(self):
        assert TranslationService.get('results_header', lang='en') == '📊 *SchoolBridge Results*\n'

    def test_header_luganda(self):
        assert TranslationService.get('results_header', lang='lg') == '📊 *SchoolBridge Ebivudde*\n'

    def test_detail_english_labels(self):
        text = TranslationService.get(
            'results_detail', lang='en',
            student_name='John Doe', term_name='Term 1 2024',
            total_marks=450, average_marks=75.0,
            rank=5, total_students=40, division='II'
        )
        assert 'Term: Term 1 2024' in text
        assert 'Total Marks: 450' in text
        assert 'Rank: 5 of 40' in text

    def test_detail_luganda_labels(self):
        text = TranslationService.get(
            'results_detail', lang='lg',
            student_name='John Doe', term_name='Term 1 2024',
            total_marks=450, average_marks=75.0,
            rank=5, total_students=40, division='II'
        )
        assert 'Ekiseera: Term 1 2024' in text
        assert 'Obubonero Bwonna: 450' in text
        assert 'Ekifo: 5 ku 40' in text

    def test_not_available_english(self):
        text = TranslationService.get('results_not_available', lang='en', student_name='John Doe')
        assert text == '• *John Doe*: No results available yet.\n'

    def test_not_available_luganda(self):
        text = TranslationService.get('results_not_available', lang='lg', student_name='John Doe')
        assert text == '• *John Doe*: Ebivudde tebinnaba kufulumizibwa.\n'

    def test_help_suffix_english(self):
        assert 'Reply HELP for more commands.' in TranslationService.get('help_suffix', lang='en')

    def test_help_suffix_luganda(self):
        assert 'Wandiika HELP ofune ebiragiro ebirala.' in TranslationService.get('help_suffix', lang='lg')
