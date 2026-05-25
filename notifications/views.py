"""Notifications REST views — list, mark read, unread count."""
from django.utils import timezone
from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework import serializers as drf_serializers
from rest_framework.permissions import IsAuthenticated
from .models import Notification


class NotificationSerializer(drf_serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = [
            'id', 'notification_type', 'title', 'message',
            'data', 'is_read', 'read_at', 'created_at',
        ]
        read_only_fields = fields


class NotificationListView(generics.ListAPIView):
    """
    US-074: List in-app notifications for the authenticated user.
    Supports ?unread_only=true filter.
    30-second polling fallback: clients poll this endpoint if WS unavailable.
    """
    serializer_class = NotificationSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        qs = Notification.all_objects.filter(recipient=self.request.user)
        unread_only = self.request.query_params.get('unread_only', 'false').lower() == 'true'
        if unread_only:
            qs = qs.filter(is_read=False)
        return qs.order_by('-created_at')[:100]


class NotificationMarkReadView(APIView):
    """Mark a single notification as read."""
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        try:
            n = Notification.all_objects.get(id=pk, recipient=request.user)
            n.mark_read()
            return Response({'message': 'Marked as read.'})
        except Notification.DoesNotExist:
            return Response({'error': 'Not found.'}, status=404)


class NotificationMarkAllReadView(APIView):
    """Mark all notifications as read."""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        Notification.all_objects.filter(
            recipient=request.user, is_read=False
        ).update(is_read=True, read_at=timezone.now())
        return Response({'message': 'All notifications marked as read.'})


class NotificationUnreadCountView(APIView):
    """
    US-074: Quick unread count for badge display.
    Polled every 30s as fallback when WebSocket unavailable.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        count = Notification.all_objects.filter(
            recipient=request.user, is_read=False
        ).count()
        return Response({'unread_count': count})
