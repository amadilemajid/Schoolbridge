"""
Unit tests for Translation Service (Task A1).
Validates all translation keys exist in both English and Luganda.
"""
import pytest
from django.test import TestCase
from messaging.translation_service import TranslationService
from students.models import Guardian, Student, ClassGroup
from schools.models import School


class TranslationServiceTests(TestCase):
    """Test suite for TranslationService."""

    def setUp(self):
        """Create test school and student with guardian."""
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

    def test_all_keys_have_english(self):
        """All translation keys must have English variant."""
        for key, translations in TranslationService.TRANSLATIONS.items():
            assert 'en' in translations, f"Key '{key}' missing English translation"

    def test_all_keys_have_luganda(self):
        """All translation keys must have Luganda variant."""
        for key, translations in TranslationService.TRANSLATIONS.items():
            assert 'lg' in translations, f"Key '{key}' missing Luganda translation"

    def test_get_translation_english(self):
        """Get method returns English translation."""
        text = TranslationService.get('menu_text', lang='en')
        assert 'Welcome to SchoolBridge' in text
        assert '1️⃣ BALANCE' in text

    def test_get_translation_luganda(self):
        """Get method returns Luganda translation."""
        text = TranslationService.get('menu_text', lang='lg')
        assert 'Tusanyukidde kukusanga' in text
        assert '1️⃣ BALANCE' in text

    def test_get_translation_with_params(self):
        """Get method formats translation with parameters."""
        text = TranslationService.get(
            'balance_detail',
            lang='en',
            icon='✅',
            student_name='John Doe',
            class_name='P.5',
            total=500000,
            paid=300000,
            balance=200000,
        )
        assert 'John Doe' in text
        assert 'P.5' in text
        assert '500,000' in text
        assert '200,000' in text

    def test_get_translation_luganda_with_params(self):
        """Get method formats Luganda translation with parameters."""
        text = TranslationService.get(
            'balance_detail',
            lang='lg',
            icon='⚠️',
            student_name='John Doe',
            class_name='P.5',
            total=500000,
            paid=300000,
            balance=200000,
        )
        assert 'John Doe' in text
        assert 'P.5' in text
        assert 'Ekkiraalagana' in text
        assert '500,000' in text

    def test_get_translation_invalid_lang_defaults_to_english(self):
        """Invalid language code defaults to English."""
        text = TranslationService.get('menu_text', lang='fr')
        assert 'Welcome to SchoolBridge' in text

    def test_get_translation_missing_key_returns_empty(self):
        """Missing translation key returns empty string."""
        text = TranslationService.get('nonexistent_key', lang='en')
        assert text == ''

    def test_get_language_from_guardian_english(self):
        """get_language returns guardian's preferred language."""
        lang = TranslationService.get_language(self.guardian_en)
        assert lang == 'en'

    def test_get_language_from_guardian_luganda(self):
        """get_language returns Luganda when set."""
        self.guardian_en.preferred_language = 'lg'
        self.guardian_en.save()
        lang = TranslationService.get_language(self.guardian_en)
        assert lang == 'lg'

    def test_get_language_from_guardian_defaults_to_english(self):
        """get_language defaults to English if invalid language."""
        self.guardian_en.preferred_language = 'fr'
        self.guardian_en.save()
        lang = TranslationService.get_language(self.guardian_en)
        assert lang == 'en'

    def test_get_language_from_phone(self):
        """get_language_from_phone looks up guardian by phone."""
        lang = TranslationService.get_language_from_phone('+256701234567')
        assert lang == 'en'

    def test_get_language_from_phone_luganda(self):
        """get_language_from_phone returns Luganda when set."""
        self.guardian_en.preferred_language = 'lg'
        self.guardian_en.save()
        lang = TranslationService.get_language_from_phone('+256701234567')
        assert lang == 'lg'

    def test_get_language_from_phone_not_found_defaults_english(self):
        """get_language_from_phone defaults to English if phone not found."""
        lang = TranslationService.get_language_from_phone('+256709999999')
        assert lang == 'en'

    def test_timetable_translations(self):
        """All timetable command translations exist."""
        assert TranslationService.get('timetable_header', lang='en')
        assert TranslationService.get('timetable_header', lang='lg')
        assert TranslationService.get('timetable_not_available', lang='en')
        assert TranslationService.get('timetable_not_available', lang='lg')

    def test_results_translations(self):
        """All results command translations exist."""
        assert TranslationService.get('results_header', lang='en')
        assert TranslationService.get('results_header', lang='lg')
        assert TranslationService.get('results_detail', lang='en')
        assert TranslationService.get('results_detail', lang='lg')

    def test_balance_translations(self):
        """All balance command translations exist."""
        assert TranslationService.get('balance_header', lang='en')
        assert TranslationService.get('balance_header', lang='lg')
        assert TranslationService.get('balance_detail', lang='en')
        assert TranslationService.get('balance_detail', lang='lg')

    def test_attend_translations(self):
        """All attendance command translations exist."""
        assert TranslationService.get('attend_header', lang='en')
        assert TranslationService.get('attend_header', lang='lg')
        assert TranslationService.get('attend_detail', lang='en')
        assert TranslationService.get('attend_detail', lang='lg')

    def test_menu_translations(self):
        """Menu command has both translations."""
        assert TranslationService.get('menu_text', lang='en')
        assert TranslationService.get('menu_text', lang='lg')

    def test_language_switched_translations(self):
        """Language switch confirmation has both translations."""
        assert TranslationService.get('language_switched', lang='en')
        assert TranslationService.get('language_switched', lang='lg')

    def test_common_message_translations(self):
        """Common messages have both translations."""
        assert TranslationService.get('not_registered', lang='en')
        assert TranslationService.get('not_registered', lang='lg')
        assert TranslationService.get('help_suffix', lang='en')
        assert TranslationService.get('help_suffix', lang='lg')
        assert TranslationService.get('unknown_command', lang='en')
        assert TranslationService.get('unknown_command', lang='lg')

    def test_format_numbers_with_commas(self):
        """Number formatting includes thousand separators."""
        text = TranslationService.get(
            'balance_detail',
            lang='en',
            icon='✅',
            student_name='Test',
            class_name='P.5',
            total=1500000,
            paid=1000000,
            balance=500000,
        )
        assert '1,500,000' in text
        assert '1,000,000' in text
        assert '500,000' in text
