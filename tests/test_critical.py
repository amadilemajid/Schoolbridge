"""
Critical production tests — Uganda-specific requirements.
US-063: CalendarService.is_school_day() — gates every automated message.
US-064: CalendarService.is_messaging_paused() — Director pause.
US-043/044/045: UNEB grading regression — PLE/UCE/UACE correctness.
US-032: Fee reminder suppressed when balance is zero.
"""
import datetime
from decimal import Decimal
from unittest.mock import patch
from django.test import TestCase
from django.utils import timezone
from django.contrib.auth import get_user_model

from schools.models import School, AcademicYear, AcademicTerm, HolidayPeriod
from schools.models import MessagingPause
from students.models import Student, Guardian, ClassGroup
from payments.models import FeeRecord
from automation.services import CalendarService

User = get_user_model()


def make_school():
    return School.objects.create(
        name='Critical Test School',
        slug='critical-test-school',
        district='Kampala', phone='+256701234567',
        email='critical@school.ug', school_type='combined',
    )


def make_term(school, start='2024-02-05', end='2024-05-31', active=True):
    year, _ = AcademicYear.objects.get_or_create(
        school=school, year=2024, defaults={'is_current': True}
    )
    return AcademicTerm.objects.create(
        school=school, academic_year=year, term_number=1,
        name='Term 1 2024', start_date=start, end_date=end,
        fee_deadline='2024-03-15', is_current=active, is_active=active,
    )


# ---------------------------------------------------------------------------
# US-063: CalendarService.is_school_day()
# Every automated message (fee reminders, absence alerts) calls this.
# If it returns wrong results, messages fire on holidays or weekends.
# ---------------------------------------------------------------------------

class CalendarServiceSchoolDayTest(TestCase):

    def setUp(self):
        self.school = make_school()
        self.term = make_term(self.school)

    def test_weekday_inside_term_is_school_day(self):
        """Monday inside an active term is a school day."""
        monday = datetime.date(2024, 3, 4)   # confirmed Monday
        self.assertTrue(CalendarService.is_school_day(self.school, monday))

    def test_saturday_is_not_school_day(self):
        """Saturday must never trigger automated messages."""
        saturday = datetime.date(2024, 3, 2)
        self.assertFalse(CalendarService.is_school_day(self.school, saturday))

    def test_sunday_is_not_school_day(self):
        """Sunday must never trigger automated messages."""
        sunday = datetime.date(2024, 3, 3)
        self.assertFalse(CalendarService.is_school_day(self.school, sunday))

    def test_date_outside_term_is_not_school_day(self):
        """Date before term starts is not a school day even if weekday."""
        before_term = datetime.date(2024, 1, 15)  # Monday, before Feb 5
        self.assertFalse(CalendarService.is_school_day(self.school, before_term))

    def test_date_after_term_ends_is_not_school_day(self):
        """Date after term ends is not a school day."""
        after_term = datetime.date(2024, 6, 10)  # after May 31
        self.assertFalse(CalendarService.is_school_day(self.school, after_term))

    def test_holiday_period_suppresses_school_day(self):
        """A weekday inside a HolidayPeriod is not a school day — US-063."""
        holiday_monday = datetime.date(2024, 3, 4)
        HolidayPeriod.objects.create(
            school=self.school,
            name='Mid-term Break',
            start_date=datetime.date(2024, 3, 4),
            end_date=datetime.date(2024, 3, 8),
        )
        self.assertFalse(CalendarService.is_school_day(self.school, holiday_monday))

    def test_no_active_term_means_not_school_day(self):
        """Without any active term, no day is a school day."""
        school2 = School.objects.create(
            name='No Term School', slug='no-term-school',
            district='Kampala', phone='+256701111111',
            email='noterm@school.ug', school_type='primary',
        )
        self.assertFalse(CalendarService.is_school_day(school2, datetime.date(2024, 3, 4)))


# ---------------------------------------------------------------------------
# US-064: CalendarService.is_messaging_paused() + record_dropped_task()
# Director can pause all automated reminders. Dropped tasks must be counted.
# ---------------------------------------------------------------------------

class MessagingPauseTest(TestCase):

    def setUp(self):
        self.school = make_school()
        self.director = User.objects.create_user(
            email='director@critical.ug', password='pass123',
            role='director', school=self.school,
            first_name='Dir', last_name='Test',
        )

    def test_no_pause_means_not_paused(self):
        """No MessagingPause record means messaging is active."""
        self.assertFalse(
            CalendarService.is_messaging_paused(self.school, datetime.date(2024, 3, 4))
        )

    def test_active_pause_covering_date_is_paused(self):
        """Active pause covering today means messaging is paused — US-064."""
        MessagingPause.objects.create(
            school=self.school,
            start_date=datetime.date(2024, 3, 1),
            end_date=datetime.date(2024, 3, 31),
            reason='Examination period',
            is_active=True,
            created_by=self.director,
        )
        self.assertTrue(
            CalendarService.is_messaging_paused(self.school, datetime.date(2024, 3, 15))
        )

    def test_expired_pause_is_not_paused(self):
        """Pause whose end_date has passed does not suppress messaging."""
        MessagingPause.objects.create(
            school=self.school,
            start_date=datetime.date(2024, 1, 1),
            end_date=datetime.date(2024, 1, 31),
            reason='Old pause',
            is_active=True,
            created_by=self.director,
        )
        self.assertFalse(
            CalendarService.is_messaging_paused(self.school, datetime.date(2024, 3, 15))
        )

    def test_inactive_pause_is_not_paused(self):
        """Pause with is_active=False does not suppress messaging."""
        MessagingPause.objects.create(
            school=self.school,
            start_date=datetime.date(2024, 3, 1),
            end_date=datetime.date(2024, 3, 31),
            reason='Ended early',
            is_active=False,
            created_by=self.director,
        )
        self.assertFalse(
            CalendarService.is_messaging_paused(self.school, datetime.date(2024, 3, 15))
        )

    def test_record_dropped_task_increments_count(self):
        """Each dropped task is counted and recorded in the pause summary."""
        pause = MessagingPause.objects.create(
            school=self.school,
            start_date=datetime.date(2024, 3, 1),
            end_date=datetime.date(2024, 3, 31),
            reason='Exams',
            is_active=True,
            created_by=self.director,
        )
        CalendarService.record_dropped_task(self.school, 'fee_reminder', datetime.date(2024, 3, 15))
        CalendarService.record_dropped_task(self.school, 'absence_alert', datetime.date(2024, 3, 15))

        pause.refresh_from_db()
        self.assertEqual(pause.dropped_tasks_count, 2)
        task_types = [t['task_type'] for t in pause.dropped_tasks_summary]
        self.assertIn('fee_reminder', task_types)
        self.assertIn('absence_alert', task_types)


# ---------------------------------------------------------------------------
# US-043/044/045: UNEB grading regression tests
# These must never silently break — wrong grades affect students legally.
# ---------------------------------------------------------------------------

class UNEBGradingRegressionTest(TestCase):
    """Regression suite — verifies all UNEB 2024 grade tables are correct."""

    def test_ple_subject_grade_boundaries(self):
        """PLE: 80+=1, 60-79=2, 40-59=3, 0-39=4."""
        from results.grading import get_ple_subject_grade
        self.assertEqual(get_ple_subject_grade(100), 1)
        self.assertEqual(get_ple_subject_grade(80), 1)
        self.assertEqual(get_ple_subject_grade(79), 2)
        self.assertEqual(get_ple_subject_grade(60), 2)
        self.assertEqual(get_ple_subject_grade(59), 3)
        self.assertEqual(get_ple_subject_grade(40), 3)
        self.assertEqual(get_ple_subject_grade(39), 4)
        self.assertEqual(get_ple_subject_grade(0), 4)

    def test_ple_division_table(self):
        """PLE divisions: I=4-12, II=13-23, III=24-29, IV=30-34, U=35+."""
        from results.grading import get_ple_division
        # Division I: four Distinctions = agg 4
        div, agg = get_ple_division([1, 1, 1, 1])
        self.assertEqual(div, 'I')
        self.assertEqual(agg, 4)
        # Division I: agg 12 (boundary)
        div, agg = get_ple_division([3, 3, 3, 3])
        self.assertEqual(div, 'I')
        # Division II: agg 13 (boundary)
        div, agg = get_ple_division([4, 3, 3, 3])
        self.assertEqual(div, 'II')
        # U: empty list
        div, agg = get_ple_division([])
        self.assertEqual(div, 'U')

    def test_uce_grade_boundaries(self):
        """UCE: D1=75+, D2=70-74, C3=65-69, C4=60-64, C5=55-59,
           C6=50-54, P7=45-49, P8=40-44, F9=0-39."""
        from results.grading import get_uce_grade
        cases = [
            (75, 'D1', 1), (74, 'D2', 2), (70, 'D2', 2),
            (65, 'C3', 3), (60, 'C4', 4), (55, 'C5', 5),
            (50, 'C6', 6), (45, 'P7', 7), (40, 'P8', 8),
            (39, 'F9', 9), (0, 'F9', 9),
        ]
        for marks, expected_grade, expected_pts in cases:
            grade, pts = get_uce_grade(marks)
            self.assertEqual(grade, expected_grade, f'UCE {marks} marks: expected {expected_grade} got {grade}')
            self.assertEqual(pts, expected_pts)

    def test_uce_division_table(self):
        """UCE divisions: I=8-32, II=33-47, III=48-56, IV=57-64, U=65+."""
        from results.grading import get_uce_division
        # Div I: 8 x D1(1) = agg 8
        div, agg = get_uce_division([1] * 8)
        self.assertEqual(div, 'I')
        # Div I: agg 32 (boundary)
        div, agg = get_uce_division([4, 4, 4, 4, 4, 4, 4, 4])
        self.assertEqual(div, 'I')
        # Div II: agg 33
        div, agg = get_uce_division([4, 4, 4, 4, 4, 4, 4, 5])
        self.assertEqual(div, 'II')
        # U: agg > 64
        div, agg = get_uce_division([9] * 8)
        self.assertEqual(div, 'U')

    def test_uace_grade_boundaries(self):
        """UACE: A=80+, B=70-79, C=60-69, D=50-59, E=40-49, O=35-39, F=0-34."""
        from results.grading import get_uace_grade
        cases = [
            (80, 'A', 6), (79, 'B', 5), (70, 'B', 5),
            (69, 'C', 4), (60, 'C', 4), (59, 'D', 3),
            (50, 'D', 3), (49, 'E', 2), (40, 'E', 2),
            (39, 'O', 1), (35, 'O', 1), (34, 'F', 0), (0, 'F', 0),
        ]
        for marks, expected_grade, expected_pts in cases:
            grade, pts = get_uace_grade(marks)
            self.assertEqual(grade, expected_grade, f'UACE {marks}: expected {expected_grade} got {grade}')

    def test_uace_aggregate_best_3_principals_only(self):
        """UACE aggregate uses best 3 principals; O and F don't count."""
        from results.grading import get_uace_aggregate
        # 3 x A = 18
        self.assertEqual(get_uace_aggregate([('A', 6), ('A', 6), ('A', 6)]), 18)
        # F(0) excluded
        self.assertEqual(get_uace_aggregate([('A', 6), ('A', 6), ('F', 0)]), 12)
        # O(1) excluded from principal aggregate
        self.assertEqual(get_uace_aggregate([('A', 6), ('O', 1), ('O', 1)]), 6)
        # Only best 3 counted even if more subjects
        self.assertEqual(get_uace_aggregate([('A', 6), ('A', 6), ('A', 6), ('A', 6)]), 18)


# ---------------------------------------------------------------------------
# US-032: Fee reminder suppression when balance is zero
# Critical: we must never spam fully-paid parents with fee reminders.
# ---------------------------------------------------------------------------

class FeeReminderSuppressionTest(TestCase):

    def setUp(self):
        self.school = make_school()
        self.term = make_term(self.school)
        cg = ClassGroup.all_objects.create(school=self.school, name='P7', level='P7')
        self.student = Student.all_objects.create(
            school=self.school, student_id='FR-001',
            first_name='Grace', last_name='Atim',
            gender='F', admission_date='2024-02-05',
            academic_year_admitted=2024, current_class=cg,
        )
        Guardian.objects.create(
            student=self.student, first_name='Moses', last_name='Atim',
            relationship='Father', phone='0701111111',
            phone_normalised='+256701111111', is_primary=True,
        )

    def test_fee_reminder_suppressed_when_fully_paid(self):
        """US-032: send_fee_reminder exits early if balance is zero."""
        fee_record = FeeRecord.all_objects.create(
            school=self.school, student=self.student,
            academic_term=self.term,
            total_amount=Decimal('300000'),
            amount_paid=Decimal('300000'),  # fully paid
        )
        self.assertTrue(fee_record.is_fully_paid)

        # The task should return without calling WhatsApp
        with patch('messaging.services.WhatsAppService.send_text_message') as mock_send:
            from messaging.tasks import send_fee_reminder
            # Run task synchronously (bypass Celery)
            send_fee_reminder.apply(args=[str(fee_record.id), 7])
            mock_send.assert_not_called()

    def test_fee_reminder_suppressed_on_holiday(self):
        """US-063: Fee reminder suppressed on a holiday — no message sent."""
        fee_record = FeeRecord.all_objects.create(
            school=self.school, student=self.student,
            academic_term=self.term,
            total_amount=Decimal('300000'),
            amount_paid=Decimal('0'),
        )
        # Mark today as a holiday
        with patch('automation.services.CalendarService.is_school_day', return_value=False):
            with patch('messaging.services.WhatsAppService.send_text_message') as mock_send:
                from messaging.tasks import send_fee_reminder
                send_fee_reminder.apply(args=[str(fee_record.id), 7])
                mock_send.assert_not_called()

    def test_fee_reminder_suppressed_during_director_pause(self):
        """US-064: Fee reminder dropped during Director messaging pause."""
        fee_record = FeeRecord.all_objects.create(
            school=self.school, student=self.student,
            academic_term=self.term,
            total_amount=Decimal('300000'),
            amount_paid=Decimal('0'),
        )
        director = User.objects.create_user(
            email='dir@feesupp.ug', password='pass123',
            role='director', school=self.school,
            first_name='Dir', last_name='Supp',
        )
        MessagingPause.objects.create(
            school=self.school,
            start_date=datetime.date.today(),
            end_date=datetime.date.today() + datetime.timedelta(days=7),
            reason='Exams',
            is_active=True,
            created_by=director,
        )
        with patch('messaging.services.WhatsAppService.send_text_message') as mock_send:
            with patch('messaging.services.WhatsAppService.is_paused', return_value=False):
                from messaging.tasks import send_fee_reminder
                send_fee_reminder.apply(args=[str(fee_record.id), 7])
                mock_send.assert_not_called()
