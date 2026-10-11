"""
Django Management Command: archive_audit_logs
Prunes/archives audit, escalation, and message logs older than a specified retention threshold (default: 90 days).
"""
import logging
from datetime import timedelta
from django.core.management.base import BaseCommand
from django.utils import timezone
from messaging.models import MessageLog
from payments.escalation_models import ReminderEscalationLog

logger = logging.getLogger('audit')


class Command(BaseCommand):
    help = 'Archives or prunes audit, message, and escalation logs older than retention threshold.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--days',
            type=int,
            default=90,
            help='Retention period in days. Logs older than this will be deleted.'
        )

    def handle(self, *args, **options):
        days = options['days']
        cutoff = timezone.now() - timedelta(days=days)

        self.stdout.write(self.style.NOTICE(f"Archiving logs older than {days} days (cutoff: {cutoff})..."))

        # Prune MessageLog
        msg_count, _ = MessageLog.all_objects.filter(sent_at__lt=cutoff).delete()
        self.stdout.write(self.style.SUCCESS(f"Successfully pruned {msg_count} old MessageLog entries."))

        # Prune ReminderEscalationLog
        esc_count, _ = ReminderEscalationLog.objects.filter(sent_at__lt=cutoff).delete()
        self.stdout.write(self.style.SUCCESS(f"Successfully pruned {esc_count} old ReminderEscalationLog entries."))

        logger.info(f"Log archival complete: {msg_count} MessageLogs, {esc_count} EscalationLogs pruned.")
