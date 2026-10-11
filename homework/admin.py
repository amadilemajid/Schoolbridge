from django.contrib import admin
from .models import HomeworkAssignment, HomeworkSubmission


@admin.register(HomeworkAssignment)
class HomeworkAssignmentAdmin(admin.ModelAdmin):
    list_display = ['title', 'class_group', 'subject', 'due_date', 'status', 'assigned_by']
    list_filter = ['status', 'is_graded', 'academic_term']
    search_fields = ['title', 'class_group__name']
    date_hierarchy = 'due_date'


@admin.register(HomeworkSubmission)
class HomeworkSubmissionAdmin(admin.ModelAdmin):
    list_display = ['assignment', 'student', 'submitted_at', 'is_late', 'marks_awarded']
    list_filter = ['is_late', 'assignment__class_group']
    search_fields = ['student__first_name', 'student__last_name']
