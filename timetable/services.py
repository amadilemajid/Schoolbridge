"""
Structured Timetable Backend — Service Layer.

Provides timetable querying, conflict detection, WhatsApp formatting,
substitution management, and attendance prefilling.
"""
import logging
from collections import defaultdict
from datetime import time

from django.db import models
from django.utils import timezone

from audit.models import AuditLog
from timetable.models import TimetableVersion, TimetableSlot, SubstitutionRecord

logger = logging.getLogger('schoolbridge')

# Emoji numbers for period display
PERIOD_EMOJI = {
    1: '1️⃣', 2: '2️⃣', 3: '3️⃣', 4: '4️⃣', 5: '5️⃣',
    6: '6️⃣', 7: '7️⃣', 8: '8️⃣', 9: '9️⃣', 10: '🔟',
}

DAY_NAMES = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday']


class TimetableService:
    """Service layer for structured timetable operations."""

    # ──────────────────────────────────────────────
    # Queries
    # ──────────────────────────────────────────────
    @classmethod
    def get_active_version(cls, class_group, term):
        """Get the active timetable version for a class and term."""
        return TimetableVersion.all_objects.filter(
            class_group=class_group,
            academic_term=term,
            is_active=True,
        ).select_related('class_group', 'academic_term').first()

    @classmethod
    def get_day_schedule(cls, class_group, term, day_of_week):
        """Get all slots for a specific day."""
        version = cls.get_active_version(class_group, term)
        if not version:
            return []
        return list(
            version.slots.filter(
                day_of_week=day_of_week
            ).select_related('subject', 'teacher').order_by('period_number')
        )

    @classmethod
    def get_teacher_schedule(cls, teacher, term, day_of_week=None):
        """Get all slots assigned to a teacher across all classes."""
        filters = {
            'teacher': teacher,
            'timetable_version__academic_term': term,
            'timetable_version__is_active': True,
        }
        if day_of_week is not None:
            filters['day_of_week'] = day_of_week

        return list(
            TimetableSlot.all_objects.filter(**filters).select_related(
                'timetable_version__class_group', 'subject'
            ).order_by('day_of_week', 'period_number')
        )

    # ──────────────────────────────────────────────
    # Conflict Detection
    # ──────────────────────────────────────────────
    @classmethod
    def validate_no_conflicts(cls, timetable_version):
        """
        Check for teacher double-booking across classes.
        Returns a list of conflict dicts if any found, empty list otherwise.
        """
        slots = timetable_version.slots.filter(
            slot_type='lesson', teacher__isnull=False
        ).select_related('teacher')

        conflicts = []

        for slot in slots:
            # Find other active slots at same time by same teacher
            overlapping = TimetableSlot.all_objects.filter(
                teacher=slot.teacher,
                day_of_week=slot.day_of_week,
                timetable_version__academic_term=timetable_version.academic_term,
                timetable_version__is_active=True,
            ).exclude(
                timetable_version=timetable_version
            ).filter(
                # Time overlap check: starts before this ends AND ends after this starts
                start_time__lt=slot.end_time,
                end_time__gt=slot.start_time,
            ).select_related(
                'timetable_version__class_group'
            )

            for other in overlapping:
                conflict = {
                    'teacher': slot.teacher.get_full_name(),
                    'day': slot.get_day_of_week_display(),
                    'time': (
                        f"{slot.start_time.strftime('%H:%M')}-"
                        f"{slot.end_time.strftime('%H:%M')}"
                    ),
                    'class_1': timetable_version.class_group.name,
                    'class_2': other.timetable_version.class_group.name,
                    'subject_1': slot.display_subject,
                    'subject_2': other.display_subject,
                }
                # Avoid duplicate reports
                reverse = {
                    **conflict,
                    'class_1': conflict['class_2'],
                    'class_2': conflict['class_1'],
                    'subject_1': conflict['subject_2'],
                    'subject_2': conflict['subject_1'],
                }
                if reverse not in conflicts:
                    conflicts.append(conflict)

        return conflicts

    # ──────────────────────────────────────────────
    # WhatsApp Formatting
    # ──────────────────────────────────────────────
    @classmethod
    def format_for_whatsapp(cls, class_group, term, day_of_week=None):
        """
        Format timetable as WhatsApp-friendly text.
        If day_of_week is None, formats the full week.
        """
        version = cls.get_active_version(class_group, term)
        if not version:
            return f"📅 No timetable set for {class_group.name} this term."

        if day_of_week is not None:
            return cls._format_day(version, class_group, day_of_week)

        # Full week
        lines = [f"📅 *Weekly Timetable — {class_group.name}*", ""]

        for day in range(5):
            day_text = cls._format_day(version, class_group, day)
            lines.append(day_text)
            lines.append("")

        return "\n".join(lines).strip()

    @classmethod
    def _format_day(cls, version, class_group, day_of_week):
        """Format a single day's schedule."""
        day_name = DAY_NAMES[day_of_week]
        slots = version.slots.filter(
            day_of_week=day_of_week
        ).select_related('subject', 'teacher').order_by('period_number')

        if not slots.exists():
            return f"📅 *{day_name}* — No classes scheduled"

        lines = [f"📅 *{day_name} Timetable — {class_group.name}*", ""]

        for slot in slots:
            emoji = PERIOD_EMOJI.get(slot.period_number, f"▪️")
            time_str = (
                f"{slot.start_time.strftime('%H:%M')}-"
                f"{slot.end_time.strftime('%H:%M')}"
            )

            if slot.slot_type in ('break', 'lunch'):
                icon = '☕' if slot.slot_type == 'break' else '🍽️'
                lines.append(
                    f"{icon} {time_str} | {slot.get_slot_type_display().upper()}"
                )
            elif slot.slot_type == 'assembly':
                lines.append(f"🏫 {time_str} | ASSEMBLY")
            else:
                teacher_name = (
                    slot.teacher.get_full_name() if slot.teacher else 'TBA'
                )
                subject = slot.display_subject
                line = f"{emoji} {time_str} | {subject} — {teacher_name}"
                if slot.room:
                    line += f" ({slot.room})"
                lines.append(line)

        return "\n".join(lines)

    # ──────────────────────────────────────────────
    # Substitution Management
    # ──────────────────────────────────────────────
    @classmethod
    def create_substitution(cls, slot, date, substitute_teacher, reason,
                            created_by=None):
        """Create a substitution record with audit logging."""
        sub, created = SubstitutionRecord.all_objects.update_or_create(
            timetable_slot=slot,
            date=date,
            defaults={
                'school': slot.school,
                'original_teacher': slot.teacher,
                'substitute_teacher': substitute_teacher,
                'reason': reason,
                'created_by': created_by,
            }
        )

        if created_by:
            AuditLog.log(
                actor=created_by,
                school=slot.school,
                category='SCHOOL',
                action='SUBSTITUTION_CREATED',
                description=(
                    f"Substitution on {date}: {slot.display_subject} "
                    f"({slot.timetable_version.class_group.name})"
                ),
                target=sub,
                after={
                    'original_teacher': (
                        slot.teacher.get_full_name() if slot.teacher else None
                    ),
                    'substitute_teacher': substitute_teacher.get_full_name(),
                    'reason': reason,
                },
            )

        return sub

    # ──────────────────────────────────────────────
    # Attendance Prefilling
    # ──────────────────────────────────────────────
    @classmethod
    def prefill_attendance_stubs(cls, school, date):
        """
        Create blank attendance stubs for all students in classes
        that have timetable slots on the given date's day of week.
        Runs daily at 6:30 AM EAT to prepare for teacher marking.
        """
        from attendance.models import AttendanceRecord
        from schools.models import AcademicTerm

        day_of_week = date.weekday()  # 0=Monday
        if day_of_week > 4:  # Weekend
            return 0

        active_term = AcademicTerm.objects.filter(
            school=school, is_active=True
        ).first()
        if not active_term:
            return 0

        # Find all class groups with active timetable slots on this day
        active_versions = TimetableVersion.all_objects.filter(
            school=school,
            academic_term=active_term,
            is_active=True,
        )

        class_group_ids = set()
        for version in active_versions:
            has_slots = version.slots.filter(
                day_of_week=day_of_week, slot_type='lesson'
            ).exists()
            if has_slots:
                class_group_ids.add(version.class_group_id)

        if not class_group_ids:
            return 0

        # Get all students in those classes
        from students.models import Student
        students = Student.all_objects.filter(
            school=school,
            current_class_id__in=class_group_ids,
            is_active=True,
        )

        created_count = 0
        for student in students:
            _, created = AttendanceRecord.all_objects.get_or_create(
                student=student,
                date=date,
                defaults={
                    'school': school,
                    'class_group': student.current_class,
                    'academic_term': active_term,
                    'status': 'present',  # Default to present, teacher marks absences
                }
            )
            if created:
                created_count += 1

        logger.info(
            f"Attendance prefill for {school.name} on {date}: "
            f"{created_count} stubs created"
        )
        return created_count
