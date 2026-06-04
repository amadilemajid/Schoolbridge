"""
Celery Beat periodic task schedule.
All scheduled tasks for SchoolBridge.
Loaded via Django DB scheduler (django-celery-beat).
Times are in Africa/Kampala (EAT = UTC+3).
"""
from celery.schedules import crontab

CELERYBEAT_SCHEDULE = {
    # US-062: Daily reconciliation report at 11pm EAT
    'daily-reconciliation-report': {
        'task': 'automation.tasks.generate_daily_reconciliation_report',
        'schedule': crontab(hour=20, minute=0),  # 20:00 UTC = 23:00 EAT
        'options': {'queue': 'automation'},
    },

    # US-075: Check unmatched payments for 24hr/48hr alerts — every hour
    'check-reconciliation-alerts': {
        'task': 'automation.tasks.check_reconciliation_alerts',
        'schedule': crontab(minute=0),  # Every hour on the hour
        'options': {'queue': 'automation'},
    },

    # US-058: Weekly Director digest — Monday 7am EAT (04:00 UTC)
    'weekly-director-digest': {
        'task': 'automation.tasks.send_weekly_director_digest',
        'schedule': crontab(hour=4, minute=0, day_of_week='monday'),
        'options': {'queue': 'automation'},
    },

    # US-077: Daily 7:30am staff digest (04:30 UTC = 07:30 EAT)
    'daily-staff-digest': {
        'task': 'automation.tasks.send_daily_staff_digest',
        'schedule': crontab(hour=4, minute=30),
        'options': {'queue': 'automation'},
    },

    # US-076: Attendance reminder to teachers at 10am EAT (07:00 UTC)
    'attendance-teacher-reminder': {
        'task': 'attendance.tasks.send_teacher_attendance_reminders',
        'schedule': crontab(hour=7, minute=0),
        'options': {'queue': 'automation'},
    },

    # US-073: Celery queue depth check — every 5 minutes
    'celery-queue-health-check': {
        'task': 'automation.tasks.check_celery_queue_health',
        'schedule': crontab(minute='*/5'),
        'options': {'queue': 'automation'},
    },

    # Airtel OAuth token refresh — every 50 minutes (token TTL = 60min)
    # US-027: Keep Airtel token fresh in Redis
    'refresh-airtel-tokens': {
        'task': 'payments.tasks.refresh_airtel_tokens',
        'schedule': crontab(minute='*/50'),
        'options': {'queue': 'payments'},
    },

    # US-073: SSL certificate expiry check — daily at 6am EAT (03:00 UTC)
    'ssl-certificate-check': {
        'task': 'automation.tasks.check_ssl_certificate_expiry',
        'schedule': crontab(hour=3, minute=0),
        'options': {'queue': 'automation'},
    },

    # US-073: Database backup health check — daily at 7am EAT (04:00 UTC)
    # Assumes backup runs at midnight; check at 7am gives 7hrs for backup to complete
    'database-backup-check': {
        'task': 'automation.tasks.check_database_backup_health',
        'schedule': crontab(hour=4, minute=0),
        'options': {'queue': 'automation'},
    },

    # US-040: Sync Meta template approval status — daily at 8am EAT (05:00 UTC)
    'sync-meta-templates': {
        'task': 'automation.tasks.sync_pending_meta_templates',
        'schedule': crontab(hour=5, minute=0),
        'options': {'queue': 'automation'},
    },
}
