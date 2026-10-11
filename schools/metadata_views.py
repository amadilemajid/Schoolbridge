"""
Global Reference & Metadata APIs (US-F01).
Provides drop-down data, enums, and quick lookups for the frontend.
"""
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import generics, serializers
from rest_framework.filters import SearchFilter
from drf_spectacular.utils import extend_schema, inline_serializer

from authentication.models import User
from students.models import ClassGroup, Student, Guardian
from schools.models import AcademicTerm
from attendance.models import AttendanceRecord
from payments.models import Payment


class SystemMetadataView(APIView):
    """
    Returns global choices and configuration for the active school.
    Used by the frontend to populate dropdowns (roles, classes, terms).
    """
    permission_classes = [IsAuthenticated]

    @extend_schema(
        responses={
            200: inline_serializer(
                name='SystemMetadataResponse',
                fields={
                    'roles': serializers.ListField(child=serializers.DictField()),
                    'attendance_statuses': serializers.ListField(child=serializers.DictField()),
                    'classes': serializers.ListField(child=serializers.DictField()),
                    'current_term': serializers.DictField(allow_null=True),
                }
            )
        },
        tags=['Metadata']
    )
    def get(self, request):
        school = request.user.school
        
        # User Roles
        roles = [{'value': k, 'label': v} for k, v in User.ROLE_CHOICES if k != 'system_admin']
        
        # Attendance Statuses
        attendance_statuses = [{'value': k, 'label': v} for k, v in AttendanceRecord.STATUS_CHOICES]
        
        # Active Classes
        db_classes = list(ClassGroup.objects.filter(school=school, is_active=True).values('id', 'name', 'level', 'stream'))
        if not db_classes:
            db_classes = [
                {'id': 'p1', 'name': 'Primary 1 (P.1)', 'level': 'P1', 'stream': 'All Streams'},
                {'id': 'p2', 'name': 'Primary 2 (P.2)', 'level': 'P2', 'stream': 'All Streams'},
                {'id': 'p3', 'name': 'Primary 3 (P.3)', 'level': 'P3', 'stream': 'All Streams'},
                {'id': 'p4', 'name': 'Primary 4 (P.4)', 'level': 'P4', 'stream': 'All Streams'},
                {'id': 'p5', 'name': 'Primary 5 (P.5)', 'level': 'P5', 'stream': 'All Streams'},
                {'id': 'p6', 'name': 'Primary 6 (P.6)', 'level': 'P6', 'stream': 'All Streams'},
                {'id': 'p7', 'name': 'Primary 7 (P.7)', 'level': 'P7', 'stream': 'All Streams'},
                {'id': 's1', 'name': 'Senior 1 (S.1)', 'level': 'S1', 'stream': 'All Streams'},
                {'id': 's2', 'name': 'Senior 2 (S.2)', 'level': 'S2', 'stream': 'All Streams'},
                {'id': 's3', 'name': 'Senior 3 (S.3)', 'level': 'S3', 'stream': 'All Streams'},
                {'id': 's4', 'name': 'Senior 4 (S.4)', 'level': 'S4', 'stream': 'All Streams'},
                {'id': 's5', 'name': 'Senior 5 (S.5)', 'level': 'S5', 'stream': 'All Streams'},
                {'id': 's6', 'name': 'Senior 6 (S.6)', 'level': 'S6', 'stream': 'All Streams'},
                {'id': 'n1', 'name': 'Baby Class (Nursery)', 'level': 'Baby Class', 'stream': 'All Streams'},
                {'id': 'n2', 'name': 'Middle Class (Nursery)', 'level': 'Middle Class', 'stream': 'All Streams'},
                {'id': 'n3', 'name': 'Top Class (Nursery)', 'level': 'Top Class', 'stream': 'All Streams'},
            ]
        
        # Active Subjects from Results app
        from results.models import Subject
        db_subjects = list(Subject.objects.filter(school=school, is_active=True).values('id', 'name', 'code', 'class_levels'))
        if not db_subjects:
            db_subjects = [
                {'id': 'sub-p1', 'name': 'English Language', 'code': 'ENG', 'class_levels': 'P1,P2,P3,P4,P5,P6,P7,S1,S2,S3,S4'},
                {'id': 'sub-p2', 'name': 'Mathematics', 'code': 'MTC', 'class_levels': 'P1,P2,P3,P4,P5,P6,P7,S1,S2,S3,S4'},
                {'id': 'sub-p3', 'name': 'Basic Science & Technology', 'code': 'SCI', 'class_levels': 'P1,P2,P3,P4,P5,P6,P7'},
                {'id': 'sub-p4', 'name': 'Social Studies (SST)', 'code': 'SST', 'class_levels': 'P1,P2,P3,P4,P5,P6,P7'},
                {'id': 'sub-p5', 'name': 'Christian Religious Education (CRE)', 'code': 'CRE', 'class_levels': 'P1,P2,P3,P4,P5,P6,P7,S1,S2,S3,S4'},
                {'id': 'sub-p6', 'name': 'Islamic Religious Education (IRE)', 'code': 'IRE', 'class_levels': 'P1,P2,P3,P4,P5,P6,P7,S1,S2,S3,S4'},
                {'id': 'sub-p7', 'name': 'Luganda / Local Language', 'code': 'LUG', 'class_levels': 'P1,P2,P3,P4,P5,P6,P7,S1,S2,S3,S4'},
                {'id': 'sub-p8', 'name': 'Physical Education (PE)', 'code': 'PE', 'class_levels': 'P1,P2,P3,P4,P5,P6,P7,S1,S2,S3,S4'},
                {'id': 'sub-o1', 'name': 'Biology', 'code': 'BIO', 'class_levels': 'S1,S2,S3,S4,S5,S6'},
                {'id': 'sub-o2', 'name': 'Chemistry', 'code': 'CHE', 'class_levels': 'S1,S2,S3,S4,S5,S6'},
                {'id': 'sub-o3', 'name': 'Physics', 'code': 'PHY', 'class_levels': 'S1,S2,S3,S4,S5,S6'},
                {'id': 'sub-o4', 'name': 'Geography', 'code': 'GEO', 'class_levels': 'S1,S2,S3,S4,S5,S6'},
                {'id': 'sub-o5', 'name': 'History & Political Education', 'code': 'HIS', 'class_levels': 'S1,S2,S3,S4,S5,S6'},
                {'id': 'sub-o6', 'name': 'Entrepreneurship Education', 'code': 'ENT', 'class_levels': 'S1,S2,S3,S4,S5,S6'},
                {'id': 'sub-o7', 'name': 'Information & Communication Tech (ICT)', 'code': 'ICT', 'class_levels': 'S1,S2,S3,S4'},
                {'id': 'sub-o8', 'name': 'Agriculture', 'code': 'AGR', 'class_levels': 'S1,S2,S3,S4,S5,S6'},
                {'id': 'sub-o9', 'name': 'Literature in English', 'code': 'LIT', 'class_levels': 'S1,S2,S3,S4,S5,S6'},
                {'id': 'sub-a1', 'name': 'General Paper (GP)', 'code': 'GP', 'class_levels': 'S5,S6'},
                {'id': 'sub-a2', 'name': 'Subsidiary Mathematics', 'code': 'SMTC', 'class_levels': 'S5,S6'},
                {'id': 'sub-a3', 'name': 'Subsidiary ICT', 'code': 'SICT', 'class_levels': 'S5,S6'},
                {'id': 'sub-a4', 'name': 'Pure Mathematics', 'code': 'PMTC', 'class_levels': 'S5,S6'},
                {'id': 'sub-a5', 'name': 'Economics', 'code': 'ECON', 'class_levels': 'S5,S6'},
                {'id': 'sub-a6', 'name': 'Fine Art', 'code': 'ART', 'class_levels': 'S5,S6'},
            ]

        # Current Term
        term = AcademicTerm.objects.filter(school=school, is_current=True).first()
        current_term = None
        if term:
            current_term = {
                'id': term.id,
                'name': term.name,
                'start_date': term.start_date,
                'end_date': term.end_date,
            }

        # Payment Methods
        payment_methods = [{'value': k, 'label': v} for k, v in Payment.PAYMENT_METHODS]

        # Standard Fee Waiver / Bursary Reasons (US-024)
        waiver_reasons = [
            {'value': 'academic_scholarship', 'label': 'Academic Scholarship'},
            {'value': 'staff_child_discount', 'label': 'Staff Child Discount'},
            {'value': 'sibling_discount', 'label': 'Sibling Discount'},
            {'value': 'orphan_bursary', 'label': 'Orphan / Vulnerability Bursary'},
            {'value': 'sports_scholarship', 'label': 'Sports Scholarship'},
            {'value': 'partial_payment_agreement', 'label': 'Partial Payment Agreement'},
            {'value': 'other', 'label': 'Other (specify below)'},
        ]

        return Response({
            'roles': roles,
            'attendance_statuses': attendance_statuses,
            'classes': db_classes,
            'subjects': db_subjects,
            'current_term': current_term,
            'payment_methods': payment_methods,
            'waiver_reasons': waiver_reasons,
            'currency': 'UGX',
        })


class StaffLookupSerializer(serializers.ModelSerializer):
    full_name = serializers.CharField(source='get_full_name', read_only=True)
    
    class Meta:
        model = User
        fields = ['id', 'full_name', 'email', 'role']


class StaffLookupView(generics.ListAPIView):
    """Lightweight endpoint for fetching staff for dropdown assignments."""
    permission_classes = [IsAuthenticated]
    serializer_class = StaffLookupSerializer
    pagination_class = None

    def get_queryset(self):
        return User.objects.filter(
            school=self.request.user.school, 
            is_active=True
        ).exclude(role='system_admin').order_by('last_name', 'first_name')


class StudentLookupSerializer(serializers.ModelSerializer):
    full_name = serializers.CharField(source='get_full_name', read_only=True)
    class_name = serializers.CharField(source='current_class.name', read_only=True)
    
    class Meta:
        model = Student
        fields = ['id', 'student_id', 'full_name', 'class_name']


class StudentLookupView(generics.ListAPIView):
    """Lightweight endpoint for fetching students for dropdowns."""
    permission_classes = [IsAuthenticated]
    serializer_class = StudentLookupSerializer
    pagination_class = None
    filter_backends = [SearchFilter]
    search_fields = ['first_name', 'last_name', 'student_id']

    def get_queryset(self):
        return Student.all_objects.filter(
            school=self.request.user.school, 
            is_active=True
        ).select_related('current_class').order_by('last_name', 'first_name')


class GuardianLookupSerializer(serializers.ModelSerializer):
    full_name = serializers.CharField(source='get_full_name', read_only=True)
    
    class Meta:
        model = Guardian
        fields = ['id', 'full_name', 'phone', 'relationship']


class GuardianLookupView(generics.ListAPIView):
    """Lightweight endpoint for fetching guardians for dropdowns."""
    permission_classes = [IsAuthenticated]
    serializer_class = GuardianLookupSerializer
    pagination_class = None

    def get_queryset(self):
        return Guardian.objects.filter(
            school=self.request.user.school
        ).order_by('last_name', 'first_name')
