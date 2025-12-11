import math
from collections import defaultdict
from decimal import Decimal

from erp.models import Document, DocumentItem, Inventory, Product, ProductPriceLevel
from django.db import transaction
from django.db.models import F, Sum
from django.utils import timezone

from .models import ForecastData, ReplenishmentItem, ReplenishmentReport


def recalculate_report_pricing(report: ReplenishmentReport):
    """
    Перераховує ціну закупівлі та рівень знижки для всіх товарів у звіті, 
    виходячи з їхнього нового загального обсягу (best_quantity) по бренду.
    """

    brand_totals = report.items.values(  # type: ignore
        'product__brand__id'
    ).annotate(
        total_brand_qty=Sum(F('best_quantity'))
    )
    
    brand_qty_map = {item['product__brand__id']: item['total_brand_qty'] for item in brand_totals}
    
    items_to_update = []
    
    for item in report.items.all().select_related('product', 'product__brand'):  # type: ignore
        brand_id = item.product.brand_id
        total_qty_for_price = brand_qty_map.get(brand_id, 0)
        
        best_price_level = ProductPriceLevel.objects.filter(
            product=item.product,
            minimal_quantity__lte=total_qty_for_price
        ).order_by('-minimal_quantity').first()

        if best_price_level:
            new_purchase_price = best_price_level.price
            new_min_qty_price = best_price_level.minimal_quantity
        else:
            min_level = ProductPriceLevel.objects.filter(product=item.product).order_by('minimal_quantity').first()
            new_purchase_price = min_level.price if min_level else Decimal(0)
            new_min_qty_price = min_level.minimal_quantity if min_level else 1

        if item.purchase_price != new_purchase_price:
            item.purchase_price = new_purchase_price
            item.pricelevel_minimum_quantity = new_min_qty_price
            items_to_update.append(item)
    
    if items_to_update:
        ReplenishmentItem.objects.bulk_update(items_to_update, ['purchase_price', 'pricelevel_minimum_quantity'])


def update_replenishment_items_with_optimization(report, optimized_results: list):
    """
    Оновлює ReplenishmentItem.best_quantity на основі результатів оптимізації (SKU -> Qty).
    """
    
    sku_to_qty_map = {
        item['Item No']: int(item['Best suggested quantity']) 
        for item in optimized_results
    }
    
    items_to_update = list(report.items.all())
    
    updated_items = []
    
    for item in items_to_update:
        sku = item.product_sku
        new_qty = sku_to_qty_map.get(sku)
        
        if new_qty is not None:
            if item.best_quantity != new_qty:
                item.best_quantity = new_qty
                updated_items.append(item)
    
    if updated_items:
        ReplenishmentItem.objects.bulk_update(updated_items, ['best_quantity'])
        
        recalculate_report_pricing(report)
        
    return len(updated_items)


def create_replenishment_report(user, warehouse, coverage_days, credit_terms):
    """
    Створює звіт, розраховуючи ціни закупівлі на основі СУМАРНОГО обсягу бренду.
    """
    
    report = ReplenishmentReport.objects.create(
        user=user,
        warehouse=warehouse,
        global_coverage_days=coverage_days,
        global_credit_terms=credit_terms,
        status=ReplenishmentReport.Status.DRAFT
    )

    products_qs = Product.objects.select_related('brand').all()
    inventory_map = dict(Inventory.objects.filter(warehouse=warehouse).values_list('product_id', 'quantity'))
    ads_map = dict(ForecastData.objects.values_list('product_id', 'ads'))
    
    final_item_data = {}
    
    brand_total_suggested = defaultdict(Decimal)
    
    for product in products_qs:
        current_stock = inventory_map.get(product.id, Decimal(0))  # type: ignore
        ads = ads_map.get(product.id, Decimal(0))  # type: ignore
        
        needed_qty_float = float(ads) * coverage_days
        suggested_raw = math.ceil(needed_qty_float - float(current_stock))
        system_suggested = max(0, suggested_raw)

        final_item_data[product.id] = {  # type: ignore
            'product': product,
            'current_stock': current_stock,
            'ads': ads,
            'system_suggested': Decimal(system_suggested),
            'brand_id': product.brand_id,  # type: ignore
        }
        
        brand_total_suggested[product.brand_id] += Decimal(system_suggested)  # type: ignore

    items_to_create = []
    
    for product_id, data in final_item_data.items():
        brand_id = data['brand_id']
        total_brand_qty = brand_total_suggested[brand_id]
        product = data['product']
        
        try:
            best_price_level = ProductPriceLevel.objects.filter(
                product=product,
                minimal_quantity__lte=total_brand_qty
            ).order_by('-minimal_quantity').first()

            if best_price_level:
                purchase_price = best_price_level.price
                min_qty_price = best_price_level.minimal_quantity
            else:
                min_level = ProductPriceLevel.objects.filter(product=product).order_by('minimal_quantity').first()
                purchase_price = min_level.price if min_level else Decimal(0)
                min_qty_price = min_level.minimal_quantity if min_level else 1
                
        except Exception:
            purchase_price = Decimal(0)
            min_qty_price = 1
        
        system_suggested = data['system_suggested']
        
        item = ReplenishmentItem(
            report=report,
            product=product,
            warehouse=warehouse,
            
            brand_name=product.brand.name,
            product_sku=product.sku,
            product_name=product.name,
            inventory=data['current_stock'],
            average_daily_sales=data['ads'],
            sale_price=product.sale_price,
            
            purchase_price=purchase_price,
            pricelevel_minimum_quantity=min_qty_price,
            
            system_coverage_days=coverage_days,
            credit_terms=credit_terms,

            system_suggested_quantity=system_suggested,
            best_quantity=system_suggested
        )
        items_to_create.append(item)

    with transaction.atomic():
        ReplenishmentItem.objects.bulk_create(items_to_create, batch_size=500)

    return report


def create_purchase_document(report: ReplenishmentReport):
    """
    Створює документ Приходу (PURCHASE) на основі фінального рішення
    в ReplenishmentReport.
    """
    
    if report.status == ReplenishmentReport.Status.ORDER_CREATED:
        raise Exception(f"Замовлення для звіту №{report.id} вже сформовано.")  # type: ignore

    items_to_order = report.items.filter(best_quantity__gt=0).select_related('product')  # type: ignore
    
    if not items_to_order.exists():
        raise Exception("У звіті відсутні товари з кількістю до замовлення > 0.")

    with transaction.atomic():
        new_doc = Document.objects.create(
            doc_type=Document.DocType.PURCHASE,
            status=Document.Status.DRAFT,
            doc_date=timezone.now(),
            dst_warehouse=report.warehouse, 
            note=f"Сформовано автоматично на основі Звіту поповнення №{report.id}"  # type: ignore
        )
        
        doc_items_to_create = []
        
        for item in items_to_order:
            quantity = Decimal(item.best_quantity) 
            
            doc_items_to_create.append(
                DocumentItem(
                    document=new_doc,
                    product=item.product,
                    quantity=quantity,
                    price=item.purchase_price * quantity
                )
            )
        DocumentItem.objects.bulk_create(doc_items_to_create)
        
        report.status = ReplenishmentReport.Status.ORDER_CREATED
        report.save()
        
        new_doc.recalc_prices()

        return new_doc
