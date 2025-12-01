import random
from decimal import Decimal

import numpy as np
from crm.models import (
    Brand,
    Document,
    DocumentItem,
    Inventory,
    Product,
    ProductPriceLevel,
    Warehouse,
)
from dateutil.relativedelta import relativedelta
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


def generate_sales_distribution(
    total_days,
    total_sales,
    start_weekday,
    # Chaos parameters
    trend_volatility=0.15,    # How strongly the trend can drift
    season_jitter=0.1,        # How much the seasonality "jitters" from week to week
    spike_prob=0.05,          # Probability of a sales spike (promo/shortage) on a given day
    spike_magnitude=0.6,      # Strength of the spike (0.6 = +/- 60%)
    base_weekly_profile=None, # Base weekly profile
    payday_factors=None
):
    if total_sales <= 0:
        return [0] * total_days

    # 1. Generate "jittery" trend (Random Walk without strong smoothing)
    # Use a smaller window or none at all for more realism
    steps = np.random.normal(0, trend_volatility, total_days)
    walk = np.cumsum(steps)
    
    # Normalize the trend to be a multiplier around 1.0
    # But do it softly to preserve local trends
    if walk.max() != walk.min():
        walk = (walk - walk.min()) / (walk.max() - walk.min()) # 0..1
        walk = 0.8 + (walk * 0.4) # Trend fluctuates from 0.8 to 1.2
    else:
        walk = np.ones(total_days)

    # 2. "Live" seasonality
    # If no profile is provided, take the standard one but add noise for this specific product
    if base_weekly_profile is None:
        # Example: slight randomization of the base so products are not synchronized
        base = np.array([1.0, 1.05, 1.1, 1.15, 1.2, 0.85, 0.8])
        perturbation = np.random.normal(0, 0.1, 7)
        base_weekly_profile = np.maximum(base + perturbation, 0.1)
    
    # Generate seasonality array day by day
    seasonality = []
    current_weekday = start_weekday
    for _ in range(total_days):
        # Take the base factor for the day
        base_factor = base_weekly_profile[current_weekday]
        # Add "jitter" (today's Friday is not the same as last Friday)
        daily_jitter = np.random.normal(0, season_jitter)
        factor = max(0.1, base_factor + daily_jitter)
        seasonality.append(factor)
        current_weekday = (current_weekday + 1) % 7
    
    seasonality = np.array(seasonality)

    # 3. Event-driven spikes (Spikes)
    # Create an event mask: 1.0 is normal, 1.5 is promo, 0.5 is shortage
    spikes = np.ones(total_days)
    # Generate random numbers where < spike_prob an event occurs
    events_mask = np.random.rand(total_days) < spike_prob
    
    # For each event decide: up or down (usually up more often if these are sales)
    for i in np.where(events_mask)[0]:
        direction = 1 if random.random() > 0.3 else -1  # 70% chance of increase, 30% decrease
        magnitude = 1.0 + (direction * random.uniform(0.2, spike_magnitude))
        spikes[i] = max(0.1, magnitude)

    # 4. Noise (daily small variability)
    noise = np.random.lognormal(mean=0.0, sigma=0.2, size=total_days)

    # 5. Assembly
    raw_curve = walk * seasonality * spikes * noise
    
    if payday_factors is not None:
        # If arrays have different lengths, trim or do not apply (error protection)
        if len(payday_factors) == len(raw_curve):
            raw_curve = raw_curve * payday_factors
    
    # 6. Normalization to Total Sales (preserving curve shape)
    current_sum = raw_curve.sum()
    if current_sum == 0:
        return [0] * total_days
        
    scale_factor = total_sales / current_sum
    final_float = raw_curve * scale_factor
    
    sales = np.floor(final_float).astype(int)

    # Remainder distribution (rounding)
    diff = int(total_sales - sales.sum())
    if diff > 0:
        # Add remainders proportionally to weights (where there are already many sales)
        # This is more realistic than random
        indices = np.random.choice(total_days, size=diff, p=raw_curve/raw_curve.sum())
        for idx in indices:
            sales[idx] += 1
    elif diff < 0:
        # If we overshoot (rare but possible with floor and float manipulations)
        for _ in range(abs(diff)):
             # Remove where there are more than 0
             nonzero_indices = np.nonzero(sales)[0]
             if len(nonzero_indices) > 0:
                 idx = random.choice(nonzero_indices)
                 sales[idx] -= 1

    return list(sales)


def get_random_product_profile():
    # Type 1: "Weekend Heavy" (Alcohol, snacks, entertainment)
    # Peak on FRI, SAT. Drop on MON-WED.
    weekend_heavy = np.array([0.7, 0.7, 0.8, 0.9, 1.3, 1.4, 1.2])

    # Type 2: "Office / Weekdays" (Business lunches, paper, B2B)
    # Peak on TUE-THU. Drop on weekends.
    weekday_heavy = np.array([1.1, 1.2, 1.2, 1.1, 1.0, 0.7, 0.7])

    # Type 3: "Staples" (Bread, milk, toilet paper)
    # Almost flat, slight rise towards weekend.
    staples = np.array([0.95, 0.95, 1.0, 1.0, 1.05, 1.1, 1.0])

    # Type 4: "Random Purchases" (Impulse items)
    # Weak day-of-week dependence.
    random_profile = np.random.normal(1.0, 0.1, 7) 
    random_profile = np.maximum(random_profile, 0.8) # Don't let it go to zero

    choices = [weekend_heavy, weekday_heavy, staples, random_profile]
    weights = [0.30, 0.20, 0.40, 0.10]  # 40% staples, 30% weekend heavy, etc.
    
    # Choose one profile
    selected_idx = np.random.choice(len(choices), p=weights)
    base = choices[selected_idx]
    
    # IMPORTANT: Add individuality to each product,
    # so even "weekend heavy" products are not clones of each other.
    unique_twist = np.random.normal(0, 0.05, 7)
    final_profile = np.maximum(base + unique_twist, 0.1)
    
    return final_profile


def get_payday_factors(days_list):
    factors = []
    for current_date in days_list:
        day = current_date.day
        factor = 1.0
        
        # 1. Payday (beginning of the month): peak on days 1-5
        if 1 <= day <= 5:
            # Gradually decreases: +15% on the 1st, +3% on the 5th
            boost = 0.15 * ((6 - day) / 5)
            factor += boost
            
        # 2. Advance (middle of the month): peak on days 15-17
        elif 15 <= day <= 17:
            factor += 0.08 # Fixed boost of 8%
            
        # 3. "End of money" (end of the month): slight decline after the 25th
        elif day > 25:
            factor -= 0.05
            
        factors.append(factor)
        
    return np.array(factors)


def simulate_sales(
    total_days: int,
    min_remain=0.0,
    max_remain=0.1,
    warehouse_name="Main Warehouse",
    func_to_show=None
):
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

    payday_mults = get_payday_factors(days_list)

    plan = {}

    if func_to_show:
        func_to_show("Creating individual sellout strategies...")

    # -------------------------
    # PLAN PHASE: target remainder for each product
    # -------------------------
    for idx, inv in enumerate(inventories, start=1):

        if func_to_show:
            func_to_show(f"Planning {idx}/{inventories.count()}", end="\r")

        initial_qty = inv.quantity
        if initial_qty <= 0:
            continue

        # main difference: use user-provided min_remain/max_remain
        target_pct = random.uniform(min_remain, max_remain)
        target_qty = int(float(initial_qty) * target_pct)

        total_sales = initial_qty - target_qty
        if total_sales <= 0:
            continue
        
        product_weekly_profile = get_random_product_profile()

        daily_sales = generate_sales_distribution(
            total_days, 
            float(total_sales), 
            start_date.weekday(),
            base_weekly_profile=product_weekly_profile,
            trend_volatility=random.uniform(0.05, 0.2), # Some products have smooth trends, others fluctuate
            spike_prob=random.uniform(0.01, 0.05),      # Some have frequent promotions, others rarely
            payday_factors=payday_mults                 # Apply payday effects
        )

        plan[inv.product.id] = {  # type: ignore
            "inv": inv,
            "daily_sales": daily_sales
        }

    if func_to_show:
        func_to_show("\nSimulating daily sales...")

    # -------------------------
    # EXECUTION PHASE
    # -------------------------
    for day_index, current_day in enumerate(days_list, start=1):

        doc_items = []

        if func_to_show:
            func_to_show(f"Day {day_index}/{total_days} {current_day.date()}", end="\r")

        for pid, data in plan.items():
            qty = data["daily_sales"][day_index - 1]
            if qty > 0:
                doc_items.append((data["inv"].product, qty))

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
                quantity=Decimal(int(qty))
            )

        doc.post()

    if func_to_show:
        func_to_show("")
