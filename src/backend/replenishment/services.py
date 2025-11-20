import math
from decimal import Decimal

from crm.models import Inventory, Product, ProductPriceLevel
from django.db import transaction

from .models import ForecastData, ReplenishmentItem, ReplenishmentReport


def create_replenishment_report(user, warehouse, coverage_days, credit_terms):
    report = ReplenishmentReport.objects.create(
        user=user,
        warehouse=warehouse,
        global_coverage_days=coverage_days,
        global_credit_terms=credit_terms,
        status=ReplenishmentReport.Status.DRAFT,
    )

    # 1. Оптимізація запитів (JOIN брендів)
    products = Product.objects.select_related('brand').all()

    # 2. Завантаження даних в пам'ять (Batch loading)
    inventory_map = dict(
        Inventory.objects.filter(warehouse=warehouse).values_list(
            "product_id", "quantity"
        )
    )
    ads_map = dict(ForecastData.objects.values_list("product_id", "ads"))

    # Завантажуємо ВСІ рівні цін для логіки вибору
    # Dict: {product_id: [(qty, price), (qty, price)...]}
    price_levels_map = {}
    all_levels = ProductPriceLevel.objects.all().order_by(
        "product_id", "minimal_quantity"
    )
    for pl in all_levels:
        if pl.product_id not in price_levels_map:  # type: ignore
            price_levels_map[pl.product_id] = []  # type: ignore
        price_levels_map[pl.product_id].append((pl.minimal_quantity, pl.price))  # type: ignore

    items_to_create = []

    for product in products:
        current_stock = inventory_map.get(product.id, Decimal(0))  # type: ignore
        ads = ads_map.get(product.id, Decimal(0))  # type: ignore

        # --- Логіка розрахунку потреби ---
        needed_qty = float(ads) * coverage_days
        suggested_raw = math.ceil(needed_qty - float(current_stock))
        system_suggested = max(0, suggested_raw)

        # --- Підбір ціни під обсяг замовлення ---
        # Шукаємо ціну, яка відповідає system_suggested
        # Якщо system_suggested = 0, беремо базову (найменший min_qty)
        levels = price_levels_map.get(product.id, [])  # type: ignore

        chosen_price = Decimal(0)
        chosen_min_qty = 1

        if levels:
            # Сортуємо: від найбільшої кількості до найменшої
            # Щоб знайти першу, яка менша або дорівнює нашому замовленню
            levels.sort(key=lambda x: x[0], reverse=True)

            target_qty = system_suggested if system_suggested > 0 else 1

            found = False
            for min_qty, price in levels:
                if target_qty >= min_qty:
                    chosen_price = price
                    chosen_min_qty = min_qty
                    found = True
                    break

            # Якщо замовлення занадто мале навіть для першого рівня, беремо найменший рівень
            if not found and levels:
                chosen_min_qty, chosen_price = levels[
                    -1
                ]  # Останній елемент (бо reverse=True) це найменший min_qty

        item = ReplenishmentItem(
            report=report,
            product=product,
            warehouse=warehouse,
            # Snapshots (Для красивої таблиці)
            brand_name=product.brand.name,
            product_sku=product.sku,
            product_name=product.name,
            inventory=current_stock,
            average_daily_sales=ads,
            sale_price=product.sale_price,
            purchase_price=chosen_price,
            pricelevel_minimum_quantity=chosen_min_qty,
            system_coverage_days=coverage_days,
            credit_terms=credit_terms,
            system_suggested_quantity=system_suggested,
            best_quantity=system_suggested,
        )
        items_to_create.append(item)

    with transaction.atomic():
        ReplenishmentItem.objects.bulk_create(items_to_create, batch_size=500)

    return report
