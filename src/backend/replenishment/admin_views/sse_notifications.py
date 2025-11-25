import redis
from config.settings import REDIS_HOST, REDIS_PORT
from django.contrib.auth.decorators import login_required
from django.http import StreamingHttpResponse

redis_client = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=0)

@login_required
def sse_notifications_view(request):
    """Генератор подій Server-Sent Events"""
    
    def event_stream():
        pubsub = redis_client.pubsub()
        channel_name = f"notifications_{request.user.id}"
        pubsub.subscribe(channel_name)
        
        for message in pubsub.listen():
            if message['type'] == 'message':
                yield f"data: {message['data'].decode('utf-8')}\n\n"

    response = StreamingHttpResponse(event_stream(), content_type='text/event-stream')  # type: ignore
    response['X-Accel-Buffering'] = 'no'
    response['Cache-Control'] = 'no-cache'
    return response