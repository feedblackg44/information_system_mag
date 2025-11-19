from crm.admin_views.sales_analytics import sales_analytics_view
from django.contrib import admin
from django.urls import path

urlpatterns = [
    path("analytics/sales/", sales_analytics_view, name="sales_analytics"),
    path('', admin.site.urls),
]
