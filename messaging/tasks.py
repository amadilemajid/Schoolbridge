"""
Messaging Celery tasks.
US-028: WhatsApp receipt within 60s of MoMo IPN.
US-032: Fee reminders at 14/7/3/1 days before deadline.
US-035: Bulk broadcast with rate limiting.
US-037: Absence alert within 30min; SMS fallback at 15min.
US-061: SMS fallback when WhatsApp fails.
"""
import logging
from celery import shared_task
from celery.exceptions import MaxRetriesExceededError
from django.utils import timezone
from django.conf import settings
from automation.services import CalendarService

logger = logging.getLogger('messaging')


@shared_task(bind=True, max_retries=1, default_retry_delay=300)  # Retry once at 5min (US-028)
def send_payment_receipt(self, payment_id: str):
    """US-028: WhatsApp receipt within 60s of payment. Retry once at 5 min."""
    from payments.models import Payment
    from messaging.models import MessageLog
    from messaging.services import WhatsAppService

    try:
        payment = Payment.all_objects.select_related(
            'student', 'fee_record', 'fee_record__academic_term', 'school'
        ).get(id=payment_id)

        student = payment.student
        if not student:
            logger.warning(f"Payment {payment_id} has no student.")
            return

        guardian = student.guardians.filter(is_primary=True).first()
        if not guardian:
            logger.warning(f"Student {student.id} has no primary guardian.")
            return

        fee_record = payment.fee_record
        balance = fee_record.balance if fee_record else 0

        text = (
            f"✅ *Payment Received*\n\n"
            f"Student: {student.get_full_name()}\n"
            f"Amount: UGX {payment.amount:,}\n"
            f"Method: {payment.get_method_display()}\n"
            f"Date: {payment.payment_date.strftime('%d %b %Y %H:%M')}\n"
            f"Balance: UGX {balance:,}\n\n"
            f"Thank you! Reply BALANCE for full account details."
        )
        if WhatsAppService.is_paused():
            WhatsAppService.queue_whatsapp_message(
                school=payment.school,
                student=student,
                recipient_phone=guardian.phone_normalised,
                message_body=text,
                template_type='payment_receipt',
            )
            logger.warning(f"WhatsApp paused; queued payment receipt for payment {payment_id}")
            return

        # US-064: Director-initiated pause — receipts are NOT dropped (financial comms always sent)
        # Payment receipts bypass the Director pause as they are financial confirmations

        recipient_phone = guardian.phone_normalised
        if not recipient_phone and guardian.phone:
            from students.models import Guardian
            recipient_phone = Guardian._normalise_phone(guardian.phone)

        msg_id, success = WhatsAppService.send_text_message(
            to_phone=recipient_phone or guardian.phone,
            text=text,
        )

        log = MessageLog.all_objects.create(
            school=payment.school,
            student=student,
            recipient_phone=recipient_phone or guardian.phone,
            channel='whatsapp',
            template_type='payment_receipt',
            message_body=text,
            whatsapp_message_id=msg_id or '',
            status='sent' if success else 'failed',
            sent_at=timezone.now() if success else None,
        )

        # US-028 / US-061: Automatic SMS fallback check at 120s if undelivered
        check_whatsapp_delivery_and_fallback.apply_async(
            args=[str(log.id)],
            countdown=120,
        )

        if not success:
            # US-028: Retry once at 5 min — Celery handles this via max_retries=1
            try:
                self.retry(countdown=300)
            except MaxRetriesExceededError:
                logger.error(f"Payment receipt failed after retry for payment {payment_id}")
    except Exception as exc:
        logger.exception(f"send_payment_receipt failed for {payment_id}: {exc}")


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def send_whatsapp_message(self, phone: str, template: str, context: dict,
                           school_id: str = None, student_id: str = None):
    """
    Generic WhatsApp message task.
    US-061: Schedules SMS fallback check at 15 min.
    """
    from messaging.services import WhatsAppService
    from messaging.models import MessageLog

    try:
        school = None
        student = None
        if school_id:
            from schools.models import School
            school = School.objects.filter(id=school_id).first()
        if student_id:
            from students.models import Student
            student = Student.all_objects.filter(id=student_id).first()

        text = context.get('text', '')

        if WhatsAppService.is_paused():
            WhatsAppService.queue_whatsapp_message(
                school=school,
                student=student,
                recipient_phone=phone,
                message_body=text,
                template_type=template,
            )
            logger.warning(f"WhatsApp paused; queued message for phone {phone}")
            return

        # US-064: Check Director-initiated pause (drops non-financial automated messages)
        if school and CalendarService.is_messaging_paused(school):
            CalendarService.record_dropped_task(school, template)
            logger.info(f"Messaging paused by Director; dropped {template} to {phone}")
            return

        msg_id, success = WhatsAppService.send_text_message(to_phone=phone, text=text)

        log = MessageLog.all_objects.create(
            school=school,
            student=student,
            recipient_phone=phone,
            channel='whatsapp',
            template_type=template,
            message_body=text,
            whatsapp_message_id=msg_id or '',
            status='sent' if success else 'failed',
            sent_at=timezone.now() if success else None,
        )

        if success and msg_id:
            # Schedule fallback check at 15 min (US-061)
            check_whatsapp_delivery_and_fallback.apply_async(
                args=[str(log.id)],
                countdown=settings.WHATSAPP_FALLBACK_DELAY_MINUTES * 60,
            )

        if not success:
            self.retry(exc=Exception("WhatsApp send failed"))
    except MaxRetriesExceededError:
        logger.error(f"WhatsApp message failed after retries: phone={phone}")


@shared_task(bind=True, max_retries=0)
def check_whatsapp_delivery_and_fallback(self, message_log_id: str):
    """
    US-061: Check if WhatsApp message was delivered.
    If status is still 'sent' (not 'delivered'/'read') after 15 min → send SMS fallback.
    """
    from messaging.models import MessageLog
    from messaging.services import SMSService

    try:
        log = MessageLog.all_objects.get(id=message_log_id)

        # If already delivered or read, nothing to do
        if log.status in ('delivered', 'read'):
            return

        # Fallback to SMS (US-061)
        logger.info(f"WhatsApp undelivered after 15min — sending SMS fallback to {log.recipient_phone}")
        sms_text = log.message_body[:160]
        success = SMSService.send_sms(to_phone=log.recipient_phone, message=sms_text)

        status_val = 'delivered' if (settings.DEBUG or getattr(settings, 'MOCK_EXTERNAL_APIS', False)) else ('sent' if success else 'failed')
        delivered_at_val = timezone.now() if (status_val == 'delivered') else None

        MessageLog.all_objects.create(
            school=log.school,
            student=log.student,
            recipient_phone=log.recipient_phone,
            channel='sms',
            template_type=log.template_type,
            message_body=sms_text,
            whatsapp_message_id=log.whatsapp_message_id or '',
            status=status_val if success else 'failed',
            is_fallback=True,
            fallback_triggered_at=timezone.now(),
            sent_at=timezone.now() if success else None,
            delivered_at=delivered_at_val,
        )
        log.fallback_triggered_at = timezone.now()
        log.save(update_fields=['fallback_triggered_at'])
    except MessageLog.DoesNotExist:
        pass
    except Exception as exc:
        logger.exception(f"Fallback check failed for log {message_log_id}: {exc}")


@shared_task(bind=True, max_retries=3, default_retry_delay=120)
def send_absence_alert(self, student_id: str, date_str: str):
    """
    US-037: Absence alert within 30min; SMS fallback at 15min.
    Called when attendance register is submitted with student absent.
    """
    from students.models import Student
    from messaging.services import WhatsAppService, SMSService
    from messaging.models import MessageLog

    try:
        student = Student.all_objects.select_related('current_class', 'school').get(id=student_id)
        guardian = student.guardians.filter(is_primary=True).first()
        if not guardian:
            MessageLog.all_objects.create(
                school=student.school,
                student=student,
                recipient_phone='',
                channel='whatsapp',
                template_type='absence_alert',
                message_body=f"Absence recorded for {student.get_full_name()} on {date_str}, but no primary guardian is registered.",
                status='failed',
            )
            logger.warning(f"send_absence_alert: student {student_id} has no primary guardian")
            return

        recipient_phone = guardian.phone_normalised
        if not recipient_phone and guardian.phone:
            from students.models import Guardian
            recipient_phone = Guardian._normalise_phone(guardian.phone)

        text = (
            f"⚠️ *Absence Alert*\n\n"
            f"{student.get_full_name()} was recorded absent today ({date_str}).\n"
            f"Class: {student.current_class.name if student.current_class else 'N/A'}\n\n"
            f"If this is an error, please contact the school. "
            f"Reply ABSENT {date_str} [reason] to notify us in advance next time."
        )

        if not recipient_phone:
            MessageLog.all_objects.create(
                school=student.school,
                student=student,
                recipient_phone=guardian.phone or '',
                channel='whatsapp',
                template_type='absence_alert',
                message_body=text,
                status='failed',
            )
            logger.warning(f"send_absence_alert: student {student_id} guardian has invalid/missing phone")
            return

        if WhatsAppService.is_paused():
            WhatsAppService.queue_whatsapp_message(
                school=student.school,
                student=student,
                recipient_phone=recipient_phone,
                message_body=text,
                template_type='absence_alert',
            )
            logger.warning(f"WhatsApp paused; queued absence alert for student {student_id}")
            return

        # US-064: Director pause check
        if CalendarService.is_messaging_paused(student.school):
            CalendarService.record_dropped_task(student.school, 'absence_alert')
            logger.info(f"Messaging paused by Director; dropped absence alert for student {student_id}")
            return

        msg_id, success = WhatsAppService.send_text_message(
            to_phone=recipient_phone, text=text
        )

        log = MessageLog.all_objects.create(
            school=student.school,
            student=student,
            recipient_phone=recipient_phone,
            channel='whatsapp',
            template_type='absence_alert',
            message_body=text,
            whatsapp_message_id=msg_id or '',
            status='sent' if success else 'failed',
            sent_at=timezone.now() if success else None,
        )

        # Schedule SMS fallback check (US-037, US-061)
        fallback_delay = 120 if not success else (settings.WHATSAPP_FALLBACK_DELAY_MINUTES * 60)
        check_whatsapp_delivery_and_fallback.apply_async(
            args=[str(log.id)],
            countdown=fallback_delay,
        )
    except Student.DoesNotExist:
        logger.warning(f"send_absence_alert: student {student_id} not found")
    except Exception as exc:
        logger.exception(f"send_absence_alert failed: {exc}")
        try:
            self.retry(exc=exc)
        except MaxRetriesExceededError:
            pass


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def send_fee_reminder(self, fee_record_id: str, days_remaining: int):
    """
    US-032: Fee reminder at 14/7/3/1 days before deadline.
    Suppressed if balance is zero or if it's a holiday.
    """
    from payments.models import FeeRecord
    from messaging.services import WhatsAppService
    from messaging.models import MessageLog
    from automation.services import CalendarService

    try:
        fr = FeeRecord.all_objects.select_related(
            'student', 'academic_term', 'school'
        ).get(id=fee_record_id)

        # Suppress if fully paid (US-032)
        if fr.is_fully_paid:
            return

        # Suppress if holiday (US-063)
        if not CalendarService.is_school_day(fr.school, timezone.localdate()):
            return

        guardian = fr.student.guardians.filter(is_primary=True).first()
        if not guardian:
            return

        urgency = "🚨" if days_remaining <= 3 else "⚠️"
        text = (
            f"{urgency} *Fee Reminder*\n\n"
            f"Student: {fr.student.get_full_name()}\n"
            f"Balance Due: UGX {fr.balance:,}\n"
            f"Deadline: {fr.academic_term.fee_deadline.strftime('%d %b %Y')}\n"
            f"Days Remaining: {days_remaining}\n\n"
            f"Reply BALANCE for details or PLAN to request a payment plan.\n"
            f"Pay via MTN MoMo: {fr.school.momo_configs.filter(provider='mtn').first().merchant_phone if fr.school.momo_configs.filter(provider='mtn').exists() else 'Contact school'}"
        )
        if WhatsAppService.is_paused():
            WhatsAppService.queue_whatsapp_message(
                school=fr.school,
                student=fr.student,
                recipient_phone=guardian.phone_normalised,
                message_body=text,
                template_type='fee_reminder',
            )
            logger.warning(f"WhatsApp paused; queued fee reminder for fee record {fee_record_id}")
            return

        # US-064: Director pause — fee reminders are dropped during pause
        if CalendarService.is_messaging_paused(fr.school):
            CalendarService.record_dropped_task(fr.school, 'fee_reminder')
            logger.info(f"Messaging paused by Director; dropped fee reminder for {fee_record_id}")
            return

        msg_id, success = WhatsAppService.send_text_message(
            to_phone=guardian.phone_normalised, text=text
        )

        log = MessageLog.all_objects.create(
            school=fr.school,
            student=fr.student,
            recipient_phone=guardian.phone_normalised,
            channel='whatsapp',
            template_type='fee_reminder',
            message_body=text,
            whatsapp_message_id=msg_id or '',
            status='sent' if success else 'failed',
            sent_at=timezone.now() if success else None,
        )

        if success and msg_id:
            check_whatsapp_delivery_and_fallback.apply_async(
                args=[str(log.id)],
                countdown=settings.WHATSAPP_FALLBACK_DELAY_MINUTES * 60,
            )

        if not success:
            self.retry(exc=Exception("WhatsApp reminder failed"))
    except FeeRecord.DoesNotExist:
        pass
    except Exception as exc:
        logger.exception(f"send_fee_reminder failed for {fee_record_id}: {exc}")
        try:
            self.retry(exc=exc)
        except MaxRetriesExceededError:
            pass


@shared_task(bind=True, max_retries=2, default_retry_delay=120)
def send_broadcast_chunk(self, broadcast_id: str, phone_list: list, message: str, channel: str = 'whatsapp'):
    """
    US-035: Send a broadcast message chunk. Rate-limited.
    WhatsApp limit: 1,000 conversations/day on basic tier.
    Uses bulk_create to batch all MessageLog inserts (performance optimisation).
    Supports channel='whatsapp' (default) or channel='sms'.
    """
    from messaging.services import WhatsAppService, SMSService
    from messaging.models import BroadcastMessage, MessageLog

    try:
        broadcast = BroadcastMessage.all_objects.get(id=broadcast_id)
        sent = 0
        failed = 0
        logs_to_create = []  # Collect logs for bulk insert

        for item in phone_list:
            phone = item.get('phone')
            student_id = item.get('student_id')
            if not phone:
                continue

            if channel == 'sms':
                # SMS path — no pause check needed (SMS is always available)
                success = SMSService.send_sms(to_phone=phone, message=message)
                msg_id = ''
            else:
                # WhatsApp path
                if WhatsAppService.is_paused():
                    WhatsAppService.queue_whatsapp_message(
                        school=broadcast.school,
                        student=None,
                        recipient_phone=phone,
                        message_body=message,
                        template_type='broadcast',
                    )
                    logger.warning(f"WhatsApp paused; queued broadcast to {phone}")
                    continue
                msg_id, success = WhatsAppService.send_text_message(to_phone=phone, text=message)

            from django.conf import settings
            from django.utils import timezone
            status = 'delivered' if (success and getattr(settings, 'DEBUG', False)) else ('sent' if success else 'failed')
            logs_to_create.append(MessageLog(
                school=broadcast.school,
                student_id=student_id,
                recipient_phone=phone,
                channel=channel,
                template_type='broadcast',
                message_body=message,
                whatsapp_message_id=msg_id if channel == 'whatsapp' else '',
                status=status,
                delivered_at=timezone.now() if status == 'delivered' else None,
                sent_at=timezone.now() if success else None,
            ))
            if success:
                sent += 1
            else:
                failed += 1

        # Single bulk insert for entire chunk (50 recipients = 1 query instead of 50)
        if logs_to_create:
            MessageLog.all_objects.bulk_create(logs_to_create, ignore_conflicts=True)

        delivered_inc = sent if getattr(settings, 'DEBUG', False) else 0
        BroadcastMessage.all_objects.filter(id=broadcast_id).update(
            sent_count=broadcast.sent_count + sent,
            delivered_count=broadcast.delivered_count + delivered_inc,
            failed_count=broadcast.failed_count + failed,
        )
    except Exception as exc:
        logger.exception(f"Broadcast chunk failed: {exc}")
        try:
            self.retry(exc=exc)
        except MaxRetriesExceededError:
            pass



@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def send_payment_reversal_notification(self, payment_id: str):
    """US-023: Notify parent on payment reversal."""
    from payments.models import Payment
    from messaging.services import WhatsAppService

    try:
        payment = Payment.all_objects.select_related('student', 'school').get(id=payment_id)
        student = payment.student
        if not student:
            return
        guardian = student.guardians.filter(is_primary=True).first()
        if not guardian:
            return
        text = (
            f"ℹ️ *Payment Reversal Notice*\n\n"
            f"A payment of UGX {payment.amount:,} for {student.get_full_name()} "
            f"has been reversed.\n"
            f"Reason: {payment.reversal_reason}\n\n"
            f"Please contact the school for clarification.\n"
            f"Reply BALANCE to see your current balance."
        )
        if WhatsAppService.is_paused():
            WhatsAppService.queue_whatsapp_message(
                school=payment.school,
                student=student,
                recipient_phone=guardian.phone_normalised,
                message_body=text,
                template_type='payment_reversal',
            )
            logger.warning(f"WhatsApp paused; queued reversal notice for payment {payment_id}")
            return
        WhatsAppService.send_text_message(to_phone=guardian.phone_normalised, text=text)
    except Exception as exc:
        logger.exception(f"Reversal notification failed for {payment_id}: {exc}")
        try:
            self.retry(exc=exc)
        except MaxRetriesExceededError:
            pass


@shared_task(bind=True, max_retries=2, default_retry_delay=30)
def process_inbound_command(self, inbound_message_id: str):
    """Process a parsed inbound WhatsApp command. Rate-limited per phone."""
    from messaging.models import InboundMessage
    from messaging.services import InboundCommandProcessor, WhatsAppService
    from messaging.rate_limiter import RateLimiter
    from messaging.translation_service import TranslationService
    try:
        msg = InboundMessage.objects.select_related('school').get(id=inbound_message_id)
        if msg.processed:
            return

        # Rate limiting check (US-A hardening)
        is_allowed, remaining, retry_after = RateLimiter.check_rate_limit(msg.from_phone)
        if not is_allowed:
            lang = TranslationService.get_language_from_phone(msg.from_phone)
            warning = RateLimiter.get_rate_limit_message(lang)
            WhatsAppService.send_text_message(to_phone=msg.from_phone, text=warning)
            msg.processed = True
            msg.response_sent = True
            msg.save(update_fields=['processed', 'response_sent'])
            logger.warning(f"Rate limit exceeded for {msg.from_phone}")
            return

        InboundCommandProcessor.process(msg)
    except InboundMessage.DoesNotExist:
        pass
    except Exception as exc:
        logger.exception(f"process_inbound_command failed: {exc}")
        try:
            self.retry(exc=exc)
        except MaxRetriesExceededError:
            pass


@shared_task(bind=True, max_retries=2, default_retry_delay=60)
def process_voice_broadcast(self, broadcast_media_id: str, recipient_phone_list: list):
    """
    US-B01/US-B02: Async Celery task to distribute voice notes.
    Sends message referencing Meta WABA media_id.
    Chunks recipients in batches of 50, sleeping 2 seconds between chunks.
    """
    import time
    from messaging.models import BroadcastMedia, MessageLog
    from messaging.services import WhatsAppService
    
    try:
        media = BroadcastMedia.objects.get(id=broadcast_media_id)
        if not media.is_ready:
            logger.error(f"process_voice_broadcast failed: BroadcastMedia {broadcast_media_id} is not uploaded/valid")
            return
            
        media_id = media.whatsapp_media_id
        
        # Chunk recipients by 50
        chunk_size = 50
        for i in range(0, len(recipient_phone_list), chunk_size):
            chunk = recipient_phone_list[i:i + chunk_size]
            for phone in chunk:
                msg_id, success = WhatsAppService.send_audio_message(
                    to_phone=phone,
                    media_id=media_id,
                    school=media.school
                )
                
                # Create MessageLog for audit trail (channel='voice' for frontend filter)
                status = 'delivered' if (success and getattr(settings, 'DEBUG', False)) else ('sent' if success else 'failed')
                MessageLog.all_objects.create(
                    school=media.school,
                    recipient_phone=phone,
                    message_body=f"Voice Note Broadcast: {media.original_filename or media.media_file.name}",
                    channel='voice',
                    whatsapp_message_id=msg_id or '',
                    status=status,
                    delivered_at=timezone.now() if status == 'delivered' else None,
                    sent_at=timezone.now() if success else None,
                    template_type='broadcast',
                )
                
            if i + chunk_size < len(recipient_phone_list):
                time.sleep(2)  # Delay between chunks of 50
                
    except BroadcastMedia.DoesNotExist:
        logger.error(f"process_voice_broadcast: BroadcastMedia {broadcast_media_id} does not exist")
    except Exception as exc:
        logger.exception(f"process_voice_broadcast failed: {exc}")
        try:
            self.retry(exc=exc)
        except MaxRetriesExceededError:
            pass


@shared_task(bind=True, max_retries=2, default_retry_delay=60)
def distribute_report_cards(self, school_id: str, report_cards_list: list):
    """
    US-B03/US-B04: Async Celery task to distribute PDF report cards.
    report_cards_list is a list of dicts: [{'student_id': str, 'parent_phone': str, 'file_path': str, 'filename': str}]
    Uploads each PDF to Meta and sends document message.
    """
    from schools.models import School
    from students.models import Student
    from messaging.models import MessageLog
    from messaging.services import WhatsAppService
    
    try:
        school = School.objects.get(id=school_id)
        
        for card in report_cards_list:
            student_id = card.get('student_id')
            parent_phone = card.get('parent_phone')
            file_path = card.get('file_path')
            filename = card.get('filename', 'ReportCard.pdf')
            
            try:
                student = Student.objects.get(id=student_id)
                
                # Upload the PDF to Meta WABA Media endpoint
                media = WhatsAppService.upload_media(
                    school=school,
                    file_path=file_path,
                    mime_type='application/pdf',
                    media_type='document',
                    original_filename=filename,
                    description=f"Report Card for {student.get_full_name()}",
                )
                
                if not media.is_ready:
                    logger.error(f"distribute_report_cards: Upload failed for student {student_id}")
                    continue
                    
                msg_id, success = WhatsAppService.send_document_message(
                    to_phone=parent_phone,
                    media_id=media.whatsapp_media_id,
                    filename=filename,
                    school=school
                )
                
                status = 'sent' if success else 'failed'
                MessageLog.all_objects.create(
                    school=school,
                    student=student,
                    recipient_phone=parent_phone,
                    channel='whatsapp',
                    message_body=f"Report Card: {filename}",
                    whatsapp_message_id=msg_id or '',
                    status=status,
                    template_type='report_card_ready',
                )
                
            except Exception as e:
                logger.error(f"distribute_report_cards: failed for card {card}: {e}")
                
    except School.DoesNotExist:
        logger.error(f"distribute_report_cards: School {school_id} does not exist")
    except Exception as exc:
        logger.exception(f"distribute_report_cards failed: {exc}")
        try:
            self.retry(exc=exc)
        except MaxRetriesExceededError:
            pass


