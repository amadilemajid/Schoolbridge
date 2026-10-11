"""
Structured Timetable Backend — Celery Tasks.

Scheduled tasks:
  - Daily attendance prefill (6:30 AM EAT on school days)
  - Sync timetable to WhatsApp-friendly format
"""
import logging
from celery import shared_task
from django.utils import timezone

logger = logging.getLogger('schoolbridge')


@shared_task(name='timetable.daily_attendance_prefill')
def daily_attendance_prefill():
    """
    Runs daily at 6:30 AM EAT. Dispatches a per-school sub-task to create
    blank attendance stubs for all students in classes with timetable slots today.
    This prevents a slow school from blocking the entire prefill run.
    """
    from schools.models import School

    today = timezone.localdate()
    schools = School.objects.filter(is_active=True).values_list('id', flat=True)
    school_ids = list(schools)

    for school_id in school_ids:
        prefill_attendance_stubs_for_school.delay(str(school_id), today.isoformat())

    logger.info(
        f"Daily attendance prefill dispatched for {len(school_ids)} schools"
    )
    return {'schools_dispatched': len(school_ids)}


@shared_task(name='timetable.prefill_attendance_stubs_for_school', bind=True, max_retries=2)
def prefill_attendance_stubs_for_school(self, school_id: str, date_str: str):
    """
    Per-school attendance stub prefill task. Retries up to 2 times on failure.
    """
    import datetime
    from schools.models import School
    from timetable.services import TimetableService

    try:
        school = School.objects.get(id=school_id)
        target_date = datetime.date.fromisoformat(date_str)
        created = TimetableService.prefill_attendance_stubs(school, target_date)
        logger.info(
            f"Attendance prefill complete for {school.name}: {created} stubs created on {date_str}"
        )
        return {'school': school.name, 'stubs_created': created}
    except School.DoesNotExist:
        logger.error(f"School {school_id} not found — skipping prefill")
        return {'error': f'School {school_id} not found'}
    except Exception as e:
        logger.error(
            f"Attendance prefill failed for school {school_id}: {e}",
            exc_info=True,
        )
        raise self.retry(exc=e, countdown=60)




@shared_task(name='timetable.sync_whatsapp_format')
def sync_timetable_to_whatsapp_format(school_id: str, class_group_id: str,
                                       term_id: str):
    """
    Regenerate the WhatsApp-friendly timetable text and update
    the existing schools.Timetable model content field.
    """
    from schools.models import School, AcademicTerm, Timetable
    from students.models import ClassGroup
    from timetable.services import TimetableService

    try:
        school = School.objects.get(id=school_id)
        class_group = ClassGroup.all_objects.get(id=class_group_id)
        term = AcademicTerm.objects.get(id=term_id)
    except Exception as e:
        logger.error(f"Timetable sync context error: {e}")
        return {'error': str(e)}

    # Generate WhatsApp text
    whatsapp_text = TimetableService.format_for_whatsapp(class_group, term)

    # Update or create the schools.Timetable record
    timetable, created = Timetable.objects.update_or_create(
        school=school,
        class_group=class_group,
        is_active=True,
        defaults={
            'content': whatsapp_text,
            'title': f"{class_group.name} — {term.name}",
        }
    )

    action = 'created' if created else 'updated'
    logger.info(
        f"WhatsApp timetable {action} for {class_group.name} at {school.name}"
    )
    return {'status': action, 'class_group': class_group.name}
