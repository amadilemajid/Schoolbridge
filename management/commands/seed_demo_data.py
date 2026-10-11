"""
Management command: seed_demo_data
Populates the database with realistic demo data for all features:
  - EPIC-A: WhatsApp parent self-service (TIMETABLE, RESULTS, PAY, ATTEND, MENU, LANG)
  - EPIC-B: Voice broadcasts and PDF report card distribution
  - EPIC-C: Smart fee collection, escalations, payment links, instalments

Usage:
    python manage.py seed_demo_data
    python manage.py seed_demo_data --reset   (wipe existing demo data first)

After seeding:
    School WhatsApp number: +256700000001
    Director login: director@stmarys.ug / Demo@12345
    Bursar login:   bursar@stmarys.ug  / Demo@12345
    Teacher login:  teacher@stmarys.ug / Demo@12345
"""
import random
from datetime import date, timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.utils import timezone


# ---------------------------------------------------------------------------
# Realistic Ugandan data pools
# ---------------------------------------------------------------------------
FIRST_NAMES_MALE = [
    'Brian', 'Ronald', 'David', 'Emmanuel', 'Joseph', 'John',
    'Michael', 'Samuel', 'Peter', 'Robert', 'Andrew', 'Moses',
    'Daniel', 'Paul', 'Simon', 'Ivan', 'Godfrey', 'Patrick',
]
FIRST_NAMES_FEMALE = [
    'Mary', 'Grace', 'Anita', 'Sharon', 'Christine', 'Doreen',
    'Harriet', 'Prossy', 'Lydia', 'Stella', 'Brenda', 'Juliet',
    'Racheal', 'Esther', 'Faith', 'Miriam', 'Agnes', 'Irene',
]
LAST_NAMES = [
    'Mukasa', 'Ssemakula', 'Namukasa', 'Nambooze', 'Kiggundu',
    'Ssebunya', 'Nakamya', 'Lwanga', 'Nanteza', 'Wasswa',
    'Nalwanga', 'Kizza', 'Mutebi', 'Babirye', 'Ssebbale',
    'Namusoke', 'Wamala', 'Nakirya', 'Kagwa', 'Sentongo',
]
GUARDIAN_RELATIONSHIPS = ['Father', 'Mother', 'Uncle', 'Aunt', 'Guardian']

# MTN (+25676x / +25677x) and Airtel (+25670x / +25675x) prefixes
PHONE_PREFIXES = ['0700', '0701', '0702', '0703', '0704',
                  '0750', '0751', '0752', '0762', '0772',
                  '0776', '0777', '0778', '0779']


def random_phone():
    prefix = random.choice(PHONE_PREFIXES)
    return prefix + str(random.randint(100000, 999999))


def normalise_phone(phone):
    phone = phone.strip()
    if phone.startswith('0'):
        return '+256' + phone[1:]
    return phone


class Command(BaseCommand):
    help = 'Seed the database with realistic demo data for all SchoolBridge features.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--reset', action='store_true',
            help='Delete existing demo school data before seeding.'
        )

    def handle(self, *args, **options):
        self.stdout.write(self.style.MIGRATE_HEADING('\n🌱  SchoolBridge Demo Data Seeder\n'))

        if options['reset']:
            self._reset()

        school = self._seed_school()
        director, bursar, teacher = self._seed_users(school)
        year, term1, term2 = self._seed_academic_calendar(school, director)
        classes = self._seed_classes(school, teacher)
        students = self._seed_students(school, classes)
        self._seed_fee_structures(school, term1, classes, bursar)
        self._seed_fee_records_and_payments(school, term1, students, bursar)
        self._seed_attendance(school, term1, students, teacher)
        self._seed_timetables(school, classes, director)
        self._seed_results(school, term1, students, classes)
        self._seed_momo_config(school)
        self._seed_broadcast_media(school, director)
        self._seed_escalations(school, term1)
        self._seed_message_templates(school)

        self.stdout.write(self.style.SUCCESS(
            '\n✅  Demo data seeded successfully!\n\n'
            '   School WhatsApp: +256700000001\n'
            '   Director:  director@stmarys.ug  /  Demo@12345\n'
            '   Bursar:    bursar@stmarys.ug    /  Demo@12345\n'
            '   Teacher:   teacher@stmarys.ug   /  Demo@12345\n'
            f'   Students:  {len(students)} created across {len(classes)} classes\n'
            '   MoMo:      Sandbox credentials seeded\n'
        ))

    # -----------------------------------------------------------------------
    def _reset(self):
        from schools.models import School
        self.stdout.write('  🗑️  Resetting existing demo school...')
        School.objects.filter(slug='st-marys-kampala-demo').delete()
        self.stdout.write('  ✓  Done.\n')

    # -----------------------------------------------------------------------
    def _seed_school(self):
        from schools.models import School
        school, created = School.objects.get_or_create(
            slug='st-marys-kampala-demo',
            defaults={
                'name': "St. Mary's College Kampala (Demo)",
                'district': 'Kampala',
                'sub_county': 'Rubaga',
                'address': 'Plot 12 Rubaga Road, Kampala',
                'phone': '+256700000001',
                'email': 'admin@stmarys.ug',
                'whatsapp_number': '+256700000001',
                'school_type': 'combined',
                'registration_number': 'MoE/PRI/KLA/2024/001',
                'default_language': 'en',
                'timezone': 'Africa/Kampala',
                'onboarded_by': 'seed_demo_data',
            }
        )
        verb = 'Created' if created else 'Found existing'
        self.stdout.write(f"  🏫  {verb} school: {school.name}")
        return school

    # -----------------------------------------------------------------------
    def _seed_users(self, school):
        from authentication.models import User
        users = []
        configs = [
            ('director@stmarys.ug', 'Demo@12345', 'director', 'Sarah', 'Namusoke'),
            ('bursar@stmarys.ug',   'Demo@12345', 'bursar',   'James', 'Ssebunya'),
            ('teacher@stmarys.ug',  'Demo@12345', 'teacher',  'Ruth',  'Nakamya'),
        ]
        for email, pwd, role, first, last in configs:
            user, created = User.objects.get_or_create(
                email=email,
                defaults={
                    'role': role, 'school': school,
                    'first_name': first, 'last_name': last,
                    'is_active': True,
                }
            )
            if created:
                user.set_password(pwd)
                user.save(update_fields=['password'])
            users.append(user)
            verb = 'Created' if created else 'Found'
            self.stdout.write(f"  👤  {verb} {role}: {email}")
        return users[0], users[1], users[2]

    # -----------------------------------------------------------------------
    def _seed_academic_calendar(self, school, director):
        from schools.models import AcademicYear, AcademicTerm

        year_obj, _ = AcademicYear.objects.get_or_create(
            school=school, year=2026,
            defaults={'is_current': True}
        )
        self.stdout.write(f"  📅  Academic year 2026")

        today = date.today()
        term1, created1 = AcademicTerm.objects.get_or_create(
            school=school, academic_year=year_obj, term_number=1,
            defaults={
                'name': 'Term 1 2026',
                'start_date': date(2026, 2, 3),
                'end_date': date(2026, 5, 30),
                'fee_deadline': date(2026, 3, 15),
                'is_current': True,
                'is_active': True,
                'activated_at': timezone.now(),
                'activated_by': director,
            }
        )

        term2, created2 = AcademicTerm.objects.get_or_create(
            school=school, academic_year=year_obj, term_number=2,
            defaults={
                'name': 'Term 2 2026',
                'start_date': date(2026, 6, 2),
                'end_date': date(2026, 9, 26),
                'fee_deadline': date(2026, 7, 10),
                'is_current': False,
                'is_active': False,
            }
        )
        self.stdout.write(f"  📅  Terms seeded: Term 1 (current, active), Term 2")
        return year_obj, term1, term2

    # -----------------------------------------------------------------------
    def _seed_classes(self, school, teacher):
        from students.models import ClassGroup
        class_defs = [
            ('P.5 East', 'P5', 'East'),
            ('P.6 East', 'P6', 'East'),
            ('P.7 East', 'P7', 'East'),
            ('P.7 West', 'P7', 'West'),
            ('S.1 A',    'S1', 'A'),
            ('S.4 A',    'S4', 'A'),
        ]
        classes = []
        for name, level, stream in class_defs:
            cg, created = ClassGroup.all_objects.get_or_create(
                school=school, name=name,
                defaults={'level': level, 'stream': stream, 'form_teacher': teacher}
            )
            classes.append(cg)
        self.stdout.write(f"  🏫  {len(classes)} classes seeded")
        return classes

    # -----------------------------------------------------------------------
    def _seed_students(self, school, classes):
        from students.models import Student, Guardian

        # 8 students per class = 48 students total
        students = []
        phone_pool = set()

        for cls in classes:
            for i in range(8):
                gender = 'M' if i % 2 == 0 else 'F'
                first = (random.choice(FIRST_NAMES_MALE) if gender == 'M'
                         else random.choice(FIRST_NAMES_FEMALE))
                last = random.choice(LAST_NAMES)

                student_id = Student.generate_student_id(school)
                student, created = Student.all_objects.get_or_create(
                    school=school,
                    student_id=student_id,
                    defaults={
                        'first_name': first,
                        'last_name': last,
                        'gender': gender,
                        'current_class': cls,
                        'admission_date': date(2024, 2, 5),
                        'academic_year_admitted': 2024,
                        'is_active': True,
                    }
                )
                students.append(student)

                # Primary guardian
                if not student.guardians.filter(is_primary=True).exists():
                    raw = random_phone()
                    while raw in phone_pool:
                        raw = random_phone()
                    phone_pool.add(raw)
                    norm = normalise_phone(raw)
                    lang = random.choice(['en', 'en', 'en', 'lg'])  # 75% English
                    Guardian.objects.create(
                        student=student,
                        first_name=random.choice(FIRST_NAMES_MALE),
                        last_name=last,
                        relationship=random.choice(['Father', 'Mother']),
                        phone=raw,
                        phone_normalised=norm,
                        is_primary=True,
                        receives_sms=True,
                        preferred_language=lang,
                    )

        # Create 2 sibling pairs for sibling-aggregation feature (EPIC-C)
        if len(students) >= 4:
            students[0].siblings.add(students[1])
            students[2].siblings.add(students[3])

        self.stdout.write(f"  👨‍🎓  {len(students)} students seeded with guardians")
        return students

    # -----------------------------------------------------------------------
    def _seed_fee_structures(self, school, term, classes, bursar):
        from payments.models import FeeStructure, FeeStructureItem

        for cls in classes:
            struct, created = FeeStructure.all_objects.get_or_create(
                school=school, academic_term=term, class_group=cls,
                defaults={
                    'name': f'{cls.name} Term 1 2026 Fees',
                    'is_active': True,
                    'created_by': bursar,
                }
            )
            if created:
                items = [
                    ('Tuition', 350000),
                    ('Lunch',   120000),
                    ('Activity',  30000),
                    ('Medical',   20000),
                ]
                for item_name, amount in items:
                    FeeStructureItem.objects.create(
                        fee_structure=struct,
                        name=item_name,
                        amount=Decimal(amount),
                        is_mandatory=(item_name != 'Activity'),
                    )

        self.stdout.write(f"  💰  Fee structures seeded for {len(classes)} classes")

    # -----------------------------------------------------------------------
    def _seed_fee_records_and_payments(self, school, term, students, bursar):
        from payments.models import FeeStructure, FeeRecord, Payment

        # Payment scenarios: fully paid, partial, defaulter
        scenarios = ['full', 'full', 'partial', 'partial', 'partial', 'zero', 'zero', 'zero']
        today = timezone.now()
        records_created = 0
        payments_created = 0

        for i, student in enumerate(students):
            struct = FeeStructure.all_objects.filter(
                school=school, academic_term=term, class_group=student.current_class
            ).first()
            if not struct:
                continue

            total = struct.total_amount
            record, rec_created = FeeRecord.all_objects.get_or_create(
                student=student, academic_term=term,
                defaults={
                    'school': school,
                    'fee_structure': struct,
                    'total_amount': Decimal(total),
                    'amount_paid': Decimal(0),
                }
            )
            if rec_created:
                records_created += 1

            scenario = scenarios[i % len(scenarios)]
            if scenario == 'full' and record.amount_paid < record.total_amount:
                paid = int(record.total_amount)
                Payment.all_objects.get_or_create(
                    school=school, student=student, fee_record=record,
                    receipt_number=f'RCP-{i+1:04d}',
                    defaults={
                        'method': 'mtn_momo',
                        'amount': Decimal(paid),
                        'status': 'completed',
                        'payment_date': today - timedelta(days=random.randint(5, 30)),
                        'recorded_by': bursar,
                    }
                )
                FeeRecord.all_objects.filter(pk=record.pk).update(amount_paid=Decimal(paid))
                payments_created += 1

            elif scenario == 'partial' and record.amount_paid == 0:
                paid = random.choice([150000, 200000, 250000])
                Payment.all_objects.get_or_create(
                    school=school, student=student, fee_record=record,
                    receipt_number=f'RCP-{i+100:04d}',
                    defaults={
                        'method': random.choice(['cash', 'mtn_momo']),
                        'amount': Decimal(paid),
                        'status': 'completed',
                        'payment_date': today - timedelta(days=random.randint(10, 45)),
                        'recorded_by': bursar,
                    }
                )
                FeeRecord.all_objects.filter(pk=record.pk).update(amount_paid=Decimal(paid))
                payments_created += 1
            # zero: no payment — defaulter

        self.stdout.write(
            f"  📋  {records_created} fee records + {payments_created} payments seeded"
        )

    # -----------------------------------------------------------------------
    def _seed_attendance(self, school, term, students, teacher):
        from attendance.models import AttendanceRecord

        today = date.today()
        records_created = 0

        for student in students:
            # Seed last 20 school days
            for day_offset in range(1, 21):
                att_date = today - timedelta(days=day_offset)
                if att_date.weekday() >= 5:  # skip weekends
                    continue
                if att_date < term.start_date:
                    continue

                # 85% present, 10% absent, 5% late
                rand = random.random()
                if rand < 0.85:
                    status = 'present'
                elif rand < 0.95:
                    status = 'absent'
                else:
                    status = 'late'

                _, created = AttendanceRecord.all_objects.get_or_create(
                    student=student, date=att_date,
                    defaults={
                        'school': school,
                        'class_group': student.current_class,
                        'academic_term': term,
                        'status': status,
                        'marked_by': teacher,
                        'alert_sent': status == 'absent',
                    }
                )
                if created:
                    records_created += 1

        self.stdout.write(f"  📊  {records_created} attendance records seeded")

    # -----------------------------------------------------------------------
    def _seed_timetables(self, school, classes, director):
        from schools.models import Timetable

        templates = {
            'P5': (
                "📚 *P.5 Timetable — Term 1 2026*\n\n"
                "Mon: English | Maths | Science | SST\n"
                "Tue: Maths | English | Art | Music\n"
                "Wed: Science | Maths | English | PE\n"
                "Thu: SST | English | Maths | CRE\n"
                "Fri: English | Science | Luganda | Library\n\n"
                "⏰ School: 8:00am–4:00pm"
            ),
            'P6': (
                "📚 *P.6 Timetable — Term 1 2026*\n\n"
                "Mon: English | Maths | Science | SST\n"
                "Tue: Maths | English | ICT | Music\n"
                "Wed: Science | Maths | English | PE\n"
                "Thu: SST | English | Maths | CRE\n"
                "Fri: English | Science | Luganda | Library\n\n"
                "⏰ School: 8:00am–4:30pm"
            ),
            'P7': (
                "📚 *P.7 Timetable — Term 1 2026*\n\n"
                "Mon: English | Maths | Science | SST\n"
                "Tue: Maths | English | ICT | Music\n"
                "Wed: Science | Maths | English | PE\n"
                "Thu: SST | English | Maths | CRE\n"
                "Fri: English | Science | Luganda | Revision\n\n"
                "⏰ School: 7:30am–5:00pm | Prep: 5:00–7:00pm"
            ),
            'S1': (
                "📚 *S.1 Timetable — Term 1 2026*\n\n"
                "Mon: Maths | Physics | English | Biology\n"
                "Tue: Chemistry | Maths | History | CRE\n"
                "Wed: Physics | English | Geography | PE\n"
                "Thu: Biology | Maths | Chemistry | Art\n"
                "Fri: English | Physics | Economics | Library\n\n"
                "⏰ School: 7:30am–5:30pm | Prep: 6:00–8:30pm"
            ),
            'S4': (
                "📚 *S.4 Timetable — Term 1 2026*\n\n"
                "Mon: Maths | Physics | English | Biology\n"
                "Tue: Chemistry | Maths | History | CRE\n"
                "Wed: Physics | English | Geography | PE\n"
                "Thu: Biology | Maths | Chemistry | Economics\n"
                "Fri: English | Physics | Past Papers | Library\n\n"
                "⏰ School: 7:30am–5:30pm | Prep: 6:00–9:00pm"
            ),
        }

        count = 0
        for cls in classes:
            level_key = cls.level[:2]
            content = templates.get(level_key, templates['P7'])
            _, created = Timetable.objects.get_or_create(
                school=school, class_group=cls, is_active=True,
                defaults={
                    'title': f'{cls.name} Timetable',
                    'content': content,
                    'created_by': director,
                }
            )
            if created:
                count += 1

        self.stdout.write(f"  📅  {count} timetables seeded")

    # -----------------------------------------------------------------------
    def _seed_results(self, school, term, students, classes):
        from results.models import Subject, Assessment, AssessmentMark, TermResult

        subjects_by_level = {
            'P': ['English', 'Mathematics', 'Science', 'Social Studies'],
            'S': ['English', 'Mathematics', 'Physics', 'Biology', 'Chemistry'],
        }
        results_created = 0

        for cls in classes:
            level_type = 'S' if cls.level.startswith('S') else 'P'
            subject_names = subjects_by_level[level_type]
            class_students = [s for s in students if s.current_class == cls]
            if not class_students:
                continue

            for subj_name in subject_names:
                subj, _ = Subject.objects.get_or_create(
                    school=school, name=subj_name,
                    defaults={'code': subj_name[:4].upper(), 'class_levels': cls.level}
                )

                assessment, _ = Assessment.objects.get_or_create(
                    school=school, academic_term=term, class_group=cls, subject=subj,
                    name='End of Term Exam',
                    defaults={
                        'assessment_type': 'eot',
                        'max_marks': 100,
                        'weight': Decimal('1.0'),
                        'is_locked': True,
                        'locked_at': timezone.now(),
                    }
                )

                for student in class_students:
                    marks = random.randint(35, 95)
                    AssessmentMark.objects.get_or_create(
                        assessment=assessment, student=student,
                        defaults={'marks_obtained': Decimal(marks), 'is_absent': False}
                    )

            # TermResult per student
            for rank, student in enumerate(sorted(class_students,
                                                   key=lambda s: s.last_name), 1):
                avg = Decimal(random.randint(45, 88))
                TermResult.objects.get_or_create(
                    school=school, student=student, academic_term=term, class_group=cls,
                    defaults={
                        'total_marks': avg * len(subject_names),
                        'average_marks': avg,
                        'class_rank': rank,
                        'total_students': len(class_students),
                        'class_average': Decimal(62),
                        'division': 'II' if avg >= 60 else 'III',
                        'aggregate': random.randint(8, 24),
                        'parent_notified': False,
                    }
                )
                results_created += 1

        self.stdout.write(f"  📝  {results_created} term results seeded")

    # -----------------------------------------------------------------------
    def _seed_momo_config(self, school):
        from schools.models import SchoolMoMoConfig
        config, created = SchoolMoMoConfig.objects.get_or_create(
            school=school, provider='mtn',
            defaults={
                'mtn_environment': 'sandbox',
                'mtn_collection_api_user': 'demo_api_user_placeholder',
                'mtn_collection_api_key': 'demo_api_key_placeholder',
                'mtn_subscription_key': 'demo_sub_key_placeholder',
                'webhook_signing_key': 'demo_webhook_signing_key_32chars!!',
                'merchant_name': "St. Mary's College MoMo",
                'merchant_phone': '+256772000001',
                'is_active': True,
            }
        )
        verb = 'Created' if created else 'Found'
        self.stdout.write(f"  📱  {verb} MTN MoMo sandbox config")

    # -----------------------------------------------------------------------
    def _seed_broadcast_media(self, school, director):
        from messaging.models import BroadcastMedia
        from django.utils import timezone as tz

        entries = [
            {
                'media_type': 'voice',
                'original_filename': 'school_announcement.ogg',
                'file_size_bytes': 48000,
                'meta_upload_status': 'uploaded',
                'whatsapp_media_id': 'demo_meta_audio_id_001',
                'description': 'Term 1 opening announcement to all parents',
            },
            {
                'media_type': 'document',
                'original_filename': 'term1_circular_2026.pdf',
                'file_size_bytes': 120000,
                'meta_upload_status': 'uploaded',
                'whatsapp_media_id': 'demo_meta_doc_id_002',
                'description': 'Term 1 2026 school circular for all parents',
            },
            {
                'media_type': 'voice',
                'original_filename': 'fee_reminder_broadcast.ogg',
                'file_size_bytes': 32000,
                'meta_upload_status': 'pending',
                'whatsapp_media_id': '',
                'description': 'Fee deadline reminder voice note',
            },
        ]

        count = 0
        for entry in entries:
            _, created = BroadcastMedia.objects.get_or_create(
                school=school,
                original_filename=entry['original_filename'],
                defaults={
                    'media_file': f"broadcast_media/{entry['original_filename']}",
                    'media_type': entry['media_type'],
                    'file_size_bytes': entry['file_size_bytes'],
                    'meta_upload_status': entry['meta_upload_status'],
                    'whatsapp_media_id': entry['whatsapp_media_id'],
                    'description': entry['description'],
                    'expires_at': tz.now() + timedelta(days=30),
                    'uploaded_by': director,
                }
            )
            if created:
                count += 1

        self.stdout.write(f"  🔊  {count} BroadcastMedia records seeded")

    # -----------------------------------------------------------------------
    def _seed_escalations(self, school, term):
        try:
            from payments.escalation_models import ReminderEscalation
            from payments.models import FeeRecord

            # Escalate the 3 worst defaulters
            defaulters = FeeRecord.all_objects.filter(
                school=school, academic_term=term, amount_paid=0
            ).select_related('student')[:3]

            count = 0
            for record in defaulters:
                _, created = ReminderEscalation.objects.get_or_create(
                    school=school, fee_record=record,
                    defaults={
                        'student': record.student,
                        'current_level': 2,
                        'escalation_count': 2,
                        'last_escalated_at': timezone.now() - timedelta(days=7),
                        'next_escalation_at': timezone.now() + timedelta(days=7),
                        'is_active': True,
                    }
                )
                if created:
                    count += 1

            self.stdout.write(f"  🚨  {count} escalation records seeded for defaulters")
        except Exception as e:
            self.stdout.write(
                self.style.WARNING(f"  ⚠️  Could not seed escalations: {e}")
            )

    # -----------------------------------------------------------------------
    def _seed_message_templates(self, school):
        from messaging.models import MessageTemplate

        templates = [
            {
                'template_type': 'payment_receipt',
                'name': 'Payment Receipt',
                'language': 'en',
                'body': (
                    "✅ *Payment Received*\n\n"
                    "Student: {student_name}\n"
                    "Amount: UGX {amount}\n"
                    "Balance: UGX {balance}\n\n"
                    "Thank you! Reply BALANCE for details."
                ),
                'is_active': True,
            },
            {
                'template_type': 'fee_reminder',
                'name': 'Fee Reminder',
                'language': 'en',
                'body': (
                    "⚠️ *Fee Reminder*\n\n"
                    "Dear Parent, fees for {student_name} are due.\n"
                    "Balance: UGX {balance}\n"
                    "Deadline: {deadline}\n\n"
                    "Reply PAY {amount} to pay via MoMo."
                ),
                'is_active': True,
            },
            {
                'template_type': 'absence_alert',
                'name': 'Absence Alert',
                'language': 'en',
                'body': (
                    "⚠️ *Absence Alert*\n\n"
                    "{student_name} was marked absent today.\n"
                    "Please contact the school if this is an error."
                ),
                'is_active': True,
            },
            {
                'template_type': 'report_card_ready',
                'name': 'Report Card Ready',
                'language': 'en',
                'body': (
                    "📋 *Report Card Available*\n\n"
                    "The report card for {student_name} is attached.\n"
                    "Please review and sign for the next term."
                ),
                'is_active': True,
            },
        ]

        count = 0
        for tmpl in templates:
            _, created = MessageTemplate.objects.get_or_create(
                school=school,
                template_type=tmpl['template_type'],
                language=tmpl['language'],
                defaults=tmpl,
            )
            if created:
                count += 1

        self.stdout.write(f"  📨  {count} message templates seeded")
