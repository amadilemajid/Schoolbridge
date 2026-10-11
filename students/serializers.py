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
        from config.validators import validate_uganda_phone
        return validate_uganda_phone(value, field_name='phone')

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


class StudentLookupSerializer(serializers.ModelSerializer):
    name = serializers.CharField(source='get_full_name', read_only=True)

    class Meta:
        model = Student
        fields = ['id', 'name', 'student_id']


class StudentListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for list views."""
    admission_number = serializers.CharField(source='student_id', read_only=True)
    full_name = serializers.CharField(source='get_full_name', read_only=True)
    class_name = serializers.CharField(source='current_class.name', read_only=True)
    current_class_name = serializers.CharField(source='current_class.name', read_only=True)
    primary_guardian_phone = serializers.SerializerMethodField()
    fee_balance = serializers.SerializerMethodField()
    amount_paid = serializers.SerializerMethodField()
    fee_status = serializers.SerializerMethodField()

    class Meta:
        model = Student
        fields = [
            'id', 'student_id', 'admission_number', 'full_name', 'first_name', 'last_name',
            'gender', 'class_name', 'current_class_name', 'is_active',
            'deactivated_at', 'deactivation_reason',
            'primary_guardian_phone', 'fee_balance', 'amount_paid', 'fee_status',
        ]

    def get_primary_guardian_phone(self, obj) -> str | None:
        g = next((g for g in obj.guardians.all() if g.is_primary), None)
        return g.phone if g else None

    def _get_current_fee_record(self, obj):
        request = self.context.get('request')
        if not request or getattr(request.user, 'role', '') not in ('director', 'bursar', 'system_admin'):
            return None
        current_term = getattr(request, '_active_term', None)
        if current_term is None and hasattr(request.user, 'school') and request.user.school:
            from schools.models import AcademicTerm
            current_term = AcademicTerm.objects.filter(school=request.user.school, is_current=True).first()
            setattr(request, '_active_term', current_term)
        if current_term:
            return next((r for r in obj.fee_records.all() if r.academic_term_id == current_term.id), None)
        return None

    def get_fee_balance(self, obj) -> float | None:
        fr = self._get_current_fee_record(obj)
        return float(fr.balance) if fr else None

    def get_amount_paid(self, obj) -> float | None:
        fr = self._get_current_fee_record(obj)
        return float(fr.amount_paid) if fr else None

    def get_fee_status(self, obj) -> str | None:
        fr = self._get_current_fee_record(obj)
        if not fr:
            return None
        if fr.balance < 0:
            return 'credit'
        if fr.balance == 0:
            return 'cleared'
        if fr.amount_paid > 0:
            return 'partial'
        return 'unpaid'


class StudentDetailSerializer(serializers.ModelSerializer):
    """Full serializer for create/retrieve/update."""
    admission_number = serializers.CharField(source='student_id', read_only=True)
    guardians = GuardianSerializer(many=True, read_only=True)
    full_name = serializers.CharField(source='get_full_name', read_only=True)
    class_name = serializers.CharField(source='current_class.name', read_only=True)
    current_class_name = serializers.CharField(source='current_class.name', read_only=True)
    fee_balance = serializers.SerializerMethodField()
    total_fees = serializers.SerializerMethodField()

    class Meta:
        model = Student
        fields = [
            'id', 'student_id', 'admission_number', 'full_name', 'first_name', 'last_name',
            'other_names', 'date_of_birth', 'gender', 'current_class',
            'class_name', 'current_class_name', 'admission_date', 'academic_year_admitted',
            'is_active', 'deactivated_at', 'deactivation_reason',
            'guardians', 'fee_balance', 'total_fees',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'student_id', 'admission_number', 'deactivated_at', 'created_at', 'updated_at']

    def get_fee_balance(self, obj) -> float | None:
        request = self.context.get('request')
        if not request or getattr(request.user, 'role', '') not in ('director', 'bursar', 'system_admin'):
            return None
        term = request.user.school.terms.filter(is_current=True).first() if hasattr(request.user, 'school') and request.user.school else None
        if term:
            fr = obj.fee_records.filter(academic_term=term).first()
            if fr:
                return float(fr.balance)
        return None

    def get_total_fees(self, obj) -> float | None:
        request = self.context.get('request')
        if not request or getattr(request.user, 'role', '') not in ('director', 'bursar', 'system_admin'):
            return None
        term = request.user.school.terms.filter(is_current=True).first() if hasattr(request.user, 'school') and request.user.school else None
        if term:
            fr = obj.fee_records.filter(academic_term=term).first()
            if fr:
                return float(fr.total_amount)
        return None

    def validate_current_class(self, value):
        if value and value.school != self.context['request'].user.school:
            raise serializers.ValidationError("Class does not belong to your school.")
        return value


class StudentCreateSerializer(serializers.ModelSerializer):
    """Used for creating a student with their primary guardian in one call."""
    admission_number = serializers.CharField(required=False, allow_blank=True, default='')
    guardian_first_name = serializers.CharField(write_only=True)
    guardian_last_name = serializers.CharField(write_only=True, required=False, default='')
    guardian_relationship = serializers.CharField(write_only=True, default='Guardian')
    guardian_phone = serializers.CharField(write_only=True)

    class Meta:
        model = Student
        fields = [
            'admission_number', 'first_name', 'last_name', 'other_names', 'date_of_birth',
            'gender', 'current_class', 'admission_date',
            'guardian_first_name', 'guardian_last_name',
            'guardian_relationship', 'guardian_phone',
        ]

    def validate_admission_number(self, value):
        val = (value or '').strip()
        if not val:
            return ''
        request = self.context.get('request')
        if request and hasattr(request.user, 'school') and request.user.school:
            if Student.all_objects.filter(school=request.user.school, student_id__iexact=val).exists():
                raise serializers.ValidationError(
                    f'Student with admission number "{val}" already exists in this school.'
                )
        return val

    def validate_guardian_phone(self, value):
        from config.validators import validate_uganda_phone
        return validate_uganda_phone(value, field_name='guardian_phone')

    @transaction.atomic
    def create(self, validated_data):
        guardian_data = {
            'first_name': validated_data.pop('guardian_first_name'),
            'last_name': validated_data.pop('guardian_last_name'),
            'relationship': validated_data.pop('guardian_relationship'),
            'phone': validated_data.pop('guardian_phone'),
        }
        school = self.context['request'].user.school
        
        # Support user-supplied admission number or auto-generate
        custom_admission_no = (validated_data.pop('admission_number', '') or '').strip()
        if custom_admission_no:
            validated_data['student_id'] = custom_admission_no
        else:
            validated_data['student_id'] = Student.generate_student_id(school)

        validated_data['academic_year_admitted'] = validated_data['admission_date'].year
        validated_data['created_by'] = self.context['request'].user
        student = Student.all_objects.create(school=school, **validated_data)
        guardian_data['phone_normalised'] = Guardian._normalise_phone(guardian_data['phone'])
        Guardian.objects.create(student=student, is_primary=True, **guardian_data)
        from .services import initialize_student_enrolment
        initialize_student_enrolment(student, assigned_by=self.context['request'].user)
        return student


class BulkImportJobSerializer(serializers.ModelSerializer):
    class Meta:
        model = BulkImportJob
        fields = [
            'id', 'status', 'total_rows', 'imported_count', 'failed_count',
            'error_report', 'error_report_file', 'started_at', 'completed_at', 'created_at',
        ]
        read_only_fields = fields
