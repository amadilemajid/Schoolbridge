"""
MoMo Webhook Views.
US-026: MTN MoMo IPN — HMAC-SHA256 validated, idempotent, atomic.
US-027: Airtel Money IPN — OAuth2, idempotent, atomic.
Webhook rate limit: 500/min/school (US-072).
"""
import hashlib
import hmac
import json
import logging
from django.conf import settings
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
        payment, status_msg = MoMoService.process_mtn_ipn(
            school=school,
            payload=payload,
            raw_bytes=raw_body,
            signature=signature,
        )

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
        """Simple Redis sliding window rate limiter."""
        try:
            from django.core.cache import cache
            count = cache.get(key, 0)
            if count >= limit:
                return False
            cache.set(key, count + 1, timeout=window)
            return True
        except Exception:
            return True  # Fail open on cache errors


@method_decorator(csrf_exempt, name='dispatch')
class AirtelMoMoWebhookView(View):
    """
    US-027: Airtel Money IPN endpoint.
    URL: /webhooks/momo/airtel/<school_id>/
    Airtel uses OAuth2 — token refreshed by Celery task and cached in Redis.
    """

    def post(self, request, school_id):
        try:
            school = School.objects.get(id=school_id, is_active=True)
        except School.DoesNotExist:
            return JsonResponse({'error': 'Not found'}, status=404)

        if not self._check_rate_limit(f"airtel_webhook:{school_id}"):
            return JsonResponse({'error': 'Rate limit exceeded'}, status=429)

        try:
            payload = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({'error': 'Invalid JSON'}, status=400)

        payment, status_msg = MoMoService.process_airtel_ipn(school=school, payload=payload)

        if status_msg == 'DUPLICATE':
            return JsonResponse({'status': 'already_processed'}, status=200)
        if status_msg == 'NON_SUCCESSFUL':
            return JsonResponse({'status': 'noted'}, status=200)

        logger.info(f"Airtel IPN processed: {status_msg} school={school_id}")
        return JsonResponse({'status': 'ok'}, status=200)

    def _check_rate_limit(self, key, limit=500, window=60):
        try:
            from django.core.cache import cache
            count = cache.get(key, 0)
            if count >= limit:
                return False
            cache.set(key, count + 1, timeout=window)
            return True
        except Exception:
            return True
