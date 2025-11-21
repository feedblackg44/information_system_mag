import pickle

from django.contrib import admin, messages
from django.contrib.admin.views.decorators import staff_member_required
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from replenishment.forms import FinalBudgetForm
from replenishment.models import ReplenishmentReport
from replenishment.services import update_replenishment_items_with_optimization
from replenishment.utils import execute_final_optimization_pass


@staff_member_required
def budget_input_view(request, object_id):
    report = get_object_or_404(ReplenishmentReport, pk=object_id)
    
    # 1. Перевірка, чи були розраховані межі
    if report.max_budget <= 0:
        messages.error(request, "Бюджетні межі не були розраховані. Потрібно спочатку завершити попередній етап.")
        return redirect(reverse('admin:replenishment_report_process', args=[report.pk]))
    # 2. Обробка POST-запиту для фінального бюджету
    if request.method == 'POST':
        form = FinalBudgetForm(request.POST)
        
        if form.is_valid():
            final_budget = form.cleaned_data['final_budget']
            
            # Встановлюємо динамічну валідацію, щоб показати помилку користувачеві
            if not (report.min_budget <= final_budget):
                 # Перевірка діапазону (включно з верхньою межею)
                 messages.error(request, f"Бюджет {final_budget:,.0f} у.о. менший за мінімально допустимий {report.min_budget:,.0f} у.о.")
            else:
                try:
                    # ⚠️ ФІНАЛЬНИЙ АЛГОРИТМ: ДЕСЕРІАЛІЗАЦІЯ ТА ВИКЛИК ⚠️
                    
                    # 1. Десеріалізація об'єкта deals_variants_all
                    deals_variants_all = pickle.loads(report.deals_variants_json)  # type: ignore

                    # 2. Виклик фінальної оптимізації
                    optimized_results = execute_final_optimization_pass(
                        deals_variants_all, 
                        final_budget, 
                        report.max_investment_period
                    )
                    
                    if optimized_results is None:
                        messages.error(request, "Алгоритм не зміг знайти оптимальне рішення в рамках заданого бюджету.")
                        # Залишаємося на цій же сторінці
                        return redirect(reverse('admin:replenishment_report_budget_input', args=[report.pk]))

                    # 3. Оновлення БД та фіналізація
                    updated_count = update_replenishment_items_with_optimization(report, optimized_results)
                    
                    messages.success(request, f"Оптимізація успішно завершена! Оновлено {updated_count} позицій. Фінальний бюджет: {final_budget:,.0f} у.о.")
                    
                    # 4. Редірект на сторінку звіту
                    return redirect(reverse('admin:replenishment_replenishmentreport_change', args=[report.pk]))
                
                except Exception as e:
                    messages.error(request, f"Виникла критична помилка під час виконання алгоритму: {e}")
                    # Можливо, повернення до попереднього етапу для перезапуску
                    return redirect(reverse('admin:replenishment_report_process', args=[report.pk]))
    else:
        # GET-запит: ініціалізація форми з підказками
        form = FinalBudgetForm()
    # 3. Налаштування контексту
    context = admin.site.each_context(request)
    context.update({
        'title': f"Фіналізація бюджету Звіту №{report.id}",  # type: ignore
        'report': report,
        'min_budget': f"{report.min_budget:,.0f}",
        'max_budget': f"{report.max_budget:,.0f}",
        'form': form
    })
    
    return render(request, 'admin/replenishment/budget_input_form.html', context)