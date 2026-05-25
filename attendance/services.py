"""
Attendance service — business logic.
US-049: Validate attendance window (7am–12pm). Lock register at 12pm.
US-050: Calculate attendance % per student.
US-051: Alert Director if below 75%.
US-052: Mark pre-excused from parent WhatsApp command.
"""
import logging
from datetime import date, timedelta
from django.db.models import Count, Q, Case, When, Value, IntegerField
from django.utils import timezone
from django.conf import settings

logger = logging.getLogger('schoolbridge')


class AttendanceService:

    @classmethod
    def is_register_open(cls, school):
        """US-049: Register open 7am–12pm EAT only."""
        now = timezone.localtime()
        return settings.ATTENDANCE_OPEN_HOUR <= now.hour < settings.ATTENDANCE_CLOSE_HOUR

    @classmethod
    def get_or_create_register(cls, class_group, term, date, marked_by):
        """Return attendance records for a class on a given date, creating blanks if needed."""
        from attendance.models import AttendanceRecord
        from students.models import Student

        students = Student.all_objects.filter(
            school=class_group.school,
            current_class=class_group,
            is_active=True,
        )

        records = {}
        for student in students:
            record, _ = AttendanceRecord.all_objects.get_or_create(
                student=student,
                date=date,
                defaults={
                    'school': class_group.school,
                    'class_group': class_group,
                    'academic_term': term,
                    'status': 'absent',  # Default to absent
                    'marked_by': marked_by,
                }
            )
            records[str(student.id)] = record
        return records

    @classmethod
    def submit_register(cls, class_group, date, attendance_data, marked_by):
        """
        US-049: Submit attendance register.
        attendance_data: [{student_id, status, notes}, ...]
        Triggers absence alerts for absent students (US-037).
        Checks 75% threshold for each absent student (US-051).
        """
        from attendance.models import AttendanceRecord
        from messaging.tasks import send_absence_alert

        if not cls.is_register_open(class_group.school):
            raise ValueError("Attendance register is closed. Submission allowed 7am–12pm only.")

        # Validate school day
        from automation.services import CalendarService
        if not CalendarService.is_school_day(class_group.school, date):
            raise ValueError("Cannot submit attendance on a non-school day.")

        updated_records = []
        absent_students = []

        for entry in attendance_data:
            student_id = entry.get('student_id')
            status = entry.get('status', 'present')
            notes = entry.get('notes', '')

            record, _ = AttendanceRecord.all_objects.update_or_create(
                student_id=student_id,
                date=date,
                defaults={
                    'school': class_group.school,
                    'class_group': class_group,
                    'status': status,
                    'notes': notes,
                    'marked_by': marked_by,
                }
            )
            updated_records.append(record)

            if status == 'absent' and not record.pre_excused:
                absent_students.append(record)

        # Fire absence alerts (US-037)
        date_str = date.strftime('%Y-%m-%d') if hasattr(date, 'strftime') else str(date)
        for record in absent_students:
            send_absence_alert.delay(str(record.student_id), date_str)

        # Check 75% threshold (US-051)
        cls._check_attendance_alerts(absent_students)

        return updated_records

    @classmethod
    def _check_attendance_alerts(cls, absent_records):
        """US-051: Alert Director when student falls below 75%. Max once per week per student."""
        from django.core.cache import cache
        from notifications.services import NotificationService

        for record in absent_records:
            student = record.student
            rate = cls.get_attendance_rate(student)
            if rate is None or rate >= settings.ATTENDANCE_ALERT_THRESHOLD:
                continue

            # Throttle: max once per student per week (US-051)
            cache_key = f"attendance_alert:{student.id}:{timezone.localdate().isocalendar()[1]}"
            if cache.get(cache_key):
                continue

            NotificationService.notify_role(
                school=student.school,
                role='director',
                message=(
                    f"⚠️ Low Attendance: {student.get_full_name()} "
                    f"({student.current_class.name if student.current_class else 'N/A'}) "
                    f"attendance rate is {rate:.1f}% — below {settings.ATTENDANCE_ALERT_THRESHOLD}% threshold."
                ),
                notification_type='LOW_ATTENDANCE_ALERT',
            )
            cache.set(cache_key, True, timeout=7 * 24 * 3600)  # 1 week

    @classmethod
    def get_attendance_rate(cls, student, term=None):
        """US-050: Calculate attendance % for a student in a term."""
        from attendance.models import AttendanceRecord
        if term is None:
            term = student.school.terms.filter(is_current=True).first()
        if not term:
            return None

        records = AttendanceRecord.all_objects.filter(
            student=student, academic_term=term
        )
        total = records.count()
        if total == 0:
            return None

        present = records.filter(status__in=['present', 'late']).count()
        return (present / total) * 100

    @classmethod
    def get_class_summary(cls, class_group, term, date=None):
        """US-050: Attendance summary for a class."""
        from attendance.models import AttendanceRecord
        qs = AttendanceRecord.all_objects.filter(
            class_group=class_group, academic_term=term
        )
        if date:
            qs = qs.filter(date=date)
        return qs.values('student__first_name', 'student__last_name', 'date', 'status')

    @classmethod
    def mark_pre_excused(cls, student, absence_date, reason=''):
        """US-052: Mark a student as pre-excused from parent WhatsApp ABSENT command."""
        from attendance.models import AttendanceRecord
        record, created = AttendanceRecord.all_objects.update_or_create(
            student=student,
            date=absence_date,
            defaults={
                'school': student.school,
                'status': 'excused',
                'pre_excused': True,
                'pre_excused_reason': reason,
                'pre_excused_at': timezone.now(),
                'class_group': student.current_class,
            }
        )
        logger.info(f"Pre-excused absence for {student} on {absence_date}")
        return record

    @classmethod
    def get_attendance_vs_fees(cls, school, term):
        """
        US-053: Cross-reference attendance vs fee payment.
        Flag students with >80% attendance but <50% fees paid.
        Available from Week 4 of term.
        """
        from attendance.models import AttendanceRecord
        from payments.models import FeeRecord
        from django.db.models import F, FloatField, ExpressionWrapper

        term_start = term.start_date
        today = timezone.localdate()
        weeks_elapsed = (today - term_start).days // 7
        if weeks_elapsed < 4:
            return None, "Cross-reference available from Week 4 of term."

        results = []
        students = school.students.filter(is_active=True).select_related('current_class')
        for student in students:
            rate = cls.get_attendance_rate(student, term)
            if rate is None or rate < 80:
                continue
            try:
                fr = FeeRecord.all_objects.get(student=student, academic_term=term)
                if fr.payment_percentage < 50:
                    results.append({
                        'student_id': str(student.id),
                        'student_name': student.get_full_name(),
                        'class': student.current_class.name if student.current_class else '',
                        'attendance_rate': round(rate, 1),
                        'fee_paid_percent': fr.payment_percentage,
                        'balance': str(fr.balance),
                    })
            except FeeRecord.DoesNotExist:
                continue
        return results, None
