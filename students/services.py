"""
Student service layer — business logic separate from views.
US-008: Bulk CSV import with pandas; partial import; downloadable error report.
US-014: Search <500ms for 5,000 students.
"""
import io
import csv
import logging
from django.db import transaction
from django.utils import timezone
from django.core.files.base import ContentFile
import pandas as pd
from .models import Student, Guardian, ClassGroup, BulkImportJob, ClassAssignment

logger = logging.getLogger('schoolbridge')


REQUIRED_CSV_COLUMNS = {
    'first_name', 'last_name', 'gender', 'admission_date',
    'guardian_name', 'guardian_phone', 'guardian_relationship',
}

OPTIONAL_CSV_COLUMNS = {
    'admission_number', 'student_id', 'admission_no',
    'other_names', 'date_of_birth', 'class_name',
    'guardian2_name', 'guardian2_phone', 'guardian2_relationship',
}


class StudentImportService:
    """
    US-008: Parse and import student CSV.
    - Downloads template available.
    - Validates each row.
    - Partial import: valid rows imported, errors reported.
    - Returns importable error report CSV.
    """

    def __init__(self, job: BulkImportJob):
        self.job = job
        self.school = job.school
        self.errors = []

    def run(self):
        from django.utils import timezone as tz
        self.job.status = 'processing'
        self.job.started_at = tz.now()
        self.job.save(update_fields=['status', 'started_at'])

        try:
            df = pd.read_csv(self.job.csv_file.path, dtype=str, keep_default_na=False)
            df.columns = [c.strip().lower().replace(' ', '_') for c in df.columns]
            self.job.total_rows = len(df)
            self._validate_columns(df)
            self._process_rows(df)
        except Exception as e:
            logger.exception(f"BulkImport {self.job.id} failed: {e}")
            self.job.status = 'failed'
            self.job.save(update_fields=['status'])
            return

        self.job.imported_count = self.job.total_rows - len(self.errors)
        self.job.failed_count = len(self.errors)
        self.job.error_report = self.errors
        self.job.status = 'completed'
        self.job.completed_at = tz.now()

        if self.errors:
            self._generate_error_report_file()

        self.job.save()
        logger.info(
            f"BulkImport {self.job.id}: {self.job.imported_count} imported, "
            f"{self.job.failed_count} failed"
        )

    def _validate_columns(self, df):
        missing = REQUIRED_CSV_COLUMNS - set(df.columns)
        if missing:
            raise ValueError(f"CSV missing required columns: {missing}")

    def _process_rows(self, df):
        """
        Process CSV rows with performance optimisations:
        - ClassGroup lookup cache avoids N DB queries per row
        - ID pre-allocation avoids locking School row for every single insert
        """
        # Cache all ClassGroups for this school in memory (1 query vs N queries)
        self._class_cache = {
            cg.name.lower(): cg
            for cg in ClassGroup.all_objects.filter(school=self.school)
        }

        # Pre-allocate the entire sequence of student IDs (1 DB lock vs N locks)
        total_rows = len(df)
        self._id_counter, self._id_prefix = self._preallocate_student_ids(total_rows)

        for idx, row in df.iterrows():
            row_num = idx + 2  # 1-indexed, header is row 1
            try:
                self._import_row(row, row_num)
            except Exception as e:
                self.errors.append({'row': row_num, 'data': row.to_dict(), 'errors': str(e)})

    def _preallocate_student_ids(self, count):
        """
        Pre-allocate `count` student IDs by acquiring a single School lock,
        determining the starting sequence number, and returning it.
        Subsequent calls in _import_row use an in-memory counter.
        """
        from django.utils import timezone
        from schools.models import School as SchoolModel

        with transaction.atomic():
            locked_school = SchoolModel.objects.select_for_update().get(pk=self.school.pk)
            year = timezone.now().year
            prefix = f"SCH-{year}-"
            last = (
                Student.all_objects
                .filter(school=locked_school, student_id__startswith=prefix)
                .order_by('-student_id').first()
            )
            if last:
                try:
                    start = int(last.student_id.split('-')[-1]) + 1
                except (ValueError, IndexError):
                    start = 1
            else:
                start = 1
        return start, prefix

    def _next_student_id(self):
        """Return next pre-allocated student ID from in-memory counter."""
        sid = f"{self._id_prefix}{self._id_counter:04d}"
        self._id_counter += 1
        return sid

    @transaction.atomic
    def _import_row(self, row, row_num):
        """Import a single row. Atomic — if anything fails, nothing is saved."""
        errors = []

        # Required fields
        first_name = row.get('first_name', '').strip()
        last_name = row.get('last_name', '').strip()
        gender = row.get('gender', '').strip().upper()[:1]
        guardian_name = row.get('guardian_name', '').strip()
        guardian_phone = row.get('guardian_phone', '').strip()
        guardian_rel = row.get('guardian_relationship', 'Guardian').strip()
        admission_date = row.get('admission_date', '').strip()

        if not first_name:
            errors.append('first_name is required')
        if not last_name:
            errors.append('last_name is required')
        if gender not in ('M', 'F'):
            errors.append('gender must be M or F')
        if not guardian_phone:
            errors.append('guardian_phone is required')
        if not admission_date:
            errors.append('admission_date is required')

        if errors:
            raise ValueError('; '.join(errors))

        # Duplicate detection: same name + same class
        class_name = row.get('class_name', '').strip()
        class_group = None
        if class_name:
            # Use in-memory cache instead of a DB query per row
            class_group = self._class_cache.get(class_name.lower())
            if class_group is None:
                raise ValueError(f"Class '{class_name}' not found in this school")

        existing = Student.all_objects.filter(
            school=self.school,
            first_name__iexact=first_name,
            last_name__iexact=last_name,
            current_class=class_group,
        )
        if existing.exists():
            raise ValueError(f"Duplicate: {first_name} {last_name} already in {class_name or 'this school'}")

        # Parse date
        from datetime import datetime
        try:
            adm_date = datetime.strptime(admission_date, '%Y-%m-%d').date()
        except ValueError:
            raise ValueError(f"admission_date must be YYYY-MM-DD, got '{admission_date}'")

        # Normalise phone
        phone_normalised = Guardian._normalise_phone(guardian_phone)

        # Assign custom admission number if provided in CSV, otherwise pre-allocated ID
        custom_id = (row.get('admission_number', '') or row.get('student_id', '') or row.get('admission_no', '')).strip()
        if custom_id:
            if Student.all_objects.filter(school=self.school, student_id__iexact=custom_id).exists():
                raise ValueError(f"Admission No. / Student ID '{custom_id}' already exists in this school")
            student_id = custom_id
        else:
            student_id = self._next_student_id()

        student = Student.all_objects.create(
            school=self.school,
            student_id=student_id,
            first_name=first_name,
            last_name=last_name,
            other_names=row.get('other_names', '').strip(),
            gender=gender,
            admission_date=adm_date,
            academic_year_admitted=adm_date.year,
            current_class=class_group,
            created_by=self.job.uploaded_by,
        )

        # Primary guardian
        gname_parts = guardian_name.split(' ', 1)
        Guardian.objects.create(
            student=student,
            first_name=gname_parts[0],
            last_name=gname_parts[1] if len(gname_parts) > 1 else '',
            relationship=guardian_rel,
            phone=guardian_phone,
            phone_normalised=phone_normalised,
            is_primary=True,
        )

        # Optional second guardian
        g2_name = row.get('guardian2_name', '').strip()
        g2_phone = row.get('guardian2_phone', '').strip()
        if g2_name and g2_phone:
            g2parts = g2_name.split(' ', 1)
            Guardian.objects.create(
                student=student,
                first_name=g2parts[0],
                last_name=g2parts[1] if len(g2parts) > 1 else '',
                relationship=row.get('guardian2_relationship', 'Guardian').strip(),
                phone=g2_phone,
                phone_normalised=Guardian._normalise_phone(g2_phone),
                is_primary=False,
            )

        initialize_student_enrolment(student, assigned_by=self.job.uploaded_by)

    def _generate_error_report_file(self):
        """Create a downloadable CSV of failed rows with error reasons."""
        output = io.StringIO()
        if not self.errors:
            return
        fieldnames = list(self.errors[0]['data'].keys()) + ['row_number', 'errors']
        writer = csv.DictWriter(output, fieldnames=fieldnames)
        writer.writeheader()
        for err in self.errors:
            row = {**err['data'], 'row_number': err['row'], 'errors': err['errors']}
            writer.writerow(row)
        content = output.getvalue().encode('utf-8')
        self.job.error_report_file.save(
            f'import_errors_{self.job.id}.csv',
            ContentFile(content),
        )


def initialize_student_enrolment(student, assigned_by=None):
    """
    Called upon student creation (single add or bulk CSV import).
    1. Preserves historical assignment via ClassAssignment if current_class is set.
    2. Opens FeeRecord for the current active term matching the class fee structure.
    """
    from schools.models import AcademicTerm
    from payments.models import FeeRecord, FeeStructure
    from decimal import Decimal

    school = student.school
    term = AcademicTerm.objects.filter(school=school, is_current=True).first()
    if not term:
        return

    # 1. Initial ClassAssignment
    if student.current_class:
        ClassAssignment.objects.get_or_create(
            student=student,
            class_group=student.current_class,
            academic_term=term,
            defaults={
                'start_date': student.admission_date or timezone.localdate(),
                'assigned_by': assigned_by,
            }
        )

    # 2. Initial FeeRecord
    structure = (
        FeeStructure.all_objects.filter(
            school=school, academic_term=term,
            class_group=student.current_class, is_active=True
        ).first() or
        FeeStructure.all_objects.filter(
            school=school, academic_term=term,
            class_group__isnull=True, is_active=True
        ).first()
    )
    total = structure.total_amount if structure else Decimal('0')
    FeeRecord.all_objects.get_or_create(
        student=student,
        academic_term=term,
        defaults={
            'school': school,
            'fee_structure': structure,
            'total_amount': total,
            'amount_paid': Decimal('0'),
            'amount_waived': Decimal('0'),
        }
    )


class StudentSearchService:
    """
    US-014: Search by name/ID/guardian phone. <500ms for 5,000 students.
    Uses DB indexes. Partial match supported.
    """

    @staticmethod
    def search(school, query, limit=50, is_active=None, class_id=None):
        from django.db.models import Q
        query = query.strip()
        if not query:
            return Student.all_objects.none()

        # Normalise phone query
        if any(c.isdigit() for c in query):
            normalised = Guardian._normalise_phone(query)
            student_ids_by_phone = Guardian.objects.filter(
                phone_normalised__icontains=normalised
            ).values_list('student_id', flat=True)[:100]
        else:
            student_ids_by_phone = []

        filter_kwargs = {'school': school}
        if is_active is not None:
            filter_kwargs['is_active'] = is_active
        if class_id is not None:
            filter_kwargs['current_class_id'] = class_id

        qs = Student.all_objects.filter(
            **filter_kwargs
        ).select_related('current_class').prefetch_related('guardians')

        tokens = query.split()
        if len(tokens) > 1:
            # Multi-word query (e.g. "Faith mu" or "Brian Namukasa")
            token_q = Q()
            for t in tokens:
                token_q &= (
                    Q(first_name__icontains=t) |
                    Q(last_name__icontains=t) |
                    Q(other_names__icontains=t) |
                    Q(student_id__icontains=t)
                )
            return qs.filter(token_q | Q(id__in=student_ids_by_phone))[:limit]

        return qs.filter(
            Q(first_name__icontains=query) |
            Q(last_name__icontains=query) |
            Q(other_names__icontains=query) |
            Q(student_id__icontains=query) |
            Q(id__in=student_ids_by_phone)
        )[:limit]
