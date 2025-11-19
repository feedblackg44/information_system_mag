from django.contrib import admin, messages
from django.contrib.admin.views.decorators import staff_member_required
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.translation import gettext_lazy
from replenishment.forms import ForecastDateRangeForm
from replenishment.utils import run_prophet_forecast_service


@staff_member_required
def run_forecast_view(request):
    if request.method == 'POST':
        form = ForecastDateRangeForm(request.POST)
        if form.is_valid():
            start_date = form.cleaned_data['start_date']
            end_date = form.cleaned_data['end_date']
            
            # --- ⚠️ Синхронний виклик ---
            updated_count, message = run_prophet_forecast_service(start_date, end_date)
            
            if updated_count > 0:
                messages.success(request, gettext_lazy(f"Прогноз успішно виконано для {updated_count} товарів. {message}"))
            else:
                messages.warning(request, gettext_lazy(message))
            
            return redirect(reverse('admin:replenishment_run_forecast'))
    else:
        form = ForecastDateRangeForm()
    
    context = admin.site.each_context(request)
    
    context.update({
        'form': form,
        'title': "Запуск прогнозу ADS",
        'subtitle': "Виберіть діапазон даних для навчання моделі Prophet та оновлення таблиці ForecastData.",
    })
    
    return render(request, 'admin/replenishment/forecast_form.html', context)
    