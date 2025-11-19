from django.contrib import admin
from django.urls import path

from .models import ForecastData
from .admin_views.run_forecast import run_forecast_view


# @admin.register(ReplenishmentReport)
# class ReplenishmentReportAdmin(admin.ModelAdmin):
#     list_display = ('id', 'user', 'warehouse', 'created_at', 'status', 'global_coverage_days')
#     list_filter = ('status', 'warehouse')


@admin.register(ForecastData)
class ForecastDataAdmin(admin.ModelAdmin):
    list_display = ('product', 'ads', 'last_updated')
    list_filter = ('last_updated',)
    search_fields = ('product__name', 'product__sku')
    
    change_list_template = "admin/replenishment/replenishment_changelist.html"

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path('run-forecast/', self.admin_site.admin_view(run_forecast_view), name='replenishment_run_forecast'),
        ]
        return custom_urls + urls
