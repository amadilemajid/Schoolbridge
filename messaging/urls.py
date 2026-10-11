from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    BroadcastViewSet, MessageLogListView, MessageTemplateViewSet,
    WhatsAppAnalyticsView, BroadcastDeliveryReportView,
    TemplateSubmitToMetaView, TemplateSyncStatusView,
    VoiceBroadcastView, MessagingKpiView,
    MessageLogRetryView, MessageLogRetryAllFailedView,
)
from .simulate_views import WhatsAppSimulateView, SimulatorContactsView

router = DefaultRouter()
router.register('broadcasts', BroadcastViewSet, basename='broadcast')
router.register('templates', MessageTemplateViewSet, basename='message-template')

urlpatterns = [
    path('', include(router.urls)),
    path('logs/', MessageLogListView.as_view(), name='message-logs'),
    path('logs/<uuid:pk>/retry/', MessageLogRetryView.as_view(), name='message-log-retry'),
    path('logs/retry-all/', MessageLogRetryAllFailedView.as_view(), name='message-log-retry-all'),
    path('analytics/', WhatsAppAnalyticsView.as_view(), name='whatsapp-analytics'),
    path('kpi/', MessagingKpiView.as_view(), name='messaging-kpi'),
    path('broadcasts/<uuid:broadcast_id>/delivery-report/', BroadcastDeliveryReportView.as_view(), name='broadcast-delivery-report'),
    path('voice-broadcasts/', VoiceBroadcastView.as_view(), name='voice-broadcast'),
    # US-040: Meta template submission
    path('templates/<uuid:pk>/submit-to-meta/', TemplateSubmitToMetaView.as_view(), name='template-submit-meta'),
    path('templates/<uuid:pk>/sync-status/', TemplateSyncStatusView.as_view(), name='template-sync-status'),
    # WhatsApp Simulator
    path('simulate/', WhatsAppSimulateView.as_view(), name='whatsapp-simulate'),
    path('simulator-contacts/', SimulatorContactsView.as_view(), name='simulator-contacts'),
]
