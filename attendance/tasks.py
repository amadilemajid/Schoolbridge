"""Attendance Celery tasks."""
import logging
from celery import shared_task
from django.utils import timezone

logger = logging.getLogger('schoolbridge')


@shared_task(bind=True)
def send_teacher_attendance_reminders(self):
    """
    US-076: At 10am EAT, remind teachers who haven't submitted attendance.
    Suppressed on non-school days (US-063).
    """
    from schools.models import School
    from students.models import ClassGroup
    from attendance.models import AttendanceRecord
    from notifications.services import NotificationService
    from automation.services import CalendarService

    today = timezone.localdate()
    for school in School.objects.filter(is_active=True):
        if not CalendarService.is_school_day(school, today):
            continue
        classes_with_attendance = AttendanceRecord.all_objects.filter(
            school=school, date=today
        ).values_list('class_group_id', flat=True).distinct()

        classes_needing_reminder = ClassGroup.objects.filter(
            school=school, is_active=True
        ).exclude(id__in=classes_with_attendance)

        for cg in classes_needing_reminder:
            if cg.form_teacher and cg.form_teacher.is_active:
                NotificationService.notify_user(
                    user=cg.form_teacher,
                    message=f"Please submit attendance for {cg.name}. Register closes at 12:00pm.",
                    notification_type='ATTENDANCE_REMINDER',
                    school=school,
                )
        logger.info(f"Attendance reminders sent for {school.name}: {classes_needing_reminder.count()} classes")


@shared_task(bind=True)
def check_low_attendance_alerts(self):
    """
    US-051: Alert parents and director when student attendance drops below 75%.
    Run weekly via Celery beat.
    """
    from schools.models import School
    from students.models import Student
    from notifications.services import NotificationService
    from attendance.services import AttendanceService
    from messaging.services import WhatsAppService

    for school in School.objects.filter(is_active=True):
        term = school.terms.filter(is_current=True).first()
        if not term:
            continue
        students = Student.all_objects.filter(school=school, is_active=True)
        for student in students:
            rate = AttendanceService.get_attendance_rate(student, term)
            if rate is not None and rate < 75:
                guardian = student.guardians.filter(is_primary=True).first()
                if guardian:
                    if WhatsAppService.is_paused():
                        WhatsAppService.queue_whatsapp_message(
                            school=school,
                            student=student,
                            recipient_phone=guardian.phone_normalised,
                            message_body=(
                                f"⚠️ *Attendance Alert*\n\n"
                                f"{student.get_full_name()} has an attendance rate of "
                                f"{rate:.1f}% this term, below the required 75%.\n\n"
                                f"Please contact the school for assistance."
                            ),
                            template_type='low_attendance_alert',
                        )
                        logger.warning(f"WhatsApp paused; queued low attendance alert for {student.id}")
                        continue
                    WhatsAppService.send_text_message(
                        to_phone=guardian.phone_normalised,
                        text=(
                            f"⚠️ *Attendance Alert*\n\n"
                            f"{student.get_full_name()} has an attendance rate of "
                            f"{rate:.1f}% this term, below the required 75%.\n\n"
                            f"Please contact the school for assistance."
                        )
                    )
                NotificationService.notify_role(
                    school=school,
                    role='director',
                    message=f"{student.get_full_name()} attendance is {rate:.1f}% (below 75%)",
                    notification_type='LOW_ATTENDANCE_ALERT',
                )
        logger.info(f"Low attendance check done for {school.name}")
