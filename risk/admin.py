"""At-Risk Student Intelligence Engine — Admin registration."""
from django.contrib import admin
from risk.models import RiskConfiguration, StudentRiskProfile, StudentRiskSnapshot


@admin.register(RiskConfiguration)
class RiskConfigurationAdmin(admin.ModelAdmin):
    list_display = [
        'school', 'attendance_threshold', 'fee_payment_ratio_threshold',
        'outstanding_balance_threshold', 'grace_period_days',
        'enable_whatsapp_alerts', 'updated_at',
    ]
    list_filter = ['enable_whatsapp_alerts', 'enable_monday_briefing']


@admin.register(StudentRiskProfile)
class StudentRiskProfileAdmin(admin.ModelAdmin):
    list_display = [
        'student', 'school', 'risk_level', 'risk_score',
        'attendance_rate', 'fee_balance', 'alert_dispatched',
        'last_calculated_at',
    ]
    list_filter = ['risk_level', 'alert_dispatched', 'school']
    search_fields = ['student__first_name', 'student__last_name', 'student__student_id']
    readonly_fields = ['last_calculated_at']


@admin.register(StudentRiskSnapshot)
class StudentRiskSnapshotAdmin(admin.ModelAdmin):
    list_display = [
        'student', 'academic_term', 'snapshot_date',
        'risk_level', 'risk_score',
    ]
    list_filter = ['risk_level', 'snapshot_date']
    date_hierarchy = 'snapshot_date'
