from django.contrib import admin
from onboarding.models import SchoolRegistrationRequest, SchoolProvisioningLog


class SchoolProvisioningLogInline(admin.TabularInline):
    model = SchoolProvisioningLog
    extra = 0
    readonly_fields = ['step_name', 'status', 'details', 'created_at']
    can_delete = False


@admin.register(SchoolRegistrationRequest)
class SchoolRegistrationRequestAdmin(admin.ModelAdmin):
    list_display = ['school_name', 'admin_email', 'admin_phone', 'district', 'status', 'created_at']
    list_filter = ['status', 'school_type', 'district']
    search_fields = ['school_name', 'admin_email', 'admin_phone']
    inlines = [SchoolProvisioningLogInline]
    readonly_fields = ['created_at', 'updated_at']
