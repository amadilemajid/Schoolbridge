from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    AttendanceRegisterView, AttendanceSummaryView, AttendanceVsFeesView,
    AttendanceReminderView, AttendanceRecordViewSet,
)

router = DefaultRouter()
router.register('records', AttendanceRecordViewSet, basename='attendance-record')

urlpatterns = [
    path('register/', AttendanceRegisterView.as_view(), name='attendance-register'),
    path('summary/', AttendanceSummaryView.as_view(), name='attendance-summary'),
    path('vs-fees/', AttendanceVsFeesView.as_view(), name='attendance-vs-fees'),
    path('remind-teachers/', AttendanceReminderView.as_view(), name='attendance-remind'),
    path('', include(router.urls)),
]
