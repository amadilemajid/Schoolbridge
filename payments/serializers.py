"""
Payments serializers — full validation for all payment-related data.
"""
from decimal import Decimal
from rest_framework import serializers
from django.conf import settings
from .models import (
    FeeStructure, FeeStructureItem, FeeRecord, Payment,
    PaymentPlan, PaymentPlanInstalment, FeeWaiver, ReconciliationQueue,
)


class FeeStructureItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = FeeStructureItem
        fields = ['id', 'name', 'amount', 'is_mandatory', 'description']


class FeeStructureSerializer(serializers.ModelSerializer):
    items = FeeStructureItemSerializer(many=True)
    total_amount = serializers.DecimalField(max_digits=12, decimal_places=0, read_only=True)

    class Meta:
        model = FeeStructure
        fields = [
            'id', 'academic_term', 'class_group', 'name', 'is_active',
            'items', 'total_amount', 'requires_approval',
            'approved_by', 'approved_at', 'created_at',
        ]
        read_only_fields = ['id', 'requires_approval', 'approved_by', 'approved_at', 'created_at']

    def validate_items(self, value):
        if not value:
            raise serializers.ValidationError("At least one fee item is required.")
        for item in value:
            if item.get('amount', 0) <= 0:
                raise serializers.ValidationError(f"Amount for '{item.get('name')}' must be > 0.")
        return value

    def create(self, validated_data):
        items_data = validated_data.pop('items')
        fee_structure = FeeStructure.all_objects.create(**validated_data)
        for item in items_data:
            FeeStructureItem.objects.create(fee_structure=fee_structure, **item)
        return fee_structure

    def update(self, instance, validated_data):
        items_data = validated_data.pop('items', None)
        # If term is already active, flag as needing Director approval (US-016)
        if instance.academic_term.is_active:
            validated_data['requires_approval'] = True
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        if items_data is not None:
            instance.items.all().delete()
            for item in items_data:
                FeeStructureItem.objects.create(fee_structure=instance, **item)
        return instance


class FeeRecordSerializer(serializers.ModelSerializer):
    student_name = serializers.CharField(source='student.get_full_name', read_only=True)
    student_id_code = serializers.CharField(source='student.student_id', read_only=True)
    class_name = serializers.CharField(source='student.current_class.name', read_only=True)
    balance = serializers.DecimalField(max_digits=12, decimal_places=0, read_only=True)
    is_fully_paid = serializers.BooleanField(read_only=True)
    payment_percentage = serializers.IntegerField(read_only=True)

    class Meta:
        model = FeeRecord
        fields = [
            'id', 'student', 'student_name', 'student_id_code', 'class_name',
            'academic_term', 'total_amount', 'amount_paid', 'amount_waived',
            'balance', 'is_fully_paid', 'payment_percentage', 'updated_at',
        ]
        read_only_fields = fields


class PaymentSerializer(serializers.ModelSerializer):
    student_name = serializers.CharField(source='student.get_full_name', read_only=True)
    recorded_by_name = serializers.CharField(source='recorded_by.get_full_name', read_only=True)

    class Meta:
        model = Payment
        fields = [
            'id', 'student', 'student_name', 'fee_record', 'method', 'amount',
            'status', 'momo_reference', 'momo_phone', 'momo_network',
            'receipt_number', 'notes', 'bank_reference',
            'requires_approval', 'approved_by', 'approved_at',
            'is_reversed', 'reversal_reason', 'reversed_at',
            'recorded_by', 'recorded_by_name', 'payment_date', 'created_at',
        ]
        read_only_fields = [
            'id', 'status', 'momo_reference', 'momo_phone', 'momo_network',
            'requires_approval', 'approved_by', 'approved_at',
            'is_reversed', 'reversed_at', 'created_at',
        ]


class PaymentCreateSerializer(serializers.Serializer):
    """For creating a manual payment."""
    fee_record_id = serializers.UUIDField()
    amount = serializers.DecimalField(max_digits=12, decimal_places=0, min_value=Decimal('1'))
    method = serializers.ChoiceField(choices=['cash', 'bank'])
    receipt_number = serializers.CharField(required=False, allow_blank=True, default='')
    notes = serializers.CharField(required=False, allow_blank=True, default='')
    bank_reference = serializers.CharField(required=False, allow_blank=True, default='')

    def validate_amount(self, value):
        if value <= 0:
            raise serializers.ValidationError("Amount must be greater than 0.")
        return value


class FeeReversalSerializer(serializers.Serializer):
    reason = serializers.CharField(min_length=10,
        error_messages={'min_length': 'Reversal reason must be at least 10 characters.'})


class PaymentPlanInstalmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = PaymentPlanInstalment
        fields = ['id', 'instalment_number', 'amount', 'due_date', 'paid_date', 'status']
        read_only_fields = ['id', 'paid_date', 'status']


class PaymentPlanSerializer(serializers.ModelSerializer):
    instalments = PaymentPlanInstalmentSerializer(many=True)

    class Meta:
        model = PaymentPlan
        fields = [
            'id', 'fee_record', 'total_amount', 'status',
            'notes', 'instalments', 'created_at',
        ]
        read_only_fields = ['id', 'status', 'created_at']

    def validate_instalments(self, value):
        if not (1 <= len(value) <= 4):
            raise serializers.ValidationError("Payment plan must have 1 to 4 instalments.")
        return value

    def validate(self, data):
        instalments = data.get('instalments', [])
        total = data.get('total_amount', 0)
        instalment_sum = sum(i['amount'] for i in instalments)
        if abs(instalment_sum - total) > 1:  # Allow 1 UGX rounding difference
            raise serializers.ValidationError(
                f"Instalment amounts ({instalment_sum:,}) must sum to total ({total:,})."
            )
        return data

    def create(self, validated_data):
        from django.db import transaction
        instalments_data = validated_data.pop('instalments')
        with transaction.atomic():
            plan = PaymentPlan.all_objects.create(**validated_data)
            for i, inst in enumerate(instalments_data, start=1):
                PaymentPlanInstalment.objects.create(
                    plan=plan,
                    instalment_number=i,
                    **inst,
                )
        return plan


class FeeWaiverSerializer(serializers.ModelSerializer):
    fee_record_id = serializers.UUIDField(write_only=True)

    class Meta:
        model = FeeWaiver
        fields = [
            'id', 'fee_record_id', 'fee_record', 'amount', 'reason',
            'approved_by', 'approved_at', 'created_at',
        ]
        read_only_fields = ['id', 'fee_record', 'approved_by', 'approved_at', 'created_at']

    def validate_amount(self, value):
        if value <= 0:
            raise serializers.ValidationError("Waiver amount must be greater than 0.")
        return value


class ReconciliationQueueSerializer(serializers.ModelSerializer):
    class Meta:
        model = ReconciliationQueue
        fields = [
            'id', 'momo_reference', 'phone', 'amount', 'provider',
            'status', 'suggested_students', 'received_at',
            'matched_at', 'matched_by', 'alert_24hr_sent', 'alert_48hr_sent',
        ]
        read_only_fields = fields
