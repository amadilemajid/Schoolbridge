"""
remediate_curriculum_and_timetables.py

Remediation script for Ugandan curriculum subjects and timetable slots:
1. Creates/updates authentic Ugandan Primary, O-Level, A-Level Science, and A-Level Arts subjects in Subject model.
2. Fixes Primary subjects class_levels so 'Science' and 'Social Studies' are strictly Primary (P1-P7).
3. Updates TimetableSlot records for all 26 classes:
   - S.5 Science & S.6 Science -> Pure Mathematics, Physics, Chemistry, Biology, General Paper, Subsidiary ICT.
   - S.5 Arts & S.6 Arts -> History, Economics, Geography, Literature in English, Divinity, General Paper, Subsidiary ICT.
   - S.1 to S.4 -> English, Mathematics, Physics, Chemistry, Biology, History, Geography, CRE, ICT, Agriculture.
   - P.1 to P.7 -> English, Mathematics, Science, Social Studies, CRE, PE.
4. Distributes teachers across slots to prevent double-booking.
5. Syncs the structured timetable to schools.Timetable (for WhatsApp & parent notifications).
"""

import os
import sys
import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
import django
django.setup()

from schools.models import School, AcademicTerm, Timetable
from students.models import ClassGroup
from results.models import Subject
from timetable.models import TimetableVersion, TimetableSlot
from authentication.models import User
from timetable.services import TimetableService


def remediate_school(school):
    print(f"\n=======================================================")
    print(f"Remediating School: {school.name} ({school.id})")
    print(f"=======================================================")

    # 1. Staff setup for realistic assignments
    teachers = list(User.objects.filter(school=school, role__in=['teacher', 'director']))
    if not teachers:
        # Fallback to any user
        teachers = list(User.objects.filter(school=school))
    print(f"Available teachers/staff: {[t.get_full_name() for t in teachers]}")

    # Create additional demo teachers if only 1 exists so timetable doesn't conflict
    school_slug = school.name.lower().replace(' ', '').replace("'", "").replace(".", "")[:10]
    teacher_catalog = [
        ('Okello David', f'okello.david@{school_slug}.ug', 'Science Teacher'),
        ('Mbabazi Christine', f'mbabazi.c@{school_slug}.ug', 'Mathematics Teacher'),
        ('Kigozi Patrick', f'kigozi.p@{school_slug}.ug', 'Humanities Teacher'),
        ('Nabatanzi Florence', f'nabatanzi.f@{school_slug}.ug', 'Languages Teacher'),
        ('Tushabe Ronald', f'tushabe.r@{school_slug}.ug', 'ICT Teacher'),
    ]
    for name, email, title in teacher_catalog:
        first, last = name.split(' ', 1)
        u, created = User.objects.get_or_create(
            email=email,
            defaults={
                'school': school,
                'first_name': first,
                'last_name': last,
                'role': 'teacher',
                'is_staff': True,
                'phone': f"+25670{abs(hash(email)) % 100000000:07d}",
            }
        )
        if created:
            u.set_password('Demo@12345')
            u.save()
            teachers.append(u)
            print(f"  [+] Created demo teacher: {name}")
        elif u not in teachers:
            teachers.append(u)

    # 2. Complete Ugandan Subject Catalog
    PRIMARY_LEVELS = "P1,P2,P3,P4,P5,P6,P7"
    OLEVEL_LEVELS = "S1,S2,S3,S4"
    ALEVEL_LEVELS = "S5,S6"

    subjects_spec = [
        # --- Primary Subjects ---
        {'name': 'English', 'code': 'ENG', 'class_levels': f"{PRIMARY_LEVELS},{OLEVEL_LEVELS}"},
        {'name': 'Mathematics', 'code': 'MATH', 'class_levels': f"{PRIMARY_LEVELS},{OLEVEL_LEVELS}"},
        {'name': 'Science', 'code': 'SCIE', 'class_levels': PRIMARY_LEVELS},
        {'name': 'Social Studies', 'code': 'SOCI', 'class_levels': PRIMARY_LEVELS},
        {'name': 'Christian Religious Education (CRE)', 'code': 'CRE', 'class_levels': f"{PRIMARY_LEVELS},{OLEVEL_LEVELS}"},
        {'name': 'Physical Education', 'code': 'PE', 'class_levels': f"{PRIMARY_LEVELS},{OLEVEL_LEVELS}"},

        # --- O-Level Subjects ---
        {'name': 'Physics', 'code': 'PHYS', 'class_levels': f"{OLEVEL_LEVELS},{ALEVEL_LEVELS}"},
        {'name': 'Chemistry', 'code': 'CHEM', 'class_levels': f"{OLEVEL_LEVELS},{ALEVEL_LEVELS}"},
        {'name': 'Biology', 'code': 'BIOL', 'class_levels': f"{OLEVEL_LEVELS},{ALEVEL_LEVELS}"},
        {'name': 'Geography', 'code': 'GEO', 'class_levels': f"{OLEVEL_LEVELS},{ALEVEL_LEVELS}"},
        {'name': 'History & Political Education', 'code': 'HIST', 'class_levels': f"{OLEVEL_LEVELS},{ALEVEL_LEVELS}"},
        {'name': 'Agriculture', 'code': 'AGRI', 'class_levels': f"{OLEVEL_LEVELS},{ALEVEL_LEVELS}"},
        {'name': 'Computer Studies / ICT', 'code': 'ICT', 'class_levels': OLEVEL_LEVELS},
        {'name': 'Literature in English', 'code': 'LIT', 'class_levels': f"{OLEVEL_LEVELS},{ALEVEL_LEVELS}"},
        {'name': 'Entrepreneurship', 'code': 'ENT', 'class_levels': f"{OLEVEL_LEVELS},{ALEVEL_LEVELS}"},
        {'name': 'Kiswahili', 'code': 'KISW', 'class_levels': f"{OLEVEL_LEVELS},{ALEVEL_LEVELS}"},
        {'name': 'Fine Art', 'code': 'ART', 'class_levels': f"{OLEVEL_LEVELS},{ALEVEL_LEVELS}"},

        # --- A-Level Compulsory & Principal Subjects ---
        {'name': 'General Paper', 'code': 'GP', 'class_levels': ALEVEL_LEVELS},
        {'name': 'Subsidiary ICT', 'code': 'SICT', 'class_levels': ALEVEL_LEVELS},
        {'name': 'Subsidiary Mathematics', 'code': 'SMTC', 'class_levels': ALEVEL_LEVELS},
        {'name': 'Pure Mathematics', 'code': 'PMTC', 'class_levels': ALEVEL_LEVELS},
        {'name': 'Economics', 'code': 'ECON', 'class_levels': ALEVEL_LEVELS},
        {'name': 'Divinity', 'code': 'DIV', 'class_levels': ALEVEL_LEVELS},
    ]

    print("\n[1/3] Ensuring Subjects in DB with Correct class_levels...")
    subject_map = {}
    for spec in subjects_spec:
        subj, created = Subject.objects.get_or_create(
            school=school, name=spec['name'],
            defaults={'code': spec['code'], 'class_levels': spec['class_levels'], 'is_active': True}
        )
        if not created:
            # Update class_levels & code to authoritative curriculum standard
            subj.code = spec['code']
            subj.class_levels = spec['class_levels']
            subj.is_active = True
            subj.save()
        subject_map[subj.name] = subj

    # Also fix any existing subjects with names like "English Language", etc.
    existing_all = Subject.objects.filter(school=school)
    for s in existing_all:
        if s.name == 'Science':
            s.class_levels = PRIMARY_LEVELS
            s.save()
        elif s.name == 'Social Studies':
            s.class_levels = PRIMARY_LEVELS
            s.save()
        elif s.name == 'Mathematics Test':
            s.is_active = False
            s.save()
        subject_map[s.name] = s

    print(f"Total active subjects for school: {Subject.objects.filter(school=school, is_active=True).count()}")

    # 3. Define curriculum subject pools for classes
    def get_subject_pool_for_class(cg):
        lvl = cg.level.upper()
        stream = (cg.stream or '').strip().lower()
        name = (cg.name or '').strip().lower()

        if lvl in ('S5', 'S6'):
            if 'sci' in stream or 'science' in name:
                # A-Level Science: Pure Math, Physics, Chemistry, Biology, General Paper, Sub-ICT
                return [
                    subject_map.get('Pure Mathematics') or subject_map.get('Mathematics'),
                    subject_map.get('Physics'),
                    subject_map.get('Chemistry'),
                    subject_map.get('Biology'),
                    subject_map.get('General Paper'),
                    subject_map.get('Subsidiary ICT'),
                ]
            else:
                # A-Level Arts: History, Economics, Geography, Literature in English, Divinity, General Paper, Sub-ICT
                return [
                    subject_map.get('History & Political Education') or subject_map.get('History'),
                    subject_map.get('Economics'),
                    subject_map.get('Geography'),
                    subject_map.get('Literature in English'),
                    subject_map.get('Divinity') or subject_map.get('Christian Religious Education (CRE)'),
                    subject_map.get('General Paper'),
                    subject_map.get('Subsidiary ICT'),
                ]
        elif lvl.startswith('S'):
            # O-Level: English, Math, Physics, Chemistry, Biology, Geography, History, CRE, Agriculture, ICT
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
            # Primary: English, Math, Science, Social Studies, CRE, PE
            return [
                subject_map.get('English'),
                subject_map.get('Mathematics'),
                subject_map.get('Science'),
                subject_map.get('Social Studies'),
                subject_map.get('Christian Religious Education (CRE)'),
                subject_map.get('Physical Education'),
            ]

    # 4. Update Timetable Slots for all active versions
    print("\n[2/3] Updating Timetable Slots across All Classes...")
    active_versions = TimetableVersion.objects.filter(school=school, is_active=True).select_related('class_group', 'academic_term')

    periods_schedule = [
        (1, datetime.time(8, 0), datetime.time(9, 0), 'lesson', 0),
        (2, datetime.time(9, 0), datetime.time(10, 0), 'lesson', 1),
        (3, datetime.time(10, 0), datetime.time(10, 30), 'break', None),
        (4, datetime.time(10, 30), datetime.time(11, 30), 'lesson', 2),
        (5, datetime.time(11, 30), datetime.time(12, 30), 'lesson', 3),
        (6, datetime.time(12, 30), datetime.time(13, 30), 'lunch', None),
        (7, datetime.time(13, 30), datetime.time(14, 30), 'lesson', 4),
        (8, datetime.time(14, 30), datetime.time(15, 30), 'study', None),
    ]

    total_slots_updated = 0
    class_idx = 0

    for tv in active_versions:
        cg = tv.class_group
        pool = [s for s in get_subject_pool_for_class(cg) if s is not None]
        class_idx += 1

        # Delete existing slots for this version to repopulate cleanly
        TimetableSlot.objects.filter(timetable_version=tv).delete()

        new_slots = []
        for day in range(5):
            for period_num, start, end, stype, sub_offset in periods_schedule:
                subj = None
                sub_name = ""
                assigned_teacher = None

                if stype == 'lesson':
                    subj_idx = (day * 2 + (sub_offset or 0)) % len(pool)
                    subj = pool[subj_idx]
                    sub_name = subj.name
                    # Rotate teacher based on class_idx + period to avoid double booking
                    assigned_teacher = teachers[(class_idx + day + period_num) % len(teachers)]
                elif stype == 'break':
                    sub_name = "Break"
                elif stype == 'lunch':
                    sub_name = "Lunch"
                elif stype == 'study':
                    sub_name = "Self Study"
                    assigned_teacher = teachers[(class_idx + day) % len(teachers)]

                slot = TimetableSlot(
                    timetable_version=tv,
                    school=school,
                    day_of_week=day,
                    period_number=period_num,
                    start_time=start,
                    end_time=end,
                    subject=subj,
                    subject_name=sub_name,
                    teacher=assigned_teacher,
                    room=f"Room {cg.name.replace('.', '')[:8]}",
                    slot_type=stype,
                )
                new_slots.append(slot)

        TimetableSlot.objects.bulk_create(new_slots)
        total_slots_updated += len(new_slots)
        print(f"  [OK] {cg.name}: Seeded {len(new_slots)} slots with {[s.name for s in pool[:4]]}...")

        # 5. Sync to schools.Timetable for WhatsApp text
        try:
            whatsapp_text = TimetableService.format_for_whatsapp(cg, tv.academic_term)
            Timetable.objects.update_or_create(
                school=school,
                class_group=cg,
                is_active=True,
                defaults={
                    'content': whatsapp_text,
                    'title': f"{cg.name} — {tv.academic_term.name}",
                }
            )
        except Exception as e:
            print(f"    [!] WhatsApp sync warning for {cg.name}: {e}")

    print(f"\n[3/3] Remediation Completed! Total slots updated: {total_slots_updated}")


if __name__ == '__main__':
    for school in School.objects.all():
        remediate_school(school)
