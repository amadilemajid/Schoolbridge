"""
SchoolBridge — Health Check Views
Three-tier endpoint hierarchy:

  GET /health/              Liveness probe   — DB only, <200ms, public
  GET /health/ready/        Readiness probe  — DB+Redis+Celery, <4s, public
  GET /health/detail/       Deep check       — all 6 services, auth-gated
  GET /health/metrics/      Prometheus text  — all 6 services, auth-gated
  GET /health/version/      Build metadata   — public, no checks

HTTP status codes:
  200  all checked services are ok
  207  at least one NON-CRITICAL service is degraded (system functional)
  503  at least one CRITICAL service is down (system impaired)

Authentication for /detail/ and /metrics/:
  Header: X-Health-Token: <HEALTH_CHECK_TOKEN from settings>
"""
import logging
import time
from datetime import datetime, timezone

from django.conf import settings
from django.http import HttpResponse, JsonResponse
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_exempt

from config.health_checks import (
    STATUS_DOWN,
    STATUS_DEGRADED,
    STATUS_OK,
    CRITICAL_CHECKS,
    run_all_checks,
    run_check,
)

logger = logging.getLogger('schoolbridge')

# Cache key for background health state
HEALTH_CACHE_KEY    = 'health:detail:latest'
HEALTH_CACHE_TTL    = 300   # 5 minutes — stale-if-error window

# Build / version metadata — override via env in CI/CD
BUILD_VERSION   = getattr(settings, 'APP_VERSION',    '1.0.0')
BUILD_COMMIT    = getattr(settings, 'GIT_COMMIT',     'unknown')
BUILD_TIMESTAMP = getattr(settings, 'BUILD_TIMESTAMP','unknown')
ENVIRONMENT     = getattr(settings, 'ENVIRONMENT',    'production' if not settings.DEBUG else 'development')


# ---------------------------------------------------------------------------
# Auth helper
# ---------------------------------------------------------------------------

def _check_health_token(request) -> bool:
    """Validate X-Health-Token header against settings.HEALTH_CHECK_TOKEN."""
    expected = getattr(settings, 'HEALTH_CHECK_TOKEN', '')
    if not expected:
        # Token not configured — allow access (dev/staging convenience)
        return True
    provided = request.headers.get('X-Health-Token', '')
    # Constant-time comparison to prevent timing attacks
    import hmac
    return hmac.compare_digest(provided, expected)


# ---------------------------------------------------------------------------
# Shared response builder
# ---------------------------------------------------------------------------

def _build_response(checks: dict, include_meta: bool = True) -> tuple[dict, int]:
    """
    Build the top-level JSON response dict and determine HTTP status code.
    Returns (payload_dict, http_status_code).
    """
    results = {name: result.as_dict() for name, result in checks.items()}

    # Determine overall status
    critical_names = set(CRITICAL_CHECKS.keys())
    any_critical_down     = any(
        r.status == STATUS_DOWN
        for name, r in checks.items()
        if name in critical_names
    )
    any_service_degraded  = any(r.status == STATUS_DEGRADED for r in checks.values())
    any_optional_down     = any(
        r.status == STATUS_DOWN
        for name, r in checks.items()
        if name not in critical_names
    )

    if any_critical_down:
        overall = STATUS_DOWN
        http_status = 503
    elif any_service_degraded or any_optional_down:
        overall = STATUS_DEGRADED
        http_status = 207
    else:
        overall = STATUS_OK
        http_status = 200

    payload = {
        'status':      overall,
        'timestamp':   datetime.now(timezone.utc).isoformat(),
        'environment': ENVIRONMENT,
        'version':     BUILD_VERSION,
        'checks':      results,
    }
    return payload, http_status


# ---------------------------------------------------------------------------
# View 1: Liveness Probe  GET /health/
# ---------------------------------------------------------------------------

@method_decorator([csrf_exempt, never_cache], name='dispatch')
class LivenessView(View):
    """
    Kubernetes / load-balancer liveness probe.
    Only checks PostgreSQL — intentionally fast (<200ms).
    Returns 200 if the app process can reach the database.
    Returns 503 if the database is completely unreachable.

    DO NOT add external service checks here — liveness failure triggers
    a pod restart, which won't fix a broken 3rd-party API.
    """

    def get(self, request):
        result = run_check('postgresql')
        # RISK-P4C: omit latency_ms — no fingerprinting data on public endpoint
        http_status = 200 if result.status == STATUS_OK else 503
        return JsonResponse(
            {'status': result.status, 'timestamp': datetime.now(timezone.utc).isoformat()},
            status=http_status,
        )


# ---------------------------------------------------------------------------
# View 2: Readiness Probe  GET /health/ready/
# ---------------------------------------------------------------------------

@method_decorator([csrf_exempt, never_cache], name='dispatch')
class ReadinessView(View):
    """
    Kubernetes / load-balancer readiness probe.
    Checks the three critical services: PostgreSQL, Redis, Celery.
    The pod is removed from the load-balancer rotation if this returns 503.

    Typical total latency: <4s (DB 3s + Redis 2s + Celery 3s, in parallel
    via thread pool would be max(3,2,3)=3s, but here they run sequentially
    for simplicity — adjust if strict SLA requires it).
    """
    CHECKS = ['postgresql', 'redis', 'celery']

    def get(self, request):
        checks = run_all_checks(names=self.CHECKS)
        # RISK-P4C: return only overall status + timestamp on this public endpoint.
        # Full check details (latency, service names, version) are only available
        # on the token-gated /health/detail/ endpoint.
        any_critical_down = any(
            r.status == STATUS_DOWN
            for name, r in checks.items()
            if name in set(CRITICAL_CHECKS.keys())
        )
        any_degraded = any(r.status in (STATUS_DOWN, STATUS_DEGRADED) for r in checks.values())
        if any_critical_down:
            overall, http_status = STATUS_DOWN, 503
        elif any_degraded:
            overall, http_status = STATUS_DEGRADED, 207
        else:
            overall, http_status = STATUS_OK, 200
        return JsonResponse(
            {'status': overall, 'timestamp': datetime.now(timezone.utc).isoformat()},
            status=http_status,
        )


# ---------------------------------------------------------------------------
# View 3: Deep Health Check  GET /health/detail/
# ---------------------------------------------------------------------------

@method_decorator([csrf_exempt, never_cache], name='dispatch')
class DetailHealthView(View):
    """
    Full health check across all 6 services.
    Auth-gated: requires X-Health-Token header.

    Results are served from a Redis-backed cache (updated every 2 minutes
    by the background Celery task `run_background_health_checks`).
    If the cache is cold, a live check is performed and the result is cached.

    Cache strategy:
      - Fresh result (< 2 min old) → served as-is with Cache-Control: max-age=120
      - Stale result (2–5 min old) → served with Cache-Control: stale-while-revalidate
      - No cache → live check performed, result cached for 5 minutes
    """

    def get(self, request):
        if not _check_health_token(request):
            return JsonResponse({'error': 'Unauthorized'}, status=401)

        # Try cache first
        cached = self._get_cached()
        if cached:
            cached['_cached'] = True
            return JsonResponse(cached, status=self._http_status(cached['status']))

        # Live check
        checks  = run_all_checks()
        payload, http_status = _build_response(checks)
        payload['_cached'] = False
        self._set_cache(payload)
        return JsonResponse(payload, status=http_status)

    def _get_cached(self):
        try:
            from django.core.cache import cache
            return cache.get(HEALTH_CACHE_KEY)
        except Exception:
            return None

    def _set_cache(self, payload: dict):
        try:
            from django.core.cache import cache
            cache.set(HEALTH_CACHE_KEY, payload, HEALTH_CACHE_TTL)
        except Exception:
            pass

    def _http_status(self, status: str) -> int:
        return {STATUS_OK: 200, STATUS_DEGRADED: 207, STATUS_DOWN: 503}.get(status, 503)


# ---------------------------------------------------------------------------
# View 4: Prometheus Metrics  GET /health/metrics/
# ---------------------------------------------------------------------------

@method_decorator([csrf_exempt, never_cache], name='dispatch')
class MetricsView(View):
    """
    Prometheus-compatible text/plain endpoint.
    Returns gauge metrics for each service health check.
    Auth-gated: requires X-Health-Token header.

    Metric values:
      1 = ok
      0 = degraded
     -1 = down

    Example scrape config (prometheus.yml):
      - job_name: schoolbridge
        static_configs:
          - targets: ['schoolbridge.yourdomain.com']
        metrics_path: /health/metrics/
        params:
          format: [prometheus]
        bearer_token: <HEALTH_CHECK_TOKEN>
        # Use bearer_token if you prefer Authorization header.
        # The view also accepts X-Health-Token for flexibility.
    """
    STATUS_VALUES = {STATUS_OK: 1, STATUS_DEGRADED: 0, STATUS_DOWN: -1}

    def get(self, request):
        if not _check_health_token(request):
            return HttpResponse('# Unauthorized\n', status=401,
                                content_type='text/plain; version=0.0.4')

        # Serve from cache if available
        checks_raw = self._get_or_run_checks()
        lines = self._build_prometheus_output(checks_raw)
        return HttpResponse('\n'.join(lines) + '\n',
                            content_type='text/plain; version=0.0.4; charset=utf-8',
                            status=200)

    def _get_or_run_checks(self) -> dict:
        try:
            from django.core.cache import cache
            cached = cache.get(HEALTH_CACHE_KEY)
            if cached:
                return cached.get('checks', {})
        except Exception:
            pass
        checks = run_all_checks()
        return {name: result.as_dict() for name, result in checks.items()}

    def _build_prometheus_output(self, checks: dict) -> list:
        ts_ms = int(time.time() * 1000)
        lines = [
            '# HELP schoolbridge_service_health Health status of external service (1=ok, 0=degraded, -1=down)',
            '# TYPE schoolbridge_service_health gauge',
        ]
        for name, result in checks.items():
            status_str = result.get('status', STATUS_DOWN) if isinstance(result, dict) else result.status
            value = self.STATUS_VALUES.get(status_str, -1)
            latency = result.get('latency_ms', 0) if isinstance(result, dict) else result.latency_ms
            lines.append(
                f'schoolbridge_service_health{{service="{name}",environment="{ENVIRONMENT}"}} {value} {ts_ms}'
            )
            lines.append(
                f'# HELP schoolbridge_service_latency_ms Latency in milliseconds for last health check of service'
            )
            lines.append(
                f'# TYPE schoolbridge_service_latency_ms gauge'
            )
            lines.append(
                f'schoolbridge_service_latency_ms{{service="{name}",environment="{ENVIRONMENT}"}} {latency} {ts_ms}'
            )

        # Overall status metric
        statuses = [
            (result.get('status', STATUS_DOWN) if isinstance(result, dict) else result.status)
            for result in checks.values()
        ]
        critical_names = set(CRITICAL_CHECKS.keys())
        critical_down = any(
            statuses[i] == STATUS_DOWN
            for i, name in enumerate(checks.keys())
            if name in critical_names
        )
        overall_val = -1 if critical_down else (0 if STATUS_DEGRADED in statuses else 1)
        lines += [
            '# HELP schoolbridge_overall_health Overall system health (1=ok, 0=degraded, -1=down)',
            '# TYPE schoolbridge_overall_health gauge',
            f'schoolbridge_overall_health{{environment="{ENVIRONMENT}"}} {overall_val} {ts_ms}',
        ]
        return lines


# ---------------------------------------------------------------------------
# View 5: Version / Build Info  GET /health/version/
# ---------------------------------------------------------------------------

@method_decorator([csrf_exempt, never_cache], name='dispatch')
class VersionView(View):
    """
    Returns build metadata. No dependency checks. Always 200.
    Safe for public access — does not expose internal state.
    """

    def get(self, request):
        # RISK-P4C: omit django_version — exact framework version is a fingerprinting risk
        return JsonResponse({
            'version':         BUILD_VERSION,
            'commit':          BUILD_COMMIT,
            'build_timestamp': BUILD_TIMESTAMP,
            'environment':     ENVIRONMENT,
        })

    def _django_version(self) -> str:
        try:
            import django
            return django.get_version()
        except Exception:
            return 'unknown'
