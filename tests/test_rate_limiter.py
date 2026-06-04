"""
Unit tests for Rate Limiter (Task A2).
Validates rate limiting logic, sliding window, and message formatting.
"""
import pytest
from django.test import TestCase
from django.core.cache import cache
from django.utils import timezone
from datetime import timedelta
from messaging.rate_limiter import RateLimiter


class RateLimiterTests(TestCase):
    """Test suite for RateLimiter."""

    def setUp(self):
        """Clear cache before each test."""
        cache.clear()
        self.test_phone = '+256701234567'

    def tearDown(self):
        """Clear cache after each test."""
        cache.clear()

    def test_first_command_is_allowed(self):
        """First command from a phone should always be allowed."""
        is_allowed, remaining, retry_after = RateLimiter.check_rate_limit(self.test_phone)
        
        assert is_allowed is True
        assert remaining == RateLimiter.MAX_COMMANDS - 1
        assert retry_after == 0

    def test_commands_under_limit_are_allowed(self):
        """Commands under the limit should be allowed."""
        for i in range(5):
            is_allowed, remaining, retry_after = RateLimiter.check_rate_limit(self.test_phone)
            assert is_allowed is True
            assert remaining == RateLimiter.MAX_COMMANDS - (i + 1)
            assert retry_after == 0

    def test_command_at_limit_is_allowed(self):
        """The 10th command (at limit) should be allowed."""
        for i in range(RateLimiter.MAX_COMMANDS):
            is_allowed, remaining, retry_after = RateLimiter.check_rate_limit(self.test_phone)
            assert is_allowed is True

    def test_command_over_limit_is_blocked(self):
        """The 11th command should be blocked."""
        # Execute MAX_COMMANDS
        for _ in range(RateLimiter.MAX_COMMANDS):
            RateLimiter.check_rate_limit(self.test_phone)
        
        # 11th command should be blocked
        is_allowed, remaining, retry_after = RateLimiter.check_rate_limit(self.test_phone)
        
        assert is_allowed is False
        assert remaining == 0
        assert retry_after > 0

    def test_retry_after_is_calculated_correctly(self):
        """Retry after should be approximately WINDOW_MINUTES * 60 seconds."""
        # Execute MAX_COMMANDS
        for _ in range(RateLimiter.MAX_COMMANDS):
            RateLimiter.check_rate_limit(self.test_phone)
        
        # Check blocked command
        is_allowed, remaining, retry_after = RateLimiter.check_rate_limit(self.test_phone)
        
        # Should be close to 15 minutes (900 seconds), allow 5 second variance
        expected_retry = RateLimiter.WINDOW_MINUTES * 60
        assert abs(retry_after - expected_retry) <= 5

    def test_different_phones_have_separate_limits(self):
        """Different phone numbers should have independent rate limits."""
        phone1 = '+256701234567'
        phone2 = '+256709999999'
        
        # Max out phone1
        for _ in range(RateLimiter.MAX_COMMANDS):
            RateLimiter.check_rate_limit(phone1)
        
        # phone1 should be blocked
        is_allowed1, _, _ = RateLimiter.check_rate_limit(phone1)
        assert is_allowed1 is False
        
        # phone2 should still be allowed
        is_allowed2, remaining2, _ = RateLimiter.check_rate_limit(phone2)
        assert is_allowed2 is True
        assert remaining2 == RateLimiter.MAX_COMMANDS - 1

    def test_reset_limit_clears_rate_limit(self):
        """reset_limit should clear the rate limit for a phone."""
        # Max out the limit
        for _ in range(RateLimiter.MAX_COMMANDS):
            RateLimiter.check_rate_limit(self.test_phone)
        
        # Should be blocked
        is_allowed, _, _ = RateLimiter.check_rate_limit(self.test_phone)
        assert is_allowed is False
        
        # Reset limit
        RateLimiter.reset_limit(self.test_phone)
        
        # Should be allowed again
        is_allowed, remaining, _ = RateLimiter.check_rate_limit(self.test_phone)
        assert is_allowed is True
        assert remaining == RateLimiter.MAX_COMMANDS - 1

    def test_get_remaining_commands_returns_correct_count(self):
        """get_remaining_commands should return correct count."""
        # Initially should have MAX_COMMANDS available
        remaining = RateLimiter.get_remaining_commands(self.test_phone)
        assert remaining == RateLimiter.MAX_COMMANDS
        
        # After 3 commands, should have MAX_COMMANDS - 3
        for _ in range(3):
            RateLimiter.check_rate_limit(self.test_phone)
        
        remaining = RateLimiter.get_remaining_commands(self.test_phone)
        assert remaining == RateLimiter.MAX_COMMANDS - 3

    def test_get_remaining_commands_for_blocked_phone(self):
        """get_remaining_commands should return 0 for blocked phone."""
        # Max out the limit
        for _ in range(RateLimiter.MAX_COMMANDS):
            RateLimiter.check_rate_limit(self.test_phone)
        
        remaining = RateLimiter.get_remaining_commands(self.test_phone)
        assert remaining == 0

    def test_record_command_logs_command(self):
        """record_command should log command execution."""
        # This primarily tests that the method doesn't crash
        RateLimiter.check_rate_limit(self.test_phone)
        RateLimiter.record_command(self.test_phone, 'BALANCE')
        # No assertion needed - just verify no exception

    def test_get_rate_limit_message_english(self):
        """get_rate_limit_message should return English message."""
        message = RateLimiter.get_rate_limit_message('en')
        
        assert 'Too Many Requests' in message
        assert str(RateLimiter.MAX_COMMANDS) in message
        assert str(RateLimiter.WINDOW_MINUTES) in message
        assert 'contact the school office' in message

    def test_get_rate_limit_message_luganda(self):
        """get_rate_limit_message should return Luganda message."""
        message = RateLimiter.get_rate_limit_message('lg')
        
        assert 'Ebiragiro Bingi' in message
        assert str(RateLimiter.MAX_COMMANDS) in message
        assert str(RateLimiter.WINDOW_MINUTES) in message

    def test_get_rate_limit_message_invalid_lang_defaults_english(self):
        """get_rate_limit_message should default to English for invalid language."""
        message = RateLimiter.get_rate_limit_message('fr')
        
        assert 'Too Many Requests' in message

    def test_cache_key_normalization(self):
        """Phone numbers should be normalized for consistent cache keys."""
        phone1 = '+256701234567'
        phone2 = '256701234567'
        phone3 = '+256 701 234 567'
        phone4 = '+256-701-234-567'
        
        key1 = RateLimiter._get_cache_key(phone1)
        key2 = RateLimiter._get_cache_key(phone2)
        key3 = RateLimiter._get_cache_key(phone3)
        key4 = RateLimiter._get_cache_key(phone4)
        
        # All should produce same key
        assert key1 == key2 == key3 == key4

    def test_get_stats_returns_correct_data(self):
        """get_stats should return accurate statistics."""
        # Execute 3 commands
        for _ in range(3):
            RateLimiter.check_rate_limit(self.test_phone)
        
        stats = RateLimiter.get_stats(self.test_phone)
        
        assert stats['phone'] == self.test_phone
        assert stats['command_count'] == 3
        assert stats['max_commands'] == RateLimiter.MAX_COMMANDS
        assert stats['remaining'] == RateLimiter.MAX_COMMANDS - 3
        assert stats['window_minutes'] == RateLimiter.WINDOW_MINUTES
        assert stats['is_rate_limited'] is False
        assert stats['oldest_command'] is not None
        assert stats['newest_command'] is not None

    def test_get_stats_for_rate_limited_phone(self):
        """get_stats should show is_rate_limited=True when blocked."""
        # Max out the limit
        for _ in range(RateLimiter.MAX_COMMANDS):
            RateLimiter.check_rate_limit(self.test_phone)
        
        stats = RateLimiter.get_stats(self.test_phone)
        
        assert stats['command_count'] == RateLimiter.MAX_COMMANDS
        assert stats['remaining'] == 0
        assert stats['is_rate_limited'] is True

    def test_get_stats_for_new_phone(self):
        """get_stats should return clean data for new phone."""
        stats = RateLimiter.get_stats(self.test_phone)
        
        assert stats['command_count'] == 0
        assert stats['remaining'] == RateLimiter.MAX_COMMANDS
        assert stats['is_rate_limited'] is False
        assert stats['oldest_command'] is None
        assert stats['newest_command'] is None

    def test_sliding_window_expires_old_commands(self):
        """Commands older than WINDOW_MINUTES should be dropped."""
        # This test requires time manipulation - we'll test the logic
        # In production, old timestamps are filtered out automatically
        
        # Execute 5 commands
        for _ in range(5):
            RateLimiter.check_rate_limit(self.test_phone)
        
        # Manually manipulate cache to add old timestamp
        cache_key = RateLimiter._get_cache_key(self.test_phone)
        timestamps = cache.get(cache_key, [])
        
        # Add a timestamp from 20 minutes ago (outside window)
        old_timestamp = timezone.now() - timedelta(minutes=20)
        timestamps.insert(0, old_timestamp)
        cache.set(cache_key, timestamps, timeout=RateLimiter.WINDOW_MINUTES * 60)
        
        # Check remaining - should not count the old timestamp
        remaining = RateLimiter.get_remaining_commands(self.test_phone)
        assert remaining == RateLimiter.MAX_COMMANDS - 5  # Only 5 recent commands counted

    def test_concurrent_checks_dont_exceed_limit(self):
        """Multiple concurrent checks should respect the limit."""
        # Simulate near-simultaneous checks
        results = []
        for _ in range(RateLimiter.MAX_COMMANDS + 5):
            is_allowed, remaining, retry_after = RateLimiter.check_rate_limit(self.test_phone)
            results.append(is_allowed)
        
        # First MAX_COMMANDS should be allowed
        assert all(results[:RateLimiter.MAX_COMMANDS])
        
        # Remaining should be blocked
        assert not any(results[RateLimiter.MAX_COMMANDS:])

    def test_rate_limiter_configuration(self):
        """Verify rate limiter configuration values."""
        assert RateLimiter.MAX_COMMANDS == 10
        assert RateLimiter.WINDOW_MINUTES == 15
        assert RateLimiter.CACHE_PREFIX == 'ratelimit:whatsapp:'

    def test_check_rate_limit_updates_cache_ttl(self):
        """check_rate_limit should update cache TTL."""
        # Execute command
        RateLimiter.check_rate_limit(self.test_phone)
        
        # Verify cache key exists
        cache_key = RateLimiter._get_cache_key(self.test_phone)
        timestamps = cache.get(cache_key)
        
        assert timestamps is not None
        assert len(timestamps) == 1

    def test_rate_limit_message_contains_key_info(self):
        """Rate limit messages should contain all required information."""
        for lang in ['en', 'lg']:
            message = RateLimiter.get_rate_limit_message(lang)
            
            # Should contain the limit numbers
            assert str(RateLimiter.MAX_COMMANDS) in message
            assert str(RateLimiter.WINDOW_MINUTES) in message
            
            # Should have warning emoji
            assert '⚠️' in message
