from rest_framework import serializers
from .models import AuditLog


class AuditLogSerializer(serializers.ModelSerializer):
    user = serializers.CharField(source='actor_email', read_only=True)
    model = serializers.CharField(source='target_model', read_only=True)
    object_id = serializers.CharField(source='target_id', read_only=True)
    timestamp = serializers.DateTimeField(source='created_at', read_only=True)

    class Meta:
        model = AuditLog
        fields = [
            'id', 'actor_email', 'actor_role', 'category', 'action',
            'description', 'target_model', 'target_id',
            'before_data', 'after_data', 'extra_data',
            'ip_address', 'created_at',
            'user', 'model', 'object_id', 'timestamp',
        ]
        read_only_fields = fields
