"""
Schools serializers — validation for all school-level data.
"""
from rest_framework import serializers
from django.utils.text import slugify
from .models import School, AcademicYear, AcademicTerm, HolidayPeriod, SchoolMoMoConfig


class SchoolSerializer(serializers.ModelSerializer):
    class Meta:
        model = School
        fields = [
            'id', 'name', 'slug', 'district', 'sub_county', 'address',
            'phone', 'email', 'whatsapp_number', 'school_type',
            'registration_number', 'logo', 'is_active', 'onboarded_at',
            'default_language', 'timezone',
        ]
        read_only_fields = ['id', 'slug', 'onboarded_at']

    def validate_name(self, value):
        slug = slugify(value)
        qs = School.objects.filter(slug=slug)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError("A school with this name already exists.")
        return value

    def create(self, validated_data):
        validated_data['slug'] = slugify(validated_data['name'])
        return super().create(validated_data)


class AcademicYearSerializer(serializers.ModelSerializer):
    class Meta:
        model = AcademicYear
        fields = ['id', 'year', 'is_current', 'created_at']
        read_only_fields = ['id', 'created_at']


class AcademicTermSerializer(serializers.ModelSerializer):
    class Meta:
        model = AcademicTerm
        fields = [
            'id', 'academic_year', 'term_number', 'name',
            'start_date', 'end_date', 'fee_deadline',
            'is_current', 'is_active', 'activated_at',
        ]
        read_only_fields = ['id', 'activated_at']

    def validate(self, data):
        start = data.get('start_date', getattr(self.instance, 'start_date', None))
        end = data.get('end_date', getattr(self.instance, 'end_date', None))
        deadline = data.get('fee_deadline', getattr(self.instance, 'fee_deadline', None))
        if start and end and start >= end:
            raise serializers.ValidationError("end_date must be after start_date.")
        if deadline and start and deadline < start:
            raise serializers.ValidationError("fee_deadline cannot be before term start_date.")
        if deadline and end and deadline > end:
            raise serializers.ValidationError("fee_deadline cannot be after term end_date.")
        return data


class HolidayPeriodSerializer(serializers.ModelSerializer):
    class Meta:
        model = HolidayPeriod
        fields = ['id', 'name', 'start_date', 'end_date', 'created_at']
        read_only_fields = ['id', 'created_at']

    def validate(self, data):
        if data.get('start_date') and data.get('end_date'):
            if data['start_date'] > data['end_date']:
                raise serializers.ValidationError("end_date must be after start_date.")
        return data


class SchoolMoMoConfigSerializer(serializers.ModelSerializer):
    """
    US-031: Credentials are NEVER returned in API responses.
    Write-only fields for all sensitive credential fields.
    """
    mtn_collection_api_user = serializers.CharField(write_only=True, required=False, allow_blank=True)
    mtn_collection_api_key = serializers.CharField(write_only=True, required=False, allow_blank=True)
    mtn_subscription_key = serializers.CharField(write_only=True, required=False, allow_blank=True)
    airtel_client_id = serializers.CharField(write_only=True, required=False, allow_blank=True)
    airtel_client_secret = serializers.CharField(write_only=True, required=False, allow_blank=True)

    class Meta:
        model = SchoolMoMoConfig
        fields = [
            'id', 'provider', 'merchant_name', 'merchant_phone',
            'mtn_environment', 'airtel_environment',
            # Write-only credential fields:
            'mtn_collection_api_user', 'mtn_collection_api_key',
            'mtn_subscription_key', 'airtel_client_id', 'airtel_client_secret',
            'is_active', 'last_tested_at',
        ]
        read_only_fields = ['id', 'last_tested_at']
