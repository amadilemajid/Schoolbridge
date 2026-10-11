import pytest
from rest_framework import status
from django.contrib.auth import get_user_model

User = get_user_model()

@pytest.mark.django_db
class TestAPIStandardization:
    def test_kebab_case_routing(self, director_client):
        # The new URL (kebab-case) should return a 400 (bad request due to missing params), NOT a 404
        response_kebab = director_client.get('/api/v1/payments/fee-records/class-summary/')
        assert response_kebab.status_code == status.HTTP_400_BAD_REQUEST

        # The old URL (snake_case) should now return a 404 (not found)
        response_snake = director_client.get('/api/v1/payments/fee-records/class_summary/')
        assert response_snake.status_code == status.HTTP_404_NOT_FOUND

    def test_invalid_uuid_handling(self, director_client):
        # Query with an invalid integer should return 400
        response = director_client.get('/api/v1/students/?class_id=invalid-integer-format')
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert 'class_id' in response.data['detail']
        assert 'Must be a valid integer' in str(response.data['detail']['class_id'])

        # Query with an invalid UUID should return 400
        response = director_client.get('/api/v1/payments/fee-records/?student_id=invalid-uuid-format')
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert 'student_id' in response.data['detail']
        assert 'Must be a valid UUID' in str(response.data['detail']['student_id'])

    def test_standardized_error_format(self, director_client):
        # Attempt class reassignment without class_id. It should raise ValidationError,
        # which is formatted by the global exception handler into a standard envelope.
        import uuid
        random_uuid = str(uuid.uuid4())
        response = director_client.post(
            f'/api/v1/students/{random_uuid}/reassign_class/',
            data={},
            format='json'
        )
        # Note: If student is not found, get_object() in DRF raises 404, which is also standardized.
        # But we'll test the validation check when a valid student is used.
        # Let's create a student first to verify reassignment validation.
        from students.models import Student
        from schools.models import School
        school_obj = School.objects.first()
        student = Student.all_objects.create(
            school=school_obj,
            student_id='TEST-999',
            first_name='Standard',
            last_name='Test',
            gender='M',
            admission_date='2024-01-01',
            academic_year_admitted=2024,
            is_active=True
        )

        # POST reassignment without class_id
        response = director_client.post(
            f'/api/v1/students/{student.id}/reassign_class/',
            data={},
            format='json'
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert response.data['status_code'] == 400
        assert 'error' in response.data
        assert 'detail' in response.data
        assert 'class_id' in response.data['detail']

    def test_dashboard_views_query_validation(self, director_client):
        # GET academic dashboard with malformed term_id
        response = director_client.get('/api/v1/automation/academic-dashboard/?term_id=bad-uuid')
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert 'term_id' in response.data['detail']
