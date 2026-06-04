"""Messaging views — broadcasts, message logs, template management."""
import logging
from django.utils import timezone
from rest_framework import viewsets, generics, status
from rest_framework.views import APIView
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.serializers import Serializer, CharField, ChoiceField, UUIDField
from rest_framework import serializers as drf_serializers

from audit.mixins import AuditMixin
from schools.permissions import IsDirector, IsDirectorOrBursar, IsSchoolStaff
from .models import BroadcastMessage, MessageLog, MessageTemplate, InboundMessage

logger = logging.getLogger('messaging')


class BroadcastSerializer(drf_serializers.ModelSerializer):
    class Meta:
        model = BroadcastMessage
        fields = [
            'id', 'title', 'message_body', 'target_type', 'target_class',
            'target_term', 'scheduled_at', 'status',
            'total_recipients', 'sent_count', 'delivered_count', 'failed_count',
            'created_at',
        ]
        read_only_fields = ['id', 'status', 'total_recipients', 'sent_count',
                            'delivered_count', 'failed_count', 'created_at']


class MessageLogSerializer(drf_serializers.ModelSerializer):
    student_name = drf_serializers.CharField(source='student.get_full_name', read_only=True)

    class Meta:
        model = MessageLog
        fields = [
            'id', 'student', 'student_name', 'recipient_phone',
            'channel', 'template_type', 'status', 'is_fallback',
            'sent_at', 'status_updated_at', 'created_at',
        ]
        read_only_fields = fields


class MessageTemplateSerializer(drf_serializers.ModelSerializer):
    class Meta:
        model = MessageTemplate
        fields = [
            'id', 'template_type', 'name', 'language', 'body',
            'meta_template_name', 'is_meta_approved',
            'meta_submission_status', 'meta_rejection_reason', 'is_active',
        ]
        read_only_fields = ['id', 'is_meta_approved', 'meta_submission_status', 'meta_rejection_reason']


class BroadcastViewSet(AuditMixin, viewsets.ModelViewSet):
    """US-035: Bulk broadcast messaging."""
    serializer_class = BroadcastSerializer
    permission_classes = [IsDirectorOrBursar]

    def get_queryset(self):
        return BroadcastMessage.objects.filter(school=self.request.user.school)

    def perform_create(self, serializer):
        broadcast = serializer.save(
            school=self.request.user.school,
            created_by=self.request.user,
        )
        self.log_action('BROADCAST_CREATED', broadcast, {'title': broadcast.title})

    @action(detail=True, methods=['post'], permission_classes=[IsDirectorOrBursar])
    def send(self, request, pk=None):
        """Dispatch the broadcast immediately (or schedule it)."""
        broadcast = self.get_object()
        if broadcast.status not in ('draft', 'scheduled'):
            return Response({'error': 'Broadcast already sent or cancelled.'}, status=400)

        # Resolve recipient list
        phone_list = self._resolve_recipients(broadcast)
        broadcast.total_recipients = len(phone_list)
        broadcast.status = 'sending'
        broadcast.save(update_fields=['total_recipients', 'status'])

        # Check daily limit (US-035)
        from django.core.cache import cache
        daily_key = f"wa_daily:{request.user.school.id}:{timezone.localdate()}"
        daily_count = cache.get(daily_key, 0)
        if daily_count + len(phone_list) > 1000:
            return Response({'error': f'WhatsApp daily limit (1,000) would be exceeded. '
                                      f'Current usage: {daily_count}. Recipients: {len(phone_list)}.'}, status=400)

        # Chunk and dispatch via Celery (rate-limited)
        from messaging.tasks import send_broadcast_chunk
        chunk_size = 50
        for i in range(0, len(phone_list), chunk_size):
            chunk = phone_list[i:i + chunk_size]
            send_broadcast_chunk.apply_async(
                args=[str(broadcast.id), chunk, broadcast.message_body],
                countdown=i // chunk_size * 2,  # 2s between chunks
            )

        cache.set(daily_key, daily_count + len(phone_list), timeout=86400)
        self.log_action('BROADCAST_SENT', broadcast, {'recipients': len(phone_list)})
        return Response({'message': f'Broadcast dispatched to {len(phone_list)} recipients.'})

    def _resolve_recipients(self, broadcast):
        from students.models import Guardian
        qs = Guardian.objects.filter(
            student__school=broadcast.school,
            is_primary=True,
            student__is_active=True,
        )
        if broadcast.target_type == 'class' and broadcast.target_class:
            qs = qs.filter(student__current_class=broadcast.target_class)
        elif broadcast.target_type == 'fee_defaulters' and broadcast.target_term:
            from payments.models import FeeRecord
            from django.db.models import F
            defaulter_ids = FeeRecord.all_objects.filter(
                academic_term=broadcast.target_term,
                school=broadcast.school,
            ).exclude(amount_paid__gte=F('total_amount') - F('amount_waived')
            ).values_list('student_id', flat=True)
            qs = qs.filter(student_id__in=defaulter_ids)
        return [{'phone': g.phone_normalised, 'student_id': str(g.student_id)} for g in qs]


class MessageLogListView(generics.ListAPIView):
    """US-039: Message delivery dashboard."""
    serializer_class = MessageLogSerializer
    permission_classes = [IsDirectorOrBursar]

    def get_queryset(self):
        qs = MessageLog.objects.filter(school=self.request.user.school)
        template_type = self.request.query_params.get('template_type')
        channel = self.request.query_params.get('channel')
        status_filter = self.request.query_params.get('status')
        if template_type:
            qs = qs.filter(template_type=template_type)
        if channel:
            qs = qs.filter(channel=channel)
        if status_filter:
            qs = qs.filter(status=status_filter)
        return qs.select_related('student')[:500]


class BroadcastDeliveryReportView(APIView):
    """
    US-039: Per-broadcast delivery report.
    Returns sent, delivered, read, failed counts with failed reason codes.
    Data retained for 90 days per spec.
    """
    permission_classes = [IsDirectorOrBursar]

    def get(self, request, broadcast_id):
        from django.db.models import Count, Q
        school = request.user.school
        try:
            broadcast = BroadcastMessage.objects.get(id=broadcast_id, school=school)
        except BroadcastMessage.DoesNotExist:
            return Response({'error': 'Broadcast not found.'}, status=404)

        logs = MessageLog.objects.filter(
            school=school,
            template_type='broadcast',
            created_at__gte=broadcast.created_at,
        )

        # Tighten to the broadcast window (created within 1hr of broadcast send)
        from django.utils import timezone
        import datetime
        window_end = broadcast.created_at + datetime.timedelta(hours=1)
        logs = logs.filter(created_at__lte=window_end)

        counts = logs.aggregate(
            total_sent=Count('id', filter=Q(status__in=['sent', 'delivered', 'read', 'failed'])),
            delivered=Count('id', filter=Q(status='delivered')),
            read=Count('id', filter=Q(status='read')),
            failed=Count('id', filter=Q(status='failed')),
        )

        # Failed messages with reason codes (US-039)
        failed_details = list(
            logs.filter(status='failed')
            .values('recipient_phone', 'error_message', 'created_at')
            .order_by('-created_at')[:200]
        )

        return Response({
            'broadcast_id': str(broadcast.id),
            'broadcast_title': broadcast.title,
            'status': broadcast.status,
            'scheduled_at': broadcast.scheduled_at,
            'created_at': broadcast.created_at,
            'total_recipients': broadcast.total_recipients,
            'sent': counts['total_sent'] or 0,
            'delivered': counts['delivered'] or 0,
            'read': counts['read'] or 0,
            'failed': counts['failed'] or 0,
            'delivery_rate_pct': round(
                counts['delivered'] / counts['total_sent'] * 100, 1
            ) if counts['total_sent'] else 0,
            'read_rate_pct': round(
                counts['read'] / counts['total_sent'] * 100, 1
            ) if counts['total_sent'] else 0,
            'failed_details': failed_details,
        })


class MessageTemplateViewSet(AuditMixin, viewsets.ModelViewSet):
    """US-040: Configurable message templates."""
    serializer_class = MessageTemplateSerializer
    permission_classes = [IsDirector]

    def get_queryset(self):
        return MessageTemplate.objects.filter(school=self.request.user.school)

    def perform_create(self, serializer):
        t = serializer.save(school=self.request.user.school)
        self.log_action('TEMPLATE_CREATED', t, {'type': t.template_type})


class TemplateSubmitToMetaView(AuditMixin, APIView):
    """
    US-040: Submit a MessageTemplate to Meta Business Manager for review.
    POST /messaging/templates/{id}/submit-to-meta/
    Idempotent — safe to resubmit a rejected template after editing.
    """
    permission_classes = [IsDirector]

    def post(self, request, pk):
        from messaging.services import MetaTemplateService
        try:
            template = MessageTemplate.objects.get(pk=pk, school=request.user.school)
        except MessageTemplate.DoesNotExist:
            return Response({'error': 'Template not found.'}, status=404)

        if template.is_meta_approved:
            return Response({
                'message': 'Template is already approved by Meta.',
                'meta_template_name': template.meta_template_name,
            })

        meta_name, success, error = MetaTemplateService.submit_template(template)
        if not success:
            return Response({'error': error or 'Submission failed.'}, status=400)

        # Persist the meta name and mark as pending
        template.meta_template_name = meta_name
        template.meta_submission_status = 'PENDING'
        template.save(update_fields=['meta_template_name', 'meta_submission_status'])

        self.log_action('TEMPLATE_SUBMITTED_TO_META', template, {
            'meta_name': meta_name,
        })
        return Response({
            'message': (
                f"Template '{meta_name}' submitted to Meta for review. "
                f"Approval typically takes 24–48 hours. "
                f"Use the sync endpoint to check status."
            ),
            'meta_template_name': meta_name,
            'status': 'PENDING',
        }, status=status.HTTP_202_ACCEPTED)


class TemplateSyncStatusView(AuditMixin, APIView):
    """
    US-040: Poll Meta API for template approval status and sync to DB.
    POST /messaging/templates/{id}/sync-status/
    Also called by Celery beat daily to auto-sync all pending templates.
    """
    permission_classes = [IsDirector]

    def post(self, request, pk):
        from messaging.services import MetaTemplateService
        try:
            template = MessageTemplate.objects.get(pk=pk, school=request.user.school)
        except MessageTemplate.DoesNotExist:
            return Response({'error': 'Template not found.'}, status=404)

        if not template.meta_template_name:
            return Response(
                {'error': 'Template has not been submitted to Meta yet. Use submit-to-meta first.'},
                status=400
            )

        meta_status, is_approved = MetaTemplateService.sync_approval_status(template)

        response_data = {
            'meta_template_name': template.meta_template_name,
            'status': meta_status,
            'is_approved': is_approved,
        }
        if meta_status == 'REJECTED' and template.meta_rejection_reason:
            response_data['rejection_reason'] = template.meta_rejection_reason
            response_data['action'] = (
                'Edit the template body to address Meta\'s feedback, then resubmit '
                'via submit-to-meta. Common reasons: no variables, policy violation, '
                'contains phone numbers or URLs in body.'
            )

        return Response(response_data)


class WhatsAppAnalyticsView(APIView):
    """US-059: WhatsApp interaction analytics."""
    permission_classes = [IsDirectorOrBursar]

    def get(self, request):
        from django.db.models import Count, Q
        from messaging.models import MessageLog, InboundMessage

        school = request.user.school
        logs = MessageLog.all_objects.filter(school=school, channel='whatsapp')

        total_sent = logs.filter(status__in=['sent', 'delivered', 'read']).count()
        total_delivered = logs.filter(status='delivered').count()
        total_read = logs.filter(status='read').count()
        total_failed = logs.filter(status='failed').count()

        by_type = logs.values('template_type').annotate(count=Count('id')).order_by('-count')

        inbound = InboundMessage.objects.filter(school=school)
        inbound_by_command = inbound.values('command').annotate(count=Count('id')).order_by('-count')

        return Response({
            'total_sent': total_sent,
            'total_delivered': total_delivered,
            'total_read': total_read,
            'total_failed': total_failed,
            'delivery_rate': round(total_delivered / total_sent * 100, 1) if total_sent else 0,
            'by_message_type': list(by_type),
            'inbound_commands': list(inbound_by_command),
        })
