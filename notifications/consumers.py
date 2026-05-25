"""
Django Channels WebSocket consumer.
US-074: Real-time in-app notifications. Authenticated staff only.
30-second polling fallback handled on the frontend when WS unavailable.
"""
import json
import logging
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async

logger = logging.getLogger('schoolbridge')


class NotificationConsumer(AsyncWebsocketConsumer):
    """
    WebSocket consumer for in-app notifications.
    Connection URL: /ws/notifications/
    Auth: JWT token passed as query param ?token=<access_token>
    Group: notifications_{user_id}
    """

    async def connect(self):
        # Authenticate via JWT token in query string
        user = await self._authenticate()
        if user is None:
            await self.close(code=4001)
            return

        self.user = user
        self.group_name = f"notifications_{user.id}"

        # Join user's notification group
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

        # Send unread notification count on connect
        unread_count = await self._get_unread_count()
        await self.send(text_data=json.dumps({
            'type': 'connection_established',
            'unread_count': unread_count,
        }))
        logger.info(f"WebSocket connected: user={user.id} group={self.group_name}")

    async def disconnect(self, close_code):
        if hasattr(self, 'group_name'):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)
            logger.info(f"WebSocket disconnected: group={self.group_name} code={close_code}")

    async def receive(self, text_data):
        """Handle messages from client (e.g. mark-read requests)."""
        try:
            data = json.loads(text_data)
            action = data.get('action')
            if action == 'mark_read':
                notification_id = data.get('notification_id')
                if notification_id:
                    await self._mark_notification_read(notification_id)
            elif action == 'mark_all_read':
                await self._mark_all_read()
        except json.JSONDecodeError:
            pass

    async def notification_message(self, event):
        """Receive from channel layer and forward to WebSocket client."""
        await self.send(text_data=json.dumps({
            'type': 'new_notification',
            'notification': event['notification'],
        }))

    @database_sync_to_async
    def _authenticate(self):
        """Validate JWT token from WebSocket query string."""
        from urllib.parse import parse_qs
        query_string = self.scope.get('query_string', b'').decode()
        params = parse_qs(query_string)
        token_list = params.get('token', [])
        if not token_list:
            return None
        token = token_list[0]
        try:
            from rest_framework_simplejwt.tokens import AccessToken
            from authentication.models import User
            access_token = AccessToken(token)
            user_id = access_token.payload.get('user_id')
            return User.objects.get(id=user_id, is_active=True)
        except Exception:
            return None

    @database_sync_to_async
    def _get_unread_count(self):
        from notifications.models import Notification
        return Notification.all_objects.filter(
            recipient=self.user, is_read=False
        ).count()

    @database_sync_to_async
    def _mark_notification_read(self, notification_id):
        from notifications.models import Notification
        try:
            n = Notification.all_objects.get(id=notification_id, recipient=self.user)
            n.mark_read()
        except Notification.DoesNotExist:
            pass

    @database_sync_to_async
    def _mark_all_read(self):
        from notifications.models import Notification
        from django.utils import timezone
        Notification.all_objects.filter(
            recipient=self.user, is_read=False
        ).update(is_read=True, read_at=timezone.now())
