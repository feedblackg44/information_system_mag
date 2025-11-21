from decimal import Decimal
from io import BytesIO

import pandas as pd
from django.contrib import admin, messages
from django.contrib.admin.views.decorators import staff_member_required
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from replenishment.forms import AlgorithmInputForm
from replenishment.models import ReplenishmentReport
from replenishment.utils import execute_initial_optimization_pass


def _get_data_for_algorithm(report):
    """
    Збирає дані для експорту, створюючи окремий рядок для кожного рівня знижки 
    та зберігаючи оригінальні назви ключів (Deal ID, Minimum Purchase UoM Quantity, тощо).
    """
    
    # Оптимізація: отримуємо основні рядки звіту та попередньо завантажуємо РІВНІ ЦІН
    items = report.items.all().select_related('product', 'warehouse').prefetch_related(
        'product__productpricelevel_set' 
    )
    
    data_for_algorithm = []
    
    for item in items:
        sale_price = item.sale_price or Decimal(0)
        
        levels = item.product.productpricelevel_set.all()
        
        if not levels:
            raise ValueError(f"Продукт {item.product.name} (SKU: {item.product.sku}) не має визначених рівнів цін.")
        
        for level in levels:
            purchase_price = level.price
            min_qty = level.minimal_quantity
            
            profit = sale_price - purchase_price
            
            data_for_algorithm.append({
                "Deal ID": item.brand_name,
                "Item No": item.product_sku,
                "Item Name": item.product_name,
                "Minimum Purchase UoM Quantity": min_qty,
                "Purchase Price": float(purchase_price),
                "Sale Price": float(sale_price),
                "Profit": float(profit),
                "Average Daily Sales": float(item.average_daily_sales),
                "Inventory": float(item.inventory),
                "System Suggested Quantity": item.system_suggested_quantity,
                "System Coverage Days": item.system_coverage_days,
                "Credit Terms": item.credit_terms
            })
            
    return data_for_algorithm

@staff_member_required
def process_report_view(request, object_id):
    report = get_object_or_404(ReplenishmentReport, pk=object_id)
    
    data_for_algorithm = _get_data_for_algorithm(report)
    header_keys = [key.replace("_", " ").upper() for key in data_for_algorithm[0].keys()] if data_for_algorithm else []

    initial_period = report.max_investment_period if report.max_investment_period > 0 else 45
    initial_data = {'max_investment_period': initial_period}

    if request.method == 'POST':
        # Ми тут обробляємо форму AlgorithmInputForm (з періодом інвестицій)
        form = AlgorithmInputForm(request.POST) 
        
        if form.is_valid():
            max_period = form.cleaned_data['max_investment_period']
            
            # --- ВИКЛИК СКЛАДНОГО РОЗРАХУНКУ МЕЖ БЮДЖЕТУ ---
            
            # 1. Готуємо дані (якщо потрібно)
            data_list = _get_data_for_algorithm(report)
            
            # 2. Викликаємо сервіс (або ставимо в чергу)
            min_b, max_b, deals_json = execute_initial_optimization_pass(data_list, max_period)
            
            # Зберігаємо всі результати у модель
            report.min_budget = min_b
            report.max_budget = max_b
            report.max_investment_period = max_period
            report.deals_variants_json = deals_json
            report.save()
            
            messages.info(request, "Розрахунок бюджетних меж завершено. Виберіть фінальний бюджет.")
            
            # Redirect до нового View для введення бюджету
            return redirect(reverse('admin:replenishment_report_budget_input', args=[report.pk]))
    else:
        form = AlgorithmInputForm(initial=initial_data)
        
    # 3. Налаштування контексту для відображення таблиці
    context = admin.site.each_context(request)
    context.update({
        'title': f"Перевірка вхідних даних для алгоритму Звіту №{report.id}",  # type: ignore
        'report': report,
        'data_list': data_for_algorithm, 
        'header_keys': header_keys,
        'algorithm_form': form,
        'is_popup': False
    })
    
    return render(request, 'admin/replenishment/json_output.html', context)

@staff_member_required
def export_report_excel_view(request, object_id):
    report = get_object_or_404(ReplenishmentReport, pk=object_id)
    
    # 1. Отримання даних
    data_list = _get_data_for_algorithm(report)
    
    if not data_list:
        messages.error(request, "Немає даних для експорту.")
        return redirect(reverse('admin:replenishment_replenishmentreport_change', args=[report.pk]))
    # 2. Генерація Excel у пам'яті (BytesIO)
    df = pd.DataFrame(data_list)
    output = BytesIO()
    
    numeric_cols = [
        "Purchase Price", "Sale Price", "Profit", 
        "Average Daily Sales", "Inventory"
    ]
    for col in numeric_cols:
        df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
    
    # Використовуємо xlsxwriter як швидший двигун
    writer = pd.ExcelWriter(output, engine='xlsxwriter')
    df.to_excel(writer, sheet_name='Replenishment Data', index=False)
    writer.close()
    output.seek(0)
    
    # 3. Формування відповіді HTTP
    filename = f'replenishment_report_{report.pk}_{timezone.now().strftime("%Y%m%d_%H%M")}.xlsx'
    response = HttpResponse(
        output.read(), 
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response