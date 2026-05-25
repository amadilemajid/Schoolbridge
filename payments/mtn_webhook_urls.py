from django.urls import path
from .webhook_views import MTNMoMoWebhookView
urlpatterns = [path('<uuid:school_id>/', MTNMoMoWebhookView.as_view(), name='mtn-webhook')]
