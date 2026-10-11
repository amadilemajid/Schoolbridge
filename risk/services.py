"""
At-Risk Student Intelligence Engine — Service Layer.

Modular evaluation pipeline with individual factor checkers.
Each checker can independently flag a student and contribute to the composite risk score.

Extension architecture:
  - Add new _check_* methods for behaviour/academics
  - Each returns metrics and appends to factors/scores lists
  - No changes needed to the aggregation logic
"""
import logging
from decimal import Decimal, ROUND_HALF_UP

from django.db import transaction
from django.db.models import Count, Q
from django.utils import timezone


from attendance.models import AttendanceRecord
from payments.models import FeeRecord, PaymentPlan, PaymentPlanInstalment
from students.models import Student

logger = logging.getLogger('schoolbridge')


class RiskEvaluationEngine:
    """Production-grade risk evaluation with modular factor checkers."""

    # ──────────────────────────────────────────────
    # Single Student Evaluation
    # ──────────────────────────────────────────────
    @classmethod
    def evaluate_student(cls, student, term, config, attendance_data=None, fee_record=None, has_compliant_plan=None):
        """
        Evaluate a single student's risk profile against config thresholds.
        Returns the updated/created StudentRiskProfile instance.
        """
        from risk.models import StudentRiskProfile

        factors = []
        scores = []

        # Factor 1: Attendance
        att_rate, total_days, days_absent = cls._check_attendance(
            student, term, config, factors, scores, attendance_data
        )

        # Factor 2: Fee payment
        payment_ratio, balance = cls._check_fees(
            student, term, config, factors, scores, fee_record, has_compliant_plan
        )

        # [Extension Hook] Factor 3: Behaviour incidents
        # cls._check_behaviour(student, term, config, factors, scores)

        # [Extension Hook] Factor 4: Academic performance
        # cls._check_academics(student, term, config, factors, scores)

        # ── Aggregate ──
        final_score = min(100, sum(scores))

        if final_score >= 70:
            risk_level = 'high'
        elif final_score >= 40:
            risk_level = 'medium'
        else:
            risk_level = 'low'

        profile, _ = StudentRiskProfile.all_objects.update_or_create(
            student=student,
            academic_term=term,
            defaults={
                'school': student.school,
                'attendance_rate': att_rate,
                'total_days_recorded': total_days,
                'days_absent': days_absent,
                'fee_payment_ratio': payment_ratio,
                'fee_balance': balance,
                'risk_score': final_score,
                'risk_level': risk_level,
                'flagged_factors': factors,
            }
        )
        return profile

    # ──────────────────────────────────────────────
    # Factor Checkers
    # ──────────────────────────────────────────────
    @classmethod
    def _check_attendance(cls, student, term, config, factors, scores, attendance_data=None):
        """
        Evaluate attendance rate against threshold.
        Returns (attendance_rate, total_days, days_absent).
        """
        if attendance_data is not None:
            total_days, days_absent = attendance_data
        else:
            records = AttendanceRecord.all_objects.filter(
                student=student, academic_term=term
            )
            total_days = records.count()
            days_absent = records.filter(status='absent').count()

        if total_days < config.grace_period_days:
            # Not enough data — skip evaluation
            return Decimal('100.00'), total_days, 0

        days_present = total_days - days_absent  # present + late + excused

        att_rate = (
            Decimal(days_present) / Decimal(total_days) * 100
        ).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

        attendance_threshold = Decimal(str(config.attendance_threshold))
        if att_rate < attendance_threshold:
            factors.append('low_attendance')
            gap = float(attendance_threshold - att_rate)
            # Scale: 25% gap → 50 points (max contribution from attendance)
            score_contribution = min(50, int(gap * 2))
            scores.append(score_contribution)

        return att_rate, total_days, days_absent

    @classmethod
    def _check_fees(cls, student, term, config, factors, scores, fee_record=None, has_compliant_plan=None):
        """
        Evaluate fee payment ratio and outstanding balance.
        Returns (payment_ratio, outstanding_balance).
        """
        if fee_record is None:
            try:
                fee_record = FeeRecord.all_objects.get(
                    student=student, academic_term=term
                )
            except FeeRecord.DoesNotExist:
                return Decimal('100.00'), Decimal('0')

        total = fee_record.total_amount
        paid = fee_record.amount_paid
        balance = fee_record.balance

        if total > 0:
            ratio = (
                Decimal(paid) / Decimal(total) * 100
            ).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        else:
            ratio = Decimal('100.00')

        is_flagged = False

        fee_payment_ratio_threshold = Decimal(str(config.fee_payment_ratio_threshold))
        if has_compliant_plan is None:
            has_plan = cls._has_compliant_payment_plan(student, term)
        else:
            has_plan = has_compliant_plan
        
        # Check ratio threshold
        if ratio < fee_payment_ratio_threshold and not has_plan:
            is_flagged = True

        # Check absolute balance threshold
        if balance > config.outstanding_balance_threshold and not has_plan:
            is_flagged = True

        if is_flagged:
            factors.append('fee_defaulter')
            fee_gap = float(fee_payment_ratio_threshold - ratio)
            score_contribution = min(50, max(10, int(fee_gap * 1.0)))
            scores.append(score_contribution)

        return ratio, balance

    @classmethod
    def _has_compliant_payment_plan(cls, student, term):
        """
        Check if student has an active payment plan with no overdue instalments.
        If so, their fee risk contribution is bypassed.
        """
        try:
            fee_record = FeeRecord.all_objects.get(
                student=student, academic_term=term
            )
            plan = PaymentPlan.all_objects.get(
                fee_record=fee_record, status='active'
            )
            has_overdue = PaymentPlanInstalment.objects.filter(
                payment_plan=plan, status='overdue'
            ).exists()
            return not has_overdue
        except (FeeRecord.DoesNotExist, PaymentPlan.DoesNotExist):
            return False

    # ──────────────────────────────────────────────
    # Batch School Recalculation
    # ──────────────────────────────────────────────
    @classmethod
    @transaction.atomic
    def recalculate_school(cls, school, term):
        """
        Batch recalculate risk metrics for all active students in a school.
        Creates/updates profiles and weekly snapshots.
        """
        from risk.models import RiskConfiguration, StudentRiskSnapshot

        config, _ = RiskConfiguration.objects.get_or_create(school=school)
        students = Student.all_objects.filter(
            school=school, is_active=True
        ).select_related('current_class')

        # --- Bulk prefetch to avoid N+1 queries ---
        # 1. Fetch attendance stats in a single query
        attendance_stats = AttendanceRecord.all_objects.filter(
            school=school, academic_term=term
        ).values('student_id').annotate(
            total_days=Count('id'),
            days_absent=Count('id', filter=Q(status='absent'))
        )
        attendance_map = {
            stat['student_id']: (stat['total_days'], stat['days_absent'])
            for stat in attendance_stats
        }

        # 2. Fetch fee records in a single query
        fee_records = FeeRecord.all_objects.filter(
            school=school, academic_term=term
        )
        fee_map = {
            record.student_id: record
            for record in fee_records
        }

        # 3. Fetch active payment plans and identify which ones have overdue installments
        active_plans = PaymentPlan.all_objects.filter(
            fee_record__school=school,
            fee_record__academic_term=term,
            status='active'
        ).select_related('fee_record')
        
        overdue_plan_ids = set(
            PaymentPlanInstalment.objects.filter(
                payment_plan__fee_record__school=school,
                payment_plan__fee_record__academic_term=term,
                payment_plan__status='active',
                status='overdue'
            ).values_list('payment_plan_id', flat=True).distinct()
        )
        
        compliant_plans_map = {
            plan.fee_record.student_id: (plan.id not in overdue_plan_ids)
            for plan in active_plans
        }

        snapshot_date = timezone.localdate()
        profiles = []

        for student in students:
            student_att = attendance_map.get(student.id, (0, 0))
            student_fee = fee_map.get(student.id)
            has_compliant_plan = compliant_plans_map.get(student.id, False)

            profile = cls.evaluate_student(
                student=student,
                term=term,
                config=config,
                attendance_data=student_att,
                fee_record=student_fee,
                has_compliant_plan=has_compliant_plan
            )
            profiles.append(profile)

            # Save weekly snapshot for trend analysis
            StudentRiskSnapshot.all_objects.update_or_create(
                student=student,
                academic_term=term,
                snapshot_date=snapshot_date,
                defaults={
                    'school': school,
                    'attendance_rate': profile.attendance_rate,
                    'fee_payment_ratio': profile.fee_payment_ratio,
                    'risk_score': profile.risk_score,
                    'risk_level': profile.risk_level,
                    'flagged_factors': profile.flagged_factors,
                }
            )

        logger.info(
            f"Risk recalculation complete for {school.name}: "
            f"{len(profiles)} students evaluated"
        )
        return profiles

    # ──────────────────────────────────────────────
    # Monday Morning Briefing
    # ──────────────────────────────────────────────
    @classmethod
    def get_monday_briefing(cls, school, term):
        """Generate Monday morning briefing summary for the Director."""
        from risk.models import StudentRiskProfile

        profiles = StudentRiskProfile.all_objects.filter(
            school=school, academic_term=term
        ).select_related('student', 'student__current_class')

        high_risk = profiles.filter(risk_level='high')
        medium_risk = profiles.filter(risk_level='medium')

        summary = {
            'school': school.name,
            'term': term.name,
            'generated_at': timezone.now().isoformat(),
            'total_students_evaluated': profiles.count(),
            'high_risk_count': high_risk.count(),
            'medium_risk_count': medium_risk.count(),
            'low_risk_count': profiles.filter(risk_level='low').count(),
            'high_risk_students': [],
        }

        for p in high_risk.order_by('-risk_score')[:20]:
            summary['high_risk_students'].append({
                'student_name': p.student.get_full_name(),
                'student_id': p.student.student_id,
                'class': (
                    p.student.current_class.name
                    if p.student.current_class else 'N/A'
                ),
                'risk_score': p.risk_score,
                'factors': p.flagged_factors,
                'attendance_rate': (
                    float(p.attendance_rate) if p.attendance_rate else None
                ),
                'fee_balance': int(p.fee_balance) if p.fee_balance else 0,
            })

        return summary

    @classmethod
    def format_briefing_whatsapp(cls, summary):
        """Format the Monday briefing as a WhatsApp-friendly text message."""
        lines = [
            f"📊 *Monday At-Risk Briefing*",
            f"*{summary['school']}* — {summary['term']}",
            "",
            f"📋 Total Students Evaluated: {summary['total_students_evaluated']}",
            f"🔴 High Risk: {summary['high_risk_count']}",
            f"🟡 Medium Risk: {summary['medium_risk_count']}",
            f"🟢 Low Risk: {summary['low_risk_count']}",
        ]

        if summary['high_risk_students']:
            lines.append("")
            lines.append("*⚠️ Top High-Risk Students:*")
            for i, s in enumerate(summary['high_risk_students'][:10], 1):
                factors_text = ", ".join(
                    f.replace('_', ' ') for f in s['factors']
                )
                lines.append(
                    f"{i}. *{s['student_name']}* ({s['class']}) "
                    f"— Score: {s['risk_score']}/100"
                )
                lines.append(f"   📍 {factors_text}")
        else:
            lines.append("")
            lines.append("✅ No students are currently at high risk.")

        lines.append("")
        lines.append("_Log in to the dashboard for full details._")

        return "\n".join(lines)
