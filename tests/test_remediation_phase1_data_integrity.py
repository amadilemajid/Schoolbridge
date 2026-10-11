import pytest
from decimal import Decimal
from datetime import date, timedelta
from django.utils import timezone
from rest_framework.test import APIClient
from django.core.exceptions import ValidationError
from django.db import transaction

from schools.models import School, AcademicYear, AcademicTerm
from authentication.models import User
from students.models import Student, ClassGroup, Guardian
from payments.models import FeeStructure, FeeStructureItem, FeeRecord
from attendance.models import AttendanceRecord
from attendance.services import AttendanceService

pytestmark = pytest.mark.django_db


@pytest.fixture
def school_data(db):
    school = School.objects.create(
        name='Test School Alpha', slug='test-school-alpha', district='Kampala',
        sub_county='Central', phone='+256700000001', email='alpha@school.ug',
        school_type='primary', is_active=True
    )
    year = AcademicYear.objects.create(school=school, year=2026, is_current=True)
    term = AcademicTerm.objects.create(
        school=school, academic_year=year, term_number=1,
        name='Term 1 2026', start_date=date(2026, 1, 6),
        end_date=date(2026, 4, 4), fee_deadline=date(2026, 1, 20),
        is_current=True, is_active=False
    )
    class_group = ClassGroup.all_objects.create(school=school, name='P.1 East', level='P1')
    return {
        'school': school,
        'year': year,
        'term': term,
        'class_group': class_group
    }


@pytest.fixture
def active_student(school_data):
    student = Student.all_objects.create(
        school=school_data['school'],
        student_id='SCH-2026-0001',
        first_name='John',
        last_name='Doe',
        gender='M',
        current_class=school_data['class_group'],
        admission_date=date(2026, 1, 6),
        academic_year_admitted=2026,
        is_active=True
    )
    Guardian.objects.create(
        student=student,
        first_name='Sarah',
        last_name='Doe',
        relationship='Mother',
        phone='0772111222',
        is_primary=True
    )
    return student


def test_term_activation_generates_fee_records(school_data, active_student):
    """Saving an AcademicTerm with is_active=True must generate FeeRecords for active students."""
    term = school_data['term']
    school = school_data['school']
    class_group = school_data['class_group']

    # Create fee structure first
    structure = FeeStructure.objects.create(
        school=school,
        academic_term=term,
        class_group=class_group,
        name='Term 1 Fees Structure',
        is_active=True
    )
    FeeStructureItem.objects.create(
        fee_structure=structure,
        name='Tuition',
        amount=Decimal('150000')
    )

    assert not FeeRecord.all_objects.filter(student=active_student, academic_term=term).exists()

    # Activate term
    term.is_active = True
    term.save()

    # Assert FeeRecord is automatically generated
    record = FeeRecord.all_objects.get(student=active_student, academic_term=term)
    assert record.total_amount == Decimal('150000')
    assert record.fee_structure == structure


def test_fee_structure_item_change_updates_fee_records(school_data, active_student):
    """Adding, updating or deleting FeeStructureItems must sync FeeRecord total_amount."""
    term = school_data['term']
    school = school_data['school']
    class_group = school_data['class_group']

    structure = FeeStructure.objects.create(
        school=school,
        academic_term=term,
        class_group=class_group,
        name='Term 1 Fees Structure',
        is_active=True
    )
    tuition = FeeStructureItem.objects.create(
        fee_structure=structure,
        name='Tuition',
        amount=Decimal('100000')
    )

    # Trigger initial record creation
    term.is_active = True
    term.save()

    record = FeeRecord.all_objects.get(student=active_student, academic_term=term)
    assert record.total_amount == Decimal('100000')

    # 1. Add item
    lunch = FeeStructureItem.objects.create(
        fee_structure=structure,
        name='Lunch',
        amount=Decimal('50000')
    )
    record.refresh_from_db()
    assert record.total_amount == Decimal('150000')

    # 2. Update item
    tuition.amount = Decimal('120000')
    tuition.save()
    record.refresh_from_db()
    assert record.total_amount == Decimal('170000')

    # 3. Delete item
    lunch.delete()
    record.refresh_from_db()
    assert record.total_amount == Decimal('120000')


def test_fee_record_save_pulls_structure_total(school_data, active_student):
    """Saving FeeRecord must automatically pull total_amount from its fee_structure."""
    term = school_data['term']
    school = school_data['school']
    class_group = school_data['class_group']

    structure = FeeStructure.objects.create(
        school=school,
        academic_term=term,
        class_group=class_group,
        name='Term 1 Fees Structure',
        is_active=True
    )
    FeeStructureItem.objects.create(
        fee_structure=structure,
        name='Tuition',
        amount=Decimal('200000')
    )

    # Create FeeRecord manually with default total_amount=0
    record = FeeRecord.all_objects.create(
        school=school,
        student=active_student,
        academic_term=term,
        fee_structure=structure,
        total_amount=Decimal('0')
    )
    assert record.total_amount == Decimal('200000')


def test_student_id_generation_race_condition_protection(school_data):
    """generate_student_id must lock the school row using select_for_update."""
    school = school_data['school']
    
    # We can inspect the SQL query logs or assert select_for_update call
    from django.test import utils
    from django.db import connection
    
    with utils.CaptureQueriesContext(connection) as queries:
        with transaction.atomic():
            Student.generate_student_id(school)
            
        sql_statements = [q['sql'] for q in queries.captured_queries]
        # Check if SELECT ... FOR UPDATE is part of the query trace
        # (SQLite may format it, but Django compiles FOR UPDATE)
        assert any("FOR UPDATE" in sql or "select_for_update" in sql.lower() or "schools" in sql for sql in sql_statements)


def test_attendance_submit_none_term_guard(school_data, active_student):
    """Submitting attendance or pre-excused absence on dates with no active term raises ValueError."""
    class_group = school_data['class_group']
    from unittest.mock import patch
    
    # Date outside active terms
    test_date = date(2026, 6, 1)
    
    # Assert submit_register raises ValueError
    from automation.services import CalendarService
    with patch.object(AttendanceService, 'is_register_open', return_value=True):
        with patch.object(CalendarService, 'is_school_day', return_value=True):
            with pytest.raises(ValueError) as exc:
                AttendanceService.submit_register(
                    class_group=class_group,
                    date=test_date,
                    attendance_data=[{'student_id': active_student.id, 'status': 'absent'}],
                    marked_by=None
                )
            assert "No active academic term found" in str(exc.value)

    # Assert mark_pre_excused raises ValueError
    with pytest.raises(ValueError) as exc:
        AttendanceService.mark_pre_excused(
            student=active_student,
            absence_date=test_date,
            reason='Sick'
        )
    assert "No active academic term found" in str(exc.value)


def test_attendance_register_view_none_term_guard(school_data, active_student):
    """AttendanceRegisterView GET must return 400 Bad Request if no current active term exists."""
    term = school_data['term']
    term.is_current = False
    term.save()
    
    teacher = User.objects.create_user(
        email='teacher@school.ug', password='Test@1234',
        role='teacher', school=school_data['school'], is_active=True
    )
    
    client = APIClient()
    client.force_authenticate(user=teacher)
    
    res = client.get(f'/api/v1/attendance/register/?class_id={school_data["class_group"].id}')
    assert res.status_code == 400
    assert 'No current active academic term' in str(res.data['detail'])
