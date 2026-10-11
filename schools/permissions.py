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


class IsDirectorOnly(BasePermission):
    """Strictly for Director governance/approvals/reversals."""
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.role in ('director', 'system_admin')


class IsBursarOnly(BasePermission):
    """Strictly for Bursar operational tasks."""
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.role in ('bursar', 'system_admin')


class IsDirectorOrBursar(BasePermission):
    """Strictly for financial and fee management operations."""
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.role in ('director', 'bursar', 'system_admin')


class IsDirectorOrAdmin(BasePermission):
    """For school administration, student records, and admissions operations."""
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.role in (
            'director', 'bursar', 'school_admin', 'registrar', 'system_admin'
        )


class IsTeacher(BasePermission):
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.role in ('teacher', 'director', 'school_admin', 'system_admin')


class IsSchoolStaff(BasePermission):
    """Any authenticated staff member of the school."""
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.role in (
            'director', 'bursar', 'teacher', 'school_admin', 'registrar', 'system_admin'
        )


class IsSameSchool(BasePermission):
    """Object-level: ensure the object belongs to the request user's school."""
    def has_object_permission(self, request, view, obj):
        if request.user.role == 'system_admin':
            return True
        school = getattr(obj, 'school', None) or getattr(obj, 'school_id', None)
        return school == request.user.school or school == request.user.school_id
