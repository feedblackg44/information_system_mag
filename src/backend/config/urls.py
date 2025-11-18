from django.contrib import admin
from django.urls import path
from crm.admin_views.sales_analytics import sales_analytics_view


urlpatterns = [
    path("analytics/sales/", sales_analytics_view, name="sales_analytics"),
    path('', admin.site.urls),
]
