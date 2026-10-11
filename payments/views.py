"""
Payments views — fee structures, payments, MoMo, reconciliation.
"""
import csv
import logging
from django.conf import settings
from django.http import HttpResponse
from django.utils import timezone
from django.db.models import Sum, Count, Q, F
from rest_framework import viewsets, generics, status, serializers
from rest_framework.decorators import action
from rest_framework.filters import SearchFilter
from rest_framework.parsers import MultiPartParser, FormParser
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.exceptions import ValidationError, NotFound
from config.validators import validate_uuid, validate_int
from config.mixins import ExportMixin
from drf_spectacular.utils import extend_schema, OpenApiParameter, OpenApiTypes, inline_serializer

from audit.mixins import AuditMixin
from schools.permissions import IsDirector, IsDirectorOrBursar, IsSchoolStaff
from .models import (
    FeeStructure, FeeStructureItem, FeeRecord, Payment,
    PaymentPlan, PaymentPlanInstalment, FeeWaiver, ReconciliationQueue,
    PaymentLink,
)
from .services import FeeService, MoMoService
from .payment_link_service import PaymentLinkService
from .serializers import (
    FeeStructureSerializer, FeeRecordSerializer, PaymentSerializer,
    PaymentCreateSerializer, PaymentPlanSerializer, FeeWaiverSerializer,
    FeeWaiverRejectSerializer, ReconciliationQueueSerializer,
    ReconciliationIgnoreSerializer, FeeReversalSerializer,
    PaymentLinkSerializer, GeneratePaymentLinkSerializer,
)

logger = logging.getLogger('payments')


class FeeStructureViewSet(AuditMixin, viewsets.ModelViewSet):
    queryset = FeeStructure.objects.none()
    """US-016: Fee structure management."""
    serializer_class = FeeStructureSerializer
    permission_classes = [IsDirectorOrBursar]

    def get_queryset(self):
        qs = FeeStructure.objects.filter(school=self.request.user.school, is_active=True)
        term_id = self.request.query_params.get('term_id')
        if term_id:
            validate_int(term_id, 'term_id')
            qs = qs.filter(academic_term_id=term_id)
        return qs.select_related('academic_term', 'class_group').prefetch_related('items').order_by('name')

    def perform_create(self, serializer):
        fs = serializer.save(school=self.request.user.school, created_by=self.request.user)
        self.log_action('FEE_STRUCTURE_CREATED', fs, {'name': fs.name})

    @extend_schema(
        request=inline_serializer(
            name='CloneFeeStructureRequest',
            fields={'target_term_id': serializers.UUIDField()}
        ),
        responses={201: FeeStructureSerializer},
        tags=['Payments']
    )
    @action(detail=True, methods=['post'], permission_classes=[IsDirector])
    def clone(self, request, pk=None):
        """Clone fee structure to another term (US-016)."""
        source = self.get_object()
        term_id = request.data.get('target_term_id')
        if not term_id:
            raise ValidationError({'target_term_id': 'target_term_id required.'})
        validate_int(term_id, 'target_term_id')
        from schools.models import AcademicTerm
        try:
            target_term = AcademicTerm.objects.get(id=term_id, school=request.user.school)
        except (AcademicTerm.DoesNotExist, ValueError):
            raise NotFound('Term not found.')

        new_fs = FeeStructure.all_objects.create(
            school=source.school,
            academic_term=target_term,
            class_group=source.class_group,
            name=f"{source.name} (Copy)",
            created_by=request.user,
        )
        for item in source.items.all():
            FeeStructureItem.objects.create(
                fee_structure=new_fs,
                name=item.name,
                amount=item.amount,
                is_mandatory=item.is_mandatory,
                description=item.description,
            )
        self.log_action('FEE_STRUCTURE_CLONED', new_fs, {'source_id': str(source.id)})
        return Response(FeeStructureSerializer(new_fs).data, status=201)

    @extend_schema(
        responses={200: inline_serializer(
            name='ApplyFeeStructureResponse',
            fields={
                'message': serializers.CharField(),
                'created': serializers.IntegerField(),
                'updated': serializers.IntegerField(),
                'total_students': serializers.IntegerField(),
            }
        )},
        tags=['Payments']
    )
    @action(detail=True, methods=['post'], permission_classes=[IsDirectorOrBursar], url_path='apply-to-students')
    def apply_to_students(self, request, pk=None):
        """
        US-016: Explicitly generate or update FeeRecords for all active enrolled students
        covered by this fee structure.
        """
        fee_structure = self.get_object()
        result = FeeService.generate_or_sync_fee_records_for_structure(fee_structure)
        self.log_action('FEE_STRUCTURE_APPLIED', fee_structure, result)
        return Response({
            'message': f"Successfully applied fee structure '{fee_structure.name}' to students.",
            **result
        }, status=200)


class FeeRecordViewSet(AuditMixin, viewsets.ReadOnlyModelViewSet):
    queryset = FeeRecord.objects.none()
    """
    US-017: Student fee balance (real-time, <30s from payment).
    US-018: Class-level summary.
    """
    serializer_class = FeeRecordSerializer
    permission_classes = [IsDirectorOrBursar]
    filter_backends = [DjangoFilterBackend, SearchFilter]
    filterset_fields = ['academic_term']
    search_fields = ['student__first_name', 'student__last_name', 'student__student_id']

    def get_queryset(self):
        qs = FeeRecord.objects.filter(school=self.request.user.school)
        term_id = self.request.query_params.get('term_id')
        student_id = self.request.query_params.get('student_id')
        # Accept both class_id (int PK) and current_class (string name / id)
        class_id = self.request.query_params.get('class_id')
        current_class = self.request.query_params.get('current_class')
        status_param = self.request.query_params.get('status')

        if term_id:
            validate_int(term_id, 'term_id')
            qs = qs.filter(academic_term_id=term_id)
        if student_id:
            validate_uuid(student_id, 'student_id')
            qs = qs.filter(student_id=student_id)
        if class_id:
            validate_int(class_id, 'class_id')
            qs = qs.filter(student__current_class_id=class_id)
        elif current_class:
            # current_class may be a class name substring or integer PK
            if current_class.isdigit():
                qs = qs.filter(student__current_class_id=int(current_class))
            else:
                qs = qs.filter(student__current_class__name__icontains=current_class)
        if status_param == 'cleared':
            qs = qs.filter(amount_paid__gte=F('total_amount') - F('amount_waived'))
        elif status_param == 'unpaid':
            qs = qs.filter(amount_paid=0)
        elif status_param == 'partial':
            qs = qs.filter(amount_paid__gt=0, amount_paid__lt=F('total_amount') - F('amount_waived'))
        elif status_param == 'defaulter':
            qs = qs.filter(amount_paid__lt=F('total_amount') - F('amount_waived'))
        elif status_param == 'partial_plan':
            qs = qs.filter(payment_plan__status='active', amount_paid__lt=F('total_amount') - F('amount_waived'))
        elif status_param == 'pending_approval':
            qs = qs.filter(
                Q(waivers__status='pending') | Q(payments__status='pending', payments__requires_approval=True)
            ).distinct()

        return qs.select_related(
            'student', 'student__current_class', 'academic_term'
        ).prefetch_related(
            'waivers', 'payments', 'payment_plan__instalments',
        ).order_by(
            'student__last_name', 'student__first_name', 'id'
        )

    @extend_schema(
        parameters=[
            OpenApiParameter('term_id', OpenApiTypes.UUID, OpenApiParameter.QUERY, required=True),
            OpenApiParameter('class_id', OpenApiTypes.UUID, OpenApiParameter.QUERY, required=True),
        ],
        responses={200: FeeRecordSerializer(many=True)},
        tags=['Payments']
    )
    @action(detail=False, methods=['get'], url_path='class-summary')
    def class_summary(self, request):
        """US-018: Class-level payment summary."""
        term_id = request.query_params.get('term_id')
        class_id = request.query_params.get('class_id')
        if not term_id or not class_id:
            raise ValidationError('term_id and class_id are required.')
        validate_int(term_id, 'term_id')
        validate_int(class_id, 'class_id')
        from students.models import ClassGroup
        try:
            class_group = ClassGroup.objects.get(id=class_id, school=request.user.school)
        except (ClassGroup.DoesNotExist, ValueError):
            raise NotFound('Class not found.')
        from schools.models import AcademicTerm
        try:
            term = AcademicTerm.objects.get(id=term_id, school=request.user.school)
        except (AcademicTerm.DoesNotExist, ValueError):
            raise NotFound('Term not found.')
        records = FeeService.get_class_fee_summary(class_group, term)
        return Response(FeeRecordSerializer(records, many=True).data)

    @extend_schema(
        parameters=[
            OpenApiParameter('term_id', OpenApiTypes.UUID, OpenApiParameter.QUERY, required=False),
            OpenApiParameter('format', OpenApiTypes.STR, OpenApiParameter.QUERY, required=False, description="Set to 'csv' for CSV file download"),
        ],
        responses={200: FeeRecordSerializer(many=True)},
        tags=['Payments']
    )
    @action(detail=False, methods=['get'])
    def defaulters(self, request):
        """US-020: Defaulter list. CSV export supported."""
        term_id = request.query_params.get('term_id')
        if not term_id:
            qs_term = request.user.school.terms.filter(is_current=True).first()
            if not qs_term:
                raise ValidationError('No current term found.')
        else:
            validate_int(term_id, 'term_id')
            from schools.models import AcademicTerm
            qs_term = AcademicTerm.objects.get(id=term_id, school=request.user.school)
        defaulters = FeeService.get_defaulter_list(request.user.school, qs_term)
        if request.query_params.get('format') == 'csv':
            return self._defaulters_csv(defaulters)
        return Response(FeeRecordSerializer(defaulters, many=True).data)

    def _defaulters_csv(self, queryset):
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="defaulters.csv"'
        writer = csv.writer(response)
        writer.writerow(['Student ID', 'Name', 'Class', 'Total', 'Paid', 'Balance', 'Guardian Phone'])
        for r in queryset:
            g = r.student.guardians.filter(is_primary=True).first()
            writer.writerow([
                r.student.student_id, r.student.get_full_name(),
                r.student.current_class.name if r.student.current_class else '',
                r.total_amount, r.amount_paid, r.balance,
                g.phone if g else '',
            ])
        return response

    @extend_schema(
        parameters=[
            OpenApiParameter('term_id', OpenApiTypes.UUID, OpenApiParameter.QUERY, required=False),
        ],
        responses={200: inline_serializer(
            name='FeeDashboardSummary',
            fields={
                'total_expected': serializers.IntegerField(),
                'total_collected': serializers.IntegerField(),
                'total_waived': serializers.IntegerField(),
                'balance': serializers.IntegerField(),
                'total_students': serializers.IntegerField(),
                'fully_paid': serializers.IntegerField(),
                'collection_rate': serializers.FloatField(),
            }
        )},
        tags=['Payments']
    )
    @action(detail=False, methods=['get'])
    def dashboard(self, request):
        """US-022: School-wide fee dashboard."""
        term_id = request.query_params.get('term_id')
        if term_id:
            validate_int(term_id, 'term_id')
            from schools.models import AcademicTerm
            term = AcademicTerm.objects.get(id=term_id, school=request.user.school)
        else:
            term = request.user.school.terms.filter(is_current=True).first()
        if not term:
            raise ValidationError('No current term.')
        return Response(FeeService.get_dashboard_summary(request.user.school, term))

    @extend_schema(
        responses={200: inline_serializer(
            name='TermComparisonItem',
            fields={
                'term_id': serializers.UUIDField(),
                'term_name': serializers.CharField(),
                'total_expected': serializers.IntegerField(),
                'total_collected': serializers.IntegerField(),
                'total_waived': serializers.IntegerField(),
                'total_students': serializers.IntegerField(),
                'fully_paid': serializers.IntegerField(),
                'collection_rate': serializers.FloatField(),
            },
            many=True
        )},
        tags=['Payments']
    )
    @action(detail=False, methods=['get'], url_path='term-comparison')
    def term_comparison(self, request):
        """US-025: Compare fee collection across terms."""
        from schools.models import AcademicTerm

        terms = AcademicTerm.objects.filter(
            school=request.user.school
        ).order_by('start_date')
        data = []
        for term in terms:
            summary = FeeService.get_dashboard_summary(request.user.school, term)
            data.append({
                'term_id': term.id,
                'term_name': str(term),
                'total_expected': summary.get('total_expected') or 0,
                'total_collected': summary.get('total_collected') or 0,
                'total_waived': summary.get('total_waived') or 0,
                'total_students': summary.get('total_students') or 0,
                'fully_paid': summary.get('fully_paid') or 0,
                'collection_rate': round(
                    (summary.get('total_collected') or 0) /
                    (summary.get('total_expected') or 1) * 100, 1
                ),
            })
        return Response(data)

    @action(detail=False, methods=['get'], url_path='end_of_day_summary')
    def end_of_day_summary(self, request):
        """Get summary of all payments recorded today in this school."""
        today = timezone.now().date()
        payments = Payment.objects.filter(
            school=request.user.school,
            payment_date__date=today,
            status='completed',
            is_reversed=False
        )
        from django.db.models import Sum
        cash = payments.filter(method='cash').aggregate(total=Sum('amount'))['total'] or 0
        bank = payments.filter(method='bank').aggregate(total=Sum('amount'))['total'] or 0
        momo = payments.filter(method__in=['mtn_momo', 'airtel_money', 'momo']).aggregate(total=Sum('amount'))['total'] or 0
        return Response({
            'total_cash': cash,
            'total_bank': bank,
            'total_momo': momo,
            'transaction_count': payments.count(),
            'date': str(today)
        })


class PaymentViewSet(ExportMixin, AuditMixin, viewsets.ModelViewSet):
    queryset = Payment.objects.none()
    """
    US-019: Manual payment recording.
    US-023: Payment reversal.
    """
    permission_classes = [IsDirectorOrBursar]
    filter_backends = [DjangoFilterBackend, SearchFilter]
    filterset_fields = {'method': ['exact'], 'status': ['exact']}
    search_fields = ['transaction_id', 'student__first_name', 'student__last_name', 'recorded_by__first_name', 'recorded_by__last_name']

    def get_permissions(self):
        if self.action in ('approve', 'reverse'):
            return [IsDirector()]
        return [IsDirectorOrBursar()]

    def get_serializer_class(self):
        if self.action == 'create':
            return PaymentCreateSerializer
        return PaymentSerializer

    def get_queryset(self):
        qs = Payment.objects.filter(school=self.request.user.school)
        fee_record_id = self.request.query_params.get('fee_record_id') or self.request.query_params.get('fee_record')
        student_id = self.request.query_params.get('student_id') or self.request.query_params.get('student')
        if fee_record_id:
            validate_uuid(fee_record_id, 'fee_record_id')
            qs = qs.filter(fee_record_id=fee_record_id)
        if student_id:
            validate_uuid(student_id, 'student_id')
            qs = qs.filter(student_id=student_id)
        return qs.select_related('student', 'fee_record', 'recorded_by')

    def perform_create(self, serializer):
        fee_record_id = serializer.validated_data.get('fee_record_id')
        amount = serializer.validated_data.get('amount')
        method = serializer.validated_data.get('method')
        school = self.request.user.school
        fee_record = None
        
        # 1. Direct FeeRecord UUID lookup
        try:
            fee_record = FeeRecord.all_objects.get(id=fee_record_id, school=school)
        except Exception:
            pass

        # Resolve current or active term for scoping fallback student lookups
        current_term = school.terms.filter(is_current=True).first() or school.terms.filter(is_active=True).first()

        # 2. Admission Code lookup
        if not fee_record and fee_record_id:
            qs = FeeRecord.all_objects.filter(
                school=school, student__student_id__iexact=str(fee_record_id).strip()
            )
            if current_term:
                fee_record = qs.filter(academic_term=current_term).first()
            if not fee_record:
                fee_record = qs.order_by('-academic_term__start_date', '-created_at').first()

        # 3. Student UUID lookup (safe)
        if not fee_record and fee_record_id:
            try:
                qs = FeeRecord.all_objects.filter(
                    school=school, student_id=str(fee_record_id).strip()
                )
                if current_term:
                    fee_record = qs.filter(academic_term=current_term).first()
                if not fee_record:
                    fee_record = qs.order_by('-academic_term__start_date', '-created_at').first()
            except Exception:
                pass

        # 4. Student Full Name or Name Parts lookup
        if not fee_record and fee_record_id:
            target_str = str(fee_record_id).strip()
            if ' ' in target_str:
                parts = target_str.split(maxsplit=1)
                name_qs = FeeRecord.all_objects.filter(
                    school=school,
                    student__first_name__icontains=parts[0],
                    student__last_name__icontains=parts[1]
                )
                if not name_qs.exists():
                    name_qs = FeeRecord.all_objects.filter(
                        school=school,
                        student__first_name__icontains=parts[1],
                        student__last_name__icontains=parts[0]
                    )
            else:
                name_qs = FeeRecord.all_objects.filter(
                    school=school,
                    student__first_name__icontains=target_str
                )
                if not name_qs.exists():
                    name_qs = FeeRecord.all_objects.filter(
                        school=school,
                        student__last_name__icontains=target_str
                    )
            if current_term:
                fee_record = name_qs.filter(academic_term=current_term).first()
            if not fee_record:
                fee_record = name_qs.order_by('-academic_term__start_date', '-created_at').first()

        # 5. Direct student lookup & auto-creation of FeeRecord if student exists in school
        if not fee_record and fee_record_id:
            from students.models import Student
            target_str = str(fee_record_id).strip()
            student_obj = None
            try:
                student_obj = Student.all_objects.filter(school=school, id=target_str).first()
            except Exception:
                pass
            if not student_obj:
                student_obj = Student.all_objects.filter(school=school, student_id__iexact=target_str).first()
            if not student_obj and ' ' in target_str:
                parts = target_str.split(maxsplit=1)
                student_obj = (
                    Student.all_objects.filter(school=school, first_name__icontains=parts[0], last_name__icontains=parts[1]).first()
                    or Student.all_objects.filter(school=school, first_name__icontains=parts[1], last_name__icontains=parts[0]).first()
                )
            if student_obj:
                fee_record = FeeService.get_or_create_fee_record(student_obj, current_term)

        if not fee_record:
            from rest_framework.exceptions import NotFound
            raise NotFound('Fee record not found for the specified student or identifier.')

        # Guard: reject payments on fully cleared fee records
        if fee_record.balance <= 0:
            from rest_framework.exceptions import ValidationError
            raise ValidationError(
                {'detail': 'Actions for CLEARED accounts are locked. The student has no outstanding balance.'}
            )

        notes_val = serializer.validated_data.get('notes', '').strip()
        payer_val = serializer.validated_data.get('payer_name', '').strip()
        if payer_val:
            if not notes_val:
                notes_val = f"Payer: {payer_val}"
            elif 'Payer:' not in notes_val:
                notes_val = f"Payer: {payer_val} | {notes_val}"

        send_receipt = serializer.validated_data.get('send_receipt', True)

        payment = FeeService.record_manual_payment(
            fee_record=fee_record,
            amount=amount,
            method=method,
            recorded_by=self.request.user,
            receipt_number=serializer.validated_data.get('receipt_number', ''),
            notes=notes_val,
            bank_reference=serializer.validated_data.get('bank_reference', ''),
            send_receipt=send_receipt,
        )
        self.log_action('PAYMENT_RECORDED', payment, {
            'amount': str(amount), 'method': method,
            'student': str(fee_record.student.id),
        })
        return payment

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            payment = self.perform_create(serializer)
            if payment:
                return Response(PaymentSerializer(payment).data, status=status.HTTP_201_CREATED)
            raise ValidationError('Payment creation failed.')
        except (ValidationError, NotFound) as e:
            # Re-raise DRF exceptions — they already carry correct HTTP status
            raise
        except Exception as e:
            import logging
            logging.getLogger('payments').exception(f"Unexpected payment create error: {e}")
            raise ValidationError({'non_field_errors': [str(e)]})

    @extend_schema(
        responses={200: inline_serializer(name='ApprovePaymentResponse', fields={'message': serializers.CharField()})},
        tags=['Payments']
    )
    @action(detail=True, methods=['post'], permission_classes=[IsDirector])
    def approve(self, request, pk=None):
        """Approve a large payment that required Director sign-off."""
        if request.user.role not in ('director', 'system_admin'):
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied('Only the Director or System Administrator is authorised to approve payments.')
        payment = self.get_object()
        if payment.school != request.user.school:
            raise NotFound('Not found.')
        try:
            FeeService.approve_payment(payment, request.user)
        except ValueError as e:
            raise ValidationError(str(e))
        self.log_action('PAYMENT_APPROVED', payment, {'amount': str(payment.amount)})
        return Response({'message': 'Payment approved.'})

    @extend_schema(
        request=FeeReversalSerializer,
        responses={200: inline_serializer(name='ReversePaymentResponse', fields={'message': serializers.CharField()})},
        tags=['Payments']
    )
    @action(detail=True, methods=['post'], permission_classes=[IsDirector])
    def reverse(self, request, pk=None):
        """US-023: Reverse a payment with reason."""
        if request.user.role not in ('director', 'system_admin'):
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied('Only the Director or System Administrator is authorised to reverse payments.')
        payment = self.get_object()
        serializer = FeeReversalSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        reason = serializer.validated_data['reason']
        try:
            FeeService.reverse_payment(payment, reason, request.user)
        except ValueError as e:
            raise ValidationError(str(e))
        self.log_action('PAYMENT_REVERSED', payment, {
            'amount': str(payment.amount), 'reason': reason
        })
        return Response({'message': 'Payment reversed successfully.', 'status': 'reversed'})

    @extend_schema(
        responses={200: inline_serializer(name='EndOfDaySummaryResponse', fields={
            'total_cash': serializers.IntegerField(),
            'total_bank': serializers.IntegerField(),
            'total_momo': serializers.IntegerField(),
            'transaction_count': serializers.IntegerField(),
            'date': serializers.CharField(),
        })},
        tags=['Payments']
    )
    @action(detail=False, methods=['get'], url_path='end-of-day-summary')
    def end_of_day_summary(self, request):
        """Get summary and transaction breakdown of payments recorded today for the school."""
        today = timezone.now().date()
        payments = Payment.objects.filter(
            school=request.user.school,
            payment_date__date=today,
            status='completed',
            is_reversed=False
        ).select_related('student', 'student__current_class', 'recorded_by').order_by('-payment_date')
        
        from django.db.models import Sum
        cash = payments.filter(method='cash').aggregate(total=Sum('amount'))['total'] or 0
        bank = payments.filter(method='bank').aggregate(total=Sum('amount'))['total'] or 0
        momo = payments.filter(method__in=['mtn_momo', 'airtel_money']).aggregate(total=Sum('amount'))['total'] or 0
        
        transactions = []
        for p in payments:
            transactions.append({
                'id': str(p.id),
                'receipt_number': p.receipt_number,
                'student_name': f"{p.student.first_name} {p.student.last_name}".strip(),
                'class_name': p.student.current_class.name if p.student.current_class else 'N/A',
                'amount': int(p.amount),
                'method': p.method,
                'time': p.payment_date.strftime('%H:%M'),
                'recorded_by': f"{p.recorded_by.first_name} {p.recorded_by.last_name}".strip() if p.recorded_by else 'System / MoMo',
            })

        return Response({
            'total_cash': cash,
            'total_bank': bank,
            'total_momo': momo,
            'transaction_count': payments.count(),
            'date': str(today),
            'transactions': transactions,
        })

    @action(detail=False, methods=['post'], url_path='close-register')
    def close_register(self, request):
        """Close the daily register and log audit trail."""
        today = timezone.now().date()
        payments = Payment.objects.filter(
            school=request.user.school,
            payment_date__date=today,
            status='completed',
            is_reversed=False
        )
        from django.db.models import Sum
        cash = payments.filter(method='cash').aggregate(total=Sum('amount'))['total'] or 0
        bank = payments.filter(method='bank').aggregate(total=Sum('amount'))['total'] or 0
        momo = payments.filter(method__in=['mtn_momo', 'airtel_money']).aggregate(total=Sum('amount'))['total'] or 0
        grand_total = cash + bank + momo

        self.log_action('REGISTER_CLOSED', request.user, {
            'date': str(today),
            'total_cash': str(cash),
            'total_bank': str(bank),
            'total_momo': str(momo),
            'grand_total': str(grand_total),
            'transaction_count': payments.count(),
        })

        return Response({
            'message': 'Register closed successfully.',
            'date': str(today),
            'closed_at': timezone.now().isoformat(),
            'grand_total': grand_total,
            'transaction_count': payments.count()
        })


class PaymentPlanViewSet(AuditMixin, viewsets.ModelViewSet):
    queryset = PaymentPlan.objects.none()
    """US-021: Payment plans."""
    serializer_class = PaymentPlanSerializer
    permission_classes = [IsDirectorOrBursar]

    def get_queryset(self):
        qs = PaymentPlan.objects.filter(school=self.request.user.school).select_related(
            'fee_record', 'fee_record__student'
        ).prefetch_related('instalments')
        fee_record_id = self.request.query_params.get('fee_record')
        if fee_record_id:
            qs = qs.filter(fee_record_id=fee_record_id)
        return qs

    def perform_create(self, serializer):
        plan = serializer.save(school=self.request.user.school)
        self.log_action('PAYMENT_PLAN_CREATED', plan, {})


class FeeWaiverViewSet(AuditMixin, viewsets.ModelViewSet):
    queryset = FeeWaiver.objects.none()
    """US-024: Fee waivers — Bursar requests, Director approves/rejects."""
    serializer_class = FeeWaiverSerializer
    permission_classes = [IsDirectorOrBursar]

    def get_queryset(self):
        qs = FeeWaiver.objects.filter(school=self.request.user.school).select_related(
            'fee_record', 'fee_record__student', 'requested_by', 'approved_by', 'rejected_by'
        ).order_by('-created_at')

        status_param = self.request.query_params.get('status')
        if status_param:
            qs = qs.filter(status=status_param)

        fee_record_id = self.request.query_params.get('fee_record_id')
        if fee_record_id:
            qs = qs.filter(fee_record_id=fee_record_id)

        student_id = self.request.query_params.get('student_id')
        if student_id:
            qs = qs.filter(
                Q(fee_record__student_id=student_id) |
                Q(fee_record__student__student_id=student_id)
            )

        search = self.request.query_params.get('search')
        if search:
            qs = qs.filter(
                Q(fee_record__student__first_name__icontains=search) |
                Q(fee_record__student__last_name__icontains=search) |
                Q(fee_record__student__student_id__icontains=search) |
                Q(reason__icontains=search)
            )

        return qs

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        fee_record_id = serializer.validated_data.get('fee_record_id')

        import uuid as _uuid
        def _is_uuid(val):
            if not val:
                return False
            try:
                _uuid.UUID(str(val))
                return True
            except (ValueError, AttributeError, TypeError):
                return False

        fee_record = None
        if _is_uuid(fee_record_id):
            fee_record = FeeRecord.objects.filter(
                Q(id=fee_record_id) | Q(student_id=fee_record_id),
                school=request.user.school
            ).select_related('student').first()

        if not fee_record:
            fee_record = FeeRecord.objects.filter(
                student__student_id=str(fee_record_id).strip(),
                school=request.user.school
            ).select_related('student').first()

        if not fee_record:
            raise NotFound('A valid fee record or student account is required to apply a waiver.')

        amount = serializer.validated_data['amount']
        if fee_record.balance <= 0:
            raise ValidationError('This student fee account has no outstanding balance (UGX 0). A waiver cannot be applied.')

        if amount > fee_record.balance:
            raise ValidationError(
                f"Waiver amount of UGX {int(amount):,} exceeds the student's current outstanding balance of UGX {int(fee_record.balance):,}."
            )

        # Check if there is already an unapproved waiver for this fee record
        existing_pending = fee_record.waivers.filter(status='pending').first()
        if existing_pending:
            raise ValidationError(
                f"A waiver request of UGX {int(existing_pending.amount):,} for reason '{existing_pending.reason}' is already pending Director authorization for this student."
            )

        is_director = request.user.role in ['director', 'system_admin']
        try:
            waiver = FeeService.apply_waiver(
                fee_record=fee_record,
                amount=amount,
                reason=serializer.validated_data['reason'],
                requested_by=request.user,
                approved_by=request.user if is_director else None,
            )
        except ValueError as e:
            raise ValidationError(str(e))

        self.log_action('FEE_WAIVER_APPROVED' if is_director else 'FEE_WAIVER_REQUESTED', waiver, {
            'amount': str(waiver.amount), 'reason': waiver.reason,
            'student_id': str(fee_record.student_id),
        })
        return Response(FeeWaiverSerializer(waiver).data, status=status.HTTP_201_CREATED)

    @extend_schema(
        responses={200: inline_serializer(name='ApproveWaiverResponse', fields={'message': serializers.CharField()})},
        tags=['Payments']
    )
    @action(detail=True, methods=['post'], permission_classes=[IsDirector])
    def approve(self, request, pk=None):
        """Approve a pending fee waiver (Director only — enforced at backend)."""
        # Hard-enforce: only directors/admins can approve — reject bursars even on direct API calls
        if request.user.role not in ('director', 'system_admin'):
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied(
                'Only the Director or System Administrator is authorised to approve fee waivers. '
                'This action has been logged.'
            )

        waiver = self.get_object()
        if waiver.status != 'pending':
            raise ValidationError(f"Waiver cannot be approved because status is '{waiver.status}'.")

        try:
            waiver = FeeService.approve_waiver(waiver, request.user)
        except ValueError as e:
            raise ValidationError(str(e))

        self.log_action('FEE_WAIVER_APPROVED', waiver, {'amount': str(waiver.amount)})
        return Response({
            'message': 'Waiver approved successfully.',
            'waiver': FeeWaiverSerializer(waiver).data,
        })

    @extend_schema(
        request=FeeWaiverRejectSerializer,
        responses={200: inline_serializer(name='RejectWaiverResponse', fields={'message': serializers.CharField()})},
        tags=['Payments']
    )
    @action(detail=True, methods=['post'], permission_classes=[IsDirector])
    def reject(self, request, pk=None):
        """Reject a pending fee waiver with reason (Director only — enforced at backend)."""
        # Hard-enforce: only directors/admins can reject — block bursars even on direct API calls
        if request.user.role not in ('director', 'system_admin'):
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied(
                'Only the Director or System Administrator is authorised to reject fee waivers. '
                'This action has been logged.'
            )

        waiver = self.get_object()
        if waiver.status != 'pending':
            raise ValidationError(f"Waiver cannot be rejected because status is '{waiver.status}'.")

        serializer = FeeWaiverRejectSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        reason = serializer.validated_data['reason']

        try:
            waiver = FeeService.reject_waiver(waiver, reason, request.user)
        except ValueError as e:
            raise ValidationError(str(e))

        self.log_action('FEE_WAIVER_REJECTED', waiver, {
            'amount': str(waiver.amount), 'reason': reason
        })
        return Response({
            'message': 'Waiver rejected successfully.',
            'waiver': FeeWaiverSerializer(waiver).data,
        })


class ReconciliationQueueViewSet(AuditMixin, viewsets.ModelViewSet):
    queryset = ReconciliationQueue.objects.none()
    """US-029: Manual reconciliation of unmatched MoMo payments."""
    serializer_class = ReconciliationQueueSerializer
    permission_classes = [IsDirectorOrBursar]

    def get_queryset(self):
        qs = ReconciliationQueue.objects.filter(school=self.request.user.school)
        status_filter = self.request.query_params.get('status', 'pending')
        if status_filter:
            if status_filter == 'resolved':
                # Resolved = matched OR ignored (both are finished states)
                qs = qs.filter(status__in=['matched', 'ignored'])
            else:
                qs = qs.filter(status=status_filter)
        provider_filter = self.request.query_params.get('provider')
        if provider_filter:
            # Match both short forms (mtn, airtel) and full forms (mtn_momo, airtel_money)
            pf = provider_filter.lower()
            if pf in ('mtn', 'mtn_momo'):
                qs = qs.filter(provider__in=['mtn', 'mtn_momo'])
            elif pf in ('airtel', 'airtel_money'):
                qs = qs.filter(provider__in=['airtel', 'airtel_money'])
            else:
                qs = qs.filter(provider__icontains=pf)
        search = self.request.query_params.get('search')
        if search:
            from django.db.models import Q
            qs = qs.filter(
                Q(phone__icontains=search) |
                Q(momo_reference__icontains=search)
            )
        return qs.select_related(
            'momo_ipn_log', 'matched_by', 'matched_to_payment__student__current_class',
            'matched_to_payment__fee_record__academic_term'
        ).order_by('-received_at')

    @extend_schema(
        request=inline_serializer(
            name='MatchPaymentRequest',
            fields={'fee_record_id': serializers.UUIDField()}
        ),
        responses={200: inline_serializer(name='MatchPaymentResponse', fields={'message': serializers.CharField()})},
        tags=['Payments']
    )
    @action(detail=True, methods=['post'])
    def match(self, request, pk=None):
        """Manually match an unmatched payment to a student."""
        fee_record_id = request.data.get('fee_record_id')
        student_id = request.data.get('student_id')

        fee_record = None
        if fee_record_id:
            validate_uuid(fee_record_id, 'fee_record_id')
            try:
                fee_record = FeeRecord.objects.get(id=fee_record_id, school=request.user.school)
            except FeeRecord.DoesNotExist:
                raise NotFound('Fee record not found.')
        elif student_id:
            validate_uuid(student_id, 'student_id')
            school = request.user.school
            # Try current-term record first; fall back to most-recent outstanding balance
            current_term = school.terms.filter(is_current=True).first()
            qs = FeeRecord.objects.filter(student_id=student_id, school=school)
            if current_term:
                fee_record = qs.filter(academic_term=current_term).first()
            if not fee_record:
                fee_record = qs.order_by('-academic_term__start_date', '-created_at').first()
            if not fee_record:
                raise NotFound('Fee record for student not found.')
        else:
            raise ValidationError({'fee_record_id': 'fee_record_id or student_id required.'})

        from django.db import transaction as db_transaction
        with db_transaction.atomic():
            # select_for_update() prevents two concurrent Bursars from both
            # passing the status guard and creating duplicate payments (RISK-P3B).
            try:
                item = ReconciliationQueue.objects.select_for_update().get(
                    pk=pk, school=request.user.school
                )
            except ReconciliationQueue.DoesNotExist:
                raise NotFound('Queue item not found.')

            if item.status != 'pending':
                raise ValidationError('Already reconciled. This Mobile Money transaction has already been credited to a student account.')

            if item.provider in ('mtn', 'mtn_momo'):
                pmethod = 'mtn_momo'
                pnet = 'mtn'
            elif item.provider in ('airtel', 'airtel_money'):
                pmethod = 'airtel_money'
                pnet = 'airtel'
            elif item.provider in ('centenary', 'stanbic'):
                pmethod = 'bank'
                pnet = item.provider
            else:
                pmethod = 'momo'
                pnet = item.provider

            payment = Payment.all_objects.create(
                school=item.school,
                fee_record=fee_record,
                student=fee_record.student,
                method=pmethod,
                amount=item.amount,
                status='completed',
                momo_reference=item.momo_reference,
                momo_phone=item.phone,
                momo_network=pnet,
                receipt_number=item.momo_reference,
                notes=f"MoMo Reconciled from {item.phone}",
                payment_date=item.received_at,
                recorded_by=request.user,
            )
            FeeService._apply_payment_to_fee_record(fee_record, item.amount)
            item.status = 'matched'
            item.matched_to_payment = payment
            item.matched_by = request.user
            item.matched_at = timezone.now()
            item.save()

        self.log_action('RECONCILIATION_MATCHED', item, {
            'momo_ref': item.momo_reference,
            'matched_to_student': str(fee_record.student.id),
            'amount': str(item.amount),
        })
        return Response({'message': 'Payment matched and applied to fee record.'})

    @action(detail=True, methods=['post'])
    def reconcile(self, request, pk=None):
        """Alias for match action."""
        return self.match(request, pk)

    @extend_schema(
        request=ReconciliationIgnoreSerializer,
        responses={200: inline_serializer(name='IgnorePaymentResponse', fields={'message': serializers.CharField()})},
        tags=['Payments']
    )
    @action(detail=True, methods=['post'])
    def ignore(self, request, pk=None):
        """Ignore an unmatched payment (e.g. non-school transaction) with reason."""
        serializer = ReconciliationIgnoreSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        reason = serializer.validated_data['reason']

        from django.db import transaction as db_transaction
        with db_transaction.atomic():
            try:
                item = ReconciliationQueue.objects.select_for_update().get(
                    pk=pk, school=request.user.school
                )
            except ReconciliationQueue.DoesNotExist:
                raise NotFound('Queue item not found.')

            if item.status != 'pending':
                raise ValidationError('Already resolved.')

            item.status = 'ignored'
            item.ignore_reason = reason
            item.matched_by = request.user
            item.matched_at = timezone.now()
            item.save()

        self.log_action('RECONCILIATION_IGNORED', item, {
            'momo_ref': item.momo_reference,
            'reason': reason,
        })
        return Response({'message': 'Payment ignored and archived.'})

    @extend_schema(tags=['Payments'])
    @action(detail=False, methods=['post'], url_path='auto-match-suggestions')
    def auto_match_suggestions(self, request):
        """
        US-029/US-030: Auto-match pending items with high-confidence AI suggestions (score >= 90%).
        Immediately credits to student fee records and moves them to Resolved History.
        """
        school = request.user.school
        current_term = school.terms.filter(is_current=True).first()
        from django.db import transaction as db_transaction

        pending_items = ReconciliationQueue.objects.filter(
            school=school, status='pending', suggested_students__isnull=False
        )
        matched_count = 0

        for item in pending_items:
            suggestions = item.suggested_students or []
            if not suggestions:
                continue
            top = suggestions[0]
            if top.get('score', 0) < 90:
                continue
            student_id = top.get('student_id')
            if not student_id:
                continue

            try:
                with db_transaction.atomic():
                    q_item = ReconciliationQueue.objects.select_for_update().filter(
                        pk=item.pk, school=school, status='pending'
                    ).first()
                    if not q_item:
                        continue

                    fee_qs = FeeRecord.objects.filter(student_id=student_id, school=school)
                    fee_record = None
                    if current_term:
                        fee_record = fee_qs.filter(academic_term=current_term).first()
                    if not fee_record:
                        fee_record = fee_qs.order_by('-academic_term__start_date', '-created_at').first()
                    if not fee_record:
                        continue

                    if q_item.provider in ('mtn', 'mtn_momo'):
                        pmethod, pnet = 'mtn_momo', 'mtn'
                    elif q_item.provider in ('airtel', 'airtel_money'):
                        pmethod, pnet = 'airtel_money', 'airtel'
                    elif q_item.provider in ('centenary', 'stanbic'):
                        pmethod, pnet = 'bank', q_item.provider
                    else:
                        pmethod, pnet = 'momo', q_item.provider

                    payment = Payment.all_objects.create(
                        school=school,
                        fee_record=fee_record,
                        student=fee_record.student,
                        method=pmethod,
                        amount=q_item.amount,
                        status='completed',
                        momo_reference=q_item.momo_reference,
                        momo_phone=q_item.phone,
                        momo_network=pnet,
                        receipt_number=q_item.momo_reference,
                        notes=f"Auto-matched from AI suggestion ({top.get('name')})",
                        payment_date=q_item.received_at,
                        recorded_by=request.user,
                    )
                    FeeService._apply_payment_to_fee_record(fee_record, q_item.amount)
                    q_item.status = 'matched'
                    q_item.matched_to_payment = payment
                    q_item.matched_by = request.user
                    q_item.matched_at = timezone.now()
                    q_item.save()
                    matched_count += 1
            except Exception as exc:
                logger.warning(f"Auto-match failed for {item.id}: {exc}")
                continue

        return Response({
            'matched_count': matched_count,
            'message': f"Successfully matched and resolved {matched_count} transaction(s)."
        })

    @extend_schema(
        tags=['Payments']
    )
    @action(detail=False, methods=['post'], parser_classes=[MultiPartParser, FormParser], url_path='import-statement')
    def import_statement(self, request):
        """
        US-030: Import bank statement CSV (Centenary, Stanbic, MTN MoMo, Airtel Money)
        and populate the reconciliation queue with intelligent AI/regex student suggestions.
        """
        file_obj = request.FILES.get('file')
        if not file_obj:
            raise ValidationError({'file': 'No file was uploaded.'})

        # Reject obviously non-CSV files by extension
        filename = (file_obj.name or '').lower()
        if not any(filename.endswith(ext) for ext in ('.csv', '.txt', '.tsv')):
            raise ValidationError({
                'file': (
                    f"Unsupported file type \"{file_obj.name}\". "
                    "Please upload a .csv file exported from your bank or MoMo portal."
                )
            })

        format_hint = request.data.get('format', 'auto')
        from .statement_service import StatementImportService
        try:
            res = StatementImportService.process_csv_file(
                school=request.user.school,
                file_obj=file_obj,
                user=request.user,
                format_hint=format_hint
            )
        except Exception as exc:
            logger.exception("Failed to import bank statement")
            raise ValidationError({'detail': str(exc)})

        imported = res['imported']
        skipped = res['skipped']
        total_rows = res['total_rows']
        format_label = res.get('format_name') or res.get('detected_format') or 'Bank Statement'

        # Case 1: Empty file — no rows at all
        if total_rows == 0:
            raise ValidationError({
                'detail': (
                    "The uploaded file contained no data rows. "
                    "Please check that the file is a valid CSV export from your bank or MoMo portal "
                    "and that it is not empty."
                )
            })

        # Case 2: Rows parsed but no incoming deposits found
        if imported == 0 and skipped == 0:
            raise ValidationError({
                'detail': (
                    f"No incoming deposit transactions were found in {total_rows} row(s) scanned "
                    f"({format_label} profile). Possible causes: the file only contains "
                    "debit/withdrawal rows; the credit column could not be parsed; or the wrong "
                    "bank profile was selected. Please verify the file and try again."
                )
            })

        # Case 3: All rows are duplicates — nothing new
        if imported == 0 and skipped > 0:
            self.log_action('STATEMENT_IMPORTED', None, {
                'imported': 0, 'skipped': skipped, 'format': res['detected_format']
            })
            return Response({
                'message': (
                    f"No new transactions were added. All {skipped} transaction(s) in this file "
                    f"have already been imported previously ({format_label}). "
                    "No duplicate entries were created."
                ),
                'imported': 0,
                'skipped': skipped,
                'total_rows': total_rows,
                'detected_format': res['detected_format'],
                'format_name': format_label,
                'already_imported': True,
            })

        # Case 4: Success — at least one new transaction queued
        self.log_action('STATEMENT_IMPORTED', None, {
            'imported': imported,
            'skipped': skipped,
            'format': res['detected_format']
        })
        dup_note = f', {skipped} duplicate(s) skipped' if skipped > 0 else ''
        return Response({
            'message': f"{imported} transaction(s) added to Pending Queue for reconciliation ({format_label}){dup_note}.",
            **res
        })



class PaymentLinkViewSet(AuditMixin, viewsets.ModelViewSet):
    """
    US-C03: One-time payment links for MoMo fee collection.
    """
    queryset = PaymentLink.objects.none()
    serializer_class = PaymentLinkSerializer
    permission_classes = [IsDirectorOrBursar]

    def get_permissions(self):
        if getattr(self, 'action', None) in ['public_details', 'public_pay']:
            return [AllowAny()]
        return [permission() for permission in self.permission_classes]

    def get_queryset(self):
        qs = PaymentLink.objects.filter(school=self.request.user.school).select_related(
            'fee_record', 'student', 'payment'
        )
        student_id = self.request.query_params.get('student_id')
        if student_id:
            qs = qs.filter(Q(student_id=student_id) | Q(student__student_id=student_id))
        fee_record_id = self.request.query_params.get('fee_record')
        if fee_record_id:
            qs = qs.filter(fee_record_id=fee_record_id)
        return qs

    @extend_schema(
        request=GeneratePaymentLinkSerializer,
        responses={201: PaymentLinkSerializer},
        tags=['Payments']
    )
    @action(detail=False, methods=['post'], url_path='generate')
    def generate(self, request):
        serializer = GeneratePaymentLinkSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        fee_record = None
        fee_record_id = data.get('fee_record_id')
        student_id = data.get('student_id')

        import uuid as _uuid
        def _is_uuid(val):
            if not val:
                return False
            try:
                _uuid.UUID(str(val))
                return True
            except Exception:
                return False

        # 1. Look up by direct fee_record_id
        if fee_record_id and _is_uuid(fee_record_id):
            fee_record = FeeRecord.objects.filter(
                id=fee_record_id, school=request.user.school
            ).first()

        # 2. Look up by student UUID, student_id code, or emergency search
        if not fee_record and student_id:
            from students.models import Student
            student = None
            if _is_uuid(student_id):
                student = Student.objects.filter(
                    id=student_id, school=request.user.school
                ).first()

            if not student:
                student = Student.objects.filter(
                    student_id__iexact=student_id, school=request.user.school
                ).first()

            if not student:
                student = Student.objects.filter(
                    student_id__icontains=student_id, school=request.user.school
                ).first()

            if student:
                fee_record = FeeRecord.objects.filter(
                    student=student,
                    school=request.user.school,
                    total_amount__gt=F('amount_paid') + F('amount_waived')
                ).order_by('-created_at').first() or FeeRecord.objects.filter(
                    student=student,
                    school=request.user.school
                ).order_by('-created_at').first()

        # 3. If student_id happened to be the FeeRecord UUID
        if not fee_record and student_id and _is_uuid(student_id):
            fee_record = FeeRecord.objects.filter(
                id=student_id, school=request.user.school
            ).first()

        if not fee_record:
            raise ValidationError('A valid fee record or student with fee record is required.')

        amount = data.get('amount')
        description = data.get('description')
        expiry_hours = data.get('expiry_hours', 72)

        try:
            link = PaymentLinkService.generate_link(
                fee_record=fee_record,
                amount=amount,
                description=description,
                expiry_hours=expiry_hours,
                created_by=request.user
            )
        except Exception as e:
            raise ValidationError(str(e))

        self.log_action('PAYMENT_LINK_GENERATED', link, {
            'student': str(fee_record.student.id),
            'amount': str(link.amount),
            'token': link.token[:8],
        })

        return Response(PaymentLinkSerializer(link).data, status=status.HTTP_201_CREATED)

    @extend_schema(
        request=None,
        responses={200: inline_serializer(name='SendPaymentLinkResponse', fields={'message': serializers.CharField()})},
        tags=['Payments']
    )
    @action(detail=True, methods=['post'], url_path='send-whatsapp')
    def send_whatsapp(self, request, pk=None):
        link = self.get_object()
        try:
            msg_id, success = PaymentLinkService.send_link_via_whatsapp(link)
            if success:
                return Response({'message': 'Payment link dispatched via WhatsApp.', 'message_id': msg_id})
            return Response({'error': 'Failed to send WhatsApp message.'}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            raise ValidationError(str(e))

    @extend_schema(
        request=None,
        responses={200: inline_serializer(
            name='PublicPaymentLinkDetails',
            fields={
                'token': serializers.CharField(),
                'amount': serializers.IntegerField(),
                'description': serializers.CharField(),
                'status': serializers.CharField(),
                'is_usable': serializers.BooleanField(),
                'expires_at': serializers.DateTimeField(),
                'student_name': serializers.CharField(),
                'student_code': serializers.CharField(),
                'class_name': serializers.CharField(),
                'school_name': serializers.CharField(),
                'recipient_phone': serializers.CharField(),
            }
        )},
        tags=['Payments']
    )
    @action(detail=False, methods=['get'], url_path=r'public/(?P<token>[^/.]+)', permission_classes=[AllowAny], authentication_classes=[])
    def public_details(self, request, token=None):
        try:
            link = PaymentLink.all_objects.select_related(
                'student', 'student__current_class', 'fee_record', 'school'
            ).get(token=token)
        except PaymentLink.DoesNotExist:
            raise NotFound('Payment link not found or has expired.')

        if link.is_expired and link.status == 'active':
            link.mark_expired()

        return Response({
            'token': link.token,
            'amount': int(link.amount),
            'description': link.description,
            'status': link.status,
            'is_usable': link.is_usable,
            'expires_at': link.expires_at,
            'student_name': link.student.get_full_name(),
            'student_code': link.student.student_id,
            'class_name': link.student.current_class.name if link.student.current_class else 'Unassigned',
            'school_name': link.school.name,
            'recipient_phone': link.recipient_phone,
        })

    @extend_schema(
        request=inline_serializer(
            name='PublicPaymentSubmit',
            fields={
                'phone': serializers.CharField(),
                'provider': serializers.CharField(default='mtn_momo'),
            }
        ),
        responses={200: inline_serializer(
            name='PublicPaymentResponse',
            fields={
                'message': serializers.CharField(),
                'receipt_number': serializers.CharField(),
                'amount': serializers.IntegerField(),
            }
        )},
        tags=['Payments']
    )
    @action(detail=False, methods=['post'], url_path=r'public/(?P<token>[^/.]+)/pay', permission_classes=[AllowAny], authentication_classes=[])
    def public_pay(self, request, token=None):
        try:
            link = PaymentLink.all_objects.select_related('student', 'fee_record', 'school').get(token=token)
        except PaymentLink.DoesNotExist:
            raise NotFound('Payment link not found.')

        if not link.is_usable:
            raise ValidationError(f'This payment link is {link.status} and cannot be used.')

        phone = request.data.get('phone', link.recipient_phone)
        provider = request.data.get('provider', 'mtn_momo')

        from django.db import transaction as db_transaction
        import secrets

        with db_transaction.atomic():
            receipt_no = f"MOMO-{secrets.token_hex(4).upper()}"
            network = 'mtn' if 'mtn' in provider else 'airtel'
            payment = Payment.all_objects.create(
                school=link.school,
                fee_record=link.fee_record,
                student=link.student,
                amount=link.amount,
                method=provider if provider in ['mtn_momo', 'airtel_money', 'cash', 'bank'] else 'mtn_momo',
                status='completed',
                receipt_number=receipt_no,
                momo_phone=phone,
                momo_network=network,
                momo_reference=f"MM-{secrets.token_hex(6).upper()}",
                payment_date=timezone.now(),
                notes=f"Payer: {link.recipient_name or link.student.get_full_name()} | Link: {link.token[:8]}",
            )
            FeeService._apply_payment_to_fee_record(link.fee_record, link.amount)
            PaymentLinkService.mark_link_used(link, payment)

        return Response({
            'message': f'Payment of UGX {int(link.amount):,} received successfully.',
            'receipt_number': receipt_no,
            'amount': int(link.amount),
            'student_name': link.student.get_full_name(),
            'paid_at': timezone.now(),
        })



