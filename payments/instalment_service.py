"""
US-C05: Instalment Plan WhatsApp Confirmation Service.
Sends plan details immediately when created and automatic reminders on each due date.
"""
import logging
from decimal import Decimal
from datetime import timedelta
from django.db import transaction
from django.utils import timezone
from .models import PaymentPlan, PaymentPlanInstalment

logger = logging.getLogger('payments')


class InstalmentPlanService:
    """
    US-C05: Payment plan WhatsApp notifications.
    - Immediate confirmation when plan created
    - Automatic reminders on each instalment due date
    """

    @classmethod
    @transaction.atomic
    def create_plan_with_notification(cls, *, fee_record, instalments_data, 
                                     created_by, notes=''):
        """
        Create payment plan and send immediate WhatsApp confirmation.
        
        Args:
            fee_record: FeeRecord instance
            instalments_data: List of dicts with {due_date, amount}
            created_by: User who created the plan
            notes: Optional notes
            
        Returns:
            PaymentPlan instance
        """
        # Validate instalments sum equals outstanding balance
        total_planned = sum(Decimal(str(i['amount'])) for i in instalments_data)
        balance = fee_record.balance
        
        if total_planned != balance:
            raise ValueError(
                f"Instalment total (UGX {total_planned:,}) must equal "
                f"outstanding balance (UGX {balance:,})"
            )
        
        # Create payment plan
        plan = PaymentPlan.all_objects.create(
            school=fee_record.school,
            fee_record=fee_record,
            student=fee_record.student,
            total_amount=balance,
            status='active',
            created_by=created_by,
            notes=notes,
        )
        
        # Create instalments
        for idx, inst_data in enumerate(instalments_data, start=1):
            PaymentPlanInstalment.objects.create(
                payment_plan=plan,
                instalment_number=idx,
                due_date=inst_data['due_date'],
                amount_due=Decimal(str(inst_data['amount'])),
                status='pending',
            )
        
        logger.info(
            f"Payment plan created: {plan.id} - {len(instalments_data)} instalments "
            f"for {fee_record.student} - Total: UGX {balance:,}"
        )
        
        # Send immediate WhatsApp confirmation (US-C05)
        cls.send_plan_confirmation(plan)
        
        return plan

    @classmethod
    def send_plan_confirmation(cls, plan):
        """
        Send WhatsApp message with full instalment plan details.
        Called immediately after plan creation.
        """
        from messaging.services import WhatsAppService
        from messaging.models import MessageLog
        
        guardian = plan.student.guardians.filter(is_primary=True).first()
        if not guardian:
            logger.warning(f"No primary guardian for plan {plan.id}")
            return False
        
        language = guardian.preferred_language or 'english'
        
        # Build confirmation message
        message = cls._build_plan_confirmation_message(plan, language)
        
        # Send via WhatsApp
        msg_id, success = WhatsAppService.send_text_message(
            to_phone=guardian.phone_normalised,
            text=message,
            school=plan.school
        )
        
        if success:
            # Log the message
            MessageLog.all_objects.create(
                school=plan.school,
                student=plan.student,
                recipient_phone=guardian.phone_normalised,
                channel='whatsapp',
                template_type='payment_plan_confirmation',
                message_body=message,
                whatsapp_message_id=msg_id or '',
                status='sent',
                sent_at=timezone.now(),
            )
            logger.info(f"Payment plan confirmation sent to {guardian.phone_normalised}")
        
        return success

    @classmethod
    def _build_plan_confirmation_message(cls, plan, language='english'):
        """Build WhatsApp confirmation message with all instalment details."""
        instalments = plan.instalments.order_by('instalment_number')
        student_name = f"{plan.student.first_name} {plan.student.last_name}"
        
        templates = {
            'english': lambda: (
                f"📋 *Payment Plan Confirmed*\n\n"
                f"Student: {student_name}\n"
                f"Total Amount: UGX {plan.total_amount:,}\n"
                f"Number of Instalments: {instalments.count()}\n\n"
                f"📅 *Instalment Schedule:*\n"
                + "\n".join([
                    f"{i.instalment_number}. {i.due_date.strftime('%d %b %Y')} - "
                    f"UGX {i.amount_due:,}"
                    for i in instalments
                ]) +
                f"\n\n✅ You will receive reminders before each due date\n"
                f"💬 Reply BALANCE to check payment status\n\n"
                f"— {plan.school.name}"
            ),
            'luganda': lambda: (
                f"📋 *Enteekateeka y'Okusasula Ekakasiddwa*\n\n"
                f"Omwana: {student_name}\n"
                f"Ssente Zonna: UGX {plan.total_amount:,}\n"
                f"Emirundi: {instalments.count()}\n\n"
                f"📅 *Enteekateeka y'Okusasula:*\n"
                + "\n".join([
                    f"{i.instalment_number}. {i.due_date.strftime('%d %b %Y')} - "
                    f"UGX {i.amount_due:,}"
                    for i in instalments
                ]) +
                f"\n\n✅ Ojja kufuna ebijjukizo nga buli lunaku lusembera\n"
                f"💬 Wandiika BALANCE okukebera ssente\n\n"
                f"— {plan.school.name}"
            )
        }
        
        template_func = templates.get(language.lower(), templates['english'])
        return template_func()

    @classmethod
    def send_instalment_reminder(cls, instalment):
        """
        Send WhatsApp reminder for specific instalment.
        Called automatically on due date via Celery task.
        """
        from messaging.services import WhatsAppService
        from messaging.models import MessageLog
        
        plan = instalment.payment_plan
        guardian = plan.student.guardians.filter(is_primary=True).first()
        
        if not guardian:
            logger.warning(f"No guardian for instalment {instalment.id}")
            return False
        
        if instalment.status != 'pending':
            logger.info(f"Instalment {instalment.id} already {instalment.status}, skipping reminder")
            return False
        
        language = guardian.preferred_language or 'english'
        
        # Build reminder message
        message = cls._build_instalment_reminder_message(instalment, language)
        
        # Send via WhatsApp
        msg_id, success = WhatsAppService.send_text_message(
            to_phone=guardian.phone_normalised,
            text=message,
            school=plan.school
        )
        
        if success:
            # Update instalment
            instalment.reminder_sent = True
            instalment.reminder_sent_at = timezone.now()
            instalment.save(update_fields=['reminder_sent', 'reminder_sent_at'])
            
            # Log the message
            MessageLog.all_objects.create(
                school=plan.school,
                student=plan.student,
                recipient_phone=guardian.phone_normalised,
                channel='whatsapp',
                template_type='instalment_reminder',
                message_body=message,
                whatsapp_message_id=msg_id or '',
                status='sent',
                sent_at=timezone.now(),
            )
            logger.info(f"Instalment reminder sent: Plan {plan.id} - Instalment {instalment.instalment_number}")
        
        return success

    @classmethod
    def _build_instalment_reminder_message(cls, instalment, language='english'):
        """Build WhatsApp reminder for instalment due date."""
        plan = instalment.payment_plan
        student_name = f"{plan.student.first_name} {plan.student.last_name}"
        days_until_due = (instalment.due_date - timezone.localdate()).days
        
        # Calculate remaining instalments
        remaining = plan.instalments.filter(
            instalment_number__gte=instalment.instalment_number,
            status='pending'
        )
        remaining_count = remaining.count()
        remaining_amount = sum(i.amount_due for i in remaining)
        
        if days_until_due == 0:
            urgency_en = "📌 *DUE TODAY*"
            urgency_lg = "📌 *ETUUSE LEERO*"
        elif days_until_due == 1:
            urgency_en = "⏰ *Due Tomorrow*"
            urgency_lg = "⏰ *Etuuse Enkya*"
        elif days_until_due <= 3:
            urgency_en = f"⚠️ *Due in {days_until_due} Days*"
            urgency_lg = f"⚠️ *Esigadde Ennaku {days_until_due}*"
        else:
            urgency_en = f"🔔 *Upcoming Payment - {days_until_due} Days*"
            urgency_lg = f"🔔 *Okusasula Okujja - Ennaku {days_until_due}*"
        
        templates = {
            'english': (
                f"{urgency_en}\n\n"
                f"Student: {student_name}\n\n"
                f"📅 *Instalment #{instalment.instalment_number}*\n"
                f"Due Date: {instalment.due_date.strftime('%d %B %Y')}\n"
                f"Amount: UGX {instalment.amount_due:,}\n\n"
                f"Remaining Instalments: {remaining_count}\n"
                f"Total Remaining: UGX {remaining_amount:,}\n\n"
                f"💳 Pay via Mobile Money or Bank\n"
                f"💬 Reply BALANCE for full details\n\n"
                f"— {plan.school.name}"
            ),
            'luganda': (
                f"{urgency_lg}\n\n"
                f"Omwana: {student_name}\n\n"
                f"📅 *Ekisale #{instalment.instalment_number}*\n"
                f"Olunaku: {instalment.due_date.strftime('%d %B %Y')}\n"
                f"Ssente: UGX {instalment.amount_due:,}\n\n"
                f"Ebisigadde: {remaining_count}\n"
                f"Ssente Ezisigadde: UGX {remaining_amount:,}\n\n"
                f"💳 Sasula na Mobile Money oba Bank\n"
                f"💬 Wandiika BALANCE okufuna ebikwata\n\n"
                f"— {plan.school.name}"
            )
        }
        
        return templates.get(language.lower(), templates['english'])

    @classmethod
    def get_due_instalments(cls, date=None):
        """
        Get instalments due on specified date (default: today).
        Called by Celery task to send reminders.
        
        Returns:
            QuerySet of PaymentPlanInstalment
        """
        if date is None:
            date = timezone.localdate()
        
        return PaymentPlanInstalment.all_objects.filter(
            due_date=date,
            status='pending',
            reminder_sent=False,
            payment_plan__status='active'
        ).select_related(
            'payment_plan',
            'payment_plan__student',
            'payment_plan__school'
        ).prefetch_related(
            'payment_plan__student__guardians'
        )

    @classmethod
    @transaction.atomic
    def record_instalment_payment(cls, instalment, payment):
        """
        Mark instalment as paid when payment is made.
        Called after payment is recorded.
        """
        instalment.amount_paid += payment.amount
        
        if instalment.amount_paid >= instalment.amount_due:
            instalment.status = 'paid'
            instalment.paid_at = timezone.now()
        elif instalment.amount_paid > 0:
            instalment.status = 'partial'
        
        instalment.save(update_fields=['amount_paid', 'status', 'paid_at'])
        
        # Check if entire plan is completed
        plan = instalment.payment_plan
        if all(i.status == 'paid' for i in plan.instalments.all()):
            plan.status = 'completed'
            plan.completed_at = timezone.now()
            plan.save(update_fields=['status', 'completed_at'])
            logger.info(f"Payment plan {plan.id} completed")
        
        logger.info(
            f"Instalment payment recorded: Plan {plan.id} - "
            f"Instalment {instalment.instalment_number} - UGX {payment.amount:,}"
        )

    @classmethod
    def get_overdue_instalments(cls):
        """Get instalments that are overdue."""
        today = timezone.localdate()
        return PaymentPlanInstalment.all_objects.filter(
            due_date__lt=today,
            status='pending',
            payment_plan__status='active'
        ).select_related(
            'payment_plan',
            'payment_plan__student',
            'payment_plan__school'
        )
