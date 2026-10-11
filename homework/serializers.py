"""
Homework serializers.
"""
import uuid
from drf_spectacular.utils import extend_schema_field
from drf_spectacular.types import OpenApiTypes
from rest_framework import serializers
from .models import HomeworkAssignment, HomeworkSubmission


class HomeworkSubmissionSerializer(serializers.ModelSerializer):
    student_name = serializers.SerializerMethodField()
    student_id = serializers.SerializerMethodField()

    class Meta:
        model = HomeworkSubmission
        fields = [
            'id', 'student', 'student_name', 'student_id',
            'submitted_at', 'is_late',
            'marks_awarded', 'feedback', 'graded_by', 'graded_at',
        ]
        read_only_fields = ['id', 'submitted_at', 'school']

    @extend_schema_field(OpenApiTypes.STR)
    def get_student_name(self, obj):
        return obj.student.get_full_name() if hasattr(obj.student, 'get_full_name') else str(obj.student)

    @extend_schema_field(OpenApiTypes.STR)
    def get_student_id(self, obj):
        return obj.student.student_id


class HomeworkSubmissionCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = HomeworkSubmission
        fields = ['student', 'marks_awarded', 'feedback']

    def validate_student(self, student):
        request = self.context['request']
        assignment = self.context['assignment']
        if student.school != request.user.school:
            raise serializers.ValidationError('Student does not belong to this school.')
        if HomeworkSubmission.objects.filter(assignment=assignment, student=student).exists():
            raise serializers.ValidationError('Submission already recorded for this student.')
        return student

    def create(self, validated_data):
        from django.utils import timezone
        assignment = self.context['assignment']
        is_late = timezone.localdate() > assignment.due_date
        return HomeworkSubmission.objects.create(
            **validated_data,
            assignment=assignment,
            school=assignment.school,
            is_late=is_late,
        )


class HomeworkAssignmentSerializer(serializers.ModelSerializer):
    class_group_name = serializers.SerializerMethodField()
    subject_name = serializers.SerializerMethodField()
    assigned_by_name = serializers.SerializerMethodField()
    submission_count = serializers.ReadOnlyField()
    completion_rate = serializers.ReadOnlyField()
    is_overdue = serializers.ReadOnlyField()

    class Meta:
        model = HomeworkAssignment
        fields = [
            'id', 'academic_term', 'class_group', 'class_group_name',
            'subject', 'subject_name', 'title', 'description',
            'assigned_date', 'due_date', 'status', 'is_graded', 'max_marks',
            'assigned_by', 'assigned_by_name',
            'guardian_notified', 'guardian_notified_at',
            'submission_count', 'completion_rate', 'is_overdue',
            'created_at', 'updated_at',
        ]
        read_only_fields = [
            'id', 'assigned_by', 'guardian_notified', 'guardian_notified_at',
            'created_at', 'updated_at',
        ]

    @extend_schema_field(OpenApiTypes.STR)
    def get_class_group_name(self, obj):
        return obj.class_group.name

    @extend_schema_field(OpenApiTypes.STR)
    def get_subject_name(self, obj):
        return obj.subject.name if obj.subject else None

    @extend_schema_field(OpenApiTypes.STR)
    def get_assigned_by_name(self, obj):
        return obj.assigned_by.get_full_name() if obj.assigned_by else None

    def validate(self, data):
        if 'due_date' in data and 'assigned_date' in data:
            if data['due_date'] < data['assigned_date']:
                raise serializers.ValidationError({'due_date': 'Due date cannot be before assigned date.'})
        if data.get('is_graded') and not data.get('max_marks'):
            raise serializers.ValidationError({'max_marks': 'max_marks is required for graded assignments.'})
        return data


class HomeworkReportSerializer(serializers.Serializer):
    assignment_id = serializers.UUIDField()
    title = serializers.CharField()
    class_group = serializers.CharField()
    due_date = serializers.DateField()
    total_students = serializers.IntegerField()
    submitted = serializers.IntegerField()
    not_submitted = serializers.IntegerField()
    completion_rate = serializers.FloatField()
    average_marks = serializers.FloatField(allow_null=True)
