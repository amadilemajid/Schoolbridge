"""
Automation services.
US-063: is_school_day() — single central check for all message tasks.
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

        # Check if within an active term
        term = AcademicTerm.objects.filter(
            school=school,
            start_date__lte=date,
            end_date__gte=date,
            is_active=True,
        ).first()

        if not term:
            return False

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
