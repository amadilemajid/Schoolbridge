"""Results Celery tasks — report card generation."""
import logging
from celery import shared_task
from celery.exceptions import MaxRetriesExceededError

logger = logging.getLogger('schoolbridge')


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def generate_single_report_card(self, term_result_id: str, level: str):
    """US-043/044/045: Generate PDF report card and notify parent."""
    from results.models import TermResult
    from results.services import ReportCardService
    from django.core.files.base import ContentFile
    from django.utils import timezone

    try:
        result = TermResult.all_objects.select_related(
            'student', 'school', 'academic_term', 'class_group'
        ).get(id=term_result_id)

        # Pick correct report card generator based on class level
        level_upper = (level or '').upper().strip()
        if 'P7' in level_upper or level_upper == 'P7':
            buffer, division, aggregate = ReportCardService.generate_ple_report_card(result)
        elif 'S4' in level_upper or level_upper == 'S4':
            buffer, division, aggregate = ReportCardService.generate_uce_report_card(result)
        else:
            # Generic report card for P1–P6, S1–S3, S5–S6, and any other level (US-045)
            buffer, division, aggregate = ReportCardService.generate_generic_report_card(result)


        pdf_filename = f"report_card_{result.student.student_id}_{result.academic_term_id}.pdf"
        result.report_card_pdf.save(pdf_filename, ContentFile(buffer.read()), save=False)
        result.report_card_generated_at = timezone.now()
        if division:
            result.division = division
        if aggregate:
            result.aggregate = aggregate
        result.save(update_fields=[
            'report_card_pdf', 'report_card_generated_at', 'division', 'aggregate'
        ])

        # Notify parent via WhatsApp (US-047)
        notify_parent_report_ready.delay(str(result.id))
        logger.info(f"Report card generated for {result.student}")
    except Exception as exc:
        logger.exception(f"generate_single_report_card failed for {term_result_id}: {exc}")
        try:
            self.retry(exc=exc)
        except MaxRetriesExceededError:
            pass


@shared_task(bind=True, max_retries=2, default_retry_delay=60)
def notify_parent_report_ready(self, term_result_id: str):
    """US-047: Notify parent via WhatsApp that report card is ready (signed link)."""
    from results.models import TermResult
    from messaging.services import WhatsAppService

    try:
        result = TermResult.all_objects.select_related(
            'student', 'school', 'academic_term'
        ).get(id=term_result_id)

        guardian = result.student.guardians.filter(is_primary=True).first()
        if not guardian:
            return

        pdf_url = result.report_card_pdf.url if result.report_card_pdf else None
        if not pdf_url:
            return

        text = (
            f"📄 *Report Card Ready*\n\n"
            f"{result.student.get_full_name()}'s report card for {result.academic_term.name} "
            f"is now available.\n\n"
            f"Division: *{result.division or 'N/A'}*\n"
            f"Rank: {result.class_rank} of {result.total_students}\n\n"
            f"View: {pdf_url}\n"
            f"(Link valid for 30 days)"
        )
        if WhatsAppService.is_paused():
            WhatsAppService.queue_whatsapp_message(
                school=result.school,
                student=result.student,
                recipient_phone=guardian.phone_normalised,
                message_body=text,
                template_type='report_card_ready',
            )
            logger.warning(f"WhatsApp paused; queued report card notification for {term_result_id}")
            return
        WhatsAppService.send_text_message(to_phone=guardian.phone_normalised, text=text)
        result.parent_notified = True
        result.save(update_fields=['parent_notified'])
    except Exception as exc:
        logger.exception(f"notify_parent_report_ready failed for {term_result_id}: {exc}")
        try:
            self.retry(exc=exc)
        except MaxRetriesExceededError:
            pass


@shared_task(bind=True, max_retries=3, default_retry_delay=30)
def recompute_term_results_task(self, assessment_id: str):
    """Asynchronously recompute term results after marks entry."""
    from results.models import Assessment
    from results.services import MarksService

    try:
        assessment = Assessment.all_objects.get(id=assessment_id)
        MarksService._recompute_term_results(assessment)
        logger.info(f"Asynchronously recomputed term results for assessment {assessment_id}")
    except Exception as exc:
        logger.exception(f"recompute_term_results_task failed for {assessment_id}: {exc}")
        try:
            self.retry(exc=exc)
        except MaxRetriesExceededError:
            pass
