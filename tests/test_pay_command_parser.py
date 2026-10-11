"""
Unit tests for PAY command parsing (Task 1 - US-A03 Part 1).
Validates PAY text/numeric parsing, amount extraction, and sibling identifier handling.
"""
from django.test import TestCase
from messaging.services import InboundCommandProcessor


class PayCommandParserTests(TestCase):
    """Test suite for PAY command parsing in InboundCommandProcessor.parse_command()."""

    def test_pay_text_no_args(self):
        """PAY without arguments should parse command with empty args."""
        cmd, args = InboundCommandProcessor.parse_command('PAY')
        assert cmd == 'PAY'
        assert args == {}

    def test_pay_numeric_shortcut(self):
        """Numeric shortcut 8 should map to PAY."""
        cmd, args = InboundCommandProcessor.parse_command('8')
        assert cmd == 'PAY'
        assert args == {}

    def test_pay_with_amount_text(self):
        """PAY 150000 should extract amount."""
        cmd, args = InboundCommandProcessor.parse_command('PAY 150000')
        assert cmd == 'PAY'
        assert args == {'amount': '150000'}

    def test_pay_with_amount_numeric(self):
        """8 250000 should extract amount via numeric shortcut."""
        cmd, args = InboundCommandProcessor.parse_command('8 250000')
        assert cmd == 'PAY'
        assert args == {'amount': '250000'}

    def test_pay_with_amount_and_identifier_text(self):
        """PAY 150000 John should extract amount and identifier."""
        cmd, args = InboundCommandProcessor.parse_command('PAY 150000 John')
        assert cmd == 'PAY'
        assert args == {'amount': '150000', 'identifier': 'JOHN'}

    def test_pay_with_amount_and_identifier_numeric(self):
        """8 250000 Alice should extract amount and identifier via numeric shortcut."""
        cmd, args = InboundCommandProcessor.parse_command('8 250000 Alice')
        assert cmd == 'PAY'
        assert args == {'amount': '250000', 'identifier': 'ALICE'}

    def test_pay_lowercase_normalized(self):
        """Lowercase 'pay 100000' should normalize to PAY with amount."""
        cmd, args = InboundCommandProcessor.parse_command('pay 100000')
        assert cmd == 'PAY'
        assert args == {'amount': '100000'}

    def test_pay_mixed_case_normalized(self):
        """Mixed case 'Pay 100000 alice' should normalize correctly."""
        cmd, args = InboundCommandProcessor.parse_command('Pay 100000 alice')
        assert cmd == 'PAY'
        assert args == {'amount': '100000', 'identifier': 'ALICE'}

    def test_pay_extra_spaces(self):
        """PAY with extra spaces should parse correctly."""
        cmd, args = InboundCommandProcessor.parse_command('  PAY   200000   ')
        assert cmd == 'PAY'
        assert args == {'amount': '200000'}

    def test_pay_multi_word_identifier(self):
        """PAY with multi-word identifier (full name) should concatenate."""
        cmd, args = InboundCommandProcessor.parse_command('PAY 500000 John Doe')
        assert cmd == 'PAY'
        assert args == {'amount': '500000', 'identifier': 'JOHN DOE'}

    def test_pay_identifier_case_preserved_uppercase(self):
        """Identifier should be uppercased due to text.upper() normalization."""
        cmd, args = InboundCommandProcessor.parse_command('pay 100000 Maria Nakato')
        assert cmd == 'PAY'
        assert args['identifier'] == 'MARIA NAKATO'

    def test_pay_is_in_commands_list(self):
        """PAY should be present in the COMMANDS list."""
        assert 'PAY' in InboundCommandProcessor.COMMANDS
