"""Structured Timetable Backend — Admin registration."""
from django.contrib import admin
from timetable.models import TimetableVersion, TimetableSlot, SubstitutionRecord


@admin.register(TimetableVersion)
class TimetableVersionAdmin(admin.ModelAdmin):
    list_display = ['school', 'class_group', 'academic_term', 'version_number', 'is_active', 'effective_from']
    list_filter = ['school', 'is_active', 'academic_term']
    search_fields = ['class_group__name', 'notes']


@admin.register(TimetableSlot)
class TimetableSlotAdmin(admin.ModelAdmin):
    list_display = ['school', 'timetable_version', 'day_of_week', 'period_number', 'start_time', 'end_time', 'subject', 'teacher', 'slot_type']
    list_filter = ['school', 'day_of_week', 'slot_type']
    search_fields = ['subject_name', 'room', 'teacher__first_name', 'teacher__last_name']


@admin.register(SubstitutionRecord)
class SubstitutionRecordAdmin(admin.ModelAdmin):
    list_display = ['school', 'timetable_slot', 'date', 'original_teacher', 'substitute_teacher', 'reason']
    list_filter = ['school', 'date']
    search_fields = ['reason', 'original_teacher__first_name', 'substitute_teacher__first_name']
