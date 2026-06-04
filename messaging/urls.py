from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    BroadcastViewSet, MessageLogListView, MessageTemplateViewSet,
    WhatsAppAnalyticsView, BroadcastDeliveryReportView,
    TemplateSubmitToMetaView, TemplateSyncStatusView,
)

router = DefaultRouter()
router.register('broadcasts', BroadcastViewSet, basename='broadcast')
router.register('templates', MessageTemplateViewSet, basename='message-template')

urlpatterns = [
    path('', include(router.urls)),
    path('logs/', MessageLogListView.as_view(), name='message-logs'),
    path('analytics/', WhatsAppAnalyticsView.as_view(), name='whatsapp-analytics'),
    path('broadcasts/<uuid:broadcast_id>/delivery-report/', BroadcastDeliveryReportView.as_view(), name='broadcast-delivery-report'),
    # US-040: Meta template submission
    path('templates/<uuid:pk>/submit-to-meta/', TemplateSubmitToMetaView.as_view(), name='template-submit-meta'),
    path('templates/<uuid:pk>/sync-status/', TemplateSyncStatusView.as_view(), name='template-sync-status'),
]
