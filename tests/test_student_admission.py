import uuid
from datetime import date
from django.test import TestCase
from rest_framework.test import APIRequestFactory
from authentication.models import User
from schools.models import School
from students.models import Student, ClassGroup, Guardian
from students.serializers import StudentListSerializer, StudentDetailSerializer, StudentCreateSerializer


class StudentAdmissionNumberTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(name="Test School Kampala", slug="test-sch")
        self.user = User.objects.create_user(
            email="director@test.ug",
            password="Password123!",
            role="director",
            school=self.school,
            first_name="Director",
            last_name="Test"
        )
        self.bursar = User.objects.create_user(
            email="bursar@test.ug",
            password="Password123!",
            role="bursar",
            school=self.school,
            first_name="Bursar",
            last_name="Test"
        )
        self.factory = APIRequestFactory()

    def test_student_model_admission_number_property(self):
        student = Student.all_objects.create(
            school=self.school,
            student_id="KDA-2026-001",
            first_name="Brian",
            last_name="Ssemakula",
            gender="M",
            admission_date=date(2026, 1, 15),
            academic_year_admitted=2026,
        )
        self.assertEqual(student.admission_number, "KDA-2026-001")
        self.assertEqual(student.student_id, "KDA-2026-001")

    def test_student_serializers_expose_admission_number(self):
        student = Student.all_objects.create(
            school=self.school,
            student_id="KDA-2026-002",
            first_name="Alice",
            last_name="Nakato",
            gender="F",
            admission_date=date(2026, 1, 15),
            academic_year_admitted=2026,
        )
        request = self.factory.get('/api/v1/students/')
        request.user = self.user

        list_serializer = StudentListSerializer(student, context={'request': request})
        self.assertIn('admission_number', list_serializer.data)
        self.assertEqual(list_serializer.data['admission_number'], "KDA-2026-002")

        detail_serializer = StudentDetailSerializer(student, context={'request': request})
        self.assertIn('admission_number', detail_serializer.data)
        self.assertEqual(detail_serializer.data['admission_number'], "KDA-2026-002")

    def test_student_create_with_custom_admission_number(self):
        request = self.factory.post('/api/v1/students/')
        request.user = self.user

        payload = {
            'first_name': 'Sarah',
            'last_name': 'Nantongo',
            'admission_number': 'KDA-2026-006',
            'date_of_birth': '2013-05-20',
            'gender': 'F',
            'admission_date': '2026-02-01',
            'guardian_first_name': 'Peter',
            'guardian_last_name': 'Nantongo',
            'guardian_phone': '+256772100006',
            'guardian_relationship': 'Father',
        }

        serializer = StudentCreateSerializer(data=payload, context={'request': request})
        self.assertTrue(serializer.is_valid(), serializer.errors)
        created_student = serializer.save()

        self.assertEqual(created_student.student_id, 'KDA-2026-006')
        self.assertEqual(created_student.admission_number, 'KDA-2026-006')

    def test_student_create_duplicate_admission_number_raises_error(self):
        Student.all_objects.create(
            school=self.school,
            student_id="KDA-2026-006",
            first_name="Existing",
            last_name="Student",
            gender="F",
            admission_date=date(2026, 1, 15),
            academic_year_admitted=2026,
        )

        request = self.factory.post('/api/v1/students/')
        request.user = self.user

        payload = {
            'first_name': 'Sarah',
            'last_name': 'Nantongo',
            'admission_number': 'KDA-2026-006',
            'date_of_birth': '2013-05-20',
            'gender': 'F',
            'admission_date': '2026-02-01',
            'guardian_first_name': 'Peter',
            'guardian_last_name': 'Nantongo',
            'guardian_phone': '+256772100006',
            'guardian_relationship': 'Father',
        }

        serializer = StudentCreateSerializer(data=payload, context={'request': request})
        self.assertFalse(serializer.is_valid())
        self.assertIn('admission_number', serializer.errors)

    def test_student_create_without_admission_number_auto_generates(self):
        request = self.factory.post('/api/v1/students/')
        request.user = self.user

        payload = {
            'first_name': 'David',
            'last_name': 'Okello',
            'date_of_birth': '2014-06-10',
            'gender': 'M',
            'admission_date': '2026-02-01',
            'guardian_first_name': 'Grace',
            'guardian_last_name': 'Okello',
            'guardian_phone': '+256772100007',
            'guardian_relationship': 'Mother',
        }

        serializer = StudentCreateSerializer(data=payload, context={'request': request})
        self.assertTrue(serializer.is_valid(), serializer.errors)
        created_student = serializer.save()

        self.assertTrue(created_student.student_id.startswith('SCH-'))
        self.assertEqual(created_student.admission_number, created_student.student_id)
