from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    SchoolViewSet, AcademicYearViewSet, AcademicTermViewSet,
    HolidayPeriodViewSet, SchoolMoMoConfigViewSet, DistrictBenchmarkView, TimetableViewSet,
    SchoolSettingsView,
)
from .term_wizard_views import TermPlanningWizardView

from students.views import ClassGroupViewSet
from authentication.views import StaffViewSet

router = DefaultRouter()
router.register('academic-years', AcademicYearViewSet, basename='academic-year')
router.register('terms', AcademicTermViewSet, basename='term')
router.register('holidays', HolidayPeriodViewSet, basename='holiday')
router.register('momo-config', SchoolMoMoConfigViewSet, basename='momo-config')
router.register('timetables', TimetableViewSet, basename='timetable')
router.register('', SchoolViewSet, basename='school')

urlpatterns = [
    path('classes/', ClassGroupViewSet.as_view({'get': 'list'}), name='school-classes'),
    path('staff/invite/', StaffViewSet.as_view({'post': 'invite'}), name='school-staff-invite'),
    path('settings/', SchoolSettingsView.as_view(), name='school-settings'),
    path('district-benchmark/', DistrictBenchmarkView.as_view(), name='district-benchmark'),
    path('term-planning-wizard/', TermPlanningWizardView.as_view(), name='term-planning-wizard'),
    path('metadata/', include('schools.metadata_urls')),
    path('', include(router.urls)),
]

