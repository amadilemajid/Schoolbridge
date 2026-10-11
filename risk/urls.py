"""At-Risk Student Intelligence Engine — URL routing."""
from django.urls import path
from risk import views

urlpatterns = [
    path('config/', views.RiskConfigurationView.as_view(), name='risk-config'),
    path('students/', views.AtRiskStudentListView.as_view(), name='at-risk-students'),
    path('recalculate/', views.TriggerRecalculationView.as_view(), name='risk-recalculate'),
    path('briefing/', views.MondayBriefingView.as_view(), name='risk-monday-briefing'),
    path('trends/<uuid:student_id>/', views.RiskTrendView.as_view(), name='risk-trends'),
]
