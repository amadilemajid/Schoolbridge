"""
Schools views — CRUD for school, terms, holidays, MoMo config.
"""
import secrets
from django.utils import timezone
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from .models import School, AcademicYear, AcademicTerm, HolidayPeriod, SchoolMoMoConfig
from .serializers import (
    SchoolSerializer, AcademicYearSerializer, AcademicTermSerializer,
    HolidayPeriodSerializer, SchoolMoMoConfigSerializer,
)
from .permissions import IsSystemAdmin, IsDirector, IsSchoolStaff
from audit.mixins import AuditMixin


class SchoolViewSet(AuditMixin, viewsets.ModelViewSet):
    """US-001: School management — SystemAdmin only."""
    serializer_class = SchoolSerializer
    permission_classes = [IsSystemAdmin]

    def get_queryset(self):
        return School.objects.filter(is_active=True)

    def perform_create(self, serializer):
        school = serializer.save(onboarded_by=str(self.request.user.id))
        self.log_action('SCHOOL_CREATED', school, {'name': school.name})


class AcademicYearViewSet(AuditMixin, viewsets.ModelViewSet):
    serializer_class = AcademicYearSerializer
    permission_classes = [IsDirector]

    def get_queryset(self):
        return AcademicYear.objects.filter(school=self.request.user.school)

    def perform_create(self, serializer):
        yr = serializer.save(school=self.request.user.school)
        self.log_action('ACADEMIC_YEAR_CREATED', yr, {'year': yr.year})


class AcademicTermViewSet(AuditMixin, viewsets.ModelViewSet):
    """
    US-013: Terms drive all Celery scheduling.
    Activation auto-generates FeeRecords for all students.
    """
    serializer_class = AcademicTermSerializer
    permission_classes = [IsDirector]

    def get_queryset(self):
        return AcademicTerm.objects.filter(school=self.request.user.school).select_related('academic_year')

    def perform_create(self, serializer):
        term = serializer.save(school=self.request.user.school)
        self.log_action('TERM_CREATED', term, {'name': term.name})

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

    @action(detail=True, methods=['post'], permission_classes=[IsDirector])
    def deactivate(self, request, pk=None):
        term = self.get_object()
        term.is_active = False
        term.is_current = False
        term.save()
        self.log_action('TERM_DEACTIVATED', term, {})
        return Response({'message': f'Term {term.name} deactivated.'})


class HolidayPeriodViewSet(AuditMixin, viewsets.ModelViewSet):
    """US-063: Holiday periods suppress all automated messaging."""
    serializer_class = HolidayPeriodSerializer
    permission_classes = [IsDirector]

    def get_queryset(self):
        return HolidayPeriod.objects.filter(school=self.request.user.school)

    def perform_create(self, serializer):
        h = serializer.save(school=self.request.user.school)
        self.log_action('HOLIDAY_CREATED', h, {'name': h.name})


class SchoolMoMoConfigViewSet(AuditMixin, viewsets.ModelViewSet):
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

    @action(detail=True, methods=['post'])
    def test_connection(self, request, pk=None):
        """Test MoMo API credentials are valid."""
        from payments.services import MoMoService
        cfg = self.get_object()
        result = MoMoService.test_credentials(cfg)
        if result['success']:
            cfg.last_tested_at = timezone.now()
            cfg.save(update_fields=['last_tested_at'])
        return Response(result)
