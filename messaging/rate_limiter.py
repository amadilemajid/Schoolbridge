"""
US-A02: Rate Limiter for WhatsApp command spam prevention.
Limits guardians to 10 commands per 15-minute sliding window.
Uses Django cache (Redis in production) for high performance.
"""
import logging
from django.core.cache import cache
from django.utils import timezone
from datetime import timedelta

logger = logging.getLogger('messaging')


class RateLimiter:
    """
    Rate limiter for WhatsApp self-service commands.
    Prevents spam by limiting commands per phone number.
    """
    
    # Rate limit configuration
    MAX_COMMANDS = 10
    WINDOW_MINUTES = 15
    
    # Cache key prefix
    CACHE_PREFIX = 'ratelimit:whatsapp:'
    
    @classmethod
    def check_rate_limit(cls, phone):
        """
        Check if phone number has exceeded rate limit.
        
        Args:
            phone: Normalized phone number (e.g. '+256701234567')
        
        Returns:
            tuple: (is_allowed: bool, remaining: int, retry_after: int)
                - is_allowed: True if command should be processed
                - remaining: Number of commands remaining in window
                - retry_after: Seconds until rate limit resets (0 if allowed)
        """
        cache_key = cls._get_cache_key(phone)
        
        # Get current command timestamps from cache
        timestamps = cache.get(cache_key, [])
        
        # Remove timestamps outside the sliding window
        now = timezone.now()
        window_start = now - timedelta(minutes=cls.WINDOW_MINUTES)
        timestamps = [ts for ts in timestamps if ts > window_start]
        
        # Check if rate limit exceeded
        if len(timestamps) >= cls.MAX_COMMANDS:
            # Calculate retry_after from oldest timestamp
            oldest = min(timestamps)
            retry_after = int((oldest + timedelta(minutes=cls.WINDOW_MINUTES) - now).total_seconds())
            remaining = 0
            is_allowed = False
            
            logger.warning(
                f"Rate limit exceeded for {phone}: {len(timestamps)} commands in {cls.WINDOW_MINUTES} minutes"
            )
        else:
            # Add current timestamp
            timestamps.append(now)
            remaining = cls.MAX_COMMANDS - len(timestamps)
            retry_after = 0
            is_allowed = True
        
        # Update cache with TTL = window duration
        cache.set(cache_key, timestamps, timeout=cls.WINDOW_MINUTES * 60)
        
        return is_allowed, remaining, retry_after
    
    @classmethod
    def record_command(cls, phone, command=None):
        """
        Record a command execution for rate limiting.
        This is called AFTER successful command processing.
        
        Args:
            phone: Normalized phone number
            command: Optional command name for logging
        
        Note: 
            check_rate_limit() already records the timestamp,
            so this method is mainly for additional logging/metrics.
        """
        cache_key = cls._get_cache_key(phone)
        timestamps = cache.get(cache_key, [])
        
        logger.info(
            f"Command recorded: phone={phone} command={command or 'unknown'} "
            f"count={len(timestamps)}/{cls.MAX_COMMANDS}"
        )
    
    @classmethod
    def reset_limit(cls, phone):
        """
        Reset rate limit for a phone number.
        Used for testing or admin intervention.
        
        Args:
            phone: Normalized phone number
        """
        cache_key = cls._get_cache_key(phone)
        cache.delete(cache_key)
        logger.info(f"Rate limit reset for {phone}")
    
    @classmethod
    def get_remaining_commands(cls, phone):
        """
        Get number of commands remaining in current window.
        
        Args:
            phone: Normalized phone number
        
        Returns:
            int: Number of commands remaining (0 to MAX_COMMANDS)
        """
        cache_key = cls._get_cache_key(phone)
        timestamps = cache.get(cache_key, [])
        
        # Remove expired timestamps
        now = timezone.now()
        window_start = now - timedelta(minutes=cls.WINDOW_MINUTES)
        timestamps = [ts for ts in timestamps if ts > window_start]
        
        return max(0, cls.MAX_COMMANDS - len(timestamps))
    
    @classmethod
    def get_rate_limit_message(cls, lang='en'):
        """
        Get rate limit exceeded message in specified language.
        
        Args:
            lang: Language code ('en' or 'lg')
        
        Returns:
            str: Rate limit message
        """
        messages = {
            'en': (
                f"⚠️ *Too Many Requests*\n\n"
                f"You have exceeded the limit of {cls.MAX_COMMANDS} commands per {cls.WINDOW_MINUTES} minutes.\n"
                f"Please wait a few minutes and try again.\n\n"
                f"For urgent assistance, contact the school office."
            ),
            'lg': (
                f"⚠️ *Ebiragiro Bingi Nnyo*\n\n"
                f"Osusse ekipimo kya biragiro {cls.MAX_COMMANDS} mu dakiika {cls.WINDOW_MINUTES}.\n"
                f"Linda akaseera katono oddeyo okugezaako.\n\n"
                f"Bw'oba oyagala obuyambi obw'amangu, tukirira woofiisi y'essomero."
            ),
        }
        return messages.get(lang, messages['en'])
    
    @classmethod
    def _get_cache_key(cls, phone):
        """
        Generate cache key for phone number.
        
        Args:
            phone: Phone number
        
        Returns:
            str: Cache key
        """
        # Normalize phone to ensure consistent key
        phone = str(phone).strip().replace('+', '').replace(' ', '').replace('-', '')
        return f"{cls.CACHE_PREFIX}{phone}"
    
    @classmethod
    def get_stats(cls, phone):
        """
        Get rate limit statistics for a phone number.
        Used for monitoring and debugging.
        
        Args:
            phone: Normalized phone number
        
        Returns:
            dict: Statistics including count, remaining, window_start, window_end
        """
        cache_key = cls._get_cache_key(phone)
        timestamps = cache.get(cache_key, [])
        
        now = timezone.now()
        window_start = now - timedelta(minutes=cls.WINDOW_MINUTES)
        
        # Remove expired timestamps
        timestamps = [ts for ts in timestamps if ts > window_start]
        
        stats = {
            'phone': phone,
            'command_count': len(timestamps),
            'max_commands': cls.MAX_COMMANDS,
            'remaining': max(0, cls.MAX_COMMANDS - len(timestamps)),
            'window_minutes': cls.WINDOW_MINUTES,
            'window_start': window_start.isoformat() if timestamps else None,
            'window_end': (now + timedelta(minutes=cls.WINDOW_MINUTES)).isoformat() if timestamps else None,
            'oldest_command': min(timestamps).isoformat() if timestamps else None,
            'newest_command': max(timestamps).isoformat() if timestamps else None,
            'is_rate_limited': len(timestamps) >= cls.MAX_COMMANDS,
        }
        
        return stats
