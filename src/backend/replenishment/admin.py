import math
import statistics
from collections import defaultdict
from decimal import Decimal

from django.contrib import admin
from django.db.models import DecimalField, F, Sum
from django.db.models.functions import Coalesce
from django.urls import path, reverse
from django.utils.html import format_html

from .admin_views.budget_input import budget_input_view
from .admin_views.create_order import create_order_view
from .admin_views.generate_report import generate_view
from .admin_views.process_report import export_report_excel_view, process_report_view
from .admin_views.run_forecast import run_forecast_view
from .models import (
    ForecastData,
    ReplenishmentItem,
    ReplenishmentReport
)
from .services import recalculate_report_pricing


@admin.register(ForecastData)
class ForecastDataAdmin(admin.ModelAdmin):
    list_display = ('product', 'ads', 'last_updated')
    list_filter = ('last_updated',)
    search_fields = ('product__name', 'product__sku')
    
    change_list_template = "admin/replenishment/replenishment_changelist.html"

    def has_add_permission(self, request):
        return False

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path('run-forecast/', self.admin_site.admin_view(run_forecast_view), name='replenishment_run_forecast')
        ]
        return custom_urls + urls


class ReplenishmentItemInline(admin.TabularInline):
    model = ReplenishmentItem
    extra = 0
    can_delete = False
    
    _variance_cache = {}
    
    fields = (
        'product_info',
        'inventory_info',
        'pricing_matrix',
        'system_suggested_quantity',
        'best_quantity',
        'days_for_sale',
        'days_for_sale_variance',
        'budget',
        'total_sales',
        'total_profit',
        'system_params'
    )
    
    readonly_fields = (
        'product_info', 'inventory_info', 'system_params', 
        'pricing_matrix', 'system_suggested_quantity', 
        'days_for_sale', 'days_for_sale_variance', 'budget', 'total_sales', 'total_profit'
    )

    def calculate_and_cache_stats(self, report_id):
        """Обчислює середнє значення та дисперсію Dfs для кожного бренду в звіті."""
        
        items = ReplenishmentItem.objects.filter(report_id=report_id).select_related('product__brand')

        brand_dfs_map = defaultdict(list)
        
        for item in items:
            ads = item.average_daily_sales or Decimal(0)
            inventory = item.inventory or Decimal(0)
            best_qty = item.best_quantity or 0

            if ads > 0:
                dfs = (inventory + Decimal(best_qty)) / ads
                brand_dfs_map[item.product.brand.id].append(float(dfs))  # type: ignore
        
        variance_results = {}
        for brand_id, dfs_list in brand_dfs_map.items():
            if len(dfs_list) >= 2:
                variance = statistics.variance(dfs_list)
                stdev = math.sqrt(variance) 
                
                variance_results[brand_id] = {
                    'avg': statistics.mean(dfs_list),
                    'stdev': stdev,
                    'count': len(dfs_list),
                }
        ReplenishmentItemInline._variance_cache = variance_results

    def get_queryset(self, request):
        ReplenishmentItemInline._variance_cache = {}
        
        qs = super().get_queryset(request)
        return qs.prefetch_related('product__productpricelevel_set')

    def product_info(self, obj):
        return format_html(
            "<b>{}</b><br>"
            "<span style='color: #666;'>{}</span><br>"
            "{}",
            obj.brand_name, obj.product_sku, obj.product_name
        )
    product_info.short_description = "Товар"

    def inventory_info(self, obj):
        return format_html(
            "Stock: <b>{}</b><br>"
            "ADS: <b>{}</b>",
            obj.inventory, obj.average_daily_sales
        )
    inventory_info.short_description = "Склад / Попит"

    def pricing_matrix(self, obj):
        levels = list(obj.product.productpricelevel_set.all().order_by('minimal_quantity'))
        if not levels:
            return "Без знижок"

        s_price = obj.sale_price or Decimal(0)
        p_price = obj.purchase_price or Decimal(0)

        html = "<div style='margin: 0; padding: 0; line-height: 1;'>"
        html += "<table style='width:100%; font-size: 11px; border-collapse: collapse; text-align: right; margin: 0; padding: 0;'>"
        
        html += "<tr style='border-bottom: 1px solid #ddd; background: #f9f9f9;'>"
        html += "<th style='text-align: left; padding: 2px 5px;'>Qty</th>"
        html += "<th style='padding: 2px 5px;'>Buy</th>"
        html += "<th style='padding: 2px 5px;'>Sell</th>"
        html += "<th style='padding: 2px 5px;'>Profit</th>"
        html += "</tr>"
        
        for lvl in levels:
            lvl_price = lvl.price or Decimal(0)
            profit = s_price - lvl_price
            profit_style = "color: green;" if profit > 0 else "color: red;"
            
            is_active = ""
            if lvl_price == p_price and p_price > 0:
                 is_active = "background-color: #d4edda; font-weight: bold;"

            html += f"<tr style='border-bottom: 1px solid #eee; {is_active}'>"
            html += f"<td style='text-align: left; padding: 2px 5px;'>{lvl.minimal_quantity}+</td>"
            html += f"<td style='padding: 2px 5px;'>{lvl_price}</td>"
            html += f"<td style='padding: 2px 5px;'>{s_price}</td>"
            html += f"<td style='padding: 2px 5px; {profit_style}'>{profit}</td>"
            html += "</tr>"
        
        html += "</table></div>"
        
        return format_html(html)
    
    pricing_matrix.short_description = "Обраний рівень знижки"
    
    def days_for_sale(self, obj):
        ads = obj.average_daily_sales or Decimal(0)
        inventory = obj.inventory or Decimal(0)
        best_qty = obj.best_quantity or 0
        
        if ads > 0:
            days = (inventory + Decimal(best_qty)) / ads
            if not self._variance_cache:
                self.calculate_and_cache_stats(obj.report_id)
            return format_html(f"<span>{days:.1f} днів</span>")
        return "N/A"
    
    def days_for_sale_variance(self, obj):
        """Відображає стандартне відхилення (σ) запасів по бренду."""
        if not self._variance_cache:
            self.calculate_and_cache_stats(obj.report_id)

        brand_id = obj.product.brand.id
        stats = self._variance_cache.get(brand_id)

        if stats and stats['count'] >= 2:
            return f"{stats['stdev']:.1f} дн."
        return "N/A"
        
    days_for_sale_variance.short_description = "Відхилення (σ)"
    
    def budget(self, obj):
        qty = obj.best_quantity or 0
        price = obj.purchase_price or Decimal(0)
        return f"{(qty * price):.2f}"
    
    budget.short_description = "Бюджет"

    def total_sales(self, obj):
        qty = obj.best_quantity or 0
        price = obj.sale_price or Decimal(0)
        return f"{(qty * price):.2f}"
    
    total_sales.short_description = "Продажі"

    def total_profit(self, obj):
        sell = obj.sale_price if obj.sale_price is not None else Decimal(0)
        buy = obj.purchase_price if obj.purchase_price is not None else Decimal(0)
        qty = obj.best_quantity or 0

        profit_per_unit = sell - buy
        total = Decimal(qty) * profit_per_unit
        
        total_profit_str = f"{total:.2f}" 

        if total > 0:
            style = "color: green; font-weight: bold;"
        elif total < 0:
            style = "color: red; font-weight: bold;"
        else:
            style = "color: #999;"

        return format_html(
            "<span style='{}'>{}</span>",
            style,
            total_profit_str
        )

    total_profit.short_description = "Прибуток"
    
    def system_params(self, obj):
        return format_html(
            "Cover: {} d<br>Credit: {} d",
            obj.system_coverage_days, obj.credit_terms
        )
    system_params.short_description = "Умови"


@admin.register(ReplenishmentReport)
class ReplenishmentReportAdmin(admin.ModelAdmin):
    list_display = ('id', 'created_at', 'user', 'warehouse', 'status', 
                    'total_budget_display', 'total_profit_display', 'view_items_link')
    list_filter = ('status', 'warehouse', 'created_at')
    readonly_fields = ('user', 'warehouse', 'status', 'total_budget_calculation', 'total_profit_calculation', 
                       'created_at', 'run_algorithm_button', 'create_order_button')
    
    exclude = (
        'min_budget',
        'max_budget',
        'max_investment_period',
        'deals_variants_json',
    )
    
    change_list_template = "admin/replenishment/report_changelist.html"
    
    inlines = [ReplenishmentItemInline]

    def total_budget_calculation(self, obj):
        """Розраховує загальний бюджет закупівлі для всього звіту."""
        
        total_budget = obj.items.aggregate(
            sum_budget=Sum(
                Coalesce(F('best_quantity'), 0) * Coalesce(F('purchase_price'), 0),
                output_field=DecimalField() 
            )
        )['sum_budget']
        
        if total_budget is None:
            return format_html("<b style='color: #E67E22;'>Не розраховано</b>")
        
        return format_html("<b>{}</b>", f"{total_budget:,.2f} у.о.")
    
    total_budget_calculation.short_description = "Загальний бюджет закупки"
    
    def total_budget_display(self, obj):
        """Відображає бюджет у списку звітів."""
        return self.total_budget_calculation(obj)
    total_budget_display.short_description = "Бюджет"
    
    def total_profit_calculation(self, obj):
        """Розраховує загальний прибуток для всього звіту."""
        
        total_profit = obj.items.aggregate(
            sum_profit=Sum(
                (Coalesce(F('sale_price'), 0) - Coalesce(F('purchase_price'), 0)) * Coalesce(F('best_quantity'), 0),
                output_field=DecimalField()
            )
        )['sum_profit']
        
        if total_profit is None:
            return format_html("<b style='color: #E67E22;'>Не розраховано</b>")
        
        style = "color: green; font-weight: bold;" if total_profit > 0 else "color: red; font-weight: bold;" if total_profit < 0 else "color: #999;"
        
        return format_html(
            "<b style='{}'>{}</b>",
            style,
            f"{total_profit:,.2f} у.о."
        )
    
    def total_profit_display(self, obj):
        """Відображає прибуток у списку звітів."""
        return self.total_profit_calculation(obj)
    total_profit_display.short_description = "Прибуток"
    
    def view_items_link(self, obj):
        count = obj.items.count()
        return f"{count} позицій"
    view_items_link.short_description = "Товари"
    
    def run_algorithm_button(self, obj):
        url = reverse('admin:replenishment_report_process', args=[obj.pk])
        
        if obj.status == ReplenishmentReport.Status.ORDER_CREATED:
            return format_html(
                '<span style="color: #999;">💰 Оптимізація недоступна, оскільки документ замовлення вже створено</span>'
            )
        
        return format_html(
            '<a class="btn btn-primary" href="{}">{}</a>',
            url,
            '💰 Запустити алгоритм'
        )
        
    run_algorithm_button.short_description = "Оптимізація замовлення"
    
    def create_order_button(self, obj):
        """Відображає кнопку для створення документа замовлення на основі звіту."""
        create_order_url = reverse('admin:replenishment_create_order', args=[obj.pk])
        
        if obj.status == ReplenishmentReport.Status.ORDER_CREATED:
            return format_html(
                '<span style="color: green; font-weight: bold;">🛒 Документ замовлення створено</span>'
            )
        
        return format_html(
            '<a class="btn btn-success" href="{}">{}</a>',
            create_order_url,
            '🛒 Створити документ замовлення'
        )
    create_order_button.short_description = "Створення замовлення"
    
    def has_change_permission(self, request, obj=None):
        """
        Забороняє редагування, якщо звіт знаходиться у статусі ORDER_CREATED.
        """
        if obj and obj.status == obj.Status.ORDER_CREATED:
            return False
        
        return super().has_change_permission(request, obj)
    
    def has_add_permission(self, request):
        return False
    
    def save_formset(self, request, form, formset, change):
        super().save_formset(request, form, formset, change)
        
        if formset.model == ReplenishmentItem:
            recalculate_report_pricing(form.instance)
    
    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path('<int:object_id>/process/', self.admin_site.admin_view(process_report_view), name='replenishment_report_process'),
            path('<int:object_id>/excel/', self.admin_site.admin_view(export_report_excel_view), name='replenishment_report_excel'),
            path('<int:object_id>/budget-input/', self.admin_site.admin_view(budget_input_view), name='replenishment_report_budget_input'),
            path('<int:object_id>/create-order/', self.admin_site.admin_view(create_order_view), name='replenishment_create_order'),
            path('generate/', self.admin_site.admin_view(generate_view), name='replenishment_generate'),
        ]
        return custom_urls + urls
