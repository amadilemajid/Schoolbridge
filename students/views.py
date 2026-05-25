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
from django.http import HttpResponse, FileResponse
from django.utils import timezone
from rest_framework import viewsets, generics, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser, FormParser
from audit.mixins import AuditMixin
from schools.permissions import IsDirector, IsSchoolStaff, IsDirectorOrBursar

from .models import Student, Guardian, ClassGroup, BulkImportJob, ClassAssignment
from .serializers import (
    StudentListSerializer, StudentDetailSerializer, StudentCreateSerializer,
    GuardianSerializer, ClassGroupSerializer, BulkImportJobSerializer,
)
from .services import StudentImportService, StudentSearchService
from .tasks import process_bulk_import


class ClassGroupViewSet(AuditMixin, viewsets.ModelViewSet):
    """US-012: Class group management."""
    serializer_class = ClassGroupSerializer
    permission_classes = [IsDirector]

    def get_queryset(self):
        return ClassGroup.objects.filter(school=self.request.user.school)

    def perform_create(self, serializer):
        cg = serializer.save(school=self.request.user.school)
        self.log_action('CLASS_CREATED', cg, {'name': cg.name})


class StudentViewSet(AuditMixin, viewsets.ModelViewSet):
    """
    US-009: Single student add.
    US-010: Edit with before/after audit.
    US-014: Search <500ms.
    """
    permission_classes = [IsSchoolStaff]

    def get_serializer_class(self):
        if self.action == 'create':
            return StudentCreateSerializer
        if self.action == 'list':
            return StudentListSerializer
        return StudentDetailSerializer

    def get_queryset(self):
        qs = Student.all_objects.filter(
            school=self.request.user.school, is_active=True
        ).select_related('current_class').prefetch_related('guardians')
        # US-014: Search
        query = self.request.query_params.get('q')
        if query:
            return StudentSearchService.search(self.request.user.school, query)
        # Filter by class
        class_id = self.request.query_params.get('class_id')
        if class_id:
            qs = qs.filter(current_class_id=class_id)
        return qs

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
        self.log_action('STUDENT_EDITED', updated, before=before, after=after)

    @action(detail=True, methods=['post'], permission_classes=[IsDirector])
    def reassign_class(self, request, pk=None):
        """US-012: Reassign student to a new class; preserve history."""
        student = self.get_object()
        class_id = request.data.get('class_id')
        term_id = request.data.get('term_id')
        if not class_id:
            return Response({'error': 'class_id is required.'}, status=400)
        try:
            new_class = ClassGroup.objects.get(id=class_id, school=request.user.school)
        except ClassGroup.DoesNotExist:
            return Response({'error': 'Class not found.'}, status=404)

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
        """US-015: Enrolment report by class, gender, year. PDF + Excel export."""
        fmt = request.query_params.get('format', 'json')
        school = request.user.school
        from django.db.models import Count, Q
        data = (
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
        return Response(list(data))

    def _enrolment_csv(self, data):
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="enrolment_report.csv"'
        writer = csv.writer(response)
        writer.writerow(['Class', 'Level', 'Male', 'Female', 'Total'])
        for row in data:
            writer.writerow([row['name'], row['level'], row['male'], row['female'], row['total']])
        return response


class GuardianViewSet(AuditMixin, viewsets.ModelViewSet):
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
    permission_classes = [IsDirector]
    parser_classes = [MultiPartParser, FormParser]

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
    permission_classes = [IsDirector]

    def get_queryset(self):
        return BulkImportJob.objects.filter(school=self.request.user.school)


class CSVTemplateView(generics.GenericAPIView):
    """US-008: Download the CSV import template."""
    permission_classes = [IsDirector]

    def get(self, request):
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="student_import_template.csv"'
        writer = csv.writer(response)
        writer.writerow([
            'first_name', 'last_name', 'other_names', 'gender',
            'date_of_birth', 'admission_date', 'class_name',
            'guardian_name', 'guardian_phone', 'guardian_relationship',
            'guardian2_name', 'guardian2_phone', 'guardian2_relationship',
        ])
        writer.writerow([
            'John', 'Mukasa', '', 'M', '2012-03-15', '2024-02-05',
            'P.7 East', 'Sarah Mukasa', '0701234567', 'Mother',
            'Peter Mukasa', '0712345678', 'Father',
        ])
        return response
