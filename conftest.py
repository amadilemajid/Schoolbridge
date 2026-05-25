"""
pytest configuration for SchoolBridge.
Global fixtures available in all tests.
"""
import pytest
from django.contrib.auth import get_user_model
from schools.models import School, AcademicYear, AcademicTerm
from students.models import ClassGroup

User = get_user_model()


@pytest.fixture
def school(db):
    """A fully configured test school."""
    return School.objects.create(
        name='Kampala Test School',
        slug='kampala-test-school',
        district='Kampala',
        phone='+256701234567',
        email='test@school.ug',
        school_type='combined',
    )


@pytest.fixture
def academic_year(db, school):
    return AcademicYear.objects.create(school=school, year=2024, is_current=True)


@pytest.fixture
def current_term(db, school, academic_year):
    return AcademicTerm.objects.create(
        school=school,
        academic_year=academic_year,
        term_number=1,
        name='Term 1 2024',
        start_date='2024-02-05',
        end_date='2024-05-31',
        fee_deadline='2024-03-15',
        is_current=True,
        is_active=True,
    )


@pytest.fixture
def director(db, school):
    return User.objects.create_user(
        email='director@school.ug',
        password='testpass123',
        role='director',
        school=school,
        first_name='Director',
        last_name='Test',
    )


@pytest.fixture
def bursar(db, school):
    return User.objects.create_user(
        email='bursar@school.ug',
        password='testpass123',
        role='bursar',
        school=school,
        first_name='Bursar',
        last_name='Test',
    )


@pytest.fixture
def teacher(db, school):
    return User.objects.create_user(
        email='teacher@school.ug',
        password='testpass123',
        role='teacher',
        school=school,
        first_name='Teacher',
        last_name='Test',
    )


@pytest.fixture
def primary_class(db, school):
    return ClassGroup.all_objects.create(
        school=school, name='P.7 East', level='P7', stream='East'
    )


@pytest.fixture
def api_client():
    from rest_framework.test import APIClient
    return APIClient()


@pytest.fixture
def director_client(api_client, director):
    """API client authenticated as director."""
    response = api_client.post('/api/v1/auth/login/', {
        'email': director.email,
        'password': 'testpass123',
    }, format='json')
    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {response.data['access']}")
    return api_client


@pytest.fixture
def bursar_client(api_client, bursar):
    response = api_client.post('/api/v1/auth/login/', {
        'email': bursar.email,
        'password': 'testpass123',
    }, format='json')
    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {response.data['access']}")
    return api_client
