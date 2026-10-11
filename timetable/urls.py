"""Structured Timetable Backend — URL routing."""
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from timetable import views

router = DefaultRouter()
router.register('versions', views.TimetableVersionViewSet, basename='timetable-version')
router.register('slots', views.TimetableSlotViewSet, basename='timetable-slot')
router.register('substitutions', views.SubstitutionRecordViewSet, basename='timetable-substitution')

urlpatterns = [
    path('', include(router.urls)),
]
