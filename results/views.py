"""Results views — marks entry, locking, report card generation."""
from django.db import models
from django.utils import timezone
from rest_framework import viewsets, generics, status
from rest_framework.decorators import action
from rest_framework.filters import SearchFilter, OrderingFilter
from rest_framework.response import Response
from rest_framework import serializers as drf_serializers
from rest_framework.exceptions import ValidationError, NotFound, PermissionDenied
from config.validators import validate_uuid, validate_int
from drf_spectacular.utils import extend_schema, OpenApiParameter, OpenApiTypes, inline_serializer

from audit.mixins import AuditMixin
from schools.permissions import IsTeacher, IsDirector, IsDirectorOrBursar, IsSchoolStaff
from .models import Subject, Assessment, AssessmentMark, TermResult
from .services import MarksService, ReportCardService


class SubjectSerializer(drf_serializers.ModelSerializer):
    class Meta:
        model = Subject
        fields = ['id', 'name', 'code', 'class_levels', 'is_active']


class AssessmentLookupSerializer(drf_serializers.ModelSerializer):
    """Minimal serializer for dropdown lookups."""
    class Meta:
        model = Assessment
        fields = ['id', 'name']


class AssessmentSerializer(drf_serializers.ModelSerializer):
    """Full assessment serializer with context for frontend display."""
    subject_name = drf_serializers.CharField(source='subject.name', read_only=True)
    subject_code = drf_serializers.CharField(source='subject.code', read_only=True)
    class_group_name = drf_serializers.CharField(source='class_group.name', read_only=True)
    class_group_level = drf_serializers.CharField(source='class_group.level', read_only=True)
    academic_year = drf_serializers.IntegerField(source='academic_term.academic_year.year', read_only=True)
    term_name = drf_serializers.CharField(source='academic_term.name', read_only=True)
    term_number = drf_serializers.IntegerField(source='academic_term.term_number', read_only=True)
    student_count = drf_serializers.SerializerMethodField()
    marks_entered_count = drf_serializers.SerializerMethodField()
    date = drf_serializers.DateField(required=False, write_only=True)
    locked_by = drf_serializers.SerializerMethodField()

    class Meta:
        model = Assessment
        fields = [
            'id', 'academic_term', 'academic_year', 'term_name', 'term_number',
            'class_group', 'class_group_name', 'class_group_level',
            'subject', 'subject_name', 'subject_code',
            'name', 'assessment_type', 'max_marks', 'weight',
            'status', 'rejection_reason', 'version',
            'is_locked', 'locked_at', 'locked_by',
            'student_count', 'marks_entered_count',
            'created_at', 'date',
        ]
        read_only_fields = ['id', 'is_locked', 'locked_at', 'locked_by', 'created_at', 'version']

    def get_locked_by(self, obj):
        """Return locked_by as a plain string UUID (JSON-safe) or None."""
        if obj.locked_by_id:
            return str(obj.locked_by_id)
        return None

    def get_student_count(self, obj):
        """Count of active students in the class group at the time of the assessment."""
        from students.models import Student
        return Student.all_objects.filter(
            school=obj.school, current_class=obj.class_group, is_active=True
        ).count()

    def get_marks_entered_count(self, obj):
        """Count of marks records entered (not absent, not null)."""
        return obj.marks.filter(marks_obtained__isnull=False, is_absent=False).count()

    def create(self, validated_data):
        """Pop the extra 'date' field (not on the model) before calling create."""
        validated_data.pop('date', None)
        return super().create(validated_data)


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
    queryset = Subject.objects.none()
    serializer_class = SubjectSerializer
    pagination_class = None

    def get_permissions(self):
        if self.action in ('list', 'retrieve'):
            return [IsSchoolStaff()]
        return [IsDirector()]

    def get_queryset(self):
        qs = Subject.objects.filter(school=self.request.user.school, is_active=True)
        class_group_id = self.request.query_params.get('class_group')
        if class_group_id:
            from students.models import ClassGroup
            cg = ClassGroup.objects.filter(id=class_group_id).first()
            if cg and cg.level:
                level = cg.level.strip()
                import re
                # Match level as an exact token in comma-separated class_levels list
                level_matched_qs = qs.filter(
                    models.Q(class_levels__regex=rf'(^|,){re.escape(level)}(,|$)')
                )
                if level_matched_qs.exists():
                    qs = level_matched_qs
                else:
                    qs = qs.filter(
                        models.Q(class_levels__regex=rf'(^|,){re.escape(level)}(,|$)') |
                        models.Q(class_levels='') |
                        models.Q(class_levels__isnull=True)
                    )

                # If A-level (S5/S6), specialize by stream if stream/name indicates Science or Arts
                stream_lower = (cg.stream or '').strip().lower()
                name_lower = (cg.name or '').strip().lower()
                is_science = 'science' in stream_lower or 'science' in name_lower or 'sci' in stream_lower
                is_arts = 'arts' in stream_lower or 'arts' in name_lower or 'art' in stream_lower

                if level in ('S5', 'S6'):
                    science_subject_names = [
                        'Pure Mathematics', 'Physics', 'Chemistry', 'Biology',
                        'General Paper', 'General Paper (GP)', 'Subsidiary ICT',
                        'Subsidiary Mathematics', 'Economics', 'Agriculture'
                    ]
                    arts_subject_names = [
                        'History', 'History & Political Education', 'Economics',
                        'Geography', 'Literature in English', 'Literature',
                        'Divinity', 'Christian Religious Education (CRE)',
                        'Entrepreneurship Education', 'Entrepreneurship',
                        'Fine Art', 'Kiswahili', 'Luganda', 'General Paper',
                        'General Paper (GP)', 'Subsidiary ICT', 'Subsidiary Mathematics'
                    ]
                    if is_science:
                        filtered_qs = qs.filter(
                            models.Q(name__in=science_subject_names) |
                            models.Q(code__in=['PMTC', 'PHY', 'CHE', 'BIO', 'GP', 'SICT', 'SMTC', 'ECON', 'AGR'])
                        )
                        if filtered_qs.exists():
                            qs = filtered_qs
                    elif is_arts:
                        filtered_qs = qs.filter(
                            models.Q(name__in=arts_subject_names) |
                            models.Q(code__in=['HIS', 'ECON', 'GEO', 'LIT', 'DIV', 'CRE', 'ENT', 'ART', 'KIS', 'LUG', 'GP', 'SICT', 'SMTC'])
                        )
                        if filtered_qs.exists():
                            qs = filtered_qs
        return qs.order_by('name')

    def perform_create(self, serializer):
        s = serializer.save(school=self.request.user.school)
        self.log_action('SUBJECT_CREATED', s, {'name': s.name})


class AssessmentViewSet(AuditMixin, viewsets.ModelViewSet):
    queryset = Assessment.objects.none()
    serializer_class = AssessmentSerializer
    permission_classes = [IsTeacher]
    filter_backends = [SearchFilter, OrderingFilter]
    search_fields = ['name', 'subject__name', 'class_group__name', 'assessment_type']
    ordering_fields = ['name', 'assessment_type', 'max_marks', 'created_at']
    ordering = ['-created_at']

    def get_queryset(self):
        qs = Assessment.objects.filter(school=self.request.user.school)
        class_id = self.request.query_params.get('class_id') or self.request.query_params.get('class_group')
        term_id = self.request.query_params.get('term_id') or self.request.query_params.get('academic_term') or self.request.query_params.get('term')
        subject_id = self.request.query_params.get('subject_id') or self.request.query_params.get('subject')
        if class_id:
            qs = qs.filter(class_group_id=class_id)
        if term_id:
            qs = qs.filter(academic_term_id=term_id)
        if subject_id:
            qs = qs.filter(subject_id=subject_id)
        return qs.select_related(
            'subject', 'class_group', 'academic_term', 'academic_term__academic_year'
        )

    def perform_create(self, serializer):
        a = serializer.save(school=self.request.user.school)
        self.log_action('ASSESSMENT_CREATED', a, {'name': a.name})

    @action(detail=False, methods=['get'])
    def lookup(self, request):
        qs = self.get_queryset()
        serializer = AssessmentLookupSerializer(qs, many=True)
        return Response(serializer.data)

    @extend_schema(
        request=inline_serializer(
            name='EnterMarksRequest',
            fields={
                'marks': drf_serializers.ListField(
                    child=inline_serializer(
                        name='StudentMarkItem',
                        fields={
                            'student': drf_serializers.UUIDField(),
                            'marks_obtained': drf_serializers.DecimalField(max_digits=5, decimal_places=2),
                            'is_absent': drf_serializers.BooleanField(required=False, default=False),
                            'comment': drf_serializers.CharField(required=False, allow_blank=True),
                        }
                    )
                )
            }
        ),
        responses={200: inline_serializer(name='EnterMarksResponse', fields={'message': drf_serializers.CharField()})},
        tags=['Results']
    )
    @action(detail=True, methods=['post'], permission_classes=[IsTeacher], url_path='enter-marks')
    def enter_marks(self, request, pk=None):
        """US-041: Enter marks for a whole class."""
        assessment = self.get_object()
        if request.user.role == 'teacher':
            is_form_teacher = assessment.class_group.form_teacher_id == request.user.id
            is_subject_teacher = False
            try:
                from timetable.models import TimetableSlot
                is_subject_teacher = TimetableSlot.objects.filter(
                    timetable_version__class_group=assessment.class_group,
                    timetable_version__is_active=True,
                    subject=assessment.subject,
                    teacher=request.user,
                ).exists()
            except Exception:
                pass
            if not (is_form_teacher or is_subject_teacher):
                raise PermissionDenied('You are only permitted to enter marks for your assigned class or subject.')
        marks_data = request.data.get('marks', [])
        if not marks_data:
            raise ValidationError({'marks': 'marks list is required.'})
        try:
            records = MarksService.enter_marks(assessment, marks_data, request.user)
        except ValueError as e:
            raise ValidationError(str(e))
        self.log_action('MARKS_ENTERED', assessment, {'count': len(records)})
        return Response({'message': f'{len(records)} marks saved.'})

    @extend_schema(
        responses={200: inline_serializer(name='SubmitAssessmentResponse', fields={'message': drf_serializers.CharField()})},
        tags=['Results']
    )
    @action(detail=True, methods=['post'], permission_classes=[IsTeacher])
    def submit(self, request, pk=None):
        """US-041: Submit and lock an assessment."""
        assessment = self.get_object()
        if request.user.role == 'teacher':
            is_form_teacher = assessment.class_group.form_teacher_id == request.user.id
            is_subject_teacher = False
            try:
                from timetable.models import TimetableSlot
                is_subject_teacher = TimetableSlot.objects.filter(
                    timetable_version__class_group=assessment.class_group,
                    timetable_version__is_active=True,
                    subject=assessment.subject,
                    teacher=request.user,
                ).exists()
            except Exception:
                pass
            if not (is_form_teacher or is_subject_teacher):
                raise PermissionDenied('You are only permitted to submit marks for your assigned class or subject.')
        try:
            MarksService._recompute_term_results(assessment)
        except Exception as e:
            logger.warning(f"Recompute on assessment submit failed: {e}")
        MarksService.lock_assessment(assessment, request.user)
        self.log_action('ASSESSMENT_SUBMITTED', assessment, {'name': assessment.name})
        return Response({'message': 'Assessment submitted and locked.'})

    @extend_schema(
        request=inline_serializer(
            name='UnlockAssessmentRequest',
            fields={'reason': drf_serializers.CharField(required=False, allow_blank=True)}
        ),
        responses={200: inline_serializer(name='UnlockAssessmentResponse', fields={'message': drf_serializers.CharField()})},
        tags=['Results']
    )
    @action(detail=True, methods=['post'], permission_classes=[IsDirector])
    def unlock(self, request, pk=None):
        """US-041: Director unlocks an assessment with audit log."""
        assessment = self.get_object()
        reason = request.data.get('reason', '')
        MarksService.unlock_assessment(assessment, request.user)
        assessment.status = 'draft'
        assessment.save(update_fields=['status'])
        self.log_action('ASSESSMENT_UNLOCKED', assessment, {
            'name': assessment.name, 'reason': reason
        })
        return Response({'message': 'Assessment unlocked.'})

    @action(detail=True, methods=['post'], permission_classes=[IsDirector])
    def approve(self, request, pk=None):
        """Director approves submitted assessment."""
        assessment = self.get_object()
        assessment.status = 'approved'
        assessment.is_locked = True
        assessment.save(update_fields=['status', 'is_locked'])
        self.log_action('ASSESSMENT_APPROVED', assessment, {'name': assessment.name})
        return Response({'message': f"Assessment '{assessment.name}' approved."})

    @action(detail=True, methods=['post'], permission_classes=[IsDirector])
    def reject(self, request, pk=None):
        """Director rejects assessment, unlocking it for teacher amendment."""
        assessment = self.get_object()
        reason = request.data.get('reason', '')
        if not reason:
            raise ValidationError({'reason': 'Rejection reason is required.'})
        assessment.status = 'rejected'
        assessment.is_locked = False
        assessment.rejection_reason = reason
        assessment.save(update_fields=['status', 'is_locked', 'rejection_reason'])
        self.log_action('ASSESSMENT_REJECTED', assessment, {'name': assessment.name, 'reason': reason})
        return Response({'message': f"Assessment '{assessment.name}' rejected and unlocked for editing."})

    @action(detail=True, methods=['get'], permission_classes=[IsTeacher], url_path='marks-roster')
    def marks_roster(self, request, pk=None):
        """
        GET /results/assessments/{id}/marks-roster/
        Returns the student roster for this assessment with any existing marks.
        Distinguishes: not_entered (null), zero (0), absent, and valid score.
        Used by the frontend marks entry grid.
        """
        from students.models import Student
        from results.models import AssessmentMark

        assessment = self.get_object()

        # Authoritative student list: active students in the class
        students = Student.all_objects.filter(
            school=assessment.school,
            current_class=assessment.class_group,
            is_active=True,
        ).order_by('last_name', 'first_name')

        # Fetch existing marks in a single query
        existing_marks = AssessmentMark.objects.filter(
            assessment=assessment
        ).select_related('student')
        marks_map = {str(m.student_id): m for m in existing_marks}

        roster = []
        for i, student in enumerate(students):
            mark = marks_map.get(str(student.id))
            score = float(mark.marks_obtained) if mark and mark.marks_obtained is not None else None
            is_absent = mark.is_absent if mark else False
            # is_entered = True only when teacher has meaningfully recorded this student:
            # either a real score (including 0) OR explicitly marked absent.
            # A null-score placeholder record from a past save does NOT count as entered.
            is_entered = mark is not None and (score is not None or is_absent)
            entry = {
                'student_id': str(student.id),
                'student_name': student.get_full_name(),
                'student_reg_no': student.student_id,
                'roll_no': i + 1,
                # Explicit mark states: null = not entered, value = score, is_absent flag
                'marks_obtained': score,
                'is_absent': is_absent,
                'is_entered': is_entered,
                'comment': mark.comment if mark else '',
                'entered_by': mark.entered_by.get_full_name() if mark and mark.entered_by else None,
                'entered_at': mark.entered_at.isoformat() if mark and mark.entered_at else None,
            }
            roster.append(entry)

        return Response({
            'assessment_id': str(assessment.id),
            'assessment_name': assessment.name,
            'assessment_type': assessment.assessment_type,
            'max_marks': assessment.max_marks,
            'is_locked': assessment.is_locked,
            'class_group_name': assessment.class_group.name,
            'class_group_level': assessment.class_group.level,
            'subject_name': assessment.subject.name,
            'subject_code': assessment.subject.code,
            'term_name': assessment.academic_term.name,
            'term_number': assessment.academic_term.term_number,
            'academic_year': assessment.academic_term.academic_year.year,
            'student_count': len(roster),
            'marks_entered_count': sum(1 for r in roster if r['is_entered'] and not r['is_absent']),
            'absent_count': sum(1 for r in roster if r['is_absent']),
            'not_entered_count': sum(1 for r in roster if not r['is_entered'] and not r['is_absent']),
            'roster': roster,
        })


class TermResultViewSet(AuditMixin, viewsets.ReadOnlyModelViewSet):
    queryset = TermResult.objects.none()
    """US-042/046: Class performance summaries."""
    serializer_class = TermResultSerializer
    permission_classes = [IsSchoolStaff]
    filter_backends = [SearchFilter, OrderingFilter]
    search_fields = ['student__first_name', 'student__last_name', 'student__student_id']
    ordering_fields = ['class_rank', 'average_marks', 'total_marks']
    ordering = ['class_rank']

    def get_queryset(self):
        qs = TermResult.objects.filter(school=self.request.user.school)
        class_id = self.request.query_params.get('class_id')
        term_id = self.request.query_params.get('term_id')
        if class_id:
            qs = qs.filter(class_group_id=class_id)
        if term_id:
            qs = qs.filter(academic_term_id=term_id)
        return qs.select_related('student', 'class_group', 'academic_term').order_by('class_rank')

    @extend_schema(
        request=inline_serializer(
            name='GenerateReportCardsRequest',
            fields={
                'class_id': drf_serializers.UUIDField(),
                'term_id': drf_serializers.UUIDField(),
            }
        ),
        responses={200: inline_serializer(name='GenerateReportCardsResponse', fields={'message': drf_serializers.CharField()})},
        tags=['Results']
    )
    @action(detail=False, methods=['post'], permission_classes=[IsDirector], url_path='generate-report-cards')
    def generate_report_cards(self, request):
        """US-043/044: Batch generate report cards for a class."""
        class_id = request.data.get('class_id')
        term_id = request.data.get('term_id')
        if not class_id or not term_id:
            raise ValidationError('class_id and term_id required.')
        from students.models import ClassGroup
        from schools.models import AcademicTerm
        try:
            cg = ClassGroup.objects.get(id=class_id, school=request.user.school)
            term = AcademicTerm.objects.get(id=term_id, school=request.user.school)
        except Exception:
            raise NotFound('Class or term not found.')
        ReportCardService.batch_generate_and_notify(cg, term, request.user)
        self.log_action('REPORT_CARDS_GENERATION_STARTED', None, {
            'class': cg.name, 'term': term.name
        })
        return Response({'message': f'Report card generation started for {cg.name}. Parents will be notified.'})

    @extend_schema(
        request=inline_serializer(
            name='PublishResultsRequest',
            fields={
                'class_id': drf_serializers.UUIDField(),
                'term_id': drf_serializers.UUIDField(),
            }
        ),
        responses={200: inline_serializer(name='PublishResultsResponse', fields={'message': drf_serializers.CharField()})},
        tags=['Results']
    )
    @action(detail=False, methods=['post'], permission_classes=[IsDirector])
    def publish(self, request):
        """US-042/046: Publish class results and trigger report card generation."""
        class_id = request.data.get('class_id')
        term_id = request.data.get('term_id')
        if not class_id or not term_id:
            raise ValidationError('class_id and term_id required.')
            
        from students.models import ClassGroup
        from schools.models import AcademicTerm
        try:
            cg = ClassGroup.objects.get(id=class_id, school=request.user.school)
            term = AcademicTerm.objects.get(id=term_id, school=request.user.school)
        except Exception:
            raise NotFound('Class or term not found.')

        # Mark results as published
        results = TermResult.objects.filter(
            class_group=cg, academic_term=term, school=request.user.school
        )
        count = results.update(is_published=True, published_at=timezone.now())

        # Trigger batch generation and notification
        ReportCardService.batch_generate_and_notify(cg, term, request.user)
        self.log_action('RESULTS_PUBLISHED', None, {
            'class': cg.name, 'term': term.name, 'count': count
        })
        return Response({
            'message': f'Results for {cg.name} published. Report card generation started for {count} students.'
        })

    @extend_schema(
        parameters=[
            OpenApiParameter('class_id', OpenApiTypes.INT, description='ClassGroup PK ID', required=True),
            OpenApiParameter('term_id', OpenApiTypes.INT, description='AcademicTerm PK ID', required=True),
        ],
        responses={200: OpenApiTypes.BINARY},
        tags=['Results']
    )
    @action(detail=False, methods=['get'], permission_classes=[IsSchoolStaff], url_path='export-class-bundle')
    def export_class_bundle(self, request):
        """
        US-043/US-044: Download a ZIP archive containing all report card PDFs for a class and term.
        If any PDF is not yet saved, it generates it on the fly.
        """
        import io
        import zipfile
        from django.http import HttpResponse
        from students.models import ClassGroup
        from schools.models import AcademicTerm

        class_id = request.query_params.get('class_id')
        term_id = request.query_params.get('term_id')
        if not class_id or not term_id:
            raise ValidationError('class_id and term_id query parameters are required.')

        cg = ClassGroup.objects.filter(id=class_id, school=request.user.school).first()
        term = AcademicTerm.objects.filter(id=term_id, school=request.user.school).first()
        if not cg or not term:
            raise NotFound('Class or term not found.')

        results = TermResult.all_objects.filter(
            class_group=cg, academic_term=term, school=request.user.school
        ).select_related('student')

        if not results.exists():
            return Response({'detail': 'No term results found for this class and term.'}, status=404)

        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
            for result in results:
                pdf_data = None
                if result.report_card_pdf and result.report_card_pdf.name:
                    try:
                        result.report_card_pdf.open('rb')
                        pdf_data = result.report_card_pdf.read()
                        result.report_card_pdf.close()
                    except Exception:
                        pdf_data = None

                if not pdf_data:
                    try:
                        level_upper = (cg.level or cg.name or '').upper().strip()
                        if 'P7' in level_upper or level_upper == 'P7':
                            buf, div, agg = ReportCardService.generate_ple_report_card(result)
                        elif 'S4' in level_upper or level_upper == 'S4':
                            buf, div, agg = ReportCardService.generate_uce_report_card(result)
                        else:
                            buf, div, agg = ReportCardService.generate_generic_report_card(result)
                        pdf_data = buf.getvalue() if hasattr(buf, 'getvalue') else buf.read()
                    except Exception as exc:
                        continue

                filename = f"{result.student.student_id}_{result.student.last_name}_{result.student.first_name}.pdf".replace(' ', '_')
                zf.writestr(filename, pdf_data)

        zip_buffer.seek(0)
        zip_filename = f"Report_Cards_{cg.name}_{term.name}.zip".replace(' ', '_')
        response = HttpResponse(zip_buffer.getvalue(), content_type='application/zip')
        response['Content-Disposition'] = f'attachment; filename="{zip_filename}"'
        return response


from rest_framework.views import APIView
from rest_framework.parsers import MultiPartParser, FormParser
import os
import tempfile

class ReportCardUploadView(AuditMixin, APIView):
    """
    US-B03/US-B04: Upload report card PDF for a student and schedule distribution via WhatsApp.
    """
    permission_classes = [IsDirectorOrBursar]
    parser_classes = [MultiPartParser, FormParser]

    @extend_schema(
        request=inline_serializer(
            name='ReportCardUploadRequest',
            fields={
                'student_id': drf_serializers.UUIDField(),
                'pdf_file': drf_serializers.FileField(),
            }
        ),
        responses={202: inline_serializer(
            name='ReportCardUploadResponse',
            fields={
                'message': drf_serializers.CharField(),
                'file_path': drf_serializers.CharField()
            }
        )},
        tags=['Results']
    )
    def post(self, request):
        student_id = request.data.get('student_id')
        pdf_file = request.FILES.get('report_card') or request.FILES.get('pdf_file')

        if not student_id or not pdf_file:
            raise ValidationError('student_id and report_card/pdf_file are required.')
        validate_uuid(student_id, 'student_id')

        from students.models import Student
        from django.conf import settings
        
        try:
            student = Student.objects.get(id=student_id, school=request.user.school)
        except Student.DoesNotExist:
            raise NotFound('Student not found.')

        guardian = student.guardians.filter(is_primary=True).first()
        if not guardian or not guardian.phone_normalised:
            raise ValidationError('Primary guardian with normalised phone number not found for this student.')

        # Save file to default storage
        from django.core.files.storage import default_storage
        from django.core.files.base import ContentFile
        import uuid

        original_filename = pdf_file.name
        storage_path = default_storage.save(
            f"uploaded_report_cards/{uuid.uuid4()}_{original_filename}",
            ContentFile(pdf_file.read())
        )
        
        try:
            # Prepare report cards list for Celery task
            report_cards_list = [{
                'student_id': str(student.id),
                'parent_phone': guardian.phone_normalised,
                'file_path': storage_path,
                'filename': original_filename,
            }]
            
            # Dispatch Celery task (automatically routed to broadcast queue)
            from messaging.tasks import distribute_report_cards
            distribute_report_cards.delay(str(request.user.school.id), report_cards_list)
            
            self.log_action('REPORT_CARD_UPLOADED', student, {
                'filename': original_filename,
                'recipient': guardian.phone_normalised,
            })
            
            return Response({
                'message': f'Report card for {student.get_full_name()} uploaded and distribution queued.',
                'file_path': storage_path,
            }, status=status.HTTP_202_ACCEPTED)
            
        except Exception as e:
            if default_storage.exists(storage_path):
                default_storage.delete(storage_path)
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)


class MarksEntryView(AuditMixin, generics.GenericAPIView):
    """
    Frontend-compatible marks entry endpoints.

    GET  /results/marks-entry/?class_group=<id>&subject=<id>&assessment_type=<type>
         Returns the class roster with existing marks for this assessment type.

    POST /results/marks-entry/bulk-save/
         Saves marks as draft or submits for approval (locks).
    """
    permission_classes = [IsTeacher]

    def get(self, request):
        class_group_id = request.query_params.get('class_group')
        subject_id = request.query_params.get('subject')
        assessment_type = request.query_params.get('assessment_type')
        term_id = request.query_params.get('academic_term') or request.query_params.get('term')
        assessment_id = request.query_params.get('assessment_id')

        from students.models import ClassGroup, Student
        from schools.models import AcademicTerm

        assessment = None
        if assessment_id:
            assessment = Assessment.objects.filter(id=assessment_id, school=request.user.school).select_related(
                'subject', 'class_group', 'academic_term', 'academic_term__academic_year'
            ).first()
            if assessment:
                class_group = assessment.class_group
                class_group_id = class_group.id
                subject_id = assessment.subject_id
                term = assessment.academic_term
                assessment_type = assessment.assessment_type

        if not assessment:
            if not class_group_id or not subject_id:
                return Response({'results': []})

            try:
                class_group = ClassGroup.objects.get(id=class_group_id, school=request.user.school, is_active=True)
            except ClassGroup.DoesNotExist:
                return Response({'error': 'Class group not found.'}, status=status.HTTP_404_NOT_FOUND)

            # Resolve selected or active term
            term = None
            if term_id:
                term = AcademicTerm.objects.filter(id=term_id, school=request.user.school).select_related('academic_year').first()
            if not term:
                term = AcademicTerm.objects.filter(school=request.user.school, is_current=True).select_related('academic_year').first()

            # Find the most relevant assessment for this class + subject + type + term
            qs = Assessment.objects.filter(
                school=request.user.school,
                class_group=class_group,
                subject_id=subject_id,
            )
            if term:
                qs = qs.filter(academic_term=term)
            if assessment_type:
                qs = qs.filter(assessment_type=assessment_type)

            assessment = qs.select_related(
                'subject', 'class_group', 'academic_term', 'academic_term__academic_year'
            ).order_by('-created_at').first()

        students = Student.all_objects.filter(
            school=request.user.school,
            current_class=class_group,
            is_active=True,
        ).order_by('last_name', 'first_name')

        marks_map = {}
        max_marks = 100
        is_locked = False
        assessment_id = None
        academic_year = None
        term_name = None
        term_obj_id = None

        if assessment:
            max_marks = assessment.max_marks
            is_locked = assessment.is_locked
            assessment_id = str(assessment.id)
            academic_year = assessment.academic_term.academic_year.year if assessment.academic_term and assessment.academic_term.academic_year else None
            term_name = assessment.academic_term.name if assessment.academic_term else None
            term_obj_id = str(assessment.academic_term.id) if assessment.academic_term else None
            existing = assessment.marks.select_related('student').all()
            marks_map = {str(m.student_id): m for m in existing}
        elif term:
            academic_year = term.academic_year.year if term.academic_year else None
            term_name = term.name
            term_obj_id = str(term.id)

        results = []
        for i, student in enumerate(students):
            mark = marks_map.get(str(student.id))
            results.append({
                'student_id': str(student.id),
                'student_name': student.get_full_name(),
                'student_reg_no': student.student_id,
                'roll_no': i + 1,
                # CRITICAL: null = not entered, float = score (including 0.0), absent = separate flag
                'score': float(mark.marks_obtained) if mark and mark.marks_obtained is not None else None,
                'is_absent': mark.is_absent if mark else False,
                'is_entered': mark is not None and (mark.marks_obtained is not None or mark.is_absent),
                'is_submitted': is_locked,
                'comment': mark.comment if mark else '',
            })

        return Response({
            'assessment_id': assessment_id,
            'max_marks': max_marks,
            'is_locked': is_locked,
            'status': assessment.status if assessment else 'draft',
            'rejection_reason': assessment.rejection_reason if assessment else '',
            'version': assessment.version if assessment else 1,
            'academic_year': academic_year,
            'term_name': term_name,
            'term_id': term_obj_id,
            'class_group_level': class_group.level,
            'assessment_types': [{'value': val, 'label': label} for val, label in Assessment.ASSESSMENT_TYPES],
            'results': results,
        })


class MarksEntryBulkSaveView(AuditMixin, generics.GenericAPIView):
    """
    POST /results/marks-entry/bulk-save/
    Finds or creates the assessment for this class+subject+type+term, then saves marks.
    If submit_for_approval=true, locks the assessment.
    Never treats null as zero. Never treats absent as zero.
    """
    permission_classes = [IsTeacher]

    def post(self, request):
        class_group_id = request.data.get('class_group')
        subject_id = request.data.get('subject')
        assessment_type = request.data.get('assessment_type', 'end_of_term')
        submit_for_approval = request.data.get('submit_for_approval', False)
        marks_data = request.data.get('marks', [])
        assessment_id = request.data.get('assessment_id')
        term_id = request.data.get('academic_term') or request.data.get('term')
        # Optimistic locking: client sends back version it last read
        client_version = request.data.get('version')  # int or None

        if not class_group_id or not subject_id:
            raise ValidationError('class_group and subject are required.')

        from students.models import ClassGroup
        from schools.models import AcademicTerm

        try:
            class_group = ClassGroup.objects.get(id=class_group_id, school=request.user.school, is_active=True)
        except ClassGroup.DoesNotExist:
            raise NotFound('Class group not found.')

        # Use provided assessment_id if given, else find or create for term
        if assessment_id:
            try:
                assessment = Assessment.objects.get(id=assessment_id, school=request.user.school)
            except Assessment.DoesNotExist:
                raise NotFound('Assessment not found.')
        else:
            term = None
            if term_id:
                term = AcademicTerm.objects.filter(id=term_id, school=request.user.school).first()
            if not term:
                term = AcademicTerm.objects.filter(
                    school=request.user.school, is_current=True
                ).first()
            if not term:
                raise ValidationError('No academic term specified or configured as current. Ask the Director to set the active term.')

            assessment, created = Assessment.objects.get_or_create(
                school=request.user.school,
                academic_term=term,
                class_group=class_group,
                subject_id=subject_id,
                assessment_type=assessment_type,
                defaults={
                    'name': f'{class_group.name} {assessment_type.replace("_", " ").title()} - {term.name}',
                    'max_marks': 100,
                }
            )
            if created:
                self.log_action('ASSESSMENT_CREATED', assessment, {
                    'name': assessment.name, 'auto_created': True
                })

        if assessment.is_locked:
            raise ValidationError(
                f"Assessment '{assessment.name}' is locked. Contact the Director to unlock it."
            )

        # Optimistic locking check: prevent concurrent write collisions
        if client_version is not None and int(client_version) != assessment.version:
            raise ValidationError(
                f"This assessment was modified by another session (version mismatch). "
                f"Please refresh the page and re-enter your changes."
            )

        # Build marks_data for MarksService — translate frontend format
        service_marks = []
        for entry in marks_data:
            service_marks.append({
                'student_id': entry.get('student_id'),
                # Explicit: null stays null (not entered), 0 stays 0 (valid zero)
                'marks_obtained': entry.get('score'),
                'is_absent': entry.get('is_absent', False),
                'comment': entry.get('comment', ''),
            })

        try:
            records = MarksService.enter_marks(assessment, service_marks, request.user)
        except ValueError as e:
            raise ValidationError(str(e))

        self.log_action('MARKS_SAVED', assessment, {
            'count': len(records),
            'submit_for_approval': submit_for_approval
        })

        # Increment version to invalidate any stale client sessions
        assessment.version = (assessment.version or 1) + 1

        if submit_for_approval:
            MarksService.lock_assessment(assessment, request.user)
            assessment.status = 'submitted'
            assessment.save(update_fields=['version', 'status'])
            self.log_action('ASSESSMENT_SUBMITTED', assessment, {'name': assessment.name})
            return Response({
                'message': f'{len(records)} marks submitted and locked for Director approval.',
                'assessment_id': str(assessment.id),
                'is_locked': True,
                'status': 'submitted',
                'version': assessment.version,
            })

        # Save as draft
        assessment.status = 'draft'
        assessment.save(update_fields=['version', 'status'])

        return Response({
            'message': f'{len(records)} marks saved as draft.',
            'assessment_id': str(assessment.id),
            'is_locked': False,
            'status': 'draft',
            'version': assessment.version,
        })


import csv
import io
from django.http import HttpResponse

class MarksCSVTemplateView(APIView):
    """
    GET /results/marks-entry/csv-template/?class_group=<id>&term=<id>
    Generates a pre-populated CSV template with student IDs and names.
    """
    permission_classes = [IsTeacher]

    def get(self, request):
        class_group_id = request.query_params.get('class_group')
        term_id = request.query_params.get('academic_term') or request.query_params.get('term')
        if not class_group_id:
            raise ValidationError({'class_group': 'class_group is required.'})

        from students.models import Student, ClassGroup
        from schools.models import AcademicTerm
        try:
            cg = ClassGroup.objects.get(id=class_group_id, school=request.user.school, is_active=True)
        except ClassGroup.DoesNotExist:
            raise NotFound('Class group not found.')

        term_suffix = ''
        if term_id:
            term = AcademicTerm.objects.filter(id=term_id, school=request.user.school).first()
            if term:
                term_suffix = f'_{term.name.replace(" ", "_")}'

        students = Student.all_objects.filter(
            school=request.user.school, current_class=cg, is_active=True
        ).order_by('last_name', 'first_name')

        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = f'attachment; filename="marks_template_{cg.name.replace(" ", "_")}{term_suffix}.csv"'

        writer = csv.writer(response)
        writer.writerow(['Student ID', 'Registration No', 'Student Name', 'Marks Obtained (0-Max)', 'Is Absent (TRUE/FALSE)', 'Comment'])

        for st in students:
            writer.writerow([str(st.id), st.student_id, st.get_full_name(), '', 'FALSE', ''])

        return response


class MarksCSVImportView(AuditMixin, generics.GenericAPIView):
    """
    POST /results/marks-entry/csv-import/
    Uploads a CSV file of marks, validates row by row, returns preview & errors.
    Supports dry_run=true for validation preview, and dry_run=false for bulk save.
    """
    permission_classes = [IsTeacher]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request):
        file_obj = request.FILES.get('csv_file')
        class_group_id = request.data.get('class_group')
        subject_id = request.data.get('subject')
        assessment_type = request.data.get('assessment_type', 'end_of_term')
        term_id = request.data.get('academic_term') or request.data.get('term')
        dry_run = request.data.get('dry_run', 'true').lower() == 'true'

        if not file_obj or not class_group_id or not subject_id:
            raise ValidationError('csv_file, class_group, and subject are required.')

        from students.models import Student, ClassGroup
        from schools.models import AcademicTerm

        try:
            cg = ClassGroup.objects.get(id=class_group_id, school=request.user.school, is_active=True)
        except ClassGroup.DoesNotExist:
            raise NotFound('Class group not found.')

        # Validate subject exists and belongs to this school
        try:
            subject_obj = Subject.objects.get(id=subject_id, school=request.user.school)
        except Subject.DoesNotExist:
            raise ValidationError(f'Subject ID "{subject_id}" does not exist or does not belong to this school.')

        term = None
        if term_id:
            term = AcademicTerm.objects.filter(id=term_id, school=request.user.school).first()
        if not term:
            term = AcademicTerm.objects.filter(school=request.user.school, is_current=True).first()
        if not term:
            raise ValidationError('No current academic term configured.')

        assessment, _ = Assessment.objects.get_or_create(
            school=request.user.school,
            academic_term=term,
            class_group=cg,
            subject=subject_obj,
            assessment_type=assessment_type,
            defaults={
                'name': f'{cg.name} {assessment_type.replace("_", " ").title()} - {term.name}',
                'max_marks': 100,
            }
        )

        if assessment.is_locked:
            raise ValidationError(f"Assessment '{assessment.name}' is locked. Contact Director to unlock.")

        # Read CSV file
        content = file_obj.read().decode('utf-8-sig')
        csv_reader = csv.reader(io.StringIO(content))
        header = next(csv_reader, None)

        if not header or len(header) < 3:
            raise ValidationError('CSV file is malformed or empty (missing header row).')

        # Build authoritative set of students enrolled in this class
        enrolled_students = Student.all_objects.filter(
            school=request.user.school,
            current_class=cg,
            is_active=True,
        ).values_list('id', flat=True)
        enrolled_ids = set(str(sid) for sid in enrolled_students)

        valid_rows = []
        errors = []
        seen_student_ids = set()  # For duplicate detection within the CSV

        for row_idx, row in enumerate(csv_reader, start=2):
            if not row or all(cell.strip() == '' for cell in row):
                continue  # skip blank rows
            if len(row) < 3:
                errors.append({'row': row_idx, 'student_id': '', 'error': f'Row {row_idx} is malformed (fewer than 3 columns).'})
                continue
            student_id = row[0].strip()
            score_str = row[3].strip() if len(row) > 3 else ''
            absent_str = row[4].strip().upper() if len(row) > 4 else 'FALSE'
            comment = row[5].strip() if len(row) > 5 else ''

            # Missing student ID
            if not student_id:
                errors.append({'row': row_idx, 'student_id': '', 'error': f'Row {row_idx}: Student ID is missing.'})
                continue

            # Duplicate within uploaded CSV
            if student_id in seen_student_ids:
                errors.append({'row': row_idx, 'student_id': student_id, 'error': f'Duplicate student ID "{student_id}" in this CSV upload.'})
                continue
            seen_student_ids.add(student_id)

            # Student does not belong to this class (wrong class / nonexistent)
            if student_id not in enrolled_ids:
                errors.append({'row': row_idx, 'student_id': student_id,
                               'error': f'Student ID "{student_id}" is not enrolled in {cg.name}. Possibly wrong class or student does not exist.'})
                continue

            is_absent = absent_str in ('TRUE', '1', 'YES', 'Y')
            score = None

            if not is_absent and score_str != '':
                try:
                    score = float(score_str)
                    if score < 0 or score > assessment.max_marks:
                        errors.append({'row': row_idx, 'student_id': student_id, 'error': f'Score {score} out of bounds (0-{assessment.max_marks}).'})
                        continue
                except ValueError:
                    errors.append({'row': row_idx, 'student_id': student_id, 'error': f'Invalid numeric score "{score_str}".'})
                    continue

            valid_rows.append({
                'student_id': student_id,
                'marks_obtained': score,
                'is_absent': is_absent,
                'comment': comment,
            })

        if dry_run:
            return Response({
                'message': f'Validation complete. {len(valid_rows)} valid rows, {len(errors)} errors.',
                'valid_count': len(valid_rows),
                'error_count': len(errors),
                'errors': errors,
                'preview': valid_rows[:10],
            })

        if errors:
            return Response({
                'error': f'Import aborted due to {len(errors)} validation errors.',
                'errors': errors,
            }, status=status.HTTP_400_BAD_REQUEST)

        # Apply marks import
        records = MarksService.enter_marks(assessment, valid_rows, request.user)
        self.log_action('MARKS_CSV_IMPORTED', assessment, {'count': len(records)})

        return Response({
            'message': f'{len(records)} marks imported successfully from CSV.',
            'assessment_id': str(assessment.id),
        })

