"""Celery tasks for student operations."""
import logging
from celery import shared_task
from celery.exceptions import MaxRetriesExceededError

logger = logging.getLogger('schoolbridge')


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def process_bulk_import(self, job_id: str):
    """US-008: Process bulk CSV import in background."""
    try:
        from .models import BulkImportJob
        from .services import StudentImportService
        job = BulkImportJob.objects.get(id=job_id)
        service = StudentImportService(job)
        service.run()
        logger.info(f"Bulk import {job_id} complete: {job.imported_count} imported")
    except Exception as exc:
        logger.error(f"Bulk import {job_id} failed: {exc}")
        try:
            self.retry(exc=exc)
        except MaxRetriesExceededError:
            from .models import BulkImportJob
            BulkImportJob.objects.filter(id=job_id).update(status='failed')
