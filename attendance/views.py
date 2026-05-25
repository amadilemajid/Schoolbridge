"""Attendance views — register submission, summaries, reports."""
from django.utils import timezone
from rest_framework import generics, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework import serializers as drf_serializers
from rest_framework.views import APIView

from audit.mixins import AuditMixin
from schools.permissions import IsTeacher, IsDirector, IsDirectorOrBursar, IsSchoolStaff
from .models import AttendanceRecord
from .services import AttendanceService


class AttendanceRecordSerializer(drf_serializers.ModelSerializer):
    student_name = drf_serializers.CharField(source='student.get_full_name', read_only=True)

    class Meta:
        model = AttendanceRecord
        fields = [
            'id', 'student', 'student_name', 'date', 'status',
            'notes', 'pre_excused', 'pre_excused_reason', 'marked_by',
        ]
        read_only_fields = ['id', 'pre_excused', 'pre_excused_reason', 'marked_by']


class AttendanceRegisterView(AuditMixin, APIView):
    """
    US-049: GET — fetch today's register for a class.
              POST — submit register (7am–12pm only, locks at 12pm).
    """
    permission_classes = [IsTeacher]

    def get(self, request):
        class_id = request.query_params.get('class_id')
        date_str = request.query_params.get('date', str(timezone.localdate()))
        if not class_id:
            return Response({'error': 'class_id required.'}, status=400)

        from students.models import ClassGroup
        from schools.models import AcademicTerm
        try:
            class_group = ClassGroup.objects.get(id=class_id, school=request.user.school)
        except ClassGroup.DoesNotExist:
            return Response({'error': 'Class not found.'}, status=404)

        from datetime import date
        try:
            record_date = date.fromisoformat(date_str)
        except ValueError:
            return Response({'error': 'Invalid date format. Use YYYY-MM-DD.'}, status=400)

        term = request.user.school.terms.filter(is_current=True).first()
        records = AttendanceService.get_or_create_register(class_group, term, record_date, request.user)
        serializer = AttendanceRecordSerializer(list(records.values()), many=True)
        is_open = AttendanceService.is_register_open(request.user.school)
        return Response({
            'date': str(record_date),
            'class': class_group.name,
            'register_open': is_open,
            'records': serializer.data,
        })

    def post(self, request):
        """Submit the attendance register."""
        class_id = request.data.get('class_id')
        date_str = request.data.get('date', str(timezone.localdate()))
        attendance_data = request.data.get('attendance', [])

        if not class_id or not attendance_data:
            return Response({'error': 'class_id and attendance are required.'}, status=400)

        from students.models import ClassGroup
        try:
            class_group = ClassGroup.objects.get(id=class_id, school=request.user.school)
        except ClassGroup.DoesNotExist:
            return Response({'error': 'Class not found.'}, status=404)

        from datetime import date
        try:
            record_date = date.fromisoformat(date_str)
        except ValueError:
            return Response({'error': 'Invalid date format.'}, status=400)

        try:
            records = AttendanceService.submit_register(
                class_group=class_group,
                date=record_date,
                attendance_data=attendance_data,
                marked_by=request.user,
            )
        except ValueError as e:
            return Response({'error': str(e)}, status=400)

        self.log_action('ATTENDANCE_SUBMITTED', None, {
            'class': class_group.name, 'date': str(record_date), 'count': len(records)
        })
        return Response({'message': f'Attendance submitted for {len(records)} students.'})


class AttendanceSummaryView(APIView):
    """US-050: Attendance summary and rates per student."""
    permission_classes = [IsSchoolStaff]

    def get(self, request):
        student_id = request.query_params.get('student_id')
        class_id = request.query_params.get('class_id')
        school = request.user.school
        term = school.terms.filter(is_current=True).first()
        if not term:
            return Response({'error': 'No current term.'}, status=400)

        from students.models import Student
        if student_id:
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
                return Response({'error': 'Student not found.'}, status=404)

        # Class summary
        if class_id:
            from students.models import ClassGroup
            try:
                cg = ClassGroup.objects.get(id=class_id, school=school)
            except ClassGroup.DoesNotExist:
                return Response({'error': 'Class not found.'}, status=404)
            students = Student.all_objects.filter(school=school, current_class=cg, is_active=True)
            data = []
            for s in students:
                rate = AttendanceService.get_attendance_rate(s, term)
                data.append({
                    'student_id': str(s.id),
                    'student_name': s.get_full_name(),
                    'attendance_rate': round(rate, 1) if rate is not None else None,
                    'below_threshold': rate is not None and rate < 75,
                })
            return Response(data)

        return Response({'error': 'student_id or class_id required.'}, status=400)


class AttendanceVsFeesView(APIView):
    """US-053: Cross-reference attendance vs fees (from Week 4 of term)."""
    permission_classes = [IsDirectorOrBursar]

    def get(self, request):
        school = request.user.school
        term = school.terms.filter(is_current=True).first()
        if not term:
            return Response({'error': 'No current term.'}, status=400)
        data, error = AttendanceService.get_attendance_vs_fees(school, term)
        if error:
            return Response({'message': error, 'data': []})
        return Response({'data': data, 'count': len(data)})


class AttendanceReminderView(APIView):
    """US-076: Manually trigger reminder to class teachers who haven't submitted."""
    permission_classes = [IsDirector]

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
