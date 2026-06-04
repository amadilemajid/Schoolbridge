"""
US-C04: Defaulter Campaign Celery Tasks.
"""
import logging
from celery import shared_task
from celery.exceptions import MaxRetriesExceededError
from django.utils import timezone

logger = logging.getLogger('payments')


@shared_task(bind=True, max_retries=3, default_retry_delay=120)
def send_campaign_message(self, target_id: str):
    """
    Send a single campaign message to a target.
    
    Args:
        target_id: DefaulterCampaignTarget ID
    """
    from payments.campaign_models import DefaulterCampaignTarget
    from messaging.services import WhatsAppService
    from automation.services import CalendarService
    
    try:
        target = DefaulterCampaignTarget.objects.select_related(
            'campaign',
            'campaign__school',
            'student'
        ).get(id=target_id)
        
        campaign = target.campaign
        
        # Check if messaging is paused
        if CalendarService.is_messaging_paused(campaign.school):
            logger.info(
                f"Campaign {campaign.name} message skipped - "
                f"messaging paused for {campaign.school.name}"
            )
            return
        
        # Send WhatsApp message
        msg_id, success = WhatsAppService.send_text_message(
            to_phone=target.guardian_phone,
            text=target.message_sent,
            school=campaign.school
        )
        
        if not success:
            # Retry up to 3 times
            try:
                self.retry(exc=Exception("WhatsApp send failed"))
            except MaxRetriesExceededError:
                target.status = 'failed'
                target.save(update_fields=['status'])
                
                # Update campaign counts
                campaign.failed_count += 1
                campaign.save(update_fields=['failed_count'])
                
                logger.error(
                    f"Campaign message failed after retries - "
                    f"Target: {target.student.get_full_name()}"
                )
            return
        
        # Update target
        target.status = 'sent'
        target.whatsapp_message_id = msg_id or ''
        target.sent_at = timezone.now()
        target.save(update_fields=['status', 'whatsapp_message_id', 'sent_at'])
        
        # Update campaign counts
        campaign.sent_count += 1
        campaign.save(update_fields=['sent_count'])
        
        logger.info(
            f"Campaign message sent - {campaign.name} -> "
            f"{target.student.get_full_name()} ({target.guardian_phone})"
        )
        
        # Check if campaign is complete
        if campaign.sent_count + campaign.failed_count >= campaign.target_count:
            from payments.campaign_service import DefaulterCampaignService
            DefaulterCampaignService.complete_campaign(campaign)
        
    except DefaulterCampaignTarget.DoesNotExist:
        logger.warning(f"Campaign target {target_id} not found")
    except Exception as exc:
        logger.exception(f"send_campaign_message failed: {exc}")
        try:
            self.retry(exc=exc)
        except MaxRetriesExceededError:
            logger.error(f"Campaign message {target_id} exhausted retries")


@shared_task(bind=True)
def execute_scheduled_campaigns(self):
    """
    Execute all campaigns scheduled for now.
    Runs every 15 minutes via Celery beat.
    """
    from payments.campaign_models import DefaulterCampaign
    from payments.campaign_service import DefaulterCampaignService
    
    now = timezone.now()
    campaigns = DefaulterCampaign.all_objects.filter(
        status='scheduled',
        scheduled_at__lte=now
    )
    
    count = 0
    for campaign in campaigns:
        DefaulterCampaignService.execute_campaign(campaign)
        count += 1
    
    if count > 0:
        logger.info(f"Executed {count} scheduled campaigns")
    
    return count


@shared_task(bind=True)
def update_campaign_delivery_status(self, campaign_id: str):
    """
    Update delivery status for campaign messages.
    Queries WhatsApp API for delivery confirmations.
    Called 30 minutes after campaign execution.
    """
    from payments.campaign_models import DefaulterCampaign, DefaulterCampaignTarget
    
    try:
        campaign = DefaulterCampaign.all_objects.get(id=campaign_id)
        
        # Get all sent messages that haven't been delivered yet
        targets = campaign.targets.filter(
            status='sent',
            delivered_at__isnull=True
        )
        
        updated = 0
        for target in targets:
            # Check MessageLog for delivery status
            from messaging.models import MessageLog
            
            log = MessageLog.all_objects.filter(
                whatsapp_message_id=target.whatsapp_message_id,
                status__in=['delivered', 'read']
            ).first()
            
            if log:
                target.status = log.status
                target.delivered_at = timezone.now()
                target.save(update_fields=['status', 'delivered_at'])
                
                campaign.delivered_count += 1
                updated += 1
        
        if updated > 0:
            campaign.save(update_fields=['delivered_count'])
            logger.info(
                f"Campaign {campaign.name} - Updated {updated} delivery statuses"
            )
        
    except DefaulterCampaign.DoesNotExist:
        logger.warning(f"Campaign {campaign_id} not found")
    except Exception as exc:
        logger.exception(f"update_campaign_delivery_status failed: {exc}")
