"""
Phase 4 Remediation Tests -- Missing Workflows & Info-Leak Hardening
=====================================================================
Covers:
  RISK-P4A  Bilingual ABSENT command with phone normalisation & error handling
  RISK-P4B  Celery ETA task deduplication via ScheduledReminder
  RISK-P4C  Info-leak masking in health endpoints (Liveness, Readiness, Version)
"""
import pytest
import datetime
from decimal import Decimal
from unittest.mock import patch, MagicMock

from django.utils import timezone
from rest_framework.test import APIClient

# ---------------------------------------------------------------------------
# Setup fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def phase4_setup(db):
    from schools.models import School, AcademicYear, AcademicTerm
    from students.models import Student, ClassGroup, Guardian
    from authentication.models import User

    school = School.objects.create(
        name="Phase 4 School", slug="phase-4-school", district="Wakiso",
        school_type="combined", is_active=True
    )
    year = AcademicYear.objects.create(school=school, year=2026, is_current=True)
    term = AcademicTerm.objects.create(
        school=school, academic_year=year, term_number=1,
        name="P4 Term 1 2026", start_date=datetime.date(2026, 1, 6),
        end_date=datetime.date(2026, 12, 31),
        fee_deadline=timezone.localdate() + datetime.timedelta(days=30),
        is_current=True, is_active=True
    )
    cg = ClassGroup.all_objects.create(school=school, name="P.5", level="P5")
    student = Student.all_objects.create(
        school=school, student_id="P4-ST-001", first_name="Bruno", last_name="M",
        gender="M", current_class=cg, admission_date=datetime.date(2026, 1, 6),
        academic_year_admitted=2026, is_active=True
    )

    import hashlib
    phone_raw = "0788111222"
    phone_normalised = "+256788111222"
    phone_hash = hashlib.sha256(phone_normalised.encode()).hexdigest()

    guardian = Guardian.objects.create(
        student=student, first_name="Guardian", last_name="Bruno",
        relationship="Father", phone=phone_raw, phone_hash=phone_hash,
        is_primary=True, preferred_language="en"
    )

    return {
        "school": school, "term": term, "student": student, "guardian": guardian,
        "phone_raw": phone_raw, "phone_normalised": phone_normalised,
    }


# ---------------------------------------------------------------------------
# RISK-P4A: ABSENT Command Tests
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestAbsentCommand:

    @patch("messaging.services.InboundCommandProcessor._send_or_queue_reply")
    def test_absent_normalises_phone(self, mock_reply, phase4_setup):
        """ABSENT normalises the phone (e.g. 256788111222) and successfully finds the guardian."""
        from messaging.services import InboundCommandProcessor
        from messaging.models import InboundMessage

        inbound = InboundMessage.objects.create(
            school=phase4_setup["school"],
            from_phone="256788111222", # omit '+'
            raw_message="ABSENT 2026-02-15 Malaria",
            command="ABSENT",
            command_args={"date": "2026-02-15", "reason": "Malaria"},
            whatsapp_message_id="msg_absent_1",
        )

        InboundCommandProcessor.process(inbound)

        mock_reply.assert_called_once()
        sent_text = mock_reply.call_args[1]["text"]
        assert "Absence noted" in sent_text
        assert "Bruno M" in sent_text

    @patch("messaging.services.InboundCommandProcessor._send_or_queue_reply")
    def test_absent_missing_date_returns_error(self, mock_reply, phase4_setup):
        """ABSENT with missing date sends format instructions instead of false success."""
        from messaging.services import InboundCommandProcessor
        from messaging.models import InboundMessage

        inbound = InboundMessage.objects.create(
            school=phase4_setup["school"],
            from_phone=phase4_setup["phone_normalised"],
            raw_message="ABSENT",
            command="ABSENT",
            command_args={},
            whatsapp_message_id="msg_absent_2",
        )

        InboundCommandProcessor.process(inbound)

        mock_reply.assert_called_once()
        sent_text = mock_reply.call_args[1]["text"]
        assert "Invalid format" in sent_text or "Endabika si ntuufu" in sent_text

    @patch("messaging.services.InboundCommandProcessor._send_or_queue_reply")
    def test_absent_invalid_date_format_returns_error(self, mock_reply, phase4_setup):
        """ABSENT with wrong date format sends validation error instead of false success."""
        from messaging.services import InboundCommandProcessor
        from messaging.models import InboundMessage

        inbound = InboundMessage.objects.create(
            school=phase4_setup["school"],
            from_phone=phase4_setup["phone_normalised"],
            raw_message="ABSENT 15-02-2026 Sick",
            command="ABSENT",
            command_args={"date": "15-02-2026", "reason": "Sick"},
            whatsapp_message_id="msg_absent_3",
        )

        InboundCommandProcessor.process(inbound)

        mock_reply.assert_called_once()
        sent_text = mock_reply.call_args[1]["text"]
        assert "Invalid date format" in sent_text or "Akabonero k'ennaku si ntuufu" in sent_text

    @patch("messaging.services.InboundCommandProcessor._send_or_queue_reply")
    def test_absent_success_marks_attendance(self, mock_reply, phase4_setup):
        """A valid ABSENT command marks the student as excused for that date in the DB."""
        from messaging.services import InboundCommandProcessor
        from messaging.models import InboundMessage
        from attendance.models import AttendanceRecord

        inbound = InboundMessage.objects.create(
            school=phase4_setup["school"],
            from_phone=phase4_setup["phone_normalised"],
            raw_message="ABSENT 2026-02-20 Funeral",
            command="ABSENT",
            command_args={"date": "2026-02-20", "reason": "Funeral"},
            whatsapp_message_id="msg_absent_4",
        )

        InboundCommandProcessor.process(inbound)

        # Check DB
        rec = AttendanceRecord.all_objects.get(
            student=phase4_setup["student"], date=datetime.date(2026, 2, 20)
        )
        assert rec.status == "excused"
        assert rec.pre_excused is True
        assert rec.pre_excused_reason == "Funeral"

    @patch("messaging.services.InboundCommandProcessor._send_or_queue_reply")
    def test_absent_bilingual_luganda(self, mock_reply, phase4_setup):
        """Luganda-preferred guardian gets Luganda replies."""
        from messaging.services import InboundCommandProcessor
        from messaging.models import InboundMessage

        # Set guardian preference to Luganda
        phase4_setup["guardian"].preferred_language = "lg"
        phase4_setup["guardian"].save()

        inbound = InboundMessage.objects.create(
            school=phase4_setup["school"],
            from_phone=phase4_setup["phone_normalised"],
            raw_message="7 2026-02-22 Malaria",
            command="ABSENT",
            command_args={"date": "2026-02-22", "reason": "Malaria"},
            whatsapp_message_id="msg_absent_5",
        )

        InboundCommandProcessor.process(inbound)

        mock_reply.assert_called_once()
        sent_text = mock_reply.call_args[1]["text"]
        assert "Obutaliwo bwa Bruno M ku 2026-02-22 buwandiikiddwa" in sent_text


# ---------------------------------------------------------------------------
# RISK-P4B: Celery ETA Deduplication Tests
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestCeleryEtaDeduplication:

    @patch("celery.current_app.control.revoke")
    @patch("messaging.tasks.send_fee_reminder.apply_async")
    def test_reschedule_revokes_old_tasks(self, mock_apply, mock_revoke, phase4_setup):
        """Calling reschedule_term_reminders revokes previously scheduled task IDs and creates new ones."""
        from automation.tasks import schedule_fee_reminders, reschedule_term_reminders
        from automation.models import ScheduledReminder
        from payments.models import FeeRecord

        # Create FeeRecord
        fr = FeeRecord.all_objects.create(
            school=phase4_setup["school"],
            student=phase4_setup["student"],
            academic_term=phase4_setup["term"],
            total_amount=Decimal("300000"),
        )

        # Mock celery task apply_async to return fake task IDs
        task_ids = ["task-14d", "task-7d", "task-3d", "task-1d"]
        task_idx = 0
        def side_effect(*args, **kwargs):
            nonlocal task_idx
            mock_task = MagicMock()
            mock_task.id = task_ids[task_idx]
            task_idx += 1
            return mock_task

        mock_apply.side_effect = side_effect

        # 1. Schedule first time
        schedule_fee_reminders(str(phase4_setup["term"].id))
        assert ScheduledReminder.objects.filter(academic_term=phase4_setup["term"]).count() == 4

        # 2. Reschedule
        reschedule_term_reminders(str(phase4_setup["term"].id))

        # Check celery revoke was called for the old task IDs
        mock_revoke.assert_called_once_with(task_ids, terminate=False)


# ---------------------------------------------------------------------------
# RISK-P4C: Health Endpoints Info-Leak Masking
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestHealthEndpointsFingerprinting:

    def test_liveness_endpoint_hides_latency(self):
        """GET /health/ does not expose latency_ms."""
        client = APIClient()
        resp = client.get("/health/")
        assert resp.status_code in (200, 503)
        data = resp.json()
        assert "status" in data
        assert "timestamp" in data
        assert "latency_ms" not in data

    def test_readiness_endpoint_hides_checks_detail(self):
        """GET /health/ready/ does not expose checks dict, latency_ms or environment/version info."""
        client = APIClient()
        resp = client.get("/health/ready/")
        assert resp.status_code in (200, 207, 503)
        data = resp.json()
        assert set(data.keys()) == {"status", "timestamp"}
        assert "checks" not in data
        assert "version" not in data
        assert "environment" not in data

    def test_version_endpoint_hides_django_version(self):
        """GET /health/version/ does not expose django_version."""
        client = APIClient()
        resp = client.get("/health/version/")
        assert resp.status_code == 200
        data = resp.json()
        assert "version" in data
        assert "commit" in data
        assert "django_version" not in data
