from .GetDealToMOQ import GetDealToMOQ


def PrecalcBadDeals(order, min_moqs):
    keys = list(order.keys())
    values = list(order.values())

    for i, deal in enumerate(values):
        cur_moq = min_moqs[i] if isinstance(min_moqs, list) else min_moqs[keys[i]]

        items_v = list(deal.values())
        l_items = {}

        # 1️⃣ Собираем только товары с IncludedDispersion = True
        for j, item in enumerate(items_v):
            if item.get('IncludedDispersion'):
                l_items[j] = item

        # 2️⃣ Применяем алгоритм GetDealToMOQ для минимального MOQ
        GetDealToMOQ(deal, cur_moq)
