from django.urls import path
from .views import (
    EnrolmentReportView,
    ReconciliationReportView,
    FinancialSummaryReportView,
    AttendanceSummaryReportView,
    DefaultersCrossReferenceReportView,
    WhatsAppDeliveryReportView,
    ReportsKpiView,
    UnifiedReportGenerateView,
)

urlpatterns = [
    # Live KPI dashboard stats — powers the /reports page header cards
    path('kpi/', ReportsKpiView.as_view(), name='reports-kpi'),

    # Unified generate endpoint — POST with report_type + format + params
    path('generate/', UnifiedReportGenerateView.as_view(), name='reports-unified-generate'),

    # Individual report endpoints
    path('enrolment/', EnrolmentReportView.as_view(), name='report-enrolment'),
    path('reconciliation/', ReconciliationReportView.as_view(), name='report-reconciliation'),
    path('financial-summary/', FinancialSummaryReportView.as_view(), name='report-financial-summary'),
    path('attendance-summary/', AttendanceSummaryReportView.as_view(), name='report-attendance-summary'),
    path('defaulters/', DefaultersCrossReferenceReportView.as_view(), name='report-defaulters'),
    path('whatsapp-delivery/', WhatsAppDeliveryReportView.as_view(), name='report-whatsapp-delivery'),
]
