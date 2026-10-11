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


app.conf.task_routes = {
    # ── Real-time / High Priority ──────────────────────────────────────────
    # These MUST run immediately to satisfy SLA (e.g. 60s receipt delivery).
    # Routed to the `realtime` queue — dedicate ≥1 worker to this queue.
    'messaging.tasks.send_payment_receipt': {'queue': 'realtime'},
    'messaging.tasks.send_payment_reversal_notification': {'queue': 'realtime'},
    'messaging.tasks.send_whatsapp_message': {'queue': 'realtime'},
    'messaging.tasks.send_sms_fallback': {'queue': 'realtime'},
    'messaging.tasks.send_absence_alert': {'queue': 'realtime'},
    'risk.tasks.dispatch_risk_alerts': {'queue': 'realtime'},

    # ── Bulk / Low Priority ────────────────────────────────────────────────
    # These are long-running and must NOT block real-time tasks.
    # Routed to the `messaging` queue so messaging workers process them.
    'messaging.tasks.send_broadcast_chunk': {'queue': 'messaging'},
    'messaging.tasks.process_voice_broadcast': {'queue': 'messaging'},
    'messaging.tasks.distribute_report_cards': {'queue': 'bulk'},
    'students.tasks.process_bulk_import': {'queue': 'bulk'},
    'results.tasks.generate_single_report_card': {'queue': 'bulk'},
    'results.tasks.notify_parent_report_ready': {'queue': 'bulk'},
    'results.tasks.recompute_term_results_task': {'queue': 'bulk'},

    # ── Default / Medium Priority ──────────────────────────────────────────
    # Everything else falls through to the `celery` (default) queue.
}

