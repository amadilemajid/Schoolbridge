"""Students serializers."""
from rest_framework import serializers
from django.db import transaction
from .models import Student, Guardian, ClassGroup, ClassAssignment, BulkImportJob


class GuardianSerializer(serializers.ModelSerializer):
    class Meta:
        model = Guardian
        fields = [
            'id', 'first_name', 'last_name', 'relationship',
            'phone', 'email', 'is_primary', 'receives_sms', 'preferred_language',
        ]

    def validate_phone(self, value):
        import re
        pattern = r'^(\+256|0)(7[0-9]{8}|4[0-9]{8}|3[0-9]{8})$'
        if not re.match(pattern, value.strip()):
            raise serializers.ValidationError(
                'Enter a valid Ugandan phone number (e.g. +256701234567 or 0701234567).'
            )
        return value.strip()

    def validate(self, data):
        student = self.context.get('student')
        if student:
            existing_count = Guardian.objects.filter(student=student).count()
            if self.instance is None and existing_count >= 3:
                raise serializers.ValidationError(
                    'A student can have at most 3 guardians.'
                )
        return data


class ClassGroupSerializer(serializers.ModelSerializer):
    form_teacher_name = serializers.CharField(source='form_teacher.get_full_name', read_only=True)

    class Meta:
        model = ClassGroup
        fields = ['id', 'name', 'level', 'stream', 'form_teacher', 'form_teacher_name', 'is_active']


class StudentListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for list views."""
    full_name = serializers.CharField(source='get_full_name', read_only=True)
    class_name = serializers.CharField(source='current_class.name', read_only=True)
    primary_guardian_phone = serializers.SerializerMethodField()

    class Meta:
        model = Student
        fields = [
            'id', 'student_id', 'full_name', 'first_name', 'last_name',
            'gender', 'class_name', 'is_active', 'primary_guardian_phone',
        ]

    def get_primary_guardian_phone(self, obj):
        g = next((g for g in obj.guardians.all() if g.is_primary), None)
        return g.phone if g else None


class StudentDetailSerializer(serializers.ModelSerializer):
    """Full serializer for create/retrieve/update."""
    guardians = GuardianSerializer(many=True, read_only=True)
    full_name = serializers.CharField(source='get_full_name', read_only=True)
    class_name = serializers.CharField(source='current_class.name', read_only=True)

    class Meta:
        model = Student
        fields = [
            'id', 'student_id', 'full_name', 'first_name', 'last_name',
            'other_names', 'date_of_birth', 'gender', 'current_class',
            'class_name', 'admission_date', 'academic_year_admitted',
            'is_active', 'guardians', 'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'student_id', 'created_at', 'updated_at']

    def validate_current_class(self, value):
        if value and value.school != self.context['request'].user.school:
            raise serializers.ValidationError("Class does not belong to your school.")
        return value


class StudentCreateSerializer(serializers.ModelSerializer):
    """Used for creating a student with their primary guardian in one call."""
    guardian_first_name = serializers.CharField(write_only=True)
    guardian_last_name = serializers.CharField(write_only=True, required=False, default='')
    guardian_relationship = serializers.CharField(write_only=True, default='Guardian')
    guardian_phone = serializers.CharField(write_only=True)

    class Meta:
        model = Student
        fields = [
            'first_name', 'last_name', 'other_names', 'date_of_birth',
            'gender', 'current_class', 'admission_date',
            'guardian_first_name', 'guardian_last_name',
            'guardian_relationship', 'guardian_phone',
        ]

    def validate_guardian_phone(self, value):
        import re
        pattern = r'^(\+256|0)(7[0-9]{8}|4[0-9]{8}|3[0-9]{8})$'
        if not re.match(pattern, value.strip()):
            raise serializers.ValidationError('Enter a valid Ugandan phone number.')
        return value.strip()

    @transaction.atomic
    def create(self, validated_data):
        guardian_data = {
            'first_name': validated_data.pop('guardian_first_name'),
            'last_name': validated_data.pop('guardian_last_name'),
            'relationship': validated_data.pop('guardian_relationship'),
            'phone': validated_data.pop('guardian_phone'),
        }
        school = self.context['request'].user.school
        validated_data['student_id'] = Student.generate_student_id(school)
        validated_data['academic_year_admitted'] = validated_data['admission_date'].year
        validated_data['created_by'] = self.context['request'].user
        student = Student.all_objects.create(school=school, **validated_data)
        guardian_data['phone_normalised'] = Guardian._normalise_phone(guardian_data['phone'])
        Guardian.objects.create(student=student, is_primary=True, **guardian_data)
        return student


class BulkImportJobSerializer(serializers.ModelSerializer):
    class Meta:
        model = BulkImportJob
        fields = [
            'id', 'status', 'total_rows', 'imported_count', 'failed_count',
            'error_report', 'error_report_file', 'started_at', 'completed_at', 'created_at',
        ]
        read_only_fields = fields
