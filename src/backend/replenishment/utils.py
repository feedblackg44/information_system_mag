import pickle
from collections import defaultdict
from datetime import date
from decimal import Decimal

import django_rq
import pandas as pd
import redis
from config.settings import REDIS_HOST, REDIS_PORT
from django.contrib.auth import get_user_model
from django.db.models import Sum
from django.db.models.functions import TruncDate
from erp.models import Document, DocumentItem
from prophet import Prophet

from .models import ForecastData, TaskNotification
from .notifications.sender import send_notification_to_user
from .optimization.beautify import beautify
from .optimization.from_matlab.GetAllDealVariants import GetAllDealVariants
from .optimization.map_to_table import map_to_table
from .optimization.prepare_file import main as prepare_file
from .optimization.solver import optimize_efficiency


def execute_initial_optimization_pass(json_table, max_investment_period):
    sorted_data = prepare_file(json_table)

    order, *_ = beautify(sorted_data, max_investment_period)

    deals_variants_all = {idx: GetAllDealVariants(deal) for idx, deal in order.items()}

    min_budget = 0
    max_budget = 0
    for deal_variants in deals_variants_all.values():
        first_deal = deal_variants[0]
        min_budget += first_deal['budget']
        last_deal = deal_variants[-1]
        max_budget += last_deal['budget']
    
    deals_variants_json = pickle.dumps(deals_variants_all)
        
    return Decimal(min_budget), Decimal(max_budget), deals_variants_json


def execute_final_optimization_pass(deals_variants_all, budget, max_investment_period):
    optimal_solution = optimize_efficiency(deals_variants_all, budget)
    
    if optimal_solution is None:
        return None
    
    correct_variant = optimal_solution['selection']
    efficiency = optimal_solution['total_efficiency']
    
    order_keys = list(deals_variants_all.keys())
    correct_order = {}
    for gp_variant in correct_variant:
        group_idx = gp_variant['group']
        variant_idx = gp_variant['variant']
        deal_key = order_keys[group_idx]
        correct_order[deal_key] = deals_variants_all[deal_key][variant_idx]['deal']

    table_out, *_ = map_to_table(correct_order, efficiency, max_investment_period)
    
    return table_out[['Item No', 'Best suggested quantity']].to_dict(orient='records')


def run_prophet_forecast_logic(start_date, end_date):
    """
    Запускає Prophet для всіх товарів і оновлює таблицю ForecastData.
    """
    
    qs = DocumentItem.objects.filter(
        document__doc_type=Document.DocType.SALE,
        document__status=Document.Status.POSTED,
        document__doc_date__date__range=(start_date, end_date)
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

    data_by_product: defaultdict[int, dict] = defaultdict(lambda: {'name': '', 'data': []})
    for entry in qs:
        pid = entry['product_id']
        data_by_product[pid]['name'] = entry['product__name']
        data_by_product[pid]['data'].append({'ds': entry['date'], 'y': float(entry['y'])})

    updated_count = 0
    
    for product_id, data in data_by_product.items():
        df = pd.DataFrame(data['data'])
        df['ds'] = pd.to_datetime(df['ds'])

        df = df.sort_values('ds')

        actual_start_date = df['ds'].min()
        actual_end_date = df['ds'].max()

        full_range = pd.date_range(start=actual_start_date, end=actual_end_date, freq='D')

        df = df.set_index('ds').reindex(full_range, fill_value=0).rename_axis('ds').reset_index()

        df['y'] = pd.to_numeric(df['y'])

        if len(df) < 15 or df['y'].sum() == 0:
            continue
            
        m = Prophet(weekly_seasonality='auto', daily_seasonality=False)  # type: ignore
        m.add_seasonality(name='payday_monthly', period=30.5, fourier_order=10, prior_scale=15.0)

        try:
            m.fit(df)
            
            future = m.make_future_dataframe(periods=30)
            forecast = m.predict(future)
            
            forecast_period = forecast[forecast['ds'] > df['ds'].max()].copy()
            
            if len(forecast_period) == 0:
                 ads_value = 0
            else:
                 forecast_period['yhat'] = forecast_period['yhat'].clip(lower=0)
                 total_predicted = forecast_period['yhat'].sum()
                 ads_value = total_predicted / len(forecast_period)

            ads_decimal = Decimal(ads_value).quantize(Decimal('.01'))
            
            ForecastData.objects.update_or_create(
                product_id=product_id,
                defaults={'ads': ads_decimal}
            )
            updated_count += 1
            
        except Exception as e:
            print(f"Error forecasting product {product_id}: {e}")
            
            if not ForecastData.objects.filter(product_id=product_id).exists():
                ForecastData.objects.create(
                    product_id=product_id,
                    ads=Decimal('0.00')
                )
            
            continue

    return updated_count, "Прогноз успішно завершено."


redis_client = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=0)

@django_rq.job('default', timeout=3600) 
def run_prophet_forecast_task(start_date_str, end_date_str, user_id):
    start_date = date.fromisoformat(start_date_str)
    end_date = date.fromisoformat(end_date_str)
    
    updated_count, message = run_prophet_forecast_logic(start_date, end_date) 
    
    try:
        User = get_user_model()
        user = User.objects.get(pk=user_id)
        
        TaskNotification.objects.create(
            user=user,
            message=f"Прогноз виконано для {updated_count} товарів. {message}",
            message_type='success' if updated_count > 0 else 'warning',
            is_read=False
        )
        
        send_notification_to_user(
            user_id,
            f"Прогноз виконано для {updated_count} товарів. {message}"
            # "success" if updated_count > 0 else "warning"  # type: ignore
        )
    except Exception as e:
        print(f"❌ Failed to create TaskNotification for user {user_id}: {e}")
    
    return updated_count, message


def run_prophet_forecast_service(start_date, end_date, user_id):
    """Обгортка, що запускає завдання в черзі."""
    job = run_prophet_forecast_task.delay(start_date.isoformat(), end_date.isoformat(), user_id)
    return job
