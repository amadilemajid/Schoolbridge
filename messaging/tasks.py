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

        msg_id, success = WhatsAppService.send_text_message(
            to_phone=guardian.phone_normalised,
            text=text,
        )

        log = MessageLog.all_objects.create(
            school=payment.school,
            student=student,
            recipient_phone=guardian.phone_normalised,
            channel='whatsapp',
            template_type='payment_receipt',
            message_body=text,
            whatsapp_message_id=msg_id or '',
            status='sent' if success else 'failed',
            sent_at=timezone.now() if success else None,
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
        msg_id, success = WhatsAppService.send_text_message(to_phone=phone, text=context.get('text', ''))

        school = None
        student = None
        if school_id:
            from schools.models import School
            school = School.objects.filter(id=school_id).first()
        if student_id:
            from students.models import Student
            student = Student.all_objects.filter(id=student_id).first()

        log = MessageLog.all_objects.create(
            school=school,
            student=student,
            recipient_phone=phone,
            channel='whatsapp',
            template_type=template,
            message_body=context.get('text', ''),
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

        MessageLog.all_objects.create(
            school=log.school,
            student=log.student,
            recipient_phone=log.recipient_phone,
            channel='sms',
            template_type=log.template_type,
            message_body=sms_text,
            status='sent' if success else 'failed',
            is_fallback=True,
            fallback_triggered_at=timezone.now(),
            sent_at=timezone.now() if success else None,
        )
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
            return

        text = (
            f"⚠️ *Absence Alert*\n\n"
            f"{student.get_full_name()} was recorded absent today ({date_str}).\n"
            f"Class: {student.current_class.name if student.current_class else 'N/A'}\n\n"
            f"If this is an error, please contact the school. "
            f"Reply ABSENT {date_str} [reason] to notify us in advance next time."
        )

        msg_id, success = WhatsAppService.send_text_message(
            to_phone=guardian.phone_normalised, text=text
        )

        log = MessageLog.all_objects.create(
            school=student.school,
            student=student,
            recipient_phone=guardian.phone_normalised,
            channel='whatsapp',
            template_type='absence_alert',
            message_body=text,
            whatsapp_message_id=msg_id or '',
            status='sent' if success else 'failed',
            sent_at=timezone.now() if success else None,
        )

        # Schedule SMS fallback check (US-037, US-061)
        if success and msg_id:
            check_whatsapp_delivery_and_fallback.apply_async(
                args=[str(log.id)],
                countdown=settings.WHATSAPP_FALLBACK_DELAY_MINUTES * 60,
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
def send_broadcast_chunk(self, broadcast_id: str, phone_list: list, message: str):
    """
    US-035: Send a broadcast message chunk. Rate-limited.
    WhatsApp limit: 1,000 conversations/day on basic tier.
    """
    from messaging.services import WhatsAppService
    from messaging.models import BroadcastMessage, MessageLog

    try:
        broadcast = BroadcastMessage.all_objects.get(id=broadcast_id)
        sent = 0
        failed = 0
        for item in phone_list:
            phone = item.get('phone')
            student_id = item.get('student_id')
            if not phone:
                continue
            msg_id, success = WhatsAppService.send_text_message(to_phone=phone, text=message)
            MessageLog.all_objects.create(
                school=broadcast.school,
                student_id=student_id,
                recipient_phone=phone,
                channel='whatsapp',
                template_type='broadcast',
                message_body=message,
                whatsapp_message_id=msg_id or '',
                status='sent' if success else 'failed',
                sent_at=timezone.now() if success else None,
            )
            if success:
                sent += 1
            else:
                failed += 1

        BroadcastMessage.all_objects.filter(id=broadcast_id).update(
            sent_count=broadcast.sent_count + sent,
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
        WhatsAppService.send_text_message(to_phone=guardian.phone_normalised, text=text)
    except Exception as exc:
        logger.exception(f"Reversal notification failed for {payment_id}: {exc}")
        try:
            self.retry(exc=exc)
        except MaxRetriesExceededError:
            pass


@shared_task(bind=True, max_retries=2, default_retry_delay=30)
def process_inbound_command(self, inbound_message_id: str):
    """Process a parsed inbound WhatsApp command."""
    from messaging.models import InboundMessage
    from messaging.services import InboundCommandProcessor
    try:
        msg = InboundMessage.objects.select_related('school').get(id=inbound_message_id)
        if msg.processed:
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
