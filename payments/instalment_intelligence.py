"""
US-C05: Smart Instalment Reminders & Default Risk Intelligence Service.
Calculates default risk scores, determines reminder urgency levels, and escalates repeated missed instalments to Director.
"""
import logging
from decimal import Decimal
from django.utils import timezone
from payments.models import PaymentPlan, PaymentPlanInstalment

logger = logging.getLogger('payments')


class InstalmentIntelligenceService:
    """
    US-C05 Intelligence Engine for fee payment plans.
    """

    @classmethod
    def calculate_default_risk_score(cls, payment_plan):
        """
        Calculate default risk score (0 to 100) for a payment plan.
        Higher score = higher likelihood of defaulting on remaining instalments.
        
        Factors:
        - Ratio of overdue instalments vs total instalments (40%)
        - Percentage of total amount remaining unpaid (30%)
        - Guardian payment compliance history (30%)
        """
        if not payment_plan:
            return 0.0

        total_instalments = payment_plan.instalments.count()
        if total_instalments == 0:
            return 0.0

        # Factor 1: Overdue ratio
        overdue_count = payment_plan.instalments.filter(status='overdue').count()
        overdue_ratio = overdue_count / float(total_instalments)
        overdue_score = overdue_ratio * 40.0

        # Factor 2: Unpaid amount ratio
        total_amount = float(payment_plan.total_amount or 1)
        paid_amount = float(sum(i.amount_paid for i in payment_plan.instalments.all()))
        unpaid_ratio = max(0.0, (total_amount - paid_amount) / total_amount)
        unpaid_score = unpaid_ratio * 30.0

        # Factor 3: Missed/Overdue history across all student plans
        student = payment_plan.student
        all_plans = PaymentPlan.all_objects.filter(student=student)
        historical_overdue = PaymentPlanInstalment.objects.filter(
            payment_plan__in=all_plans,
            status='overdue'
        ).count()
        history_score = min(30.0, historical_overdue * 10.0)

        risk_score = min(100.0, overdue_score + unpaid_score + history_score)
        return round(risk_score, 1)

    @classmethod
    def get_reminder_urgency_level(cls, payment_plan, instalment):
        """
        Determine reminder urgency tier: 'low', 'medium', 'high', 'critical'.
        """
        risk_score = cls.calculate_default_risk_score(payment_plan)
        today = timezone.localdate()
        days_until_due = (instalment.due_date - today).days

        if days_until_due < 0 or instalment.status == 'overdue':
            return 'critical' if risk_score > 50 else 'high'
        elif days_until_due <= 1:
            return 'high' if risk_score > 40 else 'medium'
        elif days_until_due <= 3:
            return 'medium' if risk_score > 30 else 'low'
        else:
            return 'low'

    @classmethod
    def check_and_escalate_to_director(cls, payment_plan):
        """
        Escalate to Director if pattern shows repeated missed instalments or high default risk (>60).
        """
        risk_score = cls.calculate_default_risk_score(payment_plan)
        overdue_count = payment_plan.instalments.filter(status='overdue').count()

        if overdue_count >= 2 or risk_score >= 60.0:
            from messaging.services import WhatsAppService

            director_phone = getattr(payment_plan.school, 'director_phone', None) or getattr(payment_plan.school, 'phone', None)

            if director_phone:
                message = (
                    f"🚨 *DIRECTOR ESCALATION: Fee Default Risk Alert*\n\n"
                    f"School: {payment_plan.school.name}\n"
                    f"Student: {payment_plan.student.first_name} {payment_plan.student.last_name}\n"
                    f"Default Risk Score: {risk_score}/100\n"
                    f"Overdue Instalments: {overdue_count}\n"
                    f"Remaining Balance: UGX {payment_plan.total_amount:,}\n\n"
                    f"Action Required: Direct follow-up advised."
                )
                WhatsAppService.send_text_message(to_phone=director_phone, text=message, school=payment_plan.school)
                logger.info(f"Director escalation sent for student {payment_plan.student} (Risk: {risk_score})")
                return True
        return False
