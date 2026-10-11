"""
Tests for Phase 1 production readiness remediation:
  - Timetable serializer tenant isolation & time validations
  - Onboarding serializer password strength & phone format
  - Risk views permission enforcement
  - HealthCheckView data masking
  - Onboarding service log durability on rollback
"""
import pytest
from datetime import time
from unittest.mock import patch, MagicMock
from rest_framework.test import APIClient

from schools.models import School, AcademicYear, AcademicTerm
from authentication.models import User
from students.models import Student, ClassGroup
from timetable.models import TimetableVersion, TimetableSlot
from timetable.serializers import TimetableSlotSerializer, TimetableVersionCreateSerializer
from onboarding.serializers import SchoolRegistrationRequestCreateSerializer
from onboarding.models import SchoolRegistrationRequest, SchoolProvisioningLog

pytestmark = pytest.mark.django_db


# ─── Fixtures ────────────────────────────────────────────────────────────────

@pytest.fixture
def school_a(db):
    return School.objects.create(
        name='School A', slug='school-a', district='Kampala',
        sub_county='Central', phone='+256700000001', email='a@school.ug',
        school_type='primary', is_active=True
    )


@pytest.fixture
def school_b(db):
    return School.objects.create(
        name='School B', slug='school-b', district='Wakiso',
        sub_county='Nansana', phone='+256700000002', email='b@school.ug',
        school_type='primary', is_active=True
    )


@pytest.fixture
def director_a(db, school_a):
    return User.objects.create_user(
        email='director_a@school.ug', password='Test@1234',
        role='director', school=school_a, is_staff=True, is_active=True
    )


@pytest.fixture
def director_b(db, school_b):
    return User.objects.create_user(
        email='director_b@school.ug', password='Test@1234',
        role='director', school=school_b, is_staff=True, is_active=True
    )


@pytest.fixture
def term_a(db, school_a):
    year = AcademicYear.objects.create(school=school_a, year=2026, is_current=True)
    return AcademicTerm.objects.create(
        school=school_a, academic_year=year, term_number=1,
        name='Term 1 2026', start_date='2026-01-06',
        end_date='2026-04-04', fee_deadline='2026-01-20',
        is_current=True, is_active=True, activated_at='2026-01-06T07:00:00Z',
        activated_by=None
    )


@pytest.fixture
def class_a(db, school_a):
    return ClassGroup.all_objects.create(school=school_a, name='P.1', level='P1')


@pytest.fixture
def class_b(db, school_b):
    return ClassGroup.all_objects.create(school=school_b, name='P.1', level='P1')


@pytest.fixture
def version_a(db, school_a, class_a, term_a, director_a):
    return TimetableVersion.all_objects.create(
        school=school_a, class_group=class_a, academic_term=term_a,
        version_number=1, is_active=True, effective_from='2026-01-06',
        created_by=director_a
    )


@pytest.fixture
def version_b(db, school_b, class_b):
    year = AcademicYear.objects.create(school=school_b, year=2026, is_current=True)
    term_b = AcademicTerm.objects.create(
        school=school_b, academic_year=year, term_number=1,
        name='Term 1 2026', start_date='2026-01-06',
        end_date='2026-04-04', fee_deadline='2026-01-20',
        is_current=True, is_active=True, activated_at='2026-01-06T07:00:00Z',
        activated_by=None
    )
    return TimetableVersion.all_objects.create(
        school=school_b, class_group=class_b, academic_term=term_b,
        version_number=1, is_active=True, effective_from='2026-01-06',
        created_by=None
    )


# ─── TimetableSlotSerializer Tests ────────────────────────────────────────────

class TestTimetableSlotSerializerTenantIsolation:

    def _make_request(self, user):
        request = MagicMock()
        request.user = user
        return request

    def test_rejects_slot_from_different_school_version(self, director_a, version_b):
        """School A director cannot reference School B's timetable version."""
        data = {
            'timetable_version': version_b.id,
            'day_of_week': 0,
            'period_number': 1,
            'start_time': '08:00:00',
            'end_time': '08:45:00',
            'slot_type': 'lesson',
        }
        serializer = TimetableSlotSerializer(
            data=data,
            context={'request': self._make_request(director_a)}
        )
        assert not serializer.is_valid()
        assert 'timetable_version' in str(serializer.errors).lower() or \
               'non_field_errors' in serializer.errors or \
               not serializer.is_valid()

    def test_rejects_end_time_before_start_time(self, director_a, version_a):
        """End time must be after start time."""
        data = {
            'timetable_version': version_a.id,
            'day_of_week': 0,
            'period_number': 1,
            'start_time': '10:00:00',
            'end_time': '09:00:00',  # before start
            'slot_type': 'lesson',
        }
        serializer = TimetableSlotSerializer(
            data=data,
            context={'request': self._make_request(director_a)}
        )
        assert not serializer.is_valid()
        errors_str = str(serializer.errors)
        assert 'end_time' in errors_str or 'non_field_errors' in errors_str

    def test_accepts_valid_slot_same_school(self, director_a, version_a):
        """Same-school slot with valid time range should pass serializer validation."""
        data = {
            'timetable_version': version_a.id,
            'day_of_week': 0,
            'period_number': 1,
            'start_time': '08:00:00',
            'end_time': '08:45:00',
            'slot_type': 'lesson',
        }
        serializer = TimetableSlotSerializer(
            data=data,
            context={'request': self._make_request(director_a)}
        )
        assert serializer.is_valid(), serializer.errors


# ─── TimetableVersionCreateSerializer Tests ────────────────────────────────────

class TestTimetableVersionCreateSerializerTenantIsolation:

    def _make_request(self, user):
        request = MagicMock()
        request.user = user
        return request

    def test_rejects_class_group_from_different_school(self, director_a, class_b, term_a):
        """School A director cannot create a version for School B class group."""
        data = {
            'class_group': class_b.id,
            'academic_term': term_a.id,
            'version_number': 1,
            'is_active': True,
            'effective_from': '2026-01-06',
        }
        serializer = TimetableVersionCreateSerializer(
            data=data,
            context={'request': self._make_request(director_a)}
        )
        assert not serializer.is_valid()
        assert 'class_group' in str(serializer.errors)


# ─── OnboardingSerializer Password & Phone Tests ──────────────────────────────

class TestSchoolRegistrationRequestCreateSerializer:

    def _make_valid_data(self, **overrides):
        base = {
            'school_name': 'Unique Academy UG',
            'admin_email': 'newdirector@unique.ug',
            'admin_first_name': 'Sarah',
            'admin_last_name': 'Namukasa',
            'admin_phone': '0772123456',
            'district': 'Kampala',
            'sub_county': 'Central',
            'school_type': 'primary',
            'admin_password': 'SecurePass@2026',
        }
        base.update(overrides)
        return base

    def test_accepts_valid_registration_data(self):
        serializer = SchoolRegistrationRequestCreateSerializer(data=self._make_valid_data())
        assert serializer.is_valid(), serializer.errors

    def test_requires_admin_password(self):
        data = self._make_valid_data()
        del data['admin_password']
        serializer = SchoolRegistrationRequestCreateSerializer(data=data)
        assert not serializer.is_valid()
        assert 'admin_password' in serializer.errors

    def test_rejects_weak_password_too_short(self):
        data = self._make_valid_data(admin_password='abc')
        serializer = SchoolRegistrationRequestCreateSerializer(data=data)
        assert not serializer.is_valid()
        assert 'admin_password' in serializer.errors

    def test_rejects_common_password(self):
        data = self._make_valid_data(admin_password='password123')
        serializer = SchoolRegistrationRequestCreateSerializer(data=data)
        assert not serializer.is_valid()
        assert 'admin_password' in serializer.errors

    def test_normalises_phone_with_leading_zero(self):
        data = self._make_valid_data(admin_phone='0772123456')
        serializer = SchoolRegistrationRequestCreateSerializer(data=data)
        assert serializer.is_valid(), serializer.errors
        assert serializer.validated_data['admin_phone'] == '+256772123456'

    def test_normalises_phone_with_country_code(self):
        data = self._make_valid_data(admin_phone='+256701999888')
        serializer = SchoolRegistrationRequestCreateSerializer(data=data)
        assert serializer.is_valid(), serializer.errors
        assert serializer.validated_data['admin_phone'] == '+256701999888'

    def test_rejects_invalid_phone_format(self):
        data = self._make_valid_data(admin_phone='0412345678')  # landline prefix
        serializer = SchoolRegistrationRequestCreateSerializer(data=data)
        assert not serializer.is_valid()
        assert 'admin_phone' in serializer.errors

    def test_rejects_duplicate_school_name(self, school_a):
        data = self._make_valid_data(school_name=school_a.name)
        serializer = SchoolRegistrationRequestCreateSerializer(data=data)
        assert not serializer.is_valid()
        assert 'school_name' in serializer.errors

    def test_rejects_duplicate_email(self, director_a):
        data = self._make_valid_data(admin_email=director_a.email)
        serializer = SchoolRegistrationRequestCreateSerializer(data=data)
        assert not serializer.is_valid()
        assert 'admin_email' in serializer.errors


# ─── Risk Views Permission Tests ──────────────────────────────────────────────

class TestRiskViewsPermissions:

    def _make_user(self, role, school):
        return User.objects.create_user(
            email=f'{role}@test.ug', password='Test@1234',
            role=role, school=school, is_active=True
        )

    def test_unauthenticated_cannot_access_risk_config(self, school_a):
        client = APIClient()
        res = client.get('/api/v1/risk/config/')
        assert res.status_code == 401

    def test_teacher_cannot_access_risk_config(self, school_a):
        teacher = self._make_user('teacher', school_a)
        client = APIClient()
        client.force_authenticate(user=teacher)
        res = client.get('/api/v1/risk/config/')
        assert res.status_code == 403

    def test_director_can_access_risk_config(self, school_a):
        director = self._make_user('director', school_a)
        client = APIClient()
        client.force_authenticate(user=director)
        res = client.get('/api/v1/risk/config/')
        assert res.status_code == 200

    def test_teacher_can_access_at_risk_list(self, school_a):
        """Teachers are school staff and should be allowed to view at-risk students."""
        teacher = self._make_user('teacher', school_a)
        client = APIClient()
        client.force_authenticate(user=teacher)
        res = client.get('/api/v1/risk/students/')
        assert res.status_code == 200

    def test_unauthenticated_cannot_access_at_risk_list(self, school_a):
        """Unauthenticated requests must be rejected."""
        client = APIClient()
        res = client.get('/api/v1/risk/students/')
        assert res.status_code == 401


# ─── HealthCheckView Masking Tests ────────────────────────────────────────────

class TestHealthCheckViewMasking:

    def test_public_request_hides_service_details(self):
        client = APIClient()
        res = client.get('/api/v1/onboarding/health/')
        assert res.status_code in (200, 503)
        # Public access should never expose services/database/redis details
        assert 'services' not in res.data

    def test_system_admin_sees_service_details(self, db):
        admin = User.objects.create_user(
            email='sysadmin@schoolbridge.ug', password='Admin@2026',
            role='system_admin', is_active=True
        )
        client = APIClient()
        client.force_authenticate(user=admin)
        res = client.get('/api/v1/onboarding/health/')
        assert res.status_code in (200, 503)
        assert 'services' in res.data


# ─── Onboarding Log Durability Tests ─────────────────────────────────────────

class TestOnboardingLogDurability:

    def test_logs_persisted_even_on_failed_provisioning(self, db):
        """Provisioning logs must survive transaction rollback."""
        from onboarding.services import SchoolProvisioningService

        # Pre-create a user to cause a conflict during director creation
        User.objects.create_user(
            email='conflict2@school.ug', password='Test@1234',
            role='teacher', first_name='Clash', last_name='Again'
        )

        req = SchoolRegistrationRequest.objects.create(
            school_name='Durable Fail School',
            admin_email='conflict2@school.ug',
            admin_first_name='Clash',
            admin_last_name='Again',
            admin_phone='+256782000000',
            district='Gulu',
            school_type='secondary',
            payload={}
        )

        with pytest.raises(ValueError):
            SchoolProvisioningService.provision_school(req, 'Test@1234')

        # All logs should exist despite transaction rollback
        assert SchoolProvisioningLog.objects.filter(
            registration_request=req
        ).exists()

        # The failed step specifically must be logged
        assert SchoolProvisioningLog.objects.filter(
            registration_request=req,
            step_name='create_director_user',
            status='failed'
        ).exists()

        # Successful prior steps should also be logged
        assert SchoolProvisioningLog.objects.filter(
            registration_request=req,
            step_name='create_school',
            status='success'
        ).exists()

        # School creation itself should have been rolled back (no orphan data)
        assert not School.objects.filter(name='Durable Fail School').exists()
