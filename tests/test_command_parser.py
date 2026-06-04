"""
Unit tests for Command Parser (Task A3).
Validates numeric shortcuts, argument parsing, and edge cases.
"""
import pytest
from django.test import TestCase
from messaging.services import InboundCommandProcessor


class CommandParserTests(TestCase):
    """Test suite for InboundCommandProcessor.parse_command()."""

    def test_parse_balance_text(self):
        """BALANCE text command should parse correctly."""
        cmd, args = InboundCommandProcessor.parse_command('BALANCE')
        assert cmd == 'BALANCE'
        assert args == {}

    def test_parse_balance_number(self):
        """Numeric shortcut 1 should map to BALANCE."""
        cmd, args = InboundCommandProcessor.parse_command('1')
        assert cmd == 'BALANCE'
        assert args == {}

    def test_parse_results_text(self):
        """RESULTS text command should parse correctly."""
        cmd, args = InboundCommandProcessor.parse_command('RESULTS')
        assert cmd == 'RESULTS'
        assert args == {}

    def test_parse_results_number(self):
        """Numeric shortcut 2 should map to RESULTS."""
        cmd, args = InboundCommandProcessor.parse_command('2')
        assert cmd == 'RESULTS'
        assert args == {}

    def test_parse_attend_text(self):
        """ATTEND text command should parse correctly."""
        cmd, args = InboundCommandProcessor.parse_command('ATTEND')
        assert cmd == 'ATTEND'
        assert args == {}

    def test_parse_attend_number(self):
        """Numeric shortcut 3 should map to ATTEND."""
        cmd, args = InboundCommandProcessor.parse_command('3')
        assert cmd == 'ATTEND'
        assert args == {}

    def test_parse_receipt_text(self):
        """RECEIPT text command should parse correctly."""
        cmd, args = InboundCommandProcessor.parse_command('RECEIPT')
        assert cmd == 'RECEIPT'
        assert args == {}

    def test_parse_receipt_number(self):
        """Numeric shortcut 4 should map to RECEIPT."""
        cmd, args = InboundCommandProcessor.parse_command('4')
        assert cmd == 'RECEIPT'
        assert args == {}

    def test_parse_receipt_with_date_text(self):
        """RECEIPT with date argument should parse correctly."""
        cmd, args = InboundCommandProcessor.parse_command('RECEIPT 2024-01-15')
        assert cmd == 'RECEIPT'
        assert args == {'date': '2024-01-15'}

    def test_parse_receipt_with_date_number(self):
        """Numeric 4 with date argument should parse correctly."""
        cmd, args = InboundCommandProcessor.parse_command('4 2024-01-15')
        assert cmd == 'RECEIPT'
        assert args == {'date': '2024-01-15'}

    def test_parse_timetable_text(self):
        """TIMETABLE text command should parse correctly."""
        cmd, args = InboundCommandProcessor.parse_command('TIMETABLE')
        assert cmd == 'TIMETABLE'
        assert args == {}

    def test_parse_timetable_number(self):
        """Numeric shortcut 5 should map to TIMETABLE."""
        cmd, args = InboundCommandProcessor.parse_command('5')
        assert cmd == 'TIMETABLE'
        assert args == {}

    def test_parse_plan_text(self):
        """PLAN text command should parse correctly."""
        cmd, args = InboundCommandProcessor.parse_command('PLAN')
        assert cmd == 'PLAN'
        assert args == {}

    def test_parse_plan_number(self):
        """Numeric shortcut 6 should map to PLAN."""
        cmd, args = InboundCommandProcessor.parse_command('6')
        assert cmd == 'PLAN'
        assert args == {}

    def test_parse_absent_text(self):
        """ABSENT text command should parse correctly."""
        cmd, args = InboundCommandProcessor.parse_command('ABSENT')
        assert cmd == 'ABSENT'
        assert args == {}

    def test_parse_absent_number(self):
        """Numeric shortcut 7 should map to ABSENT."""
        cmd, args = InboundCommandProcessor.parse_command('7')
        assert cmd == 'ABSENT'
        assert args == {}

    def test_parse_absent_with_date_text(self):
        """ABSENT with date should parse correctly."""
        cmd, args = InboundCommandProcessor.parse_command('ABSENT 2024-01-15')
        assert cmd == 'ABSENT'
        assert args == {'date': '2024-01-15', 'reason': ''}

    def test_parse_absent_with_date_number(self):
        """Numeric 7 with date should parse correctly."""
        cmd, args = InboundCommandProcessor.parse_command('7 2024-01-15')
        assert cmd == 'ABSENT'
        assert args == {'date': '2024-01-15', 'reason': ''}

    def test_parse_absent_with_date_and_reason_text(self):
        """ABSENT with date and reason should parse correctly."""
        cmd, args = InboundCommandProcessor.parse_command('ABSENT 2024-01-15 Sick')
        assert cmd == 'ABSENT'
        assert args == {'date': '2024-01-15', 'reason': 'SICK'}

    def test_parse_absent_with_date_and_multi_word_reason(self):
        """ABSENT with multi-word reason should parse correctly."""
        cmd, args = InboundCommandProcessor.parse_command('ABSENT 2024-01-15 Doctor appointment')
        assert cmd == 'ABSENT'
        assert args == {'date': '2024-01-15', 'reason': 'DOCTOR APPOINTMENT'}

    def test_parse_absent_with_date_and_reason_number(self):
        """Numeric 7 with date and reason should parse correctly."""
        cmd, args = InboundCommandProcessor.parse_command('7 2024-01-15 Sick')
        assert cmd == 'ABSENT'
        assert args == {'date': '2024-01-15', 'reason': 'SICK'}

    def test_parse_help_text(self):
        """HELP text command should parse correctly."""
        cmd, args = InboundCommandProcessor.parse_command('HELP')
        assert cmd == 'HELP'
        assert args == {}

    def test_parse_menu_text(self):
        """MENU text command should parse correctly."""
        cmd, args = InboundCommandProcessor.parse_command('MENU')
        assert cmd == 'MENU'
        assert args == {}

    def test_parse_luganda_text(self):
        """LUGANDA text command should parse correctly."""
        cmd, args = InboundCommandProcessor.parse_command('LUGANDA')
        assert cmd == 'LUGANDA'
        assert args == {}

    def test_parse_english_text(self):
        """ENGLISH text command should parse correctly."""
        cmd, args = InboundCommandProcessor.parse_command('ENGLISH')
        assert cmd == 'ENGLISH'
        assert args == {}

    def test_parse_lowercase_command(self):
        """Lowercase commands should be converted to uppercase."""
        cmd, args = InboundCommandProcessor.parse_command('balance')
        assert cmd == 'BALANCE'
        assert args == {}

    def test_parse_mixed_case_command(self):
        """Mixed case commands should be converted to uppercase."""
        cmd, args = InboundCommandProcessor.parse_command('BaLaNcE')
        assert cmd == 'BALANCE'
        assert args == {}

    def test_parse_command_with_leading_whitespace(self):
        """Commands with leading whitespace should be trimmed."""
        cmd, args = InboundCommandProcessor.parse_command('  BALANCE')
        assert cmd == 'BALANCE'
        assert args == {}

    def test_parse_command_with_trailing_whitespace(self):
        """Commands with trailing whitespace should be trimmed."""
        cmd, args = InboundCommandProcessor.parse_command('BALANCE  ')
        assert cmd == 'BALANCE'
        assert args == {}

    def test_parse_command_with_multiple_spaces(self):
        """Commands with multiple spaces should parse correctly."""
        cmd, args = InboundCommandProcessor.parse_command('RECEIPT   2024-01-15')
        assert cmd == 'RECEIPT'
        assert args == {'date': '2024-01-15'}

    def test_parse_empty_string(self):
        """Empty string should return UNKNOWN."""
        cmd, args = InboundCommandProcessor.parse_command('')
        assert cmd == 'UNKNOWN'
        assert args == {}

    def test_parse_whitespace_only(self):
        """Whitespace-only string should return UNKNOWN."""
        cmd, args = InboundCommandProcessor.parse_command('   ')
        assert cmd == 'UNKNOWN'
        assert args == {}

    def test_parse_invalid_command(self):
        """Invalid command should return UNKNOWN."""
        cmd, args = InboundCommandProcessor.parse_command('INVALID')
        assert cmd == 'UNKNOWN'
        assert args == {}

    def test_parse_invalid_number(self):
        """Invalid number should return UNKNOWN."""
        cmd, args = InboundCommandProcessor.parse_command('8')
        assert cmd == 'UNKNOWN'
        assert args == {}

    def test_parse_invalid_number_zero(self):
        """Zero should return UNKNOWN."""
        cmd, args = InboundCommandProcessor.parse_command('0')
        assert cmd == 'UNKNOWN'
        assert args == {}

    def test_parse_invalid_number_nine(self):
        """Nine should return UNKNOWN."""
        cmd, args = InboundCommandProcessor.parse_command('9')
        assert cmd == 'UNKNOWN'
        assert args == {}

    def test_parse_random_text(self):
        """Random text should return UNKNOWN."""
        cmd, args = InboundCommandProcessor.parse_command('hello world')
        assert cmd == 'UNKNOWN'
        assert args == {}

    def test_numeric_shortcuts_completeness(self):
        """All numeric shortcuts 1-7 should map to commands."""
        expected_mapping = {
            '1': 'BALANCE',
            '2': 'RESULTS',
            '3': 'ATTEND',
            '4': 'RECEIPT',
            '5': 'TIMETABLE',
            '6': 'PLAN',
            '7': 'ABSENT',
        }
        
        for number, expected_cmd in expected_mapping.items():
            cmd, args = InboundCommandProcessor.parse_command(number)
            assert cmd == expected_cmd, f"Number {number} should map to {expected_cmd}"

    def test_all_text_commands_parseable(self):
        """All COMMANDS should be parseable as text."""
        commands = InboundCommandProcessor.COMMANDS
        
        for command in commands:
            cmd, args = InboundCommandProcessor.parse_command(command)
            assert cmd == command, f"Command {command} should parse to itself"

    def test_receipt_preserves_date_format(self):
        """RECEIPT should preserve date format exactly as provided."""
        cmd, args = InboundCommandProcessor.parse_command('RECEIPT 2024-12-31')
        assert args['date'] == '2024-12-31'

    def test_absent_preserves_date_format(self):
        """ABSENT should preserve date format exactly as provided."""
        cmd, args = InboundCommandProcessor.parse_command('ABSENT 2024-12-31 Sick')
        assert args['date'] == '2024-12-31'

    def test_absent_reason_preserves_case(self):
        """ABSENT reason should preserve original case."""
        cmd, args = InboundCommandProcessor.parse_command('absent 2024-01-15 Doctor Appointment')
        # Command is uppercase but reason should preserve case
        assert args['reason'] == 'DOCTOR APPOINTMENT'  # Due to text.upper() at start

    def test_command_list_contains_all_expected_commands(self):
        """COMMANDS list should contain all expected commands."""
        expected_commands = [
            'BALANCE', 'RECEIPT', 'HELP', 'PLAN', 'ABSENT',
            'RESULTS', 'ATTEND', 'TIMETABLE', 'MENU', 'LUGANDA', 'ENGLISH',
        ]
        
        commands = InboundCommandProcessor.COMMANDS
        
        for expected in expected_commands:
            assert expected in commands, f"{expected} should be in COMMANDS list"

    def test_no_unmapped_numbers(self):
        """Numbers outside 1-7 should not be valid commands."""
        invalid_numbers = ['0', '8', '9', '10', '99', '-1']
        
        for num in invalid_numbers:
            cmd, args = InboundCommandProcessor.parse_command(num)
            assert cmd == 'UNKNOWN', f"Number {num} should return UNKNOWN"

    def test_special_characters_return_unknown(self):
        """Special characters should return UNKNOWN."""
        special_inputs = ['!', '@', '#', '$', '%', '^', '&', '*']
        
        for special in special_inputs:
            cmd, args = InboundCommandProcessor.parse_command(special)
            assert cmd == 'UNKNOWN', f"Special char {special} should return UNKNOWN"
