from django.contrib import admin, messages
from django.shortcuts import redirect, render
from django.urls import reverse

from replenishment.forms import GenerateReplenishmentForm
from replenishment.services import create_replenishment_report

def generate_view(request):
    if request.method == 'POST':
        form = GenerateReplenishmentForm(request.POST)
        if form.is_valid():
            try:
                report = create_replenishment_report(
                    user=request.user,
                    warehouse=form.cleaned_data['warehouse'],
                    coverage_days=form.cleaned_data['global_coverage_days'],
                    credit_terms=form.cleaned_data['global_credit_terms']
                )
                messages.success(request, f"Звіт №{report.id} успішно сформовано ({report.items.count()} товарів)")  # type: ignore
                
                return redirect(reverse('admin:replenishment_replenishmentreport_change', args=[report.id]))  # type: ignore
            except Exception as e:
                messages.error(request, f"Помилка генерації: {e}")
    else:
        form = GenerateReplenishmentForm()
    
    context = {
        **admin.site.each_context(request),
        'form': form,
        'title': "Генерація звіту поповнення",
        'subtitle': "Оберіть параметри для розрахунку потреби",
    }
    return render(request, 'admin/replenishment/generate_form.html', context)
