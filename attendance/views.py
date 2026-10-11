"""Attendance views — register submission, summaries, reports."""
from django.utils import timezone
from rest_framework import generics, status, viewsets
from rest_framework.decorators import api_view, permission_classes
from rest_framework.filters import SearchFilter, OrderingFilter
from rest_framework.response import Response
from rest_framework import serializers as drf_serializers
from rest_framework.views import APIView
from drf_spectacular.utils import extend_schema, OpenApiParameter, OpenApiTypes, inline_serializer
from rest_framework.exceptions import ValidationError, NotFound, PermissionDenied
from config.validators import validate_uuid, validate_int
from config.mixins import ExportMixin

from audit.mixins import AuditMixin
from schools.permissions import IsTeacher, IsDirector, IsDirectorOrBursar, IsSchoolStaff
from .models import AttendanceRecord
from .services import AttendanceService


class AttendanceRecordSerializer(drf_serializers.ModelSerializer):
    student_id = drf_serializers.UUIDField(source='student.id', read_only=True)
    student_name = drf_serializers.CharField(source='student.get_full_name', read_only=True)
    student_reg_no = drf_serializers.CharField(source='student.student_id', read_only=True)

    class Meta:
        model = AttendanceRecord
        fields = [
            'id', 'student', 'student_id', 'student_name', 'student_reg_no', 'date', 'status',
            'notes', 'pre_excused', 'pre_excused_reason', 'marked_by',
        ]
        read_only_fields = ['id', 'student_id', 'student_name', 'student_reg_no', 'pre_excused', 'pre_excused_reason', 'marked_by']


class AttendanceRegisterView(AuditMixin, APIView):
    """
    US-049: GET — fetch today's register for a class (open to school staff).
              POST — submit register (form teacher or director only, 7am–12pm).
    """
    permission_classes = [IsSchoolStaff]

    @extend_schema(
        parameters=[
            OpenApiParameter('class_id', OpenApiTypes.UUID, OpenApiParameter.QUERY, required=True),
            OpenApiParameter('date', OpenApiTypes.DATE, OpenApiParameter.QUERY, required=False),
        ],
        tags=['Attendance'],
        responses={200: inline_serializer(name='AttendanceRegisterGetResponse', fields={'date': drf_serializers.CharField(), 'class': drf_serializers.CharField(), 'register_open': drf_serializers.BooleanField(), 'records': AttendanceRecordSerializer(many=True)})}
    )

    def get(self, request):
        class_id = request.query_params.get('class_id')
        date_str = request.query_params.get('date', str(timezone.localdate()))
        if not class_id:
            raise ValidationError({'class_id': 'class_id required.'})
        validate_int(class_id, 'class_id')

        from students.models import ClassGroup
        from schools.models import AcademicTerm
        try:
            class_group = ClassGroup.objects.get(id=class_id, school=request.user.school)
        except ClassGroup.DoesNotExist:
            raise NotFound('Class not found.')

        from datetime import date
        try:
            record_date = date.fromisoformat(date_str)
        except ValueError:
            raise ValidationError({'date': 'Invalid date format. Use YYYY-MM-DD.'})

        term = AcademicTerm.objects.filter(
            school=request.user.school,
            start_date__lte=record_date, end_date__gte=record_date,
        ).first() or request.user.school.terms.filter(is_current=True).first()
        if not term:
            raise ValidationError('No current active academic term found.')
        records = AttendanceService.get_or_create_register(class_group, term, record_date, request.user)
        sorted_records = sorted(
            records.values(),
            key=lambda r: (r.student.last_name.lower() if r.student else '', r.student.first_name.lower() if r.student else '')
        )
        serializer = AttendanceRecordSerializer(sorted_records, many=True)
        is_open = AttendanceService.is_register_open(request.user.school)
        is_submitted = any(r.marked_by_id is not None for r in records.values())
        return Response({
            'date': str(record_date),
            'class': class_group.name,
            'register_open': is_open,
            'is_locked': is_submitted or not is_open,
            'records': serializer.data,
        })

    @extend_schema(
        request=inline_serializer(
            name='AttendanceRegisterRequest',
            fields={
                'class_id': drf_serializers.CharField(),
                'date': drf_serializers.DateField(required=False),
                'attendance': drf_serializers.ListField(child=drf_serializers.DictField()),
            },
        ),
        tags=['Attendance'],
        responses={200: inline_serializer(name='AttendanceRegisterPostResponse', fields={'message': drf_serializers.CharField()})}
    )

    def post(self, request):
        """Submit the attendance register."""
        class_id = request.data.get('class_id')
        date_str = request.data.get('date', str(timezone.localdate()))
        attendance_data = request.data.get('attendance', [])

        if not class_id or not attendance_data:
            raise ValidationError('class_id and attendance are required.')
        validate_int(class_id, 'class_id')

        from students.models import ClassGroup
        try:
            class_group = ClassGroup.objects.get(id=class_id, school=request.user.school)
        except ClassGroup.DoesNotExist:
            raise NotFound('Class not found.')

        if request.user.role not in ('teacher', 'director', 'school_admin', 'system_admin'):
            raise PermissionDenied('Only teachers and administrators can submit attendance registers.')

        if request.user.role == 'teacher' and class_group.form_teacher_id != request.user.id:
            raise PermissionDenied('You are only permitted to submit attendance for your assigned class.')

        from datetime import date
        try:
            record_date = date.fromisoformat(date_str)
        except ValueError:
            raise ValidationError({'date': 'Invalid date format.'})

        try:
            records = AttendanceService.submit_register(
                class_group=class_group,
                date=record_date,
                attendance_data=attendance_data,
                marked_by=request.user,
            )
        except ValueError as e:
            raise ValidationError(str(e))

        self.log_action('ATTENDANCE_SUBMITTED', None, {
            'class': class_group.name, 'date': str(record_date), 'count': len(records)
        })
        return Response({
            'message': 'Success: Attendance submitted and locked for today.',
            'locked': True,
            'is_locked': True,
            'count': len(records),
        })


class AttendanceSummaryView(APIView):
    """US-050: Attendance summary and rates per student."""
    permission_classes = [IsSchoolStaff]

    @extend_schema(
        parameters=[
            OpenApiParameter('student_id', OpenApiTypes.UUID, OpenApiParameter.QUERY, required=False),
            OpenApiParameter('class_id', OpenApiTypes.UUID, OpenApiParameter.QUERY, required=False),
        ],
        tags=['Attendance'],
        responses={200: inline_serializer(name='AttendanceSummaryResponse', fields={'student_id': drf_serializers.CharField(), 'student_name': drf_serializers.CharField(), 'attendance_rate': drf_serializers.FloatField(allow_null=True), 'below_threshold': drf_serializers.BooleanField()})}
    )

    def get(self, request):
        student_id = request.query_params.get('student_id')
        class_id = request.query_params.get('class_id')
        school = request.user.school
        term = school.terms.filter(is_current=True).first()
        if not term:
            raise ValidationError('No current term.')

        from students.models import Student
        if student_id:
            validate_uuid(student_id, 'student_id')
            try:
                student = Student.all_objects.get(id=student_id, school=school)
                rate = AttendanceService.get_attendance_rate(student, term)
                return Response({
                    'student_id': str(student.id),
                    'student_name': student.get_full_name(),
                    'attendance_rate': round(rate, 1) if rate is not None else None,
                    'below_threshold': rate is not None and rate < 75,
                })
            except Student.DoesNotExist:
                raise NotFound('Student not found.')

        # Class summary
        if class_id:
            validate_int(class_id, 'class_id')
            from students.models import ClassGroup
            try:
                cg = ClassGroup.objects.get(id=class_id, school=school)
            except ClassGroup.DoesNotExist:
                raise NotFound('Class not found.')
            students = Student.all_objects.filter(school=school, current_class=cg, is_active=True)
            
            # Bulk query aggregates to eliminate N+1 queries (US-073 performance)
            from django.db.models import Count, Q
            from .models import AttendanceRecord
            
            stats = AttendanceRecord.all_objects.filter(
                class_group=cg,
                academic_term=term,
                student__is_active=True
            ).values('student_id').annotate(
                total=Count('id'),
                present=Count('id', filter=Q(status__in=['present', 'late']))
            )
            
            rates = {
                str(stat['student_id']): (stat['present'] / stat['total'] * 100) if stat['total'] > 0 else None
                for stat in stats
            }
            
            data = []
            for s in students:
                rate = rates.get(str(s.id))
                data.append({
                    'student_id': str(s.id),
                    'student_name': s.get_full_name(),
                    'attendance_rate': round(rate, 1) if rate is not None else None,
                    'below_threshold': rate is not None and rate < 75,
                })
            return Response(data)

        # --- School-wide aggregate fallback (P2: US-050 admin overview) ---
        from students.models import ClassGroup
        from django.db.models import Count, Q

        role = request.user.role

        # Teachers without explicit params → redirect to their own form class
        if role == 'teacher':
            from students.models import ClassGroup as CG
            form_class = CG.objects.filter(school=school, form_teacher=request.user).first()
            if form_class:
                students = Student.all_objects.filter(school=school, current_class=form_class, is_active=True)
                stats = AttendanceRecord.all_objects.filter(
                    class_group=form_class, academic_term=term, student__is_active=True
                ).values('student_id').annotate(
                    total=Count('id'),
                    present=Count('id', filter=Q(status__in=['present', 'late']))
                )
                rates = {
                    str(s['student_id']): (s['present'] / s['total'] * 100) if s['total'] > 0 else None
                    for s in stats
                }
                data = [
                    {
                        'student_id': str(s.id),
                        'student_name': s.get_full_name(),
                        'attendance_rate': round(rates.get(str(s.id)), 1) if rates.get(str(s.id)) is not None else None,
                        'below_threshold': rates.get(str(s.id)) is not None and rates.get(str(s.id)) < 75,
                    }
                    for s in students
                ]
                return Response({'scope': 'class', 'class': form_class.name, 'data': data})
            raise ValidationError('You do not have a form class assigned.')

        # Admin/Director/Bursar/System-Admin → school-wide aggregate
        if role in ('director', 'bursar', 'school_admin', 'system_admin'):
            all_classes = ClassGroup.objects.filter(school=school, is_active=True)
            all_stats = AttendanceRecord.all_objects.filter(
                school=school, academic_term=term, student__is_active=True
            ).values('class_group_id').annotate(
                total=Count('id'),
                present=Count('id', filter=Q(status__in=['present', 'late'])),
                below_threshold_count=Count(
                    'student_id',
                    filter=Q(status__in=['absent', 'excused']),
                    distinct=True
                )
            )

            class_rate_map = {
                str(s['class_group_id']): {
                    'rate': round(s['present'] / s['total'] * 100, 1) if s['total'] > 0 else None,
                    'total_sessions': s['total'],
                    'present_sessions': s['present'],
                }
                for s in all_stats
            }

            class_breakdown = []
            total_sessions = 0
            present_sessions = 0
            for cg in all_classes:
                cg_stats = class_rate_map.get(str(cg.id), {})
                rate = cg_stats.get('rate')
                class_breakdown.append({
                    'class_id': cg.id,
                    'class_name': cg.name,
                    'attendance_rate': rate,
                    'below_threshold': rate is not None and rate < 75,
                })
                total_sessions += cg_stats.get('total_sessions', 0)
                present_sessions += cg_stats.get('present_sessions', 0)

            overall_rate = round(present_sessions / total_sessions * 100, 1) if total_sessions > 0 else None
            total_active_students = Student.all_objects.filter(school=school, is_active=True).count()
            classes_below = sum(1 for c in class_breakdown if c['below_threshold'])

            return Response({
                'scope': 'school',
                'term': term.name if hasattr(term, 'name') else str(term),
                'total_active_students': total_active_students,
                'overall_attendance_rate': overall_rate,
                'classes_below_threshold': classes_below,
                'class_breakdown': class_breakdown,
            })

        raise ValidationError('student_id or class_id required.')


class AttendanceVsFeesView(APIView):
    """US-053: Cross-reference attendance vs fees (from Week 4 of term)."""
    permission_classes = [IsDirectorOrBursar]

    @extend_schema(
        tags=['Attendance'],
        responses={200: inline_serializer(name='AttendanceVsFeesResponse', fields={'data': drf_serializers.ListField(child=drf_serializers.DictField()), 'count': drf_serializers.IntegerField(), 'message': drf_serializers.CharField(required=False)})}
    )

    def get(self, request):
        school = request.user.school
        term = school.terms.filter(is_current=True).first()
        if not term:
            raise ValidationError('No current term.')
        data, error = AttendanceService.get_attendance_vs_fees(school, term)
        if error:
            return Response({'message': error, 'data': []})
        return Response({'data': data, 'count': len(data)})


class AttendanceReminderView(APIView):
    """US-076: Manually trigger reminder to class teachers who haven't submitted."""
    permission_classes = [IsDirector]

    @extend_schema(
        request=None,
        tags=['Attendance'],
        responses={200: inline_serializer(name='AttendanceReminderResponse', fields={'message': drf_serializers.CharField()})}
    )

    def post(self, request):
        school = request.user.school
        from automation.services import CalendarService
        if not CalendarService.is_school_day(school, timezone.localdate()):
            return Response({'message': 'Today is not a school day.'})
        # Find classes without today's attendance
        from students.models import ClassGroup
        today = timezone.localdate()
        classes_with_attendance = AttendanceRecord.all_objects.filter(
            school=school, date=today
        ).values_list('class_group_id', flat=True).distinct()
        classes_without = ClassGroup.objects.filter(
            school=school, is_active=True
        ).exclude(id__in=classes_with_attendance)
        notified = 0
        from notifications.services import NotificationService
        for cg in classes_without:
            if cg.form_teacher:
                NotificationService.notify_user(
                    user=cg.form_teacher,
                    message=f"Reminder: Please submit attendance for {cg.name}.",
                    notification_type='ATTENDANCE_REMINDER',
                )
                notified += 1
        return Response({'message': f'Reminded {notified} teachers.'})


class AttendanceRecordViewSet(ExportMixin, AuditMixin, viewsets.ModelViewSet):
    """
    Direct CRUD access to attendance records.
    Allows staff to view and correct individual records.
    GET  /api/v1/attendance/records/
    GET  /api/v1/attendance/records/{id}/
    PATCH /api/v1/attendance/records/{id}/
    """
    serializer_class = AttendanceRecordSerializer
    permission_classes = [IsSchoolStaff]
    filter_backends = [SearchFilter, OrderingFilter]
    search_fields = ['student__first_name', 'student__last_name', 'student__student_id', 'notes']
    ordering_fields = ['date', 'status', 'created_at']
    ordering = ['-date']
    http_method_names = ['get', 'patch', 'head', 'options']  # No create/delete through this ViewSet
    lookup_field = 'pk'
    lookup_value_regex = '[0-9a-f-]+'

    def get_queryset(self):
        qs = AttendanceRecord.objects.filter(
            school=self.request.user.school
        ).select_related('student', 'class_group', 'marked_by', 'academic_term')

        class_id = self.request.query_params.get('class_id')
        student_id = self.request.query_params.get('student_id')
        term_id = self.request.query_params.get('term_id')
        date_from = self.request.query_params.get('date_from')
        date_to = self.request.query_params.get('date_to')
        status_filter = self.request.query_params.get('status')

        if class_id:
            qs = qs.filter(class_group_id=class_id)
        if student_id:
            qs = qs.filter(student_id=student_id)
        if term_id:
            qs = qs.filter(academic_term_id=term_id)
        if date_from:
            qs = qs.filter(date__gte=date_from)
        if date_to:
            qs = qs.filter(date__lte=date_to)
        if status_filter:
            qs = qs.filter(status=status_filter)

        return qs

    def perform_update(self, serializer):
        instance = self.get_object()
        user = self.request.user
        # Directors and system admins can authorize corrections on historical records
        if user.role not in ('director', 'system_admin'):
            today = timezone.localdate()
            if instance.date != today:
                raise ValidationError(
                    'Historical attendance records are finalized and locked. '
                    'Only the School Director can authorize corrections.'
                )
            if not AttendanceService.is_register_open(user.school):
                raise ValidationError(
                    'The daily attendance window (7:00 AM – 12:00 PM) has closed. '
                    'Contact the School Director to record corrections.'
                )
        serializer.save(marked_by=self.request.user)
        self.log_action('ATTENDANCE_RECORD_UPDATED', instance, {
            'student': instance.student.get_full_name(),
            'date': str(instance.date),
            'new_status': serializer.validated_data.get('status', instance.status),
        })

