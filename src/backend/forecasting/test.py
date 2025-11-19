import os
import sys
from collections import defaultdict

import django
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
import pandas as pd
from django.db.models import Sum
from django.db.models.functions import TruncDate
from prophet import Prophet

# ------------------------------------------------------------------------
# 1. НАСТРОЙКА ОКРУЖЕНИЯ DJANGO
# ------------------------------------------------------------------------

# Получаем путь к папке forecasting
current_dir = os.path.dirname(os.path.abspath(__file__))
# Получаем путь к папке backend (где лежит manage.py)
project_root = os.path.dirname(current_dir)

# ВАЖНО: Вставляем путь в НАЧАЛО списка, чтобы Python искал здесь в первую очередь
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# --- ДИАГНОСТИКА (если снова упадет) ---
# Проверяем, как называется папка с settings.py рядом с manage.py
# Обычно это 'backend', 'config', 'core' или 'diplom_system'
# Посмотрите в проводнике, какая папка лежит рядом с manage.py и содержит settings.py
settings_folder_name = 'config'  # <--- ИЗМЕНИТЕ ЭТО, ЕСЛИ ПАПКА НАЗЫВАЕТСЯ ИНАЧЕ

os.environ.setdefault('DJANGO_SETTINGS_MODULE', f'{settings_folder_name}.settings')

try:
    django.setup()
    print(f"✅ Django успешно настроен! (Settings: {settings_folder_name}.settings)")
except ModuleNotFoundError as e:  # noqa: F841
    print(f"\n❌ ОШИБКА: Не найден модуль настроек '{settings_folder_name}.settings'.")
    print(f"   Python ищет папку '{settings_folder_name}' внутри: {project_root}")
    print("   Пожалуйста, проверьте имя папки, лежащей рядом с manage.py, и измените переменную settings_folder_name в скрипте.\n")
    sys.exit(1)

# Импортируем модели ПОСЛЕ настройки Django
from crm.models import Document, DocumentItem  # noqa: E402

# ------------------------------------------------------------------------
# 2. ФУНКЦИИ ПОДГОТОВКИ ДАННЫХ
# ------------------------------------------------------------------------

def fetch_sales_data_from_db():
    """
    Извлекает агрегированные по дням продажи из Django ORM.
    Возвращает словарь: {product_id: DataFrame(ds, y, product_name)}
    """
    print("📡 Получение данных из БД...")

    # Фильтруем только Проведенные Продажи
    # Используем TruncDate, чтобы отбросить время и группировать строго по датам
    qs = DocumentItem.objects.filter(
        document__doc_type=Document.DocType.SALE,
        document__status=Document.Status.POSTED
    ).annotate(
        date=TruncDate('document__doc_date')
    ).values(
        'product_id', 
        'product__name', 
        'date'
    ).annotate(
        y=Sum('quantity')
    ).order_by('date')

    if not qs.exists():
        print("⚠️ В базе данных нет проведенных продаж.")
        return {}

    # Группируем результаты запроса по товарам
    data_by_product = defaultdict(list)
    for entry in qs:
        data_by_product[entry['product_id']].append({
            'ds': entry['date'],
            'y': float(entry['y']),
            'product_name': entry['product__name']
        })

    # Превращаем списки в Pandas DataFrames и заполняем пропуски (дни без продаж)
    ready_dfs = {}
    for pid, records in data_by_product.items():
        df = pd.DataFrame(records)
        df['ds'] = pd.to_datetime(df['ds'])
        
        # Важно: Prophet нужны непрерывные даты. Если продаж не было, ставим 0.
        full_idx = pd.date_range(start=df['ds'].min(), end=df['ds'].max(), freq='D')
        df = df.set_index('ds').reindex(full_idx, fill_value=0).rename_axis('ds').reset_index()
        
        # Восстанавливаем имя и колонку y (после reindex могут быть NaN в данных, если fill_value не сработал на колонки)
        # Но так как мы заполнили 0, нужно вернуть имя
        name = records[0]['product_name']
        df['product_name'] = name
        
        # y могли стать NaN при reindex, если не указать fill_value корректно для всей таблицы, 
        # но выше fill_value=0 заполнил всё. Убедимся:
        df['y'] = df['y'].fillna(0)

        ready_dfs[pid] = df

    return ready_dfs

# ------------------------------------------------------------------------
# 3. ПРОГНОЗИРОВАНИЕ (PROPHET)
# ------------------------------------------------------------------------

def run_forecasting(forecast_days=30):
    products_data = fetch_sales_data_from_db()
    
    if not products_data:
        return

    print(f"\n🚀 Начинаем прогнозирование для {len(products_data)} товаров...\n")
    
    results = []

    for pid, df in products_data.items():
        product_name = df['product_name'].iloc[0]
        
        # Проверка на минимальное количество данных (хотя бы 2 недели)
        if len(df) < 14:
            print(f"⏩ {product_name}: Слишком мало данных ({len(df)} дн). Пропуск.")
            continue

        # --- Настройка Prophet ---
        m = Prophet(
            weekly_seasonality=True,  # type: ignore
            daily_seasonality=False,  # type: ignore
            changepoint_prior_scale=0.05
        )

        # Добавляем кастомную сезонность "Зарплата" (начало и середина месяца)
        m.add_seasonality(
            name='payday_monthly',
            period=30.5,
            fourier_order=10,
            prior_scale=15.0
        )

        try:
            # Обучение
            m.fit(df)
            
            # Предсказание
            future = m.make_future_dataframe(periods=forecast_days)
            forecast = m.predict(future)
            
            # Расчет ADS (Average Daily Sales) только по прогнозному периоду
            future_mask = forecast['ds'] > df['ds'].max()
            forecast_period = forecast[future_mask]
            
            total_forecasted = forecast_period['yhat'].sum()
            ads = total_forecasted / forecast_days
            
            # Сохраняем результат
            results.append({
                'id': pid,
                'name': product_name,
                'ads': max(0, ads), # ADS не может быть отрицательным
                'total_predicted': total_forecasted
            })
            
            print(f"✅ {product_name:<20} | ADS: {ads:.2f}")

            # (Опционально) Показать график для первого товара, чтобы убедиться, что работает
            # if len(results) == 1:
            #     m.plot(forecast)
            #     plt.title(f"Forecast: {product_name}")
            #     plt.show()

        except Exception as e:
            print(f"❌ Ошибка для {product_name}: {e}")

    # ------------------------------------------------------------------------
    # 4. ИТОГОВЫЙ ОТЧЕТ
    # ------------------------------------------------------------------------
    print("\n" + "="*40)
    print(f"ИТОГИ ПРОГНОЗА (Горизонт: {forecast_days} дн.)")
    print("="*40)
    print(f"{'ID':<5} | {'Product Name':<25} | {'ADS':<10}")
    print("-" * 45)
    
    for res in results:
        print(f"{res['id']:<5} | {res['name']:<25} | {res['ads']:.2f}")
    
    print("="*40)

# if __name__ == "__main__":
#     # Запускаем
#     run_forecasting(forecast_days=30)


def analyze_single_product(target_id, forecast_days=30):
    print(f"\n🔍 Анализ товара ID={target_id}...")

    # 1. Точечный запрос в БД
    qs = DocumentItem.objects.filter(
        document__doc_type=Document.DocType.SALE,
        document__status=Document.Status.POSTED,
        product_id=target_id
    ).annotate(
        date=TruncDate('document__doc_date')
    ).values(
        'date', 
        'product__name'
    ).annotate(
        y=Sum('quantity')
    ).order_by('date')

    if not qs.exists():
        print(f"❌ Данных по продажам для товара ID={target_id} не найдено.")
        return

    # 2. Подготовка DataFrame
    data = list(qs)
    product_name = data[0]['product__name']
    
    df = pd.DataFrame(data)
    df = df.rename(columns={'date': 'ds'})
    df['ds'] = pd.to_datetime(df['ds'])
    
    full_idx = pd.date_range(start=df['ds'].min(), end=df['ds'].max(), freq='D')
    df = df.set_index('ds').reindex(full_idx, fill_value=0).rename_axis('ds').reset_index()
    df['y'] = df['y'].fillna(0)

    print(f"   Товар: {product_name}")
    print(f"   История: {len(df)} дней")

    # 3. Настройка и обучение Prophet
    m = Prophet(
        weekly_seasonality=True,  # type: ignore
        daily_seasonality=False,  # type: ignore
        changepoint_prior_scale=0.05
    )
    m.add_seasonality(name='payday_monthly', period=30.5, fourier_order=10, prior_scale=15.0)

    m.fit(df)

    # 4. Прогноз
    future = m.make_future_dataframe(periods=forecast_days)
    forecast = m.predict(future)

    # 5. Расчет ADS
    future_mask = forecast['ds'] > df['ds'].max()
    forecast_period = forecast[future_mask]
    total_predicted = forecast_period['yhat'].sum()
    ads = total_predicted / forecast_days

    print("\n📊 РЕЗУЛЬТАТЫ:")
    print(f"   Прогноз на {forecast_days} дней: {total_predicted:.0f} шт.")
    print(f"   ✅ ADS (Average Daily Sales): {ads:.2f}")

    # 6. Визуализация
    
    # --- ГРАФИК 1: Прогноз ---
    m.plot(forecast)
    
    # [FIX 1] Настройка заголовка, чтобы он не обрезался
    plt.title(f"Прогноз: {product_name} (ADS: {ads:.2f})", fontsize=14, pad=20)
    plt.xlabel("Дата")
    plt.ylabel("Продажи (шт)")
    plt.axvline(x=df['ds'].max(), color='r', linestyle='--', label='Сегодня')
    plt.legend()
    
    # [FIX 1] Автоматическая подгонка отступов
    plt.tight_layout() 

    # --- ГРАФИК 2: Компоненты ---
    fig2 = m.plot_components(forecast)
    
    # [FIX 2] Лечим краш при наведении мыши
    # Проблема в "Weekly" и "Payday" графиках, где Prophet ставит кастомный форматтер.
    # Мы принудительно сбрасываем его на стандартный ScalarFormatter.
    # Подписи осей станут чуть проще (числа вместо названий дней), но краш исчезнет.
    for ax in fig2.axes:
        xaxis = ax.get_xaxis()
        # Если форматтер осей - это FuncFormatter (который вызывает лямбду), сбрасываем его
        if isinstance(xaxis.get_major_formatter(), ticker.FuncFormatter):
            xaxis.set_major_formatter(ticker.ScalarFormatter())
            # Опционально: убрать дробную часть, если это дни недели
            xaxis.set_major_locator(ticker.MaxNLocator(integer=True))

    # [FIX 1] Для второго окна тоже делаем красиво
    plt.tight_layout()
    
    print("   📈 Графики построены. Открываю окна...")
    plt.show()


# --- ЗАПУСК ---
if __name__ == "__main__":
    # Укажи здесь ID нужного товара
    TARGET_PRODUCT_ID = 42 
    
    analyze_single_product(TARGET_PRODUCT_ID, forecast_days=30)
