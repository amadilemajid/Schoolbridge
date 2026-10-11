from rest_framework import serializers
from onboarding.models import SchoolRegistrationRequest, SchoolProvisioningLog


class SchoolProvisioningLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = SchoolProvisioningLog
        fields = ['id', 'step_name', 'status', 'details', 'created_at']


class SchoolRegistrationRequestSerializer(serializers.ModelSerializer):
    logs = SchoolProvisioningLogSerializer(many=True, read_only=True)

    class Meta:
        model = SchoolRegistrationRequest
        fields = [
            'id', 'school_name', 'admin_email', 'admin_first_name',
            'admin_last_name', 'admin_phone', 'district', 'sub_county',
            'school_type', 'status', 'payload', 'created_at', 'updated_at', 'logs'
        ]
        read_only_fields = ['status', 'created_at', 'updated_at']


class SchoolRegistrationRequestCreateSerializer(serializers.ModelSerializer):
    admin_password = serializers.CharField(write_only=True, required=True)

    class Meta:
        model = SchoolRegistrationRequest
        fields = [
            'school_name', 'admin_email', 'admin_first_name',
            'admin_last_name', 'admin_phone', 'district', 'sub_county',
            'school_type', 'payload', 'admin_password'
        ]

    def validate_school_name(self, value):
        from schools.models import School
        if School.objects.filter(name__iexact=value).exists():
            raise serializers.ValidationError("A school with this name already exists.")
        return value

    def validate_admin_email(self, value):
        from authentication.models import User
        if User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError("A user with this email address already exists.")
        return value

    def validate_admin_password(self, value):
        from django.contrib.auth.password_validation import validate_password
        from django.core.exceptions import ValidationError as DjangoValidationError
        try:
            validate_password(value)
        except DjangoValidationError as e:
            raise serializers.ValidationError(list(e.messages))
        return value

    def validate_admin_phone(self, value):
        import re
        val = value.strip()
        # Matches Ugandan format: optional +256 or 0, followed by 7 and 8 digits
        pattern = r'^(\+?256|0)?7[0-9]{8}$'
        if not re.match(pattern, val):
            raise serializers.ValidationError("Enter a valid Ugandan phone number (e.g. +256772000000 or 0772000000).")
        if val.startswith('0'):
            val = '+256' + val[1:]
        elif val.startswith('7'):
            val = '+256' + val
        elif val.startswith('256'):
            val = '+' + val
        return val

