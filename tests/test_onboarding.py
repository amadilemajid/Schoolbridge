import pytest
from unittest.mock import patch
from django.utils import timezone
from rest_framework.test import APIClient

from schools.models import School, AcademicYear, AcademicTerm
from authentication.models import User
from students.models import ClassGroup
from risk.models import RiskConfiguration
from onboarding.models import SchoolRegistrationRequest, SchoolProvisioningLog
from onboarding.services import SchoolProvisioningService

pytestmark = pytest.mark.django_db


def test_atomic_onboarding_pipeline_success(db):
    payload = {
        'school_name': 'Greenhill Academy',
        'admin_email': 'director@greenhill.ug',
        'admin_first_name': 'Jane',
        'admin_last_name': 'Nanziri',
        'admin_phone': '+256772111222',
        'district': 'Wakiso',
        'school_type': 'primary',
        'admin_password': 'Sb@Password123',
        'payload': {
            'academic_year': 2026,
            'term_number': 1,
            'classes': ['P.1', 'P.2', 'P.3']
        }
    }

    req = SchoolRegistrationRequest.objects.create(
        school_name=payload['school_name'],
        admin_email=payload['admin_email'],
        admin_first_name=payload['admin_first_name'],
        admin_last_name=payload['admin_last_name'],
        admin_phone=payload['admin_phone'],
        district=payload['district'],
        school_type=payload['school_type'],
        payload=payload['payload']
    )

    school = SchoolProvisioningService.provision_school(req, payload['admin_password'])
    
    # Assert school tenant created
    assert school is not None
    assert school.name == 'Greenhill Academy'
    assert school.slug == 'greenhill-academy'
    
    # Assert director user created
    user = User.objects.get(email='director@greenhill.ug')
    assert user.role == 'director'
    assert user.school == school
    assert user.is_staff
    assert user.is_active

    # Assert academic year and term created
    year = AcademicYear.objects.get(school=school, year=2026)
    assert year.is_current
    term = AcademicTerm.objects.get(school=school, academic_year=year, term_number=1)
    assert term.is_current
    assert term.is_active

    # Assert classes created
    classes = ClassGroup.all_objects.filter(school=school)
    assert classes.count() == 3
    assert set(classes.values_list('name', flat=True)) == {'P.1', 'P.2', 'P.3'}

    # Assert default Risk configuration created
    assert RiskConfiguration.objects.filter(school=school).exists()

    # Assert logs created
    assert SchoolProvisioningLog.objects.filter(registration_request=req, status='success').count() > 0


def test_atomic_onboarding_pipeline_rollback_on_failure(db):
    # Create a user with conflicting email beforehand
    User.objects.create_user(
        email='conflict@school.ug',
        password='somepassword',
        role='teacher',
        first_name='Clash',
        last_name='User'
    )

    payload = {
        'school_name': 'Failure Academy',
        'admin_email': 'conflict@school.ug',  # will fail user creation
        'admin_first_name': 'John',
        'admin_last_name': 'Doe',
        'admin_phone': '+256772111333',
        'district': 'Kampala',
        'school_type': 'secondary',
        'admin_password': 'Sb@Password123',
        'payload': {}
    }

    req = SchoolRegistrationRequest.objects.create(
        school_name=payload['school_name'],
        admin_email=payload['admin_email'],
        admin_first_name=payload['admin_first_name'],
        admin_last_name=payload['admin_last_name'],
        admin_phone=payload['admin_phone'],
        district=payload['district'],
        school_type=payload['school_type'],
        payload=payload['payload']
    )

    with pytest.raises(ValueError):
        SchoolProvisioningService.provision_school(req, payload['admin_password'])

    # Verify rollback: no School with name 'Failure Academy' should exist
    assert not School.objects.filter(name='Failure Academy').exists()
    assert req.status == 'failed'
    
    # Provisioning logs should show failure step
    assert SchoolProvisioningLog.objects.filter(
        registration_request=req,
        step_name='create_director_user',
        status='failed'
    ).exists()


def test_public_onboarding_api_register_endpoint(db):
    client = APIClient()
    data = {
        'school_name': 'API Academy',
        'admin_email': 'api-admin@school.ug',
        'admin_first_name': 'API',
        'admin_last_name': 'User',
        'admin_phone': '+256701123456',
        'district': 'Jinju',
        'school_type': 'primary',
        'admin_password': 'APIpassword123',
        'payload': {
            'classes': ['P.1']
        }
    }
    
    res = client.post('/api/v1/onboarding/register/', data, format='json')
    assert res.status_code == 201
    assert res.data['status'] == 'completed'
    assert 'school_id' in res.data
    assert res.data['admin_email'] == 'api-admin@school.ug'


def test_health_check_endpoint(db):
    client = APIClient()
    res = client.get('/api/v1/onboarding/health/')
    assert res.status_code == 200
    assert res.data['status'] == 'healthy'
    # Public access must NOT expose internal service details (security masking)
    assert 'services' not in res.data
    assert 'status' in res.data
    assert 'timestamp' in res.data



def test_swagger_documentation_endpoint(db):
    client = APIClient()
    res = client.get('/api/docs/')
    assert res.status_code == 200
    assert 'swagger' in res.content.decode().lower() or 'redoc' in res.content.decode().lower() or res.headers.get('Content-Type', '').startswith('text/html')
