"""
SchoolBridge URL Configuration — versioned API routing.
All endpoints are under /api/v1/ (US-017 versioned APIs).
"""
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path('admin/', admin.site.urls),

    # Versioned API — all client-facing endpoints
    path('api/v1/', include([
        path('auth/', include('authentication.urls')),
        path('schools/', include('schools.urls')),
        path('students/', include('students.urls')),
        path('payments/', include('payments.urls')),
        path('messaging/', include('messaging.urls')),
        path('results/', include('results.urls')),
        path('attendance/', include('attendance.urls')),
        path('notifications/', include('notifications.urls')),
        path('automation/', include('automation.urls')),
        path('audit/', include('audit.urls')),
    ])),

    # WhatsApp webhook — not versioned, Meta posts to a fixed URL
    path('webhooks/whatsapp/', include('messaging.webhook_urls')),

    # MoMo webhooks — per-provider fixed URLs
    path('webhooks/momo/mtn/', include('payments.mtn_webhook_urls')),
    path('webhooks/momo/airtel/', include('payments.airtel_webhook_urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
