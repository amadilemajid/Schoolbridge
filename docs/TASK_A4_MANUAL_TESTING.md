# Task A4: TIMETABLE Command - Manual Testing Guide

## Prerequisites
1. Django environment activated
2. Database with test school, students, guardians
3. WhatsApp test phone numbers (or WhatsApp Business API sandbox)
4. Access to Django admin or shell for data setup

## Test Data Setup

### Option 1: Django Shell
```python
python manage.py shell

from schools.models import School, AcademicYear, AcademicTerm, Timetable
from students.models import Student, ClassGroup, Guardian
from django.utils import timezone

# Create school
school = School.objects.create(
    name='Test Academy',
    slug='test-academy',
    district='Kampala',
    phone='0700000000',
    email='test@academy.ug',
    school_type='primary'
)

# Create academic year and term
year = AcademicYear.objects.create(school=school, year=2024, is_current=True)
term = AcademicTerm.objects.create(
    school=school,
    academic_year=year,
    term_number=1,
    name='Term 1 2024',
    start_date=timezone.now().date(),
    end_date=timezone.now().date(),
    fee_deadline=timezone.now().date(),
    is_current=True
)

# Create class
class_p5 = ClassGroup.objects.create(school=school, name='P5 Blue')

# Create students
student_en = Student.objects.create(
    school=school,
    first_name='John',
    last_name='Doe',
    date_of_birth=timezone.now().date(),
    current_class=class_p5
)

student_lg = Student.objects.create(
    school=school,
    first_name='Jane',
    last_name='Smith',
    date_of_birth=timezone.now().date(),
    current_class=class_p5
)

# Create guardians with language preferences
guardian_en = Guardian.objects.create(
    student=student_en,
    phone_normalised='256701234567',  # Replace with your WhatsApp test number
    is_primary=True,
    preferred_language='en'
)

guardian_lg = Guardian.objects.create(
    student=student_lg,
    phone_normalised='256707654321',  # Replace with your WhatsApp test number
    is_primary=True,
    preferred_language='lg'
)

# Create timetable
timetable = Timetable.objects.create(
    school=school,
    class_group=class_p5,
    title='Term 1 2024',
    content="""Monday:
08:00 - 09:00 Mathematics
09:00 - 10:00 English
10:00 - 10:30 Break
10:30 - 11:30 Science
11:30 - 12:30 Social Studies

Tuesday:
08:00 - 09:00 Luganda
09:00 - 10:00 Mathematics
10:00 - 10:30 Break
10:30 - 11:30 PE
11:30 - 12:30 Art

Wednesday:
08:00 - 09:00 English
09:00 - 10:00 Science
10:00 - 10:30 Break
10:30 - 11:30 Mathematics
11:30 - 12:30 Music

Thursday:
08:00 - 09:00 Mathematics
09:00 - 10:00 Social Studies
10:00 - 10:30 Break
10:30 - 11:30 English
11:30 - 12:30 ICT

Friday:
08:00 - 09:00 Science
09:00 - 10:00 Mathematics
10:00 - 10:30 Break
10:30 - 11:30 Luganda
11:30 - 12:30 PE""",
    is_active=True
)

print("✅ Test data created successfully!")
print(f"English Guardian: {guardian_en.phone_normalised}")
print(f"Luganda Guardian: {guardian_lg.phone_normalised}")
```

### Option 2: Django Admin
1. Log into Django admin: `/admin/`
2. Create School, AcademicYear, AcademicTerm
3. Create ClassGroup (e.g., "P5 Blue")
4. Create Students, assign to ClassGroup
5. Create Guardians, link to Students, set `preferred_language`
6. Create Timetable for ClassGroup, set `is_active=True`

## Manual Test Cases

### Test Case 1: English User Receives Timetable
**Objective**: Verify English timetable display

**Setup**:
- Guardian with `preferred_language='en'`
- Student in P5 Blue
- Active timetable exists

**Steps**:
1. Send WhatsApp message: `TIMETABLE` or `5`
2. Wait for response (within 5 seconds)

**Expected Result**:
```
📚 *John Doe - P5 Blue Timetable*

Monday:
08:00 - 09:00 Mathematics
09:00 - 10:00 English
...
```

**Verification**:
- ✅ Response received within 5 seconds
- ✅ Student name displayed correctly
- ✅ Class name displayed correctly
- ✅ Full timetable content visible
- ✅ Header says "Timetable" (not "Emirimu")

---

### Test Case 2: Luganda User Receives Timetable
**Objective**: Verify Luganda timetable display

**Setup**:
- Guardian with `preferred_language='lg'`
- Student in P5 Blue
- Active timetable exists

**Steps**:
1. Send WhatsApp message: `TIMETABLE` or `5`
2. Wait for response

**Expected Result**:
```
📚 *Jane Smith - P5 Blue Emirimu*

Balaza:
08:00 - 09:00 Kubala
...
```

**Verification**:
- ✅ Response received within 5 seconds
- ✅ Student name displayed correctly
- ✅ Header says "Emirimu" (not "Timetable")
- ✅ Full timetable content visible

---

### Test Case 3: Numeric Shortcut (5)
**Objective**: Verify numeric shortcut works

**Setup**: Same as Test Case 1

**Steps**:
1. Send WhatsApp message: `5`
2. Wait for response

**Expected Result**: Same as Test Case 1

**Verification**:
- ✅ Numeric shortcut recognized
- ✅ Timetable displayed correctly

---

### Test Case 4: No Timetable Published (English)
**Objective**: Verify error message when no timetable exists

**Setup**:
- Guardian with `preferred_language='en'`
- Student in P5 Blue
- **No active timetable** (set `is_active=False` or delete)

**Steps**:
1. Send WhatsApp message: `TIMETABLE`
2. Wait for response

**Expected Result**:
```
📚 *John Doe*: No timetable published yet. Contact the school.
```

**Verification**:
- ✅ Appropriate error message displayed
- ✅ Student name shown
- ✅ Guidance to contact school provided

---

### Test Case 5: No Timetable Published (Luganda)
**Objective**: Verify Luganda error message

**Setup**:
- Guardian with `preferred_language='lg'`
- Student in P5 Blue
- **No active timetable**

**Steps**:
1. Send WhatsApp message: `TIMETABLE`
2. Wait for response

**Expected Result**:
```
📚 *Jane Smith*: Emirimu teginnafulumizibwa. Tukirira essomero.
```

**Verification**:
- ✅ Luganda error message displayed
- ✅ Student name shown

---

### Test Case 6: Unregistered Phone Number
**Objective**: Verify handling of unregistered users

**Setup**:
- Use phone number **not registered** in Guardian table

**Steps**:
1. Send WhatsApp message: `TIMETABLE`
2. Wait for response

**Expected Result (English)**:
```
Your number is not registered. Contact the school office. Reply HELP for commands.
```

**Verification**:
- ✅ Generic "not registered" message shown
- ✅ Guidance to contact school office
- ✅ Mention of HELP command

---

### Test Case 7: Multiple Children
**Objective**: Verify separate messages for each child

**Setup**:
- Single guardian linked to 2+ students
- All students in classes with active timetables

**Steps**:
1. Send WhatsApp message: `TIMETABLE`
2. Wait for responses

**Expected Result**: Multiple messages received
```
Message 1:
📚 *John Doe - P5 Blue Timetable*
[content]

Message 2:
📚 *Jane Doe - P6 Red Timetable*
[content]
```

**Verification**:
- ✅ Received 2 separate messages
- ✅ Each message shows different student name
- ✅ Each message shows correct class
- ✅ Each message shows correct timetable

---

### Test Case 8: Student Not Assigned to Class
**Objective**: Verify handling when student has no class

**Setup**:
- Guardian registered
- Student has `current_class=None`

**Steps**:
1. Send WhatsApp message: `TIMETABLE`
2. Wait for response

**Expected Result (English)**:
```
No class timetable available for your linked learner records.
```

**Expected Result (Luganda)**:
```
Emirimu gy'ekiraalagana tegiriwo ku byafaanani byammwe.
```

**Verification**:
- ✅ Appropriate "no class" message displayed
- ✅ Language-specific message shown

---

### Test Case 9: Inactive Timetable Ignored
**Objective**: Verify only active timetables are returned

**Setup**:
- Guardian with student in P5 Blue
- Timetable exists but `is_active=False`

**Steps**:
1. Send WhatsApp message: `TIMETABLE`
2. Wait for response

**Expected Result**: Same as Test Case 4 (no timetable message)

**Verification**:
- ✅ Inactive timetable not displayed
- ✅ "No timetable published" message shown

---

### Test Case 10: Language Switch Then Timetable
**Objective**: Verify language preference persists

**Setup**:
- Guardian initially set to English
- Student has active timetable

**Steps**:
1. Send WhatsApp message: `LUGANDA`
2. Wait for confirmation
3. Send WhatsApp message: `TIMETABLE`
4. Wait for response

**Expected Result**:
```
Step 2:
✅ Olulimi lwaakyusibwa okutuuka *Oluganda*. Ebisubizo byonna bijja kuba mu Luganda.

Step 4:
📚 *John Doe - P5 Blue Emirimu*
[content]
```

**Verification**:
- ✅ Language switched to Luganda
- ✅ Timetable displayed in Luganda
- ✅ Header says "Emirimu"

---

## Database Verification

After each test, verify in Django admin or shell:

```python
from messaging.models import MessageLog

# Check last message sent
msg = MessageLog.objects.filter(
    channel='whatsapp',
    template_type='timetable_response'
).order_by('-created_at').first()

print(f"Phone: {msg.recipient_phone}")
print(f"Status: {msg.status}")
print(f"Body: {msg.message_body}")
```

## Performance Testing

**Objective**: Verify response time meets 5-second SLA

**Steps**:
1. Record timestamp when sending message
2. Record timestamp when receiving response
3. Calculate difference

**Acceptance**: Response within 5 seconds

**Note**: Use Python script with WhatsApp Business API for precise timing:

```python
import time
import requests

start = time.time()
# Send TIMETABLE command via API
response = send_whatsapp_message("+256701234567", "TIMETABLE")
# Wait for webhook callback or poll MessageLog
end = time.time()

print(f"Response time: {end - start:.2f} seconds")
# Should be < 5 seconds
```

## Edge Cases

### Edge Case 1: Very Long Timetable
**Setup**: Create timetable with content near 4096 char limit

**Verify**: Message not truncated, fully delivered

### Edge Case 2: Special Characters in Timetable
**Setup**: Include emojis, Unicode characters in content

**Verify**: Characters display correctly in WhatsApp

### Edge Case 3: Rate Limiting
**Setup**: Send 11 TIMETABLE commands in 15 minutes

**Verify**: 11th command blocked with rate limit message

## Regression Testing

After completing Task A4, verify other commands still work:

- ✅ `BALANCE` (or `1`) - Fee balance
- ✅ `RESULTS` (or `2`) - Exam results
- ✅ `ATTEND` (or `3`) - Attendance
- ✅ `RECEIPT` (or `4`) - Payment history
- ✅ `PLAN` (or `6`) - Payment plan
- ✅ `ABSENT` (or `7`) - Report absence
- ✅ `MENU` - Show menu
- ✅ `LUGANDA` - Switch to Luganda
- ✅ `ENGLISH` - Switch to English

## Troubleshooting

### Issue: Message not received
**Check**:
1. WhatsApp Business API status
2. School's WhatsApp number configured
3. Guardian phone normalized correctly (256...)
4. MessageLog status field

### Issue: Wrong language displayed
**Check**:
1. Guardian `preferred_language` field value
2. TranslationService.get_language_from_phone() returns correct value
3. No fallback to default English

### Issue: Timetable not found
**Check**:
1. Timetable `is_active=True`
2. Timetable `class_group` matches student's `current_class`
3. Student has `current_class` assigned

### Issue: Multiple messages not sent
**Check**:
1. Multiple Guardian records linked to same phone
2. Each student has `current_class` assigned
3. No errors in application logs

## Sign-Off

**Manual Testing Completed**: ☐  
**All Test Cases Passed**: ☐  
**Regression Tests Passed**: ☐  
**Performance SLA Met**: ☐  
**Ready for Production**: ☐  

**Tester Name**: _________________  
**Date**: _________________  
**Signature**: _________________
