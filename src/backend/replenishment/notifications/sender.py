from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync


def send_notification_to_user(user_id: int, text: str) -> None:
    channel_layer = get_channel_layer()
    group_name = f"user_{user_id}_notifications"
    async_to_sync(channel_layer.group_send)(  # type: ignore
        group_name,
        {
            "type": "notify",
            "message": text,
        }
    )
