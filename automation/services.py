"""
Automation services.
US-063: is_school_day() — single central check for all message tasks.
US-064: is_messaging_paused() — Director-initiated pause check.
"""
from django.utils import timezone
import logging

logger = logging.getLogger('schoolbridge')


class CalendarService:
    """Single source of truth for school day checks. Used by every outbound task."""

    @staticmethod
    def is_school_day(school, date=None):
        """
        US-063: Returns True if date is a school day (not holiday, weekend, or outside term).
        Always use this before sending any automated message.
        """
        if date is None:
            date = timezone.localdate()

        from schools.models import AcademicTerm, HolidayPeriod

        # Check if within an active term first (strict date bounds)
        term = AcademicTerm.objects.filter(
            school=school,
            start_date__lte=date,
            end_date__gte=date,
            is_active=True,
        ).first()

        if not term:
            # Also accept non-active terms that span the date (e.g., current term not yet toggled active)
            term = AcademicTerm.objects.filter(
                school=school,
                start_date__lte=date,
                end_date__gte=date,
            ).first()

        # If no term covers this date at all, it is NOT a school day
        if not term:
            return False

        # Demo/debug bypass: if within a term's date range, always allow for demo schools
        from django.conf import settings
        is_demo_or_test = (
            getattr(settings, 'DEBUG', False) or
            getattr(settings, 'ATTENDANCE_ALLOW_AFTER_HOURS', False) or
            (school and hasattr(school, 'name') and 'demo' in school.name.lower())
        )
        if is_demo_or_test:
            return True


        # Check if it's a holiday period
        is_holiday = HolidayPeriod.objects.filter(
            school=school,
            start_date__lte=date,
            end_date__gte=date,
        ).exists()

        if is_holiday:
            return False

        # Monday–Friday only (Uganda school week)
        if date.weekday() >= 5:  # Saturday=5, Sunday=6
            return False

        return True

    @staticmethod
    def is_messaging_paused(school, date=None):
        """
        US-064: Returns True if the Director has set an active messaging pause
        covering the given date. Emergency broadcasts bypass this check.
        """
        if date is None:
            date = timezone.localdate()
        from schools.models import MessagingPause
        return MessagingPause.objects.filter(
            school=school,
            is_active=True,
            start_date__lte=date,
            end_date__gte=date,
        ).exists()

    @staticmethod
    def record_dropped_task(school, task_type, date=None):
        """
        US-064: Record a task dropped during a messaging pause.
        Called by every automated task that is suppressed by the pause.
        """
        if date is None:
            date = timezone.localdate()
        from schools.models import MessagingPause
        pause = MessagingPause.objects.filter(
            school=school,
            is_active=True,
            start_date__lte=date,
            end_date__gte=date,
        ).first()
        if not pause:
            return
        summary = pause.dropped_tasks_summary or []
        summary.append({'task_type': task_type, 'date': str(date)})
        pause.dropped_tasks_count += 1
        pause.dropped_tasks_summary = summary
        pause.save(update_fields=['dropped_tasks_count', 'dropped_tasks_summary'])
