"""
Results services.
US-041: Marks entry with validation and locking.
US-042: Auto-compute totals, rank (<10s for 80 students).
US-043-045: Report card generation (PDF).
US-047: Signed URL delivery to parents via WhatsApp.
"""
import logging
from decimal import Decimal
from django.db import transaction
from django.utils import timezone

logger = logging.getLogger('schoolbridge')


class MarksService:

    @classmethod
    @transaction.atomic
    def enter_marks(cls, assessment, marks_data, entered_by):
        """
        US-041: Enter marks for all students in an assessment.
        marks_data: [{student_id, marks_obtained, is_absent, comment}]
        Validates marks range. Locked assessment raises error.
        """
        from results.models import AssessmentMark
        if assessment.is_locked:
            raise ValueError(f"Assessment '{assessment.name}' is locked. Contact the Director to unlock.")

        saved = []
        for entry in marks_data:
            student_id = entry.get('student_id')
            marks = entry.get('marks_obtained')
            is_absent = entry.get('is_absent', False)

            # Validate marks range (US-041)
            if marks is not None and not is_absent:
                marks = Decimal(str(marks))
                if marks < 0:
                    raise ValueError(f"Marks cannot be negative for student {student_id}.")
                if marks > assessment.max_marks:
                    raise ValueError(
                        f"Marks {marks} exceed maximum {assessment.max_marks} for student {student_id}."
                    )

            mark, _ = AssessmentMark.objects.update_or_create(
                assessment=assessment,
                student_id=student_id,
                defaults={
                    'marks_obtained': marks if not is_absent else None,
                    'is_absent': is_absent,
                    'comment': entry.get('comment', ''),
                    'entered_by': entered_by,
                }
            )
            saved.append(mark)

        # Recompute term results for this class+term
        cls._recompute_term_results(assessment)
        return saved

    @classmethod
    def lock_assessment(cls, assessment, locked_by):
        """US-041: Lock marks after submission."""
        assessment.is_locked = True
        assessment.locked_at = timezone.now()
        assessment.locked_by = locked_by
        assessment.save(update_fields=['is_locked', 'locked_at', 'locked_by'])

    @classmethod
    def unlock_assessment(cls, assessment, unlocked_by):
        """US-041: Unlock — Director only, audit-logged at view level."""
        assessment.is_locked = False
        assessment.locked_at = None
        assessment.locked_by = None
        assessment.save(update_fields=['is_locked', 'locked_at', 'locked_by'])

    @classmethod
    def _recompute_term_results(cls, assessment):
        """US-042: Recompute totals, average, rank for the class. <10s for 80 students."""
        from results.models import Assessment, AssessmentMark, TermResult
        from students.models import Student

        class_group = assessment.class_group
        term = assessment.academic_term
        school = assessment.school

        students = Student.all_objects.filter(
            school=school, current_class=class_group, is_active=True
        )

        student_totals = {}
        for student in students:
            # Sum weighted marks across all assessments for this class+term+subject
            assessments = Assessment.all_objects.filter(
                school=school, academic_term=term, class_group=class_group
            ).prefetch_related('marks')

            total = Decimal('0')
            max_total = Decimal('0')
            for asmt in assessments:
                try:
                    mark = asmt.marks.get(student=student)
                    if not mark.is_absent and mark.marks_obtained is not None:
                        total += mark.marks_obtained * Decimal(str(asmt.weight))
                        max_total += Decimal(str(asmt.max_marks)) * Decimal(str(asmt.weight))
                except AssessmentMark.DoesNotExist:
                    max_total += Decimal(str(asmt.max_marks)) * Decimal(str(asmt.weight))

            avg = (total / max_total * 100) if max_total > 0 else Decimal('0')
            student_totals[str(student.id)] = {
                'student': student, 'total': total, 'average': avg
            }

        # Compute class average
        if student_totals:
            class_avg = sum(v['average'] for v in student_totals.values()) / len(student_totals)
        else:
            class_avg = Decimal('0')

        # Rank students (US-042: ties share the same rank)
        sorted_students = sorted(student_totals.values(), key=lambda x: x['average'], reverse=True)
        ranks = {}
        current_rank = 1
        for i, entry in enumerate(sorted_students):
            if i > 0 and entry['average'] < sorted_students[i - 1]['average']:
                current_rank = i + 1
            ranks[str(entry['student'].id)] = current_rank

        # Save TermResult for each student
        for sid, data in student_totals.items():
            student = data['student']
            TermResult.all_objects.update_or_create(
                student=student,
                academic_term=term,
                defaults={
                    'school': school,
                    'class_group': class_group,
                    'total_marks': data['total'],
                    'average_marks': data['average'],
                    'class_rank': ranks.get(sid),
                    'total_students': len(student_totals),
                    'class_average': class_avg,
                }
            )


class ReportCardService:
    """US-043/044/045: Generate UNEB-compliant PDF report cards."""

    @classmethod
    def generate_ple_report_card(cls, term_result):
        """US-043: PLE (P7) report card — exact UNEB template."""
        from results.grading import get_ple_subject_grade, get_ple_division
        from results.models import AssessmentMark, Assessment
        from reportlab.lib.pagesizes import A4
        from reportlab.lib import colors
        from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.lib.units import cm
        import io

        student = term_result.student
        school = term_result.school
        term = term_result.academic_term

        # Collect subject marks
        subject_grades = []
        assessments = Assessment.all_objects.filter(
            school=school, academic_term=term,
            class_group=term_result.class_group,
        ).select_related('subject').prefetch_related('marks')

        subject_data = {}
        for asmt in assessments:
            try:
                mark = asmt.marks.get(student=student)
                subject_name = asmt.subject.name
                if subject_name not in subject_data:
                    subject_data[subject_name] = {'marks': 0, 'max': 0}
                if not mark.is_absent and mark.marks_obtained:
                    subject_data[subject_name]['marks'] += float(mark.marks_obtained)
                    subject_data[subject_name]['max'] += asmt.max_marks
            except AssessmentMark.DoesNotExist:
                pass

        grade_points = []
        rows = []
        for subject_name, data in subject_data.items():
            pct = (data['marks'] / data['max'] * 100) if data['max'] > 0 else 0
            grade_pt = get_ple_subject_grade(pct)
            grade_points.append(grade_pt)
            grade_letter = ['', 'D', 'C', 'P', 'F'][grade_pt]
            rows.append([subject_name, f"{data['marks']:.0f}/{data['max']}", f"{pct:.1f}%", grade_letter])

        division, aggregate = get_ple_division(grade_points)

        # Build PDF
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=A4,
                                rightMargin=1.5*cm, leftMargin=1.5*cm,
                                topMargin=1.5*cm, bottomMargin=1.5*cm)
        styles = getSampleStyleSheet()
        elements = []

        # Header
        elements.append(Paragraph(f"<b>{school.name.upper()}</b>", styles['Title']))
        elements.append(Paragraph("PRIMARY LEAVING EXAMINATION REPORT CARD", styles['Heading2']))
        elements.append(Spacer(1, 0.3*cm))
        elements.append(Paragraph(f"<b>Student:</b> {student.get_full_name()}", styles['Normal']))
        elements.append(Paragraph(f"<b>Student No:</b> {student.student_id}", styles['Normal']))
        elements.append(Paragraph(f"<b>Class:</b> {term_result.class_group.name}", styles['Normal']))
        elements.append(Paragraph(f"<b>Term:</b> {term.name}", styles['Normal']))
        elements.append(Spacer(1, 0.4*cm))

        # Subject table
        table_data = [['Subject', 'Marks', 'Percentage', 'Grade']] + rows
        table = Table(table_data, colWidths=[6*cm, 3*cm, 3*cm, 2*cm])
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.darkblue),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.lightgrey]),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ('ALIGN', (1, 0), (-1, -1), 'CENTER'),
        ]))
        elements.append(table)
        elements.append(Spacer(1, 0.4*cm))

        # Division and aggregate
        elements.append(Paragraph(f"<b>Aggregate: {aggregate}</b>", styles['Heading3']))
        elements.append(Paragraph(f"<b>Division: {division}</b>", styles['Heading2']))
        elements.append(Spacer(1, 0.3*cm))
        elements.append(Paragraph(
            f"Class Position: {term_result.class_rank} of {term_result.total_students}",
            styles['Normal']
        ))
        elements.append(Paragraph(f"Class Average: {term_result.class_average:.1f}%", styles['Normal']))
        elements.append(Spacer(1, 0.5*cm))
        elements.append(Paragraph(
            "This report is generated by SchoolBridge. "
            "Grades are computed per UNEB PLE guidelines.",
            styles['Italic']
        ))

        doc.build(elements)
        buffer.seek(0)
        return buffer, division, aggregate

    @classmethod
    def generate_uce_report_card(cls, term_result):
        """US-044: UCE (S4) report card — best 8 aggregate, D1–F9."""
        from results.grading import get_uce_grade, get_uce_division
        from results.models import AssessmentMark, Assessment
        from reportlab.lib.pagesizes import A4
        from reportlab.lib import colors
        from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.lib.units import cm
        import io

        student = term_result.student
        school = term_result.school
        term = term_result.academic_term

        assessments = Assessment.all_objects.filter(
            school=school, academic_term=term,
            class_group=term_result.class_group,
        ).select_related('subject').prefetch_related('marks')

        subject_data = {}
        for asmt in assessments:
            try:
                mark = asmt.marks.get(student=student)
                subject_name = asmt.subject.name
                if subject_name not in subject_data:
                    subject_data[subject_name] = {'marks': 0, 'max': 0}
                if not mark.is_absent and mark.marks_obtained:
                    subject_data[subject_name]['marks'] += float(mark.marks_obtained)
                    subject_data[subject_name]['max'] += asmt.max_marks
            except AssessmentMark.DoesNotExist:
                pass

        grade_points = []
        rows = []
        for subject_name, data in subject_data.items():
            pct = (data['marks'] / data['max'] * 100) if data['max'] > 0 else 0
            grade, points = get_uce_grade(pct)
            grade_points.append(points)
            rows.append([subject_name, f"{data['marks']:.0f}/{data['max']}", f"{pct:.1f}%", grade])

        division, aggregate = get_uce_division(grade_points)

        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=A4,
                                rightMargin=1.5*cm, leftMargin=1.5*cm,
                                topMargin=1.5*cm, bottomMargin=1.5*cm)
        styles = getSampleStyleSheet()
        elements = []

        elements.append(Paragraph(f"<b>{school.name.upper()}</b>", styles['Title']))
        elements.append(Paragraph("UGANDA CERTIFICATE OF EDUCATION — REPORT CARD", styles['Heading2']))
        elements.append(Spacer(1, 0.3*cm))
        elements.append(Paragraph(f"<b>Student:</b> {student.get_full_name()}", styles['Normal']))
        elements.append(Paragraph(f"<b>Class:</b> {term_result.class_group.name}", styles['Normal']))
        elements.append(Paragraph(f"<b>Term:</b> {term.name}", styles['Normal']))
        elements.append(Spacer(1, 0.4*cm))

        table_data = [['Subject', 'Marks', 'Percentage', 'Grade']] + rows
        table = Table(table_data, colWidths=[6*cm, 3*cm, 3*cm, 2*cm])
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.darkgreen),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.lightgrey]),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ('ALIGN', (1, 0), (-1, -1), 'CENTER'),
        ]))
        elements.append(table)
        elements.append(Spacer(1, 0.4*cm))
        elements.append(Paragraph(f"<b>Best 8 Aggregate: {aggregate}</b>", styles['Heading3']))
        elements.append(Paragraph(f"<b>Division: {division}</b>", styles['Heading2']))
        elements.append(Paragraph(
            f"Class Position: {term_result.class_rank} of {term_result.total_students}",
            styles['Normal']
        ))
        elements.append(Paragraph(
            "Grades per UNEB UCE guidelines. D1=Distinction, C3-C6=Credit, P7-P8=Pass, F9=Fail.",
            styles['Italic']
        ))
        doc.build(elements)
        buffer.seek(0)
        return buffer, division, aggregate

    @classmethod
    def batch_generate_and_notify(cls, class_group, term, generated_by):
        """
        US-043/044: Batch generate all report cards for a class.
        Runs as Celery task. Notifies parents on completion (US-047).
        """
        from results.models import TermResult
        results = TermResult.all_objects.filter(
            class_group=class_group, academic_term=term
        ).select_related('student', 'school')

        for result in results:
            from results.tasks import generate_single_report_card
            generate_single_report_card.delay(str(result.id), class_group.level)
