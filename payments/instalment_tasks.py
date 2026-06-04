"""
US-C05: Instalment Plan Celery Tasks.
Automatic reminders sent on each instalment due date.
"""
import logging
from celery import shared_task
from django.utils import timezone

logger = logging.getLogger('payments')


@shared_task(bind=True, max_retries=3)
def send_instalment_reminder(self, instalment_id):
    """
    Send WhatsApp reminder for specific instalment.
    Triggered automatically on due date via Celery beat.
    
    Args:
        instalment_id: UUID string of PaymentPlanInstalment
    """
    from payments.models import PaymentPlanInstalment
    from payments.instalment_service import InstalmentPlanService
    
    try:
        instalment = PaymentPlanInstalment.all_objects.select_related(
            'payment_plan',
            'payment_plan__student',
            'payment_plan__school'
        ).get(id=instalment_id)
        
        success = InstalmentPlanService.send_instalment_reminder(instalment)
        
        if not success:
            logger.warning(f"Failed to send instalment reminder: {instalment_id}")
            # Retry after 5 minutes
            raise self.retry(countdown=300)
        
        return {'instalment_id': str(instalment_id), 'status': 'sent'}
        
    except PaymentPlanInstalment.DoesNotExist:
        logger.error(f"PaymentPlanInstalment not found: {instalment_id}")
        return {'instalment_id': str(instalment_id), 'status': 'not_found'}
    
    except Exception as exc:
        logger.error(f"Error sending instalment reminder {instalment_id}: {exc}")
        raise self.retry(exc=exc, countdown=300)


@shared_task
def process_daily_instalment_reminders():
    """
    Daily task to send reminders for instalments due today.
    Runs every morning at 8:00 AM via Celery beat.
    """
    from payments.instalment_service import InstalmentPlanService
    
    today = timezone.localdate()
    due_instalments = InstalmentPlanService.get_due_instalments(today)
    
    count = 0
    for instalment in due_instalments:
        # Queue individual reminder tasks
        send_instalment_reminder.delay(str(instalment.id))
        count += 1
    
    logger.info(f"Queued {count} instalment reminders for {today}")
    return {'date': str(today), 'queued': count}


@shared_task
def check_overdue_instalments():
    """
    Check for overdue instalments and send escalated reminders.
    Runs daily at 10:00 AM via Celery beat.
    """
    from payments.instalment_service import InstalmentPlanService
    from payments.models import PaymentPlanInstalment
    
    overdue = InstalmentPlanService.get_overdue_instalments()
    
    # Send escalated reminders for overdue instalments
    count = 0
    for instalment in overdue:
        # Only send if last reminder was more than 2 days ago
        if instalment.reminder_sent_at:
            days_since = (timezone.now() - instalment.reminder_sent_at).days
            if days_since < 2:
                continue
        
        # Mark as overdue and send reminder
        if instalment.status != 'overdue':
            instalment.status = 'overdue'
            instalment.save(update_fields=['status'])
        
        send_instalment_reminder.delay(str(instalment.id))
        count += 1
    
    logger.info(f"Queued {count} overdue instalment reminders")
    return {'overdue_count': overdue.count(), 'reminders_sent': count}
