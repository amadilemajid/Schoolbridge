from django.urls import path
from .webhook_views import AirtelMoMoWebhookView
urlpatterns = [path('<uuid:school_id>/', AirtelMoMoWebhookView.as_view(), name='airtel-webhook')]
