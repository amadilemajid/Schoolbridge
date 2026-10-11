"""
Reports views — aggregation layer over existing models.
No new models. Produces JSON (default), PDF (via reportlab), or Excel (via openpyxl).

US-015  Enrolment report
US-030  Daily reconciliation report
US-053  Attendance vs fee cross-reference
US-056  Term-end financial summary
US-059  WhatsApp delivery analytics report
"""
import io
import logging
from collections import defaultdict
from datetime import date, timedelta

from django.db.models import Count, Sum, Q, DecimalField
from django.db.models.functions import Coalesce
from django.utils import timezone
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from drf_spectacular.utils import extend_schema, OpenApiParameter, inline_serializer
from drf_spectacular.types import OpenApiTypes
from rest_framework import serializers as drf_serializers

from schools.permissions import IsDirector, IsDirectorOrBursar, IsSchoolStaff

logger = logging.getLogger('schoolbridge')


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _excel_response(wb, filename):
    """Return an HttpResponse with an Excel workbook."""
    from django.http import HttpResponse
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    response = HttpResponse(
        buf.read(),
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    )
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


def _pdf_response(elements, filename, title='Report', subtitle=''):
    """Return an HttpResponse with a PDF built from reportlab Flowable elements."""
    from django.http import HttpResponse
    try:
        from reportlab.lib.pagesizes import A4, landscape
        from reportlab.lib import colors
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import mm
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle

        buf = io.BytesIO()
        doc = SimpleDocTemplate(
            buf,
            pagesize=A4,
            rightMargin=15 * mm,
            leftMargin=15 * mm,
            topMargin=20 * mm,
            bottomMargin=15 * mm,
            title=title,
        )
        styles = getSampleStyleSheet()
        story = [
            Paragraph(title, styles['Title']),
            Spacer(1, 4 * mm),
        ]
        if subtitle:
            story.append(Paragraph(subtitle, styles['Normal']))
            story.append(Spacer(1, 4 * mm))
        story.extend(elements)
        doc.build(story)
        buf.seek(0)
        response = HttpResponse(buf.read(), content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        return response
    except ImportError:
        from django.http import HttpResponse
        return HttpResponse('reportlab not installed', status=500)


def _resolve_term(school, term_id_param):
    """
    Resolve an AcademicTerm from a parameter string.
    Accepts: None/'current' (→ current term), integer id, or term name substring.
    Returns (term, error_response_or_None).
    """
    from schools.models import AcademicTerm

    if not school:
        return None, Response({'error': 'No school associated with this account.'}, status=400)

    if not term_id_param or str(term_id_param).lower() == 'current':
        term = AcademicTerm.objects.filter(school=school, is_current=True).first()
        if not term:
            term = AcademicTerm.objects.filter(school=school).order_by('-start_date').first()
        if not term:
            return None, Response({'error': 'No academic term found for this school. Please activate or configure a term first.'}, status=404)
        return term, None

    # Try by integer pk
    try:
        term_pk = int(term_id_param)
        term = AcademicTerm.objects.get(id=term_pk, school=school)
        return term, None
    except (ValueError, TypeError):
        pass
    except AcademicTerm.DoesNotExist:
        return None, Response({'error': f'Term with id={term_id_param} not found.'}, status=404)

    # Try by name substring
    term = AcademicTerm.objects.filter(school=school, name__icontains=str(term_id_param)).first()
    if term:
        return term, None

    return None, Response({'error': f'Term "{term_id_param}" not found.'}, status=404)


def _resolve_class(school, class_param):
    """
    Resolve a ClassGroup from an id or name string.
    Returns (class_group_or_None, error_response_or_None).
    None class_group with no error means 'all classes'.
    """
    from students.models import ClassGroup

    if not class_param:
        return None, None

    try:
        cls = ClassGroup.objects.get(id=int(class_param), school=school)
        return cls, None
    except (ValueError, TypeError):
        pass
    except ClassGroup.DoesNotExist:
        return None, Response({'error': f'Class id={class_param} not found.'}, status=404)

    cls = ClassGroup.objects.filter(school=school, name__iexact=str(class_param)).first()
    if not cls:
        cls = ClassGroup.objects.filter(school=school, name__icontains=str(class_param)).first()
    if cls:
        return cls, None

    return None, Response({'error': f'Class "{class_param}" not found.'}, status=404)


# ---------------------------------------------------------------------------
# KPI View — live dashboard stats for the Reports page
# ---------------------------------------------------------------------------

class ReportsKpiView(APIView):
    """
    Live KPI stats for the /reports dashboard header.
    GET /api/v1/reports/kpi/
    Returns:
      - students_registered: total active students
      - uneb_candidates: active students in S.4 / P.7 classes
      - reports_generated_this_term: count of reconciliation payments this term
      - total_expected_fees: sum of all fee amounts for current term
      - total_collected_fees: sum of amount_paid for current term
      - outstanding_fees: total_expected - total_collected - total_waivers
      - collection_rate: %
      - current_term: { id, name, start_date, end_date }
      - all_terms: list of { id, name, is_current }
      - all_classes: list of { id, name }
    """
    permission_classes = [IsSchoolStaff]

    def get(self, request):
        from students.models import Student, ClassGroup
        from payments.models import FeeRecord

        school = request.user.school

        # Active students
        students_qs = Student.objects.filter(school=school, is_active=True)
        students_registered = students_qs.count()

        # UNEB candidates: S.4 or P.7 classes
        uneb_candidates = students_qs.filter(
            Q(current_class__name__icontains='S.4') |
            Q(current_class__name__icontains='P.7') |
            Q(current_class__name__icontains='S4') |
            Q(current_class__name__icontains='P7')
        ).count()

        # Term resolution (reacts dynamically to ?term_id=...)
        from schools.models import AcademicTerm
        term_id_param = request.query_params.get('term_id')
        current_term, _ = _resolve_term(school, term_id_param)
        if not current_term:
            current_term = AcademicTerm.objects.filter(school=school, is_current=True).first()
            if not current_term:
                current_term = AcademicTerm.objects.filter(school=school).order_by('-start_date').first()

        # Fee totals for the selected term
        fee_totals = {'expected': 0, 'collected': 0, 'waivers': 0}
        if current_term:
            agg = FeeRecord.objects.filter(school=school, academic_term=current_term).aggregate(
                expected=Coalesce(Sum('total_amount'), 0, output_field=DecimalField()),
                collected=Coalesce(Sum('amount_paid'), 0, output_field=DecimalField()),
                waivers=Coalesce(Sum('amount_waived'), 0, output_field=DecimalField()),
            )
            fee_totals = agg

        total_expected = fee_totals['expected']
        total_collected = fee_totals['collected']
        total_waivers = fee_totals['waivers']
        outstanding = total_expected - total_collected - total_waivers
        collection_rate = round((total_collected + total_waivers) / total_expected * 100, 1) if total_expected else 0

        # All terms
        all_terms = list(
            AcademicTerm.objects.filter(school=school).order_by('-start_date').values('id', 'name', 'is_current', 'start_date', 'end_date')
        )
        for t in all_terms:
            t['id'] = str(t['id'])
            t['start_date'] = str(t['start_date'])
            t['end_date'] = str(t['end_date'])

        # All active classes
        all_classes = list(
            ClassGroup.objects.filter(school=school, is_active=True)
            .order_by('level', 'name')
            .values('id', 'name')
        )

        # Operational metrics for KPI cards — computed dynamically from audit and messaging
        from audit.models import AuditLog
        from messaging.models import MessageLog

        reports_generated = AuditLog.objects.filter(
            school_id=school.id,
            action__in=['REPORT_GENERATED', 'EXPORT_DOWNLOADED']
        ).count()

        uneb_exports = AuditLog.objects.filter(
            school_id=school.id,
            action__in=['REPORT_GENERATED', 'EXPORT_DOWNLOADED'],
            extra_data__report_type__in=['uneb_registration', 'uneb_candidates']
        ).count()

        fee_reports_shared = MessageLog.all_objects.filter(
            school=school,
            template_type__in=['fee_reminder', 'fee_receipt', 'overdue_notice']
        ).count()

        return Response({
            'students_registered': students_registered,
            'uneb_candidates': uneb_candidates,
            'reports_generated': reports_generated,
            'uneb_exports': uneb_exports,
            'fee_reports_shared': fee_reports_shared,
            'total_expected_fees': total_expected,
            'total_collected_fees': total_collected,
            'total_waivers': total_waivers,
            'outstanding_fees': outstanding,
            'collection_rate': collection_rate,
            'current_term': {
                'id': current_term.id if current_term else None,
                'name': current_term.name if current_term else None,
                'start_date': str(current_term.start_date) if current_term else None,
                'end_date': str(current_term.end_date) if current_term else None,
            } if current_term else None,
            'all_terms': all_terms,
            'all_classes': all_classes,
        })


# ---------------------------------------------------------------------------
# Enrolment Report
# ---------------------------------------------------------------------------

class EnrolmentReportView(APIView):
    """
    US-015: Enrolment report — students by class and gender.
    GET /api/v1/reports/enrolment/?format=json|excel
    """
    permission_classes = [IsSchoolStaff]

    @extend_schema(
        parameters=[
            OpenApiParameter('format', OpenApiTypes.STR, description='Response format: json or excel', enum=['json', 'excel']),
            OpenApiParameter('term_id', OpenApiTypes.STR, description='Filter by academic term (id or name or "current")'),
        ],
        responses={200: inline_serializer(name='EnrolmentReport', fields={
            'school': drf_serializers.CharField(),
            'generated_at': drf_serializers.DateTimeField(),
            'total_active_students': drf_serializers.IntegerField(),
            'classes': drf_serializers.ListField(),
        })},
        summary='Enrolment report — students by class and gender (US-015)',
        tags=['Reports'],
    )
    def get(self, request):
        from students.models import Student, ClassGroup

        school = request.user.school
        fmt = request.query_params.get('format', 'json')

        classes = ClassGroup.objects.filter(
            school=school, is_active=True
        ).order_by('level', 'name')

        rows = []
        total_active = 0

        for cls in classes:
            students = Student.objects.filter(school=school, current_class=cls, is_active=True)
            male = students.filter(gender='M').count()
            female = students.filter(gender='F').count()
            total = male + female
            total_active += total
            rows.append({
                'class': cls.name,
                'level': cls.level,
                'stream': cls.stream,
                'form_teacher': cls.form_teacher.get_full_name() if cls.form_teacher else None,
                'male': male,
                'female': female,
                'total': total,
            })

        if fmt == 'excel':
            try:
                import openpyxl
                from openpyxl.styles import Font, PatternFill, Alignment
                wb = openpyxl.Workbook()
                ws = wb.active
                ws.title = 'Enrolment'
                ws.append([school.name])
                ws.append(['Enrolment Report', '', '', '', '', f'Generated: {date.today()}', ''])
                ws.append([])
                headers = ['Class', 'Level', 'Stream', 'Form Teacher', 'Male', 'Female', 'Total']
                ws.append(headers)
                for row in rows:
                    ws.append([row['class'], row['level'], row['stream'], row['form_teacher'],
                                row['male'], row['female'], row['total']])
                ws.append([])
                ws.append(['TOTAL', '', '', '', '', '', total_active])
                return _excel_response(wb, f'enrolment_{date.today()}.xlsx')
            except ImportError:
                logger.warning('openpyxl not installed — returning JSON')

        return Response({
            'school': school.name,
            'generated_at': timezone.now(),
            'total_active_students': total_active,
            'classes': rows,
        })


# ---------------------------------------------------------------------------
# Reconciliation Report
# ---------------------------------------------------------------------------

class ReconciliationReportView(APIView):
    """
    US-030/US-062: Daily payment reconciliation report.
    GET /api/v1/reports/reconciliation/?date=YYYY-MM-DD&format=json|excel
    """
    permission_classes = [IsDirectorOrBursar]

    @extend_schema(
        parameters=[
            OpenApiParameter('date', OpenApiTypes.DATE, description='Report date (defaults to today)'),
            OpenApiParameter('format', OpenApiTypes.STR, enum=['json', 'excel']),
        ],
        responses={200: inline_serializer(name='ReconciliationReport', fields={
            'report_date': drf_serializers.DateField(),
            'total_collected': drf_serializers.DecimalField(max_digits=14, decimal_places=0),
            'momo_total': drf_serializers.DecimalField(max_digits=14, decimal_places=0),
            'manual_total': drf_serializers.DecimalField(max_digits=14, decimal_places=0),
            'auto_matched': drf_serializers.IntegerField(),
            'manually_matched': drf_serializers.IntegerField(),
            'unmatched': drf_serializers.IntegerField(),
            'payments': drf_serializers.ListField(),
        })},
        summary='Daily payment reconciliation report (US-030)',
        tags=['Reports'],
    )
    def get(self, request):
        from payments.models import Payment, ReconciliationQueue

        school = request.user.school
        report_date_str = request.query_params.get('date')
        fmt = request.query_params.get('format', 'json')

        try:
            report_date = date.fromisoformat(report_date_str) if report_date_str else date.today()
        except ValueError:
            return Response({'error': 'Invalid date format. Use YYYY-MM-DD.'}, status=400)

        payments = Payment.objects.filter(
            school=school,
            created_at__date=report_date,
            status='completed',
        )

        totals = payments.aggregate(
            total=Coalesce(Sum('amount'), 0, output_field=DecimalField()),
            momo=Coalesce(Sum('amount', filter=Q(method__in=['mtn_momo', 'airtel_money'])), 0, output_field=DecimalField()),
            manual=Coalesce(Sum('amount', filter=Q(method__in=['cash', 'bank'])), 0, output_field=DecimalField()),
        )

        recon = ReconciliationQueue.objects.filter(school=school, received_at__date=report_date)
        auto_matched = recon.filter(status='matched').count()
        manually_matched = recon.filter(status='manually_matched').count()
        unmatched = recon.filter(status='unmatched').count()

        payment_list = list(payments.select_related('fee_record__student').values(
            'id', 'amount', 'method', 'momo_reference', 'status',
            'fee_record__student__first_name', 'fee_record__student__last_name',
        ))

        if fmt == 'excel':
            try:
                import openpyxl
                wb = openpyxl.Workbook()
                ws = wb.active
                ws.title = 'Reconciliation'
                ws.append([school.name])
                ws.append([f'Daily Reconciliation Report — {report_date}'])
                ws.append([])
                ws.append(['Student', 'Amount', 'Method', 'Reference', 'Status'])
                for p in payment_list:
                    name = f"{p['fee_record__student__first_name']} {p['fee_record__student__last_name']}"
                    ws.append([name, p['amount'], p['method'], p['momo_reference'], p['status']])
                ws.append([])
                ws.append(['TOTAL COLLECTED', totals['total'], '', '', ''])
                return _excel_response(wb, f'reconciliation_{report_date}.xlsx')
            except ImportError:
                logger.warning('openpyxl not installed — returning JSON')

        return Response({
            'report_date': report_date,
            'total_collected': totals['total'],
            'momo_total': totals['momo'],
            'manual_total': totals['manual'],
            'auto_matched': auto_matched,
            'manually_matched': manually_matched,
            'unmatched': unmatched,
            'payments': payment_list,
        })


# ---------------------------------------------------------------------------
# Financial Summary Report (Test 11.1)
# ---------------------------------------------------------------------------

class FinancialSummaryReportView(APIView):
    """
    US-056: Term-end financial summary report.
    GET /api/v1/reports/financial-summary/?term_id=<id|name|current>&format=json|excel|pdf
    
    term_id is optional — defaults to the school's current term.
    """
    permission_classes = [IsDirectorOrBursar]

    @extend_schema(
        parameters=[
            OpenApiParameter('term_id', OpenApiTypes.STR, required=False,
                             description='Term id, name, or "current" (defaults to current term)'),
            OpenApiParameter('format', OpenApiTypes.STR, enum=['json', 'excel', 'pdf']),
        ],
        responses={200: inline_serializer(name='FinancialSummaryReport', fields={
            'term': drf_serializers.CharField(),
            'total_expected': drf_serializers.DecimalField(max_digits=14, decimal_places=0),
            'total_collected': drf_serializers.DecimalField(max_digits=14, decimal_places=0),
            'total_waivers': drf_serializers.DecimalField(max_digits=14, decimal_places=0),
            'outstanding': drf_serializers.DecimalField(max_digits=14, decimal_places=0),
            'net_collection': drf_serializers.DecimalField(max_digits=14, decimal_places=0),
            'collection_rate': drf_serializers.FloatField(),
            'by_class': drf_serializers.ListField(),
        })},
        summary='Term-end financial summary report — fee collection & outstanding balances (US-056)',
        tags=['Reports'],
    )
    def get(self, request):
        from payments.models import FeeRecord
        from students.models import ClassGroup

        school = request.user.school
        term_id = request.query_params.get('term_id')
        fmt = request.query_params.get('format', 'json')

        term, err = _resolve_term(school, term_id)
        if err:
            return err

        records = FeeRecord.objects.filter(school=school, academic_term=term)
        totals = records.aggregate(
            expected=Coalesce(Sum('total_amount'), 0, output_field=DecimalField()),
            collected=Coalesce(Sum('amount_paid'), 0, output_field=DecimalField()),
            waivers=Coalesce(Sum('amount_waived'), 0, output_field=DecimalField()),
        )

        total_expected = totals['expected']
        total_collected = totals['collected']
        total_waivers = totals['waivers']
        net_collection = total_collected + total_waivers
        outstanding = total_expected - net_collection
        collection_rate = round((net_collection / total_expected * 100), 1) if total_expected else 0

        # Per-class breakdown
        classes = ClassGroup.objects.filter(school=school, is_active=True).order_by('level', 'name')
        by_class = []
        for cls in classes:
            cls_records = records.filter(student__current_class=cls)
            cls_totals = cls_records.aggregate(
                expected=Coalesce(Sum('total_amount'), 0, output_field=DecimalField()),
                collected=Coalesce(Sum('amount_paid'), 0, output_field=DecimalField()),
                waivers=Coalesce(Sum('amount_waived'), 0, output_field=DecimalField()),
            )
            if cls_totals['expected'] > 0:
                cls_outstanding = cls_totals['expected'] - cls_totals['collected'] - cls_totals['waivers']
                cls_rate = round(
                    (cls_totals['collected'] + cls_totals['waivers']) / cls_totals['expected'] * 100, 1
                ) if cls_totals['expected'] else 0
                by_class.append({
                    'class': cls.name,
                    'students': cls_records.values('student').distinct().count(),
                    'expected': cls_totals['expected'],
                    'collected': cls_totals['collected'],
                    'waivers': cls_totals['waivers'],
                    'outstanding': cls_outstanding,
                    'collection_rate': cls_rate,
                })

        payload = {
            'term': term.name,
            'term_id': term.id,
            'school': school.name,
            'generated_at': timezone.now().isoformat(),
            'total_expected': total_expected,
            'total_collected': total_collected,
            'total_waivers': total_waivers,
            'net_collection': net_collection,
            'outstanding': outstanding,
            'collection_rate': collection_rate,
            'by_class': by_class,
        }

        if fmt == 'excel':
            try:
                import openpyxl
                from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
                from openpyxl.utils import get_column_letter

                wb = openpyxl.Workbook()
                ws = wb.active
                ws.title = 'Financial Summary'

                # Header
                ws.merge_cells('A1:G1')
                ws['A1'] = school.name
                ws['A1'].font = Font(bold=True, size=14)
                ws['A1'].alignment = Alignment(horizontal='center')

                ws.merge_cells('A2:G2')
                ws['A2'] = f'Fee Collection Report — {term.name}'
                ws['A2'].font = Font(bold=True, size=12)
                ws['A2'].alignment = Alignment(horizontal='center')

                ws.merge_cells('A3:G3')
                ws['A3'] = f'Generated: {date.today()}'
                ws['A3'].alignment = Alignment(horizontal='center')

                ws.append([])

                # Summary block
                ws.append(['SUMMARY', ''])
                ws.append(['Total Expected (UGX)', total_expected])
                ws.append(['Total Collected (UGX)', total_collected])
                ws.append(['Total Waivers (UGX)', total_waivers])
                ws.append(['Outstanding (UGX)', outstanding])
                ws.append(['Collection Rate', f'{collection_rate}%'])
                ws.append([])

                # Per-class header
                headers = ['Class', 'Students', 'Expected (UGX)', 'Collected (UGX)', 'Waivers (UGX)', 'Outstanding (UGX)', 'Collection Rate']
                ws.append(headers)
                for i, h in enumerate(headers, 1):
                    cell = ws.cell(row=ws.max_row, column=i)
                    cell.font = Font(bold=True)
                    cell.fill = PatternFill('solid', fgColor='1e3a5f')

                for row in by_class:
                    ws.append([
                        row['class'], row['students'], row['expected'],
                        row['collected'], row['waivers'], row['outstanding'],
                        f"{row['collection_rate']}%"
                    ])

                # Column widths
                for col in ws.columns:
                    max_len = max((len(str(cell.value or '')) for cell in col), default=10)
                    ws.column_dimensions[get_column_letter(col[0].column)].width = min(max_len + 4, 30)

                return _excel_response(wb, f'fee_collection_{term.name}_{date.today()}.xlsx')
            except ImportError:
                logger.warning('openpyxl not installed — returning JSON')

        if fmt == 'pdf':
            try:
                from reportlab.platypus import Table, TableStyle, Paragraph, Spacer
                from reportlab.lib import colors
                from reportlab.lib.styles import getSampleStyleSheet
                from reportlab.lib.units import mm

                styles = getSampleStyleSheet()
                elements = []

                # Summary table
                summary_data = [
                    ['Metric', 'Amount (UGX)'],
                    ['Total Expected', f"{total_expected:,.0f}"],
                    ['Total Collected', f"{total_collected:,.0f}"],
                    ['Total Waivers', f"{total_waivers:,.0f}"],
                    ['Outstanding', f"{outstanding:,.0f}"],
                    ['Collection Rate', f"{collection_rate}%"],
                ]
                t = Table(summary_data, colWidths=[80 * mm, 80 * mm])
                t.setStyle(TableStyle([
                    ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1e3a5f')),
                    ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                    ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                    ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
                    ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f0f4f8')]),
                ]))
                elements.append(Paragraph('Summary', styles['Heading2']))
                elements.append(Spacer(1, 3 * mm))
                elements.append(t)
                elements.append(Spacer(1, 6 * mm))

                # Per-class table
                class_data = [['Class', 'Students', 'Expected', 'Collected', 'Waivers', 'Outstanding', 'Rate']]
                for row in by_class:
                    class_data.append([
                        row['class'],
                        str(row['students']),
                        f"{row['expected']:,.0f}",
                        f"{row['collected']:,.0f}",
                        f"{row['waivers']:,.0f}",
                        f"{row['outstanding']:,.0f}",
                        f"{row['collection_rate']}%",
                    ])
                ct = Table(class_data, colWidths=[30*mm, 20*mm, 28*mm, 28*mm, 22*mm, 28*mm, 18*mm])
                ct.setStyle(TableStyle([
                    ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1e3a5f')),
                    ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                    ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                    ('FONTSIZE', (0, 0), (-1, -1), 8),
                    ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
                    ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f0f4f8')]),
                ]))
                elements.append(Paragraph('Per-Class Breakdown', styles['Heading2']))
                elements.append(Spacer(1, 3 * mm))
                elements.append(ct)

                return _pdf_response(
                    elements,
                    filename=f'fee_collection_{term.name}_{date.today()}.pdf',
                    title=f'Fee Collection Report — {term.name}',
                    subtitle=f'{school.name} | Generated {date.today()}',
                )
            except ImportError:
                logger.warning('reportlab not installed — returning JSON')

        return Response(payload)


# ---------------------------------------------------------------------------
# Attendance Summary Report (Test 11.2)
# ---------------------------------------------------------------------------

class AttendanceSummaryReportView(APIView):
    """
    Attendance summary report with daily present/absent breakdown.
    GET /api/v1/reports/attendance-summary/
        ?term_id=<id|name|current>   (optional, defaults to current term)
        &class_id=<id|name>          (optional, filters to one class)
        &days=7                      (optional, last N days — overrides term range)
        &date_from=YYYY-MM-DD        (optional)
        &date_to=YYYY-MM-DD          (optional)
        &format=json|excel|pdf
    """
    permission_classes = [IsSchoolStaff]

    @extend_schema(
        parameters=[
            OpenApiParameter('term_id', OpenApiTypes.STR, required=False,
                             description='Term id, name, or "current" (defaults to current term)'),
            OpenApiParameter('class_id', OpenApiTypes.STR, description='Class id or name (e.g. "P.5 East")'),
            OpenApiParameter('days', OpenApiTypes.INT, description='Last N days (overrides term date range)'),
            OpenApiParameter('date_from', OpenApiTypes.DATE),
            OpenApiParameter('date_to', OpenApiTypes.DATE),
            OpenApiParameter('format', OpenApiTypes.STR, enum=['json', 'excel', 'pdf']),
        ],
        responses={200: inline_serializer(name='AttendanceSummaryReport', fields={
            'term': drf_serializers.CharField(),
            'class_name': drf_serializers.CharField(),
            'date_from': drf_serializers.DateField(),
            'date_to': drf_serializers.DateField(),
            'total_students': drf_serializers.IntegerField(),
            'overall_rate': drf_serializers.FloatField(),
            'total_present': drf_serializers.IntegerField(),
            'total_absent': drf_serializers.IntegerField(),
            'daily_breakdown': drf_serializers.ListField(),
            'classes': drf_serializers.ListField(),
        })},
        summary='Attendance summary with daily present/absent counts and rate %',
        tags=['Reports'],
    )
    def get(self, request):
        from attendance.models import AttendanceRecord
        from students.models import Student, ClassGroup

        school = request.user.school
        term_id_param = request.query_params.get('term_id')
        class_param = request.query_params.get('class_id')
        days_param = request.query_params.get('days')
        date_from_param = request.query_params.get('date_from')
        date_to_param = request.query_params.get('date_to')
        fmt = request.query_params.get('format', 'json')

        # Resolve term (optional)
        term = None
        if term_id_param:
            term, err = _resolve_term(school, term_id_param)
            if err:
                return err
        else:
            from schools.models import AcademicTerm
            term = AcademicTerm.objects.filter(school=school, is_current=True).first()
            if not term:
                term = AcademicTerm.objects.filter(school=school).order_by('-start_date').first()

        # Resolve class (optional)
        cls_filter, err = _resolve_class(school, class_param)
        if err:
            return err

        # Compute date range
        today = date.today()
        if days_param:
            try:
                n_days = int(days_param)
            except ValueError:
                return Response({'error': 'days must be an integer.'}, status=400)
            date_from = today - timedelta(days=n_days - 1)
            date_to = today
        elif date_from_param and date_to_param:
            try:
                date_from = date.fromisoformat(date_from_param)
                date_to = date.fromisoformat(date_to_param)
            except ValueError:
                return Response({'error': 'Invalid date format. Use YYYY-MM-DD.'}, status=400)
        elif term:
            date_from = term.start_date
            date_to = term.end_date
        else:
            date_from = today - timedelta(days=6)
            date_to = today

        # Build base queryset
        att_qs = AttendanceRecord.objects.filter(
            school=school,
            date__gte=date_from,
            date__lte=date_to,
        )
        if cls_filter:
            att_qs = att_qs.filter(student__current_class=cls_filter)

        # Daily breakdown
        from django.db.models import Count
        daily_agg = att_qs.values('date').annotate(
            total=Count('id'),
            present_count=Count('id', filter=Q(status__in=['present', 'late'])),
            absent_count=Count('id', filter=Q(status='absent')),
            excused_count=Count('id', filter=Q(status='excused')),
        ).order_by('date')

        daily_breakdown = []
        for row in daily_agg:
            total = row['total']
            present = row['present_count']
            absent = row['absent_count']
            excused = row['excused_count']
            rate = round(present / total * 100, 1) if total else 0
            daily_breakdown.append({
                'date': str(row['date']),
                'day_name': row['date'].strftime('%A'),
                'present_count': present,
                'absent_count': absent,
                'excused_count': excused,
                'total_students': total,
                'attendance_rate': rate,
            })

        # Overall totals
        overall_agg = att_qs.aggregate(
            total=Count('id'),
            present=Count('id', filter=Q(status__in=['present', 'late'])),
            absent=Count('id', filter=Q(status='absent')),
            excused=Count('id', filter=Q(status='excused')),
        )
        overall_total = overall_agg['total']
        overall_present = overall_agg['present']
        overall_absent = overall_agg['absent']
        overall_excused = overall_agg['excused']
        overall_rate = round(overall_present / overall_total * 100, 1) if overall_total else 0

        # Total unique students in range
        total_students = att_qs.values('student').distinct().count()

        class_name = cls_filter.name if cls_filter else 'All Classes'

        payload = {
            'term': term.name if term else None,
            'term_id': term.id if term else None,
            'class_name': class_name,
            'class_id': cls_filter.id if cls_filter else None,
            'date_from': str(date_from),
            'date_to': str(date_to),
            'total_students': total_students,
            'overall_rate': overall_rate,
            'total_present': overall_present,
            'total_absent': overall_absent,
            'total_excused': overall_excused,
            'daily_breakdown': daily_breakdown,
        }

        if fmt == 'excel':
            try:
                import openpyxl
                from openpyxl.styles import Font, PatternFill, Alignment
                from openpyxl.utils import get_column_letter

                wb = openpyxl.Workbook()
                ws = wb.active
                ws.title = 'Attendance Summary'

                ws.merge_cells('A1:G1')
                ws['A1'] = school.name
                ws['A1'].font = Font(bold=True, size=14)
                ws['A1'].alignment = Alignment(horizontal='center')

                ws.merge_cells('A2:G2')
                ws['A2'] = f'Attendance Summary — {class_name}'
                ws['A2'].font = Font(bold=True, size=12)
                ws['A2'].alignment = Alignment(horizontal='center')

                ws.merge_cells('A3:G3')
                ws['A3'] = f'Period: {date_from} to {date_to} | Generated: {date.today()}'
                ws['A3'].alignment = Alignment(horizontal='center')
                ws.append([])

                ws.append(['OVERALL SUMMARY', ''])
                ws.append(['Total Students', total_students])
                ws.append(['Total Present', overall_present])
                ws.append(['Total Absent', overall_absent])
                ws.append(['Overall Attendance Rate', f'{overall_rate}%'])
                ws.append([])

                headers = ['Date', 'Day', 'Present', 'Absent', 'Excused', 'Total', 'Attendance Rate']
                ws.append(headers)
                for i, h in enumerate(headers, 1):
                    cell = ws.cell(row=ws.max_row, column=i)
                    cell.font = Font(bold=True)
                    cell.fill = PatternFill('solid', fgColor='1e3a5f')

                for row in daily_breakdown:
                    ws.append([
                        row['date'], row['day_name'],
                        row['present_count'], row['absent_count'],
                        row['excused_count'], row['total_students'],
                        f"{row['attendance_rate']}%",
                    ])

                for col in ws.columns:
                    max_len = max((len(str(cell.value or '')) for cell in col), default=8)
                    ws.column_dimensions[get_column_letter(col[0].column)].width = min(max_len + 4, 25)

                return _excel_response(wb, f'attendance_{class_name}_{date_from}_{date_to}.xlsx')
            except ImportError:
                logger.warning('openpyxl not installed — returning JSON')

        if fmt == 'pdf':
            try:
                from reportlab.platypus import Table, TableStyle, Paragraph, Spacer
                from reportlab.lib import colors
                from reportlab.lib.styles import getSampleStyleSheet
                from reportlab.lib.units import mm

                styles = getSampleStyleSheet()
                elements = []

                summary_data = [
                    ['Metric', 'Value'],
                    ['Class / Group', class_name],
                    ['Date Range', f'{date_from} to {date_to}'],
                    ['Total Students', str(total_students)],
                    ['Total Present', str(overall_present)],
                    ['Total Absent', str(overall_absent)],
                    ['Overall Attendance Rate', f'{overall_rate}%'],
                ]
                t = Table(summary_data, colWidths=[80 * mm, 80 * mm])
                t.setStyle(TableStyle([
                    ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1e3a5f')),
                    ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                    ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                    ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
                    ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f0f4f8')]),
                ]))
                elements.append(Paragraph('Summary', styles['Heading2']))
                elements.append(Spacer(1, 3 * mm))
                elements.append(t)
                elements.append(Spacer(1, 6 * mm))

                # Daily breakdown table
                daily_data = [['Date', 'Day', 'Present', 'Absent', 'Excused', 'Total', 'Rate %']]
                for row in daily_breakdown:
                    daily_data.append([
                        row['date'], row['day_name'],
                        str(row['present_count']), str(row['absent_count']),
                        str(row['excused_count']), str(row['total_students']),
                        f"{row['attendance_rate']}%",
                    ])
                dt = Table(daily_data, colWidths=[28*mm, 28*mm, 22*mm, 22*mm, 22*mm, 22*mm, 22*mm])
                dt.setStyle(TableStyle([
                    ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1e3a5f')),
                    ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                    ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                    ('FONTSIZE', (0, 0), (-1, -1), 8),
                    ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
                    ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f0f4f8')]),
                ]))
                elements.append(Paragraph('Daily Breakdown', styles['Heading2']))
                elements.append(Spacer(1, 3 * mm))
                elements.append(dt)

                return _pdf_response(
                    elements,
                    filename=f'attendance_{class_name}_{date_from}_{date_to}.pdf',
                    title=f'Attendance Summary — {class_name}',
                    subtitle=f'{school.name} | Period: {date_from} to {date_to}',
                )
            except ImportError:
                logger.warning('reportlab not installed — returning JSON')

        return Response(payload)


# ---------------------------------------------------------------------------
# Defaulters Cross-Reference Report (US-053)
# ---------------------------------------------------------------------------

class DefaultersCrossReferenceReportView(APIView):
    """
    US-053: Students attending but with fees significantly overdue.
    GET /api/v1/reports/defaulters/?term_id=<id|name|current>
    """
    permission_classes = [IsDirectorOrBursar]

    @extend_schema(
        parameters=[
            OpenApiParameter('term_id', OpenApiTypes.STR, required=False),
            OpenApiParameter('attendance_threshold', OpenApiTypes.FLOAT, description='Min attendance % (default 80)'),
            OpenApiParameter('fee_threshold', OpenApiTypes.FLOAT, description='Max fee payment % (default 50)'),
            OpenApiParameter('format', OpenApiTypes.STR, enum=['json', 'excel', 'pdf']),
        ],
        responses={200: inline_serializer(name='DefaultersCrossRef', fields={
            'term': drf_serializers.CharField(),
            'students': drf_serializers.ListField(),
        })},
        summary='Students attending but with significant fee arrears (US-053)',
        tags=['Reports'],
    )
    def get(self, request):
        from attendance.models import AttendanceRecord
        from payments.models import FeeRecord
        from students.models import Student

        school = request.user.school
        term_id = request.query_params.get('term_id')
        att_threshold = float(request.query_params.get('attendance_threshold', 80))
        fee_threshold = float(request.query_params.get('fee_threshold', 50))
        fmt = request.query_params.get('format', 'json')

        term, err = _resolve_term(school, term_id)
        if err:
            return err

        students = Student.objects.filter(school=school, is_active=True).select_related('current_class')
        flagged = []

        for student in students:
            records = AttendanceRecord.objects.filter(school=school, student=student, academic_term=term)
            total_days = records.count()
            if total_days == 0:
                continue
            present = records.filter(status__in=['present', 'late']).count()
            att_rate = (present / total_days) * 100

            if att_rate < att_threshold:
                continue

            try:
                fee_record = FeeRecord.objects.get(school=school, student=student, academic_term=term)
                if fee_record.total_amount == 0:
                    continue
                fee_rate = (fee_record.amount_paid / fee_record.total_amount) * 100
            except FeeRecord.DoesNotExist:
                continue

            if fee_rate < fee_threshold:
                flagged.append({
                    'student': f"{student.first_name} {student.last_name}",
                    'student_id': student.student_id,
                    'class': student.current_class.name if student.current_class else None,
                    'attendance_rate': round(att_rate, 1),
                    'fee_payment_rate': round(fee_rate, 1),
                    'outstanding_balance': fee_record.balance,
                })

        flagged.sort(key=lambda x: x['outstanding_balance'], reverse=True)

        if fmt == 'excel':
            try:
                import openpyxl
                from openpyxl.styles import Font, PatternFill
                wb = openpyxl.Workbook()
                ws = wb.active
                ws.title = 'Fee Defaulters'
                ws.append([school.name])
                ws.append([f'Fee Defaulters Report — {term.name}'])
                ws.append([])
                headers = ['Student', 'ID', 'Class', 'Attendance %', 'Fee Payment %', 'Outstanding (UGX)']
                ws.append(headers)
                for i, h in enumerate(headers, 1):
                    ws.cell(row=ws.max_row, column=i).font = Font(bold=True)
                for row in flagged:
                    ws.append([
                        row['student'], row['student_id'], row['class'],
                        row['attendance_rate'], row['fee_payment_rate'], row['outstanding_balance']
                    ])
                return _excel_response(wb, f'fee_defaulters_{term.name}_{date.today()}.xlsx')
            except ImportError:
                pass

        return Response({'term': term.name, 'count': len(flagged), 'students': flagged})


# ---------------------------------------------------------------------------
# WhatsApp Delivery Report (US-059)
# ---------------------------------------------------------------------------

class WhatsAppDeliveryReportView(APIView):
    """
    US-059: WhatsApp message delivery analytics report.
    GET /api/v1/reports/whatsapp-delivery/?term_id=<id|name|current>
    """
    permission_classes = [IsDirector]

    @extend_schema(
        parameters=[
            OpenApiParameter('term_id', OpenApiTypes.STR, required=False),
            OpenApiParameter('date_from', OpenApiTypes.DATE),
            OpenApiParameter('date_to', OpenApiTypes.DATE),
        ],
        responses={200: inline_serializer(name='WhatsAppDeliveryReport', fields={
            'total_sent': drf_serializers.IntegerField(),
            'delivered': drf_serializers.IntegerField(),
            'read': drf_serializers.IntegerField(),
            'failed': drf_serializers.IntegerField(),
            'delivery_rate': drf_serializers.FloatField(),
            'read_rate': drf_serializers.FloatField(),
            'by_template_type': drf_serializers.ListField(),
        })},
        summary='WhatsApp message delivery analytics (US-059)',
        tags=['Reports'],
    )
    def get(self, request):
        from messaging.models import WhatsAppLog

        school = request.user.school
        qs = WhatsAppLog.objects.filter(school=school)

        term_id = request.query_params.get('term_id')
        date_from = request.query_params.get('date_from')
        date_to = request.query_params.get('date_to')

        if term_id:
            term, err = _resolve_term(school, term_id)
            if err:
                return err
            qs = qs.filter(created_at__date__gte=term.start_date, created_at__date__lte=term.end_date)
        if date_from:
            qs = qs.filter(created_at__date__gte=date_from)
        if date_to:
            qs = qs.filter(created_at__date__lte=date_to)

        totals = qs.aggregate(
            total=Count('id'),
            delivered=Count('id', filter=Q(status='delivered')),
            read=Count('id', filter=Q(status='read')),
            failed=Count('id', filter=Q(status='failed')),
        )
        sent = totals['total']
        delivered = totals['delivered']
        read = totals['read']
        failed = totals['failed']

        by_type = list(qs.values('template_type').annotate(count=Count('id')).order_by('-count'))

        return Response({
            'total_sent': sent,
            'delivered': delivered,
            'read': read,
            'failed': failed,
            'delivery_rate': round(delivered / sent * 100, 1) if sent else 0,
            'read_rate': round(read / sent * 100, 1) if sent else 0,
            'by_template_type': by_type,
        })


# ---------------------------------------------------------------------------
# Unified Report Generate View (Test 11.3 — POST endpoint for downloads)
# ---------------------------------------------------------------------------

class UnifiedReportGenerateView(APIView):
    """
    Unified report generation endpoint.
    POST /api/v1/reports/generate/
    Body: { report_type, format, term_id, class_id, days, date_from, date_to }

    Supported report_type values:
      - fee_collection   → FinancialSummaryReportView
      - attendance_summary → AttendanceSummaryReportView
      - enrolment        → EnrolmentReportView
      - defaulter_list   → DefaultersCrossReferenceReportView
      - student_roster   → student CSV/Excel export
      - uneb_registration → UNEB candidate CSV/Excel export
    """
    permission_classes = [IsSchoolStaff]

    def post(self, request):
        try:
            resp = self._generate(request)
            if hasattr(resp, 'status_code') and 200 <= resp.status_code < 300:
                self._log_audit(request)
            return resp
        except Exception as e:
            logger.exception("UnifiedReportGenerateView unhandled exception: %s", str(e))
            return Response({'error': f'Report generation failed: {str(e)}'}, status=500)

    def _log_audit(self, request):
        try:
            school = getattr(request.user, 'school', None) or getattr(request, 'school', None)
            report_type = request.data.get('report_type', '')
            fmt = request.data.get('format', 'json')
            term_id = request.data.get('term_id', 'current')
            from audit.models import AuditLog
            AuditLog.log(
                actor=request.user,
                school=school,
                category='SCHOOL',
                action='REPORT_GENERATED',
                description=f'Generated {report_type} report ({fmt})',
                extra={'report_type': report_type, 'format': fmt, 'term_id': term_id},
                request=request,
            )
        except Exception:
            pass

    def _generate(self, request):
        report_type = request.data.get('report_type', '')
        fmt = request.data.get('format', 'json')
        term_id = request.data.get('term_id', 'current')
        class_id = request.data.get('class_id', '')
        days = request.data.get('days', '')
        date_from = request.data.get('date_from', '')
        date_to = request.data.get('date_to', '')

        school = getattr(request.user, 'school', None) or getattr(request, 'school', None)
        if not school:
            return Response({'error': 'No school associated with this account.'}, status=400)

        if report_type in ('fee_collection', 'financial_summary'):
            # Delegate to FinancialSummaryReportView logic
            term, err = _resolve_term(school, term_id)
            if err:
                return err
            from payments.models import FeeRecord
            from students.models import ClassGroup

            records = FeeRecord.objects.filter(school=school, academic_term=term)
            totals = records.aggregate(
                expected=Coalesce(Sum('total_amount'), 0, output_field=DecimalField()),
                collected=Coalesce(Sum('amount_paid'), 0, output_field=DecimalField()),
                waivers=Coalesce(Sum('amount_waived'), 0, output_field=DecimalField()),
            )
            total_expected = totals['expected']
            total_collected = totals['collected']
            total_waivers = totals['waivers']
            outstanding = total_expected - total_collected - total_waivers
            collection_rate = round((total_collected + total_waivers) / total_expected * 100, 1) if total_expected else 0

            classes = ClassGroup.objects.filter(school=school, is_active=True).order_by('level', 'name')
            by_class = []
            for cls in classes:
                cls_records = records.filter(student__current_class=cls)
                cls_totals = cls_records.aggregate(
                    expected=Coalesce(Sum('total_amount'), 0, output_field=DecimalField()),
                    collected=Coalesce(Sum('amount_paid'), 0, output_field=DecimalField()),
                    waivers=Coalesce(Sum('amount_waived'), 0, output_field=DecimalField()),
                )
                if cls_totals['expected'] > 0:
                    cls_outstanding = cls_totals['expected'] - cls_totals['collected'] - cls_totals['waivers']
                    cls_rate = round(
                        (cls_totals['collected'] + cls_totals['waivers']) / cls_totals['expected'] * 100, 1
                    )
                    by_class.append({
                        'class': cls.name,
                        'students': cls_records.values('student').distinct().count(),
                        'expected': cls_totals['expected'],
                        'collected': cls_totals['collected'],
                        'waivers': cls_totals['waivers'],
                        'outstanding': cls_outstanding,
                        'collection_rate': cls_rate,
                    })

            if fmt == 'excel':
                try:
                    import openpyxl
                    from openpyxl.styles import Font, PatternFill, Alignment
                    from openpyxl.utils import get_column_letter
                    wb = openpyxl.Workbook()
                    ws = wb.active
                    ws.title = 'Fee Collection'
                    ws.append([school.name])
                    ws.append([f'Fee Collection Report — {term.name}'])
                    ws.append([f'Generated: {date.today()}'])
                    ws.append([])
                    ws.append(['Total Expected', total_expected])
                    ws.append(['Total Collected', total_collected])
                    ws.append(['Total Waivers', total_waivers])
                    ws.append(['Outstanding', outstanding])
                    ws.append(['Collection Rate', f'{collection_rate}%'])
                    ws.append([])
                    headers = ['Class', 'Students', 'Expected', 'Collected', 'Waivers', 'Outstanding', 'Rate']
                    ws.append(headers)
                    for i, h in enumerate(headers, 1):
                        ws.cell(row=ws.max_row, column=i).font = Font(bold=True)
                    for row in by_class:
                        ws.append([row['class'], row['students'], row['expected'],
                                   row['collected'], row['waivers'], row['outstanding'],
                                   f"{row['collection_rate']}%"])
                    return _excel_response(wb, f'fee_collection_{term.name}_{date.today()}.xlsx')
                except ImportError:
                    pass

            if fmt == 'pdf':
                try:
                    from reportlab.platypus import Table, TableStyle, Paragraph, Spacer
                    from reportlab.lib import colors
                    from reportlab.lib.styles import getSampleStyleSheet
                    from reportlab.lib.units import mm
                    styles = getSampleStyleSheet()
                    elements = []
                    summary_data = [
                        ['Metric', 'Amount (UGX)'],
                        ['Total Expected', f"{total_expected:,.0f}"],
                        ['Total Collected', f"{total_collected:,.0f}"],
                        ['Total Waivers', f"{total_waivers:,.0f}"],
                        ['Outstanding', f"{outstanding:,.0f}"],
                        ['Collection Rate', f"{collection_rate}%"],
                    ]
                    t = Table(summary_data, colWidths=[80 * mm, 80 * mm])
                    t.setStyle(TableStyle([
                        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1e3a5f')),
                        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
                        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f0f4f8')]),
                    ]))
                    elements.append(Paragraph('Summary', styles['Heading2']))
                    elements.append(Spacer(1, 3 * mm))
                    elements.append(t)
                    elements.append(Spacer(1, 6 * mm))
                    class_data = [['Class', 'Students', 'Expected', 'Collected', 'Outstanding', 'Rate']]
                    for row in by_class:
                        class_data.append([
                            row['class'], str(row['students']),
                            f"{row['expected']:,.0f}", f"{row['collected']:,.0f}",
                            f"{row['outstanding']:,.0f}", f"{row['collection_rate']}%",
                        ])
                    ct = Table(class_data, colWidths=[35*mm, 22*mm, 32*mm, 32*mm, 32*mm, 22*mm])
                    ct.setStyle(TableStyle([
                        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1e3a5f')),
                        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                        ('FONTSIZE', (0, 0), (-1, -1), 8),
                        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
                        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f0f4f8')]),
                    ]))
                    elements.append(Paragraph('Per-Class Breakdown', styles['Heading2']))
                    elements.append(Spacer(1, 3 * mm))
                    elements.append(ct)
                    return _pdf_response(
                        elements,
                        filename=f'fee_collection_{term.name}_{date.today()}.pdf',
                        title=f'Fee Collection Report — {term.name}',
                        subtitle=f'{school.name} | Generated {date.today()}',
                    )
                except ImportError:
                    pass

            return Response({
                'term': term.name,
                'term_id': term.id,
                'school': school.name,
                'generated_at': timezone.now().isoformat(),
                'total_expected': total_expected,
                'total_collected': total_collected,
                'total_waivers': total_waivers,
                'outstanding': outstanding,
                'collection_rate': collection_rate,
                'by_class': by_class,
            })

        elif report_type == 'attendance_summary':
            # Build a fake request-like object to avoid code duplication
            # We call the view directly with a mutable params approach
            from attendance.models import AttendanceRecord

            term, err = _resolve_term(school, term_id)
            if err:
                return err

            cls_filter, err = _resolve_class(school, class_id if class_id else None)
            if err:
                return err

            today = date.today()
            if days:
                try:
                    n = int(days)
                except ValueError:
                    return Response({'error': 'days must be an integer.'}, status=400)
                d_from = today - timedelta(days=n - 1)
                d_to = today
            elif date_from and date_to:
                try:
                    d_from = date.fromisoformat(date_from)
                    d_to = date.fromisoformat(date_to)
                except ValueError:
                    return Response({'error': 'Invalid date format.'}, status=400)
            elif term:
                d_from = term.start_date
                d_to = term.end_date
            else:
                d_from = today - timedelta(days=6)
                d_to = today

            att_qs = AttendanceRecord.objects.filter(school=school, date__gte=d_from, date__lte=d_to)
            if cls_filter:
                att_qs = att_qs.filter(student__current_class=cls_filter)

            daily_agg = att_qs.values('date').annotate(
                total=Count('id'),
                present_count=Count('id', filter=Q(status__in=['present', 'late'])),
                absent_count=Count('id', filter=Q(status='absent')),
                excused_count=Count('id', filter=Q(status='excused')),
            ).order_by('date')

            daily_breakdown = []
            for row in daily_agg:
                total = row['total']
                present = row['present_count']
                rate = round(present / total * 100, 1) if total else 0
                daily_breakdown.append({
                    'date': str(row['date']),
                    'day_name': row['date'].strftime('%A'),
                    'present_count': present,
                    'absent_count': row['absent_count'],
                    'excused_count': row['excused_count'],
                    'total_students': total,
                    'attendance_rate': rate,
                })

            overall_agg = att_qs.aggregate(
                total=Count('id'),
                present=Count('id', filter=Q(status__in=['present', 'late'])),
                absent=Count('id', filter=Q(status='absent')),
            )
            overall_total = overall_agg['total']
            overall_present = overall_agg['present']
            overall_rate = round(overall_present / overall_total * 100, 1) if overall_total else 0
            total_students = att_qs.values('student').distinct().count()
            class_name = cls_filter.name if cls_filter else 'All Classes'

            if fmt == 'excel':
                try:
                    import openpyxl
                    from openpyxl.styles import Font, PatternFill, Alignment
                    from openpyxl.utils import get_column_letter
                    wb = openpyxl.Workbook()
                    ws = wb.active
                    ws.title = 'Attendance Summary'
                    ws.append([school.name])
                    ws.append([f'Attendance Summary — {class_name}'])
                    ws.append([f'Period: {d_from} to {d_to} | Generated: {date.today()}'])
                    ws.append([])
                    ws.append(['Total Students', total_students])
                    ws.append(['Total Present', overall_present])
                    ws.append(['Overall Rate', f'{overall_rate}%'])
                    ws.append([])
                    headers = ['Date', 'Day', 'Present', 'Absent', 'Excused', 'Total', 'Rate %']
                    ws.append(headers)
                    for i, h in enumerate(headers, 1):
                        ws.cell(row=ws.max_row, column=i).font = Font(bold=True)
                    for row in daily_breakdown:
                        ws.append([
                            row['date'], row['day_name'],
                            row['present_count'], row['absent_count'],
                            row['excused_count'], row['total_students'],
                            f"{row['attendance_rate']}%",
                        ])
                    return _excel_response(wb, f'attendance_{class_name}_{d_from}_{d_to}.xlsx')
                except ImportError:
                    pass

            if fmt == 'pdf':
                try:
                    from reportlab.platypus import Table, TableStyle, Paragraph, Spacer
                    from reportlab.lib import colors
                    from reportlab.lib.styles import getSampleStyleSheet
                    from reportlab.lib.units import mm
                    styles = getSampleStyleSheet()
                    elements = []
                    summary_data = [
                        ['Metric', 'Value'],
                        ['Class / Group', class_name],
                        ['Period', f'{d_from} to {d_to}'],
                        ['Total Students', str(total_students)],
                        ['Total Present', str(overall_present)],
                        ['Total Absent', str(overall_agg['absent'])],
                        ['Overall Rate', f'{overall_rate}%'],
                    ]
                    t = Table(summary_data, colWidths=[80 * mm, 80 * mm])
                    t.setStyle(TableStyle([
                        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1e3a5f')),
                        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
                        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f0f4f8')]),
                    ]))
                    elements.append(Paragraph('Summary', styles['Heading2']))
                    elements.append(Spacer(1, 3 * mm))
                    elements.append(t)
                    elements.append(Spacer(1, 6 * mm))
                    daily_data = [['Date', 'Day', 'Present', 'Absent', 'Excused', 'Total', 'Rate']]
                    for row in daily_breakdown:
                        daily_data.append([
                            row['date'], row['day_name'],
                            str(row['present_count']), str(row['absent_count']),
                            str(row['excused_count']), str(row['total_students']),
                            f"{row['attendance_rate']}%",
                        ])
                    dt = Table(daily_data, colWidths=[28*mm, 28*mm, 22*mm, 22*mm, 22*mm, 22*mm, 22*mm])
                    dt.setStyle(TableStyle([
                        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1e3a5f')),
                        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                        ('FONTSIZE', (0, 0), (-1, -1), 8),
                        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
                        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f0f4f8')]),
                    ]))
                    elements.append(Paragraph('Daily Breakdown', styles['Heading2']))
                    elements.append(Spacer(1, 3 * mm))
                    elements.append(dt)
                    return _pdf_response(
                        elements,
                        filename=f'attendance_{class_name}_{d_from}_{d_to}.pdf',
                        title=f'Attendance Summary — {class_name}',
                        subtitle=f'{school.name} | Period: {d_from} to {d_to}',
                    )
                except ImportError:
                    pass

            return Response({
                'term': term.name if term else None,
                'class_name': class_name,
                'date_from': str(d_from),
                'date_to': str(d_to),
                'total_students': total_students,
                'overall_rate': overall_rate,
                'total_present': overall_present,
                'total_absent': overall_agg['absent'],
                'daily_breakdown': daily_breakdown,
            })

        elif report_type == 'enrolment':
            from students.models import Student, ClassGroup
            classes = ClassGroup.objects.filter(school=school, is_active=True).order_by('level', 'name')
            rows = []
            total_active = 0
            for cls in classes:
                students = Student.objects.filter(school=school, current_class=cls, is_active=True)
                male = students.filter(gender='M').count()
                female = students.filter(gender='F').count()
                total = male + female
                total_active += total
                rows.append({
                    'class': cls.name,
                    'level': cls.level,
                    'stream': cls.stream,
                    'form_teacher': cls.form_teacher.get_full_name() if cls.form_teacher else None,
                    'male': male,
                    'female': female,
                    'total': total,
                })

            if fmt in ('excel', 'xlsx'):
                try:
                    import openpyxl
                    from openpyxl.styles import Font
                    wb = openpyxl.Workbook()
                    ws = wb.active
                    ws.title = 'Enrolment'
                    ws.append([school.name])
                    ws.append(['Enrolment Report', f'Generated: {date.today()}'])
                    ws.append([])
                    headers = ['Class', 'Level', 'Stream', 'Form Teacher', 'Male', 'Female', 'Total']
                    ws.append(headers)
                    for i, h in enumerate(headers, 1):
                        ws.cell(row=ws.max_row, column=i).font = Font(bold=True)
                    for row in rows:
                        ws.append([row['class'], row['level'], row['stream'], row['form_teacher'],
                                   row['male'], row['female'], row['total']])
                    ws.append([])
                    ws.append(['TOTAL', '', '', '', '', '', total_active])
                    return _excel_response(wb, f'enrolment_{date.today()}.xlsx')
                except ImportError:
                    pass

            if fmt == 'csv':
                from django.http import HttpResponse
                import csv
                response = HttpResponse(content_type='text/csv')
                response['Content-Disposition'] = f'attachment; filename="enrolment_{date.today()}.csv"'
                writer = csv.writer(response)
                writer.writerow(['Class', 'Level', 'Stream', 'Form Teacher', 'Male', 'Female', 'Total'])
                for row in rows:
                    writer.writerow([row['class'], row['level'], row['stream'], row['form_teacher'],
                                     row['male'], row['female'], row['total']])
                writer.writerow(['TOTAL', '', '', '', '', '', total_active])
                return response

            if fmt == 'pdf':
                try:
                    from reportlab.platypus import Table, TableStyle, Paragraph, Spacer
                    from reportlab.lib import colors
                    from reportlab.lib.styles import getSampleStyleSheet
                    from reportlab.lib.units import mm
                    styles = getSampleStyleSheet()
                    elements = [Paragraph('Enrolment Report', styles['Heading2']), Spacer(1, 3 * mm)]
                    table_data = [['Class', 'Level', 'Stream', 'Male', 'Female', 'Total']]
                    for r in rows:
                        table_data.append([r['class'], str(r['level']), r['stream'] or '', str(r['male']), str(r['female']), str(r['total'])])
                    table_data.append(['TOTAL', '', '', '', '', str(total_active)])
                    t = Table(table_data, colWidths=[35*mm, 20*mm, 25*mm, 25*mm, 25*mm, 25*mm])
                    t.setStyle(TableStyle([
                        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1e3a5f')),
                        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
                        ('ROWBACKGROUNDS', (0, 1), (-1, -2), [colors.white, colors.HexColor('#f0f4f8')]),
                        ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
                    ]))
                    elements.append(t)
                    return _pdf_response(elements, filename=f'enrolment_{date.today()}.pdf',
                                         title='Enrolment Report', subtitle=f'{school.name} | Generated {date.today()}')
                except Exception:
                    pass

            return Response({
                'school': school.name,
                'generated_at': timezone.now().isoformat(),
                'total_active_students': total_active,
                'classes': rows,
            })

        elif report_type == 'student_roster':
            from students.models import Student
            students_qs = Student.objects.filter(school=school, is_active=True).select_related('current_class').prefetch_related('guardians')

            rows = []
            for s in students_qs:
                guardians = list(s.guardians.all())
                g = next((x for x in guardians if getattr(x, 'is_primary', False)), None) or (guardians[0] if guardians else None)
                g_name = f"{g.first_name} {g.last_name}".strip() if g else ''
                g_phone = getattr(g, 'phone', '') if g else ''
                rows.append({
                    'student_id': s.student_id,
                    'first_name': s.first_name,
                    'last_name': s.last_name,
                    'class': s.current_class.name if s.current_class else '',
                    'gender': s.gender,
                    'guardian': g_name,
                    'guardian_phone': g_phone,
                })

            if fmt in ('excel', 'xlsx'):
                try:
                    import openpyxl
                    from openpyxl.styles import Font
                    wb = openpyxl.Workbook()
                    ws = wb.active
                    ws.title = 'Student Roster'
                    ws.append([school.name])
                    ws.append([f'Student Roster — Generated: {date.today()}'])
                    ws.append([])
                    headers = ['Student ID', 'First Name', 'Last Name', 'Class', 'Gender', 'Guardian', 'Guardian Phone']
                    ws.append(headers)
                    for i, h in enumerate(headers, 1):
                        ws.cell(row=ws.max_row, column=i).font = Font(bold=True)
                    for r in rows:
                        ws.append([r['student_id'], r['first_name'], r['last_name'], r['class'], r['gender'], r['guardian'], r['guardian_phone']])
                    return _excel_response(wb, f'student_roster_{date.today()}.xlsx')
                except ImportError:
                    pass

            if fmt == 'csv':
                from django.http import HttpResponse
                import csv
                response = HttpResponse(content_type='text/csv')
                response['Content-Disposition'] = f'attachment; filename="student_roster_{date.today()}.csv"'
                writer = csv.writer(response)
                writer.writerow(['Student ID', 'First Name', 'Last Name', 'Class', 'Gender', 'Guardian', 'Guardian Phone'])
                for r in rows:
                    writer.writerow([r['student_id'], r['first_name'], r['last_name'], r['class'], r['gender'], r['guardian'], r['guardian_phone']])
                return response

            if fmt == 'pdf':
                try:
                    from reportlab.platypus import Table, TableStyle, Paragraph, Spacer
                    from reportlab.lib import colors
                    from reportlab.lib.styles import getSampleStyleSheet
                    from reportlab.lib.units import mm
                    styles = getSampleStyleSheet()
                    elements = [Paragraph('Student Roster', styles['Heading2']), Spacer(1, 3 * mm)]
                    table_data = [['ID', 'Name', 'Class', 'Gender', 'Guardian Phone']]
                    for r in rows[:100]:
                        table_data.append([r['student_id'], f"{r['first_name']} {r['last_name']}", r['class'], r['gender'], r['guardian_phone']])
                    t = Table(table_data, colWidths=[25*mm, 45*mm, 30*mm, 15*mm, 45*mm])
                    t.setStyle(TableStyle([
                        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1e3a5f')),
                        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                        ('FONTSIZE', (0, 0), (-1, -1), 8),
                        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
                        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f0f4f8')]),
                    ]))
                    elements.append(t)
                    return _pdf_response(elements, filename=f'student_roster_{date.today()}.pdf',
                                         title='Student Roster', subtitle=f'{school.name} | Generated {date.today()}')
                except Exception:
                    pass

            return Response({'school': school.name, 'count': len(rows), 'students': rows})

        elif report_type in ('defaulter_list', 'fee_defaulters'):
            term, err = _resolve_term(school, term_id)
            if err:
                return err
            from attendance.models import AttendanceRecord
            from payments.models import FeeRecord
            from students.models import Student

            students = Student.objects.filter(school=school, is_active=True).select_related('current_class')
            flagged = []
            for student in students:
                records = AttendanceRecord.objects.filter(school=school, student=student, academic_term=term)
                total_days = records.count()
                if total_days == 0:
                    continue
                present = records.filter(status__in=['present', 'late']).count()
                att_rate = (present / total_days) * 100
                if att_rate < 80:
                    continue
                try:
                    fr = FeeRecord.objects.get(school=school, student=student, academic_term=term)
                    if fr.total_amount == 0:
                        continue
                    fee_rate = (fr.amount_paid / fr.total_amount) * 100
                except FeeRecord.DoesNotExist:
                    continue
                if fee_rate < 50:
                    flagged.append({
                        'student': f"{student.first_name} {student.last_name}",
                        'student_id': student.student_id,
                        'class': student.current_class.name if student.current_class else None,
                        'attendance_rate': round(att_rate, 1),
                        'fee_payment_rate': round(fee_rate, 1),
                        'outstanding_balance': fr.balance,
                    })
            flagged.sort(key=lambda x: x['outstanding_balance'], reverse=True)

            if fmt in ('excel', 'xlsx'):
                try:
                    import openpyxl
                    from openpyxl.styles import Font
                    wb = openpyxl.Workbook()
                    ws = wb.active
                    ws.title = 'Fee Defaulters'
                    ws.append([school.name])
                    ws.append([f'Fee Defaulters — {term.name}'])
                    ws.append([])
                    headers = ['Student', 'ID', 'Class', 'Attendance %', 'Fee Paid %', 'Outstanding (UGX)']
                    ws.append(headers)
                    for i, h in enumerate(headers, 1):
                        ws.cell(row=ws.max_row, column=i).font = Font(bold=True)
                    for row in flagged:
                        ws.append([row['student'], row['student_id'], row['class'],
                                   row['attendance_rate'], row['fee_payment_rate'], row['outstanding_balance']])
                    return _excel_response(wb, f'fee_defaulters_{term.name}_{date.today()}.xlsx')
                except ImportError:
                    pass

            if fmt == 'csv':
                from django.http import HttpResponse
                import csv
                response = HttpResponse(content_type='text/csv')
                response['Content-Disposition'] = f'attachment; filename="fee_defaulters_{term.name}_{date.today()}.csv"'
                writer = csv.writer(response)
                writer.writerow(['Student', 'ID', 'Class', 'Attendance %', 'Fee Paid %', 'Outstanding (UGX)'])
                for row in flagged:
                    writer.writerow([row['student'], row['student_id'], row['class'],
                                     row['attendance_rate'], row['fee_payment_rate'], row['outstanding_balance']])
                return response

            if fmt == 'pdf':
                try:
                    from reportlab.platypus import Table, TableStyle, Paragraph, Spacer
                    from reportlab.lib import colors
                    from reportlab.lib.styles import getSampleStyleSheet
                    from reportlab.lib.units import mm
                    styles = getSampleStyleSheet()
                    elements = [Paragraph(f'Fee Defaulters Report — {term.name}', styles['Heading2']), Spacer(1, 3 * mm)]
                    table_data = [['Student', 'Class', 'Attendance %', 'Fee Paid %', 'Outstanding (UGX)']]
                    for r in flagged:
                        table_data.append([r['student'], r['class'] or '', f"{r['attendance_rate']}%", f"{r['fee_payment_rate']}%", f"{r['outstanding_balance']:,.0f}"])
                    t = Table(table_data, colWidths=[45*mm, 25*mm, 25*mm, 25*mm, 35*mm])
                    t.setStyle(TableStyle([
                        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1e3a5f')),
                        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                        ('FONTSIZE', (0, 0), (-1, -1), 8),
                        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
                        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f0f4f8')]),
                    ]))
                    elements.append(t)
                    return _pdf_response(elements, filename=f'fee_defaulters_{term.name}_{date.today()}.pdf',
                                         title=f'Fee Defaulters Report — {term.name}', subtitle=f'{school.name} | Generated {date.today()}')
                except Exception:
                    pass

            return Response({'term': term.name, 'count': len(flagged), 'students': flagged})

        elif report_type in ('uneb_registration', 'uneb_candidates'):
            from students.models import Student
            candidates = Student.objects.filter(
                school=school, is_active=True
            ).filter(
                Q(current_class__name__icontains='S.4') |
                Q(current_class__name__icontains='P.7')
            ).select_related('current_class')

            rows = []
            for s in candidates:
                rows.append([
                    s.student_id, s.first_name, s.last_name,
                    s.current_class.name if s.current_class else '',
                    s.gender,
                    str(s.date_of_birth) if hasattr(s, 'date_of_birth') and s.date_of_birth else '',
                ])

            if fmt in ('csv',):
                from django.http import HttpResponse
                import csv
                response = HttpResponse(content_type='text/csv')
                response['Content-Disposition'] = f'attachment; filename="uneb_registration_{date.today()}.csv"'
                writer = csv.writer(response)
                writer.writerow(['STUDENT_ID', 'FIRST_NAME', 'LAST_NAME', 'CLASS', 'GENDER', 'DOB'])
                for r in rows:
                    writer.writerow(r)
                return response

            if fmt in ('excel', 'xlsx'):
                try:
                    import openpyxl
                    from openpyxl.styles import Font
                    wb = openpyxl.Workbook()
                    ws = wb.active
                    ws.title = 'UNEB Registration'
                    ws.append([school.name])
                    ws.append([f'UNEB Registration Export — {date.today()}'])
                    ws.append([])
                    headers = ['STUDENT_ID', 'FIRST_NAME', 'LAST_NAME', 'CLASS', 'GENDER', 'DOB']
                    ws.append(headers)
                    for i, h in enumerate(headers, 1):
                        ws.cell(row=ws.max_row, column=i).font = Font(bold=True)
                    for r in rows:
                        ws.append(r)
                    return _excel_response(wb, f'uneb_registration_{date.today()}.xlsx')
                except ImportError:
                    pass

            if fmt == 'pdf':
                try:
                    from reportlab.platypus import Table, TableStyle, Paragraph, Spacer
                    from reportlab.lib import colors
                    from reportlab.lib.styles import getSampleStyleSheet
                    from reportlab.lib.units import mm
                    styles = getSampleStyleSheet()
                    elements = [Paragraph('UNEB UCE Registration Candidates', styles['Heading2']), Spacer(1, 3 * mm)]
                    table_data = [['Student ID', 'Name', 'Class', 'Gender', 'DOB']]
                    for r in rows:
                        table_data.append([r[0], f"{r[1]} {r[2]}", r[3], r[4], r[5]])
                    t = Table(table_data, colWidths=[30*mm, 50*mm, 25*mm, 15*mm, 30*mm])
                    t.setStyle(TableStyle([
                        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1e3a5f')),
                        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                        ('FONTSIZE', (0, 0), (-1, -1), 8),
                        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
                        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f0f4f8')]),
                    ]))
                    elements.append(t)
                    return _pdf_response(elements, filename=f'uneb_registration_{date.today()}.pdf',
                                         title='UNEB UCE Registration Export', subtitle=f'{school.name} | Generated {date.today()}')
                except Exception:
                    pass

            data = [{'student_id': s.student_id, 'name': f"{s.first_name} {s.last_name}",
                     'class': s.current_class.name if s.current_class else None} for s in candidates]
            return Response({'school': school.name, 'count': len(data), 'candidates': data})

        elif report_type in ('term_results', 'grade_distribution'):
            term, err = _resolve_term(school, term_id)
            if err:
                return err
            from results.models import Assessment
            assessments = Assessment.objects.filter(school=school, academic_term=term).select_related('class_group', 'subject')
            rows = []
            for a in assessments:
                rows.append({
                    'class': a.class_group.name if a.class_group else '',
                    'subject': a.subject.name if a.subject else '',
                    'assessment': a.name,
                    'type': a.get_assessment_type_display(),
                    'max_marks': a.max_marks,
                    'status': a.get_status_display(),
                })

            if fmt in ('excel', 'xlsx'):
                try:
                    import openpyxl
                    from openpyxl.styles import Font
                    wb = openpyxl.Workbook()
                    ws = wb.active
                    ws.title = 'Term Results'
                    ws.append([school.name])
                    ws.append([f'Term Results & Grade Distribution — {term.name}'])
                    ws.append([])
                    headers = ['Class', 'Subject', 'Assessment', 'Type', 'Max Marks', 'Status']
                    ws.append(headers)
                    for i, h in enumerate(headers, 1):
                        ws.cell(row=ws.max_row, column=i).font = Font(bold=True)
                    for r in rows:
                        ws.append([r['class'], r['subject'], r['assessment'], r['type'], r['max_marks'], r['status']])
                    return _excel_response(wb, f'term_results_{term.name}_{date.today()}.xlsx')
                except ImportError:
                    pass

            if fmt == 'pdf':
                try:
                    from reportlab.platypus import Table, TableStyle, Paragraph, Spacer
                    from reportlab.lib import colors
                    from reportlab.lib.styles import getSampleStyleSheet
                    from reportlab.lib.units import mm
                    styles = getSampleStyleSheet()
                    elements = [Paragraph(f'Term Results & Grade Distribution — {term.name}', styles['Heading2']), Spacer(1, 3 * mm)]
                    table_data = [['Class', 'Subject', 'Assessment', 'Type', 'Max Marks', 'Status']]
                    for r in rows:
                        table_data.append([r['class'], r['subject'], r['assessment'], r['type'], str(r['max_marks']), r['status']])
                    t = Table(table_data, colWidths=[25*mm, 35*mm, 40*mm, 25*mm, 20*mm, 25*mm])
                    t.setStyle(TableStyle([
                        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1e3a5f')),
                        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                        ('FONTSIZE', (0, 0), (-1, -1), 8),
                        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
                        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f0f4f8')]),
                    ]))
                    elements.append(t)
                    return _pdf_response(elements, filename=f'term_results_{term.name}_{date.today()}.pdf',
                                         title=f'Term Results — {term.name}', subtitle=f'{school.name} | Generated {date.today()}')
                except Exception:
                    pass

            return Response({'term': term.name, 'count': len(rows), 'results': rows})

        elif report_type == 'result_slips':
            term, err = _resolve_term(school, term_id)
            if err:
                return err
            from students.models import Student
            candidates = Student.objects.filter(school=school, is_active=True).select_related('current_class')[:50]
            if fmt == 'pdf':
                try:
                    from reportlab.platypus import Table, TableStyle, Paragraph, Spacer
                    from reportlab.lib import colors
                    from reportlab.lib.styles import getSampleStyleSheet
                    from reportlab.lib.units import mm
                    styles = getSampleStyleSheet()
                    elements = [Paragraph(f'Student Result Slips — {term.name}', styles['Heading2']), Spacer(1, 3 * mm)]
                    table_data = [['Student ID', 'Full Name', 'Class', 'Term Status']]
                    for s in candidates:
                        table_data.append([s.student_id, f"{s.first_name} {s.last_name}", s.current_class.name if s.current_class else '', 'Completed'])
                    t = Table(table_data, colWidths=[35*mm, 55*mm, 35*mm, 35*mm])
                    t.setStyle(TableStyle([
                        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1e3a5f')),
                        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                        ('FONTSIZE', (0, 0), (-1, -1), 8),
                        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
                        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f0f4f8')]),
                    ]))
                    elements.append(t)
                    return _pdf_response(elements, filename=f'result_slips_{term.name}_{date.today()}.pdf',
                                         title=f'Student Result Slips — {term.name}', subtitle=f'{school.name} | Batch Print')
                except Exception:
                    pass

            data = [{'student_id': s.student_id, 'name': f"{s.first_name} {s.last_name}",
                     'class': s.current_class.name if s.current_class else ''} for s in candidates]
            return Response({'term': term.name, 'count': len(data), 'slips': data})

        else:
            return Response(
                {'error': f'Unknown report_type "{report_type}". Supported: fee_collection, attendance_summary, enrolment, student_roster, defaulter_list, uneb_registration, term_results, result_slips.'},
                status=400
            )
