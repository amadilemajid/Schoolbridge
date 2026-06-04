"""
US-C01: Escalation Engine Service.
Handles 5-level reminder escalation with increasing urgency.
"""
import logging
from datetime import timedelta
from decimal import Decimal
from django.db import transaction
from django.utils import timezone
from .escalation_models import ReminderEscalation, ReminderEscalationLog

logger = logging.getLogger('payments')


class EscalationEngine:
    """
    US-C01: 5-level escalation engine.
    
    Escalation schedule (days before deadline):
    - Level 1: 21 days (gentle)
    - Level 2: 14 days (friendly reminder)
    - Level 3: 7 days (firm + Director notification)
    - Level 4: 3 days (urgent + Bursar notification)
    - Level 5: 1 day (final notice)
    """
    
    ESCALATION_SCHEDULE = {
        1: 21,  # 21 days before deadline
        2: 14,  # 14 days
        3: 7,   # 7 days + Director alert
        4: 3,   # 3 days + Bursar alert
        5: 1,   # Final notice
    }

    @classmethod
    @transaction.atomic
    def initialize_escalations_for_term(cls, term):
        """
        Create escalation schedules for all fee records in a term.
        Called when term is activated or fee deadline changes.
        """
        from payments.models import FeeRecord
        
        deadline = term.fee_deadline
        today = timezone.localdate()
        
        fee_records = FeeRecord.all_objects.filter(
            academic_term=term,
            student__is_active=True
        ).select_related('student', 'school')
        
        created_count = 0
        for fee_record in fee_records:
            for level, days_before in cls.ESCALATION_SCHEDULE.items():
                scheduled_date = deadline - timedelta(days=days_before)
                
                # Skip if date is in the past
                if scheduled_date < today:
                    continue
                
                escalation, created = ReminderEscalation.all_objects.get_or_create(
                    fee_record=fee_record,
                    level=level,
                    defaults={
                        'school': fee_record.school,
                        'academic_term': term,
                        'scheduled_date': scheduled_date,
                        'status': 'scheduled',
                    }
                )
                
                if created:
                    created_count += 1
        
        logger.info(
            f"Initialized {created_count} escalation reminders for term {term.name}"
        )
        return created_count

    @classmethod
    @transaction.atomic
    def suppress_escalations_for_payment(cls, fee_record):
        """
        Cancel pending escalations when payment brings balance to zero.
        Called after successful payment application.
        """
        if not fee_record.is_fully_paid:
            return 0
        
        pending = ReminderEscalation.all_objects.filter(
            fee_record=fee_record,
            status='scheduled'
        )
        
        count = pending.update(
            status='suppressed',
            suppressed_at=timezone.now(),
            suppression_reason='balance_paid'
        )
        
        logger.info(
            f"Suppressed {count} escalations for {fee_record.student} - balance cleared"
        )
        return count

    @classmethod
    def get_message_template(cls, level, language, student_name, balance, 
                            deadline_str, days_remaining, school_name):
        """
        Get escalation message for specified level and language.
        Returns (subject_emoji, message_text).
        """
        templates = {
            'english': {
                1: {
                    'emoji': '📝',
                    'tone': 'Gentle Reminder',
                    'message': (
                        f"📝 *Gentle Reminder*\n\n"
                        f"Hello! This is a friendly reminder about {student_name}'s "
                        f"school fees.\n\n"
                        f"Current Balance: UGX {balance:,}\n"
                        f"Payment Deadline: {deadline_str}\n"
                        f"Days Remaining: {days_remaining}\n\n"
                        f"Reply BALANCE for details or PLAN for payment options.\n"
                        f"Thank you for your cooperation.\n\n"
                        f"— {school_name}"
                    )
                },
                2: {
                    'emoji': '💬',
                    'tone': 'Friendly Reminder',
                    'message': (
                        f"💬 *Friendly Reminder*\n\n"
                        f"We kindly remind you about {student_name}'s outstanding fees.\n\n"
                        f"Amount Due: UGX {balance:,}\n"
                        f"Deadline: {deadline_str} ({days_remaining} days left)\n\n"
                        f"Please arrange payment at your earliest convenience.\n"
                        f"Reply PLAN if you need a payment arrangement.\n\n"
                        f"— {school_name}"
                    )
                },
                3: {
                    'emoji': '⚠️',
                    'tone': 'Important Notice',
                    'message': (
                        f"⚠️ *Important Fee Notice*\n\n"
                        f"Dear Parent/Guardian,\n\n"
                        f"We urgently request payment of {student_name}'s school fees.\n\n"
                        f"Outstanding Balance: UGX {balance:,}\n"
                        f"Deadline: {deadline_str}\n"
                        f"Only {days_remaining} days remaining\n\n"
                        f"Continued delays may affect your child's learning experience.\n"
                        f"Please contact the school immediately if you need assistance.\n\n"
                        f"Reply PLAN for payment options.\n\n"
                        f"— {school_name} Administration"
                    )
                },
                4: {
                    'emoji': '🚨',
                    'tone': 'Urgent Notice',
                    'message': (
                        f"🚨 *URGENT FEE NOTICE*\n\n"
                        f"This is an urgent reminder regarding {student_name}'s unpaid fees.\n\n"
                        f"Amount Outstanding: UGX {balance:,}\n"
                        f"Payment Deadline: {deadline_str}\n"
                        f"⚠️ ONLY {days_remaining} DAYS LEFT\n\n"
                        f"IMMEDIATE ACTION REQUIRED\n"
                        f"Please settle this balance urgently to avoid consequences.\n\n"
                        f"Contact the Bursar's office: Reply HELP for details\n\n"
                        f"— {school_name} Bursar"
                    )
                },
                5: {
                    'emoji': '❗',
                    'tone': 'Final Notice',
                    'message': (
                        f"❗ *FINAL FEE NOTICE*\n\n"
                        f"FINAL REMINDER: {student_name}'s school fees remain unpaid.\n\n"
                        f"Balance Due: UGX {balance:,}\n"
                        f"Deadline: {deadline_str} (TOMORROW)\n\n"
                        f"⚠️ THIS IS YOUR LAST NOTICE ⚠️\n\n"
                        f"Payment must be received by the deadline to avoid:\n"
                        f"• Academic consequences\n"
                        f"• Restricted school access\n"
                        f"• Additional penalties\n\n"
                        f"Contact school IMMEDIATELY: Reply HELP\n\n"
                        f"— {school_name} Director's Office"
                    )
                }
            },
            'luganda': {
                1: {
                    'emoji': '📝',
                    'tone': 'Okujjukiza Obulungi',
                    'message': (
                        f"📝 *Okujjukiza Obulungi*\n\n"
                        f"Ki kati! Tukujjukiza ku ssente z'essomero za {student_name}.\n\n"
                        f"Ssente Ezisigadde: UGX {balance:,}\n"
                        f"Olunaku Olw'okumaliriza: {deadline_str}\n"
                        f"Ennaku Ezisigadde: {days_remaining}\n\n"
                        f"Wandiika BALANCE okufuna ebisingawo oba PLAN okusaba enkola y'okusasula.\n"
                        f"Weebale nnyo.\n\n"
                        f"— {school_name}"
                    )
                },
                2: {
                    'emoji': '💬',
                    'tone': 'Okujjukiza Mu Ngeri Ennungi',
                    'message': (
                        f"💬 *Okujjukiza*\n\n"
                        f"Tukujjukiza mu ngeri ey'ekisa ku ssente za {student_name} ezisigadde.\n\n"
                        f"Ssente: UGX {balance:,}\n"
                        f"Olunaku: {deadline_str} (ennaku {days_remaining})\n\n"
                        f"Tusaba ossemu ssente mu biseera ebisemberayo.\n"
                        f"Wandiika PLAN bw'oba oyagala enkola y'okusasula.\n\n"
                        f"— {school_name}"
                    )
                },
                3: {
                    'emoji': '⚠️',
                    'tone': 'Obubaka Obukulu',
                    'message': (
                        f"⚠️ *Obubaka Obukulu ku Ssente*\n\n"
                        f"Omuzadde/Omukuza,\n\n"
                        f"Tusaba n'obwangu okusasula ssente za {student_name}.\n\n"
                        f"Ssente Ezisigadde: UGX {balance:,}\n"
                        f"Olunaku: {deadline_str}\n"
                        f"Ennaku {days_remaining} zokka\n\n"
                        f"Okulwawo kuyinza okukosa okuyiga kw'omwana wo.\n"
                        f"Tusaba otubeereko mangu bw'oba oyetaaga obuyambi.\n\n"
                        f"Wandiika PLAN okufuna enkola.\n\n"
                        f"— {school_name}"
                    )
                },
                4: {
                    'emoji': '🚨',
                    'tone': 'Obubaka Obw\'amangu',
                    'message': (
                        f"🚨 *OBUBAKA BW'AMANGU*\n\n"
                        f"Kino kye kujjukiza okw'amangu ku ssente za {student_name}.\n\n"
                        f"Ssente: UGX {balance:,}\n"
                        f"Olunaku: {deadline_str}\n"
                        f"⚠️ ENNAKU {days_remaining} ZOKKA\n\n"
                        f"KINO KYETAAGISA EKIKOLWA KYA MANGU\n"
                        f"Tusaba ossemu ssente buno obwangu.\n\n"
                        f"Tuddiikira: Wandiika HELP\n\n"
                        f"— {school_name}"
                    )
                },
                5: {
                    'emoji': '❗',
                    'tone': 'Obubaka Obw\'enkomerero',
                    'message': (
                        f"❗ *OBUBAKA BW'ENKOMERERO*\n\n"
                        f"OKUJJUKIZA KW'ENKOMERERO: Ssente za {student_name} tezinnasasulwa.\n\n"
                        f"Ssente: UGX {balance:,}\n"
                        f"Olunaku: {deadline_str} (ENKYA)\n\n"
                        f"⚠️ KINO KYE KIRAGIRO KYO EKISEMBAYO ⚠️\n\n"
                        f"Ssente zirina okusasulwa okusobola okwewala:\n"
                        f"• Ebizibu mu kusoma\n"
                        f"• Okuziyizibwa okuyingira essomero\n"
                        f"• Ebibonerezo ebirala\n\n"
                        f"Tuddiikira MANGU: Wandiika HELP\n\n"
                        f"— {school_name}"
                    )
                }
            }
        }
        
        lang = language.lower()
        if lang not in templates:
            lang = 'english'
        
        template = templates[lang].get(level, templates[lang][1])
        return template['emoji'], template['message']

    @classmethod
    def get_due_escalations(cls, date=None):
        """
        Query escalations due to be sent on specified date (default: today).
        Returns queryset of ReminderEscalation.
        """
        if date is None:
            date = timezone.localdate()
        
        return ReminderEscalation.all_objects.filter(
            scheduled_date=date,
            status='scheduled'
        ).select_related(
            'fee_record',
            'fee_record__student',
            'fee_record__student__current_class',
            'school',
            'academic_term'
        ).prefetch_related(
            'fee_record__student__guardians'
        )

    @classmethod
    def should_notify_director(cls, level):
        """Level 3+ notifies Director."""
        return level >= 3

    @classmethod
    def should_notify_bursar(cls, level):
        """Level 4+ notifies Bursar."""
        return level >= 4
