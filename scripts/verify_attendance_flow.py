"""
Comprehensive Production Verification Script for Attendance Register Flow.
Verifies the exact scenario:
  1. Authenticate as Teacher (teacher@stmarys.ug).
  2. Locate Class Group P.5 East and today's date.
  3. Mark Student 1: Present, Student 2: Late (with note), Student 3: Absent (with note).
  4. Submit register via POST /attendance/register/.
  5. Fetch register via GET /attendance/register/ (simulating refresh F5).
  6. Assert all marked statuses and notes are accurately persisted.
"""
import os
import sys
import django

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from rest_framework.test import APIClient
from authentication.models import User
from students.models import ClassGroup, Student
from django.utils import timezone


def test_attendance_flow():
    print("=== 1. Authenticating as Teacher ===")
    teacher = User.objects.filter(email='teacher@stmarys.ug').first()
    assert teacher is not None, "Teacher teacher@stmarys.ug not found!"
    assert teacher.role == 'teacher'
    print(f"PASS: Logged in as {teacher.get_full_name()} ({teacher.email})")

    print("\n=== 2. Selecting Class 'P.5 East' and Today's Date ===")
    cg = ClassGroup.objects.filter(school=teacher.school, name='P.5 East').first()
    assert cg is not None, "Class 'P.5 East' not found in St. Mary's College Kampala!"
    import datetime
    today = timezone.localdate()
    while today.weekday() >= 5:
        today -= datetime.timedelta(days=1)
    today_str = str(today)
    print(f"PASS: Selected class: {cg.name} (ID: {cg.id}), School Day Date: {today_str}")

    students = list(Student.objects.filter(current_class=cg, is_active=True).order_by('last_name', 'first_name'))
    assert len(students) >= 3, f"Expected at least 3 students in P.5 East, found {len(students)}"
    s1, s2, s3 = students[0], students[1], students[2]
    print(f"PASS: Found students in {cg.name}:")
    print(f"  1. {s1.get_full_name()} ({s1.student_id})")
    print(f"  2. {s2.get_full_name()} ({s2.student_id})")
    print(f"  3. {s3.get_full_name()} ({s3.student_id})")

    print("\n=== 3. Submitting Attendance Register ===")
    client = APIClient()
    client.force_authenticate(user=teacher)

    late_note = "Heavy traffic on Entebbe Road"
    absent_note = "Parent reported sickness (malaria)"

    payload = {
        'class_id': cg.id,
        'date': today_str,
        'attendance': [
            {'student_id': str(s1.id), 'status': 'present', 'notes': ''},
            {'student_id': str(s2.id), 'status': 'late', 'notes': late_note},
            {'student_id': str(s3.id), 'status': 'absent', 'notes': absent_note},
        ] + [
            {'student_id': str(s.id), 'status': 'present', 'notes': ''}
            for s in students[3:]
        ]
    }

    submit_resp = client.post('/api/v1/attendance/register/', payload, format='json')
    assert submit_resp.status_code == 200, f"Submit failed with {submit_resp.status_code}: {submit_resp.data}"
    print(f"PASS: Register submitted successfully! Response: {submit_resp.data.get('message')}")

    print("\n=== 4. Refreshing Page & Re-fetching Register (GET /attendance/register/) ===")
    get_resp = client.get(f'/api/v1/attendance/register/?class_id={cg.id}&date={today_str}')
    assert get_resp.status_code == 200, f"GET failed with {get_resp.status_code}: {get_resp.data}"
    data = get_resp.json()
    records = data.get('records', [])
    assert len(records) > 0, "No records returned on GET!"

    rec1 = next((r for r in records if r['student'] == str(s1.id)), None)
    rec2 = next((r for r in records if r['student'] == str(s2.id)), None)
    rec3 = next((r for r in records if r['student'] == str(s3.id)), None)

    assert rec1 is not None, f"Record for {s1.get_full_name()} missing!"
    assert rec2 is not None, f"Record for {s2.get_full_name()} missing!"
    assert rec3 is not None, f"Record for {s3.get_full_name()} missing!"

    print(f"Checking Student 1 ({s1.get_full_name()}): status={rec1['status']}")
    assert rec1['status'] == 'present', f"Expected 'present', got '{rec1['status']}'"

    print(f"Checking Student 2 ({s2.get_full_name()}): status={rec2['status']}, notes='{rec2['notes']}'")
    assert rec2['status'] == 'late', f"Expected 'late', got '{rec2['status']}'"
    assert rec2['notes'] == late_note, f"Expected notes '{late_note}', got '{rec2['notes']}'"

    print(f"Checking Student 3 ({s3.get_full_name()}): status={rec3['status']}, notes='{rec3['notes']}'")
    assert rec3['status'] == 'absent', f"Expected 'absent', got '{rec3['status']}'"
    assert rec3['notes'] == absent_note, f"Expected notes '{absent_note}', got '{rec3['notes']}'"

    print("\n=== ALL ATTENDANCE PERSISTENCE & FLOW TESTS PASSED! ===")


if __name__ == '__main__':
    test_attendance_flow()
