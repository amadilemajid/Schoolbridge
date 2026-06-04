"""
WhatsApp Cloud API webhook handler.
US-033: Inbound commands (BALANCE, RECEIPT, HELP, PLAN, ABSENT).
US-039: Delivery status updates (delivered, read, failed).
"""
import json
import logging
from django.conf import settings
from django.http import JsonResponse, HttpResponse
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator

logger = logging.getLogger('messaging')


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
        """Parse and queue processing for inbound WhatsApp message."""
        from messaging.models import InboundMessage
        from messaging.tasks import process_inbound_command
        from messaging.services import InboundCommandProcessor
        from students.models import Guardian

        msg_id = msg.get('id', '')
        from_phone = msg.get('from', '')
        msg_type = msg.get('type', '')
        text = ''

        if msg_type == 'text':
            text = msg.get('text', {}).get('body', '').strip()
        elif msg_type == 'interactive':
            text = msg.get('interactive', {}).get('button_reply', {}).get('title', '')

        if not text:
            return

        # Avoid duplicate processing
        if InboundMessage.objects.filter(whatsapp_message_id=msg_id).exists():
            return

        # Parse command
        command, args = InboundCommandProcessor.parse_command(text)

        # Try to identify school from guardian phone
        school = None
        guardian = Guardian.objects.filter(phone_normalised=from_phone).select_related(
            'student__school'
        ).first()
        if guardian:
            school = guardian.student.school

        inbound = InboundMessage.objects.create(
            school=school,
            from_phone=from_phone,
            raw_message=text,
            command=command,
            command_args=args,
            whatsapp_message_id=msg_id,
        )

        # Process asynchronously
        process_inbound_command.delay(str(inbound.id))

    def _handle_status_update(self, status_data):
        """US-039: Update MessageLog with delivery status."""
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

        MessageLog.all_objects.filter(whatsapp_message_id=msg_id).update(**update_fields)


@method_decorator(csrf_exempt, name='dispatch')
class WhatsAppWebhookVerifyView(WhatsAppWebhookView):
    pass
