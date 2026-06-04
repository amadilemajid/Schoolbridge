"""
US-C01: Escalation Reminder Celery Tasks.
Sends escalated reminders with Director/Bursar notifications.
"""
import logging
from celery import shared_task
from celery.exceptions import MaxRetriesExceededError
from django.utils import timezone
from django.db import transaction

logger = logging.getLogger('payments')


@shared_task(bind=True, max_retries=3, default_retry_delay=120)
def send_escalated_reminder(self, escalation_id: str):
    """
    US-C01: Send a single escalation reminder.
    - Checks if balance is cleared (suppress if paid)
    - Sends WhatsApp message with appropriate urgency level
    - Notifies Director at Level 3+
    - Notifies Bursar at Level 4+
    - Creates audit log
    """
    from payments.escalation_models import ReminderEscalation, ReminderEscalationLog
    from payments.escalation_service import EscalationEngine
    from messaging.services import WhatsAppService
    from messaging.models import MessageLog
    from notifications.services import NotificationService
    from automation.services import CalendarService
    
    try:
        escalation = ReminderEscalation.all_objects.select_related(
            'fee_record',
            'fee_record__student',
            'school',
            'academic_term'
        ).prefetch_related(
            'fee_record__student__guardians'
        ).get(id=escalation_id)
        
        fee_record = escalation.fee_record
        student = fee_record.student
        
        # Suppress if fully paid
        if fee_record.is_fully_paid:
            escalation.status = 'suppressed'
            escalation.suppressed_at = timezone.now()
            escalation.suppression_reason = 'balance_paid'
            escalation.save()
            logger.info(
                f"Escalation L{escalation.level} suppressed - "
                f"{student} balance cleared"
            )
            return
        
        # Suppress if holiday
        if not CalendarService.is_school_day(escalation.school, timezone.localdate()):
            logger.info(
                f"Escalation L{escalation.level} skipped - holiday/weekend for {student}"
            )
            return
        
        # Check Director pause
        if CalendarService.is_messaging_paused(escalation.school):
            CalendarService.record_dropped_task(
                escalation.school, 
                f'escalation_L{escalation.level}'
            )
            logger.info(
                f"Escalation L{escalation.level} dropped - "
                f"messaging paused for {escalation.school.name}"
            )
            return
        
        # Get primary guardian
        guardian = student.guardians.filter(is_primary=True).first()
        if not guardian:
            escalation.status = 'failed'
            escalation.save()
            logger.warning(f"No guardian for {student} - escalation L{escalation.level} failed")
            return
        
        # Build message
        language = guardian.preferred_language or 'english'
        deadline_str = escalation.academic_term.fee_deadline.strftime('%d %b %Y')
        days_remaining = (
            escalation.academic_term.fee_deadline - timezone.localdate()
        ).days
        
        emoji, message_text = EscalationEngine.get_message_template(
            level=escalation.level,
            language=language,
            student_name=student.get_full_name(),
            balance=fee_record.balance,
            deadline_str=deadline_str,
            days_remaining=days_remaining,
            school_name=escalation.school.name
        )
        
        # Send WhatsApp
        msg_id, success = WhatsAppService.send_text_message(
            to_phone=guardian.phone_normalised,
            text=message_text
        )
        
        if not success:
            # Retry up to 3 times
            try:
                self.retry(exc=Exception("WhatsApp send failed"))
            except MaxRetriesExceededError:
                escalation.status = 'failed'
                escalation.save()
                logger.error(
                    f"Escalation L{escalation.level} failed after retries - {student}"
                )
            return
        
        # Update escalation status
        escalation.status = 'sent'
        escalation.sent_at = timezone.now()
        
        # Notify Director at Level 3+
        if EscalationEngine.should_notify_director(escalation.level):
            NotificationService.notify_role(
                school=escalation.school,
                role='director',
                message=(
                    f"Level {escalation.level} fee reminder sent to {guardian.get_full_name()} "
                    f"for {student.get_full_name()}. "
                    f"Outstanding balance: UGX {fee_record.balance:,}"
                ),
                notification_type='ESCALATION_ALERT',
            )
            escalation.director_notified = True
        
        # Notify Bursar at Level 4+
        if EscalationEngine.should_notify_bursar(escalation.level):
            NotificationService.notify_role(
                school=escalation.school,
                role='bursar',
                message=(
                    f"URGENT: Level {escalation.level} escalation for {student.get_full_name()}. "
                    f"Balance: UGX {fee_record.balance:,}. "
                    f"Deadline in {days_remaining} days."
                ),
                notification_type='ESCALATION_URGENT',
            )
            escalation.bursar_notified = True
        
        escalation.save()
        
        # Create audit log
        ReminderEscalationLog.objects.create(
            escalation=escalation,
            message_sent=message_text,
            balance_at_send=fee_record.balance,
            recipient_phone=guardian.phone_normalised,
            language=language,
            whatsapp_message_id=msg_id or '',
            delivery_status='sent',
            director_notified=escalation.director_notified,
            bursar_notified=escalation.bursar_notified,
        )
        
        # Log to MessageLog as well
        MessageLog.all_objects.create(
            school=escalation.school,
            student=student,
            recipient_phone=guardian.phone_normalised,
            channel='whatsapp',
            template_type=f'escalation_L{escalation.level}',
            message_body=message_text,
            whatsapp_message_id=msg_id or '',
            status='sent',
            sent_at=timezone.now(),
        )
        
        logger.info(
            f"Escalation L{escalation.level} sent successfully - "
            f"{student} (Balance: UGX {fee_record.balance:,})"
        )
        
    except ReminderEscalation.DoesNotExist:
        logger.warning(f"Escalation {escalation_id} not found")
    except Exception as exc:
        logger.exception(f"send_escalated_reminder failed: {exc}")
        try:
            self.retry(exc=exc)
        except MaxRetriesExceededError:
            logger.error(f"Escalation {escalation_id} exhausted retries")


@shared_task(bind=True)
def process_daily_escalations(self):
    """
    US-C01: Process all escalations due today.
    Runs daily at 8:00 AM EAT via Celery beat.
    """
    from payments.escalation_service import EscalationEngine
    
    due_escalations = EscalationEngine.get_due_escalations()
    
    count = 0
    for escalation in due_escalations:
        send_escalated_reminder.delay(str(escalation.id))
        count += 1
    
    logger.info(f"Queued {count} escalation reminders for today")
    return count


@shared_task(bind=True)
def initialize_term_escalations(self, term_id: str):
    """
    US-C01: Initialize escalation schedules when term is activated.
    Also called when term fee_deadline is changed.
    """
    from schools.models import AcademicTerm
    from payments.escalation_service import EscalationEngine
    
    try:
        term = AcademicTerm.objects.get(id=term_id)
        count = EscalationEngine.initialize_escalations_for_term(term)
        logger.info(f"Initialized {count} escalations for term {term.name}")
        return count
    except AcademicTerm.DoesNotExist:
        logger.error(f"Term {term_id} not found")
        return 0
