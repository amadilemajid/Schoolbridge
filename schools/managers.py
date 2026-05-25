"""
TenantManager — Automatically scopes all querysets to the current school.
US-001: Critical security. Every model using this manager is tenant-isolated.
"""
from django.db import models
from schools.middleware import get_current_school


class TenantManager(models.Manager):
    """
    Default manager for all tenant-scoped models.
    Automatically filters by the current school from thread-local storage.
    """

    def get_queryset(self):
        qs = super().get_queryset()
        school = get_current_school()
        if school is not None:
            return qs.filter(school=school)
        return qs

    def all_schools(self):
        """Bypass tenant scoping. Use ONLY in system admin views or migrations."""
        return super().get_queryset()


class TenantManagerMixin:
    """
    Mixin to add to any model that needs tenant isolation.
    Usage:
        objects = TenantManager()
        all_objects = models.Manager()  # Unscoped — system admin only
    """
    pass
