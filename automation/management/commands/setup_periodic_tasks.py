from django.core.management.base import BaseCommand
import json
from automation.beat_schedule import CELERYBEAT_SCHEDULE

class Command(BaseCommand):
    help = "Register all SchoolBridge Celery periodic tasks from beat_schedule"

    def handle(self, *args, **options):
        from django_celery_beat.models import PeriodicTask, CrontabSchedule
        created = updated = 0
        day_map = {
            'monday': '1', 'tuesday': '2', 'wednesday': '3',
            'thursday': '4', 'friday': '5', 'saturday': '6', 'sunday': '0'
        }

        for name, config in CELERYBEAT_SCHEDULE.items():
            sched = config['schedule']
            dow = getattr(sched, '_orig_day_of_week', '*')
            dow_str = day_map.get(str(dow).lower(), str(dow))

            schedule, _ = CrontabSchedule.objects.get_or_create(
                minute=str(getattr(sched, '_orig_minute', '*')),
                hour=str(getattr(sched, '_orig_hour', '*')),
                day_of_week=dow_str,
                day_of_month=str(getattr(sched, '_orig_day_of_month', '*')),
                month_of_year=str(getattr(sched, '_orig_month_of_year', '*')),
            )
            queue = config.get('options', {}).get('queue')

            _, was_created = PeriodicTask.objects.update_or_create(
                name=name,
                defaults={
                    "task": config["task"],
                    "crontab": schedule,
                    "enabled": True,
                    "queue": queue,
                    "args": json.dumps([]),
                },
            )
            if was_created:
                created += 1
            else:
                updated += 1
        self.stdout.write(self.style.SUCCESS(f"Done: {created} created, {updated} updated (Total {len(CELERYBEAT_SCHEDULE)} tasks synced)"))