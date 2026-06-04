"""
Integration tests for MENU and LANGUAGE commands (Tasks A5 & A7).
Validates TranslationService integration with command handlers.
"""
import pytest
from django.test import TestCase
from messaging.services import InboundCommandProcessor
from messaging.translation_service import TranslationService
from students.models import Guardian, Student, ClassGroup
from schools.models import School
from unittest.mock import patch, MagicMock


class MenuCommandTests(TestCase):
    """Test suite for MENU command with translation support."""

    def setUp(self):
        """Create test data."""
        self.school = School.objects.create(
            name='Test School',
            slug='test-school',
            district='Kampala',
            phone='0701234567',
            email='test@school.ug',
            school_type='primary',
        )
        self.class_group = ClassGroup.objects.create(
            school=self.school,
            name='P.5',
            level='P5',
        )
        self.student = Student.objects.create(
            school=self.school,
            student_id='SCH-2024-0001',
            first_name='John',
            last_name='Doe',
            gender='M',
            admission_date='2024-01-01',
            academic_year_admitted=2024,
            current_class=self.class_group,
        )
        self.guardian_en = Guardian.objects.create(
            student=self.student,
            first_name='Jane',
            last_name='Doe',
            relationship='Mother',
            phone='0701234567',
            is_primary=True,
            preferred_language='en',
        )

    @patch('messaging.services.WhatsAppService.send_text_message')
    def test_menu_command_uses_translation_service(self, mock_send):
        """MENU command should use TranslationService to get menu text."""
        mock_send.return_value = ('msg_id', True)
        
        InboundCommandProcessor._handle_menu(
            phone=self.guardian_en.phone_normalised,
            school=self.school
        )
        
        # Verify send was called
        assert mock_send.called
        call_args = mock_send.call_args
        sent_text = call_args.kwargs['text']
        
        # Should contain menu content
        assert 'Welcome to SchoolBridge' in sent_text or 'Tusanyukidde' in sent_text

    @patch('messaging.services.WhatsAppService.send_text_message')
    def test_menu_command_english_for_english_guardian(self, mock_send):
        """MENU should send English menu for English-preferring guardian."""
        mock_send.return_value = ('msg_id', True)
        
        InboundCommandProcessor._handle_menu(
            phone=self.guardian_en.phone_normalised,
            school=self.school
        )
        
        call_args = mock_send.call_args
        sent_text = call_args.kwargs['text']
        
        # Should be English
        assert 'Welcome to SchoolBridge' in sent_text
        assert 'BALANCE - Fee balance' in sent_text

    @patch('messaging.services.WhatsAppService.send_text_message')
    def test_menu_command_luganda_for_luganda_guardian(self, mock_send):
        """MENU should send Luganda menu for Luganda-preferring guardian."""
        mock_send.return_value = ('msg_id', True)
        
        # Set guardian to Luganda
        self.guardian_en.preferred_language = 'lg'
        self.guardian_en.save()
        
        InboundCommandProcessor._handle_menu(
            phone=self.guardian_en.phone_normalised,
            school=self.school
        )
        
        call_args = mock_send.call_args
        sent_text = call_args.kwargs['text']
        
        # Should be Luganda
        assert 'Tusanyukidde kukusanga' in sent_text
        assert 'BALANCE - Ensimbi ezisigaddewo' in sent_text

    @patch('messaging.services.WhatsAppService.send_text_message')
    def test_menu_command_defaults_english_for_unknown_phone(self, mock_send):
        """MENU should default to English for unknown phone numbers."""
        mock_send.return_value = ('msg_id', True)
        
        InboundCommandProcessor._handle_menu(
            phone='+256709999999',  # Unknown phone
            school=self.school
        )
        
        call_args = mock_send.call_args
        sent_text = call_args.kwargs['text']
        
        # Should default to English
        assert 'Welcome to SchoolBridge' in sent_text


class LanguageCommandTests(TestCase):
    """Test suite for LUGANDA and ENGLISH commands with translation support."""

    def setUp(self):
        """Create test data."""
        self.school = School.objects.create(
            name='Test School',
            slug='test-school',
            district='Kampala',
            phone='0701234567',
            email='test@school.ug',
            school_type='primary',
        )
        self.class_group = ClassGroup.objects.create(
            school=self.school,
            name='P.5',
            level='P5',
        )
        self.student = Student.objects.create(
            school=self.school,
            student_id='SCH-2024-0001',
            first_name='John',
            last_name='Doe',
            gender='M',
            admission_date='2024-01-01',
            academic_year_admitted=2024,
            current_class=self.class_group,
        )
        self.guardian = Guardian.objects.create(
            student=self.student,
            first_name='Jane',
            last_name='Doe',
            relationship='Mother',
            phone='0701234567',
            is_primary=True,
            preferred_language='en',
        )

    @patch('messaging.services.WhatsAppService.send_text_message')
    def test_english_command_updates_language(self, mock_send):
        """ENGLISH command should update guardian language to 'en'."""
        mock_send.return_value = ('msg_id', True)
        
        # Start with Luganda
        self.guardian.preferred_language = 'lg'
        self.guardian.save()
        
        InboundCommandProcessor._handle_language(
            phone=self.guardian.phone_normalised,
            school=self.school,
            lang='en'
        )
        
        # Check language was updated
        self.guardian.refresh_from_db()
        assert self.guardian.preferred_language == 'en'

    @patch('messaging.services.WhatsAppService.send_text_message')
    def test_luganda_command_updates_language(self, mock_send):
        """LUGANDA command should update guardian language to 'lg'."""
        mock_send.return_value = ('msg_id', True)
        
        InboundCommandProcessor._handle_language(
            phone=self.guardian.phone_normalised,
            school=self.school,
            lang='lg'
        )
        
        # Check language was updated
        self.guardian.refresh_from_db()
        assert self.guardian.preferred_language == 'lg'

    @patch('messaging.services.WhatsAppService.send_text_message')
    def test_english_command_sends_english_confirmation(self, mock_send):
        """ENGLISH command should send confirmation in English."""
        mock_send.return_value = ('msg_id', True)
        
        InboundCommandProcessor._handle_language(
            phone=self.guardian.phone_normalised,
            school=self.school,
            lang='en'
        )
        
        call_args = mock_send.call_args
        sent_text = call_args.kwargs['text']
        
        # Should contain English confirmation
        assert 'Language switched to' in sent_text
        assert 'English' in sent_text

    @patch('messaging.services.WhatsAppService.send_text_message')
    def test_luganda_command_sends_luganda_confirmation(self, mock_send):
        """LUGANDA command should send confirmation in Luganda."""
        mock_send.return_value = ('msg_id', True)
        
        InboundCommandProcessor._handle_language(
            phone=self.guardian.phone_normalised,
            school=self.school,
            lang='lg'
        )
        
        call_args = mock_send.call_args
        sent_text = call_args.kwargs['text']
        
        # Should contain Luganda confirmation
        assert 'Olulimi lwaakyusibwa' in sent_text
        assert 'Oluganda' in sent_text

    @patch('messaging.services.WhatsAppService.send_text_message')
    def test_language_command_uses_translation_service(self, mock_send):
        """Language command should use TranslationService for confirmation."""
        mock_send.return_value = ('msg_id', True)
        
        InboundCommandProcessor._handle_language(
            phone=self.guardian.phone_normalised,
            school=self.school,
            lang='en'
        )
        
        # Verify send was called with translated text
        assert mock_send.called
        call_args = mock_send.call_args
        sent_text = call_args.kwargs['text']
        
        # Should match translation key
        expected = TranslationService.get('language_switched', lang='en')
        assert sent_text == expected


class TranslationServiceIntegrationTests(TestCase):
    """Test TranslationService integration with command handlers."""

    def setUp(self):
        """Create test data."""
        self.school = School.objects.create(
            name='Test School',
            slug='test-school',
            district='Kampala',
            phone='0701234567',
            email='test@school.ug',
            school_type='primary',
        )
        self.class_group = ClassGroup.objects.create(
            school=self.school,
            name='P.5',
            level='P5',
        )
        self.student = Student.objects.create(
            school=self.school,
            student_id='SCH-2024-0001',
            first_name='John',
            last_name='Doe',
            gender='M',
            admission_date='2024-01-01',
            academic_year_admitted=2024,
            current_class=self.class_group,
        )

    def test_get_language_from_phone_returns_guardian_preference(self):
        """get_language_from_phone should return guardian's language."""
        guardian = Guardian.objects.create(
            student=self.student,
            first_name='Jane',
            last_name='Doe',
            relationship='Mother',
            phone='0701234567',
            is_primary=True,
            preferred_language='lg',
        )
        
        lang = TranslationService.get_language_from_phone(guardian.phone_normalised)
        assert lang == 'lg'

    def test_get_language_from_phone_defaults_english_for_unknown(self):
        """get_language_from_phone should default to English for unknown phones."""
        lang = TranslationService.get_language_from_phone('+256709999999')
        assert lang == 'en'

    def test_translation_service_menu_text_has_both_languages(self):
        """Translation service should have menu_text in both languages."""
        menu_en = TranslationService.get('menu_text', lang='en')
        menu_lg = TranslationService.get('menu_text', lang='lg')
        
        assert menu_en != ''
        assert menu_lg != ''
        assert menu_en != menu_lg
        assert 'Welcome to SchoolBridge' in menu_en
        assert 'Tusanyukidde kukusanga' in menu_lg

    def test_translation_service_language_switched_has_both_languages(self):
        """Translation service should have language_switched in both languages."""
        msg_en = TranslationService.get('language_switched', lang='en')
        msg_lg = TranslationService.get('language_switched', lang='lg')
        
        assert msg_en != ''
        assert msg_lg != ''
        assert msg_en != msg_lg
        assert 'Language switched to' in msg_en
        assert 'Olulimi lwaakyusibwa' in msg_lg
