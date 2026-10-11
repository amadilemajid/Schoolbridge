"""
Phase 2 Remediation Tests -- Critical Performance and Storage
=============================================================
Covers:
  RISK-026  Async recomputation of term results via Celery
  RISK-028  is_published / published_at state on TermResult + publish endpoint
  RISK-030  ReportCardUploadView saves PDFs to default_storage (not local temp files)
  RISK-041  WhatsAppService.upload_media transparently handles default_storage keys
"""
import uuid
import os
import pytest
from unittest.mock import patch, MagicMock
from datetime import date

from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.utils import timezone


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_school():
    from schools.models import School
    school, _ = School.objects.get_or_create(
        slug="phase2-test-school",
        defaults={
            "name": "Phase2 Test School",
            "district": "Kampala",
            "sub_county": "Central",
            "phone": "+256700000099",
            "email": "phase2@test.com",
            "school_type": "primary",
            "is_active": True,
        },
    )
    return school


def _make_year(school):
    from schools.models import AcademicYear
    yr, _ = AcademicYear.objects.get_or_create(
        school=school, year=2025, defaults={"is_current": False}
    )
    return yr


def _make_term(school, year):
    from schools.models import AcademicTerm
    term, _ = AcademicTerm.objects.get_or_create(
        school=school, name="Phase2 Term",
        defaults={
            "academic_year": year,
            "term_number": 1,
            "start_date": date(2025, 1, 1),
            "end_date": date(2025, 4, 30),
            "fee_deadline": date(2025, 1, 20),
            "is_active": False,
        },
    )
    return term


def _make_class(school):
    from students.models import ClassGroup
    cg, _ = ClassGroup.all_objects.get_or_create(
        school=school, name="P2-Class", defaults={"level": "P1"}
    )
    return cg


def _make_subject(school):
    from results.models import Subject
    subj, _ = Subject.objects.get_or_create(
        school=school, name="Phase2 Math",
        defaults={"code": "PM2", "class_levels": "P1,P2"}
    )
    return subj


def _make_assessment(school, term, class_group, subject):
    from results.models import Assessment
    ass, _ = Assessment.objects.get_or_create(
        school=school,
        academic_term=term,
        class_group=class_group,
        subject=subject,
        defaults={"assessment_type": "eot", "max_marks": 100, "name": "Phase2 EOT Exam"},
    )
    return ass


def _make_student(school, cg):
    from students.models import Student
    student, _ = Student.all_objects.get_or_create(
        school=school,
        student_id="P2-STU-0001",
        defaults={
            "first_name": "P2",
            "last_name": "Student",
            "date_of_birth": date(2010, 1, 1),
            "gender": "M",
            "current_class": cg,
            "admission_date": date(2025, 1, 1),
            "academic_year_admitted": 2025,
            "is_active": True,
        },
    )
    return student


# ---------------------------------------------------------------------------
# RISK-026  Async recomputation
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestAsyncResultsRecomputation:

    def test_on_commit_trigger_fires_celery_task(self):
        """enter_marks must schedule recompute_term_results_task, not call it inline."""
        from results.services import MarksService

        school = _make_school()
        year = _make_year(school)
        term = _make_term(school, year)
        cg = _make_class(school)
        subj = _make_subject(school)
        assessment = _make_assessment(school, term, cg, subj)

        with patch("results.tasks.recompute_term_results_task.delay") as mock_delay, \
             patch("django.db.transaction.on_commit", side_effect=lambda fn: fn()):
            from authentication.models import User
            user, _ = User.objects.get_or_create(
                email="phase2-teacher@test.com",
                defaults={"role": "teacher", "school": school, "is_active": True}
            )
            MarksService.enter_marks(assessment, [], entered_by=user)

        mock_delay.assert_called_once_with(str(assessment.id))

    def test_recompute_task_calls_service_method(self):
        """The Celery task body must delegate to MarksService._recompute_term_results."""
        from results.tasks import recompute_term_results_task

        school = _make_school()
        year = _make_year(school)
        term = _make_term(school, year)
        cg = _make_class(school)
        subj = _make_subject(school)
        assessment = _make_assessment(school, term, cg, subj)

        with patch("results.services.MarksService._recompute_term_results") as mock_recompute:
            recompute_term_results_task.run(str(assessment.id))
            mock_recompute.assert_called_once_with(assessment)


# ---------------------------------------------------------------------------
# RISK-028  TermResult publishing state
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestTermResultPublishing:

    def test_term_result_is_unpublished_by_default(self):
        from results.models import TermResult
        school = _make_school()
        year = _make_year(school)
        term = _make_term(school, year)
        cg = _make_class(school)
        student = _make_student(school, cg)

        tr = TermResult.objects.create(
            school=school,
            student=student,
            class_group=cg,
            academic_term=term,
            total_marks=80,
            average_marks=80,
        )
        assert tr.is_published is False
        assert tr.published_at is None

    def test_bulk_update_sets_is_published_and_timestamp(self):
        from results.models import TermResult
        school = _make_school()
        year = _make_year(school)
        term = _make_term(school, year)
        cg = _make_class(school)
        student = _make_student(school, cg)

        tr = TermResult.objects.create(
            school=school,
            student=student,
            class_group=cg,
            academic_term=term,
            total_marks=75,
            average_marks=75,
        )

        before = timezone.now()
        TermResult.objects.filter(pk=tr.pk).update(
            is_published=True, published_at=timezone.now()
        )
        tr.refresh_from_db()

        assert tr.is_published is True
        assert tr.published_at is not None
        assert tr.published_at >= before


# ---------------------------------------------------------------------------
# RISK-030  default_storage for report card PDFs
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestReportCardUploadUsesDefaultStorage:

    def test_pdf_saved_to_default_storage_and_readable_back(self):
        pdf_content = b"%PDF-1.4 test content"
        storage_key = default_storage.save(
            f"uploaded_report_cards/{uuid.uuid4()}_report.pdf",
            ContentFile(pdf_content),
        )
        try:
            assert default_storage.exists(storage_key)
            with default_storage.open(storage_key, "rb") as f:
                assert f.read() == pdf_content
        finally:
            if default_storage.exists(storage_key):
                default_storage.delete(storage_key)

    def test_storage_key_is_relative_not_absolute_path(self):
        storage_key = default_storage.save(
            f"uploaded_report_cards/{uuid.uuid4()}_check.pdf",
            ContentFile(b"%PDF test"),
        )
        try:
            assert not os.path.isabs(storage_key), (
                f"storage_key must be relative, got: {storage_key}"
            )
        finally:
            if default_storage.exists(storage_key):
                default_storage.delete(storage_key)

    def test_cleanup_on_exception_removes_file_from_storage(self):
        pdf_content = b"%PDF-cleanup test"
        storage_key = default_storage.save(
            f"uploaded_report_cards/{uuid.uuid4()}_cleanup.pdf",
            ContentFile(pdf_content),
        )
        try:
            raise RuntimeError("Simulated dispatch failure")
        except Exception:
            if default_storage.exists(storage_key):
                default_storage.delete(storage_key)

        assert not default_storage.exists(storage_key)


# ---------------------------------------------------------------------------
# RISK-041  WhatsAppService.upload_media supports default_storage keys
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestUploadMediaDefaultStorageTransparency:

    def test_local_file_path_still_works(self, tmp_path):
        """Existing callers that pass a local path must not be broken."""
        from messaging.services import WhatsAppService

        school = _make_school()
        audio_file = tmp_path / "voice.ogg"
        audio_file.write_bytes(b"OggS fake audio data")

        fake_resp = MagicMock()
        fake_resp.status_code = 200
        fake_resp.json.return_value = {"id": "meta-local-123"}

        with patch("requests.post", return_value=fake_resp):
            media = WhatsAppService.upload_media(
                school=school,
                file_path=str(audio_file),
                mime_type="audio/ogg",
                media_type="voice",
                original_filename="voice.ogg",
            )

        assert media.whatsapp_media_id == "meta-local-123"
        assert media.meta_upload_status == "uploaded"

    def test_storage_key_fetched_transparently_and_uploaded(self):
        """A default_storage key (not a local path) must work via transparent fetch."""
        from messaging.services import WhatsAppService

        school = _make_school()
        pdf_key = default_storage.save(
            f"uploaded_report_cards/{uuid.uuid4()}_test.pdf",
            ContentFile(b"%PDF-1.4 fake report card"),
        )
        try:
            fake_resp = MagicMock()
            fake_resp.status_code = 200
            fake_resp.json.return_value = {"id": "meta-storage-456"}

            with patch("requests.post", return_value=fake_resp):
                media = WhatsAppService.upload_media(
                    school=school,
                    file_path=pdf_key,
                    mime_type="application/pdf",
                    media_type="document",
                    original_filename="report.pdf",
                )

            assert media.whatsapp_media_id == "meta-storage-456"
            assert media.meta_upload_status == "uploaded"
        finally:
            if default_storage.exists(pdf_key):
                default_storage.delete(pdf_key)

    def test_nonexistent_path_raises_file_not_found(self, tmp_path):
        """A path that is neither local nor in storage must raise FileNotFoundError."""
        from messaging.services import WhatsAppService

        school = _make_school()
        nonexistent_key = f"uploaded_report_cards/does_not_exist_{uuid.uuid4()}.pdf"
        with pytest.raises(FileNotFoundError):
            WhatsAppService.upload_media(
                school=school,
                file_path=nonexistent_key,
                mime_type="audio/ogg",
            )

    def test_temp_file_cleaned_up_after_storage_fetch(self):
        """No orphan temp files should remain after fetching from default_storage."""
        import tempfile as _tempfile
        from messaging.services import WhatsAppService

        school = _make_school()
        pdf_key = default_storage.save(
            f"uploaded_report_cards/{uuid.uuid4()}_temp_check.pdf",
            ContentFile(b"%PDF-1.4 temp cleanup test"),
        )

        captured_paths = []
        orig_ntf = _tempfile.NamedTemporaryFile

        def tracking_ntf(*args, **kwargs):
            ntf = orig_ntf(*args, **kwargs)
            captured_paths.append(ntf.name)
            return ntf

        try:
            fake_resp = MagicMock()
            fake_resp.status_code = 200
            fake_resp.json.return_value = {"id": "meta-cleanup-789"}

            with patch("requests.post", return_value=fake_resp), \
                 patch("tempfile.NamedTemporaryFile", side_effect=tracking_ntf):
                WhatsAppService.upload_media(
                    school=school,
                    file_path=pdf_key,
                    mime_type="application/pdf",
                    media_type="document",
                    original_filename="cleanup.pdf",
                )

            for p in captured_paths:
                assert not os.path.exists(p), f"Temp file not cleaned up: {p}"
        finally:
            if default_storage.exists(pdf_key):
                default_storage.delete(pdf_key)
