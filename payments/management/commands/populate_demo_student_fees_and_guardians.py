"""
Management command to ensure all enrolled students in St. Mary's College Kampala (Demo)
have primary guardians and Term 1 2026 FeeRecords.
"""
import random
from decimal import Decimal
from django.core.management.base import BaseCommand
from django.utils import timezone
from schools.models import School, AcademicTerm
from students.models import Student, Guardian, ClassGroup
from payments.models import FeeStructure, FeeStructureItem, FeeRecord, Payment


FIRST_NAMES_MALE = [
    'Emmanuel', 'Joseph', 'David', 'Samuel', 'Daniel', 'John', 'Moses',
    'Peter', 'James', 'Paul', 'Brian', 'Isaac', 'Simon', 'Ronald', 'Patrick',
]

FIRST_NAMES_FEMALE = [
    'Grace', 'Mary', 'Sarah', 'Esther', 'Rebecca', 'Ruth', 'Faith',
    'Joan', 'Agnes', 'Harriet', 'Peace', 'Fiona', 'Brenda', 'Christine',
]

LAST_NAMES = [
    'Kato', 'Wasswa', 'Mukasa', 'Kigozi', 'Sserwadda', 'Nsubuga', 'Lwanga',
    'Ochieng', 'Okello', 'Opio', 'Otieno', 'Odongo', 'Owori', 'Opolot',
    'Mugisha', 'Tumusiime', 'Byamukama', 'Mwesigwa', 'Twinomujuni', 'Kiconco',
    'Namubiru', 'Nalubega', 'Nakato', 'Babirye', 'Nantongo', 'Nagawa',
]


def random_uganda_phone():
    prefixes = ['077', '078', '070', '075']
    prefix = random.choice(prefixes)
    digits = ''.join(str(random.randint(0, 9)) for _ in range(7))
    raw = f"{prefix}{digits}"
    # Normalised +256...
    return f"+256{raw[1:]}"


class Command(BaseCommand):
    help = "Populate missing guardians and FeeRecords for demo students"

    def handle(self, *args, **options):
        school = School.objects.filter(name__icontains="St. Mary's College Kampala").first()
        if not school:
            self.stderr.write("Demo school 'St. Mary's College Kampala' not found.")
            return

        term = AcademicTerm.objects.filter(school=school, is_current=True).first()
        if not term:
            self.stderr.write("No active current term found for demo school.")
            return

        self.stdout.write(f"Processing school: {school.name}")
        self.stdout.write(f"Active term: {term.name} (ID: {term.id})")

        from authentication.models import User
        bursar = User.objects.filter(school=school, role='bursar').first()

        # 1. Ensure FeeStructures exist for all classes in this term
        classes = ClassGroup.objects.filter(school=school)
        structures_by_class = {}
        for cg in classes:
            fs = FeeStructure.all_objects.filter(school=school, academic_term=term, class_group=cg).first()
            if not fs:
                is_secondary = 's.' in cg.name.lower() or 'senior' in cg.name.lower()
                tuition = Decimal('450000') if is_secondary else Decimal('350000')
                lunch = Decimal('120000')
                activity = Decimal('30000')

                fs = FeeStructure.all_objects.create(
                    school=school,
                    academic_term=term,
                    class_group=cg,
                    name=f"{cg.name} Term 1 2026 Fees",
                    is_active=True,
                    created_by=bursar,
                )
                FeeStructureItem.objects.create(fee_structure=fs, name='Tuition', amount=tuition, is_mandatory=True)
                FeeStructureItem.objects.create(fee_structure=fs, name='Lunch', amount=lunch, is_mandatory=True)
                FeeStructureItem.objects.create(fee_structure=fs, name='Activity', amount=activity, is_mandatory=False)
            structures_by_class[cg.id] = fs

        # Fallback structure
        default_struct = FeeStructure.all_objects.filter(school=school, academic_term=term).first()

        students = Student.objects.filter(school=school, is_active=True)
        guardians_created = 0
        fee_records_created = 0

        for i, student in enumerate(students):
            # 1. Primary Guardian
            has_primary = student.guardians.filter(is_primary=True).exists()
            if not has_primary:
                phone = random_uganda_phone()
                first = random.choice(FIRST_NAMES_MALE if i % 2 == 0 else FIRST_NAMES_FEMALE)
                last = student.last_name or random.choice(LAST_NAMES)
                rel = 'Father' if i % 2 == 0 else 'Mother'

                Guardian.objects.create(
                    student=student,
                    first_name=first,
                    last_name=last,
                    relationship=rel,
                    phone=phone,
                    phone_normalised=phone,
                    is_primary=True,
                    receives_sms=True,
                    preferred_language='en',
                )
                guardians_created += 1

            # 2. FeeRecord
            fee_rec = FeeRecord.all_objects.filter(student=student, academic_term=term).first()
            if not fee_rec:
                struct = structures_by_class.get(student.current_class_id) or default_struct
                total = struct.total_amount if struct else Decimal('450000')

                # Realistic demo distribution:
                # 30% cleared (paid full)
                # 45% partial payment (defaulter / balance)
                # 25% unpaid (zero paid)
                mod = i % 10
                if mod in (0, 1, 2):  # Cleared
                    paid = total
                elif mod in (3, 4, 5, 6):  # Partial
                    paid = Decimal(str(random.choice([150000, 200000, 250000, 300000])))
                    if paid >= total:
                        paid = total - Decimal('50000')
                else:  # Unpaid
                    paid = Decimal('0')

                fee_rec = FeeRecord.all_objects.create(
                    school=school,
                    student=student,
                    academic_term=term,
                    fee_structure=struct,
                    total_amount=total,
                    amount_paid=paid,
                    amount_waived=Decimal('0'),
                )
                fee_records_created += 1

                # If payment was made, record a Payment record
                if paid > 0:
                    Payment.all_objects.create(
                        school=school,
                        fee_record=fee_rec,
                        student=student,
                        method=random.choice(['cash', 'bank', 'momo']),
                        amount=paid,
                        status='completed',
                        receipt_number=f"REC-2026-{random.randint(10000, 99999)}",
                        payment_date=timezone.now(),
                        recorded_by=bursar,
                    )

        self.stdout.write(self.style.SUCCESS(
            f"Successfully updated! Created {guardians_created} missing guardians and {fee_records_created} missing FeeRecords."
        ))
