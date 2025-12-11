import json

from channels.generic.websocket import AsyncWebsocketConsumer


class NotificationsConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        user = self.scope["user"]  # type: ignore
        if user.is_anonymous:  # type: ignore
            await self.close()
            return

        self.group_name = f"user_{user.id}_notifications"  # type: ignore

        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        if hasattr(self, "group_name"):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def receive(self, text_data=None, bytes_data=None):
        pass

    async def notify(self, event):
        """
        Этот метод будет вызываться, когда мы сделаем group_send.
        """
        message = event.get("message")
        await self.send(text_data=json.dumps({"message": message}))
