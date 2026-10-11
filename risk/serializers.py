"""
At-Risk Student Intelligence Engine — Serializers.
"""
from rest_framework import serializers
from risk.models import RiskConfiguration, StudentRiskProfile, StudentRiskSnapshot


class RiskConfigurationSerializer(serializers.ModelSerializer):
    class Meta:
        model = RiskConfiguration
        fields = [
            'attendance_threshold',
            'fee_payment_ratio_threshold',
            'outstanding_balance_threshold',
            'grace_period_days',
            'enable_whatsapp_alerts',
            'enable_monday_briefing',
            'updated_at',
        ]
        read_only_fields = ['updated_at']


class StudentRiskProfileSerializer(serializers.ModelSerializer):
    student_name = serializers.CharField(
        source='student.get_full_name', read_only=True
    )
    student_id_code = serializers.CharField(
        source='student.student_id', read_only=True
    )
    class_name = serializers.SerializerMethodField()

    class Meta:
        model = StudentRiskProfile
        fields = [
            'id',
            'student_id_code',
            'student_name',
            'class_name',
            'attendance_rate',
            'total_days_recorded',
            'days_absent',
            'fee_payment_ratio',
            'fee_balance',
            'risk_score',
            'risk_level',
            'flagged_factors',
            'last_calculated_at',
        ]

    def get_class_name(self, obj) -> str:
        if obj.student.current_class:
            return obj.student.current_class.name
        return 'N/A'


class StudentRiskSnapshotSerializer(serializers.ModelSerializer):
    class Meta:
        model = StudentRiskSnapshot
        fields = [
            'snapshot_date',
            'attendance_rate',
            'fee_payment_ratio',
            'risk_score',
            'risk_level',
            'flagged_factors',
        ]
