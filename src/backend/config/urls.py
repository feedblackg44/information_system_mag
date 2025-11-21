from crm.admin_views.sales_analytics import sales_analytics_view
from django.contrib import admin
from django.http import JsonResponse
from django.urls import path
from replenishment.models import TaskNotification


def get_notifications_view(request):
    if not request.user.is_authenticated:
        return JsonResponse({'notifications': []})

    notes = TaskNotification.objects.filter(user=request.user, is_read=False)
    
    data = []
    for note in notes:
        data.append({
            'message': note.message,
            'type': note.message_type
        })
    
    notes.update(is_read=True)
    
    return JsonResponse({'notifications': data})

urlpatterns = [
    path('api/check-notifications/', get_notifications_view, name='global_check_notifications'),
    path("analytics/sales/", sales_analytics_view, name="sales_analytics"),
    path('', admin.site.urls),
]
