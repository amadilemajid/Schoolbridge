"""
Payments views — fee structures, payments, MoMo, reconciliation.
"""
import csv
import logging
from django.conf import settings
from django.http import HttpResponse
from django.utils import timezone
from django.db.models import Sum, Count, Q, F
from rest_framework import viewsets, generics, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from audit.mixins import AuditMixin
from schools.permissions import IsDirector, IsDirectorOrBursar, IsSchoolStaff
from .models import (
    FeeStructure, FeeStructureItem, FeeRecord, Payment,
    PaymentPlan, PaymentPlanInstalment, FeeWaiver, ReconciliationQueue,
)
from .services import FeeService, MoMoService
from .serializers import (
    FeeStructureSerializer, FeeRecordSerializer, PaymentSerializer,
    PaymentCreateSerializer, PaymentPlanSerializer, FeeWaiverSerializer,
    ReconciliationQueueSerializer, FeeReversalSerializer,
)

logger = logging.getLogger('payments')


class FeeStructureViewSet(AuditMixin, viewsets.ModelViewSet):
    """US-016: Fee structure management."""
    serializer_class = FeeStructureSerializer
    permission_classes = [IsDirectorOrBursar]

    def get_queryset(self):
        qs = FeeStructure.objects.filter(school=self.request.user.school, is_active=True)
        term_id = self.request.query_params.get('term_id')
        if term_id:
            qs = qs.filter(academic_term_id=term_id)
        return qs.select_related('academic_term', 'class_group').prefetch_related('items')

    def perform_create(self, serializer):
        fs = serializer.save(school=self.request.user.school, created_by=self.request.user)
        self.log_action('FEE_STRUCTURE_CREATED', fs, {'name': fs.name})

    @action(detail=True, methods=['post'], permission_classes=[IsDirector])
    def clone(self, request, pk=None):
        """Clone fee structure to another term (US-016)."""
        source = self.get_object()
        term_id = request.data.get('target_term_id')
        if not term_id:
            return Response({'error': 'target_term_id required.'}, status=400)
        from schools.models import AcademicTerm
        try:
            target_term = AcademicTerm.objects.get(id=term_id, school=request.user.school)
        except AcademicTerm.DoesNotExist:
            return Response({'error': 'Term not found.'}, status=404)

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


class FeeRecordViewSet(AuditMixin, viewsets.ReadOnlyModelViewSet):
    """
    US-017: Student fee balance (real-time, <30s from payment).
    US-018: Class-level summary.
    """
    serializer_class = FeeRecordSerializer
    permission_classes = [IsDirectorOrBursar]

    def get_queryset(self):
        qs = FeeRecord.objects.filter(school=self.request.user.school)
        term_id = self.request.query_params.get('term_id')
        student_id = self.request.query_params.get('student_id')
        class_id = self.request.query_params.get('class_id')
        if term_id:
            qs = qs.filter(academic_term_id=term_id)
        if student_id:
            qs = qs.filter(student_id=student_id)
        if class_id:
            qs = qs.filter(student__current_class_id=class_id)
        return qs.select_related('student', 'student__current_class', 'academic_term')

    @action(detail=False, methods=['get'])
    def class_summary(self, request):
        """US-018: Class-level payment summary."""
        term_id = request.query_params.get('term_id')
        class_id = request.query_params.get('class_id')
        if not term_id or not class_id:
            return Response({'error': 'term_id and class_id are required.'}, status=400)
        from students.models import ClassGroup
        try:
            class_group = ClassGroup.objects.get(id=class_id, school=request.user.school)
        except ClassGroup.DoesNotExist:
            return Response({'error': 'Class not found.'}, status=404)
        from schools.models import AcademicTerm
        try:
            term = AcademicTerm.objects.get(id=term_id, school=request.user.school)
        except AcademicTerm.DoesNotExist:
            return Response({'error': 'Term not found.'}, status=404)
        records = FeeService.get_class_fee_summary(class_group, term)
        return Response(FeeRecordSerializer(records, many=True).data)

    @action(detail=False, methods=['get'])
    def defaulters(self, request):
        """US-020: Defaulter list. CSV export supported."""
        term_id = request.query_params.get('term_id')
        if not term_id:
            qs_term = request.user.school.terms.filter(is_current=True).first()
            if not qs_term:
                return Response({'error': 'No current term found.'}, status=400)
        else:
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

    @action(detail=False, methods=['get'])
    def dashboard(self, request):
        """US-022: School-wide fee dashboard."""
        term_id = request.query_params.get('term_id')
        if term_id:
            from schools.models import AcademicTerm
            term = AcademicTerm.objects.get(id=term_id, school=request.user.school)
        else:
            term = request.user.school.terms.filter(is_current=True).first()
        if not term:
            return Response({'error': 'No current term.'}, status=400)
        return Response(FeeService.get_dashboard_summary(request.user.school, term))


class PaymentViewSet(AuditMixin, viewsets.ModelViewSet):
    """
    US-019: Manual payment recording.
    US-023: Payment reversal.
    """
    permission_classes = [IsDirectorOrBursar]

    def get_serializer_class(self):
        if self.action == 'create':
            return PaymentCreateSerializer
        return PaymentSerializer

    def get_queryset(self):
        qs = Payment.objects.filter(school=self.request.user.school)
        fee_record_id = self.request.query_params.get('fee_record_id')
        student_id = self.request.query_params.get('student_id')
        if fee_record_id:
            qs = qs.filter(fee_record_id=fee_record_id)
        if student_id:
            qs = qs.filter(student_id=student_id)
        return qs.select_related('student', 'fee_record', 'recorded_by')

    def perform_create(self, serializer):
        fee_record_id = serializer.validated_data.get('fee_record_id')
        amount = serializer.validated_data.get('amount')
        method = serializer.validated_data.get('method')
        try:
            fee_record = FeeRecord.objects.get(id=fee_record_id, school=self.request.user.school)
        except FeeRecord.DoesNotExist:
            from rest_framework.exceptions import NotFound
            raise NotFound('Fee record not found.')
        payment = FeeService.record_manual_payment(
            fee_record=fee_record,
            amount=amount,
            method=method,
            recorded_by=self.request.user,
            receipt_number=serializer.validated_data.get('receipt_number', ''),
            notes=serializer.validated_data.get('notes', ''),
            bank_reference=serializer.validated_data.get('bank_reference', ''),
        )
        self.log_action('PAYMENT_RECORDED', payment, {
            'amount': str(amount), 'method': method,
            'student': str(fee_record.student.id),
        })
        return payment

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payment = self.perform_create(serializer)
        return Response(PaymentSerializer(payment).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'], permission_classes=[IsDirector])
    def approve(self, request, pk=None):
        """Approve a large payment that required Director sign-off."""
        payment = self.get_object()
        if payment.school != request.user.school:
            return Response({'error': 'Not found.'}, status=404)
        try:
            FeeService.approve_payment(payment, request.user)
        except ValueError as e:
            return Response({'error': str(e)}, status=400)
        self.log_action('PAYMENT_APPROVED', payment, {'amount': str(payment.amount)})
        return Response({'message': 'Payment approved.'})

    @action(detail=True, methods=['post'], permission_classes=[IsDirector])
    def reverse(self, request, pk=None):
        """US-023: Reverse a payment with reason."""
        payment = self.get_object()
        serializer = FeeReversalSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        reason = serializer.validated_data['reason']
        try:
            FeeService.reverse_payment(payment, reason, request.user)
        except ValueError as e:
            return Response({'error': str(e)}, status=400)
        self.log_action('PAYMENT_REVERSED', payment, {
            'amount': str(payment.amount), 'reason': reason
        })
        return Response({'message': 'Payment reversed successfully.'})


class PaymentPlanViewSet(AuditMixin, viewsets.ModelViewSet):
    """US-021: Payment plans."""
    serializer_class = PaymentPlanSerializer
    permission_classes = [IsDirectorOrBursar]

    def get_queryset(self):
        return PaymentPlan.objects.filter(school=self.request.user.school).select_related(
            'fee_record', 'fee_record__student'
        ).prefetch_related('instalments')

    def perform_create(self, serializer):
        plan = serializer.save(school=self.request.user.school, created_by=self.request.user)
        # Schedule Celery reminders per instalment (US-021)
        from automation.tasks import schedule_instalment_reminders
        schedule_instalment_reminders.delay(str(plan.id))
        self.log_action('PAYMENT_PLAN_CREATED', plan, {})


class FeeWaiverViewSet(AuditMixin, viewsets.ModelViewSet):
    """US-024: Fee waivers — Director approval required."""
    serializer_class = FeeWaiverSerializer
    permission_classes = [IsDirectorOrBursar]

    def get_queryset(self):
        return FeeWaiver.objects.filter(school=self.request.user.school)

    def perform_create(self, serializer):
        fee_record_id = serializer.validated_data.get('fee_record_id')
        fee_record = FeeRecord.objects.get(id=fee_record_id, school=self.request.user.school)
        waiver = FeeService.apply_waiver(
            fee_record=fee_record,
            amount=serializer.validated_data['amount'],
            reason=serializer.validated_data['reason'],
            requested_by=self.request.user,
            approved_by=self.request.user if self.request.user.role == 'director' else None,
        )
        self.log_action('FEE_WAIVER_APPLIED', waiver, {
            'amount': str(waiver.amount), 'reason': waiver.reason
        })
        return Response(FeeWaiverSerializer(waiver).data, status=201)


class ReconciliationQueueViewSet(AuditMixin, viewsets.ModelViewSet):
    """US-029: Manual reconciliation of unmatched MoMo payments."""
    serializer_class = ReconciliationQueueSerializer
    permission_classes = [IsDirectorOrBursar]

    def get_queryset(self):
        qs = ReconciliationQueue.objects.filter(school=self.request.user.school)
        status_filter = self.request.query_params.get('status', 'pending')
        if status_filter:
            qs = qs.filter(status=status_filter)
        return qs.order_by('-received_at')

    @action(detail=True, methods=['post'])
    def match(self, request, pk=None):
        """Manually match an unmatched payment to a student."""
        item = self.get_object()
        if item.status != 'pending':
            return Response({'error': 'Already resolved.'}, status=400)

        fee_record_id = request.data.get('fee_record_id')
        if not fee_record_id:
            return Response({'error': 'fee_record_id required.'}, status=400)

        try:
            fee_record = FeeRecord.objects.get(id=fee_record_id, school=request.user.school)
        except FeeRecord.DoesNotExist:
            return Response({'error': 'Fee record not found.'}, status=404)

        from django.db import transaction as db_transaction
        with db_transaction.atomic():
            payment = Payment.all_objects.create(
                school=item.school,
                fee_record=fee_record,
                student=fee_record.student,
                method=f"{item.provider}_money",
                amount=item.amount,
                status='completed',
                momo_reference=item.momo_reference,
                momo_phone=item.phone,
                momo_network=item.provider,
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
        })
        return Response({'message': 'Payment matched and applied to fee record.'})
