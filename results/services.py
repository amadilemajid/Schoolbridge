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
            if isinstance(entry, (str, int)):
                continue
            student_id = entry.get('student_id') or entry.get('student')
            marks = entry.get('marks_obtained')

            is_absent = entry.get('is_absent', False)

            # Validate marks range (US-041)
            if marks is not None and not is_absent:
                try:
                    marks = Decimal(str(marks))
                except Exception:
                    raise ValueError(f"Invalid numeric score '{marks}' for student {student_id}.")
                if marks < 0:
                    raise ValueError(f"Marks cannot be negative ({marks}) for student {student_id}.")
                if marks > assessment.max_marks:
                    raise ValueError(
                        f"Marks ({marks}) exceed maximum ({assessment.max_marks}) for student {student_id}."
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

        # Synchronously recompute class totals, rank, aggregates, and division (US-042)
        try:
            cls._recompute_term_results(assessment)
        except Exception as err:
            logger.warning(f"Sync recompute failed, falling back to background task: {err}")
            from results.tasks import recompute_term_results_task
            transaction.on_commit(lambda: recompute_term_results_task.delay(str(assessment.id)))
        return saved

    @classmethod
    def lock_assessment(cls, assessment, locked_by):
        """US-041: Lock marks after submission."""
        assessment.is_locked = True
        assessment.locked_at = timezone.now()
        assessment.locked_by = locked_by
        if not assessment.status or assessment.status == 'draft':
            assessment.status = 'submitted'
        assessment.save(update_fields=['is_locked', 'locked_at', 'locked_by', 'status'])

    @classmethod
    def unlock_assessment(cls, assessment, unlocked_by):
        """US-041: Unlock — Director only, audit-logged at view level."""
        assessment.is_locked = False
        assessment.locked_at = None
        assessment.locked_by = None
        assessment.status = 'draft'
        assessment.save(update_fields=['is_locked', 'locked_at', 'locked_by', 'status'])

    @classmethod
    def compute_term_aggregates_and_division(cls, student, term):
        """
        US-042: Compute total marks, average, aggregates, and UNEB division for a student in a term.
        P.7 classes use UNEB PLE grading (best 4 subjects).
        S.4 classes use UNEB UCE grading (best 8 subjects).
        Other levels use standard grade thresholds (Div I/II/III/IV/U).
        """
        from results.models import Assessment, AssessmentMark, TermResult
        from results.grading import (
            get_ple_subject_grade, get_ple_division,
            get_uce_grade, get_uce_division,
        )

        class_group = student.current_class
        school = student.school
        assessments = list(Assessment.all_objects.filter(
            school=school, academic_term=term, class_group=class_group
        ).select_related('subject'))

        marks = AssessmentMark.objects.filter(
            assessment__in=assessments, student=student
        ).select_related('assessment', 'assessment__subject')

        total = Decimal('0')
        max_total = Decimal('0')
        subject_scores = {}

        for mark in marks:
            if not mark.is_absent and mark.marks_obtained is not None:
                asmt = mark.assessment
                weight = Decimal(str(asmt.weight))
                total += mark.marks_obtained * weight
                max_total += Decimal(str(asmt.max_marks)) * weight

                subj_key = asmt.subject.code if (asmt.subject and asmt.subject.code) else (asmt.subject.name if asmt.subject else asmt.name)
                if subj_key not in subject_scores:
                    subject_scores[subj_key] = {'score': Decimal('0'), 'max': Decimal('0')}
                subject_scores[subj_key]['score'] += mark.marks_obtained * weight
                subject_scores[subj_key]['max'] += Decimal(str(asmt.max_marks)) * weight

        avg = (total / max_total * 100) if max_total > 0 else Decimal('0')

        division = None
        aggregate = None

        level_str = (class_group.level or class_group.name or '').upper() if class_group else ''
        if 'P7' in level_str or 'P.7' in level_str:
            pts = []
            for s_info in subject_scores.values():
                s_pct = (s_info['score'] / s_info['max'] * 100) if s_info['max'] > 0 else 0
                pts.append(get_ple_subject_grade(s_pct, 100))
            if pts:
                division, aggregate = get_ple_division(pts)
        elif 'S4' in level_str or 'S.4' in level_str:
            pts = []
            for s_info in subject_scores.values():
                s_pct = (s_info['score'] / s_info['max'] * 100) if s_info['max'] > 0 else 0
                _, pt = get_uce_grade(s_pct, 100)
                pts.append(pt)
            if pts:
                division, aggregate = get_uce_division(pts)
        else:
            if avg >= 80:
                division = 'I'
            elif avg >= 65:
                division = 'II'
            elif avg >= 50:
                division = 'III'
            elif avg >= 35:
                division = 'IV'
            elif avg > 0:
                division = 'U'

        result, _ = TermResult.all_objects.update_or_create(
            student=student,
            academic_term=term,
            defaults={
                'school': school,
                'class_group': class_group,
                'total_marks': total,
                'average_marks': avg,
                'division': division,
                'aggregate': aggregate,
            }
        )
        return result

    @classmethod
    def _recompute_term_results(cls, assessment):
        """US-042: Recompute totals, average, rank, aggregates and division for the class. <10s for 80 students."""
        from results.models import Assessment, AssessmentMark, TermResult
        from students.models import Student
        from results.grading import (
            get_ple_subject_grade, get_ple_division,
            get_uce_grade, get_uce_division,
        )

        class_group = assessment.class_group
        term = assessment.academic_term
        school = assessment.school

        # Fetch all assessments for this class+term once
        assessments = list(Assessment.all_objects.filter(
            school=school, academic_term=term, class_group=class_group
        ).select_related('subject'))

        # Fetch all marks for these assessments in a single query
        marks = AssessmentMark.objects.filter(
            assessment__in=assessments
        ).select_related('student', 'assessment', 'assessment__subject')

        # Build lookup map: (student_id, assessment_id) -> mark
        marks_map = {
            (str(mark.student_id), str(mark.assessment_id)): mark
            for mark in marks
        }

        students = Student.all_objects.filter(
            school=school, current_class=class_group, is_active=True
        )

        level_str = (class_group.level or class_group.name or '').upper() if class_group else ''

        student_totals = {}
        for student in students:
            total = Decimal('0')
            max_total = Decimal('0')
            subject_scores = {}
            for asmt in assessments:
                weight = Decimal(str(asmt.weight))
                max_total += Decimal(str(asmt.max_marks)) * weight
                mark = marks_map.get((str(student.id), str(asmt.id)))
                if mark and not mark.is_absent and mark.marks_obtained is not None:
                    total += mark.marks_obtained * weight
                    subj_key = asmt.subject.code if (asmt.subject and asmt.subject.code) else (asmt.subject.name if asmt.subject else asmt.name)
                    if subj_key not in subject_scores:
                        subject_scores[subj_key] = {'score': Decimal('0'), 'max': Decimal('0')}
                    subject_scores[subj_key]['score'] += mark.marks_obtained * weight
                    subject_scores[subj_key]['max'] += Decimal(str(asmt.max_marks)) * weight

            avg = (total / max_total * 100) if max_total > 0 else Decimal('0')

            division = None
            aggregate = None

            if 'P7' in level_str or 'P.7' in level_str:
                pts = []
                for s_info in subject_scores.values():
                    s_pct = (s_info['score'] / s_info['max'] * 100) if s_info['max'] > 0 else 0
                    pts.append(get_ple_subject_grade(s_pct, 100))
                if pts:
                    division, aggregate = get_ple_division(pts)
            elif 'S4' in level_str or 'S.4' in level_str:
                pts = []
                for s_info in subject_scores.values():
                    s_pct = (s_info['score'] / s_info['max'] * 100) if s_info['max'] > 0 else 0
                    _, pt = get_uce_grade(s_pct, 100)
                    pts.append(pt)
                if pts:
                    division, aggregate = get_uce_division(pts)
            else:
                if avg >= 80:
                    division = 'I'
                elif avg >= 65:
                    division = 'II'
                elif avg >= 50:
                    division = 'III'
                elif avg >= 35:
                    division = 'IV'
                elif avg > 0:
                    division = 'U'

            student_totals[str(student.id)] = {
                'student': student, 'total': total, 'average': avg,
                'division': division, 'aggregate': aggregate,
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
                    'division': data.get('division'),
                    'aggregate': data.get('aggregate'),
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

        # Bulk-fetch marks to eliminate N+1 queries (performance optimisation)
        assessments = list(Assessment.all_objects.filter(
            school=school, academic_term=term,
            class_group=term_result.class_group,
        ).select_related('subject'))

        # Single query to get all marks for this student in this class+term
        student_marks = AssessmentMark.objects.filter(
            assessment__in=assessments, student=student
        ).select_related('assessment')
        marks_map = {str(m.assessment_id): m for m in student_marks}

        subject_data = {}
        for asmt in assessments:
            mark = marks_map.get(str(asmt.id))
            if mark:
                subject_name = asmt.subject.name
                if subject_name not in subject_data:
                    subject_data[subject_name] = {'marks': 0, 'max': 0}
                if not mark.is_absent and mark.marks_obtained:
                    subject_data[subject_name]['marks'] += float(mark.marks_obtained)
                    subject_data[subject_name]['max'] += asmt.max_marks

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

        # Bulk-fetch marks to eliminate N+1 queries (performance optimisation)
        assessments = list(Assessment.all_objects.filter(
            school=school, academic_term=term,
            class_group=term_result.class_group,
        ).select_related('subject'))

        # Single query to get all marks for this student in this class+term
        student_marks = AssessmentMark.objects.filter(
            assessment__in=assessments, student=student
        ).select_related('assessment')
        marks_map = {str(m.assessment_id): m for m in student_marks}

        subject_data = {}
        for asmt in assessments:
            mark = marks_map.get(str(asmt.id))
            if mark:
                subject_name = asmt.subject.name
                if subject_name not in subject_data:
                    subject_data[subject_name] = {'marks': 0, 'max': 0}
                if not mark.is_absent and mark.marks_obtained:
                    subject_data[subject_name]['marks'] += float(mark.marks_obtained)
                    subject_data[subject_name]['max'] += asmt.max_marks

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
    def generate_generic_report_card(cls, term_result):
        """
        US-045: Generic report card for levels other than P7/PLE and S4/UCE.
        Uses a standard A–F grade table (80–100=A, 65–79=B, 50–64=C, 35–49=D, 0–34=F).
        """
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

        assessments = list(Assessment.all_objects.filter(
            school=school, academic_term=term,
            class_group=term_result.class_group,
        ).select_related('subject'))

        student_marks = AssessmentMark.objects.filter(
            assessment__in=assessments, student=student
        ).select_related('assessment')
        marks_map = {str(m.assessment_id): m for m in student_marks}

        def _grade_letter(pct):
            if pct >= 80: return 'A'
            if pct >= 65: return 'B'
            if pct >= 50: return 'C'
            if pct >= 35: return 'D'
            return 'F'

        subject_data = {}
        for asmt in assessments:
            mark = marks_map.get(str(asmt.id))
            if mark:
                subject_name = asmt.subject.name if asmt.subject else asmt.name
                if subject_name not in subject_data:
                    subject_data[subject_name] = {'marks': 0, 'max': 0}
                if not mark.is_absent and mark.marks_obtained:
                    subject_data[subject_name]['marks'] += float(mark.marks_obtained)
                    subject_data[subject_name]['max'] += asmt.max_marks

        rows = []
        for subject_name, data in subject_data.items():
            pct = (data['marks'] / data['max'] * 100) if data['max'] > 0 else 0
            rows.append([
                subject_name,
                f"{data['marks']:.0f}/{data['max']}",
                f"{pct:.1f}%",
                _grade_letter(pct),
            ])

        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=A4,
                                rightMargin=1.5*cm, leftMargin=1.5*cm,
                                topMargin=1.5*cm, bottomMargin=1.5*cm)
        styles = getSampleStyleSheet()
        elements = []

        elements.append(Paragraph(f"<b>{school.name.upper()}</b>", styles['Title']))
        elements.append(Paragraph("TERM REPORT CARD", styles['Heading2']))
        elements.append(Spacer(1, 0.3*cm))
        elements.append(Paragraph(f"<b>Student:</b> {student.get_full_name()}", styles['Normal']))
        elements.append(Paragraph(f"<b>Admission No:</b> {student.student_id}", styles['Normal']))
        elements.append(Paragraph(f"<b>Class:</b> {term_result.class_group.name}", styles['Normal']))
        elements.append(Paragraph(f"<b>Term:</b> {term.name}", styles['Normal']))
        elements.append(Spacer(1, 0.4*cm))

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
        elements.append(Paragraph(
            f"Average: {float(term_result.average_marks):.1f}%  |  "
            f"Position: {term_result.class_rank} of {term_result.total_students}  |  "
            f"Class Average: {float(term_result.class_average):.1f}%",
            styles['Heading3']
        ))
        elements.append(Spacer(1, 0.4*cm))
        elements.append(Paragraph(
            "Grade Scale: A=80–100%, B=65–79%, C=50–64%, D=35–49%, F=0–34%",
            styles['Italic']
        ))
        doc.build(elements)
        buffer.seek(0)
        return buffer, None, None

    @classmethod
    def batch_generate_and_notify(cls, class_group, term, generated_by):
        """
        US-043/044/045: Batch generate all report cards for a class.
        Runs as Celery task. Notifies parents on completion (US-047).
        """
        from results.models import TermResult
        results = TermResult.all_objects.filter(
            class_group=class_group, academic_term=term
        ).select_related('student', 'school')

        for result in results:
            from results.tasks import generate_single_report_card
            generate_single_report_card.delay(str(result.id), class_group.level or '')

