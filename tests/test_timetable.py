import pytest
from datetime import time, date
from decimal import Decimal
from django.utils import timezone
from unittest.mock import patch

from schools.models import School, AcademicYear, AcademicTerm, Timetable
from students.models import Student, ClassGroup
from timetable.models import TimetableVersion, TimetableSlot, SubstitutionRecord
from timetable.services import TimetableService
from audit.models import AuditLog

pytestmark = pytest.mark.django_db


@pytest.fixture
def other_class(db, school):
    return ClassGroup.all_objects.create(
        school=school, name='P.7 West', level='P7', stream='West'
    )


@pytest.fixture
def timetable_version(db, school, primary_class, current_term, director):
    return TimetableVersion.all_objects.create(
        school=school,
        class_group=primary_class,
        academic_term=current_term,
        version_number=1,
        is_active=True,
        effective_from=timezone.localdate(),
        created_by=director
    )


def test_timetable_version_auto_deactivates_others(school, primary_class, current_term, director):
    v1 = TimetableVersion.all_objects.create(
        school=school,
        class_group=primary_class,
        academic_term=current_term,
        version_number=1,
        is_active=True,
        effective_from=timezone.localdate(),
        created_by=director
    )
    v2 = TimetableVersion.all_objects.create(
        school=school,
        class_group=primary_class,
        academic_term=current_term,
        version_number=2,
        is_active=True,
        effective_from=timezone.localdate(),
        created_by=director
    )
    v1.refresh_from_db()
    assert not v1.is_active
    assert v2.is_active


def test_conflict_detection(school, primary_class, other_class, current_term, teacher, director):
    v1 = TimetableVersion.all_objects.create(
        school=school, class_group=primary_class, academic_term=current_term,
        version_number=1, is_active=True, effective_from=timezone.localdate(), created_by=director
    )
    v2 = TimetableVersion.all_objects.create(
        school=school, class_group=other_class, academic_term=current_term,
        version_number=1, is_active=True, effective_from=timezone.localdate(), created_by=director
    )

    # Class 1 slot: Monday, Period 1, 8:00 - 9:00, Teacher
    s1 = TimetableSlot.all_objects.create(
        timetable_version=v1, school=school,
        day_of_week=0, period_number=1,
        start_time=time(8, 0), end_time=time(9, 0),
        teacher=teacher, slot_type='lesson', room='Room 1'
    )

    # Class 2 slot: Monday, Period 1, 8:30 - 9:30 (overlaps), Same Teacher
    s2 = TimetableSlot.all_objects.create(
        timetable_version=v2, school=school,
        day_of_week=0, period_number=1,
        start_time=time(8, 30), end_time=time(9, 30),
        teacher=teacher, slot_type='lesson', room='Room 2'
    )

    # Conflict check on v1 should identify overlap with v2
    conflicts = TimetableService.validate_no_conflicts(v1)
    assert len(conflicts) == 1
    assert conflicts[0]['teacher'] == teacher.get_full_name()
    assert conflicts[0]['class_1'] == primary_class.name
    assert conflicts[0]['class_2'] == other_class.name


def test_whatsapp_formatting(school, primary_class, timetable_version, teacher):
    TimetableSlot.all_objects.create(
        timetable_version=timetable_version, school=school,
        day_of_week=0, period_number=1,
        start_time=time(8, 0), end_time=time(9, 0),
        teacher=teacher, slot_type='lesson', room='Room A', subject_name='Math'
    )
    
    formatted = TimetableService.format_for_whatsapp(primary_class, timetable_version.academic_term)
    assert 'Weekly Timetable' in formatted
    assert 'Math' in formatted
    assert teacher.get_full_name() in formatted


def test_create_substitution_and_audit(school, timetable_version, teacher, director):
    slot = TimetableSlot.all_objects.create(
        timetable_version=timetable_version, school=school,
        day_of_week=0, period_number=1,
        start_time=time(8, 0), end_time=time(9, 0),
        teacher=director, slot_type='lesson', subject_name='Math'
    )

    sub = TimetableService.create_substitution(
        slot=slot,
        date=timezone.localdate(),
        substitute_teacher=teacher,
        reason='Sick leave',
        created_by=director
    )

    assert sub.original_teacher == director
    assert sub.substitute_teacher == teacher
    assert sub.reason == 'Sick leave'

    # Verify audit log entry
    assert AuditLog.objects.filter(
        school_id=school.id,
        action='SUBSTITUTION_CREATED',
        category='SCHOOL'
    ).exists()


def test_prefill_attendance_stubs(school, primary_class, timetable_version):
    # Create active student
    student = Student.all_objects.create(
        school=school, student_id='STU-001',
        first_name='Ali', last_name='Seka', gender='M',
        admission_date='2024-01-15', academic_year_admitted=2024,
        current_class=primary_class, is_active=True
    )

    # Add slot on Monday
    TimetableSlot.all_objects.create(
        timetable_version=timetable_version, school=school,
        day_of_week=0, period_number=1,
        start_time=time(8, 0), end_time=time(9, 0),
        slot_type='lesson'
    )

    # Mock monday date
    monday = date(2024, 6, 10)  # 2024-06-10 was a Monday
    count = TimetableService.prefill_attendance_stubs(school, monday)
    assert count == 1

    from attendance.models import AttendanceRecord
    assert AttendanceRecord.all_objects.filter(student=student, date=monday).exists()


def test_api_timetable_version_crud(director_client, primary_class, current_term):
    # Create version
    res = director_client.post('/api/v1/timetable/versions/', {
        'class_group': str(primary_class.id),
        'academic_term': str(current_term.id),
        'version_number': 3,
        'effective_from': '2024-06-08',
        'is_active': True,
        'notes': 'Initial setup'
    }, format='json')
    assert res.status_code == 201
    version_id = res.data['id']

    # List versions
    res = director_client.get('/api/v1/timetable/versions/')
    assert res.status_code == 200
    assert len(res.data['results']) > 0


def test_api_timetable_slot_crud(director_client, timetable_version):
    res = director_client.post('/api/v1/timetable/slots/', {
        'timetable_version': str(timetable_version.id),
        'day_of_week': 0,
        'period_number': 1,
        'start_time': '08:00:00',
        'end_time': '09:00:00',
        'slot_type': 'lesson',
        'subject_name': 'English'
    }, format='json')
    assert res.status_code == 201

    # Check list
    res = director_client.get(f'/api/v1/timetable/slots/?timetable_version={timetable_version.id}')
    assert res.status_code == 200
    assert len(res.data['results']) == 1


def test_api_substitution_crud(director_client, timetable_version, teacher):
    slot = TimetableSlot.all_objects.create(
        timetable_version=timetable_version, school=timetable_version.school,
        day_of_week=0, period_number=1,
        start_time=time(8, 0), end_time=time(9, 0),
        slot_type='lesson', subject_name='Science'
    )

    res = director_client.post('/api/v1/timetable/substitutions/', {
        'timetable_slot': str(slot.id),
        'date': '2024-06-08',
        'substitute_teacher': str(teacher.id),
        'reason': 'Late arrival'
    }, format='json')
    assert res.status_code == 201


def test_api_timetable_version_validate_conflicts(director_client, timetable_version):
    res = director_client.get(f'/api/v1/timetable/versions/{timetable_version.id}/validate-conflicts/')
    assert res.status_code == 200
    assert 'conflicts' in res.data


def test_api_timetable_version_whatsapp_preview(director_client, timetable_version):
    res = director_client.get(f'/api/v1/timetable/versions/{timetable_version.id}/whatsapp-preview/')
    assert res.status_code == 200
    assert 'preview' in res.data
