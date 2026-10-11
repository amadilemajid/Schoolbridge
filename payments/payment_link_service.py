"""
US-C03: Payment Link Service.
Generates secure payment links and sends via WhatsApp.
"""
import logging
import secrets
from datetime import timedelta
from decimal import Decimal
from django.db import transaction
from django.utils import timezone
from .payment_link_models import PaymentLink

logger = logging.getLogger('payments')


class PaymentLinkService:
    """
    US-C03: Generate one-time payment links for fee collection.
    Links expire after 72 hours or first use.
    """
    
    DEFAULT_EXPIRY_HOURS = 72  # 3 days
    TOKEN_LENGTH = 32  # 32 bytes = 64 hex chars

    @classmethod
    @transaction.atomic
    def generate_link(cls, fee_record, amount=None, description=None, 
                     expiry_hours=None, created_by=None):
        """
        Generate a secure payment link for a fee record.
        
        Args:
            fee_record: FeeRecord instance
            amount: Amount for this link (default: full balance)
            description: Payment description
            expiry_hours: Hours until expiry (default: 72)
            created_by: User who created the link
            
        Returns:
            PaymentLink instance
        """
        if amount is None:
            amount = fee_record.balance
        
        amount = Decimal(str(amount))
        
        if amount <= 0:
            raise ValueError("Payment amount must be greater than zero")
        
        if amount > fee_record.balance:
            raise ValueError("Payment amount exceeds outstanding balance")
        
        # Generate secure token
        token = secrets.token_urlsafe(cls.TOKEN_LENGTH)
        
        # Calculate expiry
        expiry = timezone.now() + timedelta(hours=expiry_hours or cls.DEFAULT_EXPIRY_HOURS)
        
        # Get guardian info
        guardian = fee_record.student.guardians.filter(is_primary=True).first() or fee_record.student.guardians.first()
        if guardian:
            recipient_phone = guardian.phone_normalised or getattr(guardian, 'phone', '')
            recipient_name = f"{guardian.first_name} {guardian.last_name}".strip()
        else:
            recipient_phone = getattr(fee_record.student, 'emergency_contact_phone', '') or ''
            recipient_name = f"{fee_record.student.first_name} {fee_record.student.last_name}".strip()

        # Create link
        link = PaymentLink.all_objects.create(
            school=fee_record.school,
            fee_record=fee_record,
            student=fee_record.student,
            token=token,
            amount=amount,
            description=description or f"School fees for {fee_record.student.first_name} {fee_record.student.last_name}",
            expires_at=expiry,
            recipient_phone=recipient_phone,
            recipient_name=recipient_name,
            created_by=created_by,
        )
        
        logger.info(
            f"Payment link generated: {link.token[:8]}... for "
            f"{fee_record.student} - UGX {amount:,}"
        )
        
        return link

    @classmethod
    def send_link_via_whatsapp(cls, payment_link):
        """
        Send payment link to guardian via WhatsApp.
        
        Args:
            payment_link: PaymentLink instance
            
        Returns:
            (message_id, success)
        """
        from messaging.services import WhatsAppService
        from messaging.models import MessageLog
        
        guardian = payment_link.student.guardians.filter(is_primary=True).first()
        if not guardian:
            logger.warning(f"No guardian for payment link {payment_link.id}")
            return None, False
        
        language = guardian.preferred_language or 'english'
        
        # Build message
        message = cls._build_whatsapp_message(
            payment_link=payment_link,
            language=language
        )
        
        # Send via WhatsApp
        msg_id, success = WhatsAppService.send_text_message(
            to_phone=guardian.phone_normalised,
            text=message,
            school=payment_link.school
        )
        
        if success:
            # Log the message
            MessageLog.all_objects.create(
                school=payment_link.school,
                student=payment_link.student,
                recipient_phone=guardian.phone_normalised,
                channel='whatsapp',
                template_type='payment_link',
                message_body=message,
                whatsapp_message_id=msg_id or '',
                status='sent',
                sent_at=timezone.now(),
            )
            logger.info(f"Payment link sent via WhatsApp to {guardian.phone_normalised}")
        
        return msg_id, success

    @classmethod
    def _build_whatsapp_message(cls, payment_link, language='english'):
        """Build WhatsApp message with payment link."""
        student_name = f"{payment_link.student.first_name} {payment_link.student.last_name}"
        templates = {
            'english': (
                f"💳 *Secure Payment Link*\n\n"
                f"Student: {student_name}\n"
                f"Amount Due: UGX {payment_link.amount:,}\n"
                f"Valid Until: {payment_link.expires_at.strftime('%d %b %Y %I:%M %p')}\n\n"
                f"Click to pay via Mobile Money:\n"
                f"{payment_link.full_url}\n\n"
                f"✅ Secure & instant\n"
                f"✅ Receipt sent automatically\n"
                f"✅ One-time use only\n\n"
                f"For assistance: Reply HELP\n"
                f"— {payment_link.school.name}"
            ),
            'luganda': (
                f"💳 *Link y'Okusasula Etebenkevu*\n\n"
                f"Omwana: {student_name}\n"
                f"Ssente: UGX {payment_link.amount:,}\n"
                f"Eggwayo: {payment_link.expires_at.strftime('%d %b %Y %I:%M %p')}\n\n"
                f"Nyiga wano okusasula na Mobile Money:\n"
                f"{payment_link.full_url}\n\n"
                f"✅ Tebenkevu era mangu\n"
                f"✅ Receipt eweerezebwa amangu\n"
                f"✅ Okozesa lumu lwokka\n\n"
                f"Obuyambi: Wandiika HELP\n"
                f"— {payment_link.school.name}"
            )
        }
        
        return templates.get(language.lower(), templates['english'])

    @classmethod
    def validate_and_get_link(cls, token):
        """
        Validate token and return active link.
        
        Args:
            token: Payment link token
            
        Returns:
            PaymentLink instance or None
        """
        try:
            link = PaymentLink.all_objects.select_related(
                'student',
                'fee_record',
                'school'
            ).get(token=token)
            
            # Check expiry
            if link.is_expired and link.status == 'active':
                link.mark_expired()
                return None
            
            # Check if usable
            if not link.is_usable:
                return None
            
            # Increment access counter
            link.increment_access()
            
            return link
            
        except PaymentLink.DoesNotExist:
            return None

    @classmethod
    @transaction.atomic
    def mark_link_used(cls, link, payment):
        """
        Mark link as used after successful payment.
        
        Args:
            link: PaymentLink instance
            payment: Payment instance
        """
        link.mark_used(payment)
        logger.info(
            f"Payment link {link.token[:8]}... marked as used - "
            f"Payment: UGX {payment.amount:,}"
        )

    @classmethod
    def expire_old_links(cls):
        """
        Celery task: Mark expired links.
        Runs hourly via Celery beat.
        """
        now = timezone.now()
        expired = PaymentLink.all_objects.filter(
            status='active',
            expires_at__lt=now
        )
        
        count = expired.update(status='expired')
        
        if count > 0:
            logger.info(f"Marked {count} payment links as expired")
        
        return count

    @classmethod
    def cancel_link(cls, link, cancelled_by, reason=''):
        """
        Manually cancel a payment link.
        
        Args:
            link: PaymentLink instance
            cancelled_by: User who cancelled
            reason: Cancellation reason
        """
        link.status = 'cancelled'
        link.cancelled_by = cancelled_by
        link.cancelled_at = timezone.now()
        if reason:
            link.description += f" [Cancelled: {reason}]"
        link.save(update_fields=['status', 'cancelled_by', 'cancelled_at', 'description'])
        
        logger.info(
            f"Payment link cancelled by {cancelled_by.email}: "
            f"{link.token[:8]}... - Reason: {reason}"
        )

    @classmethod
    def get_active_links_for_student(cls, student, term=None):
        """
        Get all active payment links for a student.
        
        Args:
            student: Student instance
            term: Optional AcademicTerm filter
            
        Returns:
            QuerySet of PaymentLink
        """
        qs = PaymentLink.all_objects.filter(
            student=student,
            status='active'
        ).order_by('-created_at')
        
        if term:
            qs = qs.filter(fee_record__academic_term=term)
        
        return qs
