"""
TenantMiddleware — Row-level security enforcement.
US-001: Every request is scoped to a school.
This is the critical multi-tenant isolation layer.
"""
import threading
import logging
from django.utils.deprecation import MiddlewareMixin

logger = logging.getLogger('schoolbridge')

# Thread-local storage for the current tenant
_thread_local = threading.local()


def get_current_school():
    """Return the current request's school. Use this in all querysets."""
    return getattr(_thread_local, 'school', None)


def get_current_school_id():
    """Return the current school UUID as a string."""
    school = get_current_school()
    return str(school.id) if school else None


def set_current_school(school):
    _thread_local.school = school


def clear_current_school():
    _thread_local.school = None


class TenantMiddleware(MiddlewareMixin):
    """
    Sets the current school on every authenticated request.
    School is derived from the authenticated user's school_id.
    System admins can operate across tenants with a school header.
    """

    def process_request(self, request):
        clear_current_school()
        if not hasattr(request, 'user') or not request.user.is_authenticated:
            return None

        user = request.user

        # System admins can pass X-School-ID header to operate on a specific school
        if user.role == 'system_admin':
            school_id = request.headers.get('X-School-ID')
            if school_id:
                try:
                    from schools.models import School
                    school = School.objects.get(id=school_id, is_active=True)
                    set_current_school(school)
                    request.school = school
                    return None
                except School.DoesNotExist:
                    logger.warning(f"SysAdmin {user.id} requested non-existent school {school_id}")
            return None

        # All other roles: school is fixed to their account's school
        if hasattr(user, 'school') and user.school:
            set_current_school(user.school)
            request.school = user.school
        else:
            logger.warning(f"Authenticated user {user.id} has no school assigned")

        return None

    def process_response(self, request, response):
        clear_current_school()
        return response
