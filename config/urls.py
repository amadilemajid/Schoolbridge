"""
SchoolBridge URL Configuration — versioned API routing.
All endpoints are under /api/v1/ (US-017 versioned APIs).
"""
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.http import JsonResponse
from django.views import View
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView


@method_decorator(csrf_exempt, name='dispatch')
class HealthCheckView(View):
    def get(self, request):
        checks = {}
        # Database
        try:
            from django.db import connection
            connection.ensure_connection()
            checks['db'] = 'ok'
        except Exception as e:
            checks['db'] = f'error: {str(e)}'
        # Redis
        try:
            from django.core.cache import cache
            cache.set('health_check', '1', 10)
            checks['redis'] = 'ok'
        except Exception as e:
            checks['redis'] = f'error: {str(e)}'
        # Celery
        try:
            from celery.app.control import Control
            from config.celery import app
            ctrl = Control(app)
            ping = ctrl.ping(timeout=2)
            checks['celery'] = 'ok' if ping else 'no workers'
        except Exception as e:
            checks['celery'] = f'error: {str(e)}'
        # WhatsApp
        try:
            from django.conf import settings
            checks['whatsapp_configured'] = bool(settings.WHATSAPP_ACCESS_TOKEN)
        except Exception:
            checks['whatsapp_configured'] = False

        overall = 'ok' if all(v == 'ok' for k, v in checks.items() if k != 'whatsapp_configured') else 'degraded'
        checks['status'] = overall
        checks['version'] = '1.0.0'
        return JsonResponse(checks, status=200 if overall == 'ok' else 503)

urlpatterns = [
    path('admin/', admin.site.urls),
    path('health/', HealthCheckView.as_view(), name='health-check'),
    path('api/schema/', SpectacularAPIView.as_view(), name='schema'),
    path('api/docs/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),

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
