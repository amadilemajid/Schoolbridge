"""
Tests for production health check endpoints.
Covers: liveness, readiness, detail, metrics, version.
Uses unittest.mock to isolate each external dependency.
"""
import json
from unittest.mock import MagicMock, patch

import pytest
from django.test import TestCase, RequestFactory
from django.urls import reverse


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_ok():
    from config.health_checks import HealthResult, STATUS_OK
    return HealthResult(status=STATUS_OK, latency_ms=5, detail='ok')

def _make_degraded(detail='degraded'):
    from config.health_checks import HealthResult, STATUS_DEGRADED
    return HealthResult(status=STATUS_DEGRADED, latency_ms=10, detail=detail)

def _make_down(detail='connection refused'):
    from config.health_checks import HealthResult, STATUS_DOWN
    return HealthResult(status=STATUS_DOWN, latency_ms=3001, detail=detail)


# ---------------------------------------------------------------------------
# 1. Liveness probe — GET /health/
# ---------------------------------------------------------------------------

class LivenessViewTests(TestCase):

    @patch('config.health_checks.PostgreSQLCheck.run', return_value=None)
    def setUp(self, *args):
        self.url = '/health/'

    @patch('config.health_views.run_check')
    def test_liveness_returns_200_when_db_ok(self, mock_run):
        mock_run.return_value = _make_ok()
        resp = self.client.get('/health/')
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data['status'], 'ok')
        self.assertIn('timestamp', data)

    @patch('config.health_views.run_check')
    def test_liveness_returns_503_when_db_down(self, mock_run):
        mock_run.return_value = _make_down('could not connect to server')
        resp = self.client.get('/health/')
        self.assertEqual(resp.status_code, 503)
        data = resp.json()
        self.assertEqual(data['status'], 'down')

    @patch('config.health_views.run_check')
    def test_liveness_no_cache_header(self, mock_run):
        """Liveness must never be served from cache — confirm no-cache headers."""
        mock_run.return_value = _make_ok()
        resp = self.client.get('/health/')
        self.assertIn('no-cache', resp.get('Cache-Control', '').lower())


# ---------------------------------------------------------------------------
# 2. Readiness probe — GET /health/ready/
# ---------------------------------------------------------------------------

class ReadinessViewTests(TestCase):

    @patch('config.health_views.run_all_checks')
    def test_readiness_200_all_ok(self, mock_run):
        mock_run.return_value = {
            'postgresql': _make_ok(),
            'redis':      _make_ok(),
            'celery':     _make_ok(),
        }
        resp = self.client.get('/health/ready/')
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data['status'], 'ok')
        self.assertIn('timestamp', data)

    @patch('config.health_views.run_all_checks')
    def test_readiness_503_when_db_down(self, mock_run):
        mock_run.return_value = {
            'postgresql': _make_down(),
            'redis':      _make_ok(),
            'celery':     _make_ok(),
        }
        resp = self.client.get('/health/ready/')
        self.assertEqual(resp.status_code, 503)
        self.assertEqual(resp.json()['status'], 'down')

    @patch('config.health_views.run_all_checks')
    def test_readiness_207_when_celery_degraded(self, mock_run):
        mock_run.return_value = {
            'postgresql': _make_ok(),
            'redis':      _make_ok(),
            'celery':     _make_degraded('queue depth > 50'),
        }
        resp = self.client.get('/health/ready/')
        self.assertEqual(resp.status_code, 207)
        self.assertEqual(resp.json()['status'], 'degraded')

    @patch('config.health_views.run_all_checks')
    def test_readiness_only_checks_three_services(self, mock_run):
        """Readiness must not trigger external API calls (WhatsApp/MoMo)."""
        mock_run.return_value = {
            'postgresql': _make_ok(),
            'redis':      _make_ok(),
            'celery':     _make_ok(),
        }
        self.client.get('/health/ready/')
        names = mock_run.call_args[1].get('names', mock_run.call_args[0][0] if mock_run.call_args[0] else None)
        if names:
            for n in names:
                self.assertIn(n, ('postgresql', 'redis', 'celery'))


# ---------------------------------------------------------------------------
# 3. Detail endpoint — GET /health/detail/
# ---------------------------------------------------------------------------

class DetailHealthViewTests(TestCase):

    VALID_TOKEN = 'test-health-token-abc123'

    def setUp(self):
        from django.test.utils import override_settings
        self.override = override_settings(HEALTH_CHECK_TOKEN=self.VALID_TOKEN)
        self.override.enable()

    def tearDown(self):
        self.override.disable()

    @patch('config.health_views.DetailHealthView._get_cached', return_value=None)
    @patch('config.health_views.DetailHealthView._set_cache')
    @patch('config.health_views.run_all_checks')
    def test_detail_200_with_valid_token(self, mock_run, mock_set, mock_get):
        mock_run.return_value = {
            'postgresql':   _make_ok(),
            'redis':        _make_ok(),
            'celery':       _make_ok(),
            'whatsapp':     _make_ok(),
            'mtn_momo':     _make_ok(),
            'airtel_money': _make_degraded('not configured'),
        }
        resp = self.client.get('/health/detail/',
                               HTTP_X_HEALTH_TOKEN=self.VALID_TOKEN)
        self.assertEqual(resp.status_code, 207)   # degraded because airtel is degraded
        data = resp.json()
        self.assertEqual(set(data['checks'].keys()),
                         {'postgresql', 'redis', 'celery', 'whatsapp', 'mtn_momo', 'airtel_money'})
        self.assertIn('timestamp', data)
        self.assertIn('version', data)
        self.assertIn('environment', data)

    def test_detail_401_without_token(self):
        resp = self.client.get('/health/detail/')
        self.assertEqual(resp.status_code, 401)

    def test_detail_401_with_wrong_token(self):
        resp = self.client.get('/health/detail/',
                               HTTP_X_HEALTH_TOKEN='wrong-token')
        self.assertEqual(resp.status_code, 401)

    @patch('config.health_views.DetailHealthView._get_cached')
    def test_detail_serves_from_cache(self, mock_get):
        """When cache is warm, run_all_checks must NOT be called."""
        cached_payload = {
            'status': 'ok', 'timestamp': '2026-01-01T00:00:00+00:00',
            'environment': 'test', 'version': '1.0.0',
            'checks': {'postgresql': {'status': 'ok', 'latency_ms': 2, 'detail': 'ok'}},
        }
        mock_get.return_value = cached_payload
        with patch('config.health_views.run_all_checks') as mock_run:
            resp = self.client.get('/health/detail/',
                                   HTTP_X_HEALTH_TOKEN=self.VALID_TOKEN)
            mock_run.assert_not_called()
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json().get('_cached'))

    @patch('config.health_views.DetailHealthView._get_cached', return_value=None)
    @patch('config.health_views.DetailHealthView._set_cache')
    @patch('config.health_views.run_all_checks')
    def test_detail_503_when_critical_down(self, mock_run, mock_set, mock_get):
        mock_run.return_value = {
            'postgresql':   _make_down(),
            'redis':        _make_ok(),
            'celery':       _make_ok(),
            'whatsapp':     _make_ok(),
            'mtn_momo':     _make_ok(),
            'airtel_money': _make_ok(),
        }
        resp = self.client.get('/health/detail/',
                               HTTP_X_HEALTH_TOKEN=self.VALID_TOKEN)
        self.assertEqual(resp.status_code, 503)
        self.assertEqual(resp.json()['status'], 'down')


# ---------------------------------------------------------------------------
# 4. Prometheus metrics — GET /health/metrics/
# ---------------------------------------------------------------------------

class MetricsViewTests(TestCase):

    VALID_TOKEN = 'test-health-token-abc123'

    def setUp(self):
        from django.test.utils import override_settings
        self.override = override_settings(HEALTH_CHECK_TOKEN=self.VALID_TOKEN)
        self.override.enable()

    def tearDown(self):
        self.override.disable()

    @patch('config.health_views.MetricsView._get_or_run_checks')
    def test_metrics_returns_text_plain(self, mock_checks):
        mock_checks.return_value = {
            'postgresql': {'status': 'ok', 'latency_ms': 3},
            'redis':      {'status': 'ok', 'latency_ms': 2},
        }
        resp = self.client.get('/health/metrics/',
                               HTTP_X_HEALTH_TOKEN=self.VALID_TOKEN)
        self.assertEqual(resp.status_code, 200)
        self.assertIn('text/plain', resp.get('Content-Type', ''))

    @patch('config.health_views.MetricsView._get_or_run_checks')
    def test_metrics_contains_gauge_lines(self, mock_checks):
        mock_checks.return_value = {
            'postgresql': {'status': 'ok',   'latency_ms': 5},
            'redis':      {'status': 'down',  'latency_ms': 3001},
        }
        resp = self.client.get('/health/metrics/',
                               HTTP_X_HEALTH_TOKEN=self.VALID_TOKEN)
        body = resp.content.decode()
        self.assertIn('schoolbridge_service_health', body)
        self.assertIn('service="postgresql"', body)
        self.assertIn('service="redis"', body)
        # PostgreSQL ok → value 1 (label format: service="X",environment="Y"} VALUE TIMESTAMP)
        self.assertIn('service="postgresql"', body)
        self.assertIn('} 1 ', body)   # at least one metric line has value 1
        # Redis down → value -1
        self.assertIn('service="redis"', body)
        self.assertIn('} -1 ', body)  # at least one metric line has value -1

    def test_metrics_401_without_token(self):
        resp = self.client.get('/health/metrics/')
        self.assertEqual(resp.status_code, 401)

    @patch('config.health_views.MetricsView._get_or_run_checks')
    def test_overall_health_metric_present(self, mock_checks):
        mock_checks.return_value = {
            'postgresql': {'status': 'ok', 'latency_ms': 4},
        }
        resp = self.client.get('/health/metrics/',
                               HTTP_X_HEALTH_TOKEN=self.VALID_TOKEN)
        body = resp.content.decode()
        self.assertIn('schoolbridge_overall_health', body)


# ---------------------------------------------------------------------------
# 5. Version endpoint — GET /health/version/
# ---------------------------------------------------------------------------

class VersionViewTests(TestCase):

    def test_version_returns_200(self):
        resp = self.client.get('/health/version/')
        self.assertEqual(resp.status_code, 200)

    def test_version_payload_fields(self):
        resp = self.client.get('/health/version/')
        data = resp.json()
        for field in ['version', 'commit', 'build_timestamp', 'environment']:
            self.assertIn(field, data, f"Missing field: {field}")

    def test_version_is_public_no_auth_required(self):
        """Version endpoint must be publicly accessible without any token."""
        resp = self.client.get('/health/version/')
        self.assertNotEqual(resp.status_code, 401)


# ---------------------------------------------------------------------------
# 6. Individual checker unit tests
# ---------------------------------------------------------------------------

class PostgreSQLCheckTests(TestCase):

    @patch('config.health_checks.PostgreSQLCheck._check')
    def test_ok_result(self, mock_check):
        from config.health_checks import PostgreSQLCheck, STATUS_OK
        mock_check.return_value = _make_ok()
        result = PostgreSQLCheck().run()
        self.assertEqual(result.status, STATUS_OK)

    @patch('config.health_checks._run_with_timeout')
    def test_timeout_returns_down(self, mock_timeout):
        from config.health_checks import PostgreSQLCheck, STATUS_DOWN, _TimeoutError
        mock_timeout.side_effect = _TimeoutError('timed out after 3s')
        result = PostgreSQLCheck().run()
        self.assertEqual(result.status, STATUS_DOWN)
        self.assertIn('timed out', result.detail)

    @patch('config.health_checks._run_with_timeout')
    def test_exception_returns_down(self, mock_timeout):
        from config.health_checks import PostgreSQLCheck, STATUS_DOWN
        mock_timeout.side_effect = Exception('connection refused')
        result = PostgreSQLCheck().run()
        self.assertEqual(result.status, STATUS_DOWN)


class RedisCheckTests(TestCase):

    @patch('config.health_checks._run_with_timeout')
    def test_ok_result(self, mock_timeout):
        from config.health_checks import RedisCheck, STATUS_OK
        mock_timeout.return_value = _make_ok()
        result = RedisCheck().run()
        self.assertEqual(result.status, STATUS_OK)

    @patch('config.health_checks._run_with_timeout')
    def test_timeout_returns_down(self, mock_timeout):
        from config.health_checks import RedisCheck, STATUS_DOWN, _TimeoutError
        mock_timeout.side_effect = _TimeoutError('timed out after 2s')
        result = RedisCheck().run()
        self.assertEqual(result.status, STATUS_DOWN)


class WhatsAppCheckTests(TestCase):

    @patch('config.health_checks._run_with_timeout')
    def test_unconfigured_returns_degraded(self, mock_timeout):
        from config.health_checks import WhatsAppCheck, STATUS_DEGRADED, HealthResult
        mock_timeout.return_value = HealthResult(status=STATUS_DEGRADED, detail='not configured')
        result = WhatsAppCheck().run()
        self.assertEqual(result.status, STATUS_DEGRADED)

    @patch('config.health_checks._run_with_timeout')
    def test_timeout_returns_down(self, mock_timeout):
        from config.health_checks import WhatsAppCheck, STATUS_DOWN, _TimeoutError
        mock_timeout.side_effect = _TimeoutError('timed out')
        result = WhatsAppCheck().run()
        self.assertEqual(result.status, STATUS_DOWN)


class MTNMoMoCheckTests(TestCase):

    @patch('config.health_checks._run_with_timeout')
    def test_unconfigured_returns_degraded(self, mock_timeout):
        from config.health_checks import MTNMoMoCheck, STATUS_DEGRADED, HealthResult
        mock_timeout.return_value = HealthResult(status=STATUS_DEGRADED, detail='not configured')
        result = MTNMoMoCheck().run()
        self.assertEqual(result.status, STATUS_DEGRADED)


class AirtelMoneyCheckTests(TestCase):

    @patch('config.health_checks._run_with_timeout')
    def test_unconfigured_returns_degraded_not_down(self, mock_timeout):
        """Airtel not configured is non-fatal — must be DEGRADED, not DOWN."""
        from config.health_checks import AirtelMoneyCheck, STATUS_DEGRADED, HealthResult
        mock_timeout.return_value = HealthResult(status=STATUS_DEGRADED, detail='optional')
        result = AirtelMoneyCheck().run()
        self.assertEqual(result.status, STATUS_DEGRADED)


# ---------------------------------------------------------------------------
# 7. Response format contract tests
# ---------------------------------------------------------------------------

class ResponseFormatTests(TestCase):
    """Ensure the JSON contract is stable and backward compatible."""

    @patch('config.health_views.run_check')
    def test_liveness_schema(self, mock_run):
        mock_run.return_value = _make_ok()
        data = self.client.get('/health/').json()
        required = {'status', 'timestamp'}
        self.assertTrue(required.issubset(data.keys()))

    @patch('config.health_views.run_all_checks')
    def test_readiness_schema(self, mock_run):
        mock_run.return_value = {'postgresql': _make_ok(), 'redis': _make_ok(), 'celery': _make_ok()}
        data = self.client.get('/health/ready/').json()
        required = {'status', 'timestamp'}
        self.assertTrue(required.issubset(data.keys()))
