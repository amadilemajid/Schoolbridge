"""
Management command: python manage.py setup_periodic_tasks
Registers all Celery beat periodic tasks into the database.
Run once after initial migrations.
"""
from django.core.management.base import BaseCommand
import json


class Command(BaseCommand):
    help = 'Register all SchoolBridge Celery periodic tasks into the database'

    TASKS = [
        {
            'name': 'Daily reconciliation report (11pm EAT)',
            'task': 'automation.tasks.generate_daily_reconciliation_report',
            'minute': '0', 'hour': '20',
        },
        {
            'name': 'Check reconciliation alerts (hourly)',
            'task': 'automation.tasks.check_reconciliation_alerts',
            'minute': '0', 'hour': '*',
        },
        {
            'name': 'Weekly Director digest (Mon 7am EAT)',
            'task': 'automation.tasks.send_weekly_director_digest',
            'minute': '0', 'hour': '4', 'day_of_week': '1',
        },
        {
            'name': 'Daily staff digest (7:30am EAT)',
            'task': 'automation.tasks.send_daily_staff_digest',
            'minute': '30', 'hour': '4',
        },
        {
            'name': 'Teacher attendance reminders (10am EAT)',
            'task': 'attendance.tasks.send_teacher_attendance_reminders',
            'minute': '0', 'hour': '7',
        },
        {
            'name': 'Celery queue health check (every 5 min)',
            'task': 'automation.tasks.check_celery_queue_health',
            'minute': '*/5',
        },
        {
            'name': 'Refresh Airtel tokens (every 50 min)',
            'task': 'payments.tasks.refresh_airtel_tokens',
            'minute': '*/50',
        },
    ]

    def handle(self, *args, **options):
        from django_celery_beat.models import PeriodicTask, CrontabSchedule
        created = updated = 0

        for t in self.TASKS:
            schedule, _ = CrontabSchedule.objects.get_or_create(
                minute=t.get('minute', '*'),
                hour=t.get('hour', '*'),
                day_of_week=t.get('day_of_week', '*'),
                day_of_month=t.get('day_of_month', '*'),
                month_of_year=t.get('month_of_year', '*'),
            )
            _, was_created = PeriodicTask.objects.update_or_create(
                name=t['name'],
                defaults={
                    'task': t['task'],
                    'crontab': schedule,
                    'enabled': True,
                    'args': json.dumps([]),
                }
            )
            if was_created:
                created += 1
            else:
                updated += 1

        self.stdout.write(
            self.style.SUCCESS(f'Done: {created} created, {updated} updated')
        )
