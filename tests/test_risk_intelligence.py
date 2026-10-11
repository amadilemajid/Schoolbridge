import pytest
from decimal import Decimal
from django.utils import timezone
from unittest.mock import patch

from schools.models import School, AcademicYear, AcademicTerm
from students.models import Student, ClassGroup
from payments.models import FeeRecord, PaymentPlan, PaymentPlanInstalment
from attendance.models import AttendanceRecord
from risk.models import RiskConfiguration, StudentRiskProfile, StudentRiskSnapshot
from risk.services import RiskEvaluationEngine

pytestmark = pytest.mark.django_db


@pytest.fixture
def test_student(db, school, primary_class):
    return Student.all_objects.create(
        school=school,
        student_id='TEST-STUDENT-001',
        first_name='Kato',
        last_name='John',
        gender='M',
        admission_date='2024-01-15',
        academic_year_admitted=2024,
        current_class=primary_class,
        is_active=True
    )


@pytest.fixture
def risk_config(db, school):
    config, _ = RiskConfiguration.objects.get_or_create(
        school=school,
        defaults={
            'attendance_threshold': 75.00,
            'fee_payment_ratio_threshold': 50.00,
            'outstanding_balance_threshold': 100000,
            'grace_period_days': 10,
            'enable_whatsapp_alerts': True,
            'enable_monday_briefing': True
        }
    )
    return config


def test_risk_score_calculation_low(school, current_term, test_student, risk_config):
    # 1. Mock attendance: 9 present out of 10 (90%)
    for i in range(10):
        AttendanceRecord.all_objects.create(
            school=school,
            student=test_student,
            class_group=test_student.current_class,
            academic_term=current_term,
            date=timezone.localdate() - timezone.timedelta(days=i),
            status='present' if i > 0 else 'absent'
        )

    # 2. Mock fees: paid 400,000 out of 500,000 (80%)
    FeeRecord.all_objects.create(
        school=school,
        student=test_student,
        academic_term=current_term,
        total_amount=Decimal('500000'),
        amount_paid=Decimal('400000'),
    )

    profile = RiskEvaluationEngine.evaluate_student(test_student, current_term, risk_config)
    assert profile.risk_level == 'low'
    assert profile.risk_score < 40
    assert 'low_attendance' not in profile.flagged_factors
    assert 'fee_defaulter' not in profile.flagged_factors


def test_risk_score_calculation_high(school, current_term, test_student, risk_config):
    # 1. Mock attendance: 6 absent, 4 present out of 10 (40% rate)
    for i in range(10):
        AttendanceRecord.all_objects.create(
            school=school,
            student=test_student,
            class_group=test_student.current_class,
            academic_term=current_term,
            date=timezone.localdate() - timezone.timedelta(days=i),
            status='absent' if i < 6 else 'present'
        )

    # 2. Mock fees: paid 100,000 out of 500,000 (20%)
    FeeRecord.all_objects.create(
        school=school,
        student=test_student,
        academic_term=current_term,
        total_amount=Decimal('500000'),
        amount_paid=Decimal('100000'),
    )

    profile = RiskEvaluationEngine.evaluate_student(test_student, current_term, risk_config)
    assert profile.risk_level == 'high'
    assert profile.risk_score >= 70
    assert 'low_attendance' in profile.flagged_factors
    assert 'fee_defaulter' in profile.flagged_factors


def test_grace_period_skips_evaluation(school, current_term, test_student, risk_config):
    # Only 5 attendance records (grace period is 10 days)
    for i in range(5):
        AttendanceRecord.all_objects.create(
            school=school,
            student=test_student,
            class_group=test_student.current_class,
            academic_term=current_term,
            date=timezone.localdate() - timezone.timedelta(days=i),
            status='absent'
        )

    profile = RiskEvaluationEngine.evaluate_student(test_student, current_term, risk_config)
    # Even though attendance rate is 0%, grace period applies
    assert profile.attendance_rate == Decimal('100.00')
    assert 'low_attendance' not in profile.flagged_factors


def test_fee_defaulter_with_active_payment_plan_not_flagged(school, current_term, test_student, risk_config):
    # Student has low fee payment ratio, but is on active payment plan with no overdue instalments
    fee_rec = FeeRecord.all_objects.create(
        school=school,
        student=test_student,
        academic_term=current_term,
        total_amount=Decimal('600000'),
        amount_paid=Decimal('100000'),
    )

    plan = PaymentPlan.all_objects.create(
        school=school,
        fee_record=fee_rec,
        student=test_student,
        total_amount=Decimal('500000'),
        status='active'
    )

    # Instalment not overdue (due in future)
    PaymentPlanInstalment.objects.create(
        payment_plan=plan,
        instalment_number=1,
        amount_due=Decimal('200000'),
        due_date=timezone.localdate() + timezone.timedelta(days=10),
        status='pending'
    )

    # Check that is_flagged remains false for fees
    profile = RiskEvaluationEngine.evaluate_student(test_student, current_term, risk_config)
    assert 'fee_defaulter' not in profile.flagged_factors


def test_batch_recalculation_creates_profiles(school, current_term, test_student, risk_config):
    # Evaluates school
    profiles = RiskEvaluationEngine.recalculate_school(school, current_term)
    assert len(profiles) == 1
    assert StudentRiskProfile.objects.filter(school=school).count() == 1


def test_batch_recalculation_creates_snapshots(school, current_term, test_student, risk_config):
    RiskEvaluationEngine.recalculate_school(school, current_term)
    assert StudentRiskSnapshot.objects.filter(school=school).count() == 1


def test_api_risk_config_get(director_client, risk_config):
    res = director_client.get('/api/v1/risk/config/')
    assert res.status_code == 200
    assert 'attendance_threshold' in res.data


def test_api_risk_config_update(director_client, risk_config):
    res = director_client.patch('/api/v1/risk/config/', {'grace_period_days': 15}, format='json')
    assert res.status_code == 200
    risk_config.refresh_from_db()
    assert risk_config.grace_period_days == 15


def test_api_at_risk_students_list(director_client, school, current_term, test_student, risk_config):
    RiskEvaluationEngine.recalculate_school(school, current_term)
    res = director_client.get('/api/v1/risk/students/')
    assert res.status_code == 200
    assert len(res.data['results']) == 1


def test_api_at_risk_students_filter_by_level(director_client, school, current_term, test_student, risk_config):
    # Set to high risk manually
    RiskEvaluationEngine.recalculate_school(school, current_term)
    StudentRiskProfile.objects.filter(student=test_student).update(risk_level='high')

    res = director_client.get('/api/v1/risk/students/?risk_level=high')
    assert res.status_code == 200
    assert len(res.data['results']) == 1

    res = director_client.get('/api/v1/risk/students/?risk_level=low')
    assert res.status_code == 200
    assert len(res.data['results']) == 0


def test_api_trigger_recalculation(director_client, school, current_term, test_student, risk_config):
    res = director_client.post('/api/v1/risk/recalculate/')
    assert res.status_code == 200
    assert StudentRiskProfile.objects.filter(student=test_student).exists()


def test_api_monday_briefing(director_client, school, current_term, test_student, risk_config):
    RiskEvaluationEngine.recalculate_school(school, current_term)
    res = director_client.get('/api/v1/risk/briefing/')
    assert res.status_code == 200
    assert 'high_risk_count' in res.data
    assert 'medium_risk_count' in res.data


def test_alert_not_sent_if_already_dispatched(school, current_term, test_student, risk_config):
    from risk.tasks import recalculate_school_risk_task
    
    # Calculate initial profile and set alert_dispatched = True
    profile = RiskEvaluationEngine.evaluate_student(test_student, current_term, risk_config)
    profile.risk_level = 'high'
    profile.alert_dispatched = True
    profile.save()

    with patch('risk.tasks.send_high_risk_alert.delay') as mock_alert:
        recalculate_school_risk_task(str(school.id), str(current_term.id))
        mock_alert.assert_not_called()


def test_whatsapp_alert_message_format(school, current_term, test_student, risk_config):
    from risk.tasks import send_high_risk_alert
    
    # Calculate profile
    profile = RiskEvaluationEngine.evaluate_student(test_student, current_term, risk_config)
    profile.risk_level = 'high'
    profile.risk_score = 80
    profile.flagged_factors = ['low_attendance', 'fee_defaulter']
    profile.save()

    # Director user exists (fixture)
    from django.contrib.auth import get_user_model
    User = get_user_model()
    User.objects.create_user(
        email='director_alert@school.ug',
        password='testpass123',
        role='director',
        school=school,
        phone='+256701112222',
        first_name='Director',
        last_name='Alert'
    )

    with patch('messaging.services.WhatsAppService.send_text_message', return_value=('msg_123', True)) as mock_send:
        send_high_risk_alert(str(profile.id))
        assert mock_send.called
        args, kwargs = mock_send.call_args
        assert kwargs['to_phone'] == '+256701112222'
        assert '*SchoolBridge At-Risk Alert*' in kwargs['text']
        assert 'Kato John' in kwargs['text']
        assert '80/100' in kwargs['text']
