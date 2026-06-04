# Epic-C Setup Instructions

## Quick Start

Follow these steps to deploy Epic-C features to your SchoolBridge installation.

---

## 1. Update payments/models.py

Add these import statements at the **top** of `payments/models.py`:

```python
# Epic-C model imports
from .escalation_models import ReminderEscalation, ReminderEscalationLog
from .payment_link_models import PaymentLink
from .campaign_models import DefaulterCampaign, DefaulterCampaignTarget
```

---

## 2. Run Database Migrations

```bash
# Create migration files
python manage.py makemigrations payments

# Apply migrations
python manage.py migrate payments
```

**Expected output:**
```
Migrations for 'payments':
  payments/migrations/0002_epic_c_features.py
    - Create model ReminderEscalation
    - Create model ReminderEscalationLog
    - Create model PaymentLink
    - Create model DefaulterCampaign
    - Create model DefaulterCampaignTarget
    
Running migrations:
  Applying payments.0002_epic_c_features... OK
```

---

## 3. Add Signal Handlers

Create `payments/signals.py` if it doesn't exist:

```python
"""
Payment signal handlers for Epic-C features.
"""
from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import Payment
from .escalation_service import EscalationEngine
from .campaign_service import DefaulterCampaignService


@receiver(post_save, sender=Payment)
def handle_payment_saved(sender, instance, created, **kwargs):
    """
    US-C01: Suppress escalations when balance paid.
    US-C04: Track campaign payment responses.
    """
    if instance.status == 'completed' and instance.fee_record:
        # Suppress escalations if fully paid
        if instance.fee_record.is_fully_paid:
            EscalationEngine.suppress_escalations_for_payment(instance.fee_record)
        
        # Track campaign responses
        DefaulterCampaignService.track_payment_response(instance)
```

Register signals in `payments/apps.py`:

```python
class PaymentsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'payments'

    def ready(self):
        import payments.signals  # Register signal handlers
```

---

## 4. Update Celery Beat Schedule

Add to `automation/management/commands/setup_periodic_tasks.py` or your Celery config:

```python
from celery.schedules import crontab

# Epic-C Celery Beat Tasks
CELERYBEAT_SCHEDULE.update({
    # US-C01: Daily escalation reminder processing
    'process-daily-escalations': {
        'task': 'payments.escalation_tasks.process_daily_escalations',
        'schedule': crontab(hour=8, minute=0),  # 8:00 AM EAT daily
    },
    
    # US-C03: Expire old payment links every hour
    'expire-old-payment-links': {
        'task': 'payments.payment_link_tasks.expire_old_links',
        'schedule': crontab(hour='*', minute=0),  # Every hour
    },
    
    # US-C04: Execute scheduled defaulter campaigns
    'execute-scheduled-campaigns': {
        'task': 'payments.campaign_tasks.execute_scheduled_campaigns',
        'schedule': crontab(minute='*/15'),  # Every 15 minutes
    },
})
```

Create `payments/payment_link_tasks.py`:

```python
"""Payment link Celery tasks."""
from celery import shared_task
from .payment_link_service import PaymentLinkService

@shared_task
def expire_old_links():
    """Mark expired payment links."""
    return PaymentLinkService.expire_old_links()
```

Restart Celery workers and beat:

```bash
# Stop existing workers
pkill -f celery

# Start Celery worker
celery -A schoolbridge worker -l info &

# Start Celery beat
celery -A schoolbridge beat -l info &
```

---

## 5. Initialize Escalations for Existing Terms

Run this management command to create escalation schedules for active terms:

Create `payments/management/commands/initialize_escalations.py`:

```python
"""Initialize escalation schedules for active terms."""
from django.core.management.base import BaseCommand
from schools.models import AcademicTerm
from payments.escalation_service import EscalationEngine


class Command(BaseCommand):
    help = 'Initialize escalation schedules for active terms'

    def handle(self, *args, **options):
        active_terms = AcademicTerm.objects.filter(is_current=True)
        
        for term in active_terms:
            count = EscalationEngine.initialize_escalations_for_term(term)
            self.stdout.write(
                self.style.SUCCESS(
                    f'Initialized {count} escalations for {term.school.name} - {term.name}'
                )
            )
```

Run it:

```bash
python manage.py initialize_escalations
```

---

## 6. Register Models in Django Admin

Add to `payments/admin.py`:

```python
from django.contrib import admin
from .escalation_models import ReminderEscalation, ReminderEscalationLog
from .payment_link_models import PaymentLink
from .campaign_models import DefaulterCampaign, DefaulterCampaignTarget


@admin.register(ReminderEscalation)
class ReminderEscalationAdmin(admin.ModelAdmin):
    list_display = ['level', 'fee_record', 'scheduled_date', 'status', 
                   'director_notified', 'bursar_notified', 'sent_at']
    list_filter = ['status', 'level', 'scheduled_date', 'school']
    search_fields = ['fee_record__student__first_name', 
                    'fee_record__student__last_name']
    readonly_fields = ['created_at', 'updated_at', 'sent_at', 'suppressed_at']
    date_hierarchy = 'scheduled_date'
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            'fee_record__student', 'school', 'academic_term'
        )


@admin.register(ReminderEscalationLog)
class ReminderEscalationLogAdmin(admin.ModelAdmin):
    list_display = ['escalation', 'recipient_phone', 'language', 
                   'delivery_status', 'sent_at']
    list_filter = ['language', 'delivery_status', 'sent_at']
    search_fields = ['recipient_phone', 'escalation__fee_record__student__first_name']
    readonly_fields = ['sent_at']
    date_hierarchy = 'sent_at'


@admin.register(PaymentLink)
class PaymentLinkAdmin(admin.ModelAdmin):
    list_display = ['student', 'amount', 'status', 'expires_at', 
                   'accessed_count', 'used_at']
    list_filter = ['status', 'created_at', 'expires_at']
    search_fields = ['student__first_name', 'student__last_name', 
                    'token', 'recipient_phone']
    readonly_fields = ['token', 'full_url', 'created_at', 'used_at', 
                      'accessed_count']
    date_hierarchy = 'created_at'
    
    fieldsets = (
        ('Link Details', {
            'fields': ('token', 'full_url', 'amount', 'description', 'status')
        }),
        ('Student & School', {
            'fields': ('school', 'student', 'fee_record')
        }),
        ('Recipient', {
            'fields': ('recipient_phone', 'recipient_name')
        }),
        ('Expiry & Usage', {
            'fields': ('expires_at', 'accessed_count', 'used_at', 'payment')
        }),
        ('Metadata', {
            'fields': ('created_by', 'created_at', 'cancelled_by', 'cancelled_at')
        }),
    )


@admin.register(DefaulterCampaign)
class DefaulterCampaignAdmin(admin.ModelAdmin):
    list_display = ['name', 'segment_type', 'status', 'target_count', 
                   'sent_count', 'success_rate', 'collection_rate', 
                   'scheduled_at']
    list_filter = ['status', 'segment_type', 'created_at', 'school']
    search_fields = ['name', 'description']
    readonly_fields = ['target_count', 'sent_count', 'delivered_count', 
                      'failed_count', 'success_rate', 'collection_rate',
                      'total_balance_targeted', 'payments_received',
                      'started_at', 'completed_at', 'created_at', 'updated_at']
    date_hierarchy = 'scheduled_at'
    
    fieldsets = (
        ('Campaign Details', {
            'fields': ('name', 'description', 'school', 'academic_term', 'status')
        }),
        ('Segmentation', {
            'fields': ('segment_type', 'min_balance', 'max_balance', 'target_classes')
        }),
        ('Message Templates', {
            'fields': ('message_template_en', 'message_template_lg')
        }),
        ('Scheduling', {
            'fields': ('scheduled_at', 'started_at', 'completed_at')
        }),
        ('Execution Stats', {
            'fields': ('target_count', 'sent_count', 'delivered_count', 
                      'failed_count', 'success_rate')
        }),
        ('Financial Impact', {
            'fields': ('total_balance_targeted', 'payments_received', 'collection_rate')
        }),
        ('Metadata', {
            'fields': ('created_by', 'created_at', 'updated_at')
        }),
    )
    
    filter_horizontal = ['target_classes']


@admin.register(DefaulterCampaignTarget)
class DefaulterCampaignTargetAdmin(admin.ModelAdmin):
    list_display = ['campaign', 'student', 'balance_at_send', 'status', 
                   'payment_made', 'sent_at']
    list_filter = ['status', 'language', 'payment_made', 'sent_at']
    search_fields = ['student__first_name', 'student__last_name', 
                    'guardian_phone', 'campaign__name']
    readonly_fields = ['sent_at', 'delivered_at', 'created_at']
    date_hierarchy = 'sent_at'
```

---

## 7. Test the Implementation

### Test Escalations:

```python
# Django shell
python manage.py shell

from schools.models import AcademicTerm
from payments.escalation_service import EscalationEngine

# Get current term
term = AcademicTerm.objects.filter(is_current=True).first()

# Initialize escalations
count = EscalationEngine.initialize_escalations_for_term(term)
print(f"Created {count} escalation reminders")

# Check due escalations for today
from django.utils import timezone
due = EscalationEngine.get_due_escalations(timezone.localdate())
print(f"Escalations due today: {due.count()}")
```

### Test Payment Links:

```python
from payments.models import FeeRecord
from payments.payment_link_service import PaymentLinkService

# Get a fee record with balance
fr = FeeRecord.all_objects.filter(balance__gt=0).first()

# Generate link
link = PaymentLinkService.generate_link(
    fee_record=fr,
    amount=50000,  # UGX 50,000
    description="Partial payment"
)

print(f"Payment link: {link.full_url}")
print(f"Token: {link.token}")
print(f"Expires: {link.expires_at}")

# Send via WhatsApp
msg_id, success = PaymentLinkService.send_link_via_whatsapp(link)
print(f"WhatsApp sent: {success} (ID: {msg_id})")
```

### Test Campaigns:

```python
from schools.models import School, AcademicTerm
from students.models import ClassGroup
from payments.campaign_service import DefaulterCampaignService

school = School.objects.first()
term = school.terms.filter(is_current=True).first()

# Create high-balance campaign
campaign = DefaulterCampaignService.create_campaign(
    school=school,
    term=term,
    name="Test High Balance Campaign",
    segment_type='high_balance',
    message_template_en=(
        "🚨 URGENT\n\n"
        "{student_name} ({class_name}) has balance: UGX {balance}\n"
        "Deadline: {deadline}\n\n"
        "Please pay urgently.\n— {school_name}"
    ),
    scheduled_at=timezone.now() + timedelta(minutes=5),
)

print(f"Campaign created: {campaign.name}")
print(f"Targets: {campaign.target_count}")
print(f"Total balance: UGX {campaign.total_balance_targeted:,}")

# Execute immediately (or wait for scheduled time)
DefaulterCampaignService.execute_campaign(campaign)
print("Campaign executing...")
```

---

## 8. Monitor Logs

Watch Celery logs for escalation and campaign execution:

```bash
tail -f logs/celery.log | grep -E "(escalation|campaign|payment_link)"
```

Expected log entries:
```
INFO: Escalation L3 sent successfully - John Doe (Balance: UGX 450,000)
INFO: Payment link generated: ABC123... for Jane Doe - UGX 100,000
INFO: Campaign created: High Balance Reminder - 23 targets - Total balance: UGX 6,750,000
INFO: Campaign message sent - High Balance Reminder -> John Doe (+256701234567)
```

---

## 9. Configuration (Optional)

Add these to `settings.py`:

```python
# Payment link base URL
PAYMENT_LINK_BASE_URL = 'https://pay.schoolbridge.ug'

# Escalation settings
ESCALATION_SCHEDULE = {
    1: 21,  # Days before deadline for each level
    2: 14,
    3: 7,
    4: 3,
    5: 1,
}
```

---

## 10. Production Checklist

Before going live:

- [ ] All migrations applied successfully
- [ ] Celery workers and beat running
- [ ] Signal handlers registered
- [ ] Admin interfaces accessible
- [ ] Test escalations sent successfully
- [ ] Test payment links generated and sent
- [ ] Test campaign executed and messages delivered
- [ ] Monitoring/logging configured
- [ ] Staff trained on campaign creation
- [ ] Analytics dashboard ready

---

## Troubleshooting

### Escalations not sending:

1. Check Celery beat is running: `ps aux | grep celery`
2. Verify task is scheduled: Check Django admin > Periodic Tasks
3. Check logs: `tail -f logs/celery.log`
4. Manually trigger: `python manage.py shell` then run `process_daily_escalations()`

### Payment links not working:

1. Verify `PAYMENT_LINK_BASE_URL` in settings
2. Check link expiry: `link.is_usable`
3. Test token validation: `PaymentLinkService.validate_and_get_link(token)`

### Campaigns not executing:

1. Check status is 'scheduled': `campaign.status`
2. Verify `scheduled_at` is in past
3. Check Celery beat task: `execute_scheduled_campaigns`
4. Manually execute: `DefaulterCampaignService.execute_campaign(campaign)`

---

## Support

For issues or questions:
- Email: dev@schoolbridge.ug
- Docs: https://docs.schoolbridge.ug/epic-c
- Slack: #schoolbridge-dev
