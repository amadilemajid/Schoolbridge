"""
Students views.
US-008: Bulk CSV import with error report.
US-009: Single student add.
US-010: Edit with before/after audit.
US-011: Guardian management.
US-012: Class group management + reassignment.
US-014: Search <500ms.
US-015: Enrolment report.
"""
import csv
import io
from django.db import transaction
from django.http import HttpResponse, FileResponse
from django.utils import timezone
from rest_framework import viewsets, generics, status
from rest_framework.decorators import action
from rest_framework.filters import SearchFilter, OrderingFilter
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser, FormParser
from drf_spectacular.utils import extend_schema, OpenApiTypes
from audit.mixins import AuditMixin
from schools.permissions import IsDirector, IsSchoolStaff, IsDirectorOrBursar, IsDirectorOrAdmin
from rest_framework.exceptions import ValidationError, NotFound
from config.validators import validate_uuid, validate_int
from config.mixins import ExportMixin
from .models import Student, Guardian, ClassGroup, BulkImportJob, ClassAssignment
from .serializers import (
    StudentListSerializer, StudentDetailSerializer, StudentCreateSerializer,
    GuardianSerializer, ClassGroupSerializer, BulkImportJobSerializer,
    StudentLookupSerializer,
)
from .services import StudentImportService, StudentSearchService
from .tasks import process_bulk_import


class ClassGroupViewSet(AuditMixin, viewsets.ModelViewSet):
    queryset = ClassGroup.objects.none()
    """US-012: Class group management."""
    serializer_class = ClassGroupSerializer
    pagination_class = None

    def get_permissions(self):
        if self.action in ('list', 'retrieve'):
            return [IsSchoolStaff()]
        return [IsDirector()]

    def get_queryset(self):
        qs = ClassGroup.objects.filter(school=self.request.user.school).order_by('level', 'name')
        is_active_param = self.request.query_params.get('is_active')
        if is_active_param == 'true':
            qs = qs.filter(is_active=True)
        elif is_active_param == 'false':
            qs = qs.filter(is_active=False)
        return qs

    def perform_create(self, serializer):
        cg = serializer.save(school=self.request.user.school)
        self.log_action('CLASS_CREATED', cg, {'name': cg.name})


class StudentViewSet(AuditMixin, viewsets.ModelViewSet):
    queryset = Student.objects.none()
    """
    US-009: Single student add.
    US-010: Edit with before/after audit.
    US-014: Search <500ms.
    """
    permission_classes = [IsSchoolStaff]

    def get_permissions(self):
        if self.action == 'destroy':
            return [IsDirector()]
        return super().get_permissions()

    def get_serializer_class(self):
        if self.action == 'create':
            return StudentCreateSerializer
        if self.action == 'list':
            return StudentListSerializer
        return StudentDetailSerializer

    def get_queryset(self):
        filter_kwargs = {'school': self.request.user.school}
        is_active_param = self.request.query_params.get('is_active')
        status_param = self.request.query_params.get('status')
        include_inactive = self.request.query_params.get('include_inactive', '').lower() in ('true', '1')

        is_active_filter = None
        if is_active_param is not None:
            if is_active_param.lower() in ('true', '1'):
                is_active_filter = True
            elif is_active_param.lower() in ('false', '0'):
                is_active_filter = False
        elif status_param is not None:
            if status_param.lower() == 'active':
                is_active_filter = True
            elif status_param.lower() == 'inactive':
                is_active_filter = False
        elif self.action == 'list' and not include_inactive:
            is_active_filter = True

        class_id = self.request.query_params.get('class_id') or self.request.query_params.get('current_class')
        class_id_int = None
        if class_id:
            validate_int(class_id, 'class_id')
            class_id_int = int(class_id)

        # US-014: Search (supports ?q=... or ?search=...)
        query = self.request.query_params.get('search') or self.request.query_params.get('q')
        if query:
            # If search is performed without an explicit active/inactive filter, return all matches (active & inactive)
            search_active_filter = is_active_filter if (is_active_param is not None or status_param is not None) else None
            return StudentSearchService.search(
                self.request.user.school,
                query,
                is_active=search_active_filter,
                class_id=class_id_int
            )

        if is_active_filter is not None:
            filter_kwargs['is_active'] = is_active_filter

        if class_id_int is not None:
            filter_kwargs['current_class_id'] = class_id_int

        qs = Student.all_objects.filter(
            **filter_kwargs
        ).select_related('current_class').prefetch_related('guardians')
        if getattr(self.request.user, 'role', '') in ('director', 'bursar', 'system_admin'):
            qs = qs.prefetch_related('fee_records')
        return qs

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        student = serializer.save()
        self.log_action('STUDENT_ADDED', student, {'student_id': student.student_id})
        detail_serializer = StudentDetailSerializer(student, context=self.get_serializer_context())
        headers = self.get_success_headers(detail_serializer.data)
        return Response(detail_serializer.data, status=status.HTTP_201_CREATED, headers=headers)

    def perform_create(self, serializer):
        student = serializer.save()
        self.log_action('STUDENT_ADDED', student, {'student_id': student.student_id})

    def perform_update(self, serializer):
        """US-010: Capture before/after for all edits."""
        instance = self.get_object()
        before = {
            'first_name': instance.first_name,
            'last_name': instance.last_name,
            'current_class': str(instance.current_class_id),
            'is_active': instance.is_active,
        }
        updated = serializer.save()
        after = {
            'first_name': updated.first_name,
            'last_name': updated.last_name,
            'current_class': str(updated.current_class_id),
            'is_active': updated.is_active,
        }
        if updated.is_active and not before['is_active']:
            updated.deactivated_at = None
            updated.deactivation_reason = ''
            updated.save(update_fields=['deactivated_at', 'deactivation_reason'])
            self.log_action('STUDENT_REACTIVATED', updated, {'student_id': updated.student_id})
        else:
            self.log_action('STUDENT_EDITED', updated, before=before, after=after)

    def destroy(self, request, *args, **kwargs):
        """
        Soft-deactivate student instead of hard cascading delete to protect financial,
        attendance, and academic ledger history. Restricted strictly to Director.
        """
        student = self.get_object()
        reason = request.data.get('reason', '') if hasattr(request, 'data') and isinstance(request.data, dict) else ''
        student.is_active = False
        student.deactivated_at = timezone.now()
        student.deactivation_reason = reason or 'Deactivated by Director'
        student.save(update_fields=['is_active', 'deactivated_at', 'deactivation_reason'])

        self.log_action('STUDENT_DEACTIVATED', student, {
            'student_id': student.student_id,
            'reason': student.deactivation_reason
        })
        return Response(
            {'message': f'Student {student.get_full_name()} ({student.student_id}) has been deactivated.'},
            status=status.HTTP_200_OK
        )

    @action(detail=True, methods=['post'], permission_classes=[IsDirector])
    def reactivate(self, request, pk=None):
        """Restore a deactivated student to active status."""
        student = self.get_object()
        student.is_active = True
        student.deactivated_at = None
        student.deactivation_reason = ''
        student.save(update_fields=['is_active', 'deactivated_at', 'deactivation_reason'])
        self.log_action('STUDENT_REACTIVATED', student, {'student_id': student.student_id})
        return Response(
            {'message': f'Student {student.get_full_name()} ({student.student_id}) has been reactivated.'},
            status=status.HTTP_200_OK
        )

    @action(detail=False, methods=['get'], permission_classes=[IsSchoolStaff])
    def lookup(self, request):
        """Lightweight endpoint for UI dropdowns."""
        qs = self.get_queryset()
        serializer = StudentLookupSerializer(qs, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=['post'], permission_classes=[IsDirector])
    def reassign_class(self, request, pk=None):
        """US-012: Reassign student to a new class; preserve history atomically."""
        student = self.get_object()
        class_id = request.data.get('class_id')
        term_id = request.data.get('term_id')
        if not class_id:
            raise ValidationError({'class_id': 'class_id is required.'})
        validate_int(class_id, 'class_id')
        try:
            new_class = ClassGroup.objects.get(id=class_id, school=request.user.school)
        except (ClassGroup.DoesNotExist, ValueError):
            raise NotFound('Class not found.')

        with transaction.atomic():
            # Close current assignment
            today = timezone.localdate()
            ClassAssignment.objects.filter(student=student, end_date__isnull=True).update(end_date=today)

            # Create new assignment
            from schools.models import AcademicTerm
            term = AcademicTerm.objects.filter(school=request.user.school, is_current=True).first()
            ClassAssignment.objects.create(
                student=student,
                class_group=new_class,
                academic_term=term,
                start_date=today,
                assigned_by=request.user,
            )
            old_class = student.current_class
            student.current_class = new_class
            student.save(update_fields=['current_class'])

        self.log_action('CLASS_REASSIGNED', student, {
            'from_class': str(old_class), 'to_class': str(new_class)
        })
        return Response({'message': f'{student.get_full_name()} moved to {new_class.name}.'})

    @action(detail=False, methods=['get'], permission_classes=[IsDirectorOrBursar])
    def enrolment_report(self, request):
        """US-015: Enrolment report by class, gender. JSON, CSV and PDF export."""
        fmt = request.query_params.get('format', 'json')
        school = request.user.school
        from django.db.models import Count, Q
        data = list(
            ClassGroup.objects.filter(school=school, is_active=True)
            .annotate(
                total=Count('current_students', filter=Q(current_students__is_active=True)),
                male=Count('current_students', filter=Q(
                    current_students__is_active=True, current_students__gender='M'
                )),
                female=Count('current_students', filter=Q(
                    current_students__is_active=True, current_students__gender='F'
                )),
            )
            .values('name', 'level', 'total', 'male', 'female')
            .order_by('level', 'name')
        )
        if fmt == 'csv':
            return self._enrolment_csv(data)
        if fmt == 'pdf':
            return self._enrolment_pdf(data, school)
        # JSON: include grand totals
        grand_total = sum(r['total'] for r in data)
        grand_male = sum(r['male'] for r in data)
        grand_female = sum(r['female'] for r in data)
        return Response({
            'school': school.name,
            'classes': data,
            'totals': {'total': grand_total, 'male': grand_male, 'female': grand_female},
        })

    def _enrolment_csv(self, data):
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="enrolment_report.csv"'
        writer = csv.writer(response)
        writer.writerow(['Class', 'Level', 'Male', 'Female', 'Total'])
        for row in data:
            writer.writerow([row['name'], row['level'], row['male'], row['female'], row['total']])
        return response

    def _enrolment_pdf(self, data, school):
        """US-015: PDF enrolment report with school name and date stamp."""
        try:
            from reportlab.lib.pagesizes import A4
            from reportlab.lib import colors
            from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
            from reportlab.lib.styles import getSampleStyleSheet
            from reportlab.lib.units import cm
            import io
        except ImportError:
            return Response({'error': 'PDF generation requires reportlab. Run: pip install reportlab'}, status=500)

        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=A4,
                                rightMargin=1.5*cm, leftMargin=1.5*cm,
                                topMargin=1.5*cm, bottomMargin=1.5*cm)
        styles = getSampleStyleSheet()
        elements = []

        elements.append(Paragraph(f"<b>{school.name.upper()}</b>", styles['Title']))
        elements.append(Paragraph("STUDENT ENROLMENT REPORT", styles['Heading2']))
        elements.append(Paragraph(
            f"Date: {timezone.localdate().strftime('%d %B %Y')}",
            styles['Normal']
        ))
        elements.append(Spacer(1, 0.4*cm))

        table_data = [['Class', 'Level', 'Male', 'Female', 'Total']]
        grand_total = grand_male = grand_female = 0
        for row in data:
            table_data.append([row['name'], row['level'], row['male'], row['female'], row['total']])
            grand_total += row['total']
            grand_male += row['male']
            grand_female += row['female']
        table_data.append(['TOTAL', '', grand_male, grand_female, grand_total])

        table = Table(table_data, colWidths=[5*cm, 4*cm, 3*cm, 3*cm, 3*cm])
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.darkblue),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
            ('BACKGROUND', (0, -1), (-1, -1), colors.lightgrey),
            ('ROWBACKGROUNDS', (0, 1), (-1, -2), [colors.white, colors.HexColor('#f0f0f0')]),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ('ALIGN', (2, 0), (-1, -1), 'CENTER'),
        ]))
        elements.append(table)

        doc.build(elements)
        buffer.seek(0)
        response = HttpResponse(buffer.read(), content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="enrolment_report_{timezone.localdate()}.pdf"'
        return response


class GuardianViewSet(ExportMixin, AuditMixin, viewsets.ModelViewSet):
    queryset = Guardian.objects.none()
    """US-011: Guardian management for a student."""
    serializer_class = GuardianSerializer
    permission_classes = [IsSchoolStaff]

    def get_queryset(self):
        student_pk = self.kwargs.get('student_pk')
        return Guardian.objects.filter(student_id=student_pk, student__school=self.request.user.school)

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        student_pk = self.kwargs.get('student_pk')
        try:
            ctx['student'] = Student.all_objects.get(pk=student_pk, school=self.request.user.school)
        except Student.DoesNotExist:
            pass
        return ctx

    def perform_create(self, serializer):
        student_pk = self.kwargs.get('student_pk')
        student = Student.all_objects.get(pk=student_pk, school=self.request.user.school)
        g = serializer.save(student=student)
        self.log_action('GUARDIAN_ADDED', student, {'guardian': g.phone})


class BulkImportView(AuditMixin, generics.CreateAPIView):
    """US-008: Bulk student CSV import."""
    permission_classes = [IsDirectorOrAdmin]
    parser_classes = [MultiPartParser, FormParser]

    @extend_schema(
        request={
            'multipart/form-data': {
                'type': 'object',
                'properties': {
                    'file': {
                        'type': 'string',
                        'format': 'binary',
                        'description': 'CSV file containing students'
                    }
                }
            }
        },
        responses={202: BulkImportJobSerializer}
    )
    def post(self, request, *args, **kwargs):
        csv_file = request.FILES.get('file')
        if not csv_file:
            return Response({'error': 'No file uploaded. Please upload a CSV file.'}, status=400)
        if not csv_file.name.endswith('.csv'):
            return Response({'error': 'File must be a CSV.'}, status=400)

        job = BulkImportJob.objects.create(
            school=request.user.school,
            uploaded_by=request.user,
            csv_file=csv_file,
        )
        # Run in background (Celery)
        process_bulk_import.delay(str(job.id))
        self.log_action('BULK_IMPORT_STARTED', None, {'job_id': str(job.id)})
        return Response(BulkImportJobSerializer(job).data, status=status.HTTP_202_ACCEPTED)


class BulkImportJobDetailView(generics.RetrieveAPIView):
    """Poll import job status."""
    serializer_class = BulkImportJobSerializer
    permission_classes = [IsDirectorOrAdmin]

    def get_queryset(self):
        return BulkImportJob.objects.filter(school=self.request.user.school)


class CSVTemplateView(generics.GenericAPIView):
    """US-008: Download the CSV import template."""
    permission_classes = [IsDirectorOrAdmin]

    @extend_schema(responses={200: OpenApiTypes.BINARY})
    def get(self, request):
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="student_import_template.csv"'
        writer = csv.writer(response)
        writer.writerow([
            'first_name', 'last_name', 'other_names', 'admission_number', 'gender',
            'date_of_birth', 'admission_date', 'class_name',
            'guardian_name', 'guardian_phone', 'guardian_relationship',
            'guardian2_name', 'guardian2_phone', 'guardian2_relationship',
        ])
        writer.writerow([
            'John', 'Mukasa', '', 'KDA-2026-001', 'M',
            '2012-03-15', '2024-02-05', 'P.7 East',
            'Sarah Mukasa', '0701234567', 'Mother',
            'Peter Mukasa', '0712345678', 'Father',
        ])
        return response


class GuardianListView(generics.ListAPIView):
    """
    School-wide guardian listing with search.
    GET /api/v1/students/guardians/
    Supports ?search=name_or_phone
    """
    serializer_class = GuardianSerializer
    permission_classes = [IsSchoolStaff]
    filter_backends = [SearchFilter, OrderingFilter]
    search_fields = ['first_name', 'last_name', 'phone', 'student__first_name', 'student__last_name']
    ordering_fields = ['first_name', 'last_name']
    ordering = ['last_name']

    def get_queryset(self):
        qs = Guardian.objects.filter(
            student__school=self.request.user.school
        ).select_related('student', 'student__current_class')

        is_primary = self.request.query_params.get('is_primary')
        student_id = self.request.query_params.get('student_id')
        if is_primary == 'true':
            qs = qs.filter(is_primary=True)
        if student_id:
            qs = qs.filter(student_id=student_id)
        return qs