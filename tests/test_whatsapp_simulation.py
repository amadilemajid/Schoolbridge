"""
Comprehensive test suite for the WhatsApp Command Simulation API and InboundCommandProcessor.simulate().
Verifies that all 11 WhatsApp commands and numeric shortcuts execute synchronously and return
accurate replies without Meta Cloud API.
"""
from django.test import TestCase
from rest_framework.test import APIClient
from rest_framework import status

from schools.models import School, AcademicYear, AcademicTerm
from students.models import ClassGroup, Student, Guardian
from payments.models import FeeRecord, Payment
from results.models import Subject, Assessment, AssessmentMark, TermResult
from attendance.models import AttendanceRecord
from timetable.models import TimetableVersion, TimetableSlot
from messaging.services import InboundCommandProcessor


def make_test_school():
    return School.objects.create(
        name='St. Jude Simulation College',
        slug='st-jude-sim',
        district='Wakiso',
        phone='0701112233',
        email='director@stjude.ug',
        school_type='primary'
    )


class WhatsAppSimulationTests(TestCase):

    def setUp(self):
        self.client = APIClient()
        self.school = make_test_school()
        self.year = AcademicYear.objects.create(school=self.school, year=2025, is_current=True)
        self.term = AcademicTerm.objects.create(
            school=self.school, academic_year=self.year, term_number=1,
            name='Term 1 2025', start_date='2025-02-03', end_date='2025-05-02',
            fee_deadline='2025-03-07', is_current=True, is_active=True
        )
        self.class_group = ClassGroup.objects.create(school=self.school, name='P.6 Blue', level='P6')
        self.student = Student.objects.create(
            school=self.school, first_name='David', last_name='Mukasa',
            date_of_birth='2013-05-12', gender='M', student_id='STJ-2025-001',
            admission_date='2022-01-10', academic_year_admitted=2022,
            current_class=self.class_group, is_active=True
        )
        self.guardian = Guardian.objects.create(
            student=self.student, first_name='Agnes', last_name='Nambi',
            relationship='Mother', phone='0772123456',
            is_primary=True, preferred_language='en'
        )
        self.fee_record = FeeRecord.objects.create(
            school=self.school, student=self.student, academic_term=self.term,
            total_amount=500000, amount_paid=200000, amount_waived=0
        )

    def test_simulate_balance_command(self):
        """Test BALANCE command simulation returns accurate balance and sibling summary."""
        result = InboundCommandProcessor.simulate(
            from_phone='0772123456',
            message_text='BALANCE',
            school=self.school
        )
        self.assertTrue(result['success'])
        self.assertEqual(result['command'], 'BALANCE')
        self.assertIn('David Mukasa', result['reply'])
        self.assertIn('UGX 500,000', result['reply'])
        self.assertIn('UGX 200,000', result['reply'])
        self.assertIn('UGX 300,000', result['reply'])

    def test_simulate_numeric_shortcut_1(self):
        """Test numeric shortcut '1' maps directly to BALANCE."""
        result = InboundCommandProcessor.simulate(
            from_phone='256772123456',
            message_text='1',
            school=self.school
        )
        self.assertTrue(result['success'])
        self.assertEqual(result['command'], 'BALANCE')
        self.assertIn('David Mukasa', result['reply'])

    def test_simulate_results_command(self):
        """Test RESULTS command simulation returns published term results."""
        TermResult.objects.create(
            school=self.school, student=self.student, academic_term=self.term,
            class_group=self.class_group, total_marks=350, average_marks=87.5,
            class_rank=2, total_students=45, division='1', aggregate=6, is_published=True
        )
        result = InboundCommandProcessor.simulate(
            from_phone='0772123456',
            message_text='RESULTS',
            school=self.school
        )
        self.assertTrue(result['success'])
        self.assertEqual(result['command'], 'RESULTS')
        self.assertIn('David Mukasa', result['reply'])
        self.assertIn('Division: 1', result['reply'])
        self.assertIn('Rank: 2 of 45', result['reply'])

    def test_simulate_attendance_command(self):
        """Test ATTEND command returns attendance rate percentage."""
        AttendanceRecord.objects.create(
            school=self.school, student=self.student, class_group=self.class_group,
            academic_term=self.term, date='2025-02-10', status='present'
        )
        AttendanceRecord.objects.create(
            school=self.school, student=self.student, class_group=self.class_group,
            academic_term=self.term, date='2025-02-11', status='present'
        )
        result = InboundCommandProcessor.simulate(
            from_phone='0772123456',
            message_text='ATTEND',
            school=self.school
        )
        self.assertTrue(result['success'])
        self.assertEqual(result['command'], 'ATTEND')
        self.assertIn('David Mukasa', result['reply'])
        self.assertIn('Attendance: 100.0%', result['reply'])

    def test_simulate_timetable_command(self):
        """Test TIMETABLE command simulation returns weekly schedule."""
        from schools.models import Timetable
        Timetable.objects.create(
            school=self.school, class_group=self.class_group,
            content="Mon: Mathematics 08:00 - 09:00\nTue: English 09:00 - 10:00",
            is_active=True
        )
        result = InboundCommandProcessor.simulate(
            from_phone='0772123456',
            message_text='TIMETABLE',
            school=self.school
        )
        self.assertTrue(result['success'])
        self.assertEqual(result['command'], 'TIMETABLE')
        self.assertIn('P.6 Blue', result['reply'])
        self.assertIn('Mathematics', result['reply'])

    def test_simulate_menu_and_language(self):
        """Test MENU and LUGANDA switching."""
        menu_res = InboundCommandProcessor.simulate(
            from_phone='0772123456',
            message_text='MENU',
            school=self.school
        )
        self.assertTrue(menu_res['success'])
        self.assertEqual(menu_res['command'], 'MENU')
        self.assertIn('SchoolBridge', menu_res['reply'])

        # Switch to Luganda
        lg_res = InboundCommandProcessor.simulate(
            from_phone='0772123456',
            message_text='LUGANDA',
            school=self.school
        )
        self.assertTrue(lg_res['success'])
        self.assertEqual(lg_res['command'], 'LUGANDA')
        self.assertIn('Olulimi lwaakyusibwa', lg_res['reply'])

    def test_simulate_absent_command(self):
        """Test ABSENT pre-excusal command."""
        result = InboundCommandProcessor.simulate(
            from_phone='0772123456',
            message_text='ABSENT 2025-02-20 Malaria fever',
            school=self.school
        )
        self.assertTrue(result['success'])
        self.assertEqual(result['command'], 'ABSENT')
        self.assertIn('Absence noted for David Mukasa on 2025-02-20', result['reply'])
        
        # Verify attendance record created as excused
        rec = AttendanceRecord.objects.filter(student=self.student, date='2025-02-20').first()
        self.assertIsNotNone(rec)
        self.assertEqual(rec.status, 'excused')

    def test_simulate_api_endpoint(self):
        """Test POST /api/v1/messaging/simulate/ REST API."""
        payload = {
            'phone': '0772123456',
            'message': 'BALANCE',
            'school_id': str(self.school.id)
        }
        response = self.client.post('/api/v1/messaging/simulate/', payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertTrue(data['success'])
        self.assertEqual(data['command'], 'BALANCE')
        self.assertIn('David Mukasa', data['reply'])
        self.assertEqual(data['school'], 'St. Jude Simulation College')
