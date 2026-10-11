"""
Homework views.
"""
import logging
from django.db.models import Avg
from django.utils import timezone
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.filters import SearchFilter, OrderingFilter
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from drf_spectacular.utils import extend_schema, OpenApiParameter, inline_serializer
from drf_spectacular.types import OpenApiTypes
from rest_framework import serializers as drf_serializers

from audit.mixins import AuditMixin
from schools.permissions import IsDirector, IsSchoolStaff
from .models import HomeworkAssignment, HomeworkSubmission
from .serializers import (
    HomeworkAssignmentSerializer,
    HomeworkSubmissionSerializer,
    HomeworkSubmissionCreateSerializer,
    HomeworkReportSerializer,
)

logger = logging.getLogger('schoolbridge')


class HomeworkAssignmentViewSet(AuditMixin, viewsets.ModelViewSet):
    """
    Manage homework assignments.
    Teachers create assignments; Directors can view all.
    Guardians receive WhatsApp notifications when assignments are published.
    """
    serializer_class = HomeworkAssignmentSerializer
    permission_classes = [IsSchoolStaff]
    filter_backends = [SearchFilter, OrderingFilter]
    search_fields = ['title', 'description', 'class_group__name', 'subject__name']
    ordering_fields = ['due_date', 'assigned_date', 'created_at']
    ordering = ['-due_date']
    lookup_field = 'pk'
    lookup_value_regex = '[0-9a-f-]+'

    def get_queryset(self):
        qs = HomeworkAssignment.objects.filter(
            school=self.request.user.school
        ).select_related('class_group', 'subject', 'assigned_by', 'academic_term')

        # Filters
        term_id = self.request.query_params.get('term_id')
        class_id = self.request.query_params.get('class_id')
        status_filter = self.request.query_params.get('status')
        subject_id = self.request.query_params.get('subject_id')

        if term_id:
            qs = qs.filter(academic_term_id=term_id)
        if class_id:
            qs = qs.filter(class_group_id=class_id)
        if status_filter:
            qs = qs.filter(status=status_filter)
        if subject_id:
            qs = qs.filter(subject_id=subject_id)

        return qs

    def perform_create(self, serializer):
        serializer.save(
            school=self.request.user.school,
            assigned_by=self.request.user,
        )

    @extend_schema(
        request=None,
        responses={200: HomeworkAssignmentSerializer},
        summary='Publish a homework assignment and notify guardians',
        tags=['Homework'],
    )
    @action(detail=True, methods=['post'], url_path='publish')
    def publish(self, request, pk=None):
        """Publish an assignment and send WhatsApp notifications to guardians."""
        assignment = self.get_object()

        if assignment.status != 'draft':
            return Response(
                {'error': f'Assignment is already {assignment.status}. Only drafts can be published.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        assignment.status = 'published'
        assignment.save(update_fields=['status', 'updated_at'])

        # Dispatch WhatsApp notifications to guardians in background
        self._notify_guardians(assignment)

        logger.info(
            f'Homework published: {assignment.title} for {assignment.class_group} '
            f'by {request.user.email}'
        )
        return Response(HomeworkAssignmentSerializer(assignment, context={'request': request}).data)

    @extend_schema(
        request=None,
        responses={200: HomeworkAssignmentSerializer},
        summary='Close submissions for a homework assignment',
        tags=['Homework'],
    )
    @action(detail=True, methods=['post'], url_path='close')
    def close(self, request, pk=None):
        """Close an assignment — no more submissions accepted."""
        assignment = self.get_object()

        if assignment.status == 'closed':
            return Response({'error': 'Assignment is already closed.'}, status=status.HTTP_400_BAD_REQUEST)

        assignment.status = 'closed'
        assignment.save(update_fields=['status', 'updated_at'])
        return Response(HomeworkAssignmentSerializer(assignment, context={'request': request}).data)

    @extend_schema(
        parameters=[
            OpenApiParameter('assignment_id', OpenApiTypes.UUID, location=OpenApiParameter.PATH),
        ],
        responses={200: HomeworkSubmissionSerializer(many=True)},
        summary='List submissions for a homework assignment',
        tags=['Homework'],
    )
    @action(detail=True, methods=['get'], url_path='submissions')
    def submissions(self, request, pk=None):
        """List all submissions for this assignment."""
        assignment = self.get_object()
        subs = HomeworkSubmission.objects.filter(
            assignment=assignment
        ).select_related('student', 'graded_by')
        serializer = HomeworkSubmissionSerializer(subs, many=True, context={'request': request})
        return Response(serializer.data)

    @extend_schema(
        request=HomeworkSubmissionCreateSerializer,
        responses={201: HomeworkSubmissionSerializer},
        summary='Record a student submission',
        tags=['Homework'],
    )
    @action(detail=True, methods=['post'], url_path='submit')
    def submit(self, request, pk=None):
        """Record that a student has submitted their homework."""
        assignment = self.get_object()

        if assignment.status != 'published':
            return Response(
                {'error': 'Can only submit to published assignments.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = HomeworkSubmissionCreateSerializer(
            data=request.data,
            context={'request': request, 'assignment': assignment},
        )
        serializer.is_valid(raise_exception=True)
        submission = serializer.save()
        return Response(
            HomeworkSubmissionSerializer(submission, context={'request': request}).data,
            status=status.HTTP_201_CREATED,
        )

    @extend_schema(
        responses={200: HomeworkReportSerializer},
        summary='Get completion report for a homework assignment',
        tags=['Homework'],
    )
    @action(detail=True, methods=['get'], url_path='report')
    def report(self, request, pk=None):
        """Return a summary of submission completion rates and average marks."""
        assignment = self.get_object()
        total = assignment.class_group.current_students.filter(is_active=True).count()
        submitted = assignment.submissions.count()
        avg_marks = assignment.submissions.aggregate(avg=Avg('marks_awarded'))['avg']

        return Response({
            'assignment_id': assignment.id,
            'title': assignment.title,
            'class_group': assignment.class_group.name,
            'due_date': assignment.due_date,
            'total_students': total,
            'submitted': submitted,
            'not_submitted': max(0, total - submitted),
            'completion_rate': round((submitted / total) * 100, 1) if total else 0,
            'average_marks': round(avg_marks, 1) if avg_marks else None,
        })

    def _notify_guardians(self, assignment):
        """Send WhatsApp notifications to guardians of students in the class."""
        try:
            from messaging.services import WhatsAppService
            from students.models import Guardian

            guardians = Guardian.objects.filter(
                student__current_class=assignment.class_group,
                student__is_active=True,
                is_primary=True,
            ).select_related('student')

            message = (
                f"Dear Parent, a new homework assignment has been posted for "
                f"{assignment.class_group.name}:\n\n"
                f"*{assignment.title}*\n"
                f"Due: {assignment.due_date.strftime('%d %b %Y')}\n\n"
                f"{assignment.description[:200] if assignment.description else ''}"
            ).strip()

            sent_count = 0
            for guardian in guardians:
                try:
                    WhatsAppService.send_text(
                        phone=guardian.phone_normalised,
                        message=message,
                        school=assignment.school,
                    )
                    sent_count += 1
                except Exception as e:
                    logger.warning(f'Failed to notify guardian {guardian.phone_normalised}: {e}')

            assignment.guardian_notified = True
            assignment.guardian_notified_at = timezone.now()
            assignment.save(update_fields=['guardian_notified', 'guardian_notified_at'])

            logger.info(
                f'Homework notifications sent: {sent_count}/{guardians.count()} guardians '
                f'for assignment {assignment.id}'
            )
        except Exception as e:
            logger.error(f'Failed to send homework notifications for {assignment.id}: {e}')

class HomeworkSubmissionViewSet(AuditMixin, viewsets.ModelViewSet):
    """
    Manage individual homework submissions.
    Allows teachers to grade submissions (PATCH).
    """
    queryset = HomeworkSubmission.objects.none()
    serializer_class = HomeworkSubmissionSerializer
    permission_classes = [IsSchoolStaff]
    http_method_names = ['get', 'patch', 'head', 'options']

    def get_queryset(self):
        return HomeworkSubmission.objects.filter(
            assignment__school=self.request.user.school
        ).select_related('student', 'assignment')

    def perform_update(self, serializer):
        from django.utils import timezone
        submission = serializer.save(
            graded_by=self.request.user,
            graded_at=timezone.now()
        )
        self.log_action('HOMEWORK_GRADED', submission, {'marks': submission.marks_awarded})

