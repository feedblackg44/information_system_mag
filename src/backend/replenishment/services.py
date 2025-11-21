import math
from collections import defaultdict
from decimal import Decimal

from crm.models import Document, DocumentItem, Inventory, Product, ProductPriceLevel
from django.db import transaction
from django.db.models import F, Sum
from django.utils import timezone

from .models import ForecastData, ReplenishmentItem, ReplenishmentReport


def recalculate_report_pricing(report: ReplenishmentReport):
    """
    Перераховує ціну закупівлі та рівень знижки для всіх товарів у звіті, 
    виходячи з їхнього нового загального обсягу (best_quantity) по бренду.
    """
    
    # 1. АГРЕГАЦІЯ: Отримуємо загальну кількість best_quantity за брендом
    brand_totals = report.items.values(  # type: ignore
        'product__brand__id'
    ).annotate(
        total_brand_qty=Sum(F('best_quantity'))
    )
    
    brand_qty_map = {item['product__brand__id']: item['total_brand_qty'] for item in brand_totals}
    
    items_to_update = []
    
    # 2. ПЕРЕРАХУНОК ЦІНИ ТА ОНОВЛЕННЯ РЯДКІВ
    for item in report.items.all().select_related('product', 'product__brand'):  # type: ignore
        brand_id = item.product.brand_id
        # Використовуємо 0 як безпечний дефолт
        total_qty_for_price = brand_qty_map.get(brand_id, 0)
        
        # 2.1. Знаходимо новий рівень ціни
        best_price_level = ProductPriceLevel.objects.filter(
            product=item.product,
            minimal_quantity__lte=total_qty_for_price
        ).order_by('-minimal_quantity').first()

        if best_price_level:
            new_purchase_price = best_price_level.price
            new_min_qty_price = best_price_level.minimal_quantity
        else:
            # Fallback: Беремо найменший поріг (якщо обсяг недостатній)
            min_level = ProductPriceLevel.objects.filter(product=item.product).order_by('minimal_quantity').first()
            new_purchase_price = min_level.price if min_level else Decimal(0)
            new_min_qty_price = min_level.minimal_quantity if min_level else 1
            
        # 2.2. Оновлення об'єкта
        if item.purchase_price != new_purchase_price:
            item.purchase_price = new_purchase_price
            item.pricelevel_minimum_quantity = new_min_qty_price
            items_to_update.append(item)
            
    # 3. Виконання пакетного оновлення
    if items_to_update:
        ReplenishmentItem.objects.bulk_update(items_to_update, ['purchase_price', 'pricelevel_minimum_quantity'])


def update_replenishment_items_with_optimization(report, optimized_results: list):
    """
    Оновлює ReplenishmentItem.best_quantity на основі результатів оптимізації (SKU -> Qty).
    """
    
    # Створюємо словник для швидкого пошуку: {SKU: QTY}
    # Значення з оптимізатора зазвичай можуть бути float/int/Decimal, тому приводимо до int
    sku_to_qty_map = {
        item['Item No']: int(item['Best suggested quantity']) 
        for item in optimized_results
    }
    
    # Отримуємо всі рядки звіту, які потрібно оновити
    items_to_update = list(report.items.all())
    
    updated_items = []
    
    for item in items_to_update:
        sku = item.product_sku # Використовуємо знімок SKU для зіставлення
        new_qty = sku_to_qty_map.get(sku)
        
        if new_qty is not None:
            # Оновлюємо об'єкт лише якщо кількість змінилася
            if item.best_quantity != new_qty:
                item.best_quantity = new_qty
                updated_items.append(item)
                
    # Виконуємо пакетне оновлення
    if updated_items:
        ReplenishmentItem.objects.bulk_update(updated_items, ['best_quantity'])
        
        recalculate_report_pricing(report)
        
    return len(updated_items)


def create_replenishment_report(user, warehouse, coverage_days, credit_terms):
    """
    Створює звіт, розраховуючи ціни закупівлі на основі СУМАРНОГО обсягу бренду.
    """
    
    # 1. Створюємо "Шапку" звіту
    report = ReplenishmentReport.objects.create(
        user=user,
        warehouse=warehouse,
        global_coverage_days=coverage_days,
        global_credit_terms=credit_terms,
        status=ReplenishmentReport.Status.DRAFT
    )

    # Отримуємо всі необхідні дані в оптимізований словник
    products_qs = Product.objects.select_related('brand').all()
    inventory_map = dict(Inventory.objects.filter(warehouse=warehouse).values_list('product_id', 'quantity'))
    ads_map = dict(ForecastData.objects.values_list('product_id', 'ads'))
    
    # Словник для зберігання даних про товари, готових до фінального запису
    final_item_data = {}
    
    # Словник для підрахунку загальної потреби бренду
    brand_total_suggested = defaultdict(Decimal)

    # --- ЕТАП 1: Розрахунок індивідуальної потреби та суми бренду ---
    
    for product in products_qs:
        current_stock = inventory_map.get(product.id, Decimal(0))  # type: ignore
        ads = ads_map.get(product.id, Decimal(0))  # type: ignore
        
        # Розрахунок потреби (системою)
        needed_qty_float = float(ads) * coverage_days
        suggested_raw = math.ceil(needed_qty_float - float(current_stock))
        system_suggested = max(0, suggested_raw)

        # Зберігаємо проміжні дані
        final_item_data[product.id] = {  # type: ignore
            'product': product,
            'current_stock': current_stock,
            'ads': ads,
            'system_suggested': Decimal(system_suggested),
            'brand_id': product.brand_id,  # type: ignore
        }
        
        # Сумуємо за брендом
        brand_total_suggested[product.brand_id] += Decimal(system_suggested)  # type: ignore


    # --- ЕТАП 2: Визначення ціни закупівлі на основі СУМИ БРЕНДУ ---
    
    items_to_create = []
    
    for product_id, data in final_item_data.items():
        brand_id = data['brand_id']
        total_brand_qty = brand_total_suggested[brand_id]
        product = data['product']
        
        # Знаходимо найкращий рівень ціни для даної СУМИ БРЕНДУ
        try:
            # 1. Шукаємо найбільшу мінімальну кількість, меншу або рівну загальній кількості бренду
            best_price_level = ProductPriceLevel.objects.filter(
                product=product,
                minimal_quantity__lte=total_brand_qty
            ).order_by('-minimal_quantity').first()

            # 2. Якщо рівень знайдено, використовуємо його. Інакше беремо найменшу базову ціну (або 0)
            if best_price_level:
                purchase_price = best_price_level.price
                min_qty_price = best_price_level.minimal_quantity
            else:
                # Беремо найнижчий поріг, якщо наш обсяг менший за мінімальний
                min_level = ProductPriceLevel.objects.filter(product=product).order_by('minimal_quantity').first()
                purchase_price = min_level.price if min_level else Decimal(0)
                min_qty_price = min_level.minimal_quantity if min_level else 1
                
        except Exception:
            purchase_price = Decimal(0)
            min_qty_price = 1

        # --- ЕТАП 3: Створення об'єкта ReplenishmentItem ---
        
        system_suggested = data['system_suggested']
        
        item = ReplenishmentItem(
            report=report,
            product=product,
            warehouse=warehouse,
            
            # Snapshots
            brand_name=product.brand.name,
            product_sku=product.sku,
            product_name=product.name,
            inventory=data['current_stock'],
            average_daily_sales=data['ads'],
            sale_price=product.sale_price,
            
            purchase_price=purchase_price,
            pricelevel_minimum_quantity=min_qty_price,
            
            # Inputs
            system_coverage_days=coverage_days,
            credit_terms=credit_terms,
            
            # Outputs
            system_suggested_quantity=system_suggested,
            best_quantity=system_suggested
        )
        items_to_create.append(item)

    # 4. Масове збереження в БД
    with transaction.atomic():
        ReplenishmentItem.objects.bulk_create(items_to_create, batch_size=500)

    return report


def create_purchase_document(report: ReplenishmentReport):
    """
    Створює документ Приходу (PURCHASE) на основі фінального рішення
    в ReplenishmentReport.
    """
    
    # 1. Перевірка статусу (щоб не створювати документ двічі)
    if report.status == ReplenishmentReport.Status.ORDER_CREATED:
        raise Exception(f"Замовлення для звіту №{report.id} вже сформовано.")  # type: ignore

    # 2. Фільтруємо позиції з кількістю > 0
    items_to_order = report.items.filter(best_quantity__gt=0).select_related('product')  # type: ignore
    
    if not items_to_order.exists():
        raise Exception("У звіті відсутні товари з кількістю до замовлення > 0.")

    # Використовуємо транзакцію для забезпечення цілісності
    with transaction.atomic():
        # 3. Створення шапки документа (Document)
        new_doc = Document.objects.create(
            doc_type=Document.DocType.PURCHASE,
            status=Document.Status.DRAFT,
            doc_date=timezone.now(),
            # PURCHASE використовує лише склад призначення (dst_warehouse)
            dst_warehouse=report.warehouse, 
            note=f"Сформовано автоматично на основі Звіту поповнення №{report.id}"  # type: ignore
        )
        
        doc_items_to_create = []
        
        # 4. Створення рядків документа (DocumentItem)
        for item in items_to_order:
            # Важливо: використовуємо дані з ReplenishmentItem,
            # оскільки вони містять фінальні ціни закупівлі, розраховані алгоритмом!
            
            # Django ORM вимагає Decimal, тому конвертуємо
            quantity = Decimal(item.best_quantity) 
            
            # Створюємо DocumentItem
            doc_items_to_create.append(
                DocumentItem(
                    document=new_doc,
                    product=item.product,
                    quantity=quantity,
                    # Використовуємо ціну за одиницю з нашого звіту, 
                    # помножену на кількість, як загальну суму рядка.
                    # Поле price в DocumentItem має бути заповнене ціною закупівлі.
                    # ВАЖЛИВО: Ми повинні заповнити price ТІЛЬКИ загальною сумою рядка,
                    # оскільки Document.recalc_prices() розрахує його з нуля.
                    # АЛЕ: Якщо ми хочемо використати нашу ціну (item.purchase_price),
                    # ми повинні передати її правильно.
                    
                    # Простіше: покласти загальну суму.
                    price=item.purchase_price * quantity # Загальна вартість рядка
                )
            )

        # 5. Масове створення рядків документа
        DocumentItem.objects.bulk_create(doc_items_to_create)
        
        # 6. Оновлення шапки звіту про поповнення (встановлення статусу)
        report.status = ReplenishmentReport.Status.ORDER_CREATED
        report.save()
        
        # 7. Перерахунок цін у новому документі (це обов'язково, 
        # оскільки логіка recalc_prices може залежати від суми DocumentItem)
        # new_doc.recalc_prices() # Цей метод викликається після збереження рядків

        return new_doc
