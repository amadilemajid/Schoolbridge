from django.urls import path
from .views import (
    MessagingPauseView, MessagingPauseEndView,
    OperationsDashboardView, AcademicDashboardView,
    FeeCollectionTrendView, TermFinancialSummaryView,
)

urlpatterns = [
    # US-064: Director messaging pause
    path('messaging-pause/', MessagingPauseView.as_view(), name='messaging-pause'),
    path('messaging-pause/<int:pause_id>/end/', MessagingPauseEndView.as_view(), name='messaging-pause-end'),

    # US-054: Combined operations dashboard
    path('dashboard/', OperationsDashboardView.as_view(), name='operations-dashboard'),

    # US-048: School-wide academic performance dashboard
    path('academic-dashboard/', AcademicDashboardView.as_view(), name='academic-dashboard'),

    # US-055: Fee collection trend chart
    path('fee-trend/', FeeCollectionTrendView.as_view(), name='fee-collection-trend'),

    # US-056: Term-end financial summary
    path('financial-summary/', TermFinancialSummaryView.as_view(), name='financial-summary'),
]
