"""
Phase 5 Remediation Tests -- Security & Query Optimisation
===========================================================
Covers:
  RISK-P5A  N+1 query reduction in DistrictBenchmarkView
  RISK-P5B  fully_paid recipient resolution bug in BroadcastViewSet
  RISK-P5C  Cross-tenant validation in BroadcastSerializer
"""
import pytest
import datetime
from decimal import Decimal
from unittest.mock import patch, MagicMock

from django.db import connection
from django.utils import timezone
from rest_framework.test import APIClient


# ---------------------------------------------------------------------------
# Setup fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def phase5_setup(db):
    from schools.models import School, AcademicYear, AcademicTerm
    from students.models import Student, ClassGroup, Guardian
    from payments.models import FeeRecord
    from authentication.models import User

    # 1. School A (our main school)
    school_a = School.objects.create(
        name="School A", slug="school-a", district="Wakiso",
        school_type="primary", is_active=True
    )
    year_a = AcademicYear.objects.create(school=school_a, year=2026, is_current=True)
    term_a = AcademicTerm.objects.create(
        school=school_a, academic_year=year_a, term_number=1,
        name="Term A", start_date=datetime.date(2026, 1, 6),
        end_date=datetime.date(2026, 12, 31),
        fee_deadline=datetime.date(2026, 2, 1),
        is_current=True, is_active=True
    )
    director_a = User.objects.create_user(
        email="director-a@schoola.ug", password="testpassword1",
        role="director", school=school_a, is_active=True
    )
    cg_a = ClassGroup.all_objects.create(school=school_a, name="P1", level="P1")

    # Students for School A (one paid, one defaulter)
    stu_paid = Student.all_objects.create(
        school=school_a, student_id="STU-PAID", first_name="Paid", last_name="Student",
        gender="M", current_class=cg_a, admission_date=datetime.date(2026, 1, 6),
        academic_year_admitted=2026, is_active=True
    )
    fr_paid = FeeRecord.all_objects.create(
        school=school_a, student=stu_paid, academic_term=term_a,
        total_amount=Decimal("100000"), amount_paid=Decimal("100000"),
    )
    Guardian.objects.create(
        student=stu_paid, first_name="Parent", last_name="Paid",
        relationship="Mother", phone="0777123456", phone_hash="hash_paid",
        is_primary=True, preferred_language="en"
    )

    stu_def = Student.all_objects.create(
        school=school_a, student_id="STU-DEF", first_name="Defaulter", last_name="Student",
        gender="F", current_class=cg_a, admission_date=datetime.date(2026, 1, 6),
        academic_year_admitted=2026, is_active=True
    )
    fr_def = FeeRecord.all_objects.create(
        school=school_a, student=stu_def, academic_term=term_a,
        total_amount=Decimal("100000"), amount_paid=Decimal("20000"),
    )
    Guardian.objects.create(
        student=stu_def, first_name="Parent", last_name="Def",
        relationship="Father", phone="0777987654", phone_hash="hash_def",
        is_primary=True, preferred_language="en"
    )

    # 2. School B (same district, for benchmark calculations)
    school_b = School.objects.create(
        name="School B", slug="school-b", district="Wakiso",
        school_type="primary", is_active=True
    )
    year_b = AcademicYear.objects.create(school=school_b, year=2026, is_current=True)
    term_b = AcademicTerm.objects.create(
        school=school_b, academic_year=year_b, term_number=1,
        name="Term B", start_date=datetime.date(2026, 1, 6),
        end_date=datetime.date(2026, 12, 31),
        fee_deadline=datetime.date(2026, 2, 1),
        is_current=True, is_active=True
    )
    stu_b = Student.all_objects.create(
        school=school_b, student_id="STU-B", first_name="SchoolB", last_name="Student",
        gender="M", admission_date=datetime.date(2026, 1, 6),
        academic_year_admitted=2026, is_active=True
    )
    # School B has 80% collection rate
    FeeRecord.all_objects.create(
        school=school_b, student=stu_b, academic_term=term_b,
        total_amount=Decimal("200000"), amount_paid=Decimal("160000"),
    )

    # 3. School C (foreign tenant, another district/school group, for cross-tenant tests)
    school_c = School.objects.create(
        name="School C", slug="school-c", district="Kampala",
        school_type="primary", is_active=True
    )
    year_c = AcademicYear.objects.create(school=school_c, year=2026, is_current=True)
    term_c = AcademicTerm.objects.create(
        school=school_c, academic_year=year_c, term_number=1,
        name="Term C", start_date=datetime.date(2026, 1, 6),
        end_date=datetime.date(2026, 12, 31),
        fee_deadline=datetime.date(2026, 2, 1),
        is_current=True, is_active=True
    )
    cg_c = ClassGroup.all_objects.create(school=school_c, name="P1", level="P1")

    return {
        "school_a": school_a, "term_a": term_a, "director_a": director_a, "cg_a": cg_a,
        "school_b": school_b, "term_b": term_b,
        "school_c": school_c, "term_c": term_c, "cg_c": cg_c,
    }


# ---------------------------------------------------------------------------
# RISK-P5A: DistrictBenchmarkView Query Optimisation
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestDistrictBenchmarkOptimisation:

    def test_benchmark_calculation_correct(self, phase5_setup):
        """District benchmark correctly calculates unweighted averages of collection rates of district schools."""
        client = APIClient()
        client.force_authenticate(user=phase5_setup["director_a"])

        resp = client.get("/api/v1/schools/district-benchmark/")
        assert resp.status_code == 200
        data = resp.json()

        # School A collection rate: (100k+20k)/(100k+100k) = 120k/200k = 60.0%
        assert data["school_collection_rate"] == 60.0
        # School B collection rate: 160k/200k = 80.0%
        assert data["district_average_collection_rate"] == 80.0
        assert data["schools_in_district"] == 1
        assert data["above_district_average"] is False

    def test_benchmark_reduces_query_count(self, phase5_setup):
        """District benchmark fetches average using a constant/low query count (no N+1 loops)."""
        client = APIClient()
        client.force_authenticate(user=phase5_setup["director_a"])

        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        with CaptureQueriesContext(connection) as ctx:
            resp = client.get("/api/v1/schools/district-benchmark/")
            assert resp.status_code == 200

        # With the N+1 loop removed, query count should be low (< 10)
        assert len(ctx.captured_queries) < 10, f"Benchmark view query count too high: {len(ctx.captured_queries)}"


# ---------------------------------------------------------------------------
# RISK-P5B: Broadcast Recipient Leakage Tests
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestBroadcastRecipientResolution:

    def test_resolve_recipients_fully_paid(self, phase5_setup):
        """Broadcast with fully_paid target type resolves only fully paid students."""
        from messaging.models import BroadcastMessage
        from messaging.views import BroadcastViewSet

        broadcast = BroadcastMessage.objects.create(
            school=phase5_setup["school_a"],
            title="Fully Paid Broadcast",
            message_body="Thank you for paying!",
            target_type="fully_paid",
            target_term=phase5_setup["term_a"],
            created_by=phase5_setup["director_a"],
        )

        view = BroadcastViewSet()
        recipients = view._resolve_recipients(broadcast)

        # Only 'STU-PAID' guardian should be resolved
        assert len(recipients) == 1
        # Compare with the actual database UUID of stu_paid
        from students.models import Student
        stu_paid = Student.all_objects.get(student_id="STU-PAID")
        assert recipients[0]["student_id"] == str(stu_paid.id)

    def test_resolve_recipients_fee_defaulters(self, phase5_setup):
        """Broadcast with fee_defaulters target type resolves only defaulters."""
        from messaging.models import BroadcastMessage
        from messaging.views import BroadcastViewSet

        broadcast = BroadcastMessage.objects.create(
            school=phase5_setup["school_a"],
            title="Defaulters Broadcast",
            message_body="Please pay your fees!",
            target_type="fee_defaulters",
            target_term=phase5_setup["term_a"],
            created_by=phase5_setup["director_a"],
        )

        view = BroadcastViewSet()
        recipients = view._resolve_recipients(broadcast)

        # Only 'STU-DEF' guardian should be resolved
        assert len(recipients) == 1
        from students.models import Student
        stu_def = Student.all_objects.get(student_id="STU-DEF")
        assert recipients[0]["student_id"] == str(stu_def.id)


# ---------------------------------------------------------------------------
# RISK-P5C: Cross-tenant Target Validation Tests
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestBroadcastTenantSecurity:

    def test_cross_tenant_class_rejected(self, phase5_setup):
        """Attempting to save a broadcast targeting another school's class returns 400 validation error."""
        client = APIClient()
        client.force_authenticate(user=phase5_setup["director_a"])

        payload = {
            "title": "Hack Class",
            "message_body": "Spam Class",
            "target_type": "class",
            "target_class": str(phase5_setup["cg_c"].id), # School C class
        }

        resp = client.post("/api/v1/messaging/broadcasts/", payload, format="json")
        assert resp.status_code == 400
        assert "target_class" in resp.data["detail"]

    def test_cross_tenant_term_rejected(self, phase5_setup):
        """Attempting to save a broadcast targeting another school's term returns 400 validation error."""
        client = APIClient()
        client.force_authenticate(user=phase5_setup["director_a"])

        payload = {
            "title": "Hack Term",
            "message_body": "Spam Term",
            "target_type": "fee_defaulters",
            "target_term": str(phase5_setup["term_c"].id), # School C term
        }

        resp = client.post("/api/v1/messaging/broadcasts/", payload, format="json")
        assert resp.status_code == 400
        assert "target_term" in resp.data["detail"]
