from collections import defaultdict
from decimal import Decimal

import pandas as pd
from crm.models import Document, DocumentItem
from django.db.models import Sum
from django.db.models.functions import TruncDate
from prophet import Prophet

from .models import ForecastData


def run_prophet_forecast_service(start_date, end_date):
    """
    ⚠️ УВАГА: Це синхронний запуск. В реальному додатку має бути Celery/RQ!
    Запускає Prophet для всіх товарів і оновлює таблицю ForecastData.
    """
    
    # 1. Отримання та агрегація даних
    qs = DocumentItem.objects.filter(
        document__doc_type=Document.DocType.SALE,
        document__status=Document.Status.POSTED,
        document__doc_date__date__range=(start_date, end_date) # Фільтр по датах
    ).annotate(
        date=TruncDate('document__doc_date')
    ).values(
        'product_id', 
        'product__name', 
        'date'
    ).annotate(
        y=Sum('quantity')
    ).order_by('product_id', 'date')

    if not qs.exists():
        return 0, "Не знайдено проведених продажів у заданому діапазоні."

    # Групування в DataFrame
    data_by_product: defaultdict[int, dict] = defaultdict(lambda: {'name': '', 'data': []})
    for entry in qs:
        pid = entry['product_id']
        data_by_product[pid]['name'] = entry['product__name']
        data_by_product[pid]['data'].append({'ds': entry['date'], 'y': float(entry['y'])})

    # 2. Цикл прогнозування
    updated_count = 0
    
    for product_id, data in data_by_product.items():
        df = pd.DataFrame(data['data'])
        df['ds'] = pd.to_datetime(df['ds'])
        
        # --- КРОК 2.1: ЗАПОВНЕННЯ НУЛЯМИ І ОБРІЗКА ---
        
        # Створюємо повний діапазон дат для заповнення нулями
        date_range = pd.date_range(start=start_date, end=end_date, freq='D')
        df = df.set_index('ds').reindex(date_range, fill_value=0).rename_axis('ds').reset_index()
        
        # Prophet вимагає числових значень.
        df['y'] = pd.to_numeric(df['y'])

        # Знаходимо першу (start_idx) та останню (end_idx) ненульову точку
        nonzero_indices = df[df['y'] > 0].index
        
        if len(nonzero_indices) == 0:
            # Продажів в діапазоні не було (можливо, були, але не в цей період)
            continue
            
        first_sale_index = nonzero_indices.min()
        last_sale_index = nonzero_indices.max()
        
        # Обрізаємо DataFrame, залишаючи історію від першого до останнього продажу
        # + додаємо невеликий буфер, якщо потрібно
        df = df.iloc[first_sale_index : last_sale_index + 1].copy()

        # --- КРОК 2.2: ПЕРЕВІРКА ---
        
        # Продовжуємо, тільки якщо є достатньо даних для навчання (наприклад, 15 днів)
        if len(df) < 15 or df['y'].sum() == 0:
            continue
            
        # --- 3. Налаштування та навчання Prophet ---
        
        # Використовуємо 'auto' для тиші Pylance
        m = Prophet(weekly_seasonality='auto', daily_seasonality=False)  # type: ignore
        m.add_seasonality(name='payday_monthly', period=30.5, fourier_order=10, prior_scale=15.0)

        m.fit(df)
        
        # 4. Прогноз ADS (Прогнозуємо на 30 днів вперед для розрахунку середнього)
        future = m.make_future_dataframe(periods=30)
        forecast = m.predict(future)
        
        # Беремо тільки прогнозний період
        forecast_period = forecast[forecast['ds'] > df['ds'].max()]
        
        # Прогноз може бути не 30 днів, якщо останній день історії дуже близький до сьогодні
        if len(forecast_period) == 0:
             # Якщо прогноз не охоплює 30 днів вперед (наприклад, якщо end_date сьогодні)
             # Ми можемо взяти прогнозоване ADS за min_periods днів
             ads_value = 0 # Прогноз не вдалий
        else:
             total_predicted = forecast_period['yhat'].sum()
             ads_value = total_predicted / len(forecast_period) # ADS = Сума прогнозу / Кількість днів

        
        # 5. Оновлення таблиці ForecastData
        ads_decimal = Decimal(ads_value).quantize(Decimal('.01'))
        
        ForecastData.objects.update_or_create(
            product_id=product_id,
            defaults={'ads': ads_decimal}
        )
        updated_count += 1

    return updated_count, "Прогноз успішно завершено."
