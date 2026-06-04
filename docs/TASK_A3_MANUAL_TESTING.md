# Task A3: Command Parser Update - Manual Testing Guide

## Overview
Command Parser now supports numeric shortcuts (1-7) in addition to text commands, making it easier for users to access frequently used features.

## Prerequisites
1. Django development environment running
2. Python shell access (`python manage.py shell`)

---

## Test 1: Numeric Shortcuts

### Test 1.1: Number 1 Maps to BALANCE
```python
from messaging.services import InboundCommandProcessor

cmd, args = InboundCommandProcessor.parse_command('1')
print(f"Command: {cmd}")
print(f"Args: {args}")
```

**Expected Result:**
```
Command: BALANCE
Args: {}
```

### Test 1.2: Number 2 Maps to RESULTS
```python
cmd, args = InboundCommandProcessor.parse_command('2')
print(f"Command: {cmd}")
```

**Expected Result:**
```
Command: RESULTS
```

### Test 1.3: All Numeric Shortcuts (1-7)
```python
shortcuts = {
    '1': 'BALANCE',
    '2': 'RESULTS',
    '3': 'ATTEND',
    '4': 'RECEIPT',
    '5': 'TIMETABLE',
    '6': 'PLAN',
    '7': 'ABSENT',
}

for number, expected_cmd in shortcuts.items():
    cmd, args = InboundCommandProcessor.parse_command(number)
    status = "✓" if cmd == expected_cmd else "✗"
    print(f"{status} {number} → {cmd} (expected: {expected_cmd})")
```

**Expected Result:**
```
✓ 1 → BALANCE (expected: BALANCE)
✓ 2 → RESULTS (expected: RESULTS)
✓ 3 → ATTEND (expected: ATTEND)
✓ 4 → RECEIPT (expected: RECEIPT)
✓ 5 → TIMETABLE (expected: TIMETABLE)
✓ 6 → PLAN (expected: PLAN)
✓ 7 → ABSENT (expected: ABSENT)
```

---

## Test 2: Text Commands Still Work

### Test 2.1: BALANCE Text Command
```python
cmd, args = InboundCommandProcessor.parse_command('BALANCE')
print(f"Command: {cmd}")
```

**Expected Result:**
```
Command: BALANCE
```

### Test 2.2: All Text Commands
```python
commands = [
    'BALANCE', 'RESULTS', 'ATTEND', 'TIMETABLE', 
    'RECEIPT', 'PLAN', 'ABSENT', 'HELP', 'MENU', 
    'LUGANDA', 'ENGLISH'
]

for text_cmd in commands:
    cmd, args = InboundCommandProcessor.parse_command(text_cmd)
    status = "✓" if cmd == text_cmd else "✗"
    print(f"{status} {text_cmd}")
```

**Expected Result:**
```
✓ BALANCE
✓ RESULTS
✓ ATTEND
✓ TIMETABLE
✓ RECEIPT
✓ PLAN
✓ ABSENT
✓ HELP
✓ MENU
✓ LUGANDA
✓ ENGLISH
```

---

## Test 3: Arguments Parsing

### Test 3.1: RECEIPT with Date (Text)
```python
cmd, args = InboundCommandProcessor.parse_command('RECEIPT 2024-01-15')
print(f"Command: {cmd}")
print(f"Args: {args}")
```

**Expected Result:**
```
Command: RECEIPT
Args: {'date': '2024-01-15'}
```

### Test 3.2: RECEIPT with Date (Numeric)
```python
cmd, args = InboundCommandProcessor.parse_command('4 2024-01-15')
print(f"Command: {cmd}")
print(f"Args: {args}")
```

**Expected Result:**
```
Command: RECEIPT
Args: {'date': '2024-01-15'}
```

### Test 3.3: ABSENT with Date (Text)
```python
cmd, args = InboundCommandProcessor.parse_command('ABSENT 2024-01-15')
print(f"Command: {cmd}")
print(f"Args: {args}")
```

**Expected Result:**
```
Command: ABSENT
Args: {'date': '2024-01-15', 'reason': ''}
```

### Test 3.4: ABSENT with Date and Reason (Text)
```python
cmd, args = InboundCommandProcessor.parse_command('ABSENT 2024-01-15 Sick')
print(f"Command: {cmd}")
print(f"Args: {args}")
```

**Expected Result:**
```
Command: ABSENT
Args: {'date': '2024-01-15', 'reason': 'SICK'}
```

### Test 3.5: ABSENT with Date and Multi-Word Reason
```python
cmd, args = InboundCommandProcessor.parse_command('ABSENT 2024-01-15 Doctor appointment')
print(f"Command: {cmd}")
print(f"Args: {args}")
```

**Expected Result:**
```
Command: ABSENT
Args: {'date': '2024-01-15', 'reason': 'DOCTOR APPOINTMENT'}
```

### Test 3.6: ABSENT with Date and Reason (Numeric)
```python
cmd, args = InboundCommandProcessor.parse_command('7 2024-01-15 Sick')
print(f"Command: {cmd}")
print(f"Args: {args}")
```

**Expected Result:**
```
Command: ABSENT
Args: {'date': '2024-01-15', 'reason': 'SICK'}
```

---

## Test 4: Edge Cases

### Test 4.1: Lowercase Commands
```python
cmd, args = InboundCommandProcessor.parse_command('balance')
print(f"Command: {cmd}")
```

**Expected Result:**
```
Command: BALANCE
```

### Test 4.2: Mixed Case Commands
```python
cmd, args = InboundCommandProcessor.parse_command('BaLaNcE')
print(f"Command: {cmd}")
```

**Expected Result:**
```
Command: BALANCE
```

### Test 4.3: Leading/Trailing Whitespace
```python
cmd, args = InboundCommandProcessor.parse_command('  BALANCE  ')
print(f"Command: {cmd}")
```

**Expected Result:**
```
Command: BALANCE
```

### Test 4.4: Multiple Spaces Between Words
```python
cmd, args = InboundCommandProcessor.parse_command('RECEIPT   2024-01-15')
print(f"Command: {cmd}")
print(f"Args: {args}")
```

**Expected Result:**
```
Command: RECEIPT
Args: {'date': '2024-01-15'}
```

### Test 4.5: Empty String
```python
cmd, args = InboundCommandProcessor.parse_command('')
print(f"Command: {cmd}")
```

**Expected Result:**
```
Command: UNKNOWN
```

### Test 4.6: Whitespace Only
```python
cmd, args = InboundCommandProcessor.parse_command('   ')
print(f"Command: {cmd}")
```

**Expected Result:**
```
Command: UNKNOWN
```

### Test 4.7: Invalid Command
```python
cmd, args = InboundCommandProcessor.parse_command('INVALID')
print(f"Command: {cmd}")
```

**Expected Result:**
```
Command: UNKNOWN
```

### Test 4.8: Invalid Numbers (0, 8, 9)
```python
invalid_numbers = ['0', '8', '9']

for num in invalid_numbers:
    cmd, args = InboundCommandProcessor.parse_command(num)
    print(f"{num} → {cmd}")
```

**Expected Result:**
```
0 → UNKNOWN
8 → UNKNOWN
9 → UNKNOWN
```

### Test 4.9: Special Characters
```python
special = ['!', '@', '#', '$']

for char in special:
    cmd, args = InboundCommandProcessor.parse_command(char)
    print(f"{char} → {cmd}")
```

**Expected Result:**
```
! → UNKNOWN
@ → UNKNOWN
# → UNKNOWN
$ → UNKNOWN
```

---

## Test 5: Run Automated Tests

### Test 5.1: Run Full Test Suite
```bash
call venv\Scripts\activate.bat && pytest tests/test_command_parser.py -v
```

**Expected Result:**
```
======================== 45 passed in X.XXs ========================
```

### Test 5.2: Run with Coverage
```bash
call venv\Scripts\activate.bat && pytest tests/test_command_parser.py --cov=messaging.services --cov-report=term-missing
```

---

## Acceptance Criteria Checklist

- [ ] Numeric shortcut 1 maps to BALANCE
- [ ] Numeric shortcut 2 maps to RESULTS
- [ ] Numeric shortcut 3 maps to ATTEND
- [ ] Numeric shortcut 4 maps to RECEIPT
- [ ] Numeric shortcut 5 maps to TIMETABLE
- [ ] Numeric shortcut 6 maps to PLAN
- [ ] Numeric shortcut 7 maps to ABSENT
- [ ] All text commands still work (BALANCE, RESULTS, etc.)
- [ ] RECEIPT with date argument works (text and numeric)
- [ ] ABSENT with date and reason works (text and numeric)
- [ ] Lowercase commands converted to uppercase
- [ ] Whitespace trimmed correctly
- [ ] Invalid commands return UNKNOWN
- [ ] Invalid numbers (0, 8, 9) return UNKNOWN
- [ ] All 45 automated tests pass

---

## Quick Validation Script

Run this complete validation in Django shell:

```python
from messaging.services import InboundCommandProcessor

# Test 1: All numeric shortcuts
print("=== Numeric Shortcuts ===")
shortcuts = {
    '1': 'BALANCE', '2': 'RESULTS', '3': 'ATTEND', '4': 'RECEIPT',
    '5': 'TIMETABLE', '6': 'PLAN', '7': 'ABSENT'
}

all_pass = True
for num, expected in shortcuts.items():
    cmd, _ = InboundCommandProcessor.parse_command(num)
    if cmd == expected:
        print(f"✓ {num} → {cmd}")
    else:
        print(f"✗ {num} → {cmd} (expected {expected})")
        all_pass = False

# Test 2: Arguments parsing
print("\n=== Arguments Parsing ===")
cmd, args = InboundCommandProcessor.parse_command('4 2024-01-15')
if cmd == 'RECEIPT' and args.get('date') == '2024-01-15':
    print("✓ RECEIPT with date (numeric)")
else:
    print("✗ RECEIPT with date failed")
    all_pass = False

cmd, args = InboundCommandProcessor.parse_command('7 2024-01-15 Sick')
if cmd == 'ABSENT' and args.get('date') == '2024-01-15' and args.get('reason') == 'SICK':
    print("✓ ABSENT with date and reason (numeric)")
else:
    print("✗ ABSENT with date and reason failed")
    all_pass = False

# Test 3: Edge cases
print("\n=== Edge Cases ===")
cmd, _ = InboundCommandProcessor.parse_command('balance')
if cmd == 'BALANCE':
    print("✓ Lowercase conversion")
else:
    print("✗ Lowercase conversion failed")
    all_pass = False

cmd, _ = InboundCommandProcessor.parse_command('  BALANCE  ')
if cmd == 'BALANCE':
    print("✓ Whitespace trimming")
else:
    print("✗ Whitespace trimming failed")
    all_pass = False

cmd, _ = InboundCommandProcessor.parse_command('8')
if cmd == 'UNKNOWN':
    print("✓ Invalid number returns UNKNOWN")
else:
    print("✗ Invalid number handling failed")
    all_pass = False

# Final result
print("\n" + "="*40)
if all_pass:
    print("🎉 All validation checks passed!")
else:
    print("❌ Some checks failed")
```

**Expected Output:**
```
=== Numeric Shortcuts ===
✓ 1 → BALANCE
✓ 2 → RESULTS
✓ 3 → ATTEND
✓ 4 → RECEIPT
✓ 5 → TIMETABLE
✓ 6 → PLAN
✓ 7 → ABSENT

=== Arguments Parsing ===
✓ RECEIPT with date (numeric)
✓ ABSENT with date and reason (numeric)

=== Edge Cases ===
✓ Lowercase conversion
✓ Whitespace trimming
✓ Invalid number returns UNKNOWN

========================================
🎉 All validation checks passed!
```
