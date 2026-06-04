"""
Automation views.
US-064: Director-initiated messaging pause with start/end date and dropped-task summary.
US-054: Combined school operations overview dashboard.
US-048: School-wide academic performance dashboard.
US-055: Fee collection trend chart.
US-056: Term-end financial summary report.
"""
import logging
from django.utils import timezone
from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework import serializers as drf_serializers

from audit.mixins import AuditMixin
from schools.permissions import IsDirector, IsDirectorOrBursar, IsSchoolStaff

logger = logging.getLogger('schoolbridge')


# ---------------------------------------------------------------------------
# US-064: Messaging Pause
# ---------------------------------------------------------------------------

class MessagingPauseSerializer(drf_serializers.Serializer):
    start_date = drf_serializers.DateField()
    end_date = drf_serializers.DateField()
    reason = drf_serializers.CharField(max_length=500)

    def validate(self, data):
        if data['end_date'] < data['start_date']:
            raise drf_serializers.ValidationError('end_date must be on or after start_date.')
        return data


class MessagingPauseView(AuditMixin, APIView):
    """
    US-064: Director sets a messaging pause period.
    GET  — list all pauses for this school (active + historical).
    POST — create a new pause (start_date, end_date, reason).
    """
    permission_classes = [IsDirector]

    def get(self, request):
        from schools.models import MessagingPause
        pauses = MessagingPause.objects.filter(school=request.user.school).values(
            'id', 'start_date', 'end_date', 'reason', 'is_active',
            'dropped_tasks_count', 'dropped_tasks_summary', 'created_at', 'ended_at'
        )
        return Response(list(pauses))

    def post(self, request):
        from schools.models import MessagingPause
        serializer = MessagingPauseSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        d = serializer.validated_data

        # Deactivate any overlapping active pause first
        MessagingPause.objects.filter(
            school=request.user.school, is_active=True
        ).update(is_active=False, ended_at=timezone.now())

        pause = MessagingPause.objects.create(
            school=request.user.school,
            start_date=d['start_date'],
            end_date=d['end_date'],
            reason=d['reason'],
            created_by=request.user,
        )
        self.log_action('MESSAGING_PAUSE_CREATED', pause, {
            'start_date': str(d['start_date']),
            'end_date': str(d['end_date']),
            'reason': d['reason'],
        })
        logger.info(
            f"Messaging paused for {request.user.school.name} "
            f"from {d['start_date']} to {d['end_date']}: {d['reason']}"
        )
        return Response({
            'id': pause.id,
            'message': (
                f"All automated reminders paused from {d['start_date']} to {d['end_date']}. "
                f"Emergency broadcasts will still go through."
            ),
        }, status=status.HTTP_201_CREATED)


class MessagingPauseEndView(AuditMixin, APIView):
    """
    US-064: End an active messaging pause early.
    Returns summary of tasks dropped during the pause.
    """
    permission_classes = [IsDirector]

    def post(self, request, pause_id):
        from schools.models import MessagingPause
        try:
            pause = MessagingPause.objects.get(
                id=pause_id, school=request.user.school, is_active=True
            )
        except MessagingPause.DoesNotExist:
            return Response({'error': 'Active pause not found.'}, status=404)

        pause.is_active = False
        pause.ended_at = timezone.now()
        pause.save(update_fields=['is_active', 'ended_at'])

        self.log_action('MESSAGING_PAUSE_ENDED', pause, {
            'dropped_tasks_count': pause.dropped_tasks_count,
        })
        return Response({
            'message': 'Messaging pause ended.',
            'dropped_tasks_count': pause.dropped_tasks_count,
            'dropped_tasks_summary': pause.dropped_tasks_summary or [],
        })


# ---------------------------------------------------------------------------
# US-054: Combined operations overview dashboard
# ---------------------------------------------------------------------------

class OperationsDashboardView(APIView):
    """
    US-054: Single-screen operations overview for Director.
    Returns today's collections, attendance rate, pending reconciliation,
    unread alerts, and WhatsApp delivery stats — all in one response.
    Data refreshes every 5 minutes (cache-backed).
    """
    permission_classes = [IsDirector]

    def get(self, request):
        from django.core.cache import cache
        school = request.user.school
        cache_key = f'ops_dashboard:{school.id}'
        cached = cache.get(cache_key)
        if cached:
            return Response(cached)

        data = self._build_dashboard(school)
        cache.set(cache_key, data, timeout=300)  # 5-minute cache
        return Response(data)

    def _build_dashboard(self, school):
        from payments.models import Payment, ReconciliationQueue, FeeRecord
        from attendance.models import AttendanceRecord
        from notifications.models import Notification
        from django.db.models import Sum, Count, Q, F
        from messaging.models import MessageLog

        today = timezone.localdate()
        term = school.terms.filter(is_current=True).first()

        # Today's MoMo collections
        today_payments = Payment.all_objects.filter(
            school=school,
            payment_date__date=today,
            status='completed',
            is_reversed=False,
        ).aggregate(total=Sum('amount'), count=Count('id'))

        # Current term collection rate
        collection_rate = None
        total_expected = None
        total_collected = None
        if term:
            agg = FeeRecord.all_objects.filter(
                school=school, academic_term=term
            ).aggregate(
                expected=Sum('total_amount'),
                collected=Sum('amount_paid'),
            )
            total_expected = agg['expected'] or 0
            total_collected = agg['collected'] or 0
            collection_rate = round(
                total_collected / total_expected * 100, 1
            ) if total_expected else 0

        # Today's school-wide attendance rate
        attendance_rate = None
        if term:
            total_students = AttendanceRecord.all_objects.filter(
                school=school, date=today
            ).count()
            present = AttendanceRecord.all_objects.filter(
                school=school, date=today, status__in=['present', 'late']
            ).count()
            attendance_rate = round(
                present / total_students * 100, 1
            ) if total_students else None

        # Pending reconciliation items
        pending_recon = ReconciliationQueue.all_objects.filter(
            school=school, status='pending'
        ).count()

        # Unread staff alerts
        unread_alerts = Notification.all_objects.filter(
            school=school, is_read=False
        ).count()

        # WhatsApp delivery stats today
        wa_today = MessageLog.all_objects.filter(
            school=school, created_at__date=today, channel='whatsapp'
        ).aggregate(
            sent=Count('id', filter=Q(status__in=['sent', 'delivered', 'read'])),
            failed=Count('id', filter=Q(status='failed')),
        )

        # Active messaging pause
        from schools.models import MessagingPause
        active_pause = MessagingPause.objects.filter(
            school=school, is_active=True,
            start_date__lte=today, end_date__gte=today,
        ).values('start_date', 'end_date', 'reason').first()

        return {
            'school': school.name,
            'date': str(today),
            'term': str(term) if term else None,
            'today_collections_ugx': today_payments['total'] or 0,
            'today_payment_count': today_payments['count'] or 0,
            'term_collection_rate_pct': collection_rate,
            'term_total_expected_ugx': total_expected,
            'term_total_collected_ugx': total_collected,
            'today_attendance_rate_pct': attendance_rate,
            'pending_reconciliation_count': pending_recon,
            'unread_alerts_count': unread_alerts,
            'whatsapp_sent_today': wa_today['sent'] or 0,
            'whatsapp_failed_today': wa_today['failed'] or 0,
            'messaging_paused': bool(active_pause),
            'active_pause': active_pause,
        }


# ---------------------------------------------------------------------------
# US-048: School-wide academic performance dashboard
# ---------------------------------------------------------------------------

class AcademicDashboardView(APIView):
    """
    US-048: School-wide academic performance for current term.
    Director only. Shows class averages, subject averages, top/bottom students.
    """
    permission_classes = [IsDirector]

    def get(self, request):
        from results.models import TermResult, AssessmentMark, Assessment
        from students.models import ClassGroup
        from django.db.models import Avg, Count

        school = request.user.school
        term_id = request.query_params.get('term_id')

        if term_id:
            from schools.models import AcademicTerm
            try:
                term = AcademicTerm.objects.get(id=term_id, school=school)
            except AcademicTerm.DoesNotExist:
                return Response({'error': 'Term not found.'}, status=404)
        else:
            term = school.terms.filter(is_current=True).first()

        if not term:
            return Response({'error': 'No current term.'}, status=400)

        results = TermResult.all_objects.filter(
            school=school, academic_term=term
        ).select_related('student', 'class_group')

        if not results.exists():
            return Response({'error': 'No results for this term yet.'}, status=200)

        # Average per class
        class_averages = (
            results.values('class_group__name', 'class_group__id')
            .annotate(
                avg=Avg('average_marks'),
                student_count=Count('id'),
            )
            .order_by('-avg')
        )

        # Subject averages across school
        subject_averages = (
            AssessmentMark.objects.filter(
                assessment__school=school,
                assessment__academic_term=term,
                is_absent=False,
                marks_obtained__isnull=False,
            )
            .values('assessment__subject__name')
            .annotate(avg=Avg('marks_obtained'))
            .order_by('-avg')
        )

        # Top 10 and bottom 10 students (anonymised for non-directors)
        sorted_results = results.order_by('-average_marks')
        top_10 = [
            {
                'student_name': r.student.get_full_name(),
                'class': r.class_group.name,
                'average': float(r.average_marks),
                'rank': r.class_rank,
            }
            for r in sorted_results[:10]
        ]
        bottom_10 = [
            {
                'student_name': r.student.get_full_name(),
                'class': r.class_group.name,
                'average': float(r.average_marks),
                'rank': r.class_rank,
            }
            for r in sorted_results.order_by('average_marks')[:10]
        ]

        # School-wide average
        school_average = results.aggregate(avg=Avg('average_marks'))['avg'] or 0

        return Response({
            'term': str(term),
            'school_average_pct': round(float(school_average), 1),
            'total_students_assessed': results.count(),
            'class_averages': list(class_averages),
            'subject_averages': list(subject_averages),
            'top_10_students': top_10,
            'bottom_10_students': bottom_10,
        })


# ---------------------------------------------------------------------------
# US-055: Fee collection trend chart
# ---------------------------------------------------------------------------

class FeeCollectionTrendView(APIView):
    """
    US-055: Daily fee collection trend for the current term.
    Returns one data point per school day with cumulative and daily totals.
    """
    permission_classes = [IsDirectorOrBursar]

    def get(self, request):
        from payments.models import Payment, FeeRecord
        from django.db.models import Sum
        import datetime

        school = request.user.school
        term_id = request.query_params.get('term_id')

        if term_id:
            from schools.models import AcademicTerm
            try:
                term = AcademicTerm.objects.get(id=term_id, school=school)
            except AcademicTerm.DoesNotExist:
                return Response({'error': 'Term not found.'}, status=404)
        else:
            term = school.terms.filter(is_current=True).first()

        if not term:
            return Response({'error': 'No current term.'}, status=400)

        # Total expected for target line
        total_expected = FeeRecord.all_objects.filter(
            school=school, academic_term=term
        ).aggregate(total=Sum('total_amount'))['total'] or 0

        # Daily collections from term start to today
        today = timezone.localdate()
        end_date = min(term.end_date, today)
        current = term.start_date
        daily_data = []
        cumulative = 0

        while current <= end_date:
            day_total = Payment.all_objects.filter(
                school=school,
                payment_date__date=current,
                status='completed',
                is_reversed=False,
            ).aggregate(total=Sum('amount'))['total'] or 0

            cumulative += day_total
            daily_data.append({
                'date': str(current),
                'daily_ugx': int(day_total),
                'cumulative_ugx': int(cumulative),
                'is_school_day': current.weekday() < 5,
            })
            current += datetime.timedelta(days=1)

        # Compute daily target line (even spread across term school days)
        term_days = (term.end_date - term.start_date).days + 1
        school_days = max(1, sum(
            1 for i in range(term_days)
            if (term.start_date + datetime.timedelta(days=i)).weekday() < 5
        ))
        daily_target = int(total_expected / school_days) if school_days else 0

        return Response({
            'term': str(term),
            'term_start': str(term.start_date),
            'term_end': str(term.end_date),
            'total_expected_ugx': int(total_expected),
            'total_collected_ugx': int(cumulative),
            'collection_rate_pct': round(cumulative / total_expected * 100, 1) if total_expected else 0,
            'daily_target_ugx': daily_target,
            'data': daily_data,
        })


# ---------------------------------------------------------------------------
# US-056: Term-end financial summary report
# ---------------------------------------------------------------------------

class TermFinancialSummaryView(APIView):
    """
    US-056: Term-end financial summary combining all payment types.
    Returns structured data for PDF generation on the frontend.
    Includes: total expected, MoMo + manual collections, waivers,
    net collection, collection rate, breakdown by class and fee category.
    """
    permission_classes = [IsDirector]

    def get(self, request):
        from payments.models import Payment, FeeRecord, FeeWaiver
        from django.db.models import Sum, Count, Q

        school = request.user.school
        term_id = request.query_params.get('term_id')

        if term_id:
            from schools.models import AcademicTerm
            try:
                term = AcademicTerm.objects.get(id=term_id, school=school)
            except AcademicTerm.DoesNotExist:
                return Response({'error': 'Term not found.'}, status=404)
        else:
            term = school.terms.filter(is_current=True).first()

        if not term:
            return Response({'error': 'No current term.'}, status=400)

        # Overall totals
        records = FeeRecord.all_objects.filter(school=school, academic_term=term)
        totals = records.aggregate(
            total_expected=Sum('total_amount'),
            total_collected=Sum('amount_paid'),
            total_waived=Sum('amount_waived'),
            total_students=Count('id'),
            fully_paid=Count('id', filter=Q(
                amount_paid__gte=models_F('total_amount') - models_F('amount_waived')
            )),
        )

        # Split by payment channel
        payments = Payment.all_objects.filter(
            school=school,
            fee_record__academic_term=term,
            status='completed',
            is_reversed=False,
        )
        channel_breakdown = payments.values('method').annotate(
            total=Sum('amount'), count=Count('id')
        ).order_by('-total')

        # Breakdown by class
        class_breakdown = (
            records.values(
                'student__current_class__name',
                'student__current_class__level',
            )
            .annotate(
                expected=Sum('total_amount'),
                collected=Sum('amount_paid'),
                waived=Sum('amount_waived'),
                students=Count('id'),
            )
            .order_by('student__current_class__level', 'student__current_class__name')
        )

        # Total reversals
        reversals = Payment.all_objects.filter(
            school=school,
            fee_record__academic_term=term,
            is_reversed=True,
        ).aggregate(total=Sum('amount'), count=Count('id'))

        expected = totals['total_expected'] or 0
        collected = totals['total_collected'] or 0
        waived = totals['total_waived'] or 0
        net = collected - (reversals['total'] or 0)

        return Response({
            'school': school.name,
            'term': str(term),
            'term_start': str(term.start_date),
            'term_end': str(term.end_date),
            'fee_deadline': str(term.fee_deadline),
            'generated_at': timezone.now().isoformat(),
            'totals': {
                'total_expected_ugx': int(expected),
                'total_collected_ugx': int(collected),
                'total_waived_ugx': int(waived),
                'total_reversals_ugx': int(reversals['total'] or 0),
                'net_collected_ugx': int(net),
                'collection_rate_pct': round(collected / expected * 100, 1) if expected else 0,
                'total_students': totals['total_students'] or 0,
                'fully_paid_students': totals['fully_paid'] or 0,
            },
            'by_payment_channel': list(channel_breakdown),
            'by_class': list(class_breakdown),
        })


# Import needed for term summary annotate
from django.db.models import F as models_F
