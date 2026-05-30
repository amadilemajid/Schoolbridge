from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    SchoolViewSet, AcademicYearViewSet, AcademicTermViewSet,
    HolidayPeriodViewSet, SchoolMoMoConfigViewSet, DistrictBenchmarkView,
)

router = DefaultRouter()
router.register('academic-years', AcademicYearViewSet, basename='academic-year')
router.register('terms', AcademicTermViewSet, basename='term')
router.register('holidays', HolidayPeriodViewSet, basename='holiday')
router.register('momo-config', SchoolMoMoConfigViewSet, basename='momo-config')
router.register('', SchoolViewSet, basename='school')

urlpatterns = [
    path('district-benchmark/', DistrictBenchmarkView.as_view(), name='district-benchmark'),
    path('', include(router.urls)),
]
