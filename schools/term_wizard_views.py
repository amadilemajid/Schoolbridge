"""
Composite Term Planning Wizard API (US-E04).
Allows Director to configure a complete academic term in a single atomic transaction:
1. Academic Year & Term Dates
2. Fee Structures & Line Items mapped to Classes
3. Optional Timetable Cloning from a previous term
4. Optional Immediate Activation with FeeRecord generation
"""
import logging
from django.db import transaction
from django.utils import timezone
from rest_framework import serializers, status
from rest_framework.views import APIView
from rest_framework.response import Response
from drf_spectacular.utils import extend_schema, inline_serializer

from audit.mixins import AuditMixin
from schools.permissions import IsDirector
from schools.models import AcademicYear, AcademicTerm
from students.models import ClassGroup
from payments.models import FeeStructure, FeeStructureItem, FeeRecord
from payments.services import FeeService
from automation.tasks import schedule_fee_reminders

logger = logging.getLogger('schoolbridge')


class FeeStructureItemInputSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=100)
    amount = serializers.DecimalField(max_digits=12, decimal_places=0, min_value=0)
    is_mandatory = serializers.BooleanField(default=True)
    description = serializers.CharField(max_length=255, required=False, allow_blank=True, default='')


class FeeStructureInputSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=100)
    class_group_ids = serializers.ListField(
        child=serializers.CharField(),
        allow_empty=False,
        help_text="List of ClassGroup IDs to associate with this fee structure"
    )
    items = FeeStructureItemInputSerializer(many=True, allow_empty=False)


class TermPlanningWizardSerializer(serializers.Serializer):
    academic_year_id = serializers.CharField(required=False, allow_null=True)
    year = serializers.IntegerField(required=False, allow_null=True, min_value=2020, max_value=2050)
    term_number = serializers.IntegerField(min_value=1, max_value=4)
    name = serializers.CharField(max_length=100)
    start_date = serializers.DateField()
    end_date = serializers.DateField()
    fee_deadline = serializers.DateField()
    
    fee_structures = FeeStructureInputSerializer(many=True, required=False, default=list)
    clone_timetable_from_term_id = serializers.CharField(required=False, allow_null=True)
    activate_immediately = serializers.BooleanField(default=False)

    def validate(self, data):
        if data['end_date'] <= data['start_date']:
            raise serializers.ValidationError({"end_date": "end_date must be strictly after start_date."})
        if not (data['start_date'] <= data['fee_deadline'] <= data['end_date']):
            raise serializers.ValidationError({"fee_deadline": "fee_deadline must fall between start_date and end_date."})
        if not data.get('academic_year_id') and not data.get('year'):
            raise serializers.ValidationError("Either academic_year_id or year must be provided.")
        return data


class TermPlanningWizardView(AuditMixin, APIView):
    """
    POST /api/v1/schools/term-planning-wizard/
    Director only. Atomically provisions a new term, associated fee structures,
    optional timetable slots, and generates student billing upon activation.
    """
    permission_classes = [IsDirector]

    @extend_schema(
        summary="Composite Term Planning Wizard",
        description="Creates an academic term, class fee structures, line items, and optional timetable clone in one atomic transaction.",
        request=TermPlanningWizardSerializer,
        responses={
            201: inline_serializer(
                name="TermPlanningWizardResponse",
                fields={
                    "success": serializers.BooleanField(),
                    "term_id": serializers.UUIDField(),
                    "term_name": serializers.CharField(),
                    "is_active": serializers.BooleanField(),
                    "fee_structures_created": serializers.IntegerField(),
                    "fee_records_generated": serializers.IntegerField(),
                    "timetable_slots_cloned": serializers.IntegerField(),
                    "message": serializers.CharField(),
                }
            )
        },
        tags=["Schools"]
    )
    def post(self, request):
        serializer = TermPlanningWizardSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        d = serializer.validated_data

        school = request.user.school

        with transaction.atomic():
            # 1. Resolve Academic Year
            if d.get('academic_year_id'):
                academic_year = AcademicYear.objects.filter(
                    id=d['academic_year_id'], school=school
                ).first()
                if not academic_year:
                    return Response({"error": "AcademicYear not found for this school."}, status=404)
            else:
                academic_year, _ = AcademicYear.objects.get_or_create(
                    school=school,
                    year=d['year'],
                    defaults={'is_current': True}
                )

            # 2. Create Academic Term
            term = AcademicTerm.objects.create(
                school=school,
                academic_year=academic_year,
                term_number=d['term_number'],
                name=d['name'],
                start_date=d['start_date'],
                end_date=d['end_date'],
                fee_deadline=d['fee_deadline'],
                is_active=False,
                is_current=False,
            )

            # 3. Create Fee Structures & Items
            fee_structures_count = 0
            for fs_data in d.get('fee_structures', []):
                class_groups = ClassGroup.objects.filter(
                    id__in=fs_data['class_group_ids'], school=school
                )
                targets = list(class_groups) if class_groups.exists() else [None]
                for cg in targets:
                    fee_structure = FeeStructure.objects.create(
                        school=school,
                        academic_term=term,
                        class_group=cg,
                        name=fs_data['name'] if not cg else f"{cg.name} - {fs_data['name']}",
                        created_by=request.user,
                    )
                    # Create items
                    for item_data in fs_data['items']:
                        FeeStructureItem.objects.create(
                            fee_structure=fee_structure,
                            name=item_data['name'],
                            amount=item_data['amount'],
                            is_mandatory=item_data.get('is_mandatory', True),
                            description=item_data.get('description', ''),
                        )
                    fee_structures_count += 1

            # 4. Optional Timetable Cloning
            cloned_slots_count = 0
            clone_term_id = d.get('clone_timetable_from_term_id')
            if clone_term_id:
                from timetable.models import TimetableVersion, TimetableSlot
                source_versions = TimetableVersion.objects.filter(
                    academic_term_id=clone_term_id, school=school, is_active=True
                )
                for source_version in source_versions:
                    new_version = TimetableVersion.objects.create(
                        school=school,
                        academic_term=term,
                        class_group=source_version.class_group,
                        version_number=1,
                        is_active=True,
                        effective_from=term.start_date,
                        created_by=request.user,
                    )
                    source_slots = TimetableSlot.objects.filter(timetable_version=source_version)
                    new_slots = [
                        TimetableSlot(
                            timetable_version=new_version,
                            school=school,
                            day_of_week=slot.day_of_week,
                            period_number=slot.period_number,
                            subject=slot.subject,
                            subject_name=slot.subject_name,
                            teacher=slot.teacher,
                            start_time=slot.start_time,
                            end_time=slot.end_time,
                            room=slot.room,
                            slot_type=slot.slot_type,
                        )
                        for slot in source_slots
                    ]
                    TimetableSlot.objects.bulk_create(new_slots)
                    cloned_slots_count += len(new_slots)

            # 5. Immediate Activation if requested
            fee_records_count = 0
            if d.get('activate_immediately'):
                # Deactivate previously active terms
                AcademicTerm.objects.filter(school=school, is_active=True).update(is_active=False, is_current=False)

                term.is_active = True
                term.is_current = True
                term.activated_at = timezone.now()
                term.activated_by = request.user
                term.save()

                # US-016: Generate one FeeRecord per active student with the correct total_amount
                try:
                    fee_records_count = FeeService.generate_fee_records_for_term(term)
                except Exception as e:
                    logger.error(f"Could not generate FeeRecords for term {term.pk}: {e}")
                    fee_records_count = 0

                # Schedule fee reminders
                try:
                    schedule_fee_reminders.delay(str(term.pk))
                except Exception as e:
                    logger.warning(f"Could not enqueue schedule_fee_reminders task: {e}")

            self.log_action('TERM_PLANNING_WIZARD_COMPLETED', term, {
                'term_name': term.name,
                'fee_structures': fee_structures_count,
                'cloned_slots': cloned_slots_count,
                'activated': term.is_active,
            })

            return Response({
                "success": True,
                "term_id": str(term.id),
                "term_name": term.name,
                "is_active": term.is_active,
                "fee_structures_created": fee_structures_count,
                "fee_records_generated": fee_records_count,
                "timetable_slots_cloned": cloned_slots_count,
                "message": f"Term {term.name} planned and provisioned successfully."
            }, status=status.HTTP_201_CREATED)
