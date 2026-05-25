"""Results views — marks entry, locking, report card generation."""
from django.utils import timezone
from rest_framework import viewsets, generics, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework import serializers as drf_serializers

from audit.mixins import AuditMixin
from schools.permissions import IsTeacher, IsDirector, IsDirectorOrBursar, IsSchoolStaff
from .models import Subject, Assessment, AssessmentMark, TermResult
from .services import MarksService, ReportCardService


class SubjectSerializer(drf_serializers.ModelSerializer):
    class Meta:
        model = Subject
        fields = ['id', 'name', 'code', 'class_levels', 'is_active']


class AssessmentSerializer(drf_serializers.ModelSerializer):
    subject_name = drf_serializers.CharField(source='subject.name', read_only=True)

    class Meta:
        model = Assessment
        fields = [
            'id', 'academic_term', 'class_group', 'subject', 'subject_name',
            'name', 'assessment_type', 'max_marks', 'weight',
            'is_locked', 'locked_at', 'locked_by',
        ]
        read_only_fields = ['id', 'is_locked', 'locked_at', 'locked_by']


class AssessmentMarkSerializer(drf_serializers.ModelSerializer):
    student_name = drf_serializers.CharField(source='student.get_full_name', read_only=True)

    class Meta:
        model = AssessmentMark
        fields = ['id', 'student', 'student_name', 'marks_obtained', 'is_absent', 'comment']


class TermResultSerializer(drf_serializers.ModelSerializer):
    student_name = drf_serializers.CharField(source='student.get_full_name', read_only=True)
    class_name = drf_serializers.CharField(source='class_group.name', read_only=True)

    class Meta:
        model = TermResult
        fields = [
            'id', 'student', 'student_name', 'class_name', 'academic_term',
            'total_marks', 'average_marks', 'class_rank', 'total_students',
            'class_average', 'division', 'aggregate',
            'report_card_pdf', 'report_card_generated_at', 'parent_notified',
        ]
        read_only_fields = fields


class SubjectViewSet(AuditMixin, viewsets.ModelViewSet):
    serializer_class = SubjectSerializer
    permission_classes = [IsDirector]

    def get_queryset(self):
        return Subject.objects.filter(school=self.request.user.school, is_active=True)

    def perform_create(self, serializer):
        s = serializer.save(school=self.request.user.school)
        self.log_action('SUBJECT_CREATED', s, {'name': s.name})


class AssessmentViewSet(AuditMixin, viewsets.ModelViewSet):
    serializer_class = AssessmentSerializer
    permission_classes = [IsTeacher]

    def get_queryset(self):
        qs = Assessment.objects.filter(school=self.request.user.school)
        class_id = self.request.query_params.get('class_id')
        term_id = self.request.query_params.get('term_id')
        if class_id:
            qs = qs.filter(class_group_id=class_id)
        if term_id:
            qs = qs.filter(academic_term_id=term_id)
        return qs.select_related('subject', 'class_group')

    def perform_create(self, serializer):
        a = serializer.save(school=self.request.user.school)
        self.log_action('ASSESSMENT_CREATED', a, {'name': a.name})

    @action(detail=True, methods=['post'], permission_classes=[IsTeacher])
    def enter_marks(self, request, pk=None):
        """US-041: Enter marks for a whole class."""
        assessment = self.get_object()
        marks_data = request.data.get('marks', [])
        if not marks_data:
            return Response({'error': 'marks list is required.'}, status=400)
        try:
            records = MarksService.enter_marks(assessment, marks_data, request.user)
        except ValueError as e:
            return Response({'error': str(e)}, status=400)
        self.log_action('MARKS_ENTERED', assessment, {'count': len(records)})
        return Response({'message': f'{len(records)} marks saved.'})

    @action(detail=True, methods=['post'], permission_classes=[IsTeacher])
    def submit(self, request, pk=None):
        """US-041: Submit and lock an assessment."""
        assessment = self.get_object()
        MarksService.lock_assessment(assessment, request.user)
        self.log_action('ASSESSMENT_SUBMITTED', assessment, {'name': assessment.name})
        return Response({'message': 'Assessment submitted and locked.'})

    @action(detail=True, methods=['post'], permission_classes=[IsDirector])
    def unlock(self, request, pk=None):
        """US-041: Director unlocks an assessment with audit log."""
        assessment = self.get_object()
        reason = request.data.get('reason', '')
        MarksService.unlock_assessment(assessment, request.user)
        self.log_action('ASSESSMENT_UNLOCKED', assessment, {
            'name': assessment.name, 'reason': reason
        })
        return Response({'message': 'Assessment unlocked.'})


class TermResultViewSet(AuditMixin, viewsets.ReadOnlyModelViewSet):
    """US-042/046: Class performance summaries."""
    serializer_class = TermResultSerializer
    permission_classes = [IsSchoolStaff]

    def get_queryset(self):
        qs = TermResult.objects.filter(school=self.request.user.school)
        class_id = self.request.query_params.get('class_id')
        term_id = self.request.query_params.get('term_id')
        if class_id:
            qs = qs.filter(class_group_id=class_id)
        if term_id:
            qs = qs.filter(academic_term_id=term_id)
        return qs.select_related('student', 'class_group').order_by('class_rank')

    @action(detail=False, methods=['post'], permission_classes=[IsDirector])
    def generate_report_cards(self, request):
        """US-043/044: Batch generate report cards for a class."""
        class_id = request.data.get('class_id')
        term_id = request.data.get('term_id')
        if not class_id or not term_id:
            return Response({'error': 'class_id and term_id required.'}, status=400)
        from students.models import ClassGroup
        from schools.models import AcademicTerm
        try:
            cg = ClassGroup.objects.get(id=class_id, school=request.user.school)
            term = AcademicTerm.objects.get(id=term_id, school=request.user.school)
        except Exception:
            return Response({'error': 'Class or term not found.'}, status=404)
        ReportCardService.batch_generate_and_notify(cg, term, request.user)
        self.log_action('REPORT_CARDS_GENERATION_STARTED', None, {
            'class': cg.name, 'term': term.name
        })
        return Response({'message': f'Report card generation started for {cg.name}. Parents will be notified.'})


class results_urls:
    pass
