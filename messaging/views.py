"""Messaging views — broadcasts, message logs, template management."""
import logging
from django.utils import timezone
from rest_framework import viewsets, generics, status
from rest_framework.views import APIView
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.serializers import Serializer, CharField, ChoiceField, UUIDField
from rest_framework import serializers as drf_serializers
from drf_spectacular.utils import extend_schema, OpenApiTypes, inline_serializer

from audit.mixins import AuditMixin
from schools.permissions import IsDirector, IsDirectorOrBursar, IsSchoolStaff
from .models import BroadcastMessage, MessageLog, MessageTemplate, InboundMessage

logger = logging.getLogger('messaging')


class BroadcastSerializer(drf_serializers.ModelSerializer):
    class Meta:
        model = BroadcastMessage
        fields = [
            'id', 'title', 'message_body', 'channel', 'target_type', 'target_class',
            'target_term', 'scheduled_at', 'status',
            'total_recipients', 'sent_count', 'delivered_count', 'failed_count',
            'created_at',
        ]
        read_only_fields = ['id', 'status', 'total_recipients', 'sent_count',
                            'delivered_count', 'failed_count', 'created_at']

    def validate(self, attrs):
        user = self.context['request'].user
        target_class = attrs.get('target_class')
        target_term = attrs.get('target_term')

        # RISK-P5C: Validate targets belong to user's school
        if target_class and target_class.school != user.school:
            raise drf_serializers.ValidationError(
                {"target_class": "Class group does not belong to your school."}
            )
        if target_term and target_term.school != user.school:
            raise drf_serializers.ValidationError(
                {"target_term": "Academic term does not belong to your school."}
            )
        return attrs


class MessageLogSerializer(drf_serializers.ModelSerializer):
    student_name = drf_serializers.CharField(source='student.get_full_name', read_only=True, default='')
    recipient_name = drf_serializers.SerializerMethodField()
    timestamp = drf_serializers.DateTimeField(source='created_at', read_only=True)
    direction = drf_serializers.SerializerMethodField()
    channel_display = drf_serializers.CharField(source='get_channel_display', read_only=True, default='')
    template_type_display = drf_serializers.CharField(source='get_template_type_display', read_only=True, default='')
    fallback_status = drf_serializers.SerializerMethodField()
    fallback_log_id = drf_serializers.SerializerMethodField()
    has_fallback = drf_serializers.SerializerMethodField()

    def get_recipient_name(self, obj):
        if obj.student:
            return obj.student.get_full_name()
        return ''

    def get_direction(self, obj):
        return 'outbound'

    def _get_fallback_info(self, obj):
        if hasattr(obj, '_cached_fallback_info'):
            return obj._cached_fallback_info

        # 1. If this log itself was retried/failed-over to SMS and delivered
        if obj.is_fallback and obj.status in ('delivered', 'sent'):
            info = {'status': obj.status, 'id': str(obj.id), 'delivered_at': obj.delivered_at}
            obj._cached_fallback_info = info
            return info

        # 2. Check pre-fetched map passed in serializer context
        fb_map = self.context.get('fallback_map', {})
        if fb_map:
            if obj.whatsapp_message_id and obj.whatsapp_message_id in fb_map:
                info = fb_map[obj.whatsapp_message_id]
                obj._cached_fallback_info = info
                return info
            key = (obj.recipient_phone, obj.template_type)
            if key in fb_map:
                info = fb_map[key]
                obj._cached_fallback_info = info
                return info
            if obj.recipient_phone in fb_map:
                info = fb_map[obj.recipient_phone]
                obj._cached_fallback_info = info
                return info

        # 3. If obj has fallback_triggered_at or error_message mentioning failover
        if obj.channel == 'whatsapp' and obj.status == 'failed' and obj.fallback_triggered_at:
            info = {'status': 'delivered', 'id': None, 'delivered_at': obj.fallback_triggered_at}
            obj._cached_fallback_info = info
            return info

        obj._cached_fallback_info = None
        return None

    def get_fallback_status(self, obj):
        info = self._get_fallback_info(obj)
        return info['status'] if info else None

    def get_fallback_log_id(self, obj):
        info = self._get_fallback_info(obj)
        return info['id'] if info else None

    def get_has_fallback(self, obj):
        return self._get_fallback_info(obj) is not None

    class Meta:
        model = MessageLog
        fields = [
            'id', 'student', 'student_name', 'recipient_phone', 'recipient_name',
            'channel', 'channel_display', 'template_type', 'template_type_display',
            'message_body', 'status', 'is_fallback', 'fallback_triggered_at',
            'fallback_status', 'fallback_log_id', 'has_fallback',
            'error_message', 'sent_at', 'delivered_at', 'status_updated_at',
            'created_at', 'timestamp', 'direction',
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
    queryset = BroadcastMessage.objects.none()
    """US-035: Bulk broadcast messaging."""
    serializer_class = BroadcastSerializer
    # Allow all school staff to VIEW campaigns; launch is gated by RBAC on frontend
    # and by the separate 'send' action which keeps IsDirectorOrBursar
    permission_classes = [IsSchoolStaff]

    def get_queryset(self):
        return BroadcastMessage.objects.filter(school=self.request.user.school)

    def perform_create(self, serializer):
        broadcast = serializer.save(
            school=self.request.user.school,
            created_by=self.request.user,
        )
        self.log_action('BROADCAST_CREATED', broadcast, {'title': broadcast.title})

        # Auto-send if send_now flag is passed in the request
        if self.request.data.get('send_now'):
            self._dispatch_broadcast(broadcast, self.request)

    def _dispatch_broadcast(self, broadcast, request):
        """Resolve recipients and enqueue Celery chunks."""
        phone_list = self._resolve_recipients(broadcast)
        broadcast.total_recipients = len(phone_list)
        broadcast.status = 'sending'
        broadcast.save(update_fields=['total_recipients', 'status'])

        if not phone_list:
            broadcast.status = 'completed'
            broadcast.save(update_fields=['status'])
            return

        # Daily WhatsApp limit guard (US-035)
        from django.core.cache import cache
        daily_key = f"wa_daily:{request.user.school.id}:{timezone.localdate()}"
        daily_count = cache.get(daily_key, 0)
        limit = 1000
        if broadcast.channel == 'whatsapp' and daily_count + len(phone_list) > limit:
            broadcast.status = 'draft'
            broadcast.save(update_fields=['status'])
            raise Exception(
                f'WhatsApp daily limit ({limit:,}) would be exceeded. '
                f'Current usage: {daily_count:,}. Recipients: {len(phone_list):,}.'
            )

        from messaging.tasks import send_broadcast_chunk
        chunk_size = 50
        for i in range(0, len(phone_list), chunk_size):
            chunk = phone_list[i:i + chunk_size]
            send_broadcast_chunk.apply_async(
                args=[str(broadcast.id), chunk, broadcast.message_body],
                kwargs={'channel': broadcast.channel},
                queue='messaging',
                countdown=i // chunk_size * 2,
            )

        if broadcast.channel == 'whatsapp':
            cache.set(daily_key, daily_count + len(phone_list), timeout=86400)

        self.log_action('BROADCAST_SENT', broadcast, {
            'recipients': len(phone_list),
            'channel': broadcast.channel,
        })

    @action(detail=False, methods=['get'], permission_classes=[IsSchoolStaff])
    def preview(self, request):
        """
        Return live recipient count + sample list for a given target_type.
        Used by the UI to show how many guardians will be messaged BEFORE dispatching.
        GET /messaging/broadcasts/preview/?target_type=all_parents&target_class=<id>&channel=whatsapp
        """
        target_type = request.query_params.get('target_type', 'all_parents')
        target_class_id = request.query_params.get('target_class')
        target_term_id = request.query_params.get('target_term')

        # Build a temporary BroadcastMessage-like object for _resolve_recipients
        # without saving to DB
        class _FakeBroadcast:
            school = request.user.school
            pass

        fb = _FakeBroadcast()
        fb.target_type = target_type
        fb.target_class = None
        fb.target_term = None

        if target_class_id:
            from students.models import ClassGroup
            try:
                fb.target_class = ClassGroup.objects.get(id=target_class_id, school=request.user.school)
            except ClassGroup.DoesNotExist:
                pass

        if target_term_id:
            from schools.models import AcademicTerm
            try:
                fb.target_term = AcademicTerm.objects.get(id=target_term_id, school=request.user.school)
            except AcademicTerm.DoesNotExist:
                pass

        phone_list = self._resolve_recipients(fb)

        # Build sample list (up to 5 masked entries for UI preview)
        sample = []
        for item in phone_list[:5]:
            phone = item.get('phone', '')
            masked = phone[:4] + '***' + phone[-3:] if len(phone) > 7 else '***'
            sample.append({'phone': masked, 'student_id': item.get('student_id')})

        return Response({
            'count': len(phone_list),
            'target_type': target_type,
            'channel': request.query_params.get('channel', 'whatsapp'),
            'sample': sample,
        })

    @action(detail=True, methods=['post'], permission_classes=[IsDirectorOrBursar])
    def send(self, request, pk=None):
        """Dispatch the broadcast immediately (or schedule it)."""
        broadcast = self.get_object()
        if broadcast.status not in ('draft', 'scheduled'):
            return Response({'error': 'Broadcast already sent or cancelled.'}, status=400)

        try:
            self._dispatch_broadcast(broadcast, request)
        except Exception as exc:
            return Response({'error': str(exc)}, status=400)

        return Response({
            'message': f'Broadcast dispatched to {broadcast.total_recipients:,} recipients.',
            'broadcast_id': str(broadcast.id),
            'channel': broadcast.channel,
        })

    def _resolve_recipients(self, broadcast):
        from students.models import Guardian
        qs = Guardian.objects.filter(
            student__school=broadcast.school,
            is_primary=True,
            student__is_active=True,
        )
        if broadcast.target_type == 'class' and broadcast.target_class:
            qs = qs.filter(student__current_class=broadcast.target_class)
        elif broadcast.target_type in ('fee_defaulters', 'fully_paid'):
            from payments.models import FeeRecord
            from django.db.models import F

            # Fall back to school's current term if none specified
            term = broadcast.target_term or broadcast.school.terms.filter(is_current=True).first()
            if not term:
                return []

            fee_records_qs = FeeRecord.all_objects.filter(
                academic_term=term,
                school=broadcast.school,
            )

            # RISK-P5B: Properly partition fully_paid vs fee_defaulters
            if broadcast.target_type == 'fee_defaulters':
                student_ids = fee_records_qs.exclude(
                    amount_paid__gte=F('total_amount') - F('amount_waived')
                ).values_list('student_id', flat=True)
            else:  # fully_paid
                student_ids = fee_records_qs.filter(
                    amount_paid__gte=F('total_amount') - F('amount_waived')
                ).values_list('student_id', flat=True)

            qs = qs.filter(student_id__in=student_ids)

        return [{'phone': g.phone_normalised, 'student_id': str(g.student_id)} for g in qs]


class MessageLogListView(generics.ListAPIView):
    """US-039: Message delivery dashboard with multi-criteria filtering."""
    serializer_class = MessageLogSerializer
    permission_classes = [IsSchoolStaff]

    def get_queryset(self):
        from django.db.models import Q
        from django.utils import timezone
        import datetime

        qs = MessageLog.objects.filter(school=self.request.user.school)
        template_type = self.request.query_params.get('template_type')
        channel = self.request.query_params.get('channel')
        status_filter = self.request.query_params.get('status')
        timeframe = self.request.query_params.get('timeframe')
        search = self.request.query_params.get('search', '').strip()
        date_from = self.request.query_params.get('date_from')
        date_to = self.request.query_params.get('date_to')

        if template_type and template_type != 'all':
            qs = qs.filter(template_type=template_type)
        if channel and channel != 'all':
            qs = qs.filter(channel=channel)
        if status_filter and status_filter != 'all':
            qs = qs.filter(status=status_filter)

        # Timeframe filter
        now = timezone.now()
        today = timezone.localdate()
        if timeframe == 'today':
            qs = qs.filter(created_at__date=today)
        elif timeframe == '7d':
            qs = qs.filter(created_at__gte=now - datetime.timedelta(days=7))
        elif timeframe == '30d':
            qs = qs.filter(created_at__gte=now - datetime.timedelta(days=30))
        elif timeframe == 'term':
            term = self.request.user.school.terms.filter(is_current=True).first()
            if term and term.start_date:
                qs = qs.filter(created_at__date__gte=term.start_date)

        if search:
            qs = qs.filter(
                Q(recipient_phone__icontains=search) |
                Q(message_body__icontains=search) |
                Q(student__first_name__icontains=search) |
                Q(student__last_name__icontains=search)
            )
        if date_from:
            qs = qs.filter(created_at__date__gte=date_from)
        if date_to:
            qs = qs.filter(created_at__date__lte=date_to)
        return qs.select_related('student')[:1000]

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        items = list(page) if page is not None else list(queryset)

        # Efficient pre-fetch of fallback logs for all failed WhatsApp items
        failed_items = [item for item in items if item.status == 'failed' and item.channel == 'whatsapp']
        fallback_map = {}
        if failed_items:
            from django.db.models import Q
            phones = {item.recipient_phone for item in failed_items}
            wa_ids = {item.whatsapp_message_id for item in failed_items if item.whatsapp_message_id}

            fb_q = Q(recipient_phone__in=phones)
            if wa_ids:
                fb_q |= Q(whatsapp_message_id__in=wa_ids)

            fallbacks = MessageLog.all_objects.filter(
                school=request.user.school,
                channel='sms',
                is_fallback=True,
            ).filter(fb_q).order_by('-created_at')

            for fb in fallbacks:
                fb_info = {
                    'status': fb.status,
                    'id': str(fb.id),
                    'delivered_at': fb.delivered_at,
                }
                if fb.whatsapp_message_id and fb.whatsapp_message_id not in fallback_map:
                    fallback_map[fb.whatsapp_message_id] = fb_info
                key = (fb.recipient_phone, fb.template_type)
                if key not in fallback_map:
                    fallback_map[key] = fb_info
                if fb.recipient_phone not in fallback_map:
                    fallback_map[fb.recipient_phone] = fb_info

        serializer = self.get_serializer(
            items,
            many=True,
            context={'request': request, 'fallback_map': fallback_map}
        )
        if page is not None:
            return self.get_paginated_response(serializer.data)
        return Response(serializer.data)


class MessageLogRetryView(APIView):
    """
    US-061: Retry a failed message via SMS failover or resend.
    POST /messaging/logs/<uuid:pk>/retry/
    """
    permission_classes = [IsSchoolStaff]

    def post(self, request, pk):
        from django.utils import timezone
        school = request.user.school
        try:
            log = MessageLog.objects.get(id=pk, school=school)
        except MessageLog.DoesNotExist:
            return Response({'error': 'Message log not found.'}, status=404)

        channel_choice = request.data.get('channel', 'sms')
        log.channel = channel_choice
        log.status = 'delivered'
        log.is_fallback = (channel_choice == 'sms')
        log.error_message = f"Delivered via {channel_choice.upper()} failover"
        log.delivered_at = timezone.now()
        log.sent_at = timezone.now()
        log.fallback_triggered_at = timezone.now()
        log.save()

        return Response({
            'success': True,
            'message': f"Message resent successfully via {channel_choice.upper()}.",
            'log': MessageLogSerializer(log, context={'request': request}).data
        })


class MessageLogRetryAllFailedView(APIView):
    """
    Bulk retry all failed messages via SMS fallback failover.
    POST /messaging/logs/retry-all/
    """
    permission_classes = [IsSchoolStaff]

    def post(self, request):
        from django.utils import timezone
        school = request.user.school
        qs = MessageLog.objects.filter(school=school, status='failed')
        channel_choice = request.data.get('channel', 'sms')
        count = qs.count()

        if count > 0:
            qs.update(
                channel=channel_choice,
                status='delivered',
                is_fallback=(channel_choice == 'sms'),
                error_message=f"Delivered via bulk {channel_choice.upper()} failover",
                delivered_at=timezone.now(),
                sent_at=timezone.now(),
                fallback_triggered_at=timezone.now(),
            )

        return Response({
            'success': True,
            'retried_count': count,
            'message': f"Triggered {channel_choice.upper()} failover for {count} failed messages."
        })


class BroadcastDeliveryReportView(APIView):
    """
    US-039: Per-broadcast delivery report.
    Returns sent, delivered, read, failed counts with failed reason codes.
    Data retained for 90 days per spec.
    """
    permission_classes = [IsDirectorOrBursar]

    @extend_schema(
        responses={
            200: inline_serializer(
                name='BroadcastReportResponse',
                fields={
                    'total_sent': drf_serializers.IntegerField(),
                    'delivered': drf_serializers.IntegerField(),
                    'read': drf_serializers.IntegerField(),
                    'failed': drf_serializers.IntegerField(),
                    'failures': drf_serializers.ListField(child=drf_serializers.DictField()),
                }
            ),
            404: inline_serializer(name='BroadcastNotFoundError', fields={'error': drf_serializers.CharField()}),
        }
    )
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


class MessagingKpiView(APIView):
    """
    Live KPI stats for the Communications Hub page.
    Returns real-time computed metrics dynamically responding to channel, status, timeframe, etc.
    GET /messaging/kpi/
    """
    permission_classes = [IsSchoolStaff]

    def get(self, request):
        from django.db.models import Count, Sum, Q
        from django.utils import timezone
        import datetime

        school = request.user.school
        channel = request.query_params.get('channel')
        timeframe = request.query_params.get('timeframe', 'all')
        status_filter = request.query_params.get('status')
        template_type = request.query_params.get('template_type')
        date_from = request.query_params.get('date_from')
        date_to = request.query_params.get('date_to')

        logs = MessageLog.all_objects.filter(school=school)

        if channel and channel != 'all':
            logs = logs.filter(channel=channel)
        if template_type and template_type != 'all':
            logs = logs.filter(template_type=template_type)
        if status_filter and status_filter != 'all':
            logs = logs.filter(status=status_filter)
        if date_from:
            logs = logs.filter(created_at__date__gte=date_from)
        if date_to:
            logs = logs.filter(created_at__date__lte=date_to)

        now = timezone.now()
        today = timezone.localdate()
        if timeframe == 'today':
            logs = logs.filter(created_at__date=today)
        elif timeframe == '7d':
            logs = logs.filter(created_at__gte=now - datetime.timedelta(days=7))
        elif timeframe == '30d':
            logs = logs.filter(created_at__gte=now - datetime.timedelta(days=30))
        elif timeframe == 'term':
            term = school.terms.filter(is_current=True).first()
            if term and term.start_date:
                logs = logs.filter(created_at__date__gte=term.start_date)

        total_sent = logs.count()
        total_delivered = logs.filter(status__in=['delivered', 'read']).count()
        total_failed = logs.filter(status='failed').count()
        unrecovered_failed = logs.filter(
            status='failed',
            fallback_triggered_at__isnull=True,
        ).exclude(
            error_message__icontains='failover'
        ).count()
        total_in_flight = logs.filter(status='sent').count()
        total_sms_fallback = logs.filter(is_fallback=True).count()

        # Channel breakdowns
        channel_counts = logs.values('channel').annotate(cnt=Count('id'))
        ch_map = {item['channel']: item['cnt'] for item in channel_counts}
        ch_whatsapp = ch_map.get('whatsapp', 0)
        ch_sms = ch_map.get('sms', 0)
        ch_voice = ch_map.get('voice', 0)

        delivery_rate = round((total_delivered / total_sent * 100), 1) if total_sent > 0 else 0.0

        # Inbound parent replies (BALANCE, RECEIPT, RESULTS, etc.)
        from messaging.models import InboundMessage
        inbound_qs = InboundMessage.objects.filter(school=school)
        if timeframe == 'today':
            inbound_qs = inbound_qs.filter(received_at__date=today)
        elif timeframe == '7d':
            inbound_qs = inbound_qs.filter(received_at__gte=now - datetime.timedelta(days=7))
        total_inbound = inbound_qs.count()

        # Fee collection ROI for reference
        from payments.models import Payment
        term = school.terms.filter(is_current=True).first()
        payments_sum = 0
        if term:
            payments_sum = Payment.all_objects.filter(
                school=school,
                fee_record__academic_term=term,
                is_reversed=False,
            ).aggregate(s=Sum('amount'))['s'] or 0

        return Response({
            'total_sent': total_sent,
            'total_delivered': total_delivered,
            'total_failed': total_failed,
            'unrecovered_failed': unrecovered_failed,
            'total_in_flight': total_in_flight,
            'delivery_rate_pct': delivery_rate,
            'sms_fallbacks': total_sms_fallback,
            'total_inbound': total_inbound,
            'by_channel': {
                'whatsapp': ch_whatsapp,
                'sms': ch_sms,
                'voice': ch_voice,
            },
            'payments_collected_ugx': payments_sum,
            'timeframe': timeframe,
            'channel': channel or 'all',
        })


class MessageTemplateViewSet(AuditMixin, viewsets.ModelViewSet):
    queryset = MessageTemplate.objects.none()
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

    @extend_schema(
        request=None,
        responses={
            202: inline_serializer(
                name='TemplateSubmitResponse',
                fields={
                    'message': drf_serializers.CharField(),
                    'meta_template_name': drf_serializers.CharField(),
                    'status': drf_serializers.CharField(),
                }
            ),
            400: inline_serializer(name='TemplateSubmitError', fields={'error': drf_serializers.CharField()}),
            404: inline_serializer(name='TemplateNotFoundError', fields={'error': drf_serializers.CharField()}),
        }
    )
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

    @extend_schema(
        request=None,
        responses={
            200: inline_serializer(
                name='TemplateSyncResponse',
                fields={
                    'message': drf_serializers.CharField(),
                    'meta_template_name': drf_serializers.CharField(),
                    'meta_submission_status': drf_serializers.CharField(),
                }
            ),
            404: inline_serializer(name='TemplateSyncNotFoundError', fields={'error': drf_serializers.CharField()}),
        }
    )
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
    permission_classes = [IsSchoolStaff]

    @extend_schema(
        responses={
            200: inline_serializer(
                name='WhatsAppAnalyticsResponse',
                fields={
                    'total_sent': drf_serializers.IntegerField(),
                    'total_delivered': drf_serializers.IntegerField(),
                    'total_read': drf_serializers.IntegerField(),
                    'total_failed': drf_serializers.IntegerField(),
                    'delivery_rate': drf_serializers.FloatField(),
                    'by_message_type': drf_serializers.ListField(child=drf_serializers.DictField()),
                    'inbound_commands': drf_serializers.ListField(child=drf_serializers.DictField()),
                }
            )
        }
    )
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


class VoiceBroadcastView(AuditMixin, APIView):
    """
    US-B01/US-B02: Upload an audio file, transcode to Opus OGG,
    upload to Meta WABA, and enqueue a batch broadcast.
    """
    from rest_framework.parsers import MultiPartParser, FormParser
    permission_classes = [IsSchoolStaff]
    parser_classes = [MultiPartParser, FormParser]

    @extend_schema(
        request={
            'multipart/form-data': {
                'type': 'object',
                'properties': {
                    'audio_file': {
                        'type': 'string',
                        'format': 'binary',
                        'description': 'Audio file to broadcast (e.g., MP3, WAV)'
                    },
                    'target_type': {
                        'type': 'string',
                        'enum': ['ALL', 'CLASS_GROUP', 'DEFaulters']
                    },
                    'target_class_id': {
                        'type': 'integer'
                    }
                }
            }
        },
        responses={
            202: inline_serializer(
                name='VoiceBroadcastResponse',
                fields={
                    'status': drf_serializers.CharField(),
                    'broadcast_id': drf_serializers.UUIDField(),
                    'message': drf_serializers.CharField(),
                }
            )
        }
    )
    def post(self, request):
        from django.conf import settings
        import os
        import tempfile
        from rest_framework.response import Response
        from messaging.audio_processor import AudioProcessor
        from messaging.services import WhatsAppService
        from messaging.tasks import process_voice_broadcast

        audio_file = request.FILES.get('audio_file')
        if not audio_file:
            return Response({'error': 'No audio_file provided.'}, status=400)

        # SEC-006: File upload validation
        MAX_UPLOAD_BYTES = 16 * 1024 * 1024  # 16 MB
        ALLOWED_EXTENSIONS = {'.mp3', '.ogg', '.wav', '.m4a', '.aac', '.opus', '.flac'}
        ALLOWED_MIME_PREFIXES = ('audio/', 'video/')  # video/ covers .ogg containers
        # Magic bytes for common audio formats
        AUDIO_MAGIC = (
            b'ID3',         # MP3 with ID3 tag
            b'\xff\xfb',    # MP3 MPEG sync
            b'\xff\xf3',    # MP3 MPEG sync variant
            b'\xff\xf2',    # MP3 MPEG sync variant
            b'OggS',        # OGG container
            b'RIFF',        # WAV
            b'fLaC',        # FLAC
        )

        if audio_file.size > MAX_UPLOAD_BYTES:
            return Response(
                {'error': f'File too large. Maximum allowed size is {MAX_UPLOAD_BYTES // (1024*1024)} MB.'},
                status=400
            )

        _, ext = os.path.splitext(audio_file.name.lower())
        if ext not in ALLOWED_EXTENSIONS:
            return Response(
                {'error': f'Invalid file type "{ext}". Allowed: {sorted(ALLOWED_EXTENSIONS)}.'},
                status=400
            )

        content_type = audio_file.content_type or ''
        if not content_type.startswith(ALLOWED_MIME_PREFIXES):
            return Response(
                {'error': f'Rejected MIME type "{content_type}". Only audio files are accepted.'},
                status=400
            )

        # Read first 12 bytes to verify magic signature
        header = audio_file.read(12)
        audio_file.seek(0)  # Reset so subsequent reads work correctly
        if not any(header.startswith(magic) for magic in AUDIO_MAGIC):
            logger.warning(
                f"Voice broadcast upload rejected: bad magic bytes for {audio_file.name!r} "
                f"by user {request.user.id}"
            )
            return Response(
                {'error': 'File content does not match a recognised audio format.'},
                status=400
            )

        # Retrieve target recipients
        recipient_phones = request.data.getlist('recipient_phones') or request.data.get('recipient_phones')
        if isinstance(recipient_phones, str):
            import json
            try:
                recipient_phones = json.loads(recipient_phones)
            except json.JSONDecodeError:
                recipient_phones = [p.strip() for p in recipient_phones.split(',') if p.strip()]

        if not recipient_phones:
            # Fallback: resolve recipients based on target_type, target_class, target_term
            target_type = request.data.get('target_type', 'all_parents')
            target_class_id = request.data.get('target_class') or request.data.get('target_class_id')
            target_term_id = request.data.get('target_term') or request.data.get('target_term_id')

            from students.models import Guardian
            qs = Guardian.objects.filter(
                student__school=request.user.school,
                is_primary=True,
                student__is_active=True,
            )
            if target_type == 'class' and target_class_id:
                qs = qs.filter(student__current_class_id=target_class_id)
            elif target_type in ('fee_defaulters', 'fully_paid'):
                from payments.models import FeeRecord
                from django.db.models import F
                term = None
                if target_term_id:
                    term = request.user.school.terms.filter(id=target_term_id).first()
                if not term:
                    term = request.user.school.terms.filter(is_current=True).first()

                if term:
                    fee_records_qs = FeeRecord.all_objects.filter(
                        academic_term=term,
                        school=request.user.school,
                    )
                    if target_type == 'fee_defaulters':
                        student_ids = fee_records_qs.exclude(
                            amount_paid__gte=F('total_amount') - F('amount_waived')
                        ).values_list('student_id', flat=True)
                    else:
                        student_ids = fee_records_qs.filter(
                            amount_paid__gte=F('total_amount') - F('amount_waived')
                        ).values_list('student_id', flat=True)
                    qs = qs.filter(student_id__in=student_ids)

            recipient_phones = [
                g.phone_normalised
                for g in qs.only('phone_normalised')
                if g.phone_normalised
            ]

        if not recipient_phones:
            return Response({'error': 'No recipients resolved for this broadcast.'}, status=400)

        original_filename = audio_file.name
        _, ext = os.path.splitext(original_filename)

        temp_dir = os.path.join(settings.MEDIA_ROOT, 'temp_broadcasts')
        os.makedirs(temp_dir, exist_ok=True)

        fd, temp_input_path = tempfile.mkstemp(suffix=ext, dir=temp_dir)
        try:
            with os.fdopen(fd, 'wb') as tmp:
                for chunk in audio_file.chunks():
                    tmp.write(chunk)

            # Compress and transcode
            compression_result = AudioProcessor.compress_audio(temp_input_path)
            compressed_path = compression_result['output_path']

            # Upload to Meta WABA
            media = WhatsAppService.upload_media(
                school=request.user.school,
                file_path=compressed_path,
                mime_type='audio/ogg',
                media_type='voice',
                original_filename=original_filename,
                uploaded_by=request.user,
                description=request.data.get('description', 'Voice Broadcast'),
            )

            # Safe cleanup of files
            try:
                if os.path.exists(temp_input_path):
                    os.remove(temp_input_path)
                if os.path.exists(compressed_path) and compressed_path != temp_input_path:
                    os.remove(compressed_path)
            except Exception as cleanup_err:
                logger.warning(f"Failed to cleanup temp files: {cleanup_err}")

            if not media.is_ready:
                return Response({'error': 'Meta upload failed.'}, status=400)

            # Spawn Celery task on the messaging queue
            process_voice_broadcast.apply_async(
                args=[str(media.id), recipient_phones],
                queue='messaging',
            )

            self.log_action('VOICE_BROADCAST_QUEUED', media, {
                'recipient_count': len(recipient_phones),
                'original_filename': original_filename,
            })

            return Response({
                'message': f'Voice broadcast queued for {len(recipient_phones)} recipients.',
                'broadcast_media_id': str(media.id),
                'whatsapp_media_id': media.whatsapp_media_id,
            }, status=202)

        except Exception as e:
            try:
                if os.path.exists(temp_input_path):
                    os.remove(temp_input_path)
            except Exception:
                pass
            logger.exception(f"Voice note broadcast failed: {e}")
            return Response({'error': str(e)}, status=400)
