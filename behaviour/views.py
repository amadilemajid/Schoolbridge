"""
Behaviour & Discipline views.
"""
import logging
from django.db.models import Count, Q, Sum
from django.utils import timezone
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.filters import SearchFilter, OrderingFilter
from rest_framework.response import Response
from rest_framework.views import APIView
from drf_spectacular.utils import extend_schema, OpenApiParameter
from drf_spectacular.types import OpenApiTypes

from audit.mixins import AuditMixin
from config.mixins import ExportMixin
from schools.permissions import IsDirector, IsSchoolStaff
from .models import BehaviourIncident, BehaviourSuspension
from .serializers import (
    BehaviourIncidentSerializer,
    BehaviourSuspensionSerializer,
    BehaviourDashboardSerializer,
    StudentBehaviourSummarySerializer,
)

logger = logging.getLogger('schoolbridge')


class BehaviourIncidentViewSet(ExportMixin, AuditMixin, viewsets.ModelViewSet):
    """
    Manage behaviour incidents (positive and disciplinary).
    Supports WhatsApp guardian notifications.
    """
    serializer_class = BehaviourIncidentSerializer
    permission_classes = [IsSchoolStaff]
    filter_backends = [SearchFilter, OrderingFilter]
    search_fields = ['title', 'description', 'student__first_name', 'student__last_name']
    ordering_fields = ['incident_date', 'created_at', 'incident_type']
    ordering = ['-incident_date']
    lookup_field = 'pk'
    lookup_value_regex = '[0-9a-f-]+'

    def get_queryset(self):
        qs = BehaviourIncident.objects.filter(
            school=self.request.user.school
        ).select_related(
            'student', 'class_group', 'reported_by', 'handled_by', 'academic_term'
        ).prefetch_related('suspension')

        term_id = self.request.query_params.get('term_id')
        class_id = self.request.query_params.get('class_id')
        incident_type = self.request.query_params.get('incident_type')
        category = self.request.query_params.get('category')
        student_id = self.request.query_params.get('student_id')
        date_from = self.request.query_params.get('date_from')
        date_to = self.request.query_params.get('date_to')

        if term_id:
            qs = qs.filter(academic_term_id=term_id)
        if class_id:
            qs = qs.filter(class_group_id=class_id)
        if incident_type:
            qs = qs.filter(incident_type=incident_type)
        if category:
            qs = qs.filter(category=category)
        if student_id:
            qs = qs.filter(student_id=student_id)
        if date_from:
            qs = qs.filter(incident_date__gte=date_from)
        if date_to:
            qs = qs.filter(incident_date__lte=date_to)

        return qs

    def perform_create(self, serializer):
        user = self.request.user
        # Auto-set class_group from student if not provided
        student = serializer.validated_data.get('student')
        class_group = serializer.validated_data.get('class_group')
        if not class_group and student and student.current_class:
            class_group = student.current_class

        serializer.save(
            school=user.school,
            reported_by=user,
            class_group=class_group,
        )

    @extend_schema(
        request=None,
        responses={200: BehaviourIncidentSerializer},
        summary='Send WhatsApp notification to guardian about incident',
        tags=['Behaviour'],
    )
    @action(detail=True, methods=['post'], url_path='notify-parent')
    def notify_parent(self, request, pk=None):
        """Send a WhatsApp message to the student's primary guardian about this incident."""
        incident = self.get_object()

        try:
            from messaging.services import WhatsAppService
            from students.models import Guardian

            guardian = Guardian.objects.filter(
                student=incident.student, is_primary=True
            ).first()

            if not guardian:
                return Response(
                    {'error': 'No primary guardian found for this student.'},
                    status=status.HTTP_404_NOT_FOUND,
                )

            if incident.incident_type == 'positive':
                message = (
                    f"Dear Parent, we are pleased to inform you that your child "
                    f"*{incident.student.first_name}* has received a commendation:\n\n"
                    f"*{incident.title}*\n\n{incident.description[:300]}"
                )
            else:
                message = (
                    f"Dear Parent, this is to inform you about a disciplinary matter "
                    f"regarding your child *{incident.student.first_name}* "
                    f"({incident.get_incident_type_display()}):\n\n"
                    f"*{incident.title}*\n\n{incident.description[:300]}\n\n"
                    f"Action taken: {incident.action_taken or 'Under review'}\n\n"
                    f"Please contact the school for more information."
                )

            WhatsAppService.send_text(
                phone=guardian.phone_normalised,
                message=message,
                school=incident.school,
            )

            incident.parent_notified = True
            incident.parent_notified_at = timezone.now()
            incident.parent_notification_message = message
            incident.save(update_fields=['parent_notified', 'parent_notified_at', 'parent_notification_message'])

            logger.info(f'Behaviour notification sent to {guardian.phone_normalised} for incident {incident.id}')
            return Response(BehaviourIncidentSerializer(incident, context={'request': request}).data)

        except Exception as e:
            logger.error(f'Failed to send behaviour notification for incident {incident.id}: {e}')
            return Response({'error': f'Failed to send notification: {str(e)}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @extend_schema(
        responses={200: BehaviourDashboardSerializer},
        summary='School-wide behaviour dashboard summary',
        tags=['Behaviour'],
    )
    @action(detail=False, methods=['get'], url_path='dashboard')
    def dashboard(self, request):
        """Return school-wide behaviour statistics for the current or specified term."""
        school = request.user.school
        term_id = request.query_params.get('term_id')

        qs = BehaviourIncident.objects.filter(school=school)
        if term_id:
            qs = qs.filter(academic_term_id=term_id)

        totals = qs.aggregate(
            total=Count('id'),
            positive=Count('id', filter=Q(incident_type='positive')),
            warnings=Count('id', filter=Q(incident_type='warning')),
            suspensions=Count('id', filter=Q(incident_type='suspension')),
            expulsions=Count('id', filter=Q(incident_type='expulsion')),
        )

        by_category = list(
            qs.values('category').annotate(count=Count('id')).order_by('-count')
        )

        top_students = list(
            qs.filter(incident_type__in=['warning', 'suspension', 'expulsion'])
            .values('student__id', 'student__first_name', 'student__last_name')
            .annotate(count=Count('id'))
            .order_by('-count')[:5]
        )

        recent = qs.select_related('student', 'class_group', 'reported_by').order_by('-incident_date')[:10]

        return Response({
            'total_incidents': totals['total'],
            'positive': totals['positive'],
            'warnings': totals['warnings'],
            'suspensions': totals['suspensions'],
            'expulsions': totals['expulsions'],
            'by_category': by_category,
            'top_students': top_students,
            'recent_incidents': BehaviourIncidentSerializer(recent, many=True, context={'request': request}).data,
        })


class BehaviourSuspensionViewSet(AuditMixin, viewsets.ModelViewSet):
    """
    Manage formal suspension records.
    Requires Director approval before taking effect.
    """
    serializer_class = BehaviourSuspensionSerializer
    permission_classes = [IsSchoolStaff]
    filter_backends = [SearchFilter, OrderingFilter]
    search_fields = ['student__first_name', 'student__last_name', 'reason']
    ordering_fields = ['suspension_start', 'created_at']
    ordering = ['-suspension_start']
    lookup_field = 'pk'
    lookup_value_regex = '[0-9a-f-]+'

    def get_queryset(self):
        qs = BehaviourSuspension.objects.filter(
            school=self.request.user.school
        ).select_related('student', 'incident', 'approved_by', 'reinstatement_confirmed_by')

        active_only = self.request.query_params.get('active_only')
        unapproved_only = self.request.query_params.get('unapproved_only')

        if active_only == 'true':
            today = timezone.localdate()
            qs = qs.filter(suspension_start__lte=today, suspension_end__gte=today, reinstated=False)
        if unapproved_only == 'true':
            qs = qs.filter(director_approved=False)

        return qs

    @extend_schema(
        request=None,
        responses={200: BehaviourSuspensionSerializer},
        summary='Director approves a suspension',
        tags=['Behaviour'],
    )
    @action(detail=True, methods=['post'], url_path='approve', permission_classes=[IsDirector])
    def approve(self, request, pk=None):
        """Director approves a pending suspension."""
        suspension = self.get_object()
        if suspension.director_approved:
            return Response({'error': 'Suspension already approved.'}, status=status.HTTP_400_BAD_REQUEST)

        suspension.director_approved = True
        suspension.approved_by = request.user
        suspension.approved_at = timezone.now()
        suspension.save(update_fields=['director_approved', 'approved_by', 'approved_at', 'updated_at'])

        logger.info(f'Suspension {suspension.id} approved by {request.user.email}')
        return Response(BehaviourSuspensionSerializer(suspension, context={'request': request}).data)

    @extend_schema(
        request=None,
        responses={200: BehaviourSuspensionSerializer},
        summary='Record student reinstatement after suspension',
        tags=['Behaviour'],
    )
    @action(detail=True, methods=['post'], url_path='reinstate')
    def reinstate(self, request, pk=None):
        """Record that the student has been reinstated after suspension."""
        suspension = self.get_object()
        if suspension.reinstated:
            return Response({'error': 'Student is already reinstated.'}, status=status.HTTP_400_BAD_REQUEST)

        notes = request.data.get('notes', '')
        suspension.reinstated = True
        suspension.reinstatement_date = timezone.localdate()
        suspension.reinstatement_confirmed_by = request.user
        suspension.reinstatement_notes = notes
        suspension.save(update_fields=[
            'reinstated', 'reinstatement_date', 'reinstatement_confirmed_by',
            'reinstatement_notes', 'updated_at'
        ])

        logger.info(f'Student {suspension.student} reinstated by {request.user.email}')
        return Response(BehaviourSuspensionSerializer(suspension, context={'request': request}).data)


class StudentBehaviourSummaryView(APIView):
    """
    GET /api/v1/behaviour/students/{student_id}/summary/
    Returns the full behaviour history for a specific student.
    """
    permission_classes = [IsSchoolStaff]

    @extend_schema(
        responses={200: StudentBehaviourSummarySerializer},
        summary='Get full behaviour history for a student',
        tags=['Behaviour'],
    )
    def get(self, request, student_id):
        from students.models import Student

        try:
            student = Student.objects.get(id=student_id, school=request.user.school)
        except Student.DoesNotExist:
            return Response({'error': 'Student not found.'}, status=status.HTTP_404_NOT_FOUND)

        incidents = BehaviourIncident.objects.filter(
            student=student, school=request.user.school
        ).select_related('reported_by', 'handled_by', 'class_group').prefetch_related('suspension')

        suspensions = BehaviourSuspension.objects.filter(
            student=student, school=request.user.school
        )
        total_suspension_days = sum(s.duration_days for s in suspensions)

        totals = incidents.aggregate(
            total=Count('id'),
            positive=Count('id', filter=Q(incident_type='positive')),
            warnings=Count('id', filter=Q(incident_type='warning')),
            susp=Count('id', filter=Q(incident_type='suspension')),
        )

        return Response({
            'student_id': student.id,
            'student_name': f"{student.first_name} {student.last_name}".strip(),
            'total_incidents': totals['total'],
            'positive': totals['positive'],
            'warnings': totals['warnings'],
            'suspensions': totals['susp'],
            'total_suspension_days': total_suspension_days,
            'incidents': BehaviourIncidentSerializer(incidents, many=True, context={'request': request}).data,
        })
