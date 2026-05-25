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
