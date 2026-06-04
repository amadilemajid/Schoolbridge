"""
Initialize escalation schedules for active terms.
"""
from django.core.management.base import BaseCommand
from schools.models import AcademicTerm
from payments.escalation_service import EscalationEngine


class Command(BaseCommand):
    help = 'Initialize escalation schedules for active/current terms'

    def add_arguments(self, parser):
        parser.add_argument(
            '--all',
            action='store_true',
            help='Initialize for all future terms, not just current ones',
        )

    def handle(self, *args, **options):
        if options['all']:
            # All terms with future deadlines
            from django.utils import timezone
            terms = AcademicTerm.objects.filter(
                fee_deadline__gte=timezone.localdate()
            )
            self.stdout.write(f"Processing all {terms.count()} terms with future deadlines...")
        else:
            # Just current terms
            terms = AcademicTerm.objects.filter(is_current=True)
            self.stdout.write(f"Processing {terms.count()} current terms...")
        
        total_count = 0
        for term in terms:
            count = EscalationEngine.initialize_escalations_for_term(term)
            total_count += count
            self.stdout.write(
                self.style.SUCCESS(
                    f'✓ {term.school.name} - {term.name}: {count} escalations'
                )
            )
        
        self.stdout.write(
            self.style.SUCCESS(
                f'\nTotal: {total_count} escalation reminders initialized'
            )
        )
