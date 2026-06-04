# Task A2: Rate Limiter - Manual Testing Guide

## Overview
Rate Limiter prevents WhatsApp command spam by limiting users to 10 commands per 15-minute sliding window.

## Prerequisites
1. Django development environment running
2. Redis or cache backend configured
3. Python shell access (`python manage.py shell`)

---

## Test 1: Basic Rate Limiting

### Test 1.1: First Command (Always Allowed)
```python
from messaging.rate_limiter import RateLimiter

phone = '+256701234567'
is_allowed, remaining, retry_after = RateLimiter.check_rate_limit(phone)

print(f"Allowed: {is_allowed}")
print(f"Remaining: {remaining}")
print(f"Retry after: {retry_after} seconds")
```

**Expected Result:**
```
Allowed: True
Remaining: 9
Retry after: 0 seconds
```

### Test 1.2: Multiple Commands Under Limit
```python
for i in range(1, 6):
    is_allowed, remaining, retry_after = RateLimiter.check_rate_limit(phone)
    print(f"Command {i}: Allowed={is_allowed}, Remaining={remaining}")
```

**Expected Result:**
```
Command 1: Allowed=True, Remaining=9
Command 2: Allowed=True, Remaining=8
Command 3: Allowed=True, Remaining=7
Command 4: Allowed=True, Remaining=6
Command 5: Allowed=True, Remaining=5
```

---

## Test 2: Rate Limit Enforcement

### Test 2.1: Reach the Limit (10 Commands)
```python
from messaging.rate_limiter import RateLimiter
from django.core.cache import cache

# Clear any existing rate limit
cache.clear()

phone = '+256701234567'

# Execute 10 commands
for i in range(1, 11):
    is_allowed, remaining, retry_after = RateLimiter.check_rate_limit(phone)
    print(f"Command {i}: Allowed={is_allowed}, Remaining={remaining}")
```

**Expected Result:**
```
Command 1: Allowed=True, Remaining=9
Command 2: Allowed=True, Remaining=8
...
Command 9: Allowed=True, Remaining=1
Command 10: Allowed=True, Remaining=0
```

### Test 2.2: Exceed the Limit (11th Command Blocked)
```python
# 11th command should be blocked
is_allowed, remaining, retry_after = RateLimiter.check_rate_limit(phone)

print(f"11th Command:")
print(f"  Allowed: {is_allowed}")
print(f"  Remaining: {remaining}")
print(f"  Retry after: {retry_after} seconds ({retry_after/60:.1f} minutes)")
```

**Expected Result:**
```
11th Command:
  Allowed: False
  Remaining: 0
  Retry after: 900 seconds (15.0 minutes)
```

---

## Test 3: Independent Rate Limits

### Test 3.1: Different Phones Have Separate Limits
```python
from django.core.cache import cache
cache.clear()

phone1 = '+256701234567'
phone2 = '+256709999999'

# Max out phone1
for _ in range(10):
    RateLimiter.check_rate_limit(phone1)

# Check phone1 is blocked
is_allowed1, _, _ = RateLimiter.check_rate_limit(phone1)
print(f"Phone1 (maxed out): Allowed={is_allowed1}")

# Check phone2 is still allowed
is_allowed2, remaining2, _ = RateLimiter.check_rate_limit(phone2)
print(f"Phone2 (fresh): Allowed={is_allowed2}, Remaining={remaining2}")
```

**Expected Result:**
```
Phone1 (maxed out): Allowed=False
Phone2 (fresh): Allowed=True, Remaining=9
```

---

## Test 4: Rate Limit Reset

### Test 4.1: Manual Reset
```python
from django.core.cache import cache
cache.clear()

phone = '+256701234567'

# Max out the limit
for _ in range(10):
    RateLimiter.check_rate_limit(phone)

# Verify blocked
is_allowed, _, _ = RateLimiter.check_rate_limit(phone)
print(f"Before reset: Allowed={is_allowed}")

# Reset the limit
RateLimiter.reset_limit(phone)

# Verify allowed again
is_allowed, remaining, _ = RateLimiter.check_rate_limit(phone)
print(f"After reset: Allowed={is_allowed}, Remaining={remaining}")
```

**Expected Result:**
```
Before reset: Allowed=False
After reset: Allowed=True, Remaining=9
```

---

## Test 5: Get Remaining Commands

### Test 5.1: Check Remaining Count
```python
from django.core.cache import cache
cache.clear()

phone = '+256701234567'

# Check initial
remaining = RateLimiter.get_remaining_commands(phone)
print(f"Initial remaining: {remaining}")

# Execute 3 commands
for _ in range(3):
    RateLimiter.check_rate_limit(phone)

# Check remaining
remaining = RateLimiter.get_remaining_commands(phone)
print(f"After 3 commands: {remaining}")
```

**Expected Result:**
```
Initial remaining: 10
After 3 commands: 7
```

---

## Test 6: Rate Limit Messages

### Test 6.1: English Message
```python
message = RateLimiter.get_rate_limit_message('en')
print(message)
```

**Expected Result:**
```
⚠️ *Too Many Requests*

You have exceeded the limit of 10 commands per 15 minutes.
Please wait a few minutes and try again.

For urgent assistance, contact the school office.
```

### Test 6.2: Luganda Message
```python
message = RateLimiter.get_rate_limit_message('lg')
print(message)
```

**Expected Result:**
```
⚠️ *Ebiragiro Bingi Nnyo*

Osusse ekipimo kya biragiro 10 mu dakiika 15.
Linda akaseera katono oddeyo okugezaako.

Bw'oba oyagala obuyambi obw'amangu, tukirira woofiisi y'essomero.
```

---

## Test 7: Statistics

### Test 7.1: Get Rate Limit Stats
```python
from django.core.cache import cache
cache.clear()

phone = '+256701234567'

# Execute 5 commands
for _ in range(5):
    RateLimiter.check_rate_limit(phone)

# Get stats
stats = RateLimiter.get_stats(phone)

print(f"Phone: {stats['phone']}")
print(f"Command count: {stats['command_count']}")
print(f"Max commands: {stats['max_commands']}")
print(f"Remaining: {stats['remaining']}")
print(f"Window (minutes): {stats['window_minutes']}")
print(f"Is rate limited: {stats['is_rate_limited']}")
print(f"Oldest command: {stats['oldest_command']}")
print(f"Newest command: {stats['newest_command']}")
```

**Expected Result:**
```
Phone: +256701234567
Command count: 5
Max commands: 10
Remaining: 5
Window (minutes): 15
Is rate limited: False
Oldest command: 2024-01-15T10:30:00.123456+03:00
Newest command: 2024-01-15T10:30:05.654321+03:00
```

### Test 7.2: Stats for Blocked Phone
```python
from django.core.cache import cache
cache.clear()

phone = '+256701234567'

# Max out limit
for _ in range(10):
    RateLimiter.check_rate_limit(phone)

# Get stats
stats = RateLimiter.get_stats(phone)

print(f"Command count: {stats['command_count']}")
print(f"Remaining: {stats['remaining']}")
print(f"Is rate limited: {stats['is_rate_limited']}")
```

**Expected Result:**
```
Command count: 10
Remaining: 0
Is rate limited: True
```

---

## Test 8: Phone Number Normalization

### Test 8.1: Different Formats Same Cache Key
```python
phone1 = '+256701234567'
phone2 = '256701234567'
phone3 = '+256 701 234 567'
phone4 = '+256-701-234-567'

key1 = RateLimiter._get_cache_key(phone1)
key2 = RateLimiter._get_cache_key(phone2)
key3 = RateLimiter._get_cache_key(phone3)
key4 = RateLimiter._get_cache_key(phone4)

print(f"Key1: {key1}")
print(f"Key2: {key2}")
print(f"Key3: {key3}")
print(f"Key4: {key4}")
print(f"All equal: {key1 == key2 == key3 == key4}")
```

**Expected Result:**
```
Key1: ratelimit:whatsapp:256701234567
Key2: ratelimit:whatsapp:256701234567
Key3: ratelimit:whatsapp:256701234567
Key4: ratelimit:whatsapp:256701234567
All equal: True
```

---

## Test 9: Run Automated Tests

### Test 9.1: Run Full Test Suite
```bash
call venv\Scripts\activate.bat && pytest tests/test_rate_limiter.py -v
```

**Expected Result:**
```
======================== XX passed in X.XXs ========================
```

### Test 9.2: Run with Coverage
```bash
call venv\Scripts\activate.bat && pytest tests/test_rate_limiter.py --cov=messaging.rate_limiter --cov-report=term-missing
```

**Expected Result:**
```
messaging/rate_limiter.py    XXX    0   100%
```

---

## Acceptance Criteria Checklist

- [ ] First command always allowed (10 remaining)
- [ ] Commands 1-10 are allowed
- [ ] Command 11+ blocked when within 15-minute window
- [ ] retry_after calculated correctly (~900 seconds)
- [ ] Different phones have independent limits
- [ ] reset_limit() clears rate limit
- [ ] get_remaining_commands() returns correct count
- [ ] Rate limit messages exist in English and Luganda
- [ ] Phone number normalization works (different formats = same key)
- [ ] get_stats() returns accurate data
- [ ] All automated tests pass

---

## Known Issues / Notes

1. **Cache Dependency**: Rate limiter requires Django cache (Redis recommended for production)
2. **Sliding Window**: Uses sliding window algorithm - commands expire exactly 15 minutes after execution
3. **Cache TTL**: Cache entries expire after 15 minutes automatically
4. **Admin Override**: Use `reset_limit()` to manually clear rate limits

---

## Quick Validation Script

Run this complete validation in Django shell:

```python
from messaging.rate_limiter import RateLimiter
from django.core.cache import cache

# Clear cache
cache.clear()

phone = '+256701234567'

# Test 1: First 10 commands allowed
print("Test 1: Execute 10 commands")
for i in range(1, 11):
    is_allowed, remaining, _ = RateLimiter.check_rate_limit(phone)
    print(f"  Command {i}: Allowed={is_allowed}, Remaining={remaining}")

# Test 2: 11th command blocked
print("\nTest 2: 11th command should be blocked")
is_allowed, remaining, retry_after = RateLimiter.check_rate_limit(phone)
print(f"  Allowed={is_allowed}, Remaining={remaining}, Retry={retry_after}s")

# Test 3: Get stats
print("\nTest 3: Rate limit stats")
stats = RateLimiter.get_stats(phone)
print(f"  Count={stats['command_count']}, Limited={stats['is_rate_limited']}")

# Test 4: Reset works
print("\nTest 4: Reset rate limit")
RateLimiter.reset_limit(phone)
is_allowed, remaining, _ = RateLimiter.check_rate_limit(phone)
print(f"  After reset: Allowed={is_allowed}, Remaining={remaining}")

print("\n✅ Rate Limiter validation complete!")
```

**Expected Output:**
```
Test 1: Execute 10 commands
  Command 1: Allowed=True, Remaining=9
  Command 2: Allowed=True, Remaining=8
  ...
  Command 10: Allowed=True, Remaining=0

Test 2: 11th command should be blocked
  Allowed=False, Remaining=0, Retry=900s

Test 3: Rate limit stats
  Count=10, Limited=True

Test 4: Reset rate limit
  After reset: Allowed=True, Remaining=9

✅ Rate Limiter validation complete!
```
