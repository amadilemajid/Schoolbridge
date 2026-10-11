"""
MoMo Webhook Views.
US-026: MTN MoMo IPN — HMAC-SHA256 validated, idempotent, atomic.
US-027: Airtel Money IPN — OAuth2 bearer-token verified, idempotent, atomic.
SEC-004: Airtel OAuth token validation (cached by refresh_airtel_tokens task).
Webhook rate limit: 500/min/school (US-072).
"""
import hashlib
import hmac
import json
import logging
from django.conf import settings
from django.db import IntegrityError
from django.http import JsonResponse
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from schools.models import School
from .services import MoMoService

logger = logging.getLogger('payments')


@method_decorator(csrf_exempt, name='dispatch')
class MTNMoMoWebhookView(View):
    """
    US-026: MTN MoMo IPN endpoint.
    URL: /webhooks/momo/mtn/<school_id>/
    Each school has a unique signing key — validated per request.
    """

    def post(self, request, school_id):
        # Validate school exists
        try:
            school = School.objects.get(id=school_id, is_active=True)
        except School.DoesNotExist:
            logger.warning(f"MTN webhook: school {school_id} not found")
            return JsonResponse({'error': 'Not found'}, status=404)

        # Rate limit check (500/min/school) — tracked in Redis
        if not self._check_rate_limit(f"mtn_webhook:{school_id}"):
            return JsonResponse({'error': 'Rate limit exceeded'}, status=429)

        # Get raw body for HMAC validation (US-026)
        raw_body = request.body
        signature = request.headers.get('X-Callback-Signature', '')

        try:
            payload = json.loads(raw_body)
        except json.JSONDecodeError:
            logger.warning(f"MTN webhook: invalid JSON from school {school_id}")
            return JsonResponse({'error': 'Invalid JSON'}, status=400)

        # Process IPN (signature validation happens inside service)
        # Catch IntegrityError from concurrent duplicate IPNs hitting the
        # unique constraint on Payment.momo_reference before the idempotency
        # check can run — return 200 to prevent gateway retry storms.
        try:
            payment, status_msg = MoMoService.process_mtn_ipn(
                school=school,
                payload=payload,
                raw_bytes=raw_body,
                signature=signature,
            )
        except IntegrityError:
            logger.warning(
                f"MTN IPN: IntegrityError (concurrent duplicate) for school {school_id} — returning already_processed"
            )
            return JsonResponse({'status': 'already_processed'}, status=200)

        if status_msg == 'INVALID_SIGNATURE':
            return JsonResponse({'error': 'Invalid signature'}, status=401)
        if status_msg == 'DUPLICATE':
            # Return 200 for duplicates — MoMo will retry on non-200
            return JsonResponse({'status': 'already_processed'}, status=200)
        if status_msg == 'NON_SUCCESSFUL':
            return JsonResponse({'status': 'noted'}, status=200)

        logger.info(f"MTN IPN processed: {status_msg} school={school_id}")
        return JsonResponse({'status': 'ok'}, status=200)

    def _check_rate_limit(self, key, limit=500, window=60):
        """
        Atomic rate limiter using cache.add + cache.incr to avoid TTL-reset bug.
        - cache.add sets the key only if it does not already exist (atomic init with TTL).
        - cache.incr increments an existing key without touching its TTL.
        This ensures the counter naturally resets after `window` seconds.
        """
        try:
            from django.core.cache import cache
            # Attempt to initialize the counter; no-op if already exists
            cache.add(key, 0, timeout=window)
            count = cache.incr(key)
            return count <= limit
        except Exception:
            return True  # Fail open on cache errors


@method_decorator(csrf_exempt, name='dispatch')
class AirtelMoMoWebhookView(View):
    """
    US-027: Airtel Money IPN endpoint.
    URL: /webhooks/momo/airtel/<school_id>/
    SEC-004: Airtel uses OAuth2 — token refreshed by Celery task and cached in Redis.
    Inbound callbacks must supply 'Authorization: Bearer <token>' matching the cached token.
    """

    def post(self, request, school_id):
        try:
            school = School.objects.get(id=school_id, is_active=True)
        except School.DoesNotExist:
            return JsonResponse({'error': 'Not found'}, status=404)

        if not self._check_rate_limit(f"airtel_webhook:{school_id}"):
            return JsonResponse({'error': 'Rate limit exceeded'}, status=429)

        # SEC-004: Verify Airtel OAuth bearer token
        # The token is cached by refresh_airtel_tokens Celery task (payments/tasks.py).
        # Airtel includes it as "Authorization: Bearer <token>" on callback requests.
        if not self._verify_airtel_token(request, str(school_id)):
            logger.warning(f"Airtel webhook: invalid/missing token for school {school_id}")
            return JsonResponse({'error': 'Unauthorized'}, status=401)

        try:
            payload = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({'error': 'Invalid JSON'}, status=400)

        # Catch IntegrityError from concurrent duplicate IPNs before the
        # idempotency check can serialize them — return 200 to stop retries.
        try:
            payment, status_msg = MoMoService.process_airtel_ipn(school=school, payload=payload)
        except IntegrityError:
            logger.warning(
                f"Airtel IPN: IntegrityError (concurrent duplicate) for school {school_id} — returning already_processed"
            )
            return JsonResponse({'status': 'already_processed'}, status=200)

        if status_msg == 'DUPLICATE':
            return JsonResponse({'status': 'already_processed'}, status=200)
        if status_msg == 'NON_SUCCESSFUL':
            return JsonResponse({'status': 'noted'}, status=200)

        logger.info(f"Airtel IPN processed: {status_msg} school={school_id}")
        return JsonResponse({'status': 'ok'}, status=200)

    def _verify_airtel_token(self, request, school_id):
        """
        SEC-004: Verify Airtel OAuth bearer token on inbound callback.
        The current token is cached in Redis by the refresh_airtel_tokens task.
        Falls back to fail-open only if DEBUG=True (test/dev environments).
        """
        try:
            from django.core.cache import cache
            cached_token = cache.get(f"airtel_token:{school_id}")
            if not cached_token:
                # No cached token — allow in DEBUG (dev/test), reject in production
                if settings.DEBUG:
                    return True
                logger.warning(
                    f"Airtel webhook: no cached token for school {school_id} — rejecting in production"
                )
                return False
            auth_header = request.headers.get('Authorization', '')
            if not auth_header.startswith('Bearer '):
                return False
            received_token = auth_header[7:].strip()
            return hmac.compare_digest(received_token, cached_token)
        except Exception as exc:
            logger.error(f"Airtel token verification error: {exc}")
            # Fail-safe: reject in production, allow in debug
            return settings.DEBUG

    def _check_rate_limit(self, key, limit=500, window=60):
        """
        Atomic rate limiter using cache.add + cache.incr to avoid TTL-reset bug.
        - cache.add sets the key only if it does not already exist (atomic init with TTL).
        - cache.incr increments an existing key without touching its TTL.
        This ensures the counter naturally resets after `window` seconds.
        """
        try:
            from django.core.cache import cache
            cache.add(key, 0, timeout=window)
            count = cache.incr(key)
            return count <= limit
        except Exception:
            return True
