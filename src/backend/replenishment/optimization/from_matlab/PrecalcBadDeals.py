from .GetDealToMOQ import GetDealToMOQ


def PrecalcBadDeals(order, min_moqs):
    keys = list(order.keys())
    values = list(order.values())

    for i, deal in enumerate(values):
        cur_moq = min_moqs[i] if isinstance(min_moqs, list) else min_moqs[keys[i]]

        items_v = list(deal.values())
        l_items = {}

        for j, item in enumerate(items_v):
            if item.get('IncludedDispersion'):
                l_items[j] = item

        GetDealToMOQ(deal, cur_moq)
