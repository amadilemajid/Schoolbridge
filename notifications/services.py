"""
Notification service layer.
Central place to create in-app notifications and push them via WebSocket.
US-074: Real-time delivery via Django Channels.
US-073: Admin/infrastructure alerts.
"""
import logging
from django.utils import timezone

logger = logging.getLogger('schoolbridge')


class NotificationService:
    """Create and deliver in-app notifications to staff."""

    @classmethod
    def notify_user(cls, *, user, message, notification_type, title=None, data=None, school=None):
        """
        Create a Notification for a specific user and push via WebSocket.
        Falls back gracefully if Channels is not available.
        """
        from notifications.models import Notification
        school = school or getattr(user, 'school', None)
        if title is None:
            title = notification_type.replace('_', ' ').title()

        notification = Notification.all_objects.create(
            school=school,
            recipient=user,
            notification_type=notification_type,
            title=title,
            message=message,
            data=data,
        )

        # Push via WebSocket (US-074)
        cls._push_websocket(user, notification)
        return notification

    @classmethod
    def notify_role(cls, *, school, role, message, notification_type,
                    title=None, data=None):
        """
        Send a notification to all active staff members of a given role in a school.
        US-074: Each recipient gets a WebSocket push.
        """
        from authentication.models import User
        recipients = User.objects.filter(
            school=school, role=role, is_active=True
        )
        notifications = []
        for user in recipients:
            n = cls.notify_user(
                user=user,
                message=message,
                notification_type=notification_type,
                title=title,
                data=data,
                school=school,
            )
            notifications.append(n)
        return notifications

    @classmethod
    def _push_websocket(cls, user, notification):
        """
        US-074: Push notification data to user's WebSocket channel group.
        Group name: 'notifications_{user_id}'
        Falls back silently if Channels not configured.
        """
        try:
            from channels.layers import get_channel_layer
            from asgiref.sync import async_to_sync
            channel_layer = get_channel_layer()
            if channel_layer is None:
                return
            group_name = f"notifications_{user.id}"
            async_to_sync(channel_layer.group_send)(
                group_name,
                {
                    'type': 'notification.message',
                    'notification': {
                        'id': str(notification.id),
                        'type': notification.notification_type,
                        'title': notification.title,
                        'message': notification.message,
                        'data': notification.data,
                        'created_at': notification.created_at.isoformat(),
                        'is_read': False,
                    },
                }
            )
        except Exception as e:
            # Never let WebSocket errors break the main flow
            logger.warning(f"WebSocket push failed for user {user.id}: {e}")


def send_admin_alert(*, alert_type, message, payload=None):
    """
    US-073: Send a system-level alert to all system admins.
    Used for: webhook failures, DB backup failures, cert expiry,
              Celery queue overflow, dead-letter queue entries.
    """
    from authentication.models import User
    from notifications.models import Notification

    system_admins = User.objects.filter(role='system_admin', is_active=True)
    for admin in system_admins:
        Notification.all_objects.create(
            school=None,
            recipient=admin,
            notification_type='SYSTEM_ALERT',
            title=f"System Alert: {alert_type}",
            message=message,
            data=payload,
        )
        logger.error(f"SYSTEM_ALERT | {alert_type} | {message}")
