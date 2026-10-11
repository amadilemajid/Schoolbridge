import csv
import io
from decimal import Decimal
from django.test import TestCase
from rest_framework.test import APIClient
from rest_framework import status
from authentication.models import User
from schools.models import School, AcademicYear, AcademicTerm
from students.models import ClassGroup, Student
from results.models import Subject, Assessment, AssessmentMark, TermResult


class ResultsModuleTestCase(TestCase):
    def setUp(self):
        # Create Primary Tenant
        self.school = School.objects.create(
            name="Kampala Model School",
            slug="kampala-model",
            district="Kampala",
            phone="+256700000001",
            email="info@kms.ac.ug",
            school_type="combined",
        )

        # Create Secondary Tenant for Tenant Isolation Testing
        self.school_other = School.objects.create(
            name="Entebbe Secondary School",
            slug="entebbe-ss",
            district="Wakiso",
            phone="+256700000002",
            email="info@ess.ac.ug",
            school_type="secondary",
        )

        # Users — create_user(email, password, **extra)
        self.director = User.objects.create_user(
            email="director@kms.ac.ug",
            password="Password123!",
            role="director",
            school=self.school,
            first_name="Joseph",
            last_name="Director",
        )

        self.teacher = User.objects.create_user(
            email="teacher@kms.ac.ug",
            password="Password123!",
            role="teacher",
            school=self.school,
            first_name="Sarah",
            last_name="Nakamya",
        )

        self.teacher_other = User.objects.create_user(
            email="teacher@ess.ac.ug",
            password="Password123!",
            role="teacher",
            school=self.school_other,
            first_name="David",
            last_name="Kato",
        )

        # Academic Calendar
        self.academic_year = AcademicYear.objects.create(
            school=self.school,
            year=2026,
            is_current=True,
        )

        self.academic_term = AcademicTerm.objects.create(
            school=self.school,
            academic_year=self.academic_year,
            term_number=1,
            name="Term 1 2026",
            start_date="2026-02-01",
            end_date="2026-05-01",
            fee_deadline="2026-02-15",
            is_current=True,
            is_active=True,
        )

        # Class Group & Subject
        self.class_group = ClassGroup.objects.create(
            school=self.school,
            name="P.7 East",
            level="P7",
            stream="East",
        )

        self.subject = Subject.objects.create(
            school=self.school,
            name="Mathematics",
            code="MTC",
            class_levels="P7",
        )

        # Students
        self.student1 = Student.objects.create(
            school=self.school,
            student_id="SCH-2026-0001",
            first_name="Irene",
            last_name="Babirye",
            gender="F",
            current_class=self.class_group,
            admission_date="2026-01-10",
            academic_year_admitted=2026,
        )

        self.student2 = Student.objects.create(
            school=self.school,
            student_id="SCH-2026-0002",
            first_name="John",
            last_name="Mukasa",
            gender="M",
            current_class=self.class_group,
            admission_date="2026-01-10",
            academic_year_admitted=2026,
        )

        # API Clients
        self.teacher_client = APIClient()
        self.teacher_client.force_authenticate(user=self.teacher)

        self.director_client = APIClient()
        self.director_client.force_authenticate(user=self.director)

        self.other_client = APIClient()
        self.other_client.force_authenticate(user=self.teacher_other)

    def test_assessment_creation_and_serializer_context(self):
        """Verify assessment creation and serializer returns academic context."""
        response = self.teacher_client.post('/api/v1/results/assessments/', {
            'academic_term': self.academic_term.id,
            'class_group': self.class_group.id,
            'subject': self.subject.id,
            'name': 'P.7 MTC Mid-Term Exam',
            'assessment_type': 'mot',
            'max_marks': 100,
            'weight': 1.0,
        })
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        data = response.data
        self.assertEqual(data['name'], 'P.7 MTC Mid-Term Exam')
        self.assertEqual(data['academic_year'], 2026)
        self.assertEqual(data['term_name'], 'Term 1 2026')
        self.assertEqual(data['class_group_name'], 'P.7 East')
        self.assertEqual(data['student_count'], 2)

    def test_marks_entry_validation_and_zero_vs_null(self):
        """Verify score validation (0-max_marks) and explicit 0 vs null distinction."""
        assessment = Assessment.objects.create(
            school=self.school,
            academic_term=self.academic_term,
            class_group=self.class_group,
            subject=self.subject,
            name="Mathematics End of Term",
            assessment_type="eot",
            max_marks=100,
        )

        # Invalid score > max_marks
        response = self.teacher_client.post(f'/api/v1/results/assessments/{assessment.id}/enter-marks/', {
            'marks': [{'student': str(self.student1.id), 'marks_obtained': 150.0}]
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        # Valid score = 0 (valid zero) for student1, and absent for student2
        response = self.teacher_client.post(f'/api/v1/results/assessments/{assessment.id}/enter-marks/', {
            'marks': [
                {'student': str(self.student1.id), 'marks_obtained': 0.0, 'is_absent': False},
                {'student': str(self.student2.id), 'marks_obtained': None, 'is_absent': True},
            ]
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)


        mark1 = AssessmentMark.objects.get(assessment=assessment, student=self.student1)
        self.assertEqual(mark1.marks_obtained, Decimal('0.00'))
        self.assertFalse(mark1.is_absent)

        mark2 = AssessmentMark.objects.get(assessment=assessment, student=self.student2)
        self.assertIsNone(mark2.marks_obtained)
        self.assertTrue(mark2.is_absent)

    def test_locked_assessment_rejects_modifications(self):
        """Verify locked assessments cannot be edited by teachers."""
        assessment = Assessment.objects.create(
            school=self.school,
            academic_term=self.academic_term,
            class_group=self.class_group,
            subject=self.subject,
            name="Locked Assessment",
            assessment_type="eot",
            max_marks=100,
            is_locked=True,
            status="submitted",
        )

        response = self.teacher_client.post(f'/api/v1/results/assessments/{assessment.id}/enter-marks/', {
            'marks': [{'student': str(self.student1.id), 'marks_obtained': 85.0}]
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


    def test_director_approval_lifecycle_approve_and_reject(self):
        """Verify Director approve and reject workflow."""
        assessment = Assessment.objects.create(
            school=self.school,
            academic_term=self.academic_term,
            class_group=self.class_group,
            subject=self.subject,
            name="Assessment For Approval",
            assessment_type="eot",
            max_marks=100,
            is_locked=True,
            status="submitted",
        )

        # Teacher cannot approve
        res_teacher = self.teacher_client.post(f'/api/v1/results/assessments/{assessment.id}/approve/')
        self.assertEqual(res_teacher.status_code, status.HTTP_403_FORBIDDEN)

        # Director rejects with reason
        res_reject = self.director_client.post(f'/api/v1/results/assessments/{assessment.id}/reject/', {
            'reason': 'Scores for Mukasa John appear incorrect.'
        })
        self.assertEqual(res_reject.status_code, status.HTTP_200_OK)

        assessment.refresh_from_db()
        self.assertEqual(assessment.status, 'rejected')
        self.assertFalse(assessment.is_locked)
        self.assertEqual(assessment.rejection_reason, 'Scores for Mukasa John appear incorrect.')

        # Director approves
        res_approve = self.director_client.post(f'/api/v1/results/assessments/{assessment.id}/approve/')
        self.assertEqual(res_approve.status_code, status.HTTP_200_OK)

        assessment.refresh_from_db()
        self.assertEqual(assessment.status, 'approved')
        self.assertTrue(assessment.is_locked)

    def test_marks_csv_template_and_import(self):
        """Verify CSV template download and row-by-row import validation."""
        # Download CSV Template
        res_temp = self.teacher_client.get(f'/api/v1/results/marks-entry/csv-template/?class_group={self.class_group.id}')
        self.assertEqual(res_temp.status_code, status.HTTP_200_OK)
        self.assertEqual(res_temp['Content-Type'], 'text/csv')

        # CSV Content Upload Test
        csv_data = f"Student ID,Reg No,Student Name,Marks,Absent,Comment\n{self.student1.id},{self.student1.student_id},Irene Babirye,88.5,FALSE,Good work\n{self.student2.id},{self.student2.student_id},John Mukasa,,TRUE,Absent due to illness\n"
        file_obj = io.BytesIO(csv_data.encode('utf-8'))
        file_obj.name = 'marks.csv'

        res_import = self.teacher_client.post('/api/v1/results/marks-entry/csv-import/', {
            'csv_file': file_obj,
            'class_group': self.class_group.id,
            'subject': self.subject.id,
            'assessment_type': 'eot',
            'dry_run': 'false',
        }, format='multipart')

        self.assertEqual(res_import.status_code, status.HTTP_200_OK)

        # Check records created
        marks = AssessmentMark.objects.all()
        self.assertEqual(marks.count(), 2)

    def test_tenant_isolation(self):
        """Verify teacher from another school cannot access assessments or marks."""
        assessment = Assessment.objects.create(
            school=self.school,
            academic_term=self.academic_term,
            class_group=self.class_group,
            subject=self.subject,
            name="KMS Secret Assessment",
            assessment_type="eot",
            max_marks=100,
        )

        res = self.other_client.get(f'/api/v1/results/assessments/{assessment.id}/')
        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)
