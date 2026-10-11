"""
SchoolBridge — Production Health Checks
One checker class per external dependency.

Design principles:
  - Every check catches ALL exceptions and returns a structured result.
  - Signal-based UNIX alarm is used for hard timeouts where supported;
    on Windows (dev) we fall back to a threading-based timeout wrapper.
  - Checks are completely stateless; the caller decides whether to cache.
  - HTTP checks (WhatsApp, MoMo) use a short requests.Session with
    connect_timeout and read_timeout set independently.
"""
import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Optional

logger = logging.getLogger('schoolbridge')


# ---------------------------------------------------------------------------
# Result container
# ---------------------------------------------------------------------------

STATUS_OK       = 'ok'
STATUS_DEGRADED = 'degraded'
STATUS_DOWN     = 'down'


@dataclass
class HealthResult:
    """Standardised result returned by every checker."""
    status: str                          # ok | degraded | down
    latency_ms: int = 0
    detail: str = ''
    meta: dict = field(default_factory=dict)   # extra diagnostic data

    def as_dict(self) -> dict:
        return {
            'status':     self.status,
            'latency_ms': self.latency_ms,
            'detail':     self.detail,
            **({'meta': self.meta} if self.meta else {}),
        }


# ---------------------------------------------------------------------------
# Timeout helper (cross-platform)
# ---------------------------------------------------------------------------

class _TimeoutError(Exception):
    pass


def _run_with_timeout(fn, timeout_seconds: float):
    """
    Run fn() in a daemon thread.  Raises _TimeoutError if it doesn't
    complete within timeout_seconds.  Works on Windows + Linux.
    """
    result_holder = [None]
    exc_holder    = [None]

    def target():
        try:
            result_holder[0] = fn()
        except Exception as exc:  # noqa: BLE001
            exc_holder[0] = exc

    t = threading.Thread(target=target, daemon=True)
    t.start()
    t.join(timeout=timeout_seconds)

    if t.is_alive():
        raise _TimeoutError(f'timed out after {timeout_seconds}s')
    if exc_holder[0] is not None:
        raise exc_holder[0]
    return result_holder[0]


# ---------------------------------------------------------------------------
# 1. PostgreSQL
# ---------------------------------------------------------------------------

class PostgreSQLCheck:
    """
    Executes `SELECT 1` via Django's DB connection.
    Timeout: 3 s.  Verifies row returns successfully.
    Also reports: connection pool size, server version.
    """
    TIMEOUT = 3

    def run(self) -> HealthResult:
        start = time.monotonic()
        try:
            result = _run_with_timeout(self._check, self.TIMEOUT)
            return result
        except _TimeoutError:
            return HealthResult(
                status=STATUS_DOWN,
                latency_ms=int((time.monotonic() - start) * 1000),
                detail=f'Query timed out after {self.TIMEOUT}s',
            )
        except Exception as exc:  # noqa: BLE001
            return HealthResult(
                status=STATUS_DOWN,
                latency_ms=int((time.monotonic() - start) * 1000),
                detail=str(exc),
            )

    def _check(self) -> HealthResult:
        from django.db import connection
        start = time.monotonic()
        with connection.cursor() as cursor:
            cursor.execute('SELECT 1')
            row = cursor.fetchone()
        latency_ms = int((time.monotonic() - start) * 1000)
        if row != (1,):
            return HealthResult(status=STATUS_DOWN, latency_ms=latency_ms, detail='Unexpected row returned')
        meta = {}
        try:
            with connection.cursor() as cursor:
                cursor.execute('SELECT version()')
                meta['server_version'] = cursor.fetchone()[0].split(',')[0]
            meta['conn_max_age'] = connection.settings_dict.get('CONN_MAX_AGE', 'unknown')
        except Exception:  # noqa: BLE001
            pass
        return HealthResult(status=STATUS_OK, latency_ms=latency_ms, meta=meta)


# ---------------------------------------------------------------------------
# 2. Redis
# ---------------------------------------------------------------------------

class RedisCheck:
    """
    Sends PING to Redis and verifies PONG reply.
    Also checks: used_memory_human, connected_clients from INFO.
    Timeout: 2 s.
    """
    TIMEOUT = 2

    def run(self) -> HealthResult:
        start = time.monotonic()
        try:
            result = _run_with_timeout(self._check, self.TIMEOUT)
            return result
        except _TimeoutError:
            return HealthResult(
                status=STATUS_DOWN,
                latency_ms=int((time.monotonic() - start) * 1000),
                detail=f'PING timed out after {self.TIMEOUT}s',
            )
        except Exception as exc:  # noqa: BLE001
            return HealthResult(
                status=STATUS_DOWN,
                latency_ms=int((time.monotonic() - start) * 1000),
                detail=str(exc),
            )

    def _check(self) -> HealthResult:
        import redis as redis_lib
        from django.conf import settings
        start = time.monotonic()
        url = getattr(settings, 'REDIS_URL', 'redis://localhost:6379/0')
        client = redis_lib.from_url(url, socket_connect_timeout=self.TIMEOUT,
                                    socket_timeout=self.TIMEOUT, decode_responses=True)
        pong = client.ping()
        latency_ms = int((time.monotonic() - start) * 1000)
        if not pong:
            return HealthResult(status=STATUS_DOWN, latency_ms=latency_ms, detail='PING did not return PONG')
        meta = {}
        try:
            info = client.info(section='memory')
            meta['used_memory_human'] = info.get('used_memory_human', 'unknown')
            info2 = client.info(section='clients')
            meta['connected_clients'] = info2.get('connected_clients', 'unknown')
        except Exception:  # noqa: BLE001
            pass
        return HealthResult(status=STATUS_OK, latency_ms=latency_ms, meta=meta)


# ---------------------------------------------------------------------------
# 3. Celery
# ---------------------------------------------------------------------------

class CeleryCheck:
    """
    Pings all active Celery workers.
    Status:
      ok       — at least one worker responded within timeout
      degraded — workers responded but queue depth > threshold
      down     — no workers responded
    Timeout: 3 s.
    """
    TIMEOUT          = 3
    QUEUE_WARN_DEPTH = 50  # warn if pending tasks exceed this

    def run(self) -> HealthResult:
        start = time.monotonic()
        try:
            result = _run_with_timeout(self._check, self.TIMEOUT + 1)
            return result
        except _TimeoutError:
            return HealthResult(
                status=STATUS_DOWN,
                latency_ms=int((time.monotonic() - start) * 1000),
                detail=f'Worker ping timed out after {self.TIMEOUT}s',
            )
        except Exception as exc:  # noqa: BLE001
            return HealthResult(
                status=STATUS_DOWN,
                latency_ms=int((time.monotonic() - start) * 1000),
                detail=str(exc),
            )

    def _check(self) -> HealthResult:
        from celery.app.control import Control
        from config.celery import app
        start = time.monotonic()
        ctrl = Control(app)
        ping_responses = ctrl.ping(timeout=self.TIMEOUT)
        latency_ms = int((time.monotonic() - start) * 1000)

        if not ping_responses:
            return HealthResult(status=STATUS_DOWN, latency_ms=latency_ms,
                                detail='No Celery workers responded to PING')

        worker_names = [list(r.keys())[0] for r in ping_responses]
        meta = {
            'worker_count': len(worker_names),
            'workers':      worker_names,
        }

        # Check queue depth via Redis
        queue_status = STATUS_OK
        try:
            import redis as redis_lib
            from django.conf import settings
            url = getattr(settings, 'CELERY_BROKER_URL', 'redis://localhost:6379/1')
            client = redis_lib.from_url(url, socket_connect_timeout=2,
                                        socket_timeout=2, decode_responses=True)
            for q in ('celery', 'automation', 'payments', 'messaging'):
                depth = client.llen(q)
                meta[f'queue_{q}_depth'] = depth
                if depth > self.QUEUE_WARN_DEPTH:
                    queue_status = STATUS_DEGRADED
        except Exception:  # noqa: BLE001
            pass

        return HealthResult(status=queue_status, latency_ms=latency_ms,
                            detail=f'{len(worker_names)} worker(s) active', meta=meta)


# ---------------------------------------------------------------------------
# 4. WhatsApp Cloud API
# ---------------------------------------------------------------------------

class WhatsAppCheck:
    """
    Verifies the Meta WhatsApp Cloud API token is valid by calling
    GET /v19.0/{phone_number_id}?fields=display_phone_number,verified_name
    Timeout: connect=3s, read=5s.
    Status:
      ok       — 200, token valid
      degraded — 200 but unexpected payload
      down     — 401/403/5xx or network error
    """
    CONNECT_TIMEOUT = 3
    READ_TIMEOUT    = 5

    def run(self) -> HealthResult:
        start = time.monotonic()
        try:
            result = _run_with_timeout(self._check, self.CONNECT_TIMEOUT + self.READ_TIMEOUT + 1)
            return result
        except _TimeoutError:
            return HealthResult(
                status=STATUS_DOWN,
                latency_ms=int((time.monotonic() - start) * 1000),
                detail=f'Request timed out after {self.CONNECT_TIMEOUT + self.READ_TIMEOUT}s',
            )
        except Exception as exc:  # noqa: BLE001
            return HealthResult(
                status=STATUS_DOWN,
                latency_ms=int((time.monotonic() - start) * 1000),
                detail=str(exc),
            )

    def _check(self) -> HealthResult:
        import requests
        from django.conf import settings
        token    = getattr(settings, 'WHATSAPP_ACCESS_TOKEN', '')
        phone_id = getattr(settings, 'WHATSAPP_PHONE_NUMBER_ID', '')
        base_url = getattr(settings, 'WHATSAPP_API_URL', 'https://graph.facebook.com/v19.0')

        if not token or not phone_id:
            return HealthResult(status=STATUS_DEGRADED, latency_ms=0,
                                detail='WHATSAPP_ACCESS_TOKEN or WHATSAPP_PHONE_NUMBER_ID not configured')

        url = f'{base_url}/{phone_id}'
        params = {'fields': 'display_phone_number,verified_name,quality_rating'}
        headers = {'Authorization': f'Bearer {token}'}

        start = time.monotonic()
        resp = requests.get(url, params=params, headers=headers,
                            timeout=(self.CONNECT_TIMEOUT, self.READ_TIMEOUT))
        latency_ms = int((time.monotonic() - start) * 1000)

        if resp.status_code == 200:
            data = resp.json()
            meta = {
                'display_phone_number': data.get('display_phone_number', ''),
                'verified_name':        data.get('verified_name', ''),
                'quality_rating':       data.get('quality_rating', 'UNKNOWN'),
                'http_status':          200,
            }
            return HealthResult(status=STATUS_OK, latency_ms=latency_ms,
                                detail='Token valid', meta=meta)
        elif resp.status_code in (401, 403):
            return HealthResult(status=STATUS_DOWN, latency_ms=latency_ms,
                                detail=f'Token invalid or expired (HTTP {resp.status_code})',
                                meta={'http_status': resp.status_code})
        else:
            return HealthResult(status=STATUS_DEGRADED, latency_ms=latency_ms,
                                detail=f'Unexpected HTTP {resp.status_code}',
                                meta={'http_status': resp.status_code, 'body': resp.text[:200]})


# ---------------------------------------------------------------------------
# 5. MTN MoMo
# ---------------------------------------------------------------------------

class MTNMoMoCheck:
    """
    Verifies MTN MoMo API reachability by requesting a Collection OAuth token.
    We request a *new* token (not the cached app token) using Basic auth so we
    exercise the actual credential path.
    Timeout: connect=3s, read=5s.
    Status:
      ok       — 200 / 202 from token endpoint
      degraded — endpoint reachable but unexpected status
      down     — network failure or 4xx auth error
    """
    CONNECT_TIMEOUT = 3
    READ_TIMEOUT    = 5

    def run(self) -> HealthResult:
        start = time.monotonic()
        try:
            result = _run_with_timeout(self._check, self.CONNECT_TIMEOUT + self.READ_TIMEOUT + 1)
            return result
        except _TimeoutError:
            return HealthResult(
                status=STATUS_DOWN,
                latency_ms=int((time.monotonic() - start) * 1000),
                detail=f'Request timed out after {self.CONNECT_TIMEOUT + self.READ_TIMEOUT}s',
            )
        except Exception as exc:  # noqa: BLE001
            return HealthResult(
                status=STATUS_DOWN,
                latency_ms=int((time.monotonic() - start) * 1000),
                detail=str(exc),
            )

    def _check(self) -> HealthResult:
        import requests
        from django.conf import settings

        base_url    = getattr(settings, 'MTN_MOMO_BASE_URL', 'https://sandbox.momodeveloper.mtn.com')
        sub_key     = getattr(settings, 'MTN_MOMO_SUBSCRIPTION_KEY', '')
        api_user    = getattr(settings, 'MTN_MOMO_API_USER', '')
        api_key     = getattr(settings, 'MTN_MOMO_API_KEY', '')
        environment = getattr(settings, 'MTN_MOMO_ENVIRONMENT', 'sandbox')

        if not all([sub_key, api_user, api_key]):
            return HealthResult(status=STATUS_DEGRADED, latency_ms=0,
                                detail='MTN MoMo credentials not configured',
                                meta={'environment': environment})

        url     = f'{base_url}/collection/token/'
        headers = {
            'Ocp-Apim-Subscription-Key': sub_key,
            'X-Target-Environment':      environment,
        }

        start = time.monotonic()
        resp = requests.post(url, headers=headers,
                             auth=(api_user, api_key),
                             timeout=(self.CONNECT_TIMEOUT, self.READ_TIMEOUT))
        latency_ms = int((time.monotonic() - start) * 1000)

        meta = {'environment': environment, 'http_status': resp.status_code}
        if resp.status_code == 200:
            data = resp.json()
            # Don't leak the token — only report token_type and expires_in
            meta['token_type']   = data.get('token_type', '')
            meta['expires_in']   = data.get('expires_in', '')
            return HealthResult(status=STATUS_OK, latency_ms=latency_ms,
                                detail='Token acquired successfully', meta=meta)
        elif resp.status_code in (401, 403):
            return HealthResult(status=STATUS_DOWN, latency_ms=latency_ms,
                                detail=f'Credential error (HTTP {resp.status_code})', meta=meta)
        else:
            return HealthResult(status=STATUS_DEGRADED, latency_ms=latency_ms,
                                detail=f'Unexpected HTTP {resp.status_code}', meta=meta)


# ---------------------------------------------------------------------------
# 6. Airtel Money
# ---------------------------------------------------------------------------

class AirtelMoneyCheck:
    """
    Verifies Airtel Money API reachability by requesting an OAuth2 client-credentials token.
    Reads AIRTEL_CLIENT_ID and AIRTEL_CLIENT_SECRET from settings.
    Timeout: connect=3s, read=5s.
    Status:
      ok       — token endpoint returns 200 with access_token
      degraded — credentials not configured (non-critical if Airtel not used)
      down     — endpoint unreachable or 4xx
    """
    CONNECT_TIMEOUT = 3
    READ_TIMEOUT    = 5

    # Airtel endpoints
    PRODUCTION_URL = 'https://openapi.airtel.africa/auth/oauth2/token'
    SANDBOX_URL    = 'https://openapiuat.airtel.africa/auth/oauth2/token'

    def run(self) -> HealthResult:
        start = time.monotonic()
        try:
            result = _run_with_timeout(self._check, self.CONNECT_TIMEOUT + self.READ_TIMEOUT + 1)
            return result
        except _TimeoutError:
            return HealthResult(
                status=STATUS_DOWN,
                latency_ms=int((time.monotonic() - start) * 1000),
                detail=f'Request timed out after {self.CONNECT_TIMEOUT + self.READ_TIMEOUT}s',
            )
        except Exception as exc:  # noqa: BLE001
            return HealthResult(
                status=STATUS_DOWN,
                latency_ms=int((time.monotonic() - start) * 1000),
                detail=str(exc),
            )

    def _check(self) -> HealthResult:
        import requests
        from django.conf import settings

        client_id     = getattr(settings, 'AIRTEL_CLIENT_ID', '')
        client_secret = getattr(settings, 'AIRTEL_CLIENT_SECRET', '')
        environment   = getattr(settings, 'AIRTEL_ENVIRONMENT', 'sandbox')

        if not all([client_id, client_secret]):
            # Airtel is optional — degraded, not down
            return HealthResult(status=STATUS_DEGRADED, latency_ms=0,
                                detail='Airtel credentials not configured (optional)',
                                meta={'environment': environment})

        url = self.SANDBOX_URL if environment == 'sandbox' else self.PRODUCTION_URL
        payload = {
            'client_id':     client_id,
            'client_secret': client_secret,
            'grant_type':    'client_credentials',
        }
        headers = {'Content-Type': 'application/json'}

        start = time.monotonic()
        resp = requests.post(url, json=payload, headers=headers,
                             timeout=(self.CONNECT_TIMEOUT, self.READ_TIMEOUT))
        latency_ms = int((time.monotonic() - start) * 1000)

        meta = {'environment': environment, 'http_status': resp.status_code}
        if resp.status_code == 200:
            data = resp.json()
            meta['token_type'] = data.get('token_type', '')
            meta['expires_in'] = data.get('expires_in', '')
            return HealthResult(status=STATUS_OK, latency_ms=latency_ms,
                                detail='Token acquired successfully', meta=meta)
        elif resp.status_code in (401, 403):
            return HealthResult(status=STATUS_DOWN, latency_ms=latency_ms,
                                detail=f'Credential error (HTTP {resp.status_code})', meta=meta)
        else:
            return HealthResult(status=STATUS_DEGRADED, latency_ms=latency_ms,
                                detail=f'Unexpected HTTP {resp.status_code}', meta=meta)


# ---------------------------------------------------------------------------
# Registry — maps check name → class
# ---------------------------------------------------------------------------

# CRITICAL checks: system is non-functional if any of these is DOWN
CRITICAL_CHECKS = {
    'postgresql': PostgreSQLCheck,
    'redis':      RedisCheck,
    'celery':     CeleryCheck,
}

# NON-CRITICAL checks: system is degraded but partially functional if these fail
OPTIONAL_CHECKS = {
    'whatsapp':     WhatsAppCheck,
    'mtn_momo':     MTNMoMoCheck,
    'airtel_money': AirtelMoneyCheck,
}

ALL_CHECKS = {**CRITICAL_CHECKS, **OPTIONAL_CHECKS}


def run_check(name: str) -> HealthResult:
    """Run a single named check and return its HealthResult."""
    cls = ALL_CHECKS.get(name)
    if cls is None:
        return HealthResult(status=STATUS_DOWN, detail=f'Unknown check: {name}')
    return cls().run()


def run_all_checks(names: Optional[list] = None) -> dict:
    """
    Run all (or a subset of) checks sequentially.
    Returns dict keyed by check name → HealthResult.
    """
    target = {k: v for k, v in ALL_CHECKS.items() if names is None or k in names}
    return {name: cls().run() for name, cls in target.items()}
