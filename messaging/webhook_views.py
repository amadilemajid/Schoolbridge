"""
WhatsApp Cloud API webhook handler.
US-033: Inbound commands (BALANCE, RECEIPT, HELP, PLAN, ABSENT).
US-039: Delivery status updates (delivered, read, failed).
US-061: Automatic SMS fallback triggered on 'failed' delivery status for
        transactional messages (payment_receipt, absence_alert, fee_reminder).

FIXES (production-critical):
  FIX-1: from_phone normalisation — Meta omits the leading '+', so we add it
          before computing SHA-256 so it matches Guardian.phone_hash.
  FIX-2: 'button' message type — template quick-reply clicks (msg.button.text /
          msg.button.payload) are now resolved to text commands.
  FIX-3: 'interactive' list_reply — menu list selections (interactive.list_reply.id
          / .title) are now resolved to text commands alongside button_reply.
  FIX-4: Delivery 'failed' status now triggers immediate SMS fallback for all
          transactional MessageLog entries where is_fallback=False.
"""
import json
import logging
import hashlib

from django.conf import settings
from django.http import JsonResponse, HttpResponse
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator

logger = logging.getLogger('messaging')

# Template types that MUST be delivered — fallback to SMS immediately on failure
_TRANSACTIONAL_TYPES = {
    'payment_receipt',
    'absence_alert',
    'fee_reminder',
    'daily_digest',
    'report_card_ready',
    'payment_reversal',
}


def _normalise_from_phone(raw: str) -> str:
    """
    FIX-1: Meta Cloud API sends phone numbers WITHOUT leading '+' (e.g. '256701234567').
    We normalise to E.164 (+256701234567) so SHA-256 hash matches Guardian.phone_hash
    which is always computed from phone_normalised = +256XXXXXXXXX.
    """
    raw = raw.strip()
    if not raw.startswith('+'):
        raw = '+' + raw
    return raw


@method_decorator(csrf_exempt, name='dispatch')
class WhatsAppWebhookView(View):

    def get(self, request):
        """Meta webhook verification handshake."""
        mode = request.GET.get('hub.mode')
        token = request.GET.get('hub.verify_token')
        challenge = request.GET.get('hub.challenge')
        if mode == 'subscribe' and token == settings.WHATSAPP_WEBHOOK_VERIFY_TOKEN:
            logger.info("WhatsApp webhook verified")
            return HttpResponse(challenge, content_type='text/plain')
        return HttpResponse('Forbidden', status=403)

    def post(self, request):
        """Process inbound messages and delivery status updates."""
        app_secret = getattr(settings, 'WHATSAPP_APP_SECRET', None)

        # SEC-003: Enforce HMAC validation in production.
        if not app_secret:
            if not settings.DEBUG:
                logger.error(
                    "WHATSAPP_APP_SECRET is not configured. "
                    "All inbound webhook requests are rejected in production."
                )
                return HttpResponse('Forbidden', status=403)
        else:
            import hmac as _hmac
            signature = request.META.get('HTTP_X_HUB_SIGNATURE_256', '')
            if not signature:
                logger.warning("Missing X-Hub-Signature-256 header")
                return HttpResponse('Forbidden', status=403)

            try:
                sha_name, signature_hash = signature.split('=', 1)
                if sha_name != 'sha256':
                    raise ValueError("Unexpected algorithm")
            except ValueError:
                logger.warning("Unsupported signature format")
                return HttpResponse('Forbidden', status=403)

            mac = _hmac.new(
                app_secret.encode('utf-8'),
                msg=request.body,
                digestmod=hashlib.sha256,
            )
            if not _hmac.compare_digest(mac.hexdigest(), signature_hash):
                logger.warning("Invalid webhook signature — request rejected")
                return HttpResponse('Forbidden', status=403)

        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({'error': 'Invalid JSON'}, status=400)

        try:
            entry = data.get('entry', [{}])[0]
            changes = entry.get('changes', [{}])[0]
            value = changes.get('value', {})

            # Handle inbound messages
            messages = value.get('messages', [])
            for msg in messages:
                self._handle_inbound_message(msg, value)

            # Handle status updates (US-039)
            statuses = value.get('statuses', [])
            for status_update in statuses:
                self._handle_status_update(status_update)

        except Exception as e:
            logger.exception(f"WhatsApp webhook processing error: {e}")

        # Always return 200 — Meta will retry on non-200
        return JsonResponse({'status': 'ok'}, status=200)

    def _handle_inbound_message(self, msg, value):
        """
        Parse and queue processing for inbound WhatsApp message.

        Supports:
          - text      → plain text body
          - button    → template quick-reply (FIX-2: previously ignored)
          - interactive → button_reply OR list_reply (FIX-2/3)
        """
        from messaging.models import InboundMessage
        from messaging.tasks import process_inbound_command
        from messaging.services import InboundCommandProcessor
        from students.models import Guardian

        msg_id = msg.get('id', '')
        raw_from = msg.get('from', '')
        msg_type = msg.get('type', '')
        text = ''

        # FIX-2 & FIX-3: Extract text from all supported inbound message types
        if msg_type == 'text':
            text = msg.get('text', {}).get('body', '').strip()

        elif msg_type == 'button':
            # Template quick-reply button click — Meta sends msg.button.text (the button label)
            # and msg.button.payload (the developer-defined payload, usually the command).
            # Prefer payload as it is machine-readable; fall back to text.
            btn = msg.get('button', {})
            text = (btn.get('payload') or btn.get('text') or '').strip()
            logger.info(f"WhatsApp button reply: payload={btn.get('payload')!r}, text={btn.get('text')!r}")

        elif msg_type == 'interactive':
            interactive = msg.get('interactive', {})
            interactive_type = interactive.get('type', '')

            if interactive_type == 'button_reply':
                # Interactive button click (non-template) — title is human-readable
                reply = interactive.get('button_reply', {})
                # button_reply.id is the machine-readable payload; title is the label
                text = (reply.get('id') or reply.get('title') or '').strip()

            elif interactive_type == 'list_reply':
                # FIX-3: List menu selection — id is the row_id (command), title is display
                reply = interactive.get('list_reply', {})
                text = (reply.get('id') or reply.get('title') or '').strip()
                logger.info(
                    f"WhatsApp list_reply: id={reply.get('id')!r}, title={reply.get('title')!r}"
                )

        if not text:
            logger.debug(f"Ignoring WhatsApp message id={msg_id!r} type={msg_type!r} — no actionable text")
            return

        # Avoid duplicate processing
        if InboundMessage.objects.filter(whatsapp_message_id=msg_id).exists():
            logger.debug(f"Duplicate inbound message {msg_id} — skipping")
            return

        # Parse command
        command, args = InboundCommandProcessor.parse_command(text)

        # FIX-1: Normalise phone BEFORE hashing — Meta omits leading '+'
        from_phone_normalised = _normalise_from_phone(raw_from)
        phone_hash = hashlib.sha256(from_phone_normalised.encode()).hexdigest()

        school = None
        guardian = Guardian.objects.filter(phone_hash=phone_hash).select_related(
            'student__school'
        ).first()
        if guardian:
            school = guardian.student.school

        if not school:
            logger.warning(
                f"Inbound WhatsApp from {from_phone_normalised!r} — no matching Guardian found. "
                f"Command will be processed without school context."
            )

        inbound = InboundMessage.objects.create(
            school=school,
            from_phone=from_phone_normalised,  # store normalised phone
            raw_message=text,
            command=command,
            command_args=args,
            whatsapp_message_id=msg_id,
        )

        # Process asynchronously
        process_inbound_command.delay(str(inbound.id))

    def _handle_status_update(self, status_data):
        """
        US-039: Update MessageLog with delivery status.
        FIX-4: Immediately trigger SMS fallback for transactional messages on 'failed' status,
                instead of waiting 15 min for the scheduled Celery check.
        """
        from messaging.models import MessageLog
        from messaging.services import WhatsAppService
        from django.utils import timezone

        msg_id = status_data.get('id', '')
        new_status = status_data.get('status', '')  # sent, delivered, read, failed
        errors = status_data.get('errors', []) or []

        status_map = {
            'sent': 'sent',
            'delivered': 'delivered',
            'read': 'read',
            'failed': 'failed',
        }
        mapped = status_map.get(new_status)
        if not mapped or not msg_id:
            return

        error_message = ''
        if errors:
            first_error = errors[0]
            error_message = first_error.get('message') or first_error.get('title') or ''
            if first_error.get('code') == 131031:
                WhatsAppService.pause_for_lock(
                    reason=error_message or 'Business Account locked',
                    payload={
                        'message_id': msg_id,
                        'status_data': status_data,
                    },
                )

        update_fields = {
            'status': mapped,
            'status_updated_at': timezone.now(),
        }
        if error_message:
            update_fields['error_message'] = error_message
        if mapped == 'delivered':
            update_fields['delivered_at'] = timezone.now()

        updated_count = MessageLog.all_objects.filter(
            whatsapp_message_id=msg_id
        ).update(**update_fields)

        # FIX-4: Immediate SMS fallback on hard failure for transactional messages
        if mapped == 'failed' and updated_count:
            self._trigger_sms_fallback_on_failure(msg_id, error_message)

    def _trigger_sms_fallback_on_failure(self, whatsapp_message_id: str, error_message: str):
        """
        FIX-4: When Meta delivers a 'failed' status for a transactional WhatsApp message,
        immediately queue an SMS fallback via Africa's Talking rather than waiting 15 min
        for the Celery scheduled check. Non-transactional messages (e.g. balance_response,
        simulation) are intentionally excluded from this path.
        """
        from messaging.models import MessageLog
        from messaging.tasks import check_whatsapp_delivery_and_fallback

        logs = MessageLog.all_objects.filter(
            whatsapp_message_id=whatsapp_message_id,
            channel='whatsapp',
            is_fallback=False,
            template_type__in=_TRANSACTIONAL_TYPES,
        )
        for log in logs:
            logger.warning(
                f"WhatsApp delivery FAILED for {log.recipient_phone!r} "
                f"(msg_id={whatsapp_message_id!r}, type={log.template_type!r}). "
                f"Error: {error_message!r}. Triggering immediate SMS fallback."
            )
            # Reuse the existing fallback task — countdown=0 means run now
            check_whatsapp_delivery_and_fallback.apply_async(
                args=[str(log.id)],
                countdown=0,
            )


@method_decorator(csrf_exempt, name='dispatch')
class WhatsAppWebhookVerifyView(WhatsAppWebhookView):
    pass
