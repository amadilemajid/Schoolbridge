"""
US-C04: Defaulter Campaign Views.
Fixed Issues:
  1. perform_create bypassed DefaulterCampaignService → target_count always 0
  2. launch rejected 'scheduled' status (service sets 'scheduled', not 'draft')
  3. No academic_term None guard → DB crash
  4. No recipient preview endpoint for UI
  5. No detailed success response from launch
"""
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django.utils import timezone
from .campaign_models import DefaulterCampaign
from audit.mixins import AuditMixin
from schools.permissions import IsDirectorOrBursar
from rest_framework import serializers


class DefaulterCampaignSerializer(serializers.ModelSerializer):
    class Meta:
        model = DefaulterCampaign
        fields = '__all__'
        read_only_fields = (
            'id', 'school', 'academic_term', 'status', 'target_count',
            'sent_count', 'delivered_count', 'failed_count',
            'started_at', 'completed_at', 'total_balance_targeted',
            'payments_received', 'created_by',
        )


class DefaulterCampaignViewSet(AuditMixin, viewsets.ModelViewSet):
    """
    US-C04: Defaulter Campaign management.
    """
    queryset = DefaulterCampaign.objects.none()
    serializer_class = DefaulterCampaignSerializer
    permission_classes = [IsDirectorOrBursar]

    def get_queryset(self):
        return DefaulterCampaign.objects.filter(school=self.request.user.school)

    def create(self, request, *args, **kwargs):
        """
        Create a campaign using DefaulterCampaignService so target list is built
        and target_count is correctly populated.
        Fix: perform_create used to call serializer.save() directly, bypassing the
        service, resulting in target_count=0 and no DefaulterCampaignTarget records.
        """
        from .campaign_service import DefaulterCampaignService

        term = request.user.school.terms.filter(is_current=True).first()
        if not term:
            return Response(
                {'detail': 'No active academic term found. Please configure an active term before sending reminders.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        try:
            campaign = DefaulterCampaignService.create_campaign(
                school=request.user.school,
                term=term,
                name=data.get('name', f'Fee Reminder – {timezone.now().strftime("%d %b %Y")}'),
                segment_type=data.get('segment_type', 'all'),
                message_template_en=data.get('message_template_en', ''),
                message_template_lg=data.get('message_template_lg', ''),
                min_balance=data.get('min_balance'),
                max_balance=data.get('max_balance'),
                created_by=request.user,
            )
        except Exception as exc:
            return Response(
                {'detail': f'Failed to build campaign target list: {exc}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        self.log_action('CAMPAIGN_CREATED', campaign, {
            'segment': campaign.segment_type,
            'target_count': campaign.target_count,
        })
        out = self.get_serializer(campaign)
        return Response(out.data, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=['get'])
    def today(self, request):
        """
        US-C04: Authoritative check for campaigns dispatched today (in school timezone).
        Returns whether a campaign was already dispatched today, count, and summary details
        to power the today's duplicate guard banner with live backend data.
        """
        from django.utils import timezone
        now = timezone.now()
        today_start = timezone.localtime(now).replace(hour=0, minute=0, second=0, microsecond=0)

        dispatched_today = DefaulterCampaign.objects.filter(
            school=request.user.school,
            started_at__gte=today_start,
        ).exclude(status__in=['draft', 'cancelled']).order_by('-started_at')

        if not dispatched_today.exists():
            dispatched_today = DefaulterCampaign.objects.filter(
                school=request.user.school,
                created_at__gte=today_start,
                status__in=['running', 'completed'],
            ).order_by('-created_at')

        count = dispatched_today.count()
        last_campaign = dispatched_today.first()

        last_info = None
        if last_campaign:
            last_info = {
                'id': str(last_campaign.id),
                'name': last_campaign.name,
                'segment_type': last_campaign.segment_type,
                'segment_label': last_campaign.get_segment_type_display(),
                'target_count': last_campaign.target_count,
                'sent_count': last_campaign.sent_count,
                'status': last_campaign.status,
                'dispatched_at': last_campaign.started_at or last_campaign.created_at,
            }

        return Response({
            'already_dispatched_today': count > 0,
            'count': count,
            'last_campaign': last_info,
            'campaigns': [
                {
                    'id': str(c.id),
                    'name': c.name,
                    'segment_type': c.segment_type,
                    'segment_label': c.get_segment_type_display(),
                    'target_count': c.target_count,
                    'sent_count': c.sent_count,
                    'status': c.status,
                    'dispatched_at': c.started_at or c.created_at,
                }
                for c in dispatched_today[:5]
            ],
        })

    @action(detail=False, methods=['get'])
    def preview(self, request):
        """
        Return live recipient count + sample for a given segment_type.
        Used by the UI to show how many guardians will be messaged BEFORE dispatching.
        This prevents surprises — the count is fetched from the actual DB, not hardcoded.
        """
        from payments.models import FeeRecord
        from django.db.models import F

        segment_type = request.query_params.get('segment_type', 'all')

        term = request.user.school.terms.filter(is_current=True).first()
        if not term:
            return Response({'count': 0, 'sample': [], 'segment_type': segment_type})

        HIGH_BALANCE = 500_000
        MEDIUM_MIN = 200_000

        qs = (
            FeeRecord.all_objects.filter(
                school=request.user.school,
                academic_term=term,
                student__is_active=True,
            )
            .annotate(calc_balance=F('total_amount') - F('amount_paid') - F('amount_waived'))
            .filter(calc_balance__gt=0)
            .select_related('student', 'student__current_class')
            .prefetch_related('student__guardians')
        )

        if segment_type == 'high_balance':
            qs = qs.filter(calc_balance__gte=HIGH_BALANCE)
        elif segment_type == 'medium_balance':
            qs = qs.filter(calc_balance__gte=MEDIUM_MIN, calc_balance__lt=HIGH_BALANCE)
        elif segment_type == 'low_balance':
            qs = qs.filter(calc_balance__lt=MEDIUM_MIN)
        elif segment_type == 'zero_payment':
            qs = qs.filter(amount_paid=0)
        elif segment_type == 'partial_payment':
            qs = qs.filter(amount_paid__gt=0, calc_balance__gt=0)

        count = 0
        sample = []
        for fr in qs[:200]:
            guardian = fr.student.guardians.filter(is_primary=True).first()
            if not guardian:
                continue
            count += 1
            if len(sample) < 5:
                phone = guardian.phone_normalised or ''
                masked = (phone[:3] + '****' + phone[-2:]) if len(phone) >= 6 else '****'
                sample.append({
                    'student_name': f"{fr.student.first_name} {fr.student.last_name}".strip(),
                    'class_name': fr.student.current_class.name if fr.student.current_class else 'N/A',
                    'balance': int(fr.calc_balance),
                    'guardian_phone': masked,
                })

        return Response({'count': count, 'sample': sample, 'segment_type': segment_type})

    @action(detail=True, methods=['post'])
    def launch(self, request, pk=None):
        """
        Launch the campaign.
        Fix: was checking status == 'draft' but DefaulterCampaignService.create_campaign()
        sets status='scheduled'. Changed to accept both 'draft' and 'scheduled'.
        """
        campaign = self.get_object()
        if campaign.status not in ('draft', 'scheduled'):
            return Response(
                {
                    'detail': (
                        f'Campaign is already {campaign.status}. '
                        'Only draft or scheduled campaigns can be launched.'
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        campaign.status = 'running'
        campaign.started_at = timezone.now()
        campaign.save(update_fields=['status', 'started_at'])

        self.log_action('CAMPAIGN_LAUNCHED', campaign, {
            'segment': campaign.segment_type,
            'target_count': campaign.target_count,
        })
        return Response({
            'message': 'Campaign launched successfully.',
            'status': 'running',
            'target_count': campaign.target_count,
            'name': campaign.name,
        })
