"""
Schools views — CRUD for school, terms, holidays, MoMo config.
"""
import secrets
from django.utils import timezone
from rest_framework import viewsets, status, serializers
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.exceptions import ValidationError, NotFound
from config.validators import validate_uuid, validate_int
from drf_spectacular.utils import extend_schema, OpenApiParameter, OpenApiTypes, inline_serializer
from .models import School, AcademicYear, AcademicTerm, HolidayPeriod, SchoolMoMoConfig, Timetable
from .serializers import (
    SchoolSerializer, AcademicYearSerializer, AcademicTermSerializer,
    HolidayPeriodSerializer, SchoolMoMoConfigSerializer, TimetableSerializer,
)
from .permissions import IsSystemAdmin, IsDirector, IsSchoolStaff
from audit.mixins import AuditMixin


class SchoolViewSet(AuditMixin, viewsets.ModelViewSet):
    queryset = School.objects.none()
    """US-001: School management — SystemAdmin only."""
    serializer_class = SchoolSerializer
    permission_classes = [IsSystemAdmin]

    def get_queryset(self):
        return School.objects.filter(is_active=True)

    def perform_create(self, serializer):
        school = serializer.save(onboarded_by=str(self.request.user.id))
        self.log_action('SCHOOL_CREATED', school, {'name': school.name})


class AcademicYearViewSet(AuditMixin, viewsets.ModelViewSet):
    queryset = AcademicYear.objects.none()
    serializer_class = AcademicYearSerializer
    pagination_class = None

    def get_permissions(self):
        if self.action in ('list', 'retrieve'):
            return [IsSchoolStaff()]
        return [IsDirector()]

    def get_queryset(self):
        return AcademicYear.objects.filter(school=self.request.user.school).order_by('-year')

    def perform_create(self, serializer):
        yr = serializer.save(school=self.request.user.school)
        self.log_action('ACADEMIC_YEAR_CREATED', yr, {'year': yr.year})


class AcademicTermViewSet(AuditMixin, viewsets.ModelViewSet):
    queryset = AcademicTerm.objects.none()
    """
    US-013: Terms drive all Celery scheduling.
    Activation auto-generates FeeRecords for all students.
    """
    serializer_class = AcademicTermSerializer
    pagination_class = None

    def get_permissions(self):
        if self.action in ('list', 'retrieve'):
            return [IsSchoolStaff()]
        return [IsDirector()]

    def get_queryset(self):
        return AcademicTerm.objects.filter(school=self.request.user.school).select_related('academic_year').order_by('-academic_year__year', 'term_number')

    def perform_create(self, serializer):
        term = serializer.save(school=self.request.user.school)
        self.log_action('TERM_CREATED', term, {'name': term.name})

    @extend_schema(
        responses={200: inline_serializer(name='ActivateTermResponse', fields={'message': serializers.CharField()})},
        tags=['Schools']
    )
    @action(detail=True, methods=['post'], permission_classes=[IsDirector])
    def activate(self, request, pk=None):
        """
        Activate a term: generates FeeRecords for all active students,
        schedules fee reminders via Celery.
        """
        term = self.get_object()
        if term.is_active:
            return Response({'error': 'Term is already active.'}, status=400)

        from payments.services import FeeService
        from automation.tasks import schedule_fee_reminders

        FeeService.generate_fee_records_for_term(term)
        term.is_active = True
        term.is_current = True
        term.activated_at = timezone.now()
        term.activated_by = request.user
        term.save()

        schedule_fee_reminders.delay(str(term.pk))
        self.log_action('TERM_ACTIVATED', term, {'term': term.name})
        return Response({'message': f'Term {term.name} activated. Fee records generated.'})

    @extend_schema(
        responses={200: inline_serializer(name='DeactivateTermResponse', fields={'message': serializers.CharField()})},
        tags=['Schools']
    )
    @action(detail=True, methods=['post'], permission_classes=[IsDirector])
    def deactivate(self, request, pk=None):
        term = self.get_object()
        term.is_active = False
        term.is_current = False
        term.save()
        self.log_action('TERM_DEACTIVATED', term, {})
        return Response({'message': f'Term {term.name} deactivated.'})


class HolidayPeriodViewSet(AuditMixin, viewsets.ModelViewSet):
    queryset = HolidayPeriod.objects.none()
    """US-063: Holiday periods suppress all automated messaging."""
    serializer_class = HolidayPeriodSerializer
    permission_classes = [IsDirector]

    def get_queryset(self):
        return HolidayPeriod.objects.filter(school=self.request.user.school)

    def perform_create(self, serializer):
        h = serializer.save(school=self.request.user.school)
        self.log_action('HOLIDAY_CREATED', h, {'name': h.name})


class SchoolMoMoConfigViewSet(AuditMixin, viewsets.ModelViewSet):
    queryset = SchoolMoMoConfig.objects.none()
    """
    US-031: MoMo credential management.
    Credentials stored encrypted; never returned in responses.
    """
    serializer_class = SchoolMoMoConfigSerializer
    permission_classes = [IsDirector]

    def get_queryset(self):
        return SchoolMoMoConfig.objects.filter(school=self.request.user.school)

    def perform_create(self, serializer):
        # Generate a unique HMAC signing key per school+provider
        signing_key = secrets.token_hex(32)
        cfg = serializer.save(
            school=self.request.user.school,
            webhook_signing_key=signing_key,
        )
        self.log_action('MOMO_CONFIG_CREATED', cfg, {'provider': cfg.provider})

    @extend_schema(
        responses={200: inline_serializer(
            name='TestMoMoConnectionResponse',
            fields={
                'success': serializers.BooleanField(),
                'message': serializers.CharField(),
            }
        )},
        tags=['Schools']
    )
    @action(detail=True, methods=['post'], url_path='test-connection')
    def test_connection(self, request, pk=None):
        """Test MoMo API credentials are valid."""
        from payments.services import MoMoService
        cfg = self.get_object()
        result = MoMoService.test_credentials(cfg)
        if result['success']:
            cfg.last_tested_at = timezone.now()
            cfg.save(update_fields=['last_tested_at'])
        return Response(result)


class DistrictBenchmarkView(APIView):
    """
    US-057: Compare school performance vs district averages.
    Optimised to avoid N+1 query loop across district schools (RISK-P5A).
    """
    permission_classes = [IsDirector]

    @extend_schema(
        responses={
            200: inline_serializer(
                name='DistrictBenchmarkResponse',
                fields={
                    'school_name': serializers.CharField(),
                    'district': serializers.CharField(),
                    'school_collection_rate': serializers.FloatField(),
                    'district_average_collection_rate': serializers.FloatField(allow_null=True),
                    'schools_in_district': serializers.IntegerField(),
                    'above_district_average': serializers.BooleanField(allow_null=True),
                }
            )
        }
    )
    def get(self, request):
        from payments.services import FeeService
        school = request.user.school
        term = school.terms.filter(is_current=True).first()
        if not term:
            return Response({'error': 'No current term.'}, status=400)

        school_summary = FeeService.get_dashboard_summary(school, term)
        school_rate = round(
            (school_summary.get('total_collected') or 0) /
            (school_summary.get('total_expected') or 1) * 100, 1
        )

        from schools.models import School, AcademicTerm
        from payments.models import FeeRecord
        from django.db.models import Sum

        # Fetch current terms of active schools in same district in one query
        current_terms_qs = AcademicTerm.objects.filter(
            school__district=school.district,
            school__is_active=True,
            is_current=True
        ).exclude(school=school)

        # Aggregate total_expected and total_collected grouped by term in one query
        school_rates = FeeRecord.all_objects.filter(
            academic_term__in=current_terms_qs
        ).values('academic_term').annotate(
            total_expected=Sum('total_amount'),
            total_collected=Sum('amount_paid')
        )

        district_rates = []
        for s_summary in school_rates:
            expected = s_summary.get('total_expected') or 0
            collected = s_summary.get('total_collected') or 0
            rate = round((collected / expected) * 100, 1) if expected > 0 else 0.0
            district_rates.append(rate)

        district_avg = round(sum(district_rates) / len(district_rates), 1) if district_rates else None

        return Response({
            'school_name': school.name,
            'district': school.district,
            'school_collection_rate': school_rate,
            'district_average_collection_rate': district_avg,
            'schools_in_district': len(district_rates),
            'above_district_average': school_rate > district_avg if district_avg else None,
        })



class TimetableViewSet(AuditMixin, viewsets.ModelViewSet):
    queryset = Timetable.objects.none()
    """Manage class timetable content used by parent messaging commands."""
    serializer_class = TimetableSerializer

    def get_permissions(self):
        if self.action in ['list', 'retrieve']:
            permission_classes = [IsSchoolStaff]
        else:
            permission_classes = [IsDirector]
        return [permission() for permission in permission_classes]

    def get_queryset(self):
        qs = Timetable.objects.filter(school=self.request.user.school).select_related('class_group')
        class_id = self.request.query_params.get('class_id')
        if class_id:
            validate_int(class_id, 'class_id')
            qs = qs.filter(class_group_id=class_id)
        is_active = self.request.query_params.get('is_active')
        if is_active in ['true', 'false']:
            qs = qs.filter(is_active=(is_active == 'true'))
        return qs

    def perform_create(self, serializer):
        obj = serializer.save(school=self.request.user.school, created_by=self.request.user)
        self.log_action('TIMETABLE_CREATED', obj, {'class_group': obj.class_group.name})

    def perform_update(self, serializer):
        obj = serializer.save()
        self.log_action('TIMETABLE_UPDATED', obj, {'class_group': obj.class_group.name})

    def perform_destroy(self, instance):
        self.log_action('TIMETABLE_DELETED', instance, {'class_group': instance.class_group.name})

    @extend_schema(
        responses={200: inline_serializer(
            name='TimetableDashboardResponse',
            fields={
                'total_timetables': serializers.IntegerField(),
                'active_timetables': serializers.IntegerField(),
            }
        )},
        tags=['Schools']
    )
    @action(detail=False, methods=['get'])
    def dashboard(self, request):
        qs = self.get_queryset()
        total = qs.count()
        active = qs.filter(is_active=True).count()
        
        return Response({
            'total_timetables': total,
            'active_timetables': active,
        })


class SchoolSettingsView(AuditMixin, APIView):
    """
    School profile, notification preferences, and term configuration settings.
    """
    permission_classes = [IsDirector]

    def get(self, request):
        school = request.user.school
        term = school.terms.filter(is_current=True).first() or school.terms.first()
        pause = school.messaging_pauses.filter(is_active=True).first()

        return Response({
            'name': school.name,
            'registration_number': school.registration_number or '',
            'district': school.district or '',
            'head_teacher': getattr(school, 'head_teacher', '') or '',
            'phone': school.phone or '',
            'email': school.email or '',
            'term_start_date': str(term.start_date) if term else '',
            'term_end_date': str(term.end_date) if term else '',
            'messaging_window_start': getattr(school, 'messaging_window_start', '08:00'),
            'messaging_window_end': getattr(school, 'messaging_window_end', '21:00'),
            'whatsapp_pause_reason': pause.reason if pause else '',
            'whatsapp_paused_until': str(pause.end_date) if pause else '',
        })

    def patch(self, request):
        school = request.user.school
        data = request.data

        # Update school fields
        for field in ['name', 'registration_number', 'district', 'phone', 'email']:
            if field in data and data[field] is not None:
                setattr(school, field, data[field])
        school.save()

        # Update term dates if supplied
        term = school.terms.filter(is_current=True).first()
        if term:
            if 'term_start_date' in data and data['term_start_date']:
                term.start_date = data['term_start_date']
            if 'term_end_date' in data and data['term_end_date']:
                term.end_date = data['term_end_date']
            term.save()

        self.log_action('SCHOOL_SETTINGS_UPDATED', school, {'updated_fields': list(data.keys())})
        return self.get(request)

