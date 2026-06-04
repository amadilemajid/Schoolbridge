"""
Messaging services.
WhatsApp Cloud API integration.
Africa's Talking SMS fallback.
Inbound command processor.
"""
import logging
import requests
from django.conf import settings
from django.core.cache import cache
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
    LOCK_CACHE_KEY = 'whatsapp_business_locked'
    LOCK_REASON_CACHE_KEY = 'whatsapp_business_locked_reason'
    LOCK_ALERT_CACHE_KEY = 'whatsapp_business_locked_alert_sent'

    @classmethod
    def is_paused(cls):
        return bool(cache.get(cls.LOCK_CACHE_KEY))

    @classmethod
    def pause_for_lock(cls, reason=None, payload=None, ttl=86400):
        previous_state = cache.get(cls.LOCK_CACHE_KEY)
        cache.set(cls.LOCK_CACHE_KEY, True, timeout=ttl)
        if reason:
            cache.set(cls.LOCK_REASON_CACHE_KEY, reason, timeout=ttl)

        if not cache.get(cls.LOCK_ALERT_CACHE_KEY):
            cache.add(cls.LOCK_ALERT_CACHE_KEY, True, timeout=ttl)
            from notifications.services import send_admin_alert

            message = 'WhatsApp sending paused because the business account is locked.'
            if reason:
                message = f'{message} Reason: {reason}'
            send_admin_alert(
                alert_type='WHATSAPP_BUSINESS_LOCKED',
                message=message,
                payload=payload or {},
            )

        if not previous_state:
            logger.error(
                f"WhatsApp sending paused due to locked business account: {reason or 'no details provided'}"
            )

    @classmethod
    def clear_pause(cls):
        cache.delete(cls.LOCK_CACHE_KEY)
        cache.delete(cls.LOCK_REASON_CACHE_KEY)
        cache.delete(cls.LOCK_ALERT_CACHE_KEY)

    @classmethod
    def queue_whatsapp_message(cls, *, school, recipient_phone, message_body, template_type='queued', student=None, error_message='WhatsApp sending paused because the business account is locked.'):
        from messaging.models import MessageLog

        return MessageLog.all_objects.create(
            school=school,
            student=student,
            recipient_phone=recipient_phone,
            channel='whatsapp',
            template_type=template_type,
            message_body=message_body,
            status='queued',
            error_message=error_message,
        )

    @classmethod
    def send_template_message(cls, *, to_phone, template_name, language='en',
                               components=None, school=None):
        """
        Send a Meta-approved WhatsApp template message.
        Returns (whatsapp_message_id, success_bool).
        """
        if cls.is_paused():
            logger.warning(f"WhatsApp paused; skipping template send to {to_phone}")
            return None, False
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
        except requests.HTTPError as e:
            response = getattr(e, 'response', None)
            body = response.text if response is not None else str(e)
            logger.error(
                f"WhatsApp send failed to {phone}: status={getattr(response, 'status_code', 'unknown')} "
                f"phone_id={cls.PHONE_ID} body={body}"
            )
            return None, False
        except requests.RequestException as e:
            logger.error(f"WhatsApp send failed to {phone}: phone_id={cls.PHONE_ID} error={e}")
            return None, False

    @classmethod
    def send_text_message(cls, *, to_phone, text, school=None):
        """Send a plain text WhatsApp message (for command responses within 24hr window)."""
        if cls.is_paused():
            logger.warning(f"WhatsApp paused; skipping text send to {to_phone}")
            return None, False
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
        except requests.HTTPError as e:
            response = getattr(e, 'response', None)
            body = response.text if response is not None else str(e)
            logger.error(
                f"WhatsApp text failed to {phone}: status={getattr(response, 'status_code', 'unknown')} "
                f"phone_id={cls.PHONE_ID} body={body}"
            )
            return None, False
        except requests.RequestException as e:
            logger.error(f"WhatsApp text failed to {phone}: phone_id={cls.PHONE_ID} error={e}")
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


class MetaTemplateService:
    """
    US-040: Submit WhatsApp message templates to Meta Business Manager API
    for review and approval. Polls approval status and syncs is_meta_approved.

    Meta Graph API reference:
    POST /v19.0/{waba_id}/message_templates
    GET  /v19.0/{waba_id}/message_templates?name={name}
    """
    BASE_URL = settings.WHATSAPP_API_URL
    WABA_ID = getattr(settings, 'WHATSAPP_BUSINESS_ACCOUNT_ID', '')

    # Template category mapping — US-040: all automated messages = UTILITY
    CATEGORY_MAP = {
        'fee_reminder': 'UTILITY',
        'payment_receipt': 'UTILITY',
        'payment_reversal': 'UTILITY',
        'report_card_ready': 'UTILITY',
        'absence_alert': 'UTILITY',
        'broadcast': 'MARKETING',
        'balance_response': 'UTILITY',
        'receipt_response': 'UTILITY',
        'help_response': 'UTILITY',
        'plan_notification': 'UTILITY',
        'number_changed': 'UTILITY',
        'daily_digest': 'UTILITY',
    }

    @classmethod
    def _headers(cls):
        return {
            'Authorization': f'Bearer {settings.WHATSAPP_ACCESS_TOKEN}',
            'Content-Type': 'application/json',
        }

    @classmethod
    def submit_template(cls, template):
        """
        Submit a MessageTemplate to Meta for approval.
        Returns (meta_template_name, success, error_message).
        Sets template.meta_submission_status to 'PENDING' on success.
        """
        if not cls.WABA_ID:
            return None, False, 'WHATSAPP_BUSINESS_ACCOUNT_ID not configured in settings.'

        category = cls.CATEGORY_MAP.get(template.template_type, 'UTILITY')
        lang_code = 'en_US' if template.language == 'en' else 'lg'

        # Build components: single BODY component with the template text
        # Variables in the body use {{1}}, {{2}} format required by Meta
        body_text = cls._convert_placeholders(template.body)
        components = [{
            'type': 'BODY',
            'text': body_text,
        }]

        payload = {
            'name': template.meta_template_name or cls._build_meta_name(template),
            'category': category,
            'language': lang_code,
            'components': components,
        }

        try:
            response = requests.post(
                f"{cls.BASE_URL}/{cls.WABA_ID}/message_templates",
                headers=cls._headers(),
                json=payload,
                timeout=15,
            )
            data = response.json()

            if response.status_code in (200, 201):
                meta_name = data.get('name', payload['name'])
                logger.info(
                    f"Template '{meta_name}' submitted to Meta for approval "
                    f"(id={data.get('id')}, status={data.get('status')})"
                )
                return meta_name, True, None
            else:
                error = data.get('error', {}).get('message', str(data))
                logger.error(f"Meta template submission failed: {error}")
                return None, False, error

        except requests.RequestException as exc:
            logger.error(f"Meta template submission request failed: {exc}")
            return None, False, str(exc)

    @classmethod
    def sync_approval_status(cls, template):
        """
        Poll Meta API for template approval status.
        Updates template.is_meta_approved and template.meta_submission_status.
        Called by Celery beat daily or after webhook notification.
        Returns (status_string, is_approved).
        """
        if not cls.WABA_ID or not template.meta_template_name:
            return 'UNKNOWN', False

        try:
            response = requests.get(
                f"{cls.BASE_URL}/{cls.WABA_ID}/message_templates",
                headers=cls._headers(),
                params={'name': template.meta_template_name, 'fields': 'name,status,rejected_reason'},
                timeout=10,
            )
            data = response.json()
            templates = data.get('data', [])
            if not templates:
                return 'NOT_FOUND', False

            meta_status = templates[0].get('status', 'UNKNOWN').upper()
            rejected_reason = templates[0].get('rejected_reason', '')

            is_approved = (meta_status == 'APPROVED')
            update_fields = ['is_meta_approved']
            template.is_meta_approved = is_approved

            # Store rejection reason if present
            if hasattr(template, 'meta_rejection_reason') and rejected_reason:
                template.meta_rejection_reason = rejected_reason
                update_fields.append('meta_rejection_reason')
            if hasattr(template, 'meta_submission_status'):
                template.meta_submission_status = meta_status
                update_fields.append('meta_submission_status')

            template.save(update_fields=update_fields)

            logger.info(
                f"Template '{template.meta_template_name}' Meta status: {meta_status}"
                + (f" | Reason: {rejected_reason}" if rejected_reason else "")
            )
            return meta_status, is_approved

        except requests.RequestException as exc:
            logger.error(f"Meta template status poll failed: {exc}")
            return 'ERROR', False

    @staticmethod
    def _convert_placeholders(body_text):
        """
        Convert Django-style {{variable}} to Meta-style {{1}}, {{2}}.
        Extracts variables in order of appearance and numbers them.
        """
        import re
        counter = [0]
        seen = {}

        def replace(match):
            var = match.group(1)
            if var not in seen:
                counter[0] += 1
                seen[var] = counter[0]
            return '{{' + str(seen[var]) + '}}'

        return re.sub(r'\{\{(\w+)\}\}', replace, body_text)

    @staticmethod
    def _build_meta_name(template):
        """Generate a valid Meta template name: lowercase, underscores, max 512 chars."""
        school_slug = (
            template.school.slug if template.school else 'schoolbridge'
        )
        name = f"sb_{school_slug}_{template.template_type}_{template.language}"
        return name[:512].replace('-', '_').lower()


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

    COMMANDS = [
        'BALANCE', 'RECEIPT', 'HELP', 'PLAN', 'ABSENT',
        'RESULTS', 'ATTEND', 'TIMETABLE', 'MENU', 'LUGANDA', 'ENGLISH',
    ]

    @classmethod
    def parse_command(cls, text):
        """
        Parse raw message into (command, args).
        
        US-A03: Supports both text commands and numeric shortcuts (1-7).
        Numeric shortcuts map to frequently used commands:
        1=BALANCE, 2=RESULTS, 3=ATTEND, 4=RECEIPT, 5=TIMETABLE, 6=PLAN, 7=ABSENT
        
        Args:
            text: Raw message text from user
        
        Returns:
            tuple: (command_str, args_dict)
                - command_str: Parsed command or 'UNKNOWN'
                - args_dict: Extracted arguments (e.g. {'date': '2024-01-15'})
        """
        text = text.strip().upper()
        parts = text.split()
        if not parts:
            return 'UNKNOWN', {}
        
        cmd = parts[0]
        
        # US-A03: Numeric shortcuts (1-7)
        number_map = {
            '1': 'BALANCE',
            '2': 'RESULTS',
            '3': 'ATTEND',
            '4': 'RECEIPT',
            '5': 'TIMETABLE',
            '6': 'PLAN',
            '7': 'ABSENT',
        }
        cmd = number_map.get(cmd, cmd)
        
        # Check if command is valid
        if cmd not in cls.COMMANDS:
            return 'UNKNOWN', {}
        
        # Extract arguments for specific commands
        args = {}
        
        # RECEIPT command: optional date argument
        # Format: "RECEIPT 2024-01-15" or "4 2024-01-15"
        if cmd == 'RECEIPT' and len(parts) > 1:
            args['date'] = parts[1]
        
        # ABSENT command: date + reason
        # Format: "ABSENT 2024-01-15 Sick" or "7 2024-01-15 Sick"
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
        elif cmd == 'RESULTS':
            cls._handle_results(phone, school)
        elif cmd == 'ATTEND':
            cls._handle_attend(phone, school)
        elif cmd == 'TIMETABLE':
            cls._handle_timetable(phone, school)
        elif cmd == 'MENU':
            cls._handle_menu(phone, school)
        elif cmd == 'LUGANDA':
            cls._handle_language(phone, school, 'lg')
        elif cmd == 'ENGLISH':
            cls._handle_language(phone, school, 'en')
        else:
            cls._handle_unknown(phone, school)

        inbound_message.processed = True
        inbound_message.response_sent = True
        inbound_message.save(update_fields=['processed', 'response_sent'])

    @classmethod
    def _normalise_inbound_phone(cls, phone):
        """Normalise WhatsApp inbound phone to match Guardian.phone_normalised (+256...)."""
        phone = str(phone).strip()
        if not phone.startswith('+'):
            phone = '+' + phone
        return phone

    @classmethod
    def _send_or_queue_reply(cls, *, phone, school, text, template_type, student=None):
        if WhatsAppService.is_paused():
            WhatsAppService.queue_whatsapp_message(
                school=school,
                student=student,
                recipient_phone=phone,
                message_body=text,
                template_type=template_type,
            )
            logger.warning(f"WhatsApp paused; queued reply {template_type} for {phone}")
            return
        WhatsAppService.send_text_message(to_phone=phone, text=text, school=school)

    @classmethod
    def _handle_balance(cls, phone, school):
        """US-033 + US-C02: Fee balance inquiry with sibling aggregation and bilingual support."""
        from students.models import Guardian
        from messaging.translation_service import TranslationService
        from payments.services import FeeService

        lang = TranslationService.get_language_from_phone(phone)
        phone = cls._normalise_inbound_phone(phone)
        guardians = Guardian.objects.filter(phone_normalised=phone).select_related(
            'student', 'student__current_class'
        )
        if not guardians.exists():
            cls._send_or_queue_reply(
                phone=phone, school=school,
                text=TranslationService.get('balance_not_registered', lang=lang),
                template_type='balance_response',
            )
            return

        lines = [TranslationService.get('balance_header', lang=lang)]
        current_term = school.terms.filter(is_current=True).first() if school else None

        # US-C02: Get first student to check for siblings
        first_guardian = guardians.first()
        first_student = first_guardian.student if first_guardian else None
        
        # Check if sibling aggregation should be shown
        show_sibling_summary = False
        sibling_summary = None
        
        if first_student and current_term:
            sibling_summary = FeeService.get_sibling_balance_summary(first_student, current_term)
            # Show summary if there are siblings and total balance > 0
            if sibling_summary and sibling_summary['sibling_count'] > 1 and sibling_summary['total_balance'] > 0:
                show_sibling_summary = True

        # Show individual student balances
        for g in guardians:
            student = g.student
            if current_term:
                from payments.models import FeeRecord
                try:
                    fr = FeeRecord.all_objects.get(student=student, academic_term=current_term)
                    icon = '✅' if fr.is_fully_paid else '⚠️'
                    lines.append(
                        TranslationService.get(
                            'balance_detail', lang=lang,
                            icon=icon,
                            student_name=student.get_full_name(),
                            class_name=student.current_class.name if student.current_class else 'N/A',
                            total=int(fr.total_amount),
                            paid=int(fr.amount_paid),
                            balance=int(fr.balance),
                        )
                    )
                except FeeRecord.DoesNotExist:
                    lines.append(
                        TranslationService.get(
                            'balance_no_record', lang=lang,
                            student_name=student.get_full_name()
                        )
                    )
            else:
                lines.append(
                    TranslationService.get(
                        'balance_no_term', lang=lang,
                        student_name=student.get_full_name()
                    )
                )

        # US-C02: Add sibling aggregation summary
        if show_sibling_summary:
            lines.append("\n" + "─" * 30 + "\n")
            lines.append(
                f"👨‍👩‍👧‍👦 *Family Total Balance*\n"
                f"Combined balance for {sibling_summary['sibling_count']} students:\n"
                f"UGX {int(sibling_summary['total_balance']):,}\n"
            )

        lines.append(TranslationService.get('help_suffix', lang=lang))
        cls._send_or_queue_reply(
            phone=phone, school=school,
            text=''.join(lines),
            template_type='balance_response',
        )

    @classmethod
    def _handle_receipt(cls, phone, school, date_str=None):
        """US-034: Payment receipts with bilingual support. Optionally filtered by date."""
        from students.models import Guardian
        from payments.models import Payment
        from messaging.translation_service import TranslationService

        lang = TranslationService.get_language_from_phone(phone)
        phone = cls._normalise_inbound_phone(phone)
        guardians = Guardian.objects.filter(phone_normalised=phone).select_related('student')
        if not guardians.exists():
            cls._send_or_queue_reply(
                phone=phone, school=school,
                text=TranslationService.get('receipt_not_registered', lang=lang),
                template_type='receipt_response',
            )
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
                cls._send_or_queue_reply(
                    phone=phone, school=school,
                    text=TranslationService.get('receipt_invalid_date', lang=lang),
                    template_type='receipt_response',
                )
                return

        payments = qs[:10]
        if not payments:
            date_suffix = TranslationService.get(
                'receipt_date_suffix', lang=lang, date=date_str
            ) if date_str else ''
            cls._send_or_queue_reply(
                phone=phone, school=school,
                text=TranslationService.get(
                    'receipt_none_found', lang=lang, date_suffix=date_suffix
                ),
                template_type='receipt_response',
            )
            return

        lines = [TranslationService.get('receipt_header', lang=lang)]
        for p in payments:
            lines.append(
                TranslationService.get(
                    'receipt_line', lang=lang,
                    date=p.payment_date.strftime('%d %b %Y'),
                    amount=int(p.amount),
                    method=p.get_method_display(),
                )
            )
        cls._send_or_queue_reply(
            phone=phone, school=school,
            text='\n'.join(lines),
            template_type='receipt_response',
        )

    @classmethod
    def _handle_help(cls, phone, school):
        """US-036: Help menu. English default."""
        help_text = (
            "📱 *SchoolBridge Commands*\n\n"
            "• BALANCE — Fee balance\n"
            "• RESULTS — Latest exam results\n"
            "• ATTEND — Attendance rate\n"
            "• TIMETABLE — Class schedule\n"
            "• RECEIPT — Recent payments\n"
            "• RECEIPT 2024-01-15 — Payments on a date\n"
            "• PLAN — Request payment plan\n"
            "• ABSENT 2024-01-15 Sick — Report absence\n"
            "• LUGANDA — Switch to Luganda\n"
            "• ENGLISH — Switch to English\n"
            "• MENU — Show this menu\n\n"
            "For assistance, contact the school office."
        )
        cls._send_or_queue_reply(
            phone=phone,
            school=school,
            text=help_text,
            template_type='help_response',
        )

    @classmethod
    def _handle_plan(cls, phone, school):
        """US-038: Payment plan request — notify Bursar for follow-up."""
        from students.models import Guardian
        from notifications.services import NotificationService
        guardians = Guardian.objects.filter(phone_normalised=phone).select_related('student')
        if not guardians.exists():
            cls._send_or_queue_reply(
                phone=phone,
                school=school,
                text="Number not registered. Reply HELP.",
                template_type='plan_notification',
            )
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
        cls._send_or_queue_reply(
            phone=phone,
            school=school,
            text=(
                "✅ Your payment plan request has been received.\n"
                "Our bursar will contact you within 1 business day.\n"
                "Thank you."
            ),
            template_type='plan_notification',
        )

    @classmethod
    def _handle_absent(cls, phone, school, date_str, reason):
        """US-052: Parent pre-notifies absence. Marks as excused in system."""
        from students.models import Guardian
        guardians = Guardian.objects.filter(
            phone_normalised=phone, is_primary=True
        ).select_related('student')
        if not guardians.exists():
            cls._send_or_queue_reply(
                phone=phone,
                school=school,
                text="Number not registered. Reply HELP.",
                template_type='number_changed',
            )
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

        cls._send_or_queue_reply(
            phone=phone,
            school=school,
            text=f"✅ Absence noted for {date_str or 'the specified date'}. Thank you.",
            template_type='absence_alert',
        )

    @classmethod
    def _handle_results(cls, phone, school):
        """US-A02: Send latest term results to parent with language support."""
        from students.models import Guardian
        from results.models import TermResult
        from messaging.translation_service import TranslationService

        lang = TranslationService.get_language_from_phone(phone)
        phone = cls._normalise_inbound_phone(phone)
        guardians = Guardian.objects.filter(phone_normalised=phone).select_related('student')
        if not guardians.exists():
            cls._send_or_queue_reply(
                phone=phone,
                school=school,
                text=TranslationService.get('not_registered', lang=lang),
                template_type='results_response',
            )
            return

        lines = [TranslationService.get('results_header', lang=lang)]
        for g in guardians:
            student = g.student
            result = TermResult.objects.filter(student=student).order_by('-academic_term__start_date').first()
            if result:
                lines.append(
                    TranslationService.get(
                        'results_detail',
                        lang=lang,
                        student_name=student.get_full_name(),
                        term_name=str(result.academic_term),
                        total_marks=result.total_marks,
                        average_marks=result.average_marks,
                        rank=result.class_rank,
                        total_students=result.total_students,
                        division=result.division if result.division else 'N/A'
                    )
                )
            else:
                lines.append(
                    TranslationService.get(
                        'results_not_available',
                        lang=lang,
                        student_name=student.get_full_name()
                    )
                )

        lines.append(TranslationService.get('help_suffix', lang=lang))
        cls._send_or_queue_reply(
            phone=phone,
            school=school,
            text=''.join(lines),
            template_type='results_response',
        )

    @classmethod
    def _handle_attend(cls, phone, school):
        """US-A04: Send attendance rate to parent with language support."""
        from students.models import Guardian
        from attendance.services import AttendanceService
        from messaging.translation_service import TranslationService

        lang = TranslationService.get_language_from_phone(phone)
        phone = cls._normalise_inbound_phone(phone)
        guardians = Guardian.objects.filter(phone_normalised=phone).select_related('student')
        if not guardians.exists():
            cls._send_or_queue_reply(
                phone=phone,
                school=school,
                text=TranslationService.get('not_registered', lang=lang),
                template_type='attendance_response',
            )
            return

        lines = [TranslationService.get('attend_header', lang=lang)]
        current_term = school.terms.filter(is_current=True).first() if school else None
        for g in guardians:
            student = g.student
            if current_term:
                rate = AttendanceService.get_attendance_rate(student, current_term)
                if rate is not None:
                    icon = '✅' if rate >= 75 else '⚠️'
                    status = TranslationService.get(
                        'attend_status_good' if rate >= 75 else 'attend_status_low',
                        lang=lang
                    )
                    lines.append(
                        TranslationService.get(
                            'attend_detail', lang=lang,
                            icon=icon, student_name=student.get_full_name(),
                            rate=rate, status=status
                        )
                    )
                else:
                    lines.append(
                        TranslationService.get(
                            'attend_no_records', lang=lang,
                            student_name=student.get_full_name()
                        )
                    )
            else:
                lines.append(
                    TranslationService.get(
                        'balance_no_term', lang=lang,
                        student_name=student.get_full_name()
                    )
                )

        lines.append(TranslationService.get('help_suffix', lang=lang))
        cls._send_or_queue_reply(
            phone=phone,
            school=school,
            text=''.join(lines),
            template_type='attendance_response',
        )

    @classmethod
    def _handle_timetable(cls, phone, school):
        """US-A01: Send child's class timetable to parent with language support."""
        from students.models import Guardian
        from messaging.translation_service import TranslationService

        lang = TranslationService.get_language_from_phone(phone)
        phone = cls._normalise_inbound_phone(phone)
        guardians = Guardian.objects.filter(phone_normalised=phone).select_related('student__current_class')
        if not guardians.exists():
            cls._send_or_queue_reply(
                phone=phone,
                school=school,
                text=TranslationService.get('not_registered', lang=lang),
                template_type='timetable_response',
            )
            return

        sent_any = False
        for g in guardians:
            student = g.student
            class_group = student.current_class
            if not class_group:
                continue

            timetable_text = None
            try:
                from schools.models import Timetable
                timetable = Timetable.objects.filter(class_group=class_group, is_active=True).first()
                if timetable:
                    timetable_text = TranslationService.get(
                        'timetable_header',
                        lang=lang,
                        student_name=student.get_full_name(),
                        class_name=class_group.name,
                        content=timetable.content
                    )
            except Exception:
                timetable_text = None

            if timetable_text:
                cls._send_or_queue_reply(
                    phone=phone,
                    school=school,
                    text=timetable_text,
                    template_type='timetable_response',
                    student=student,
                )
            else:
                cls._send_or_queue_reply(
                    phone=phone,
                    school=school,
                    text=TranslationService.get(
                        'timetable_not_available',
                        lang=lang,
                        student_name=student.get_full_name()
                    ),
                    template_type='timetable_response',
                    student=student,
                )
            sent_any = True

        if not sent_any:
            cls._send_or_queue_reply(
                phone=phone,
                school=school,
                text=TranslationService.get('timetable_no_class', lang=lang),
                template_type='timetable_response',
            )

    @classmethod
    def _handle_menu(cls, phone, school):
        """US-A06: Send interactive menu to parent with language support."""
        from messaging.translation_service import TranslationService
        
        # Get user's preferred language
        lang = TranslationService.get_language_from_phone(phone)
        
        # Get translated menu text
        menu_text = TranslationService.get('menu_text', lang=lang)
        
        cls._send_or_queue_reply(
            phone=phone,
            school=school,
            text=menu_text,
            template_type='help_response',
        )

    @classmethod
    def _handle_language(cls, phone, school, lang):
        """US-A05: Switch parent language preference."""
        from students.models import Guardian
        from messaging.translation_service import TranslationService

        # Update guardian language preference
        guardian_fields = {f.name for f in Guardian._meta.fields}
        if 'preferred_language' in guardian_fields:
            Guardian.objects.filter(phone_normalised=phone).update(preferred_language=lang)
        else:
            logger.info('preferred_language field missing on Guardian model; language change not persisted.')

        # Get translated confirmation message
        text = TranslationService.get('language_switched', lang=lang)
        
        cls._send_or_queue_reply(
            phone=phone,
            school=school,
            text=text,
            template_type='help_response',
        )

    @classmethod
    def _handle_unknown(cls, phone, school):
        cls._send_or_queue_reply(
            phone=phone,
            school=school,
            text="Sorry, I didn't understand that command. Reply HELP for a list of commands.",
            template_type='help_response',
        )
