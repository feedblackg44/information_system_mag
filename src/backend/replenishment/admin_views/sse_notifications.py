import asyncio

from config.settings import REDIS_HOST, REDIS_PORT
from django.contrib.auth.decorators import login_required
from django.http import StreamingHttpResponse
from redis.asyncio import Redis

redis_client = Redis(host=REDIS_HOST, port=REDIS_PORT, db=0)

async def async_event_stream(user_id):
    pubsub = redis_client.pubsub()
    channel_name = f"notifications_{user_id}"
    await pubsub.subscribe(channel_name)

    try:
        while True:
            message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
            if message:
                yield f"data: {message['data'].decode('utf-8')}\n\n"
            await asyncio.sleep(0.1)  # allow other tasks to run
    finally:
        await pubsub.unsubscribe(channel_name)
        await pubsub.close()

@login_required
def sse_notifications_view(request):
    user_id = request.user.id

    async def stream():
        async for data in async_event_stream(user_id):
            yield data

    response = StreamingHttpResponse(stream(), content_type='text/event-stream')  # type: ignore
    response['X-Accel-Buffering'] = 'no'
    response['Cache-Control'] = 'no-cache'
    return response
