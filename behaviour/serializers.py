"""
Behaviour serializers.
"""
from drf_spectacular.utils import extend_schema_field
from drf_spectacular.types import OpenApiTypes
from rest_framework import serializers
from .models import BehaviourIncident, BehaviourSuspension


class BehaviourIncidentSerializer(serializers.ModelSerializer):
    student_name = serializers.SerializerMethodField()
    student_id_display = serializers.SerializerMethodField()
    class_group_name = serializers.SerializerMethodField()
    reported_by_name = serializers.SerializerMethodField()
    handled_by_name = serializers.SerializerMethodField()
    incident_type_display = serializers.SerializerMethodField()
    category_display = serializers.SerializerMethodField()
    has_suspension = serializers.SerializerMethodField()

    class Meta:
        model = BehaviourIncident
        fields = [
            'id', 'academic_term', 'student', 'student_name', 'student_id_display',
            'class_group', 'class_group_name',
            'incident_type', 'incident_type_display',
            'category', 'category_display',
            'title', 'description', 'incident_date', 'action_taken',
            'reported_by', 'reported_by_name',
            'handled_by', 'handled_by_name',
            'parent_notified', 'parent_notified_at',
            'has_suspension',
            'created_at', 'updated_at',
        ]
        read_only_fields = [
            'id', 'reported_by', 'parent_notified', 'parent_notified_at',
            'created_at', 'updated_at',
        ]

    @extend_schema_field(OpenApiTypes.STR)
    def get_student_name(self, obj):
        return f"{obj.student.first_name} {obj.student.last_name}".strip()

    @extend_schema_field(OpenApiTypes.STR)
    def get_student_id_display(self, obj):
        return obj.student.student_id

    @extend_schema_field(OpenApiTypes.STR)
    def get_class_group_name(self, obj):
        return obj.class_group.name if obj.class_group else None

    @extend_schema_field(OpenApiTypes.STR)
    def get_reported_by_name(self, obj):
        return obj.reported_by.get_full_name() if obj.reported_by else None

    @extend_schema_field(OpenApiTypes.STR)
    def get_handled_by_name(self, obj):
        return obj.handled_by.get_full_name() if obj.handled_by else None

    @extend_schema_field(OpenApiTypes.STR)
    def get_incident_type_display(self, obj):
        return obj.get_incident_type_display()

    @extend_schema_field(OpenApiTypes.STR)
    def get_category_display(self, obj):
        return obj.get_category_display()

    @extend_schema_field(OpenApiTypes.BOOL)
    def get_has_suspension(self, obj):
        return hasattr(obj, 'suspension')


class BehaviourSuspensionSerializer(serializers.ModelSerializer):
    student_name = serializers.SerializerMethodField()
    approved_by_name = serializers.SerializerMethodField()
    reinstatement_confirmed_by_name = serializers.SerializerMethodField()
    duration_days = serializers.ReadOnlyField()

    class Meta:
        model = BehaviourSuspension
        fields = [
            'id', 'incident', 'student', 'student_name',
            'suspension_start', 'suspension_end', 'duration_days', 'reason',
            'director_approved', 'approved_by', 'approved_by_name', 'approved_at',
            'reinstated', 'reinstatement_date',
            'reinstatement_confirmed_by', 'reinstatement_confirmed_by_name',
            'reinstatement_notes',
            'created_at', 'updated_at',
        ]
        read_only_fields = [
            'id', 'school', 'student',
            'director_approved', 'approved_by', 'approved_at',
            'reinstated', 'reinstatement_date', 'reinstatement_confirmed_by',
            'created_at', 'updated_at',
        ]

    @extend_schema_field(OpenApiTypes.STR)
    def get_student_name(self, obj):
        return f"{obj.student.first_name} {obj.student.last_name}".strip()

    @extend_schema_field(OpenApiTypes.STR)
    def get_approved_by_name(self, obj):
        return obj.approved_by.get_full_name() if obj.approved_by else None

    @extend_schema_field(OpenApiTypes.STR)
    def get_reinstatement_confirmed_by_name(self, obj):
        return obj.reinstatement_confirmed_by.get_full_name() if obj.reinstatement_confirmed_by else None

    def validate(self, data):
        if 'suspension_end' in data and 'suspension_start' in data:
            if data['suspension_end'] < data['suspension_start']:
                raise serializers.ValidationError(
                    {'suspension_end': 'End date cannot be before start date.'}
                )
        return data

    def create(self, validated_data):
        incident = validated_data['incident']
        validated_data['school'] = incident.school
        validated_data['student'] = incident.student
        return super().create(validated_data)


class BehaviourDashboardSerializer(serializers.Serializer):
    total_incidents = serializers.IntegerField()
    positive = serializers.IntegerField()
    warnings = serializers.IntegerField()
    suspensions = serializers.IntegerField()
    expulsions = serializers.IntegerField()
    by_category = serializers.ListField()
    top_students = serializers.ListField()
    recent_incidents = BehaviourIncidentSerializer(many=True)


class StudentBehaviourSummarySerializer(serializers.Serializer):
    student_id = serializers.UUIDField()
    student_name = serializers.CharField()
    total_incidents = serializers.IntegerField()
    positive = serializers.IntegerField()
    warnings = serializers.IntegerField()
    suspensions = serializers.IntegerField()
    total_suspension_days = serializers.IntegerField()
    incidents = BehaviourIncidentSerializer(many=True)
