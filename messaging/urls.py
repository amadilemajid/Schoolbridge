from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import BroadcastViewSet, MessageLogListView, MessageTemplateViewSet, WhatsAppAnalyticsView

router = DefaultRouter()
router.register('broadcasts', BroadcastViewSet, basename='broadcast')
router.register('templates', MessageTemplateViewSet, basename='message-template')

urlpatterns = [
    path('', include(router.urls)),
    path('logs/', MessageLogListView.as_view(), name='message-logs'),
    path('analytics/', WhatsAppAnalyticsView.as_view(), name='whatsapp-analytics'),
]
