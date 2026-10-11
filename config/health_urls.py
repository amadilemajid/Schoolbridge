"""
SchoolBridge — Health check URL routing.
Included in config/urls.py under the root (no /api/v1/ prefix).
"""
from django.urls import path
from config.health_views import (
    LivenessView,
    ReadinessView,
    DetailHealthView,
    MetricsView,
    VersionView,
)

urlpatterns = [
    # Fast liveness — Kubernetes liveness probe, load-balancer ping
    path('',        LivenessView.as_view(),  name='health-liveness'),

    # Readiness — Kubernetes readiness probe (DB + Redis + Celery)
    path('ready/',  ReadinessView.as_view(), name='health-readiness'),

    # Deep check — all 6 services, auth-gated (X-Health-Token)
    path('detail/', DetailHealthView.as_view(), name='health-detail'),

    # Prometheus scrape endpoint, auth-gated (X-Health-Token)
    path('metrics/', MetricsView.as_view(), name='health-metrics'),

    # Build / version metadata, public
    path('version/', VersionView.as_view(), name='health-version'),
]
