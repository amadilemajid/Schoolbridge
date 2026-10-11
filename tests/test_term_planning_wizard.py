"""
Tests for Composite Term Planning Wizard View (US-E04).
Verifies atomic provisioning of AcademicTerm, FeeStructures, line items,
optional timetable cloning, and automatic FeeRecord generation upon activation.
"""
from django.test import TestCase
from rest_framework.test import APIClient
from rest_framework import status

from authentication.models import User
from schools.models import School, AcademicYear, AcademicTerm
from students.models import ClassGroup, Student
from payments.models import FeeStructure, FeeRecord
from timetable.models import TimetableVersion, TimetableSlot
from results.models import Subject


class TermPlanningWizardTests(TestCase):

    def setUp(self):
        self.client = APIClient()
        self.school = School.objects.create(
            name='Kingsway Academy Kampala',
            slug='kingsway-academy',
            district='Kampala',
            phone='0700112233',
            email='admin@kingsway.ug',
            school_type='primary'
        )
        self.director = User.objects.create_user(
            email='director@kingsway.ug',
            password='TestPassword123!',
            first_name='Director',
            last_name='Okello',
            role='director',
            school=self.school
        )
        self.teacher = User.objects.create_user(
            email='teacher@kingsway.ug',
            password='TestPassword123!',
            first_name='Teacher',
            last_name='Musa',
            role='teacher',
            school=self.school
        )
        self.year = AcademicYear.objects.create(school=self.school, year=2025, is_current=True)
        self.class_p1 = ClassGroup.objects.create(school=self.school, name='P.1 Red', level='P1')
        self.class_p2 = ClassGroup.objects.create(school=self.school, name='P.2 Green', level='P2')
        
        # Create active students
        self.s1 = Student.objects.create(
            school=self.school, first_name='Allan', last_name='Kato',
            date_of_birth='2017-04-10', gender='M', student_id='KW-2025-001',
            admission_date='2023-01-10', academic_year_admitted=2023,
            current_class=self.class_p1, is_active=True
        )
        self.s2 = Student.objects.create(
            school=self.school, first_name='Betty', last_name='Babirye',
            date_of_birth='2016-08-15', gender='F', student_id='KW-2025-002',
            admission_date='2023-01-10', academic_year_admitted=2023,
            current_class=self.class_p2, is_active=True
        )

    def test_term_wizard_creation_with_fee_structures(self):
        """Director can atomically provision term with fee structures."""
        self.client.force_authenticate(user=self.director)
        payload = {
            'academic_year_id': str(self.year.id),
            'term_number': 1,
            'name': 'Term 1 2025',
            'start_date': '2025-02-03',
            'end_date': '2025-05-02',
            'fee_deadline': '2025-03-07',
            'activate_immediately': False,
            'fee_structures': [
                {
                    'name': 'Lower Primary Tuition',
                    'class_group_ids': [str(self.class_p1.id), str(self.class_p2.id)],
                    'items': [
                        {'name': 'Tuition', 'amount': 350000, 'is_mandatory': True},
                        {'name': 'Development', 'amount': 50000, 'is_mandatory': True}
                    ]
                }
            ]
        }
        response = self.client.post('/api/v1/schools/term-planning-wizard/', payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        data = response.json()
        self.assertTrue(data['success'])
        self.assertEqual(data['fee_structures_created'], 2)
        self.assertFalse(data['is_active'])

        # Verify DB records
        term = AcademicTerm.objects.get(id=data['term_id'])
        self.assertEqual(term.name, 'Term 1 2025')
        self.assertEqual(term.fee_structures.count(), 2)

    def test_term_wizard_immediate_activation_generates_fee_records(self):
        """Immediate activation generates FeeRecord ledgers for all active students."""
        self.client.force_authenticate(user=self.director)
        payload = {
            'academic_year_id': str(self.year.id),
            'term_number': 2,
            'name': 'Term 2 2025',
            'start_date': '2025-05-26',
            'end_date': '2025-08-22',
            'fee_deadline': '2025-06-20',
            'activate_immediately': True,
            'fee_structures': [
                {
                    'name': 'P1-P2 Tuition',
                    'class_group_ids': [str(self.class_p1.id), str(self.class_p2.id)],
                    'items': [
                        {'name': 'Tuition', 'amount': 400000, 'is_mandatory': True}
                    ]
                }
            ]
        }
        response = self.client.post('/api/v1/schools/term-planning-wizard/', payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        data = response.json()
        self.assertTrue(data['is_active'])
        self.assertEqual(data['fee_records_generated'], 2)

        # Verify FeeRecords exist in DB
        term = AcademicTerm.objects.get(id=data['term_id'])
        fee_records = FeeRecord.objects.filter(academic_term=term)
        self.assertEqual(fee_records.count(), 2)
        for fr in fee_records:
            self.assertEqual(fr.total_amount, 400000)

    def test_term_wizard_clones_timetable(self):
        """Clones timetable version and slots from previous term if specified."""
        prev_term = AcademicTerm.objects.create(
            school=self.school, academic_year=self.year, term_number=1,
            name='Term 1 Previous', start_date='2025-02-03', end_date='2025-05-02',
            fee_deadline='2025-03-07'
        )
        v1 = TimetableVersion.objects.create(
            school=self.school, academic_term=prev_term, class_group=self.class_p1,
            version_number=1, is_active=True, effective_from='2025-02-03'
        )
        sub = Subject.objects.create(school=self.school, name='English', code='ENG')
        TimetableSlot.objects.create(
            timetable_version=v1, school=self.school, subject=sub,
            day_of_week=0, period_number=1, start_time='08:00', end_time='09:00', room='1A'
        )

        self.client.force_authenticate(user=self.director)
        payload = {
            'academic_year_id': str(self.year.id),
            'term_number': 3,
            'name': 'Term 3 2025',
            'start_date': '2025-09-15',
            'end_date': '2025-12-05',
            'fee_deadline': '2025-10-10',
            'clone_timetable_from_term_id': str(prev_term.id),
        }
        response = self.client.post('/api/v1/schools/term-planning-wizard/', payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        data = response.json()
        self.assertEqual(data['timetable_slots_cloned'], 1)

    def test_term_wizard_permissions(self):
        """Teacher cannot execute term planning wizard."""
        self.client.force_authenticate(user=self.teacher)
        payload = {
            'academic_year_id': str(self.year.id),
            'term_number': 1,
            'name': 'Unauthorized Term',
            'start_date': '2025-02-03',
            'end_date': '2025-05-02',
            'fee_deadline': '2025-03-07',
        }
        response = self.client.post('/api/v1/schools/term-planning-wizard/', payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
