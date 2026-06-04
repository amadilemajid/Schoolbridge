# Task A1: Translation Service - Manual Testing Guide

## Overview
Translation Service provides English and Luganda translations for all WhatsApp command responses.

## Prerequisites
1. Django development environment running
2. Test database populated with at least one guardian with phone number
3. Python shell access (`python manage.py shell`)

---

## Test 1: Basic Translation Retrieval

### Test 1.1: Get English Menu
```python
from messaging.translation_service import TranslationService

menu = TranslationService.get('menu_text', lang='en')
print(menu)
```

**Expected Result:**
```
👋 *Welcome to SchoolBridge*

Please reply with a number or command:

1️⃣ BALANCE - Fee balance
2️⃣ RESULTS - Exam results
...
```

### Test 1.2: Get Luganda Menu
```python
menu_lg = TranslationService.get('menu_text', lang='lg')
print(menu_lg)
```

**Expected Result:**
```
👋 *Tusanyukidde kukusanga ku SchoolBridge*

Wandiika ennamba oba ekiragiro:

1️⃣ BALANCE - Ensimbi ezisigaddewo
...
```

---

## Test 2: Translation with Parameters

### Test 2.1: Balance Detail (English)
```python
text = TranslationService.get(
    'balance_detail',
    lang='en',
    icon='✅',
    student_name='John Doe',
    class_name='P.5',
    total=500000,
    paid=300000,
    balance=200000
)
print(text)
```

**Expected Result:**
```
✅ *John Doe*
   Class: P.5
   Total: UGX 500,000
   Paid: UGX 300,000
   Balance: UGX 200,000
```

### Test 2.2: Balance Detail (Luganda)
```python
text_lg = TranslationService.get(
    'balance_detail',
    lang='lg',
    icon='⚠️',
    student_name='John Doe',
    class_name='P.5',
    total=500000,
    paid=300000,
    balance=200000
)
print(text_lg)
```

**Expected Result:**
```
⚠️ *John Doe*
   Ekkiraalagana: P.5
   Zonna: UGX 500,000
   Ezisasuliddwa: UGX 300,000
   Ezisigaddewo: UGX 200,000
```

---

## Test 3: Language Detection from Guardian

### Test 3.1: Get Language from Guardian (English)
```python
from students.models import Guardian

guardian = Guardian.objects.filter(preferred_language='en').first()
if guardian:
    lang = TranslationService.get_language(guardian)
    print(f"Guardian language: {lang}")
else:
    print("No English guardian found - create one in Django admin")
```

**Expected Result:**
```
Guardian language: en
```

### Test 3.2: Get Language from Guardian (Luganda)
```python
# First, update a guardian to Luganda
guardian = Guardian.objects.first()
guardian.preferred_language = 'lg'
guardian.save()

lang = TranslationService.get_language(guardian)
print(f"Guardian language: {lang}")
```

**Expected Result:**
```
Guardian language: lg
```

---

## Test 4: Language Detection from Phone Number

### Test 4.1: Lookup by Phone
```python
guardian = Guardian.objects.first()
phone = guardian.phone_normalised
print(f"Testing with phone: {phone}")

lang = TranslationService.get_language_from_phone(phone)
print(f"Detected language: {lang}")
```

**Expected Result:**
```
Testing with phone: +256701234567
Detected language: en (or lg, depending on guardian's preference)
```

### Test 4.2: Phone Not Found (Defaults to English)
```python
lang = TranslationService.get_language_from_phone('+256709999999')
print(f"Language for unknown phone: {lang}")
```

**Expected Result:**
```
Language for unknown phone: en
```

---

## Test 5: All Translation Keys

### Test 5.1: Verify All Keys Have Both Languages
```python
missing = []
for key in TranslationService.TRANSLATIONS.keys():
    translations = TranslationService.TRANSLATIONS[key]
    if 'en' not in translations:
        missing.append(f"{key} missing English")
    if 'lg' not in translations:
        missing.append(f"{key} missing Luganda")

if missing:
    print("MISSING TRANSLATIONS:")
    for m in missing:
        print(f"  - {m}")
else:
    print("✅ All translation keys have both English and Luganda")
```

**Expected Result:**
```
✅ All translation keys have both English and Luganda
```

---

## Test 6: Run Automated Tests

```bash
pytest tests/test_translation_service.py -v
```

**Expected Result:**
```
tests/test_translation_service.py::TranslationServiceTests::test_all_keys_have_english PASSED
tests/test_translation_service.py::TranslationServiceTests::test_all_keys_have_luganda PASSED
...
======================== XX passed in X.XXs ========================
```

---

## Quick Validation Script

Run this complete validation in Django shell:

```python
from messaging.translation_service import TranslationService
from students.models import Guardian

# 1. Check all keys present
keys = list(TranslationService.TRANSLATIONS.keys())
print(f"✅ Total translation keys: {len(keys)}")

# 2. Verify English and Luganda for each
complete = all(
    'en' in TranslationService.TRANSLATIONS[k] and 
    'lg' in TranslationService.TRANSLATIONS[k]
    for k in keys
)
print(f"✅ All keys have both languages: {complete}")

# 3. Test sample translation
menu_en = TranslationService.get('menu_text', lang='en')
menu_lg = TranslationService.get('menu_text', lang='lg')
print(f"✅ English menu length: {len(menu_en)} chars")
print(f"✅ Luganda menu length: {len(menu_lg)} chars")

# 4. Test with guardian
guardian = Guardian.objects.first()
if guardian:
    lang = TranslationService.get_language(guardian)
    print(f"✅ Guardian language detection: {lang}")

print("\n🎉 Task A1 Translation Service is ready!")
```

**Expected Output:**
```
✅ Total translation keys: 21
✅ All keys have both languages: True
✅ English menu length: 387 chars
✅ Luganda menu length: 375 chars
✅ Guardian language detection: en

🎉 Task A1 Translation Service is ready!
```
