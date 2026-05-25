from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    SchoolViewSet, AcademicYearViewSet, AcademicTermViewSet,
    HolidayPeriodViewSet, SchoolMoMoConfigViewSet,
)

router = DefaultRouter()
router.register('', SchoolViewSet, basename='school')
router.register('academic-years', AcademicYearViewSet, basename='academic-year')
router.register('terms', AcademicTermViewSet, basename='term')
router.register('holidays', HolidayPeriodViewSet, basename='holiday')
router.register('momo-config', SchoolMoMoConfigViewSet, basename='momo-config')

urlpatterns = [path('', include(router.urls))]
