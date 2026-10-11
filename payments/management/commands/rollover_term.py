"""
Management command: rollover_term
Closes the current academic term and rolls over any outstanding fee balances
into the new term's fee records as "Previous Term Arrears".

Usage:
    python manage.py rollover_term --term-id <id> --new-term-id <id> [--dry-run]
"""
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone


class Command(BaseCommand):
    help = "Rollover outstanding fee balances from the current term into the next term's fee records."

    def add_arguments(self, parser):
        parser.add_argument(
            '--term-id', type=int, required=True,
            help='ID of the closing (current) academic term.'
        )
        parser.add_argument(
            '--new-term-id', type=int, required=True,
            help='ID of the new academic term to roll balances into.'
        )
        parser.add_argument(
            '--dry-run', action='store_true', default=False,
            help='Preview what would happen without making any database changes.'
        )

    @transaction.atomic
    def handle(self, *args, **options):
        from schools.models import AcademicTerm
        from payments.models import FeeRecord, FeeStructure, FeeStructureItem

        term_id = options['term_id']
        new_term_id = options['new_term_id']
        dry_run = options['dry_run']

        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN — No database changes will be made.\n'))

        # Validate terms
        try:
            current_term = AcademicTerm.objects.get(id=term_id)
        except AcademicTerm.DoesNotExist:
            raise CommandError(f'Term with ID {term_id} does not exist.')

        try:
            new_term = AcademicTerm.objects.get(id=new_term_id)
        except AcademicTerm.DoesNotExist:
            raise CommandError(f'New term with ID {new_term_id} does not exist.')

        if current_term.school != new_term.school:
            raise CommandError('Both terms must belong to the same school.')

        # Find all unpaid/partially paid records in the current term
        unpaid_records = FeeRecord.objects.filter(
            school=current_term.school,
            academic_term=current_term,
        ).select_related('student', 'fee_structure')

        outstanding_records = [r for r in unpaid_records if r.balance > 0]

        self.stdout.write(
            f'Found {len(outstanding_records)} records with outstanding balances '
            f'in "{current_term}" (School: {current_term.school.name}).\n'
        )

        rollover_count = 0
        total_arrears = 0

        for record in outstanding_records:
            arrears_amount = record.balance
            student = record.student

            self.stdout.write(
                f'  [{student.student_id}] {student.get_full_name()}: '
                f'UGX {arrears_amount:,} outstanding → rolling into {new_term}'
            )

            if not dry_run:
                # Find or create the new term's fee record for this student
                new_fee_record, created = FeeRecord.all_objects.get_or_create(
                    school=current_term.school,
                    student=student,
                    academic_term=new_term,
                    defaults={
                        'fee_structure': new_term.fee_structures.filter(
                            class_group=student.current_class
                        ).first() or new_term.fee_structures.first(),
                        'total_amount': 0,
                    }
                )

                # Inject "Previous Term Arrears" as additional amount_owed
                new_fee_record.total_amount += arrears_amount
                new_fee_record.save()

                self.stdout.write(
                    f'    → {"Created new" if created else "Updated existing"} '
                    f'fee record for {new_term}. Total: UGX {new_fee_record.total_amount:,}'
                )

            rollover_count += 1
            total_arrears += arrears_amount

        # Mark old term as closed
        if not dry_run:
            current_term.is_current = False
            current_term.save()

        self.stdout.write('\n' + '=' * 60)
        self.stdout.write(self.style.SUCCESS(
            f'{"[DRY RUN] Would roll" if dry_run else "Rolled"} over '
            f'{rollover_count} records with total arrears of UGX {total_arrears:,}.'
        ))

        if dry_run:
            # Rollback all changes made during dry run
            transaction.set_rollback(True)
            self.stdout.write(self.style.WARNING('DRY RUN complete — all changes rolled back.\n'))
