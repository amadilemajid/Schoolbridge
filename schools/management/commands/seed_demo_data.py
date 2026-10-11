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
        self.stdout.write(self.style.MIGRATE_HEADING('\n[SEED]  SchoolBridge Demo Data Seeder\n'))

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
        self._seed_structured_timetables(school, term1, classes, teacher, director)
        self._seed_results(school, term1, students, classes)
        self._seed_risk_intelligence(school, term1, students)
        self._seed_self_onboarding()
        self._seed_momo_config(school)
        self._seed_broadcast_media(school, director)
        self._seed_escalations(school, term1)
        self._seed_message_templates(school)

        self.stdout.write(self.style.SUCCESS(
            '\n[OK]  Demo data seeded successfully!\n\n'
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
        from onboarding.models import SchoolRegistrationRequest
        self.stdout.write('  [RESET]  Resetting existing demo school and onboarding requests...')
        School.objects.filter(slug='st-marys-kampala-demo').delete()
        SchoolRegistrationRequest.objects.filter(school_name__contains='(Demo Onboarding)').delete()
        self.stdout.write('  [DONE]\n')

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
        self.stdout.write(f"  [SCHOOL]  {verb} school: {school.name}")
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
            self.stdout.write(f"  [USER]  {verb} {role}: {email}")
        return users[0], users[1], users[2]

    # -----------------------------------------------------------------------
    def _seed_academic_calendar(self, school, director):
        from schools.models import AcademicYear, AcademicTerm

        year_obj, _ = AcademicYear.objects.get_or_create(
            school=school, year=2026,
            defaults={'is_current': True}
        )
        self.stdout.write("  [CAL]  Academic year 2026")

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
        self.stdout.write("  [CAL]  Terms seeded: Term 1 (current, active), Term 2")
        return year_obj, term1, term2

    # -----------------------------------------------------------------------
    def _seed_classes(self, school, teacher):
        from students.models import ClassGroup
        class_defs = [
            ('P.1 East', 'P1', 'East'),
            ('P.1 West', 'P1', 'West'),
            ('P.2 East', 'P2', 'East'),
            ('P.2 West', 'P2', 'West'),
            ('P.3 East', 'P3', 'East'),
            ('P.3 West', 'P3', 'West'),
            ('P.4 East', 'P4', 'East'),
            ('P.4 West', 'P4', 'West'),
            ('P.5 East', 'P5', 'East'),
            ('P.5 West', 'P5', 'West'),
            ('P.6 East', 'P6', 'East'),
            ('P.6 West', 'P6', 'West'),
            ('P.7 East', 'P7', 'East'),
            ('P.7 West', 'P7', 'West'),
            ('S.1 A',    'S1', 'A'),
            ('S.1 B',    'S1', 'B'),
            ('S.2 A',    'S2', 'A'),
            ('S.2 B',    'S2', 'B'),
            ('S.3 A',    'S3', 'A'),
            ('S.3 B',    'S3', 'B'),
            ('S.4 A',    'S4', 'A'),
            ('S.4 B',    'S4', 'B'),
            ('S.5 Science', 'S5', 'Science'),
            ('S.5 Arts',    'S5', 'Arts'),
            ('S.6 Science', 'S6', 'Science'),
            ('S.6 Arts',    'S6', 'Arts'),
        ]
        classes = []
        for name, level, stream in class_defs:
            cg, created = ClassGroup.all_objects.get_or_create(
                school=school, name=name,
                defaults={'level': level, 'stream': stream, 'form_teacher': teacher}
            )
            classes.append(cg)
        self.stdout.write(f"  [CLASS]  {len(classes)} classes seeded")
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

        self.stdout.write(f"  [STUDENTS]  {len(students)} students seeded with guardians")
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

        self.stdout.write(f"  [FEES]  Fee structures seeded for {len(classes)} classes")

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
            f"  [PAY]  {records_created} fee records + {payments_created} payments seeded"
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

        self.stdout.write(f"  [ATTEND]  {records_created} attendance records seeded")

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

        self.stdout.write(f"  [TIMETABLE]  {count} timetables seeded")

    # -----------------------------------------------------------------------
    def _seed_results(self, school, term, students, classes):
        from results.models import Subject, Assessment, AssessmentMark, TermResult

        for cls in classes:
            lvl = cls.level.upper()
            stream = (cls.stream or '').strip().lower()
            name = (cls.name or '').strip().lower()

            if lvl in ('S5', 'S6'):
                if 'sci' in stream or 'science' in name:
                    subject_names = ['Pure Mathematics', 'Physics', 'Chemistry', 'Biology', 'General Paper']
                else:
                    subject_names = ['History & Political Education', 'Economics', 'Geography', 'Literature in English', 'General Paper']
            elif lvl.startswith('S'):
                subject_names = ['English', 'Mathematics', 'Physics', 'Biology', 'Chemistry']
            else:
                subject_names = ['English', 'Mathematics', 'Science', 'Social Studies']

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

        self.stdout.write(f"  [RESULTS]  {results_created} term results seeded")

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
        self.stdout.write(f"  [MOMO]  {verb} MTN MoMo sandbox config")

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

        self.stdout.write(f"  [MEDIA]  {count} BroadcastMedia records seeded")

    # -----------------------------------------------------------------------
    def _seed_escalations(self, school, term):
        try:
            from payments.escalation_models import ReminderEscalation
            from payments.models import FeeRecord
            from datetime import date, timedelta

            # Escalate the 3 worst defaulters across 3 levels each
            defaulters = FeeRecord.all_objects.filter(
                school=school, academic_term=term, amount_paid=0
            ).select_related('student')[:3]

            count = 0
            today = date.today()
            for record in defaulters:
                for level in [1, 2, 3]:
                    _, created = ReminderEscalation.objects.get_or_create(
                        fee_record=record, level=level,
                        defaults={
                            'school': school,
                            'academic_term': term,
                            'scheduled_date': today - timedelta(days=(3 - level) * 7),
                            'status': 'sent' if level < 3 else 'scheduled',
                            'director_notified': level >= 3,
                            'bursar_notified': level >= 4,
                        }
                    )
                    if created:
                        count += 1

            self.stdout.write(f"  [ESCALATE]  {count} escalation records seeded for defaulters")
        except Exception as e:
            self.stdout.write(
                self.style.WARNING(f"  [WARN]  Could not seed escalations: {e}")
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

        self.stdout.write(f"  [TEMPLATES]  {count} message templates seeded")

    # -----------------------------------------------------------------------
    def _seed_structured_timetables(self, school, term, classes, teacher, director):
        from timetable.models import TimetableVersion, TimetableSlot, SubstitutionRecord
        from results.models import Subject
        from authentication.models import User
        from timetable.services import TimetableService
        from schools.models import Timetable
        import datetime

        self.stdout.write('  [TIMETABLE] Seeding structured timetables...')

        # Ensure complete Ugandan subjects exist
        PRIMARY_LEVELS = "P1,P2,P3,P4,P5,P6,P7"
        OLEVEL_LEVELS = "S1,S2,S3,S4"
        ALEVEL_LEVELS = "S5,S6"

        subjects_spec = [
            {'name': 'English', 'code': 'ENG', 'class_levels': f"{PRIMARY_LEVELS},{OLEVEL_LEVELS}"},
            {'name': 'Mathematics', 'code': 'MATH', 'class_levels': f"{PRIMARY_LEVELS},{OLEVEL_LEVELS}"},
            {'name': 'Science', 'code': 'SCIE', 'class_levels': PRIMARY_LEVELS},
            {'name': 'Social Studies', 'code': 'SOCI', 'class_levels': PRIMARY_LEVELS},
            {'name': 'Christian Religious Education (CRE)', 'code': 'CRE', 'class_levels': f"{PRIMARY_LEVELS},{OLEVEL_LEVELS}"},
            {'name': 'Physical Education', 'code': 'PE', 'class_levels': f"{PRIMARY_LEVELS},{OLEVEL_LEVELS}"},
            {'name': 'Physics', 'code': 'PHYS', 'class_levels': f"{OLEVEL_LEVELS},{ALEVEL_LEVELS}"},
            {'name': 'Chemistry', 'code': 'CHEM', 'class_levels': f"{OLEVEL_LEVELS},{ALEVEL_LEVELS}"},
            {'name': 'Biology', 'code': 'BIOL', 'class_levels': f"{OLEVEL_LEVELS},{ALEVEL_LEVELS}"},
            {'name': 'Geography', 'code': 'GEO', 'class_levels': f"{OLEVEL_LEVELS},{ALEVEL_LEVELS}"},
            {'name': 'History & Political Education', 'code': 'HIST', 'class_levels': f"{OLEVEL_LEVELS},{ALEVEL_LEVELS}"},
            {'name': 'Agriculture', 'code': 'AGRI', 'class_levels': f"{OLEVEL_LEVELS},{ALEVEL_LEVELS}"},
            {'name': 'Computer Studies / ICT', 'code': 'ICT', 'class_levels': OLEVEL_LEVELS},
            {'name': 'Literature in English', 'code': 'LIT', 'class_levels': f"{OLEVEL_LEVELS},{ALEVEL_LEVELS}"},
            {'name': 'Entrepreneurship', 'code': 'ENT', 'class_levels': f"{OLEVEL_LEVELS},{ALEVEL_LEVELS}"},
            {'name': 'Fine Art', 'code': 'ART', 'class_levels': f"{OLEVEL_LEVELS},{ALEVEL_LEVELS}"},
            {'name': 'General Paper', 'code': 'GP', 'class_levels': ALEVEL_LEVELS},
            {'name': 'Subsidiary ICT', 'code': 'SICT', 'class_levels': ALEVEL_LEVELS},
            {'name': 'Pure Mathematics', 'code': 'PMTC', 'class_levels': ALEVEL_LEVELS},
            {'name': 'Economics', 'code': 'ECON', 'class_levels': ALEVEL_LEVELS},
            {'name': 'Divinity', 'code': 'DIV', 'class_levels': ALEVEL_LEVELS},
        ]

        subject_map = {}
        for spec in subjects_spec:
            subj, _ = Subject.objects.get_or_create(
                school=school, name=spec['name'],
                defaults={'code': spec['code'], 'class_levels': spec['class_levels'], 'is_active': True}
            )
            subj.code = spec['code']
            subj.class_levels = spec['class_levels']
            subj.is_active = True
            subj.save()
            subject_map[subj.name] = subj

        # Available teachers for rotation to prevent conflicts
        teachers = list(User.objects.filter(school=school, role__in=['teacher', 'director']))
        if not teachers:
            teachers = [teacher]

        def get_pool_for_class(cls_group):
            lvl = cls_group.level.upper()
            stream = (cls_group.stream or '').strip().lower()
            name = (cls_group.name or '').strip().lower()
            if lvl in ('S5', 'S6'):
                if 'sci' in stream or 'science' in name:
                    return [
                        subject_map.get('Pure Mathematics') or subject_map.get('Mathematics'),
                        subject_map.get('Physics'),
                        subject_map.get('Chemistry'),
                        subject_map.get('Biology'),
                        subject_map.get('General Paper'),
                        subject_map.get('Subsidiary ICT'),
                    ]
                else:
                    return [
                        subject_map.get('History & Political Education'),
                        subject_map.get('Economics'),
                        subject_map.get('Geography'),
                        subject_map.get('Literature in English'),
                        subject_map.get('Divinity') or subject_map.get('Christian Religious Education (CRE)'),
                        subject_map.get('General Paper'),
                        subject_map.get('Subsidiary ICT'),
                    ]
            elif lvl.startswith('S'):
                return [
                    subject_map.get('English'),
                    subject_map.get('Mathematics'),
                    subject_map.get('Physics'),
                    subject_map.get('Chemistry'),
                    subject_map.get('Biology'),
                    subject_map.get('Geography'),
                    subject_map.get('History & Political Education'),
                    subject_map.get('Christian Religious Education (CRE)'),
                    subject_map.get('Computer Studies / ICT'),
                    subject_map.get('Agriculture'),
                ]
            else:
                return [
                    subject_map.get('English'),
                    subject_map.get('Mathematics'),
                    subject_map.get('Science'),
                    subject_map.get('Social Studies'),
                    subject_map.get('Christian Religious Education (CRE)'),
                    subject_map.get('Physical Education'),
                ]

        versions_count = 0
        slots_count = 0

        periods_data = [
            (1, datetime.time(8, 0), datetime.time(9, 0), 'lesson', 0),
            (2, datetime.time(9, 0), datetime.time(10, 0), 'lesson', 1),
            (3, datetime.time(10, 0), datetime.time(10, 30), 'break', None),
            (4, datetime.time(10, 30), datetime.time(11, 30), 'lesson', 2),
            (5, datetime.time(11, 30), datetime.time(12, 30), 'lesson', 3),
            (6, datetime.time(12, 30), datetime.time(13, 30), 'lunch', None),
            (7, datetime.time(13, 30), datetime.time(14, 30), 'lesson', 4),
            (8, datetime.time(14, 30), datetime.time(15, 30), 'study', None),
        ]

        class_idx = 0
        for cls in classes:
            class_idx += 1
            pool = [s for s in get_pool_for_class(cls) if s is not None]
            version, created = TimetableVersion.all_objects.get_or_create(
                school=school,
                class_group=cls,
                academic_term=term,
                version_number=1,
                defaults={
                    'is_active': True,
                    'effective_from': term.start_date,
                    'notes': f"Initial structured timetable version for {cls.name}",
                    'created_by': director
                }
            )
            if created:
                versions_count += 1

            for day in range(5):
                for period_num, start, end, stype, sub_offset in periods_data:
                    subj = None
                    sub_name = ""
                    teacher_user = None

                    if stype == 'lesson':
                        idx = (day * 2 + (sub_offset or 0)) % len(pool)
                        subj = pool[idx]
                        sub_name = subj.name
                        teacher_user = teachers[(class_idx + day + period_num) % len(teachers)]
                    elif stype == 'break':
                        sub_name = "Break"
                    elif stype == 'lunch':
                        sub_name = "Lunch"
                    elif stype == 'study':
                        sub_name = "Self Study"
                        teacher_user = teachers[(class_idx + day) % len(teachers)]

                    slot, slot_created = TimetableSlot.all_objects.get_or_create(
                        timetable_version=version,
                        day_of_week=day,
                        period_number=period_num,
                        defaults={
                            'school': school,
                            'start_time': start,
                            'end_time': end,
                            'subject': subj,
                            'subject_name': sub_name,
                            'teacher': teacher_user,
                            'room': f"Room {cls.name.replace('.', '')[:8]}",
                            'slot_type': stype,
                        }
                    )
                    if slot_created:
                        slots_count += 1

            # Sync to schools.Timetable for WhatsApp text
            try:
                whatsapp_text = TimetableService.format_for_whatsapp(cls, term)
                Timetable.objects.update_or_create(
                    school=school,
                    class_group=cls,
                    is_active=True,
                    defaults={
                        'content': whatsapp_text,
                        'title': f"{cls.name} — {term.name}",
                    }
                )
            except Exception:
                pass
            
            # Create a SubstitutionRecord for the first lesson slot of Monday in the current week
            mon_p1_slot = TimetableSlot.all_objects.filter(
                timetable_version=version,
                day_of_week=0,
                period_number=1
            ).first()
            
            if mon_p1_slot:
                today = datetime.date.today()
                days_since_monday = today.weekday()
                recent_monday = today - datetime.timedelta(days=days_since_monday)
                
                SubstitutionRecord.all_objects.get_or_create(
                    timetable_slot=mon_p1_slot,
                    date=recent_monday,
                    defaults={
                        'school': school,
                        'original_teacher': teacher,
                        'substitute_teacher': director,
                        'reason': "Teacher attending curriculum training in Kampala",
                        'created_by': director
                    }
                )

        self.stdout.write(f"  [TIMETABLE] Created {versions_count} versions, {slots_count} slots, and substitutions.")

    # -----------------------------------------------------------------------
    def _seed_risk_intelligence(self, school, term, students):
        from risk.models import RiskConfiguration, StudentRiskProfile, StudentRiskSnapshot
        from risk.services import RiskEvaluationEngine
        import datetime
        from decimal import Decimal

        self.stdout.write('  [RISK] Seeding At-Risk student engine data...')
        
        # Create RiskConfiguration
        config, created = RiskConfiguration.objects.get_or_create(
            school=school,
            defaults={
                'attendance_threshold': Decimal('75.00'),
                'fee_payment_ratio_threshold': Decimal('50.00'),
                'outstanding_balance_threshold': Decimal('100000'),
                'grace_period_days': 10,
                'enable_whatsapp_alerts': True,
                'enable_monday_briefing': True
            }
        )
        if not created:
            config.attendance_threshold = Decimal('75.00')
            config.fee_payment_ratio_threshold = Decimal('50.00')
            config.outstanding_balance_threshold = Decimal('100000')
            config.grace_period_days = 10
            config.save()
            
        # Run recalculation engine for the school to evaluate and cache the current state
        profiles = RiskEvaluationEngine.recalculate_school(school, term)
        self.stdout.write(f"  [RISK] Evaluated {len(profiles)} students for current term.")
        
        # Seed historical trends for the last 3 weeks
        today = datetime.date.today()
        weeks = [1, 2, 3]
        snapshots_count = 0
        
        for student in students:
            profile = StudentRiskProfile.all_objects.filter(student=student, academic_term=term).first()
            if not profile:
                continue
                
            base_score = profile.risk_score
            base_att = profile.attendance_rate or Decimal('90.00')
            base_pay = profile.fee_payment_ratio or Decimal('100.00')
            
            for w in weeks:
                snapshot_date = today - datetime.timedelta(weeks=w)
                
                # Deterministic pseudo-random variation based on student id
                variation = (student.id.int % 10) - 5
                att_val = max(Decimal('40.00'), min(Decimal('100.00'), base_att + Decimal(str(variation * w))))
                pay_val = max(Decimal('0.00'), min(Decimal('100.00'), base_pay - Decimal(str(variation * 5 * w))))
                
                factors = []
                score_contribs = []
                if att_val < config.attendance_threshold:
                    factors.append('low_attendance')
                    score_contribs.append(min(50, int((config.attendance_threshold - att_val) * 2)))
                if pay_val < config.fee_payment_ratio_threshold:
                    factors.append('fee_defaulter')
                    score_contribs.append(min(50, max(10, int(config.fee_payment_ratio_threshold - pay_val))))
                    
                risk_score = min(100, sum(score_contribs))
                if risk_score >= 70:
                    level = 'high'
                elif risk_score >= 40:
                    level = 'medium'
                else:
                    level = 'low'
                    
                StudentRiskSnapshot.all_objects.get_or_create(
                    student=student,
                    academic_term=term,
                    snapshot_date=snapshot_date,
                    defaults={
                        'school': school,
                        'attendance_rate': att_val,
                        'fee_payment_ratio': pay_val,
                        'risk_score': risk_score,
                        'risk_level': level,
                        'flagged_factors': factors,
                    }
                )
                snapshots_count += 1
                
        self.stdout.write(f"  [RISK] Seeded {snapshots_count} historical risk snapshots.")

    # -----------------------------------------------------------------------
    def _seed_self_onboarding(self):
        from onboarding.models import SchoolRegistrationRequest, SchoolProvisioningLog
        
        self.stdout.write('  [ONBOARDING] Seeding school self-onboarding requests and provisioning logs...')
        
        # 1. Seed completed request
        req_completed, created_comp = SchoolRegistrationRequest.objects.get_or_create(
            school_name="Mbarara High School (Demo Onboarding)",
            defaults={
                'admin_email': 'bursar@mbararahigh.ac.ug',
                'admin_first_name': 'Amos',
                'admin_last_name': 'Kaguta',
                'admin_phone': '+256772123456',
                'district': 'Mbarara',
                'sub_county': 'Kakoba',
                'school_type': 'secondary',
                'status': 'completed',
                'payload': {
                    'term_start': '2026-06-01',
                    'term_end': '2026-09-15',
                    'classes': ['S.1 A', 'S.2 A', 'S.3 A', 'S.4 A']
                }
            }
        )
        if created_comp:
            steps = [
                ("Validating request parameters", "success", "All fields validated successfully. Admin email is unique."),
                ("Creating database tenant schema", "success", "Database schema and tenant records created for schema mbarara_high."),
                ("Initializing default parameters", "success", "Academic year 2026 and Term 2 initialized."),
                ("Creating administrator user", "success", "User bursar@mbararahigh.ac.ug created with role director."),
                ("Completing provisioning transaction", "success", "Self-onboarding transaction committed successfully.")
            ]
            for step, status, details in steps:
                SchoolProvisioningLog.objects.create(
                    registration_request=req_completed,
                    step_name=step,
                    status=status,
                    details=details
                )
                
        # 2. Seed pending request
        req_pending, created_pend = SchoolRegistrationRequest.objects.get_or_create(
            school_name="Gombe High School (Demo Onboarding)",
            defaults={
                'admin_email': 'info@gombehigh.sc.ug',
                'admin_first_name': 'Farouk',
                'admin_last_name': 'Mugalu',
                'admin_phone': '+256701987654',
                'district': 'Butambala',
                'sub_county': 'Gombe',
                'school_type': 'combined',
                'status': 'pending',
                'payload': {
                    'term_start': '2026-06-01',
                    'term_end': '2026-09-15',
                    'classes': ['P.1', 'P.7', 'S.1', 'S.6']
                }
            }
        )
        
        # 3. Seed failed request
        req_failed, created_fail = SchoolRegistrationRequest.objects.get_or_create(
            school_name="Greenhill Academy Kampala (Demo Onboarding)",
            defaults={
                'admin_email': 'admin@greenhill.co.ug',
                'admin_first_name': 'Juliet',
                'admin_last_name': 'Mukasa',
                'admin_phone': '+256755443322',
                'district': 'Kampala',
                'sub_county': 'Nakawa',
                'school_type': 'primary',
                'status': 'failed',
                'payload': {
                    'term_start': '2026-06-01',
                    'term_end': '2026-09-15',
                    'classes': ['P.1', 'P.2', 'P.3']
                }
            }
        )
        if created_fail:
            steps = [
                ("Validating request parameters", "success", "All fields validated successfully. Admin email is unique."),
                ("Creating database tenant schema", "success", "Database schema and tenant records created."),
                ("Initializing default parameters", "failed", "Failed to initialize default classes: stream 'A' conflicts with default layout."),
            ]
            for step, status, details in steps:
                SchoolProvisioningLog.objects.create(
                    registration_request=req_failed,
                    step_name=step,
                    status=status,
                    details=details
                )
                
        self.stdout.write('  [ONBOARDING] Seeded onboarding registration requests and logs.')
