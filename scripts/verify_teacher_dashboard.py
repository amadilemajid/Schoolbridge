"""
Standalone Test Script for Teacher's Dashboard API.
Tests live database queries, permissions, serialization, and frontend-backend contracts.
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
from timetable.models import TimetableSlot
from attendance.models import AttendanceRecord
from results.models import Assessment
from django.utils import timezone


def run_tests():
    print("=== 1. Checking Teacher Account ===")
    ruth = User.objects.filter(email='teacher@stmarys.ug').first()
    assert ruth is not None, "Ruth Nakamya not found in database!"
    assert ruth.role == 'teacher', f"Expected role teacher, got {ruth.role}"
    print(f"PASS: Found teacher {ruth.first_name} {ruth.last_name} ({ruth.email})")

    print("\n=== 2. Testing Unauthenticated Access ===")
    client = APIClient()
    unauth_resp = client.get('/api/v1/automation/teacher-dashboard/')
    assert unauth_resp.status_code == 401, f"Expected 401, got {unauth_resp.status_code}"
    print("PASS: Unauthenticated access rejected with 401")

    print("\n=== 3. Testing Authenticated Teacher API ===")
    client.force_authenticate(user=ruth)
    resp = client.get('/api/v1/automation/teacher-dashboard/')
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.data}"
    data = resp.json()

    required_keys = [
        'teacher', 'school', 'current_term', 'today_date', 'today_day_name',
        'kpis', 'today_schedule', 'assigned_classes', 'absent_students_today', 'pending_marks'
    ]
    for k in required_keys:
        assert k in data, f"Missing key in response: {k}"
    print(f"PASS: Response contains all required keys: {required_keys}")

    print("\n=== 4. Validating Real Data Integrity ===")
    # Teacher details
    assert data['teacher']['name'] == 'Ruth Nakamya'
    assert data['teacher']['email'] == 'teacher@stmarys.ug'
    assert data['teacher']['role'] == 'teacher'
    print(f"PASS: Teacher profile verified ({data['teacher']['name']})")

    # School & Term
    assert "St. Mary's" in data['school']['name']
    assert data['current_term'] is not None
    print(f"PASS: School ({data['school']['name']}) and Term ({data['current_term']['name']})")

    # KPIs vs Database
    kpis = data['kpis']
    actual_form_classes_count = ClassGroup.objects.filter(school=ruth.school, form_teacher=ruth, is_active=True).count()
    assert kpis['assigned_classes_count'] == actual_form_classes_count, \
        f"KPI mismatch: {kpis['assigned_classes_count']} vs {actual_form_classes_count}"

    actual_students_count = Student.objects.filter(
        school=ruth.school,
        current_class__form_teacher=ruth,
        is_active=True
    ).count()
    assert kpis['total_students_count'] == actual_students_count, \
        f"Student count mismatch: {kpis['total_students_count']} vs {actual_students_count}"

    today_weekday = timezone.localdate().weekday()
    actual_slots_count = TimetableSlot.all_objects.filter(
        school=ruth.school,
        teacher=ruth,
        day_of_week=today_weekday,
        timetable_version__is_active=True
    ).count()
    assert kpis['today_lessons_count'] == actual_slots_count, \
        f"Lesson count mismatch: {kpis['today_lessons_count']} vs {actual_slots_count}"

    print(f"PASS: KPIs accurately match database:")
    print(f"  - Assigned Form Classes: {kpis['assigned_classes_count']}")
    print(f"  - Enrolled Students: {kpis['total_students_count']}")
    print(f"  - Today's Lessons: {kpis['today_lessons_count']}")
    print(f"  - Absent Students Today: {kpis['absent_students_today_count']}")
    print(f"  - Pending Marks: {kpis['pending_assessments_count']}")

    print("\n=== 5. Testing Today's Timetable Slots ===")
    schedule = data['today_schedule']
    assert len(schedule) == actual_slots_count
    if schedule:
        first = schedule[0]
        assert 'period_number' in first and 'start_time' in first and 'subject_name' in first
        print(f"PASS: First slot: Period {first['period_number']} - {first['subject_name']} ({first['class_group_name']}) at {first['start_time']}–{first['end_time']}")

    print("\n=== 6. Testing Absent Students Alert Roster with Mocked Record ===")
    today = timezone.localdate()
    cg = ruth.form_classes.first()
    stu = Student.objects.filter(current_class=cg).first()
    term = ruth.school.terms.filter(is_current=True).first()

    temp_rec, _ = AttendanceRecord.all_objects.update_or_create(
        school=ruth.school,
        student=stu,
        date=today,
        defaults={
            'class_group': cg,
            'academic_term': term,
            'status': 'absent',
            'pre_excused': False,
            'notes': 'Unexcused absence test'
        }
    )

    resp_absent = client.get('/api/v1/automation/teacher-dashboard/')
    assert resp_absent.status_code == 200
    absent_data = resp_absent.json()
    assert absent_data['kpis']['absent_students_today_count'] >= 1
    found_stu = next((s for s in absent_data['absent_students_today'] if s['student_id'] == str(stu.id)), None)
    assert found_stu is not None, "Created absent student not found in absent_students_today roster!"
    assert found_stu['student_name'] == stu.get_full_name()
    assert found_stu['reg_number'] == stu.student_id
    assert found_stu['class_group_name'] == cg.name
    print(f"PASS: Absent student alert generated for {found_stu['student_name']} (Guardian: {found_stu['guardian_name']}, Phone: {found_stu['guardian_phone']})")

    # Clean up test record
    temp_rec.delete()

    print("\n=== ALL TEACHER DASHBOARD TESTS PASSED SUCCESSFULLY! ===")


if __name__ == '__main__':
    run_tests()
