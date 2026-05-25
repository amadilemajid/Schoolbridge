from rest_framework import serializers
from .models import AuditLog


class AuditLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = AuditLog
        fields = [
            'id', 'actor_email', 'actor_role', 'category', 'action',
            'description', 'target_model', 'target_id',
            'before_data', 'after_data', 'extra_data',
            'ip_address', 'created_at',
        ]
        read_only_fields = fields
