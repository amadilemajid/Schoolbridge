"""
US-C04: Defaulter Campaign Service.
Create and execute targeted fee collection campaigns.
"""
import logging
from decimal import Decimal
from django.db import transaction
from django.utils import timezone
from django.db.models import Q
from .campaign_models import DefaulterCampaign, DefaulterCampaignTarget

logger = logging.getLogger('payments')


class DefaulterCampaignService:
    """
    US-C04: Targeted defaulter campaigns with smart segmentation.
    """
    
    # Balance thresholds for segmentation
    HIGH_BALANCE_THRESHOLD = Decimal('500000')  # 500k UGX
    MEDIUM_BALANCE_MIN = Decimal('200000')      # 200k UGX
    MEDIUM_BALANCE_MAX = Decimal('500000')

    @classmethod
    @transaction.atomic
    def create_campaign(cls, *, school, term, name, segment_type,
                       message_template_en, message_template_lg='',
                       min_balance=None, max_balance=None, target_classes=None,
                       created_by=None, scheduled_at=None):
        """
        Create a new defaulter campaign.
        
        Args:
            school: School instance
            term: AcademicTerm instance
            name: Campaign name
            segment_type: Segment choice from SEGMENT_CHOICES
            message_template_en: English message template
            message_template_lg: Luganda message template
            min_balance: Minimum balance filter
            max_balance: Maximum balance filter
            target_classes: List of ClassGroup instances
            created_by: User who created
            scheduled_at: When to send (default: immediate)
            
        Returns:
            DefaulterCampaign instance
        """
        campaign = DefaulterCampaign.all_objects.create(
            school=school,
            academic_term=term,
            name=name,
            segment_type=segment_type,
            message_template_en=message_template_en,
            message_template_lg=message_template_lg,
            min_balance=min_balance,
            max_balance=max_balance,
            scheduled_at=scheduled_at or timezone.now(),
            status='scheduled',
            created_by=created_by,
        )
        
        if target_classes:
            campaign.target_classes.set(target_classes)
        
        # Build target list
        targets = cls._build_target_list(campaign)
        campaign.target_count = len(targets)
        
        # Calculate total balance
        campaign.total_balance_targeted = sum(t['balance'] for t in targets)
        campaign.save(update_fields=['target_count', 'total_balance_targeted'])
        
        # Create target records
        cls._create_targets(campaign, targets)
        
        logger.info(
            f"Campaign created: {name} - {campaign.target_count} targets - "
            f"Total balance: UGX {campaign.total_balance_targeted:,}"
        )
        
        return campaign

    @classmethod
    def _build_target_list(cls, campaign):
        """
        Build list of students matching campaign criteria.
        
        Returns:
            List of dicts with student data
        """
        from payments.models import FeeRecord
        from django.db.models import F
        
        # Base query: all defaulters in term
        qs = FeeRecord.all_objects.filter(
            school=campaign.school,
            academic_term=campaign.academic_term,
            student__is_active=True
        ).annotate(
            calc_balance=F('total_amount') - F('amount_paid') - F('amount_waived')
        ).filter(calc_balance__gt=0).select_related(
            'student',
            'student__current_class'
        ).prefetch_related(
            'student__guardians'
        )
        
        # Apply segment filters
        if campaign.segment_type == 'high_balance':
            qs = qs.filter(calc_balance__gte=cls.HIGH_BALANCE_THRESHOLD)
        
        elif campaign.segment_type == 'medium_balance':
            qs = qs.filter(
                calc_balance__gte=cls.MEDIUM_BALANCE_MIN,
                calc_balance__lt=cls.MEDIUM_BALANCE_MAX
            )
        
        elif campaign.segment_type == 'low_balance':
            qs = qs.filter(calc_balance__lt=cls.MEDIUM_BALANCE_MIN)
        
        elif campaign.segment_type == 'zero_payment':
            qs = qs.filter(amount_paid=0)
        
        elif campaign.segment_type == 'partial_payment':
            qs = qs.filter(amount_paid__gt=0, calc_balance__gt=0)
        
        elif campaign.segment_type == 'specific_class':
            class_ids = campaign.target_classes.values_list('id', flat=True)
            qs = qs.filter(student__current_class_id__in=class_ids)
        
        # Apply custom balance filters
        if campaign.min_balance:
            qs = qs.filter(calc_balance__gte=campaign.min_balance)
        if campaign.max_balance:
            qs = qs.filter(calc_balance__lte=campaign.max_balance)
        
        # Build target list
        targets = []
        for fr in qs:
            guardian = fr.student.guardians.filter(is_primary=True).first()
            if not guardian:
                continue
            
            targets.append({
                'fee_record': fr,
                'student': fr.student,
                'guardian': guardian,
                'balance': fr.calc_balance,
                'class_name': fr.student.current_class.name if fr.student.current_class else 'N/A',
            })
        
        return targets

    @classmethod
    def _create_targets(cls, campaign, targets):
        """
        Create DefaulterCampaignTarget records.
        Fix: now passes parent_name to _build_message.
        Fix: uses ignore_conflicts=True so a re-run won't crash on unique_together.
        """
        target_objs = []

        for t in targets:
            guardian = t['guardian']
            # Fix: Guardian model uses 'en'/'lg' choices, not 'english'/'luganda'
            language = guardian.preferred_language or 'en'
            parent_name = f"{guardian.first_name} {guardian.last_name}".strip() or 'Parent/Guardian'

            message = cls._build_message(
                campaign=campaign,
                student_name=f"{t['student'].first_name} {t['student'].last_name}",
                parent_name=parent_name,
                balance=t['balance'],
                class_name=t['class_name'],
                language=language,
                school_name=campaign.school.name,
            )

            target_objs.append(
                DefaulterCampaignTarget(
                    campaign=campaign,
                    fee_record=t['fee_record'],
                    student=t['student'],
                    guardian_phone=guardian.phone_normalised,
                    balance_at_send=t['balance'],
                    message_sent=message,
                    language=language,
                )
            )

        # ignore_conflicts prevents crash on unique_together ('campaign', 'fee_record')
        # if this method is somehow called twice for the same campaign.
        DefaulterCampaignTarget.objects.bulk_create(target_objs, ignore_conflicts=True)

    @classmethod
    def _build_message(cls, campaign, student_name, parent_name='Parent/Guardian',
                       balance=0, class_name='N/A', language='en', school_name=''):
        """
        Build personalized message from template.

        Fixes:
          1. Added parent_name parameter — was missing, caused KeyError if template
             used {parent_name}.
          2. Bridge bracket-style tags [Student Name] → {student_name} so UI-authored
             templates work without requiring users to learn Python format syntax.
          3. language comparison fixed: Guardian model uses 'en'/'lg', not 'english'/'luganda'.
          4. Wrapped .format() in try/except — any unrecognised placeholder no longer
             crashes the entire campaign.
          5. Added fee_deadline None guard — if term has no deadline, uses empty string.
          6. Added {payment_link} placeholder support.
        """
        # Select template by language
        template = (
            campaign.message_template_lg if language in ('lg', 'luganda')
            else campaign.message_template_en
        ) or campaign.message_template_en

        # Bridge UI bracket-style tags → Python .format() placeholders
        bracket_to_format = {
            '[Student Name]': '{student_name}',
            '[Parent Name]': '{parent_name}',
            '[Balance]': '{balance}',
            '[Class Name]': '{class_name}',
            '[School Name]': '{school_name}',
            '[Deadline]': '{deadline}',
            '[Payment Link]': '{payment_link}',
        }
        for bracket_tag, fmt_tag in bracket_to_format.items():
            template = template.replace(bracket_tag, fmt_tag)

        # Safe deadline string
        deadline_str = ''
        term = campaign.academic_term
        if term and getattr(term, 'fee_deadline', None):
            deadline_str = term.fee_deadline.strftime('%d %b %Y')

        try:
            return template.format(
                student_name=student_name,
                parent_name=parent_name,
                balance=f"{int(balance):,}",
                class_name=class_name,
                school_name=school_name,
                deadline=deadline_str,
                payment_link='schoolbridge.io/pay',
            )
        except (KeyError, ValueError, IndexError) as exc:
            # Fallback: return a safe default message so the campaign still runs
            logger.warning(
                f"Template formatting failed for campaign '{campaign.name}': {exc}. "
                "Using fallback message."
            )
            return (
                f"Dear {parent_name}, your child {student_name} owes "
                f"UGX {int(balance):,}. "
                f"Please clear by {deadline_str or 'end of term'}. — {school_name}"
            )

    @classmethod
    @transaction.atomic
    def execute_campaign(cls, campaign):
        """
        Execute campaign by sending messages to all targets.
        Called by Celery task at scheduled_at time.
        """
        if campaign.status != 'scheduled':
            logger.warning(f"Campaign {campaign.id} not scheduled - status: {campaign.status}")
            return
        
        campaign.status = 'running'
        campaign.started_at = timezone.now()
        campaign.save(update_fields=['status', 'started_at'])
        
        # Queue individual sends
        from .campaign_tasks import send_campaign_message
        
        targets = campaign.targets.filter(status='pending')
        for target in targets:
            send_campaign_message.delay(str(target.id))
        
        logger.info(
            f"Campaign {campaign.name} started - queued {targets.count()} messages"
        )

    @classmethod
    @transaction.atomic
    def complete_campaign(cls, campaign):
        """Mark campaign as completed."""
        campaign.status = 'completed'
        campaign.completed_at = timezone.now()
        campaign.save(update_fields=['status', 'completed_at'])
        
        logger.info(
            f"Campaign {campaign.name} completed - "
            f"Sent: {campaign.sent_count}/{campaign.target_count} - "
            f"Success rate: {campaign.success_rate}%"
        )

    @classmethod
    def track_payment_response(cls, payment):
        """
        Track payments made in response to campaign messages.
        Called after payment is recorded.
        """
        # Find campaigns targeting this student
        targets = DefaulterCampaignTarget.objects.filter(
            student=payment.student,
            campaign__status__in=['running', 'completed'],
            payment_made=False,
            sent_at__lt=payment.payment_date,
        ).select_related('campaign')
        
        for target in targets:
            target.payment_made = True
            target.payment_amount = payment.amount
            target.payment_date = payment.payment_date
            target.save(update_fields=['payment_made', 'payment_amount', 'payment_date'])
            
            # Update campaign totals
            campaign = target.campaign
            campaign.payments_received += payment.amount
            campaign.save(update_fields=['payments_received'])
            
            logger.info(
                f"Campaign {campaign.name} - Payment tracked: UGX {payment.amount:,} "
                f"from {target.student.get_full_name()}"
            )

    @classmethod
    def get_campaign_analytics(cls, campaign):
        """
        Get detailed analytics for a campaign.
        
        Returns dict with:
        - target_count, sent_count, delivered_count, failed_count
        - success_rate, collection_rate
        - payments_received, total_balance_targeted
        - class_breakdown, balance_segment_breakdown
        """
        targets = campaign.targets.all()
        
        # Class breakdown
        from django.db.models import Count, Sum
        class_breakdown = targets.values(
            'student__current_class__name'
        ).annotate(
            count=Count('id'),
            total_balance=Sum('balance_at_send')
        ).order_by('-total_balance')
        
        return {
            'target_count': campaign.target_count,
            'sent_count': campaign.sent_count,
            'delivered_count': campaign.delivered_count,
            'failed_count': campaign.failed_count,
            'success_rate': campaign.success_rate,
            'collection_rate': campaign.collection_rate,
            'payments_received': campaign.payments_received,
            'total_balance_targeted': campaign.total_balance_targeted,
            'class_breakdown': list(class_breakdown),
            'status': campaign.status,
            'started_at': campaign.started_at,
            'completed_at': campaign.completed_at,
        }
