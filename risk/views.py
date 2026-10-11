"""
At-Risk Student Intelligence Engine — API Views.

Provides endpoints for:
  - Risk configuration management
  - At-risk student listing with filters
  - Manual recalculation trigger
  - Monday morning briefing
  - Student risk trend data
"""
from rest_framework import generics, status, views
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from schools.permissions import IsDirector, IsSchoolStaff
from rest_framework.exceptions import ValidationError, NotFound
from config.validators import validate_uuid, validate_int
from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import serializers

from audit.models import AuditLog
from risk.models import RiskConfiguration, StudentRiskProfile, StudentRiskSnapshot
from risk.serializers import (
    RiskConfigurationSerializer,
    StudentRiskProfileSerializer,
    StudentRiskSnapshotSerializer,
)
from risk.services import RiskEvaluationEngine
from schools.models import AcademicTerm


class RiskConfigurationView(generics.RetrieveUpdateAPIView):
    """
    GET: Retrieve the school's risk thresholds.
    PATCH/PUT: Update risk thresholds.
    """
    permission_classes = [IsAuthenticated, IsDirector]
    serializer_class = RiskConfigurationSerializer

    def get_object(self):
        config, _ = RiskConfiguration.objects.get_or_create(
            school=self.request.user.school
        )
        return config

    def perform_update(self, serializer):
        before = RiskConfigurationSerializer(self.get_object()).data
        instance = serializer.save()
        AuditLog.log(
            actor=self.request.user,
            school=self.request.user.school,
            category='SCHOOL',
            action='RISK_CONFIG_UPDATED',
            description='Risk thresholds updated',
            target=instance,
            before=before,
            after=serializer.data,
            request=self.request,
        )


class AtRiskStudentListView(generics.ListAPIView):
    """
    List students with their cached risk profiles.
    Supports filtering by risk_level, class_group, and factor.
    Ordered by worst risk score first.
    """
    permission_classes = [IsAuthenticated, IsSchoolStaff]
    serializer_class = StudentRiskProfileSerializer

    def get_queryset(self):
        school = self.request.user.school
        qs = StudentRiskProfile.all_objects.filter(
            school=school
        ).select_related('student', 'student__current_class')

        # Filters
        risk_level = self.request.query_params.get('risk_level')
        class_group = self.request.query_params.get('class_group')
        factor = self.request.query_params.get('factor')

        if risk_level:
            qs = qs.filter(risk_level=risk_level)
        if class_group:
            validate_int(class_group, 'class_group')
            qs = qs.filter(student__current_class_id=class_group)
        if factor:
            qs = qs.filter(flagged_factors__contains=factor)

        return qs.order_by('-risk_score')


class TriggerRecalculationView(views.APIView):
    """POST: Manually trigger risk recalculation for the school."""
    permission_classes = [IsAuthenticated, IsSchoolStaff]

    @extend_schema(
        request=None,
        responses={
            200: inline_serializer(
                name='TriggerRecalculationResponse',
                fields={
                    'status': serializers.CharField(),
                    'students_evaluated': serializers.IntegerField(),
                    'high_risk_count': serializers.IntegerField(),
                    'medium_risk_count': serializers.IntegerField(),
                }
            )
        }
    )
    def post(self, request, *args, **kwargs):
        school = request.user.school
        active_term = AcademicTerm.objects.filter(
            school=school, is_active=True
        ).first()

        if not active_term:
            raise ValidationError('No active term configured')

        profiles = RiskEvaluationEngine.recalculate_school(school, active_term)

        AuditLog.log(
            actor=request.user,
            school=school,
            category='SYSTEM',
            action='RISK_MANUAL_RECALCULATION',
            description=f'Manual recalculation: {len(profiles)} students',
            request=request,
        )

        high = sum(1 for p in profiles if p.risk_level == 'high')
        medium = sum(1 for p in profiles if p.risk_level == 'medium')

        return Response({
            'status': 'Recalculation completed successfully',
            'students_evaluated': len(profiles),
            'high_risk_count': high,
            'medium_risk_count': medium,
        })


class MondayBriefingView(views.APIView):
    """GET: Retrieve the Monday morning briefing summary."""
    permission_classes = [IsAuthenticated, IsSchoolStaff]

    @extend_schema(
        responses={
            200: inline_serializer(
                name='MondayBriefingResponse',
                fields={
                    'school': serializers.CharField(),
                    'term': serializers.CharField(),
                    'generated_at': serializers.DateTimeField(),
                    'total_students_evaluated': serializers.IntegerField(),
                    'high_risk_count': serializers.IntegerField(),
                    'medium_risk_count': serializers.IntegerField(),
                    'attendance_alerts': serializers.ListField(child=serializers.DictField()),
                    'fee_alerts': serializers.ListField(child=serializers.DictField()),
                }
            )
        }
    )
    def get(self, request, *args, **kwargs):
        school = request.user.school
        active_term = AcademicTerm.objects.filter(
            school=school, is_active=True
        ).first()

        if not active_term:
            raise ValidationError('No active term configured')

        summary = RiskEvaluationEngine.get_monday_briefing(school, active_term)
        return Response(summary)


class RiskTrendView(generics.ListAPIView):
    """
    GET: Retrieve risk trend snapshots for a specific student.
    Used for trend charts on the dashboard.
    """
    permission_classes = [IsAuthenticated, IsSchoolStaff]
    serializer_class = StudentRiskSnapshotSerializer

    def get_queryset(self):
        student_id = self.kwargs['student_id']
        school = self.request.user.school

        return StudentRiskSnapshot.all_objects.filter(
            student_id=student_id,
            school=school,
        ).order_by('snapshot_date')
