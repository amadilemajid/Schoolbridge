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
