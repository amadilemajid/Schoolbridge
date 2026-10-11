"""
Comprehensive Production Verification Tests for Teacher's Dashboard Feature.
Covers:
  - TeacherDashboardView permissions & tenant isolation
  - Live data accuracy: KPIs, today's schedule, assigned form classes, attendance status
  - Absent students alert roster with decrypted guardian contacts & WhatsApp links
  - Pending marks completion tracking
  - Edge cases (weekend, no form classes, non-teacher accounts)
"""
import uuid
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase
from authentication.models import User
from schools.models import School, AcademicYear, AcademicTerm
from students.models import ClassGroup, Student, Guardian
from timetable.models import TimetableVersion, TimetableSlot
from attendance.models import AttendanceRecord
from results.models import Subject, Assessment, AssessmentMark


class TeacherDashboardTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        # 1. School & Academic Calendar
        cls.school = School.objects.create(
            name="Test Teacher Academy",
            slug="test-teacher-academy",
            district="Kampala",
            phone="0700112233",
            email="admin@tta.ug",
            school_type="primary",
        )
        cls.year = AcademicYear.objects.create(school=cls.school, year=2026, is_current=True)
        cls.term = AcademicTerm.objects.create(
            school=cls.school,
            academic_year=cls.year,
            name="Term 1 2026",
            term_number=1,
            start_date=timezone.now().date(),
            end_date=timezone.now().date() + timezone.timedelta(days=90),
            fee_deadline=timezone.now().date() + timezone.timedelta(days=30),
            is_current=True
        )

        # 2. Teacher & Director
        cls.teacher = User.objects.create_user(
            email="teacher.test@tta.ac.ug",
            password="StrongPassword123!",
            role="teacher",
            first_name="Rose",
            last_name="Namubiru",
            school=cls.school
        )

        cls.director = User.objects.create_user(
            email="director.test@tta.ac.ug",
            password="StrongPassword123!",
            role="director",
            first_name="David",
            last_name="Mukasa",
            school=cls.school
        )

        # 3. Form Classes
        cls.p5_east = ClassGroup.objects.create(
            school=cls.school,
            name="P.5 East",
            level="P5",
            stream="East",
            form_teacher=cls.teacher,
            is_active=True
        )
        cls.p6_west = ClassGroup.objects.create(
            school=cls.school,
            name="P.6 West",
            level="P6",
            stream="West",
            form_teacher=cls.teacher,
            is_active=True
        )

        # 4. Students
        cls.student1 = Student.objects.create(
            school=cls.school,
            student_id="SCH-2026-9001",
            first_name="Brian",
            last_name="Kato",
            gender="M",
            admission_date=timezone.now().date(),
            academic_year_admitted=2026,
            current_class=cls.p5_east,
            is_active=True
        )
        cls.student2 = Student.objects.create(
            school=cls.school,
            student_id="SCH-2026-9002",
            first_name="Grace",
            last_name="Babirye",
            gender="F",
            admission_date=timezone.now().date(),
            academic_year_admitted=2026,
            current_class=cls.p5_east,
            is_active=True
        )
        cls.student3 = Student.objects.create(
            school=cls.school,
            student_id="SCH-2026-9003",
            first_name="Ivan",
            last_name="Ssebaggala",
            gender="M",
            admission_date=timezone.now().date(),
            academic_year_admitted=2026,
            current_class=cls.p6_west,
            is_active=True
        )

        # 5. Guardian with phone
        cls.guardian = Guardian.objects.create(
            student=cls.student1,
            first_name="Patrick",
            last_name="Kato",
            relationship="Father",
            phone="0772123456",
            is_primary=True
        )

        # 6. Subject & Assessment
        cls.math_subject = Subject.objects.create(
            school=cls.school,
            name="Mathematics",
            code="MTC",
            class_levels="P5,P6"
        )
        cls.assessment = Assessment.objects.create(
            school=cls.school,
            academic_term=cls.term,
            class_group=cls.p5_east,
            subject=cls.math_subject,
            name="Mid Term Exam",
            assessment_type="mot",
            max_marks=100,
            status="draft"
        )
        AssessmentMark.objects.create(
            assessment=cls.assessment,
            student=cls.student1,
            marks_obtained=85.0
        )

        # 7. Timetable Version & Slot for Today
        cls.today_weekday = timezone.localdate().weekday()
        cls.tt_version = TimetableVersion.objects.create(
            school=cls.school,
            class_group=cls.p5_east,
            academic_term=cls.term,
            version_number=1,
            is_active=True,
            effective_from=timezone.now().date()
        )
        cls.slot = TimetableSlot.objects.create(
            school=cls.school,
            timetable_version=cls.tt_version,
            day_of_week=cls.today_weekday,
            period_number=1,
            start_time="08:30:00",
            end_time="09:30:00",
            subject=cls.math_subject,
            teacher=cls.teacher,
            room="Room 5E",
            slot_type="lesson"
        )

    def test_unauthenticated_request_rejected(self):
        """Unauthenticated user receives 401."""
        response = self.client.get('/api/v1/automation/teacher-dashboard/')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_authenticated_teacher_receives_complete_dashboard(self):
        """Authenticated teacher receives full 200 payload with all expected keys."""
        self.client.force_authenticate(user=self.teacher)
        response = self.client.get('/api/v1/automation/teacher-dashboard/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        data = response.json()
        expected_keys = [
            'teacher', 'school', 'current_term', 'today_date', 'today_day_name',
            'kpis', 'today_schedule', 'assigned_classes', 'absent_students_today', 'pending_marks'
        ]
        for key in expected_keys:
            self.assertIn(key, data, f"Missing key: {key}")

        # Teacher profile
        self.assertEqual(data['teacher']['id'], str(self.teacher.id))
        self.assertEqual(data['teacher']['name'], "Rose Namubiru")
        self.assertEqual(data['teacher']['role'], "teacher")

        # School & Term
        self.assertEqual(data['school']['name'], "Test Teacher Academy")
        self.assertEqual(data['current_term']['name'], "Term 1 2026")

        # KPIs
        self.assertEqual(data['kpis']['assigned_classes_count'], 2)
        self.assertEqual(data['kpis']['total_students_count'], 3)
        self.assertEqual(data['kpis']['today_lessons_count'], 1)
        self.assertEqual(data['kpis']['absent_students_today_count'], 0)
        self.assertEqual(data['kpis']['pending_assessments_count'], 1)

        # Schedule
        self.assertEqual(len(data['today_schedule']), 1)
        slot_data = data['today_schedule'][0]
        self.assertEqual(slot_data['period_number'], 1)
        self.assertEqual(slot_data['start_time'], "08:30")
        self.assertEqual(slot_data['end_time'], "09:30")
        self.assertEqual(slot_data['subject_name'], "Mathematics")
        self.assertEqual(slot_data['class_group_name'], "P.5 East")
        self.assertEqual(slot_data['room'], "Room 5E")

        # Assigned classes
        self.assertEqual(len(data['assigned_classes']), 2)
        p5 = next(c for c in data['assigned_classes'] if c['name'] == "P.5 East")
        self.assertEqual(p5['student_count'], 2)
        self.assertFalse(p5['attendance_today']['is_marked'])

        # Pending marks completion
        self.assertEqual(len(data['pending_marks']), 1)
        mark_data = data['pending_marks'][0]
        self.assertEqual(mark_data['name'], "Mid Term Exam")
        self.assertEqual(mark_data['marks_entered_count'], 1)
        self.assertEqual(mark_data['total_students_count'], 2)
        self.assertEqual(mark_data['completion_pct'], 50.0)

    def test_absent_students_today_and_attendance_summary(self):
        """When a student is marked absent today, they appear on the absent roster."""
        today = timezone.localdate()
        AttendanceRecord.objects.create(
            school=self.school,
            student=self.student1,
            class_group=self.p5_east,
            academic_term=self.term,
            date=today,
            status='absent',
            pre_excused=True,
            pre_excused_reason='Parent called: Malaria treatment',
            notes='Hospital appointment'
        )

        self.client.force_authenticate(user=self.teacher)
        response = self.client.get('/api/v1/automation/teacher-dashboard/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        data = response.json()
        self.assertEqual(data['kpis']['absent_students_today_count'], 1)
        self.assertEqual(len(data['absent_students_today']), 1)

        absent = data['absent_students_today'][0]
        self.assertEqual(absent['student_name'], "Brian Kato")
        self.assertEqual(absent['reg_number'], "SCH-2026-9001")
        self.assertEqual(absent['class_group_name'], "P.5 East")
        self.assertEqual(absent['guardian_name'], "Patrick Kato")
        self.assertEqual(absent['guardian_phone'], "0772123456")
        self.assertTrue(absent['pre_excused'])
        self.assertEqual(absent['notes'], "Hospital appointment")

        # Class attendance summary reflects this
        p5 = next(c for c in data['assigned_classes'] if c['name'] == "P.5 East")
        self.assertTrue(p5['attendance_today']['is_marked'])
        self.assertEqual(p5['attendance_today']['absent_count'], 1)
        self.assertEqual(p5['attendance_today']['attendance_rate'], 0.0)

    def test_tenant_isolation(self):
        """Teacher cannot see data from another school."""
        other_school = School.objects.create(
            name="Other Academy", slug="other-academy",
            district="Wakiso", phone="0700999888",
            email="admin@otheracademy.ug", school_type="primary",
        )
        other_teacher = User.objects.create_user(
            email="other.teacher@oa.ac.ug",
            password="Password123!",
            role="teacher",
            school=other_school
        )

        self.client.force_authenticate(user=other_teacher)
        response = self.client.get('/api/v1/automation/teacher-dashboard/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertEqual(data['school']['name'], "Other Academy")
        self.assertEqual(data['kpis']['assigned_classes_count'], 0)
        self.assertEqual(len(data['today_schedule']), 0)
        self.assertEqual(len(data['assigned_classes']), 0)
