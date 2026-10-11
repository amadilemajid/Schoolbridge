"""
Tests for rate limiting integration in process_inbound_command.
Task 3: Webhook Hardening - prevents spam from individual phone numbers.
"""
import uuid
from unittest.mock import patch, MagicMock
from django.test import TestCase
from messaging.models import InboundMessage
from schools.models import School


class InboundRateLimitingTests(TestCase):
    """Tests for rate limiting in the inbound command processing pipeline."""

    def setUp(self):
        self.school = School.objects.create(
            name='Rate Limit Test School', slug='rate-limit-test',
            district='Kampala', phone='0700000000',
            email='admin@school.ug', school_type='primary'
        )

    def _create_inbound(self, phone='256701234567', command='BALANCE'):
        return InboundMessage.objects.create(
            school=self.school,
            from_phone=phone,
            raw_message=command,
            command=command,
            whatsapp_message_id=str(uuid.uuid4()),
            processed=False,
            response_sent=False,
        )

    @patch('messaging.services.WhatsAppService')
    @patch('messaging.rate_limiter.RateLimiter')
    @patch('messaging.translation_service.TranslationService')
    @patch('messaging.services.InboundCommandProcessor')
    def test_rate_limited_phone_gets_warning(self, mock_icp, mock_ts, mock_rl, mock_wa):
        """A rate-limited phone receives a warning and command is not processed."""
        from messaging.tasks import process_inbound_command

        msg = self._create_inbound()

        # Rate limit exceeded
        mock_rl.check_rate_limit.return_value = (False, 0, 120)
        mock_ts.get_language_from_phone.return_value = 'en'
        mock_rl.get_rate_limit_message.return_value = 'Too many requests.'
        mock_wa.send_text_message.return_value = ('msg_id', True)

        process_inbound_command(str(msg.id))

        # Verify warning was sent
        mock_wa.send_text_message.assert_called_once_with(
            to_phone='256701234567', text='Too many requests.'
        )
        # Verify InboundCommandProcessor.process was NOT called
        mock_icp.process.assert_not_called()

        # Verify message was marked as processed
        msg.refresh_from_db()
        self.assertTrue(msg.processed)
        self.assertTrue(msg.response_sent)

    @patch('messaging.services.WhatsAppService')
    @patch('messaging.rate_limiter.RateLimiter')
    @patch('messaging.translation_service.TranslationService')
    @patch('messaging.services.InboundCommandProcessor')
    def test_rate_limited_luganda_user_gets_luganda_warning(self, mock_icp, mock_ts, mock_rl, mock_wa):
        """A Luganda-speaking rate-limited user gets Luganda warning."""
        from messaging.tasks import process_inbound_command

        msg = self._create_inbound(phone='256702345678')

        mock_rl.check_rate_limit.return_value = (False, 0, 60)
        mock_ts.get_language_from_phone.return_value = 'lg'
        mock_rl.get_rate_limit_message.return_value = 'Ebiragiro Bingi Nnyo'
        mock_wa.send_text_message.return_value = ('msg_id', True)

        process_inbound_command(str(msg.id))

        mock_rl.get_rate_limit_message.assert_called_once_with('lg')
        text = mock_wa.send_text_message.call_args[1]['text']
        assert 'Ebiragiro Bingi Nnyo' in text

    @patch('messaging.rate_limiter.RateLimiter')
    @patch('messaging.services.InboundCommandProcessor')
    def test_normal_phone_passes_rate_check(self, mock_icp, mock_rl):
        """A phone within rate limits proceeds to normal processing."""
        from messaging.tasks import process_inbound_command

        msg = self._create_inbound()

        mock_rl.check_rate_limit.return_value = (True, 8, 0)

        process_inbound_command(str(msg.id))

        # Verify InboundCommandProcessor.process was called
        mock_icp.process.assert_called_once()

    @patch('messaging.rate_limiter.RateLimiter')
    @patch('messaging.services.InboundCommandProcessor')
    def test_already_processed_skips_rate_check(self, mock_icp, mock_rl):
        """Already processed messages skip rate limiting entirely."""
        from messaging.tasks import process_inbound_command

        msg = self._create_inbound()
        msg.processed = True
        msg.save()

        process_inbound_command(str(msg.id))

        # Rate limiter should not be called
        mock_rl.check_rate_limit.assert_not_called()
        mock_icp.process.assert_not_called()
