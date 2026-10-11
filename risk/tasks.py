"""
At-Risk Student Intelligence Engine — Celery Tasks.

Scheduled tasks:
  - Weekly risk recalculation (Sunday 1 AM EAT)
  - Monday morning briefing (Monday 7 AM EAT)
  - Immediate high-risk WhatsApp alerts
"""
import logging
from celery import shared_task
from django.utils import timezone

logger = logging.getLogger('schoolbridge')


@shared_task(name='risk.weekly_risk_recalculation')
def weekly_risk_recalculation():
    """
    Triggered every Sunday at 1 AM EAT via celery-beat.
    Spawns per-school recalculation tasks for tenant isolation.
    """
    from schools.models import School, AcademicTerm

    schools = School.objects.filter(is_active=True)
    dispatched = 0

    for school in schools:
        active_term = AcademicTerm.objects.filter(
            school=school, is_active=True
        ).first()
        if active_term:
            recalculate_school_risk_task.delay(
                str(school.id), str(active_term.id)
            )
            dispatched += 1

    logger.info(
        f"Weekly risk recalculation dispatched for {dispatched} schools"
    )
    return {'schools_dispatched': dispatched}


@shared_task(name='risk.recalculate_school_risk')
def recalculate_school_risk_task(school_id: str, term_id: str):
    """
    Per-school risk recalculation. Detects newly escalated high-risk
    students and triggers WhatsApp alerts.
    """
    from schools.models import School, AcademicTerm
    from risk.models import RiskConfiguration, StudentRiskProfile
    from risk.services import RiskEvaluationEngine
    from audit.models import AuditLog

    try:
        school = School.objects.get(id=school_id)
        term = AcademicTerm.objects.get(id=term_id)
    except (School.DoesNotExist, AcademicTerm.DoesNotExist) as e:
        logger.error(f"Risk recalculation context error: {e}")
        return {'error': str(e)}

    # Snapshot current high-risk set to detect new escalations
    pre_high_risk_ids = set(
        StudentRiskProfile.all_objects.filter(
            school=school, risk_level='high'
        ).values_list('student_id', flat=True)
    )

    # Run evaluation
    profiles = RiskEvaluationEngine.recalculate_school(school, term)

    # Detect newly escalated high-risk students
    config, _ = RiskConfiguration.objects.get_or_create(school=school)

    if config.enable_whatsapp_alerts:
        new_high_risk = StudentRiskProfile.all_objects.filter(
            school=school,
            risk_level='high',
            alert_dispatched=False,
        ).exclude(student_id__in=pre_high_risk_ids)

        for profile in new_high_risk:
            send_high_risk_alert.delay(str(profile.id))

    # Audit log
    AuditLog.log(
        school=school,
        category='SYSTEM',
        action='RISK_RECALCULATION_COMPLETED',
        description=(
            f"Weekly risk recalculation for {school.name}: "
            f"{len(profiles)} students evaluated"
        ),
    )

    return {
        'school': school.name,
        'students_evaluated': len(profiles),
        'new_high_risk_alerts': new_high_risk.count() if config.enable_whatsapp_alerts else 0,
    }


@shared_task(
    name='risk.send_high_risk_alert',
    max_retries=2,
    default_retry_delay=60,
)
def send_high_risk_alert(profile_id: str):
    """
    Dispatch WhatsApp alert to School Director when a student
    enters critical dropout risk for the first time in the cycle.
    """
    from risk.models import StudentRiskProfile
    from messaging.services import WhatsAppService

    try:
        profile = StudentRiskProfile.all_objects.select_related(
            'student', 'student__current_class', 'school'
        ).get(id=profile_id)
    except StudentRiskProfile.DoesNotExist:
        logger.error(f"Risk profile {profile_id} not found for alert")
        return

    # Find active Director
    director = profile.school.staff.filter(
        role='director', is_active=True
    ).first()

    if not director or not director.phone:
        logger.warning(
            f"No director phone for {profile.school.name}; "
            f"skipping risk alert for {profile.student}"
        )
        return

    # Check WhatsApp pause
    if WhatsAppService.is_paused():
        logger.warning("WhatsApp paused; queuing high-risk alert")
        WhatsAppService.queue_whatsapp_message(
            school=profile.school,
            recipient_phone=director.phone,
            message_body=_format_alert_message(profile),
            template_type='risk_alert',
        )
        profile.alert_dispatched = True
        profile.save(update_fields=['alert_dispatched'])
        return

    # Dispatch
    factors_text = ", ".join(
        f.replace('_', ' ') for f in profile.flagged_factors
    )
    message = _format_alert_message(profile)

    msg_id, success = WhatsAppService.send_text_message(
        to_phone=director.phone, text=message
    )

    if success:
        profile.alert_dispatched = True
        profile.save(update_fields=['alert_dispatched'])
        logger.info(
            f"High-risk alert sent for {profile.student} "
            f"to {director.email} (msg_id={msg_id})"
        )
    else:
        logger.error(
            f"Failed to send high-risk alert for {profile.student}"
        )


@shared_task(name='risk.send_monday_briefing')
def send_monday_briefing():
    """
    Triggered every Monday at 7 AM EAT via celery-beat.
    Sends a summary briefing to each school's Director.
    """
    from schools.models import School, AcademicTerm
    from risk.models import RiskConfiguration
    from risk.services import RiskEvaluationEngine
    from messaging.services import WhatsAppService

    schools = School.objects.filter(is_active=True)
    sent_count = 0

    for school in schools:
        try:
            config, _ = RiskConfiguration.objects.get_or_create(school=school)
            if not config.enable_monday_briefing:
                continue

            active_term = AcademicTerm.objects.filter(
                school=school, is_active=True
            ).first()
            if not active_term:
                continue

            director = school.staff.filter(
                role='director', is_active=True
            ).first()
            if not director or not director.phone:
                continue

            # Generate briefing
            summary = RiskEvaluationEngine.get_monday_briefing(
                school, active_term
            )
            message = RiskEvaluationEngine.format_briefing_whatsapp(summary)

            # Send
            if WhatsAppService.is_paused():
                WhatsAppService.queue_whatsapp_message(
                    school=school,
                    recipient_phone=director.phone,
                    message_body=message,
                    template_type='monday_briefing',
                )
            else:
                WhatsAppService.send_text_message(
                    to_phone=director.phone, text=message
                )

            sent_count += 1

        except Exception as e:
            logger.error(
                f"Monday briefing failed for {school.name}: {e}",
                exc_info=True,
            )

    logger.info(f"Monday briefing dispatched to {sent_count} schools")
    return {'schools_notified': sent_count}


def _format_alert_message(profile):
    """Format the high-risk alert WhatsApp message."""
    factors_text = ", ".join(
        f.replace('_', ' ') for f in profile.flagged_factors
    )
    class_name = (
        profile.student.current_class.name
        if profile.student.current_class else 'N/A'
    )

    return (
        f"⚠️ *SchoolBridge At-Risk Alert*\n\n"
        f"Student *{profile.student.get_full_name()}* ({class_name}) "
        f"has been flagged as *HIGH RISK* "
        f"(Score: {profile.risk_score}/100).\n\n"
        f"Factors: {factors_text}\n"
        f"Attendance Rate: {profile.attendance_rate:.1f}%\n"
        f"Fee Balance: UGX {profile.fee_balance:,}\n\n"
        f"Please log in to the dashboard to review this case."
    )
