from django.contrib import admin, messages
from django.contrib.admin.views.decorators import staff_member_required
from django.shortcuts import redirect, render
from django.urls import reverse
from replenishment.forms import ForecastDateRangeForm
from replenishment.utils import run_prophet_forecast_service


@staff_member_required
def run_forecast_view(request):
    if request.method == 'POST':
        form = ForecastDateRangeForm(request.POST)
        if form.is_valid():
            start_date = form.cleaned_data['start_date']
            end_date = form.cleaned_data['end_date']
            
            # --- 🚀 АСИНХРОННИЙ ВИКЛИК ---
            # Передаємо user_id
            job = run_prophet_forecast_service(start_date, end_date, request.user.id)
            
            # Зберігаємо ID завдання в сесії
            request.session['forecast_job_id'] = job.id  # type: ignore
            
            # Повідомлення про запуск
            messages.info(request, "Прогнозування запущено у фоновому режимі. Очікуйте завершення.")
            
            # PRG-патерн
            return redirect(reverse('admin:replenishment_run_forecast'))
    
    # 3. Ініціалізація форми (якщо job_id був видалений, форма буде чистою)
    form = ForecastDateRangeForm()
    
    context = admin.site.each_context(request)
    context.update({
        'form': form,
        'title': "Запуск прогнозу ADS",
        'subtitle': "Виберіть діапазон даних..."
    })
    
    return render(request, 'admin/replenishment/forecast_form.html', context)