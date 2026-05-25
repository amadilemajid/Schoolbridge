"""
Celery configuration for SchoolBridge.
All background tasks — WhatsApp, SMS, reports, reminders — run here.
"""
import os
from celery import Celery
from celery.signals import task_failure
import logging

logger = logging.getLogger('schoolbridge')

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

app = Celery('schoolbridge')
app.config_from_object('django.conf:settings', namespace='CELERY')
app.autodiscover_tasks()


@task_failure.connect
def handle_task_failure(sender, task_id, exception, args, kwargs, traceback, einfo, **kw):
    """
    Dead-letter queue: log all tasks that exhaust their retries.
    Admin is alerted via US-073 monitoring.
    """
    logger.error(
        f"DEAD_LETTER | task={sender.name} | task_id={task_id} | "
        f"args={args} | kwargs={kwargs} | exception={exception}"
    )
    # Import here to avoid circular imports at module load time
    from notifications.services import send_admin_alert
    send_admin_alert(
        alert_type='CELERY_TASK_FAILURE',
        message=f"Task {sender.name} failed permanently: {exception}",
        payload={'task_id': task_id, 'args': str(args), 'kwargs': str(kwargs)},
    )


@app.task(bind=True, ignore_result=True)
def debug_task(self):
    print(f'Request: {self.request!r}')
