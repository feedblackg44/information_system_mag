import random
from dateutil.relativedelta import relativedelta
from decimal import Decimal

from crm.models import (
    Brand,
    Document,
    DocumentItem,
    Inventory,
    Product,
    ProductPriceLevel,
    Warehouse,
)
from django.utils.timezone import now


def generate_random_name():
    parts = [
        'Pro', 'Max', 'Tech', 'Data', 'Net', 'Core', 'Flex', 'Ultra', 'Nano', 'Smart',
        'Alpha', 'Mega', 'Mini', 'Hyper', 'Super', 'Micro', 'Eco', 'Power', 'Speed',
        'Multi', 'True', 'Fast', 'Quick', 'Easy', 'Gold', 'Silver', 'Platinum',
        'Diamond', 'Titan', 'Titanium', 'Quantum', 'Solar', 'Lunar', 'Aero', 'Cyber',
        'Neo', 'Opti', 'Velo', 'Zen', 'Pulse', 'Nexus', 'Vertex', 'Fusion', 'Matrix',
        'Vector', 'Prime', 'Evo', 'Nova', 'Spectra', 'Vortex', 'Strato', 'Aqua',
        'Terra', 'Luxe', 'Elite', 'Penta', 'Hexa', 'Octa', 'Alpha', 'Beta', 'Gamma'
    ]
    suffix = [
        'drive', 'wave', 'ware', 'link', 'byte', 'deck', 'box', 'sphere', 'grid',
        'works', 'port', 'scan', 'motion', 'frame', 'track', 'line', 'point', 'hub',
        'zone', 'core', 'net', 'tech', 'soft', 'data', 'cloud', 'logic', 'pulse',
        'flux', 'shift', 'spark', 'glide', 'rise', 'flow', 'boost', 'quest',
        'forge', 'craft', 'blend', 'sync', 'wave', 'beam', 'flare', 'storm', 'trail'
    ]
    return random.choice(parts) + random.choice(suffix)


def generate_brands(count):
    brands = []
    for _ in range(count):
        b = Brand.objects.create(
            name=generate_random_name(),
            country=random.choice(["USA", "Germany", "China", "Japan", "France"])
        )
        brands.append(b)
    return brands


def generate_products(brands, max_products_per_brand=5, max_price_levels=5):
    products = []

    for brand in brands:
        products_count = random.randint(1, max_products_per_brand)

        for _ in range(products_count):

            name = generate_random_name()

            product = Product.objects.create(
                name=name,
                sku=name.upper()[:10] + str(random.randint(100, 999)),
                brand=brand,
                sale_price=0
            )

            min_purchase_price = generate_price_levels(product, max_price_levels)

            sale_price = round(random.uniform(
                min_purchase_price * 1.05,
                min_purchase_price * 1.3
            ), 2)

            product.sale_price = sale_price  # type: ignore
            product.save()

            products.append(product)

    return products



def generate_price_levels(product, max_levels):
    """
    Generates random price levels for a product.
    Returns the minimum purchase price.
    """
    moq = {1: round(random.uniform(5, 100), 2)}

    extra_levels = random.randint(1, max_levels - 1)

    additional_quantities = sorted(
        random.sample(range(2, 100), k=extra_levels)
    )

    last_price = moq[1]
    min_purchase_price = last_price

    for idx, q in enumerate(additional_quantities):
        new_price = round(last_price - random.uniform(0.5, 1.5), 2)

        if new_price < 1:
            new_price = round(last_price - 0.1, 2)

        moq[q] = new_price
        last_price = new_price
        min_purchase_price = new_price

    for q, price in sorted(moq.items()):
        ProductPriceLevel.objects.create(
            product=product,
            minimal_quantity=q,
            price=price
        )

    return min_purchase_price


def generate_initial_stock(warehouse_name, total_days: int, 
                           target_date=None,
                           func_to_show=None):
    """
    Creates a purchase document to initialize stock levels for all products.
    Each product will receive a quantity based on a random average daily sales (ADS)
    """

    try:
        warehouse = Warehouse.objects.get(name=warehouse_name)
    except Warehouse.DoesNotExist:
        raise ValueError(f"Warehouse '{warehouse_name}' does not exist.")

    if func_to_show:
        func_to_show(f"Using warehouse: {warehouse.name}")

    doc = Document.objects.create(
        doc_type=Document.DocType.PURCHASE,
        status=Document.Status.DRAFT,
        dst_warehouse=warehouse,
        doc_date=target_date if target_date else now(),
        note="Початкове завантаження складу",
    )

    len_products = Product.objects.count()
    for idx, product in enumerate(Product.objects.all(), start=1):
        if func_to_show:
            func_to_show(f"Processing product {idx}/{len_products}.", end="\r")
        
        ads = random.uniform(0.01, 10.0)

        qty_raw = ads * total_days * random.uniform(0.9, 1.2)
        qty = int(max(1, round(qty_raw)))

        DocumentItem.objects.create(
            document=doc,
            product=product,
            quantity=Decimal(qty),
            price=Decimal("0")
        )

    if func_to_show:
        func_to_show("")
    
    doc.post()

    return doc


def simulate_sales(
    total_days: int,
    min_remain=0.0,
    max_remain=0.1,
    warehouse_name="Main Warehouse",
    func_to_show=None
):
    """
    Realistic & imperfect sales simulation:
    - Some items go to zero
    - Some keep 1–5%
    - Some keep 5–10%
    - Some keep even more
    """

    try:
        warehouse = Warehouse.objects.get(name=warehouse_name)
    except Warehouse.DoesNotExist:
        raise ValueError(f"Warehouse '{warehouse_name}' not found.")

    if func_to_show:
        func_to_show(f"Using warehouse: {warehouse.name}")

    inventories = Inventory.objects.filter(warehouse=warehouse).select_related("product")

    if not inventories:
        raise ValueError("No inventory found to simulate sales.")

    if func_to_show:
        func_to_show(f"Found {inventories.count()} inventory items.")

    start_date = now().replace(hour=8, minute=0, second=0, microsecond=0) - relativedelta(days=total_days)
    days_list = [start_date + relativedelta(days=i) for i in range(total_days)]

    plan = {}

    if func_to_show:
        func_to_show("Creating individual sellout strategies...")

    for idx, inv in enumerate(inventories, start=1):
        if func_to_show:
            func_to_show(f"Planning {idx}/{inventories.count()}", end="\r")

        initial_qty = inv.quantity
        if initial_qty <= 0:
            continue

        # assign different behavior to each product
        roll = random.random()
        if roll < 0.2:
            target_pct = random.uniform(0.0, 0.02)       # 20% → sold almost to zero
        elif roll < 0.6:
            target_pct = random.uniform(0.02, 0.07)      # 40% → low remainder
        elif roll < 0.9:
            target_pct = random.uniform(0.07, 0.12)      # 30% → medium remainder
        else:
            target_pct = random.uniform(0.12, 0.25)      # 10% → high remainder

        target_pct = Decimal(target_pct)
        target_qty = int(initial_qty * target_pct)
        to_sell = max(0, initial_qty - target_qty)

        if to_sell <= 0:
            continue

        plan[inv.product.id] = {  # type: ignore
            "inv": inv,
            "initial": initial_qty,
            "target": target_qty,
            "remaining": to_sell
        }

    if func_to_show:
        func_to_show("")

    if func_to_show:
        func_to_show("Simulating daily sales...")

    for day_index, current_day in enumerate(days_list, start=1):
        doc_items = []
        if func_to_show:
            func_to_show(f"Day {day_index}/{total_days} {current_day.date()}", end="\r")

        remaining_days = total_days - day_index + 1

        for pid, data in plan.items():
            remaining = data["remaining"]
            if remaining <= 0:
                continue

            # adaptive daily mean
            daily_mean = float(remaining / remaining_days)

            # realistic variations
            sale = int(abs(random.gauss(daily_mean, daily_mean * 0.25)))
            if sale > remaining:
                sale = remaining

            if sale <= 0:
                continue

            doc_items.append((data["inv"].product, sale))
            data["remaining"] -= sale

        if not doc_items:
            continue

        doc = Document.objects.create(
            doc_type=Document.DocType.SALE,
            status=Document.Status.DRAFT,
            src_warehouse=warehouse,
            doc_date=current_day,
            note=f"Simulated sales for {current_day.date()}",
        )

        for product, qty in doc_items:
            DocumentItem.objects.create(
                document=doc,
                product=product,
                quantity=Decimal(qty)
            )

        doc.post()

    if func_to_show:
        func_to_show("")
