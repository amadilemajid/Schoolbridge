from django.urls import path
from .metadata_views import (
    SystemMetadataView,
    StaffLookupView,
    StudentLookupView,
    GuardianLookupView,
)

urlpatterns = [
    path('', SystemMetadataView.as_view(), name='system-metadata'),
    path('lookups/staff/', StaffLookupView.as_view(), name='lookup-staff'),
    path('lookups/students/', StudentLookupView.as_view(), name='lookup-students'),
    path('lookups/guardians/', GuardianLookupView.as_view(), name='lookup-guardians'),
]
