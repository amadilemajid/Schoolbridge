"""Structured Timetable Backend — Serializers."""
from rest_framework import serializers
from timetable.models import TimetableVersion, TimetableSlot, SubstitutionRecord


class TimetableSlotSerializer(serializers.ModelSerializer):
    subject_display = serializers.CharField(
        source='display_subject', read_only=True
    )
    teacher_name = serializers.SerializerMethodField()
    day_name = serializers.CharField(
        source='get_day_of_week_display', read_only=True
    )

    class Meta:
        model = TimetableSlot
        fields = [
            'id', 'timetable_version', 'day_of_week', 'day_name', 'period_number',
            'start_time', 'end_time', 'subject', 'subject_name',
            'subject_display', 'teacher', 'teacher_name', 'room',
            'slot_type',
        ]

    def get_teacher_name(self, obj) -> str | None:
        return obj.teacher.get_full_name() if obj.teacher else None

    def validate(self, attrs):
        request = self.context.get('request')
        if not (request and request.user):
            return attrs
            
        school = request.user.school
        
        # Get values (falling back to instance for updates)
        version = attrs.get('timetable_version', getattr(self.instance, 'timetable_version', None))
        subject = attrs.get('subject', getattr(self.instance, 'subject', None))
        teacher = attrs.get('teacher', getattr(self.instance, 'teacher', None))
        start_time = attrs.get('start_time', getattr(self.instance, 'start_time', None))
        end_time = attrs.get('end_time', getattr(self.instance, 'end_time', None))
        day_of_week = attrs.get('day_of_week', getattr(self.instance, 'day_of_week', None))
        
        # 1. Tenant validations
        if version and version.school != school:
            raise serializers.ValidationError({'timetable_version': 'Invalid timetable version.'})
        if subject and subject.school != school:
            raise serializers.ValidationError({'subject': 'Invalid subject.'})
        if teacher and teacher.school != school:
            raise serializers.ValidationError({'teacher': 'Invalid teacher.'})
            
        # 2. Time validations
        if start_time and end_time and start_time >= end_time:
            raise serializers.ValidationError({'end_time': 'End time must be after start time.'})
            
        # 3. Check overlaps in the same timetable version
        if version and day_of_week is not None and start_time and end_time:
            overlapping_slots = TimetableSlot.all_objects.filter(
                timetable_version=version,
                day_of_week=day_of_week,
            ).filter(
                start_time__lt=end_time,
                end_time__gt=start_time
            )
            if self.instance:
                overlapping_slots = overlapping_slots.exclude(pk=self.instance.pk)
                
            if overlapping_slots.exists():
                raise serializers.ValidationError('This slot overlaps with another slot in the same timetable version.')
                
        return attrs


class TimetableVersionSerializer(serializers.ModelSerializer):
    slots = TimetableSlotSerializer(many=True, read_only=True)
    class_group_name = serializers.CharField(
        source='class_group.name', read_only=True
    )
    term_name = serializers.CharField(
        source='academic_term.name', read_only=True
    )

    class Meta:
        model = TimetableVersion
        fields = [
            'id', 'class_group', 'class_group_name', 'academic_term',
            'term_name', 'version_number', 'is_active', 'effective_from',
            'notes', 'created_by', 'created_at', 'slots',
        ]
        read_only_fields = ['created_at', 'created_by']


class TimetableVersionCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = TimetableVersion
        fields = [
            'id', 'class_group', 'academic_term', 'version_number',
            'is_active', 'effective_from', 'notes',
        ]
        read_only_fields = ['id']

    def validate(self, attrs):
        request = self.context.get('request')
        if request and request.user:
            school = request.user.school
            class_group = attrs.get('class_group')
            if class_group and class_group.school != school:
                raise serializers.ValidationError({'class_group': 'Invalid class group.'})
            term = attrs.get('academic_term')
            if term and term.school != school:
                raise serializers.ValidationError({'academic_term': 'Invalid academic term.'})
        return attrs


class SubstitutionRecordSerializer(serializers.ModelSerializer):
    original_teacher_name = serializers.SerializerMethodField()
    substitute_teacher_name = serializers.SerializerMethodField()

    class Meta:
        model = SubstitutionRecord
        fields = [
            'id', 'timetable_slot', 'date',
            'original_teacher', 'original_teacher_name',
            'substitute_teacher', 'substitute_teacher_name',
            'reason', 'created_by', 'created_at',
        ]
        read_only_fields = ['created_at', 'created_by', 'original_teacher']

    def get_original_teacher_name(self, obj) -> str | None:
        return (
            obj.original_teacher.get_full_name()
            if obj.original_teacher else None
        )

    def get_substitute_teacher_name(self, obj) -> str | None:
        return (
            obj.substitute_teacher.get_full_name()
            if obj.substitute_teacher else None
        )

    def validate(self, attrs):
        request = self.context.get('request')
        if not (request and request.user):
            return attrs
            
        school = request.user.school
        slot = attrs.get('timetable_slot', getattr(self.instance, 'timetable_slot', None))
        substitute = attrs.get('substitute_teacher', getattr(self.instance, 'substitute_teacher', None))
        
        if slot and slot.school != school:
            raise serializers.ValidationError({'timetable_slot': 'Invalid timetable slot.'})
        if substitute and substitute.school != school:
            raise serializers.ValidationError({'substitute_teacher': 'Invalid substitute teacher.'})
            
        return attrs

