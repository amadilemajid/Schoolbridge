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
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework import serializers as drf_serializers
from rest_framework.exceptions import ValidationError, NotFound
from config.validators import validate_int
from drf_spectacular.utils import extend_schema, OpenApiParameter, OpenApiTypes, inline_serializer

from audit.mixins import AuditMixin
from schools.permissions import IsDirector, IsDirectorOrBursar

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

    @extend_schema(
        responses={200: inline_serializer(
            name='MessagingPauseListResponse',
            fields={
                'id': drf_serializers.IntegerField(),
                'start_date': drf_serializers.DateField(),
                'end_date': drf_serializers.DateField(),
                'reason': drf_serializers.CharField(),
                'is_active': drf_serializers.BooleanField(),
                'dropped_tasks_count': drf_serializers.IntegerField(),
                'dropped_tasks_summary': drf_serializers.JSONField(),
                'created_at': drf_serializers.DateTimeField(),
                'ended_at': drf_serializers.DateTimeField(allow_null=True),
            },
            many=True
        )},
        tags=['Automation']
    )
    def get(self, request):
        from schools.models import MessagingPause
        pauses = MessagingPause.objects.filter(school=request.user.school).values(
            'id', 'start_date', 'end_date', 'reason', 'is_active',
            'dropped_tasks_count', 'dropped_tasks_summary', 'created_at', 'ended_at'
        )
        return Response(list(pauses))

    @extend_schema(
        request=MessagingPauseSerializer,
        responses={201: inline_serializer(
            name='MessagingPauseCreateResponse',
            fields={
                'id': drf_serializers.IntegerField(),
                'message': drf_serializers.CharField(),
            }
        )},
        tags=['Automation']
    )
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

    @extend_schema(
        request=None,
        responses={200: inline_serializer(
            name='MessagingPauseEndResponse',
            fields={
                'message': drf_serializers.CharField(),
                'dropped_tasks_count': drf_serializers.IntegerField(),
                'dropped_tasks_summary': drf_serializers.JSONField(),
            }
        )},
        tags=['Automation']
    )
    def post(self, request, pause_id):
        from schools.models import MessagingPause
        try:
            pause = MessagingPause.objects.get(
                id=pause_id, school=request.user.school, is_active=True
            )
        except MessagingPause.DoesNotExist:
            raise NotFound('Active pause not found.')

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
    US-054: Combined school operations overview dashboard.
    Returns today's collections, attendance rate, pending reconciliation,
    unread alerts, WhatsApp delivery stats, collection trends, and class breakdown.
    Data refreshes every 5 minutes (cache-backed).
    """
    permission_classes = [IsDirectorOrBursar]

    def get(self, request):
        from django.core.cache import cache
        school = request.user.school
        cache_key = f'ops_dashboard:{school.id}'
        if request.query_params.get('refresh') == 'true':
            cache.delete(cache_key)
        else:
            cached = cache.get(cache_key)
            if cached:
                return Response(cached)

        data = self._build_dashboard(school)
        cache.set(cache_key, data, timeout=60)  # 1-minute cache for snappy live updates
        return Response(data)

    def _build_dashboard(self, school):
        from payments.models import Payment, ReconciliationQueue, FeeRecord
        from attendance.models import AttendanceRecord
        from notifications.models import Notification
        from students.models import Student, ClassGroup
        from django.db.models import Sum, Count, Q, F
        from django.db.models.functions import TruncDate
        from datetime import timedelta
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
        collection_rate = 0.0
        total_expected = 0
        total_collected = 0
        if term:
            agg = FeeRecord.all_objects.filter(
                school=school, academic_term=term
            ).aggregate(
                expected=Sum('total_amount'),
                collected=Sum('amount_paid'),
            )
            total_expected = int(agg['expected'] or 0)
            total_collected = int(agg['collected'] or 0)
            collection_rate = round(
                total_collected / total_expected * 100, 1
            ) if total_expected else 0.0

        outstanding_revenue = max(0, total_expected - total_collected)

        # Today's school-wide attendance rate
        attendance_rate = None
        if term:
            total_attendance_records = AttendanceRecord.all_objects.filter(
                school=school, date=today
            ).count()
            present = AttendanceRecord.all_objects.filter(
                school=school, date=today, status__in=['present', 'late']
            ).count()
            attendance_rate = round(
                present / total_attendance_records * 100, 1
            ) if total_attendance_records else None

        # Active students count
        active_students = Student.objects.filter(school=school, is_active=True).count()

        # Defaulters count (students with remaining balance > 0 in current term)
        defaulters_count = 0
        if term:
            defaulters_count = FeeRecord.all_objects.filter(
                school=school, academic_term=term, total_amount__gt=F('amount_paid') + F('amount_waived')
            ).count()

        # Continuous 14-day payment trend data (always generates 14 days chronologically)
        fourteen_days_ago = today - timedelta(days=13)
        recent_payments = Payment.all_objects.filter(
            school=school,
            status='completed',
            is_reversed=False,
            payment_date__date__gte=fourteen_days_ago,
            payment_date__date__lte=today,
        ).annotate(p_date=TruncDate('payment_date')).values('p_date').annotate(
            amount=Sum('amount')
        ).order_by('p_date')

        payment_map = {
            p['p_date']: int(p['amount'] or 0)
            for p in recent_payments if p.get('p_date')
        }

        trend_data = [
            {
                'date': (today - timedelta(days=i)).strftime('%d %b'),
                'amount': payment_map.get(today - timedelta(days=i), 0)
            }
            for i in range(13, -1, -1)
        ]

        # Low collection classes breakdown
        low_classes = []
        if term:
            classes = ClassGroup.objects.filter(school=school)
            for cg in classes:
                c_agg = FeeRecord.all_objects.filter(
                    school=school, academic_term=term, student__current_class=cg
                ).aggregate(
                    expected=Sum('total_amount'),
                    collected=Sum('amount_paid')
                )
                exp = int(c_agg['expected'] or 0)
                col = int(c_agg['collected'] or 0)
                if exp > 0:
                    rate = round(col / exp * 100, 1)
                    low_classes.append({
                        'class_name': cg.name,
                        'expected': exp,
                        'collected': col,
                        'rate': rate
                    })
            low_classes.sort(key=lambda x: x['rate'])

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
            # Frontend overview fields
            'total_revenue_collected': total_collected,
            'expected_revenue': total_expected,
            'outstanding_revenue': outstanding_revenue,
            'collection_rate': collection_rate,
            'active_students': active_students,
            'attendance_rate_today': attendance_rate if attendance_rate is not None else 0.0,
            'high_risk_defaulters_count': defaulters_count,
            'total_defaulters_count': defaulters_count,
            'trend_data': trend_data,
            'low_collection_classes': low_classes[:5],
            # Legacy operations dashboard fields
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

    @extend_schema(
        parameters=[
            OpenApiParameter('term_id', OpenApiTypes.UUID, OpenApiParameter.QUERY, required=False),
        ],
        responses={200: inline_serializer(
            name='AcademicDashboardResponse',
            fields={
                'term': drf_serializers.CharField(),
                'school_average_pct': drf_serializers.FloatField(),
                'total_students_assessed': drf_serializers.IntegerField(),
                'class_averages': drf_serializers.JSONField(),
                'subject_averages': drf_serializers.JSONField(),
                'top_10_students': drf_serializers.JSONField(),
                'bottom_10_students': drf_serializers.JSONField(),
            }
        )},
        tags=['Automation']
    )
    def get(self, request):
        from results.models import TermResult, AssessmentMark, Assessment
        from students.models import ClassGroup
        from django.db.models import Avg, Count

        school = request.user.school
        term_id = request.query_params.get('term_id')

        if term_id:
            validate_int(term_id, 'term_id')
            from schools.models import AcademicTerm
            try:
                term = AcademicTerm.objects.get(id=term_id, school=school)
            except (AcademicTerm.DoesNotExist, ValueError):
                raise NotFound('Term not found.')
        else:
            term = school.terms.filter(is_current=True).first()

        if not term:
            raise ValidationError('No current term.')

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

    @extend_schema(
        parameters=[
            OpenApiParameter('term_id', OpenApiTypes.UUID, OpenApiParameter.QUERY, required=False),
        ],
        responses={200: inline_serializer(
            name='FeeCollectionTrendResponse',
            fields={
                'term': drf_serializers.CharField(),
                'term_start': drf_serializers.DateField(),
                'term_end': drf_serializers.DateField(),
                'total_expected_ugx': drf_serializers.IntegerField(),
                'total_collected_ugx': drf_serializers.IntegerField(),
                'collection_rate_pct': drf_serializers.FloatField(),
                'daily_target_ugx': drf_serializers.IntegerField(),
                'data': drf_serializers.JSONField(),
            }
        )},
        tags=['Automation']
    )
    def get(self, request):
        from payments.models import Payment, FeeRecord
        from django.db.models import Sum
        import datetime

        school = request.user.school
        term_id = request.query_params.get('term_id')

        if term_id:
            validate_int(term_id, 'term_id')
            from schools.models import AcademicTerm
            try:
                term = AcademicTerm.objects.get(id=term_id, school=school)
            except (AcademicTerm.DoesNotExist, ValueError):
                raise NotFound('Term not found.')
        else:
            term = school.terms.filter(is_current=True).first()

        if not term:
            raise ValidationError('No current term.')

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

    @extend_schema(
        parameters=[
            OpenApiParameter('term_id', OpenApiTypes.UUID, OpenApiParameter.QUERY, required=False),
        ],
        responses={200: inline_serializer(
            name='TermFinancialSummaryResponse',
            fields={
                'school': drf_serializers.CharField(),
                'term': drf_serializers.CharField(),
                'term_start': drf_serializers.DateField(),
                'term_end': drf_serializers.DateField(),
                'fee_deadline': drf_serializers.DateField(),
                'generated_at': drf_serializers.DateTimeField(),
                'totals': drf_serializers.JSONField(),
                'by_payment_channel': drf_serializers.JSONField(),
                'by_class': drf_serializers.JSONField(),
            }
        )},
        tags=['Automation']
    )
    def get(self, request):
        from payments.models import Payment, FeeRecord, FeeWaiver
        from django.db.models import Sum, Count, Q

        school = request.user.school
        term_id = request.query_params.get('term_id')

        if term_id:
            validate_int(term_id, 'term_id')
            from schools.models import AcademicTerm
            try:
                term = AcademicTerm.objects.get(id=term_id, school=school)
            except (AcademicTerm.DoesNotExist, ValueError):
                raise NotFound('Term not found.')
        else:
            term = school.terms.filter(is_current=True).first()

        if not term:
            raise ValidationError('No current term.')

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
from rest_framework.permissions import IsAuthenticated


# ---------------------------------------------------------------------------
# Teacher Dashboard View: Real-time academic, attendance & timetable metrics
# ---------------------------------------------------------------------------

class TeacherDashboardView(APIView):
    """
    Real-time Teacher Dashboard API.
    Scoped to the authenticated teacher and their school.
    Returns:
      - Teacher profile and school context
      - Current academic term
      - Top KPIs (assigned classes, enrolled students, lessons today, absent students, pending marks)
      - Today's timetable schedule (chronological order)
      - Assigned form classes with live attendance marking status
      - Absent students roster today with primary guardian contacts
      - Pending assessment marks queue
    """
    permission_classes = [IsAuthenticated]

    @extend_schema(
        responses={200: inline_serializer(
            name='TeacherDashboardResponse',
            fields={
                'teacher': drf_serializers.JSONField(),
                'school': drf_serializers.JSONField(),
                'current_term': drf_serializers.JSONField(),
                'today_date': drf_serializers.CharField(),
                'today_day_name': drf_serializers.CharField(),
                'kpis': drf_serializers.JSONField(),
                'today_schedule': drf_serializers.JSONField(),
                'assigned_classes': drf_serializers.JSONField(),
                'absent_students_today': drf_serializers.JSONField(),
                'pending_marks': drf_serializers.JSONField(),
            }
        )},
        tags=['Automation']
    )
    def get(self, request):
        from students.models import ClassGroup, Student
        from timetable.models import TimetableSlot
        from attendance.models import AttendanceRecord
        from results.models import Assessment, AssessmentMark

        school = getattr(request.user, 'school', None)
        if not school:
            return Response({'error': 'User has no associated school.'}, status=status.HTTP_400_BAD_REQUEST)

        today = timezone.localdate()
        weekday = today.weekday()  # 0=Monday ... 4=Friday, 5=Saturday, 6=Sunday
        day_name = today.strftime('%A')

        # 1. Current Academic Term
        term = school.terms.filter(is_current=True).first()
        term_data = None
        if term:
            term_data = {
                'id': term.id,
                'name': term.name,
                'academic_year': term.academic_year.year if hasattr(term, 'academic_year') and term.academic_year else None,
                'term_number': term.term_number,
                'start_date': str(term.start_date),
                'end_date': str(term.end_date),
            }

        # 2. Assigned Form Classes (Classes where request.user is form_teacher)
        form_classes = ClassGroup.objects.filter(
            school=school,
            form_teacher=request.user,
            is_active=True
        ).order_by('level', 'stream')

        # All classes relevant to this teacher (form classes + timetable classes)
        timetable_class_ids = set(
            TimetableSlot.all_objects.filter(
                school=school,
                teacher=request.user
            ).values_list('timetable_version__class_group_id', flat=True)
        )
        relevant_class_ids = set(form_classes.values_list('id', flat=True)) | {cid for cid in timetable_class_ids if cid}

        assigned_classes_data = []
        total_students_in_form_classes = 0
        for cg in form_classes:
            student_count = Student.objects.filter(school=school, current_class=cg, is_active=True).count()
            total_students_in_form_classes += student_count

            # Check attendance today for this class
            att_records = AttendanceRecord.all_objects.filter(school=school, class_group=cg, date=today)
            is_marked = att_records.exists()
            p_cnt = att_records.filter(status='present').count()
            l_cnt = att_records.filter(status='late').count()
            a_cnt = att_records.filter(status='absent').count()
            e_cnt = att_records.filter(status='excused').count()
            tot_marked = p_cnt + l_cnt + a_cnt + e_cnt
            rate = round((p_cnt + l_cnt) / tot_marked * 100, 1) if tot_marked > 0 else (100.0 if is_marked else None)

            assigned_classes_data.append({
                'id': cg.id,
                'name': cg.name,
                'level': cg.level,
                'stream': cg.stream or '',
                'student_count': student_count,
                'attendance_today': {
                    'is_marked': is_marked,
                    'present_count': p_cnt,
                    'late_count': l_cnt,
                    'absent_count': a_cnt,
                    'excused_count': e_cnt,
                    'total_marked': tot_marked,
                    'attendance_rate': rate,
                }
            })

        # Teaching Classes (Classes taught by this teacher via timetable, not form class)
        teaching_classes_qs = ClassGroup.objects.filter(
            school=school,
            id__in=timetable_class_ids,
            is_active=True
        ).exclude(id__in=form_classes.values_list('id', flat=True)).order_by('level', 'stream')

        teaching_classes_data = []
        for t_cg in teaching_classes_qs:
            teaching_classes_data.append({
                'id': t_cg.id,
                'name': t_cg.name,
                'level': t_cg.level,
                'stream': t_cg.stream or '',
                'student_count': Student.objects.filter(school=school, current_class=t_cg, is_active=True).count(),
            })

        # 3. Scheduled Lessons (With Day Selector & Weekend Fallback)
        DAYS = [
            {'id': 0, 'name': 'Monday', 'short': 'Mon'},
            {'id': 1, 'name': 'Tuesday', 'short': 'Tue'},
            {'id': 2, 'name': 'Wednesday', 'short': 'Wed'},
            {'id': 3, 'name': 'Thursday', 'short': 'Thu'},
            {'id': 4, 'name': 'Friday', 'short': 'Fri'},
        ]

        day_param = request.query_params.get('day_of_week')
        is_weekend = weekday >= 5
        is_fallback = False

        if day_param is not None and day_param.isdigit():
            target_day = int(day_param) % 5
        elif not is_weekend:
            target_day = weekday
        else:
            # On Saturday/Sunday, default to Monday so teachers can preview upcoming lessons
            target_day = 0
            is_fallback = True

        today_slots = TimetableSlot.all_objects.filter(
            school=school,
            teacher=request.user,
            day_of_week=target_day,
            timetable_version__is_active=True,
        ).select_related('timetable_version__class_group', 'subject').order_by('period_number', 'start_time')

        today_schedule_data = []
        for slot in today_slots:
            cg = slot.timetable_version.class_group if slot.timetable_version else None
            today_schedule_data.append({
                'id': str(slot.id),
                'period_number': slot.period_number,
                'start_time': slot.start_time.strftime('%H:%M') if slot.start_time else '',
                'end_time': slot.end_time.strftime('%H:%M') if slot.end_time else '',
                'subject_name': slot.display_subject,
                'class_group_id': cg.id if cg else None,
                'class_group_name': cg.name if cg else 'N/A',
                'room': slot.room or 'Standard Classroom',
                'slot_type': slot.slot_type,
            })

        # 4. Absent Students Today (in teacher's form classes or today's classes)
        attendance_class_ids = set(form_classes.values_list('id', flat=True))
        if not attendance_class_ids and today_slots.exists():
            attendance_class_ids = {s.timetable_version.class_group_id for s in today_slots if s.timetable_version and s.timetable_version.class_group_id}

        absent_students_data = []
        if attendance_class_ids:
            absent_records = AttendanceRecord.all_objects.filter(
                school=school,
                class_group_id__in=attendance_class_ids,
                date=today,
                status='absent'
            ).select_related('student', 'class_group').prefetch_related('student__guardians').order_by('class_group__name', 'student__last_name')

            for rec in absent_records:
                primary_guardian = rec.student.guardians.filter(is_primary=True).first() or rec.student.guardians.first()
                g_name = f"{primary_guardian.first_name} {primary_guardian.last_name}".strip() if primary_guardian else "No Guardian Listed"
                g_phone = primary_guardian.phone if primary_guardian else ""
                absent_students_data.append({
                    'student_id': str(rec.student.id),
                    'student_name': rec.student.get_full_name(),
                    'reg_number': rec.student.student_id,
                    'class_group_name': rec.class_group.name,
                    'guardian_name': g_name,
                    'guardian_phone': g_phone,
                    'pre_excused': rec.pre_excused,
                    'notes': rec.notes or rec.pre_excused_reason or ('Parent Notified' if rec.pre_excused else 'Unexcused Absence'),
                })

        # 5. Pending Marks & Assessments
        pending_marks_data = []
        target_assess_class_ids = relevant_class_ids
        if not target_assess_class_ids and request.user.role != 'teacher':
            target_assess_class_ids = set(ClassGroup.objects.filter(school=school).values_list('id', flat=True)[:5])

        if target_assess_class_ids:
            assess_qs = Assessment.all_objects.filter(
                school=school,
                class_group_id__in=target_assess_class_ids,
                status__in=['draft', 'submitted', 'rejected']
            ).select_related('class_group', 'subject', 'academic_term').order_by('-created_at')[:15]

            for assess in assess_qs:
                stu_count = Student.objects.filter(school=school, current_class=assess.class_group, is_active=True).count()
                marks_entered = AssessmentMark.objects.filter(
                    assessment=assess,
                    marks_obtained__isnull=False
                ).count() + AssessmentMark.objects.filter(
                    assessment=assess,
                    is_absent=True
                ).count()
                comp_pct = round(marks_entered / stu_count * 100, 1) if stu_count > 0 else 0.0

                pending_marks_data.append({
                    'assessment_id': str(assess.id),
                    'name': assess.name,
                    'assessment_type': assess.get_assessment_type_display(),
                    'class_group_id': assess.class_group.id,
                    'class_group_name': assess.class_group.name,
                    'subject_id': assess.subject.id if assess.subject else None,
                    'subject_name': assess.subject.name if assess.subject else 'General',
                    'max_marks': assess.max_marks,
                    'status': assess.status,
                    'is_locked': assess.is_locked,
                    'marks_entered_count': marks_entered,
                    'total_students_count': stu_count,
                    'completion_pct': comp_pct,
                })

        # 6. Overall Teacher KPIs
        kpis = {
            'assigned_classes_count': form_classes.count(),
            'total_students_count': total_students_in_form_classes,
            'today_lessons_count': len(today_schedule_data),
            'absent_students_today_count': len(absent_students_data),
            'pending_assessments_count': len(pending_marks_data),
        }

        first_name = request.user.first_name or ''
        last_name = request.user.last_name or ''
        full_name = f"{first_name} {last_name}".strip() or request.user.email

        primary_form = form_classes.first()

        return Response({
            'teacher': {
                'id': str(request.user.id),
                'name': full_name,
                'email': request.user.email,
                'role': request.user.role,
                'phone': getattr(request.user, 'phone', ''),
            },
            'school': {
                'id': school.id,
                'name': school.name,
            },
            'current_term': term_data,
            'today_date': str(today),
            'today_day_name': day_name,
            'kpis': kpis,
            'schedule_day': {
                'id': target_day,
                'name': DAYS[target_day]['name'],
                'short': DAYS[target_day]['short'],
                'is_today': target_day == weekday,
                'is_weekend_fallback': is_fallback,
                'available_days': DAYS,
            },
            'primary_form_class': {
                'id': primary_form.id,
                'name': primary_form.name,
                'level': primary_form.level,
                'stream': primary_form.stream or '',
            } if primary_form else None,
            'today_schedule': today_schedule_data,
            'assigned_classes': assigned_classes_data,
            'teaching_classes': teaching_classes_data,
            'absent_students_today': absent_students_data,
            'pending_marks': pending_marks_data,
        })


# ---------------------------------------------------------------------------
# Generic Auto-Suggestion API
# ---------------------------------------------------------------------------

class AutoSuggestionView(APIView):
    """
    Generic auto-suggestion API for text fields across SchoolBridge.
    Merges school-level database records with Ugandan school domain presets.
    Supports categories:
      - excused_reasons
      - late_reasons
      - absence_reasons
      - attendance_notes
      - academic_remarks
      - rejection_reasons
      - unlock_reasons
      - waiver_reasons
      - deactivation_reasons
    """
    permission_classes = [IsAuthenticated]

    DOMAIN_PRESETS = {
        'excused_reasons': [
            'Parent called - family emergency',
            'Medical appointment / Clinic visit',
            'Sick with malaria / fever (Parent notified)',
            'School fee collection / Bank errand',
            'Official school sports / Music festival competition',
            'Bereavement / Attending burial ceremony',
            'Dental / Eye checkup',
            'Authorized pass-out granted by Head Teacher',
            'Floods / Impassable road after heavy rain',
            'National ID / UNEB registration errand',
            'Religious observance / Holiday',
            'Transport breakdown on school van',
        ],
        'late_reasons': [
            'Heavy morning rainfall / Road flooding',
            'Traffic congestion on main road',
            'Transport breakdown / Matatu delay',
            'Late walking from distant village',
            'Assisting guardian with urgent errand',
            'Delayed at clinic / Morning hospital visit',
            'Uniform / Scholastic materials preparation',
        ],
        'absence_reasons': [
            'Sick - Malaria / Fever (No note yet)',
            'Unannounced absence - Parent phone unreachable',
            'Family emergency / Travel upcountry',
            'School fees balance follow-up',
            'Hospitalized / Under medical care',
            'Absent without official communication',
        ],
        'attendance_notes': [
            'Parent notified via SMS / Phone call',
            'Clinic referral issued by nurse',
            'Disciplinary warning issued',
            'Special counseling required',
            'Scholastic assistance needed',
        ],
        'academic_remarks': [
            'Excellent performance; keeps up the good work',
            'Shows great improvement; encouraged to participate more',
            'Capable of better results with increased focus',
            'Needs more practice in numerical problem solving',
            'Good effort; should concentrate on handwriting & presentation',
            'Very attentive and disciplined in class',
            'Active in group discussions and practical work',
        ],
        'rejection_reasons': [
            'Marks entered exceed assessment paper maximum',
            'Missing scores for several enrolled candidates',
            'Grading scale or assessment weight mismatch',
            'Clerical calculation error detected in marks sheet',
            'Unapproved moderation adjustments submitted',
        ],
        'unlock_reasons': [
            'Correction of teacher clerical entry typo approved by Director',
            'Audit reconciliation following paper remark request',
            'Late medical submission verified by administration',
        ],
        'waiver_reasons': [
            'Director special scholarship discount',
            'Staff child tuition waiver',
            'Bursary awarded for sports / talent excellence',
            'Hardship relief approved by school board',
            'Sibling discount concession',
        ],
        'deactivation_reasons': [
            'Transferred to another school (Relocation)',
            'Completed final examination candidate cycle',
            'Prolonged unannounced absence / Dropped out',
            'Medical withdrawal upon guardian request',
            'Financial hardship relocation',
        ],
    }

    @extend_schema(
        parameters=[
            OpenApiParameter('category', OpenApiTypes.STR, description='Suggestion category', required=False),
            OpenApiParameter('query', OpenApiTypes.STR, description='Filter query string', required=False),
            OpenApiParameter('limit', OpenApiTypes.INT, description='Maximum number of suggestions', required=False),
        ],
        responses={200: inline_serializer(
            name='AutoSuggestionResponse',
            fields={
                'category': drf_serializers.CharField(),
                'query': drf_serializers.CharField(),
                'count': drf_serializers.IntegerField(),
                'suggestions': drf_serializers.ListField(child=drf_serializers.CharField()),
            }
        )},
        tags=['Automation']
    )
    def get(self, request):
        category = request.query_params.get('category', 'excused_reasons').strip().lower()
        query = (request.query_params.get('query') or request.query_params.get('q') or '').strip()
        try:
            limit = min(int(request.query_params.get('limit', 15)), 50)
        except (ValueError, TypeError):
            limit = 15

        school = getattr(request.user, 'school', None)
        db_items = []

        # 1. Fetch real historical reasons from tenant database
        if school:
            try:
                if category in ('excused_reasons', 'late_reasons', 'absence_reasons', 'attendance_notes'):
                    from attendance.models import AttendanceRecord
                    status_map = {
                        'excused_reasons': 'excused',
                        'late_reasons': 'late',
                        'absence_reasons': 'absent',
                    }
                    qs = AttendanceRecord.all_objects.filter(school=school)
                    if category in status_map:
                        qs = qs.filter(status=status_map[category])
                    notes = qs.exclude(notes='').values_list('notes', flat=True).distinct()[:25]
                    db_items.extend(list(notes))

                    if category == 'excused_reasons':
                        pre_excused = AttendanceRecord.all_objects.filter(
                            school=school, pre_excused=True
                        ).exclude(pre_excused_reason='').values_list('pre_excused_reason', flat=True).distinct()[:25]
                        db_items.extend(list(pre_excused))

                elif category == 'rejection_reasons':
                    from results.models import Assessment
                    rej = Assessment.all_objects.filter(
                        school=school, status='rejected'
                    ).exclude(rejection_reason='').values_list('rejection_reason', flat=True).distinct()[:25]
                    db_items.extend(list(rej))

                elif category == 'waiver_reasons':
                    from finance.models import FeeWaiver
                    waivers = FeeWaiver.objects.filter(
                        school=school
                    ).exclude(reason='').values_list('reason', flat=True).distinct()[:25]
                    db_items.extend(list(waivers))
            except Exception as e:
                logger.warning(f"Error fetching DB suggestions for {category}: {e}")

        # 2. Combine DB items with Domain Presets
        presets = self.DOMAIN_PRESETS.get(category, self.DOMAIN_PRESETS['excused_reasons'])
        combined = []
        seen = set()

        for item in (db_items + presets):
            cleaned = item.strip()
            if not cleaned:
                continue
            key = cleaned.lower()
            if key not in seen:
                seen.add(key)
                combined.append(cleaned)

        # 3. Filter by query substring if provided
        if query:
            q_lower = query.lower()
            # Prioritize items starting with query, then containing query
            starts = [c for c in combined if c.lower().startswith(q_lower)]
            contains = [c for c in combined if q_lower in c.lower() and not c.lower().startswith(q_lower)]
            filtered = starts + contains
        else:
            filtered = combined

        final_suggestions = filtered[:limit]

        return Response({
            'category': category,
            'query': query,
            'count': len(final_suggestions),
            'suggestions': final_suggestions,
        })


