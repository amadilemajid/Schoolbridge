from django.contrib import admin
from .models import BehaviourIncident, BehaviourSuspension


@admin.register(BehaviourIncident)
class BehaviourIncidentAdmin(admin.ModelAdmin):
    list_display = ['title', 'student', 'incident_type', 'category', 'incident_date', 'parent_notified']
    list_filter = ['incident_type', 'category', 'parent_notified', 'academic_term']
    search_fields = ['title', 'student__first_name', 'student__last_name']
    date_hierarchy = 'incident_date'


@admin.register(BehaviourSuspension)
class BehaviourSuspensionAdmin(admin.ModelAdmin):
    list_display = ['student', 'suspension_start', 'suspension_end', 'director_approved', 'reinstated']
    list_filter = ['director_approved', 'reinstated']
    search_fields = ['student__first_name', 'student__last_name']
