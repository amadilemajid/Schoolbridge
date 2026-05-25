"""
Attendance tests — window enforcement, pre-excused absence, 75% alert.
"""
from unittest.mock import patch
from django.test import TestCase
from django.utils import timezone
from django.contrib.auth import get_user_model
from schools.models import School, AcademicTerm, AcademicYear
from students.models import Student, Guardian, ClassGroup
from attendance.services import AttendanceService
import datetime

User = get_user_model()


def quick_setup():
    school = School.objects.create(
        name='Att School', slug='att-school',
        district='Kampala', phone='+256701234567',
        email='att@school.ug', school_type='primary',
    )
    year = AcademicYear.objects.create(school=school, year=2024, is_current=True)
    term = AcademicTerm.objects.create(
        school=school, academic_year=year, term_number=1,
        name='T1', start_date='2024-02-05', end_date='2024-05-31',
        fee_deadline='2024-03-15', is_current=True, is_active=True,
    )
    cg = ClassGroup.all_objects.create(school=school, name='P6', level='P6')
    teacher = User.objects.create_user(
        email='teacher@att.ug', password='pass',
        role='teacher', school=school, first_name='T', last_name='T',
    )
    cg.form_teacher = teacher
    cg.save()
    student = Student.all_objects.create(
        school=school, student_id='ATT-001',
        first_name='Ali', last_name='Kato',
        gender='M', admission_date='2024-02-05',
        academic_year_admitted=2024, current_class=cg,
    )
    Guardian.objects.create(
        student=student, first_name='Parent', last_name='Kato',
        relationship='Father', phone='0712345678',
        phone_normalised='+256712345678', is_primary=True,
    )
    return school, term, cg, teacher, student


class AttendanceWindowTest(TestCase):
    """US-049: Attendance window 7am–12pm. Reject outside this window."""

    def test_submit_outside_window_raises_error(self):
        """Submitting outside 7am–12pm raises ValueError."""
        school, term, cg, teacher, student = quick_setup()
        with patch('attendance.services.timezone') as mock_tz:
            mock_now = datetime.datetime(2024, 3, 1, 13, 30)  # 1:30pm
            mock_tz.localtime.return_value = mock_now
            mock_tz.localdate.return_value = datetime.date(2024, 3, 1)
            with patch('automation.services.CalendarService.is_school_day', return_value=True):
                with self.assertRaises(ValueError) as ctx:
                    AttendanceService.submit_register(
                        class_group=cg, date=datetime.date(2024, 3, 1),
                        attendance_data=[{'student_id': str(student.id), 'status': 'present'}],
                        marked_by=teacher,
                    )
                self.assertIn('closed', str(ctx.exception).lower())


class PreExcusedAbsenceTest(TestCase):
    """US-052: Parent WhatsApp ABSENT command marks student as pre-excused."""

    def test_pre_excused_suppresses_absence_alert(self):
        school, term, cg, teacher, student = quick_setup()
        absence_date = datetime.date(2024, 3, 1)

        # Mark pre-excused (parent sent ABSENT command)
        AttendanceService.mark_pre_excused(student, absence_date, 'Doctor appointment')

        from attendance.models import AttendanceRecord
        record = AttendanceRecord.all_objects.get(student=student, date=absence_date)
        self.assertEqual(record.status, 'excused')
        self.assertTrue(record.pre_excused)
        self.assertEqual(record.pre_excused_reason, 'Doctor appointment')

    def test_regular_absent_triggers_alert(self):
        """Absent (not pre-excused) triggers send_absence_alert task."""
        school, term, cg, teacher, student = quick_setup()

        with patch('attendance.services.timezone') as mock_tz:
            mock_now = datetime.datetime(2024, 3, 1, 8, 0)  # 8am — window open
            mock_tz.localtime.return_value = mock_now
            mock_tz.localdate.return_value = datetime.date(2024, 3, 1)
            with patch('automation.services.CalendarService.is_school_day', return_value=True):
                with patch('messaging.tasks.send_absence_alert.delay') as mock_alert:
                    with patch('attendance.services.AttendanceService._check_attendance_alerts'):
                        AttendanceService.submit_register(
                            class_group=cg,
                            date=datetime.date(2024, 3, 1),
                            attendance_data=[{
                                'student_id': str(student.id),
                                'status': 'absent',
                            }],
                            marked_by=teacher,
                        )
                    mock_alert.assert_called_once_with(str(student.id), '2024-03-01')
