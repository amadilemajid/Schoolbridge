from django.urls import path
from .views import AttendanceRegisterView, AttendanceSummaryView, AttendanceVsFeesView, AttendanceReminderView

urlpatterns = [
    path('register/', AttendanceRegisterView.as_view(), name='attendance-register'),
    path('summary/', AttendanceSummaryView.as_view(), name='attendance-summary'),
    path('vs-fees/', AttendanceVsFeesView.as_view(), name='attendance-vs-fees'),
    path('remind-teachers/', AttendanceReminderView.as_view(), name='attendance-remind'),
]
