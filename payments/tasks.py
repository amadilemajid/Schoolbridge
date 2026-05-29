"""Payments Celery tasks."""
import logging
from celery import shared_task
from celery.exceptions import MaxRetriesExceededError

logger = logging.getLogger('payments')


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def refresh_airtel_tokens(self):
    """
    US-027: Refresh Airtel OAuth token for all active schools with Airtel config.
    Caches token in Redis (1hr TTL) and DB.
    """
    from schools.models import SchoolMoMoConfig
    import requests
    import datetime
    from django.utils import timezone
    from django.core.cache import cache

    configs = SchoolMoMoConfig.objects.filter(provider='airtel', is_active=True)
    for cfg in configs:
        try:
            # Call Airtel token endpoint
            response = requests.post(
                'https://openapi.airtel.africa/auth/oauth2/token',
                json={
                    'client_id': cfg.airtel_client_id,
                    'client_secret': cfg.airtel_client_secret,
                    'grant_type': 'client_credentials',
                },
                timeout=15,
            )
            response.raise_for_status()
            data = response.json()
            token = data.get('access_token', '')
            expires_in = data.get('expires_in', 3600)

            # Cache in Redis
            cache_key = f"airtel_token:{cfg.school_id}"
            cache.set(cache_key, token, timeout=expires_in - 60)

            logger.info(f"Airtel token refreshed for school {cfg.school_id}")
        except Exception as exc:
            logger.error(f"Airtel token refresh failed for school {cfg.school_id}: {exc}")
            from notifications.services import send_admin_alert
            send_admin_alert(
                alert_type='AIRTEL_TOKEN_REFRESH_FAILED',
                message=f"Failed to refresh Airtel token for school {cfg.school_id}: {exc}",
                payload={'school_id': str(cfg.school_id)},
            )


@shared_task(bind=True, max_retries=5, default_retry_delay=60)
def retry_failed_momo_webhook(self, school_id, payload, provider):
    """
    US-068: Retry failed MoMo webhook processing up to 5 times.
    Called when webhook processing fails due to transient errors.
    """
    from schools.models import School
    from payments.services import MoMoService

    try:
        school = School.objects.get(id=school_id)
        if provider == 'mtn':
            payment, status_msg = MoMoService.process_mtn_ipn(
                school=school,
                payload=payload,
                raw_bytes=str(payload).encode(),
                signature='',
            )
        else:
            payment, status_msg = MoMoService.process_airtel_ipn(
                school=school,
                payload=payload,
            )
        logger.info(
            f"Webhook retry succeeded: {status_msg} school={school_id} attempt={self.request.retries + 1}"
        )
    except Exception as exc:
        logger.error(f"Webhook retry failed (attempt {self.request.retries + 1}): {exc}")
        try:
            self.retry(exc=exc)
        except MaxRetriesExceededError:
            logger.error(f"Webhook retry exhausted after 5 attempts for school {school_id}")
            from notifications.services import send_admin_alert

            send_admin_alert(
                alert_type='MOMO_WEBHOOK_RETRY_EXHAUSTED',
                message=f"MoMo webhook failed after 5 retries for school {school_id}",
                payload={'school_id': school_id, 'provider': provider},
            )
