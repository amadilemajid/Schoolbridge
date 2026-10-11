"""
Automation & Task Queue Health Monitoring Service.
Monitors queue depth, task backlog, and queue latency.
"""
import logging
from celery import shared_task
from django.conf import settings

logger = logging.getLogger('automation')


class QueueHealthService:
    """
    Service for inspecting queue size and health metrics.
    """

    @classmethod
    def check_queue_health(cls, max_backlog=500):
        """
        Inspect task queue depth and log health status.
        """
        status = {
            'healthy': True,
            'queue_size': 0,
            'max_threshold': max_backlog,
            'message': 'Queue operation normal'
        }

        try:
            # Check if redis client available
            import redis
            broker_url = getattr(settings, 'CELERY_BROKER_URL', 'redis://localhost:6379/0')
            r = redis.Redis.from_url(broker_url)
            queue_len = r.llen('celery')
            status['queue_size'] = queue_len

            if queue_len > max_backlog:
                status['healthy'] = False
                status['message'] = f"WARNING: Queue backlog elevated ({queue_len} pending tasks > {max_backlog})"
                logger.warning(status['message'])
            else:
                logger.info(f"Queue health check passed: {queue_len} tasks in queue.")

        except Exception as exc:
            # If Redis connection fails or in test mode without Redis
            logger.info(f"Queue health check fallback (redis unavailable or mocked): {exc}")
            status['message'] = f"Queue health check executed with fallback: {exc}"

        return status


@shared_task
def monitor_queue_health_task():
    """
    Celery periodic task to monitor queue backlog every 15 minutes.
    """
    return QueueHealthService.check_queue_health()
