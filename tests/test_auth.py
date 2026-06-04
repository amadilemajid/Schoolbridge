"""
Authentication tests — lockout, password history, token rotation, role permissions.
"""
from django.test import TestCase
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from schools.models import School
import uuid

User = get_user_model()


def make_school():
    return School.objects.create(
        name=f"Auth Test School {uuid.uuid4().hex[:4]}",
        slug=f"auth-test-{uuid.uuid4().hex[:4]}",
        district='Kampala', phone='+256701234567',
        email='auth@school.ug', school_type='primary',
    )


class LoginLockoutTest(TestCase):
    """US-002: Account locked after 5 failed attempts for 15 minutes."""

    def setUp(self):
        self.school = make_school()
        self.user = User.objects.create_user(
            email='teacher@school.ug', password='correct_password_123',
            role='teacher', school=self.school,
            first_name='Jane', last_name='Teacher',
        )
        self.client = APIClient()

    def test_lockout_after_five_failures(self):
        """User is locked out after 5 wrong password attempts."""
        for i in range(5):
            self.client.post('/api/v1/auth/login/', {
                'email': 'teacher@school.ug',
                'password': 'wrong_password',
            }, format='json')

        self.user.refresh_from_db()
        self.assertTrue(self.user.is_locked)
        self.assertIsNotNone(self.user.locked_until)

    def test_correct_login_resets_failed_count(self):
        """Successful login resets the failed attempt counter."""
        for i in range(3):
            self.client.post('/api/v1/auth/login/', {
                'email': 'teacher@school.ug',
                'password': 'wrong',
            }, format='json')

        response = self.client.post('/api/v1/auth/login/', {
            'email': 'teacher@school.ug',
            'password': 'correct_password_123',
        }, format='json')

        self.assertEqual(response.status_code, 200)
        self.user.refresh_from_db()
        self.assertEqual(self.user.failed_login_count, 0)

    def test_locked_user_cannot_login(self):
        """Locked user gets 400 response even with correct password."""
        from django.utils import timezone
        import datetime
        self.user.failed_login_count = 5
        self.user.locked_until = timezone.now() + datetime.timedelta(minutes=15)
        self.user.save()

        response = self.client.post('/api/v1/auth/login/', {
            'email': 'teacher@school.ug',
            'password': 'correct_password_123',
        }, format='json')
        self.assertEqual(response.status_code, 400)
        # DRF ValidationError surfaces under non_field_errors
        error_text = str(response.data).lower()
        self.assertIn('locked', error_text)


class RolePermissionTest(TestCase):
    """US-003: Bursar cannot edit marks. Teacher cannot access fees."""

    def setUp(self):
        self.school = make_school()
        self.bursar = User.objects.create_user(
            email='bursar@school.ug', password='pass123456',
            role='bursar', school=self.school,
            first_name='Bill', last_name='Bursar',
        )
        self.teacher = User.objects.create_user(
            email='teacher@school.ug', password='pass123456',
            role='teacher', school=self.school,
            first_name='Tom', last_name='Teacher',
        )
        self.client = APIClient()

    def _login(self, user):
        response = self.client.post('/api/v1/auth/login/', {
            'email': user.email, 'password': 'pass123456',
        }, format='json')
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {response.data['access']}")

    def test_teacher_cannot_access_fee_dashboard(self):
        """Teacher role is blocked from fee management endpoints."""
        self._login(self.teacher)
        response = self.client.get('/api/v1/payments/fee-records/dashboard/')
        self.assertIn(response.status_code, [403, 401])

    def test_bursar_can_access_payments(self):
        """Bursar can access payment endpoints."""
        self._login(self.bursar)
        response = self.client.get('/api/v1/payments/payments/')
        self.assertNotEqual(response.status_code, 403)

    def test_deactivated_user_cannot_login(self):
        """US-006: Deactivated user is rejected at login."""
        self.teacher.is_active = False
        self.teacher.save()
        response = self.client.post('/api/v1/auth/login/', {
            'email': 'teacher@school.ug', 'password': 'pass123456',
        }, format='json')
        self.assertEqual(response.status_code, 400)
