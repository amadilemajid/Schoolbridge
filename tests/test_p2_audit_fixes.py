# P2 Production Acceptance Audit Remediation Tests
# Covers:
#   1. AttendanceSummaryView school-wide aggregate for director/admin roles
#   2. AttendanceSummaryView form-class fallback for teachers without params
#   3. IsDirectorOrBursar excludes school_admin (financial segregation of duties)
#   4. IsDirectorOrAdmin includes school_admin (registrar/bulk-import)
#   5. FeeStructureItemSerializer quantizes decimal UGX amounts to whole shillings
#   6. FeeWaiver ordered by -created_at (no UnorderedObjectListWarning)
import pytest
from decimal import Decimal
from datetime import date
from unittest.mock import MagicMock
from rest_framework.test import APIRequestFactory


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

def _make_school():
    from schools.models import School
    school, _ = School.objects.get_or_create(
        slug='p2-audit-school',
        defaults={
            'name': 'P2 Audit School',
            'district': 'Kampala',
            'sub_county': 'Central',
            'phone': '+256700000088',
            'email': 'p2audit@test.com',
            'school_type': 'primary',
            'is_active': True,
        },
    )
    return school


def _make_year(school):
    from schools.models import AcademicYear
    yr, _ = AcademicYear.objects.get_or_create(
        school=school, year=2026, defaults={'is_current': True}
    )
    return yr


def _make_term(school, year, is_current=True):
    from schools.models import AcademicTerm
    term, _ = AcademicTerm.objects.get_or_create(
        school=school, name='P2 Audit Term',
        defaults={
            'academic_year': year,
            'term_number': 1,
            'start_date': date(2026, 1, 13),
            'end_date': date(2026, 4, 30),
            'fee_deadline': date(2026, 1, 20),
            'is_current': is_current,
            'is_active': True,
        },
    )
    return term


def _make_class(school, name='P2-Class-A', level='P1'):
    from students.models import ClassGroup
    cg, _ = ClassGroup.all_objects.get_or_create(
        school=school, name=name, defaults={'level': level, 'is_active': True}
    )
    return cg


def _make_user(school, role, email=None, form_class=None):
    from authentication.models import User
    email = email or (role + '-p2-' + school.slug + '@test.com')
    user, _ = User.objects.get_or_create(
        email=email,
        defaults={'role': role, 'school': school, 'is_active': True},
    )
    if form_class:
        form_class.form_teacher = user
        form_class.save()
    return user


def _make_student(school, cg, student_id='P2-STU-9001'):
    from students.models import Student
    student, _ = Student.all_objects.get_or_create(
        school=school,
        student_id=student_id,
        defaults={
            'first_name': 'Test',
            'last_name': 'Student',
            'date_of_birth': date(2012, 1, 1),
            'gender': 'M',
            'current_class': cg,
            'admission_date': date(2026, 1, 1),
            'academic_year_admitted': 2026,
            'is_active': True,
        },
    )
    return student


def _make_attendance(school, student, cg, term, rec_date, status_val='present'):
    from attendance.models import AttendanceRecord
    rec, _ = AttendanceRecord.all_objects.get_or_create(
        school=school,
        student=student,
        class_group=cg,
        date=rec_date,
        academic_term=term,
        defaults={'status': status_val},
    )
    return rec


# ---------------------------------------------------------------------------
# 1 & 2. AttendanceSummaryView school-wide aggregate
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestAttendanceSummarySchoolWide:
    def _call(self, user, params=None):
        from attendance.views import AttendanceSummaryView
        factory = APIRequestFactory()
        request = factory.get('/api/v1/attendance/summary/', params or {})
        request.user = user
        return AttendanceSummaryView.as_view()(request)

    def test_director_no_params_returns_school_scope(self):
        school = _make_school()
        year = _make_year(school)
        _make_term(school, year)
        director = _make_user(school, 'director', email='director-p2-sw@test.com')
        response = self._call(director)
        assert response.status_code == 200, response.data
        assert response.data.get('scope') == 'school'
        assert 'total_active_students' in response.data
        assert 'class_breakdown' in response.data
        assert 'overall_attendance_rate' in response.data
        assert isinstance(response.data['class_breakdown'], list)

    def test_bursar_no_params_returns_school_scope(self):
        school = _make_school()
        year = _make_year(school)
        _make_term(school, year)
        bursar = _make_user(school, 'bursar', email='bursar-p2-sw@test.com')
        response = self._call(bursar)
        assert response.status_code == 200
        assert response.data.get('scope') == 'school'

    def test_school_admin_no_params_returns_school_scope(self):
        school = _make_school()
        year = _make_year(school)
        _make_term(school, year)
        admin = _make_user(school, 'school_admin', email='sadmin-p2-sw@test.com')
        response = self._call(admin)
        assert response.status_code == 200
        assert response.data.get('scope') == 'school'

    def test_class_breakdown_has_required_fields(self):
        school = _make_school()
        year = _make_year(school)
        term = _make_term(school, year)
        cg = _make_class(school, name='P2-Rate-Class')
        director = _make_user(school, 'director', email='director-rate@test.com')
        student = _make_student(school, cg, 'P2-STU-R001')
        for d, s in [
            (date(2026, 3, 1), 'present'), (date(2026, 3, 2), 'absent'),
            (date(2026, 3, 3), 'absent'), (date(2026, 3, 4), 'absent'),
        ]:
            _make_attendance(school, student, cg, term, d, s)
        response = self._call(director)
        assert response.status_code == 200
        breakdown = response.data['class_breakdown']
        if breakdown:
            entry = breakdown[0]
            assert 'class_name' in entry
            assert 'attendance_rate' in entry
            assert 'below_threshold' in entry
        found = next((c for c in breakdown if c['class_name'] == 'P2-Rate-Class'), None)
        if found:
            assert found['below_threshold'] is True


@pytest.mark.django_db
class TestAttendanceSummaryTeacherFallback:
    def _call(self, user, params=None):
        from attendance.views import AttendanceSummaryView
        factory = APIRequestFactory()
        request = factory.get('/api/v1/attendance/summary/', params or {})
        request.user = user
        return AttendanceSummaryView.as_view()(request)

    def test_teacher_with_form_class_returns_class_scope(self):
        school = _make_school()
        year = _make_year(school)
        term = _make_term(school, year)
        cg = _make_class(school, name='P2-TClass-A')
        teacher = _make_user(school, 'teacher', email='teacher-p2-fb@test.com', form_class=cg)
        student = _make_student(school, cg, 'P2-STU-TF01')
        _make_attendance(school, student, cg, term, date(2026, 3, 1), 'present')
        response = self._call(teacher)
        assert response.status_code == 200, response.data
        assert response.data.get('scope') == 'class'
        assert 'data' in response.data
        assert isinstance(response.data['data'], list)

    def test_teacher_class_data_has_required_fields(self):
        school = _make_school()
        year = _make_year(school)
        term = _make_term(school, year)
        cg = _make_class(school, name='P2-TClass-B')
        teacher = _make_user(school, 'teacher', email='teacher-p2-fields@test.com', form_class=cg)
        student = _make_student(school, cg, 'P2-STU-TF02')
        _make_attendance(school, student, cg, term, date(2026, 3, 1), 'present')
        response = self._call(teacher)
        assert response.status_code == 200
        data_list = response.data['data']
        assert len(data_list) >= 1
        entry = data_list[0]
        assert 'student_name' in entry
        assert 'attendance_rate' in entry
        assert 'below_threshold' in entry

    def test_teacher_without_form_class_returns_400(self):
        school = _make_school()
        year = _make_year(school)
        _make_term(school, year)
        teacher = _make_user(school, 'teacher', email='teacher-p2-nc@test.com')
        response = self._call(teacher)
        assert response.status_code == 400


# ---------------------------------------------------------------------------
# 3 & 4. Permission hardening
# ---------------------------------------------------------------------------

class TestPermissionHardening:
    def _perm(self, cls_name, role):
        import schools.permissions as perms
        perm = getattr(perms, cls_name)()
        request = MagicMock()
        request.user = MagicMock()
        request.user.role = role
        request.user.is_authenticated = True
        return perm.has_permission(request, None)

    # IsDirectorOrBursar
    def test_IsDirectorOrBursar_allows_director(self):
        assert self._perm('IsDirectorOrBursar', 'director') is True

    def test_IsDirectorOrBursar_allows_bursar(self):
        assert self._perm('IsDirectorOrBursar', 'bursar') is True

    def test_IsDirectorOrBursar_allows_system_admin(self):
        assert self._perm('IsDirectorOrBursar', 'system_admin') is True

    def test_IsDirectorOrBursar_denies_school_admin(self):
        # school_admin must NOT have financial ledger access
        assert self._perm('IsDirectorOrBursar', 'school_admin') is False

    def test_IsDirectorOrBursar_denies_teacher(self):
        assert self._perm('IsDirectorOrBursar', 'teacher') is False

    def test_IsDirectorOrBursar_denies_registrar(self):
        assert self._perm('IsDirectorOrBursar', 'registrar') is False

    # IsDirectorOrAdmin
    def test_IsDirectorOrAdmin_allows_director(self):
        assert self._perm('IsDirectorOrAdmin', 'director') is True

    def test_IsDirectorOrAdmin_allows_school_admin(self):
        # Registrar (school_admin) must run bulk imports
        assert self._perm('IsDirectorOrAdmin', 'school_admin') is True

    def test_IsDirectorOrAdmin_allows_system_admin(self):
        assert self._perm('IsDirectorOrAdmin', 'system_admin') is True

    def test_IsDirectorOrAdmin_denies_bursar(self):
        assert self._perm('IsDirectorOrAdmin', 'bursar') is False

    def test_IsDirectorOrAdmin_denies_teacher(self):
        assert self._perm('IsDirectorOrAdmin', 'teacher') is False


# ---------------------------------------------------------------------------
# 5. UGX decimal quantization
# ---------------------------------------------------------------------------

class TestFeeUGXQuantization:
    def _validate(self, raw_amount):
        from payments.serializers import FeeStructureItemSerializer
        s = FeeStructureItemSerializer(
            data={'name': 'Tuition', 'amount': raw_amount, 'is_mandatory': True}
        )
        s.is_valid(raise_exception=True)
        return s.validated_data['amount']

    def test_integer_passes_unchanged(self):
        assert self._validate(650000) == Decimal('650000')

    def test_dot_zero_zero_string_quantized_to_integer(self):
        assert self._validate('650000.00') == Decimal('650000')

    def test_half_rounds_up(self):
        # 650000.50 -> 650001
        assert self._validate('650000.50') == Decimal('650001')

    def test_below_half_rounds_down(self):
        # 650000.30 -> 650000
        assert self._validate('650000.30') == Decimal('650000')

    def test_large_ugx_amount(self):
        # 1,200,000 shillings (common term fee)
        assert self._validate('1200000.00') == Decimal('1200000')


# ---------------------------------------------------------------------------
# 6. FeeWaiver ordering
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestFeeWaiverOrdering:
    def test_ordering_is_minus_created_at(self):
        from payments.models import FeeWaiver
        assert FeeWaiver._meta.ordering is not None, 'FeeWaiver must have explicit ordering'
        assert '-created_at' in FeeWaiver._meta.ordering, (
            'Expected -created_at in ordering, got: ' + str(FeeWaiver._meta.ordering)
        )

