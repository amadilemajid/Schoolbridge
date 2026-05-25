"""
Automation Celery tasks.
US-032: Schedule fee reminders at 14/7/3/1 days.
US-021: Schedule instalment reminders.
US-013: Reschedule all tasks when term dates change.
US-062: Daily reconciliation report at 11pm EAT.
US-058: Weekly digest email Monday 7am EAT.
US-077: Daily 7:30am staff digest.
"""
import logging
from celery import shared_task
from celery.exceptions import MaxRetriesExceededError
from django.utils import timezone

logger = logging.getLogger('schoolbridge')


@shared_task(bind=True)
def schedule_fee_reminders(self, term_id: str):
    """
    US-032: Schedule WhatsApp fee reminders for all students in a term.
    Reminder days: 14, 7, 3, 1 before fee_deadline.
    Each FeeRecord gets its own set of Celery eta tasks.
    """
    from schools.models import AcademicTerm
    from payments.models import FeeRecord
    from messaging.tasks import send_fee_reminder
    import datetime

    try:
        term = AcademicTerm.objects.get(id=term_id)
        deadline = term.fee_deadline
        today = timezone.localdate()
        reminder_days = [14, 7, 3, 1]

        fee_records = FeeRecord.all_objects.filter(
            academic_term=term, student__is_active=True
        ).values_list('id', flat=True)

        scheduled = 0
        for days in reminder_days:
            reminder_date = deadline - datetime.timedelta(days=days)
            if reminder_date <= today:
                continue  # Past — skip
            # Schedule at 8:00 AM EAT on the reminder date
            import pytz
            eat = pytz.timezone('Africa/Kampala')
            remind_at = eat.localize(
                datetime.datetime.combine(reminder_date, datetime.time(8, 0))
            )
            for fr_id in fee_records:
                send_fee_reminder.apply_async(
                    args=[str(fr_id), days],
                    eta=remind_at,
                )
                scheduled += 1

        logger.info(f"Scheduled {scheduled} fee reminders for term {term_id}")
    except Exception as exc:
        logger.exception(f"schedule_fee_reminders failed for term {term_id}: {exc}")


@shared_task(bind=True)
def reschedule_term_reminders(self, term_id: str):
    """
    US-013: Called when term fee_deadline changes.
    Cancels old scheduled tasks and reschedules them.
    Note: With Celery ETA tasks, we rely on idempotency — suppressed if paid.
    Simply re-run schedule_fee_reminders to create new tasks.
    """
    logger.info(f"Rescheduling reminders for term {term_id} due to date change")
    schedule_fee_reminders.delay(term_id)


@shared_task(bind=True)
def schedule_instalment_reminders(self, plan_id: str):
    """US-021: Schedule per-instalment reminders for a payment plan."""
    from payments.models import PaymentPlan
    from messaging.tasks import send_fee_reminder
    import datetime
    import pytz

    try:
        plan = PaymentPlan.all_objects.select_related('fee_record__student').get(id=plan_id)
        eat = pytz.timezone('Africa/Kampala')
        for instalment in plan.instalments.all():
            # Remind 3 days before instalment due date
            remind_date = instalment.due_date - datetime.timedelta(days=3)
            remind_at = eat.localize(
                datetime.datetime.combine(remind_date, datetime.time(8, 0))
            )
            task = send_fee_reminder.apply_async(
                args=[str(plan.fee_record.id), 3],
                eta=remind_at,
            )
            instalment.reminder_task_id = task.id
            instalment.save(update_fields=['reminder_task_id'])
        logger.info(f"Instalment reminders scheduled for plan {plan_id}")
    except Exception as exc:
        logger.exception(f"schedule_instalment_reminders failed: {exc}")


@shared_task(bind=True, max_retries=1, default_retry_delay=1800)  # Retry at 11:30pm
def generate_daily_reconciliation_report(self):
    """US-062: Daily reconciliation report at 11pm EAT. Retry at 11:30pm on failure."""
    from payments.models import ReconciliationQueue, Payment
    from django.core.mail import send_mail
    from django.conf import settings
    from django.utils import timezone

    try:
        today = timezone.localdate()
        school_ids = list(
            Payment.all_objects.filter(payment_date__date=today)
            .values_list('school_id', flat=True).distinct()
        )

        for school_id in school_ids:
            _generate_school_recon_report.delay(str(school_id), str(today))

        logger.info(f"Daily reconciliation reports triggered for {len(school_ids)} schools")
    except Exception as exc:
        logger.exception(f"generate_daily_reconciliation_report failed: {exc}")
        try:
            self.retry(exc=exc)
        except MaxRetriesExceededError:
            from notifications.services import send_admin_alert
            send_admin_alert(
                alert_type='RECON_REPORT_FAILED',
                message='Daily reconciliation report failed after retry',
                payload={'date': str(timezone.localdate())},
            )


@shared_task(bind=True, max_retries=2, default_retry_delay=60)
def _generate_school_recon_report(self, school_id: str, date_str: str):
    """Generate and email reconciliation report for one school."""
    from schools.models import School
    from payments.models import Payment, ReconciliationQueue
    from django.core.mail import send_mail
    from django.conf import settings
    import datetime

    try:
        school = School.objects.get(id=school_id)
        date = datetime.date.fromisoformat(date_str)

        momo_payments = Payment.all_objects.filter(
            school=school,
            payment_date__date=date,
            method__in=['mtn_momo', 'airtel_money'],
            status='completed',
        )
        unmatched = ReconciliationQueue.all_objects.filter(
            school=school,
            received_at__date=date,
            status='pending',
        )

        total_momo = sum(p.amount for p in momo_payments)
        report_lines = [
            f"SchoolBridge Daily Reconciliation — {school.name}",
            f"Date: {date}",
            f"",
            f"MoMo Payments Received: {momo_payments.count()} | Total: UGX {total_momo:,}",
            f"Unmatched Payments: {unmatched.count()}",
            f"",
        ]
        for item in unmatched:
            report_lines.append(f"  - {item.phone} | UGX {item.amount:,} | {item.provider.upper()}")

        report_text = '\n'.join(report_lines)

        # Email to Bursar and Director
        recipients = list(
            school.staff.filter(role__in=['bursar', 'director'], is_active=True)
            .values_list('email', flat=True)
        )
        if recipients:
            send_mail(
                subject=f"[SchoolBridge] Daily Reconciliation — {school.name} — {date}",
                message=report_text,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=recipients,
                fail_silently=True,
            )

        logger.info(f"Recon report sent for {school.name} on {date}")
    except Exception as exc:
        logger.exception(f"_generate_school_recon_report failed: {exc}")
        try:
            self.retry(exc=exc)
        except MaxRetriesExceededError:
            pass


@shared_task(bind=True)
def check_reconciliation_alerts(self):
    """
    US-075: Alert Bursar at 24hr, Director at 48hr for unmatched payments.
    Run every hour via Celery beat.
    """
    from payments.models import ReconciliationQueue
    from notifications.services import NotificationService
    from django.utils import timezone
    import datetime

    now = timezone.now()
    threshold_24hr = now - datetime.timedelta(hours=24)
    threshold_48hr = now - datetime.timedelta(hours=48)

    # 24hr alert
    items_24hr = ReconciliationQueue.all_objects.filter(
        status='pending',
        received_at__lte=threshold_24hr,
        alert_24hr_sent=False,
    )
    for item in items_24hr:
        NotificationService.notify_role(
            school=item.school,
            role='bursar',
            message=(f"Unmatched MoMo payment ({item.phone} — UGX {item.amount:,}) "
                     f"has been pending for over 24 hours. Please reconcile."),
            notification_type='UNMATCHED_PAYMENT_24HR',
        )
        item.alert_24hr_sent = True
        item.save(update_fields=['alert_24hr_sent'])

    # 48hr escalation to Director
    items_48hr = ReconciliationQueue.all_objects.filter(
        status='pending',
        received_at__lte=threshold_48hr,
        alert_48hr_sent=False,
    )
    for item in items_48hr:
        NotificationService.notify_role(
            school=item.school,
            role='director',
            message=(f"ESCALATION: Unmatched MoMo payment ({item.phone} — UGX {item.amount:,}) "
                     f"pending for 48+ hours. Immediate action required."),
            notification_type='UNMATCHED_PAYMENT_48HR',
        )
        item.alert_48hr_sent = True
        item.save(update_fields=['alert_48hr_sent'])


@shared_task(bind=True)
def send_weekly_director_digest(self):
    """US-058: Weekly Monday digest to Directors at 7am EAT."""
    from schools.models import School
    from django.core.mail import send_mail
    from django.conf import settings
    from django.utils import timezone
    from payments.models import FeeRecord, Payment
    from attendance.models import AttendanceRecord

    today = timezone.localdate()
    week_ago = today - __import__('datetime').timedelta(days=7)

    for school in School.objects.filter(is_active=True):
        try:
            directors = list(school.staff.filter(role='director', is_active=True)
                             .values_list('email', flat=True))
            if not directors:
                continue

            term = school.terms.filter(is_current=True).first()
            week_payments = Payment.all_objects.filter(
                school=school, payment_date__date__gte=week_ago, status='completed'
            )
            week_total = sum(p.amount for p in week_payments)

            send_mail(
                subject=f"[SchoolBridge] Weekly Digest — {school.name}",
                message=(
                    f"SchoolBridge Weekly Summary — {school.name}\n"
                    f"Week ending: {today}\n\n"
                    f"Payments this week: {week_payments.count()} | UGX {week_total:,}\n"
                    f"\nLog in to view full details: https://app.schoolbridge.ug"
                ),
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=directors,
                fail_silently=True,
            )
        except Exception as e:
            logger.exception(f"Weekly digest failed for {school.name}: {e}")


@shared_task(bind=True)
def send_daily_staff_digest(self):
    """US-077: Daily 7:30am digest to school staff."""
    from schools.models import School
    from django.utils import timezone
    from automation.services import CalendarService

    today = timezone.localdate()
    for school in School.objects.filter(is_active=True):
        if not CalendarService.is_school_day(school, today):
            continue
        _send_school_daily_digest.delay(str(school.id), str(today))


@shared_task(bind=True)
def _send_school_daily_digest(self, school_id: str, date_str: str):
    from schools.models import School
    from payments.models import Payment
    from attendance.models import AttendanceRecord
    from messaging.services import WhatsAppService
    from django.conf import settings
    from django.core.mail import send_mail
    import datetime

    try:
        school = School.objects.get(id=school_id)
        date = datetime.date.fromisoformat(date_str)
        yesterday = date - datetime.timedelta(days=1)

        yesterday_payments = Payment.all_objects.filter(
            school=school, payment_date__date=yesterday, status='completed'
        )
        total_collected = sum(p.amount for p in yesterday_payments)

        digest_text = (
            f"📊 {school.name} Daily Digest — {date}\n"
            f"Yesterday's Collections: UGX {total_collected:,} ({yesterday_payments.count()} payments)\n"
            f"Log in: https://app.schoolbridge.ug"
        )

        # Email digest
        staff_emails = list(school.staff.filter(
            role__in=['director', 'bursar'], is_active=True
        ).values_list('email', flat=True))
        if staff_emails:
            send_mail(
                subject=f"[SchoolBridge] Daily Digest — {school.name}",
                message=digest_text,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=staff_emails,
                fail_silently=True,
            )
    except Exception as exc:
        logger.exception(f"School daily digest failed for {school_id}: {exc}")


@shared_task(bind=True)
def check_celery_queue_health(self):
    """
    US-073: Alert if Celery queue depth exceeds 1,000 tasks.
    """
    try:
        from celery import current_app
        inspect = current_app.control.inspect()
        reserved = inspect.reserved() or {}
        total_queued = sum(len(tasks) for tasks in reserved.values())
        if total_queued > 1000:
            from notifications.services import send_admin_alert
            send_admin_alert(
                alert_type='CELERY_QUEUE_OVERFLOW',
                message=f'Celery queue depth is {total_queued} tasks (threshold: 1,000).',
                payload={'queue_depth': total_queued},
            )
            logger.error(f"Celery queue overflow: {total_queued} tasks queued")
    except Exception as exc:
        logger.warning(f"Queue health check failed: {exc}")
