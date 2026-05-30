"""
Messaging services.
WhatsApp Cloud API integration.
Africa's Talking SMS fallback.
Inbound command processor.
"""
import logging
import requests
from django.conf import settings
from django.utils import timezone

logger = logging.getLogger('messaging')


class WhatsAppService:
    """
    US-032–040: WhatsApp Cloud API via Meta Business Manager.
    All templates must be Meta-approved before use.
    """
    BASE_URL = settings.WHATSAPP_API_URL
    PHONE_ID = settings.WHATSAPP_PHONE_NUMBER_ID
    TOKEN = None  # Loaded dynamically per request

    @classmethod
    def send_template_message(cls, *, to_phone, template_name, language='en',
                               components=None, school=None):
        """
        Send a Meta-approved WhatsApp template message.
        Returns (whatsapp_message_id, success_bool).
        """
        # Normalise phone
        phone = cls._normalise_phone(to_phone)

        payload = {
            'messaging_product': 'whatsapp',
            'to': phone,
            'type': 'template',
            'template': {
                'name': template_name,
                'language': {'code': 'en_US' if language == 'en' else 'lg'},
                'components': components or [],
            },
        }

        try:
            response = requests.post(
                f"{cls.BASE_URL}/{cls.PHONE_ID}/messages",
                headers={
                    'Authorization': f'Bearer {settings.WHATSAPP_ACCESS_TOKEN}',
                    'Content-Type': 'application/json',
                },
                json=payload,
                timeout=10,
            )
            response.raise_for_status()
            data = response.json()
            msg_id = data.get('messages', [{}])[0].get('id', '')
            logger.info(f"WhatsApp sent to {phone}: template={template_name} id={msg_id}")
            return msg_id, True
        except requests.RequestException as e:
            logger.error(f"WhatsApp send failed to {phone}: {e}")
            return None, False

    @classmethod
    def send_text_message(cls, *, to_phone, text, school=None):
        """Send a plain text WhatsApp message (for command responses within 24hr window)."""
        phone = cls._normalise_phone(to_phone)
        payload = {
            'messaging_product': 'whatsapp',
            'to': phone,
            'type': 'text',
            'text': {'body': text},
        }
        try:
            response = requests.post(
                f"{cls.BASE_URL}/{cls.PHONE_ID}/messages",
                headers={
                    'Authorization': f'Bearer {settings.WHATSAPP_ACCESS_TOKEN}',
                    'Content-Type': 'application/json',
                },
                json=payload,
                timeout=10,
            )
            response.raise_for_status()
            data = response.json()
            msg_id = data.get('messages', [{}])[0].get('id', '')
            return msg_id, True
        except requests.RequestException as e:
            logger.error(f"WhatsApp text failed to {phone}: {e}")
            return None, False

    @staticmethod
    def _normalise_phone(phone):
        phone = str(phone).strip().replace('+', '').replace(' ', '').replace('-', '')
        if phone.startswith('0'):
            return '256' + phone[1:]
        return phone

    @staticmethod
    def verify_webhook_token(token):
        return token == settings.WHATSAPP_WEBHOOK_VERIFY_TOKEN


class SMSService:
    """
    US-061: Africa's Talking SMS fallback for Uganda.
    Triggered when WhatsApp delivery not confirmed after 15 minutes.
    """

    @classmethod
    def send_sms(cls, *, to_phone, message, school=None):
        """Send SMS via Africa's Talking."""
        try:
            import africastalking
            africastalking.initialize(settings.AT_USERNAME, settings.AT_API_KEY)
            sms = africastalking.SMS
            # Truncate to 160 chars for single SMS
            message = message[:160]
            response = sms.send(message, [to_phone], sender_id=settings.AT_SENDER_ID)
            recipients = response.get('SMSMessageData', {}).get('Recipients', [])
            if recipients and recipients[0].get('status') == 'Success':
                logger.info(f"SMS sent to {to_phone}")
                return True
            else:
                logger.error(f"SMS failed to {to_phone}: {response}")
                return False
        except Exception as e:
            logger.error(f"SMS error to {to_phone}: {e}")
            return False


class InboundCommandProcessor:
    """
    US-033: BALANCE — fee balance inquiry.
    US-034: RECEIPT — payment receipt for a date.
    US-036: HELP — list of commands.
    US-038: PLAN — request a payment plan.
    US-052: ABSENT — pre-notify absence.
    """

    COMMANDS = ['BALANCE', 'RECEIPT', 'HELP', 'PLAN', 'ABSENT']

    @classmethod
    def parse_command(cls, text):
        """Parse raw message into (command, args)."""
        text = text.strip().upper()
        parts = text.split()
        if not parts:
            return 'UNKNOWN', {}
        cmd = parts[0]
        if cmd not in cls.COMMANDS:
            return 'UNKNOWN', {}
        args = {}
        if cmd == 'RECEIPT' and len(parts) > 1:
            args['date'] = parts[1]
        if cmd == 'ABSENT' and len(parts) >= 2:
            args['date'] = parts[1]
            args['reason'] = ' '.join(parts[2:]) if len(parts) > 2 else ''
        return cmd, args

    @classmethod
    def process(cls, inbound_message):
        """Process a parsed inbound command and send a response."""
        cmd = inbound_message.command
        phone = inbound_message.from_phone
        school = inbound_message.school

        if cmd == 'BALANCE':
            cls._handle_balance(phone, school)
        elif cmd == 'RECEIPT':
            args = inbound_message.command_args or {}
            cls._handle_receipt(phone, school, args.get('date'))
        elif cmd == 'HELP':
            cls._handle_help(phone, school)
        elif cmd == 'PLAN':
            cls._handle_plan(phone, school)
        elif cmd == 'ABSENT':
            args = inbound_message.command_args or {}
            cls._handle_absent(phone, school, args.get('date'), args.get('reason', ''))
        else:
            cls._handle_unknown(phone, school)

        inbound_message.processed = True
        inbound_message.response_sent = True
        inbound_message.save(update_fields=['processed', 'response_sent'])

    @classmethod
    def _handle_balance(cls, phone, school):
        """US-033: Respond within 5 seconds. Handles multiple children."""
        from students.models import Guardian
        guardians = Guardian.objects.filter(phone_normalised=phone).select_related(
            'student', 'student__current_class'
        )
        if not guardians.exists():
            WhatsAppService.send_text_message(
                to_phone=phone,
                text=(
                    "Your number is not registered in our system. "
                    "Please contact the school office to register. "
                    "Reply HELP for more information."
                )
            )
            return

        lines = ["📚 *SchoolBridge Fee Balance*\n"]
        current_term = school.terms.filter(is_current=True).first() if school else None

        for g in guardians:
            student = g.student
            if current_term:
                from payments.models import FeeRecord
                try:
                    fr = FeeRecord.all_objects.get(student=student, academic_term=current_term)
                    status_icon = "✅" if fr.is_fully_paid else "⚠️"
                    lines.append(
                        f"{status_icon} *{student.get_full_name()}*\n"
                        f"   Class: {student.current_class.name if student.current_class else 'N/A'}\n"
                        f"   Total: UGX {fr.total_amount:,}\n"
                        f"   Paid: UGX {fr.amount_paid:,}\n"
                        f"   Balance: UGX {fr.balance:,}\n"
                    )
                except FeeRecord.DoesNotExist:
                    lines.append(f"• *{student.get_full_name()}*: No fee record for current term.\n")
            else:
                lines.append(f"• *{student.get_full_name()}*: No active term found.\n")

        lines.append("\nReply HELP for more commands.")
        WhatsAppService.send_text_message(to_phone=phone, text='\n'.join(lines))

    @classmethod
    def _handle_receipt(cls, phone, school, date_str=None):
        """US-034: Send payment receipts. Optionally filtered by date."""
        from students.models import Guardian
        from payments.models import Payment
        guardians = Guardian.objects.filter(phone_normalised=phone).select_related('student')
        if not guardians.exists():
            WhatsAppService.send_text_message(to_phone=phone, text="Number not registered. Reply HELP.")
            return

        student_ids = [g.student_id for g in guardians]
        qs = Payment.all_objects.filter(
            student_id__in=student_ids, status='completed', is_reversed=False
        ).order_by('-payment_date')

        if date_str:
            try:
                from datetime import datetime
                date = datetime.strptime(date_str, '%Y-%m-%d').date()
                qs = qs.filter(payment_date__date=date)
            except ValueError:
                WhatsAppService.send_text_message(
                    to_phone=phone,
                    text="Invalid date format. Use: RECEIPT YYYY-MM-DD"
                )
                return

        payments = qs[:10]
        if not payments:
            WhatsAppService.send_text_message(
                to_phone=phone,
                text="No payments found." + (f" for {date_str}" if date_str else "")
            )
            return

        lines = ["🧾 *Payment Receipts*\n"]
        for p in payments:
            lines.append(
                f"• {p.payment_date.strftime('%d %b %Y')} — UGX {p.amount:,} "
                f"via {p.get_method_display()}"
            )
        WhatsAppService.send_text_message(to_phone=phone, text='\n'.join(lines))

    @classmethod
    def _handle_help(cls, phone, school):
        """US-036: Help menu. English default."""
        help_text = (
            "📱 *SchoolBridge Commands*\n\n"
            "• BALANCE — Check your child's fee balance\n"
            "• RECEIPT — View recent payments\n"
            "• RECEIPT 2024-01-15 — Payments on a specific date\n"
            "• ABSENT 2024-01-15 Sick — Notify absence in advance\n"
            "• PLAN — Request a payment plan\n"
            "• HELP — Show this menu\n\n"
            "For assistance, contact the school office."
        )
        WhatsAppService.send_text_message(to_phone=phone, text=help_text)

    @classmethod
    def _handle_plan(cls, phone, school):
        """US-038: Payment plan request — notify Bursar for follow-up."""
        from students.models import Guardian
        from notifications.services import NotificationService
        guardians = Guardian.objects.filter(phone_normalised=phone).select_related('student')
        if not guardians.exists():
            WhatsAppService.send_text_message(to_phone=phone, text="Number not registered. Reply HELP.")
            return

        student_names = ', '.join(g.student.get_full_name() for g in guardians)
        # Notify Bursar (US-038)
        if school:
            NotificationService.notify_role(
                school=school,
                role='bursar',
                message=f"Payment plan requested by guardian ({phone}) for: {student_names}",
                notification_type='PAYMENT_PLAN_REQUEST',
            )
        WhatsAppService.send_text_message(
            to_phone=phone,
            text=(
                "✅ Your payment plan request has been received.\n"
                "Our bursar will contact you within 1 business day.\n"
                "Thank you."
            )
        )

    @classmethod
    def _handle_absent(cls, phone, school, date_str, reason):
        """US-052: Parent pre-notifies absence. Marks as excused in system."""
        from students.models import Guardian
        guardians = Guardian.objects.filter(
            phone_normalised=phone, is_primary=True
        ).select_related('student')
        if not guardians.exists():
            WhatsAppService.send_text_message(to_phone=phone, text="Number not registered. Reply HELP.")
            return

        for g in guardians:
            student = g.student
            if date_str:
                try:
                    from datetime import datetime
                    absence_date = datetime.strptime(date_str, '%Y-%m-%d').date()
                    from attendance.services import AttendanceService
                    AttendanceService.mark_pre_excused(student, absence_date, reason)
                except (ValueError, Exception) as e:
                    logger.warning(f"ABSENT command error for {student}: {e}")

        WhatsAppService.send_text_message(
            to_phone=phone,
            text=f"✅ Absence noted for {date_str or 'the specified date'}. Thank you."
        )

    @classmethod
    def _handle_unknown(cls, phone, school):
        WhatsAppService.send_text_message(
            to_phone=phone,
            text="Sorry, I didn't understand that command. Reply HELP for a list of commands."
        )
