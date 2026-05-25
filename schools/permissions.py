"""
Reusable permission classes used across all apps.
US-003: Role-based access control.
"""
from rest_framework.permissions import BasePermission


class IsSystemAdmin(BasePermission):
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.role == 'system_admin'


class IsDirector(BasePermission):
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.role in ('director', 'system_admin')


class IsDirectorOrBursar(BasePermission):
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.role in ('director', 'bursar', 'system_admin')


class IsTeacher(BasePermission):
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.role in ('teacher', 'director', 'system_admin')


class IsSchoolStaff(BasePermission):
    """Any authenticated staff member of the school."""
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.role in (
            'director', 'bursar', 'teacher', 'system_admin'
        )


class IsSameSchool(BasePermission):
    """Object-level: ensure the object belongs to the request user's school."""
    def has_object_permission(self, request, view, obj):
        if request.user.role == 'system_admin':
            return True
        school = getattr(obj, 'school', None) or getattr(obj, 'school_id', None)
        return school == request.user.school or school == request.user.school_id
