"""
Structured Timetable Backend — API Views.
"""
from rest_framework import viewsets, status, serializers
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.filters import SearchFilter
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.permissions import IsAuthenticated
from rest_framework.exceptions import ValidationError, NotFound
from config.validators import validate_uuid
from drf_spectacular.utils import extend_schema, OpenApiParameter, OpenApiTypes, inline_serializer
from config.mixins import ExportMixin


from audit.mixins import AuditMixin
from schools.permissions import IsSchoolStaff, IsDirector, IsSameSchool
from timetable.models import TimetableVersion, TimetableSlot, SubstitutionRecord
from timetable.serializers import (
    TimetableSlotSerializer, TimetableVersionSerializer,
    TimetableVersionCreateSerializer, SubstitutionRecordSerializer
)
from timetable.services import TimetableService


class TimetableVersionViewSet(ExportMixin, AuditMixin, viewsets.ModelViewSet):
    queryset = TimetableVersion.objects.none()
    """Manage timetable versions."""
    permission_classes = [IsAuthenticated, IsSchoolStaff, IsSameSchool]

    def get_serializer_class(self):
        if self.action == 'create':
            return TimetableVersionCreateSerializer
        return TimetableVersionSerializer

    def get_queryset(self):
        qs = TimetableVersion.objects.filter(school=self.request.user.school).select_related(
            'class_group', 'academic_term'
        )
        # Allow frontend to filter by class group, term, and active status
        class_group_id = self.request.query_params.get('class_group')
        if class_group_id:
            qs = qs.filter(class_group_id=class_group_id)
        academic_term_id = self.request.query_params.get('academic_term')
        if academic_term_id:
            qs = qs.filter(academic_term_id=academic_term_id)
        is_active_param = self.request.query_params.get('is_active')
        if is_active_param == 'true':
            qs = qs.filter(is_active=True)
        elif is_active_param == 'false':
            qs = qs.filter(is_active=False)
        return qs

    def perform_create(self, serializer):
        version = serializer.save(school=self.request.user.school, created_by=self.request.user)
        self.log_action('TIMETABLE_VERSION_CREATED', version, {
            'class_group': version.class_group.name,
            'version_number': version.version_number
        })

    def perform_update(self, serializer):
        version = serializer.save()
        self.log_action('TIMETABLE_VERSION_UPDATED', version, {
            'class_group': version.class_group.name,
            'version_number': version.version_number
        })

    def perform_destroy(self, instance):
        self.log_action('TIMETABLE_VERSION_DELETED', instance, {
            'class_group': instance.class_group.name,
            'version_number': instance.version_number
        })
        super().perform_destroy(instance)

    @extend_schema(
        responses={200: inline_serializer(name='PublishTimetableVersionResponse', fields={'message': serializers.CharField(), 'status': serializers.CharField()})},
        tags=['Timetable']
    )
    @action(detail=True, methods=['post'], permission_classes=[IsAuthenticated, IsSchoolStaff, IsSameSchool], url_path='publish')
    def publish(self, request, pk=None):
        """Publish timetable version (make active and sync to WhatsApp format)."""
        version = self.get_object()
        version.is_active = True
        version.save()
        # Side effects inside save() will deactivate other versions
        self.log_action('TIMETABLE_VERSION_PUBLISHED', version, {
            'class_group': version.class_group.name,
            'version_number': version.version_number
        })
        # Trigger WhatsApp format update
        try:
            from timetable.tasks import sync_timetable_to_whatsapp_format
            sync_timetable_to_whatsapp_format.delay(
                school_id=str(version.school.id),
                class_group_id=str(version.class_group.id),
                term_id=str(version.academic_term.id)
            )
        except Exception:
            try:
                from timetable.tasks import sync_timetable_to_whatsapp_format
                sync_timetable_to_whatsapp_format(
                    school_id=str(version.school.id),
                    class_group_id=str(version.class_group.id),
                    term_id=str(version.academic_term.id)
                )
            except Exception:
                pass
        return Response({
            'message': f'Version {version.version_number} is now published and active.',
            'status': 'Published'
        })

    @extend_schema(
        responses={200: inline_serializer(name='ActivateTimetableVersionResponse', fields={'message': serializers.CharField(), 'status': serializers.CharField()})},
        tags=['Timetable']
    )
    @action(detail=True, methods=['post'], permission_classes=[IsAuthenticated, IsSchoolStaff, IsSameSchool])
    def activate(self, request, pk=None):
        """Manually activate this timetable version."""
        return self.publish(request, pk)

    @extend_schema(
        responses={200: inline_serializer(
            name='ValidateConflictsResponse',
            fields={
                'conflicts': serializers.ListField(child=serializers.CharField())
            }
        )},
        tags=['Timetable']
    )
    @action(detail=True, methods=['get'], url_path='validate-conflicts')
    def validate_conflicts(self, request, pk=None):
        """Validate if there are teacher double-bookings."""
        version = self.get_object()
        conflicts = TimetableService.validate_no_conflicts(version)
        return Response({'conflicts': conflicts})

    @extend_schema(
        parameters=[
            OpenApiParameter('day', OpenApiTypes.INT, OpenApiParameter.QUERY, required=False, description="0 (Monday) to 4 (Friday)"),
        ],
        responses={200: inline_serializer(
            name='WhatsAppPreviewResponse',
            fields={'preview': serializers.CharField()}
        )},
        tags=['Timetable']
    )
    @action(detail=True, methods=['get'], url_path='whatsapp-preview')
    def whatsapp_preview(self, request, pk=None):
        """Get the formatted WhatsApp timetable preview."""
        version = self.get_object()
        day = request.query_params.get('day')
        day_of_week = int(day) if (day is not None and day.isdigit()) else None
        
        preview = TimetableService.format_for_whatsapp(
            class_group=version.class_group,
            term=version.academic_term,
            day_of_week=day_of_week
        )
        return Response({'preview': preview})


class TimetableSlotViewSet(AuditMixin, viewsets.ModelViewSet):
    queryset = TimetableSlot.objects.none()
    """Manage timetable slots."""
    serializer_class = TimetableSlotSerializer
    permission_classes = [IsAuthenticated, IsSchoolStaff, IsSameSchool]
    filter_backends = [DjangoFilterBackend, SearchFilter]
    filterset_fields = ['day_of_week', 'teacher', 'subject']
    search_fields = ['teacher__first_name', 'teacher__last_name', 'subject__name', 'room']

    def get_queryset(self):
        qs = TimetableSlot.objects.filter(school=self.request.user.school).select_related(
            'timetable_version', 'subject', 'teacher'
        )
        version_id = self.request.query_params.get('timetable_version')
        if version_id:
            validate_uuid(version_id, 'timetable_version')
            qs = qs.filter(timetable_version_id=version_id)
        return qs

    def perform_create(self, serializer):
        version = serializer.validated_data['timetable_version']
        if version.school != self.request.user.school:
            raise ValidationError('Invalid timetable version school.')
        
        slot = serializer.save(school=self.request.user.school)
        self.log_action('TIMETABLE_SLOT_CREATED', slot, {
            'timetable_version': str(slot.timetable_version.id),
            'day_of_week': slot.day_of_week,
            'period_number': slot.period_number
        })
        # Sync to WhatsApp
        from timetable.tasks import sync_timetable_to_whatsapp_format
        sync_timetable_to_whatsapp_format.delay(
            school_id=str(slot.school.id),
            class_group_id=str(version.class_group.id),
            term_id=str(version.academic_term.id)
        )

    def perform_update(self, serializer):
        slot = serializer.save()
        self.log_action('TIMETABLE_SLOT_UPDATED', slot, {
            'timetable_version': str(slot.timetable_version.id),
            'day_of_week': slot.day_of_week,
            'period_number': slot.period_number
        })
        # Sync to WhatsApp
        from timetable.tasks import sync_timetable_to_whatsapp_format
        sync_timetable_to_whatsapp_format.delay(
            school_id=str(slot.school.id),
            class_group_id=str(slot.timetable_version.class_group.id),
            term_id=str(slot.timetable_version.academic_term.id)
        )

    def perform_destroy(self, instance):
        self.log_action('TIMETABLE_SLOT_DELETED', instance, {
            'timetable_version': str(instance.timetable_version.id),
            'day_of_week': instance.day_of_week,
            'period_number': instance.period_number
        })
        version = instance.timetable_version
        super().perform_destroy(instance)
        # Sync to WhatsApp
        from timetable.tasks import sync_timetable_to_whatsapp_format
        sync_timetable_to_whatsapp_format.delay(
            school_id=str(version.school.id),
            class_group_id=str(version.class_group.id),
            term_id=str(version.academic_term.id)
        )


class SubstitutionRecordViewSet(AuditMixin, viewsets.ModelViewSet):
    queryset = SubstitutionRecord.objects.none()
    """Manage substitution records."""
    serializer_class = SubstitutionRecordSerializer
    permission_classes = [IsAuthenticated, IsSchoolStaff, IsSameSchool]

    def get_queryset(self):
        return SubstitutionRecord.objects.filter(school=self.request.user.school).select_related(
            'timetable_slot', 'original_teacher', 'substitute_teacher'
        )

    def perform_create(self, serializer):
        slot = serializer.validated_data['timetable_slot']
        if slot.school != self.request.user.school:
            raise ValidationError('Invalid slot school.')
        
        # Use service to create and log
        sub = TimetableService.create_substitution(
            slot=slot,
            date=serializer.validated_data['date'],
            substitute_teacher=serializer.validated_data['substitute_teacher'],
            reason=serializer.validated_data['reason'],
            created_by=self.request.user
        )
        serializer.instance = sub
