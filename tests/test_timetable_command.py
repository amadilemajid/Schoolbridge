"""
Tests for Task A4: TIMETABLE Command with Translation Service Integration.
Validates bilingual support for timetable retrieval.
"""
import pytest
from django.test import TestCase
from django.utils import timezone
from unittest.mock import patch, MagicMock

from messaging.services import InboundCommandProcessor, WhatsAppService
from messaging.translation_service import TranslationService
from students.models import Guardian, Student, ClassGroup
from schools.models import School, AcademicYear, AcademicTerm, Timetable


class TimetableCommandTests(TestCase):
    """Test TIMETABLE command with TranslationService integration."""

    def setUp(self):
        self.school = School.objects.create(
            name='Test School',
            slug='test-school',
            district='Kampala',
            phone='0700000001',
            email='test@school.ug',
            school_type='primary'
        )
        self.year = AcademicYear.objects.create(school=self.school, year=2024, is_current=True)
        self.term = AcademicTerm.objects.create(
            school=self.school,
            academic_year=self.year,
            term_number=1,
            name='Term 1 2024',
            start_date=timezone.now().date(),
            end_date=timezone.now().date(),
            fee_deadline=timezone.now().date(),
            is_current=True
        )
        self.class_group = ClassGroup.objects.create(
            school=self.school,
            name='P5 Blue'
        )
        self.student = Student.objects.create(
            school=self.school, first_name='John', last_name='Doe',
            date_of_birth=timezone.now().date(), gender='M',
            student_id='SCH-2024-0001', admission_date=timezone.now().date(),
            academic_year_admitted=2024, current_class=self.class_group
        )

    @patch.object(WhatsAppService, 'send_text_message')
    def test_timetable_english_with_content(self, mock_send):
        """Test TIMETABLE command returns timetable in English."""
        Guardian.objects.create(
            student=self.student, first_name='Test', last_name='Guardian',
            relationship='Parent', phone='0700000001',
            is_primary=True, preferred_language='en'
        )
        Timetable.objects.create(
            school=self.school,
            class_group=self.class_group,
            content='Mon: Math, English\nTue: Science, SST',
            is_active=True
        )
        mock_send.return_value = ('msg_id', True)

        InboundCommandProcessor._handle_timetable('256700000001', self.school)

        mock_send.assert_called_once()
        args, kwargs = mock_send.call_args
        text = kwargs['text']
        assert '📚 *John Doe - P5 Blue Timetable*' in text
        assert 'Mon: Math, English' in text
        assert 'Tue: Science, SST' in text

    @patch.object(WhatsAppService, 'send_text_message')
    def test_timetable_luganda_with_content(self, mock_send):
        """Test TIMETABLE command returns timetable in Luganda."""
        Guardian.objects.create(
            student=self.student, first_name='Test', last_name='Guardian',
            relationship='Parent', phone='0700000002',
            is_primary=True, preferred_language='lg'
        )
        Timetable.objects.create(
            school=self.school,
            class_group=self.class_group,
            content='Balaza: Kubala, Lungereza\nKawakawakya: Saayansi, SST',
            is_active=True
        )
        mock_send.return_value = ('msg_id', True)

        InboundCommandProcessor._handle_timetable('256700000002', self.school)

        mock_send.assert_called_once()
        args, kwargs = mock_send.call_args
        text = kwargs['text']
        assert '📚 *John Doe - P5 Blue Emirimu*' in text
        assert 'Balaza: Kubala, Lungereza' in text

    @patch.object(WhatsAppService, 'send_text_message')
    def test_timetable_not_published_english(self, mock_send):
        """Test TIMETABLE command when no timetable exists - English."""
        Guardian.objects.create(
            student=self.student, first_name='Test', last_name='Guardian',
            relationship='Parent', phone='0700000003',
            is_primary=True, preferred_language='en'
        )
        mock_send.return_value = ('msg_id', True)

        InboundCommandProcessor._handle_timetable('256700000003', self.school)

        mock_send.assert_called_once()
        args, kwargs = mock_send.call_args
        text = kwargs['text']
        assert '📚 *John Doe*: No timetable published yet. Contact the school.' in text

    @patch.object(WhatsAppService, 'send_text_message')
    def test_timetable_not_published_luganda(self, mock_send):
        """Test TIMETABLE command when no timetable exists - Luganda."""
        Guardian.objects.create(
            student=self.student, first_name='Test', last_name='Guardian',
            relationship='Parent', phone='0700000004',
            is_primary=True, preferred_language='lg'
        )
        mock_send.return_value = ('msg_id', True)

        InboundCommandProcessor._handle_timetable('256700000004', self.school)

        mock_send.assert_called_once()
        args, kwargs = mock_send.call_args
        text = kwargs['text']
        assert '📚 *John Doe*: Emirimu teginnafulumizibwa. Tukirira essomero.' in text

    @patch.object(WhatsAppService, 'send_text_message')
    def test_timetable_not_registered_english(self, mock_send):
        """Test TIMETABLE command for unregistered number - English."""
        mock_send.return_value = ('msg_id', True)

        InboundCommandProcessor._handle_timetable('256799999999', self.school)

        mock_send.assert_called_once()
        args, kwargs = mock_send.call_args
        text = kwargs['text']
        assert 'Your number is not registered. Contact the school office.' in text

    @patch.object(WhatsAppService, 'send_text_message')
    def test_timetable_multiple_children_english(self, mock_send):
        """Test TIMETABLE command with multiple children - English."""
        Guardian.objects.create(
            student=self.student, first_name='Test', last_name='Guardian',
            relationship='Parent', phone='0700000005',
            is_primary=True, preferred_language='en'
        )
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
        Timetable.objects.create(
            school=self.school,
            class_group=self.class_group,
            content='Mon: Math\nTue: Science',
            is_active=True
        )
        mock_send.return_value = ('msg_id', True)

        InboundCommandProcessor._handle_timetable('256700000005', self.school)

        assert mock_send.call_count == 2
        calls = mock_send.call_args_list
        text1 = calls[0][1]['text']
        text2 = calls[1][1]['text']
        assert 'John Doe' in text1
        assert 'Jane Doe' in text2

    @patch.object(WhatsAppService, 'send_text_message')
    def test_timetable_no_class_assigned(self, mock_send):
        """Test TIMETABLE command when student has no class - English."""
        student_no_class = Student.objects.create(
            school=self.school, first_name='Bob', last_name='Smith',
            date_of_birth=timezone.now().date(), gender='M',
            student_id='SCH-2024-0003', admission_date=timezone.now().date(),
            academic_year_admitted=2024, current_class=None
        )
        Guardian.objects.create(
            student=student_no_class, first_name='Test', last_name='Guardian',
            relationship='Parent', phone='0700000006',
            is_primary=True, preferred_language='en'
        )
        mock_send.return_value = ('msg_id', True)

        InboundCommandProcessor._handle_timetable('256700000006', self.school)
        mock_send.assert_called_once()
        args, kwargs = mock_send.call_args
        text = kwargs['text']
        assert 'No class timetable available' in text

    @patch.object(WhatsAppService, 'send_text_message')
    def test_timetable_inactive_timetable_ignored(self, mock_send):
        """Test that inactive timetables are ignored."""
        Guardian.objects.create(
            student=self.student, first_name='Test', last_name='Guardian',
            relationship='Parent', phone='0700000007',
            is_primary=True, preferred_language='en'
        )
        Timetable.objects.create(
            school=self.school,
            class_group=self.class_group,
            content='Old timetable',
            is_active=False
        )
        mock_send.return_value = ('msg_id', True)

        InboundCommandProcessor._handle_timetable('256700000007', self.school)
        mock_send.assert_called_once()
        args, kwargs = mock_send.call_args
        text = kwargs['text']
        assert 'No timetable published yet' in text


class TranslationServiceTimetableIntegrationTests(TestCase):
    """Test TranslationService integration for timetable messages."""

    def test_timetable_header_english(self):
        """Test timetable header translation in English."""
        text = TranslationService.get(
            'timetable_header',
            lang='en',
            student_name='John Doe',
            class_name='P5 Blue',
            content='Mon: Math'
        )
        assert text == '📚 *John Doe - P5 Blue Timetable*\n\nMon: Math'

    def test_timetable_header_luganda(self):
        """Test timetable header translation in Luganda."""
        text = TranslationService.get(
            'timetable_header',
            lang='lg',
            student_name='John Doe',
            class_name='P5 Blue',
            content='Balaza: Kubala'
        )
        assert text == '📚 *John Doe - P5 Blue Emirimu*\n\nBalaza: Kubala'

    def test_timetable_not_available_english(self):
        """Test timetable not available message in English."""
        text = TranslationService.get(
            'timetable_not_available',
            lang='en',
            student_name='John Doe'
        )
        assert text == '📚 *John Doe*: No timetable published yet. Contact the school.'

    def test_timetable_not_available_luganda(self):
        """Test timetable not available message in Luganda."""
        text = TranslationService.get(
            'timetable_not_available',
            lang='lg',
            student_name='John Doe'
        )
        assert text == '📚 *John Doe*: Emirimu teginnafulumizibwa. Tukirira essomero.'

    def test_timetable_no_class_english(self):
        """Test no class timetable message in English."""
        text = TranslationService.get('timetable_no_class', lang='en')
        assert text == 'No class timetable available for your linked learner records.'

    def test_timetable_no_class_luganda(self):
        """Test no class timetable message in Luganda."""
        text = TranslationService.get('timetable_no_class', lang='lg')
        assert text == "Emirimu gy'ekiraalagana tegiriwo ku byafaanani byammwe."
