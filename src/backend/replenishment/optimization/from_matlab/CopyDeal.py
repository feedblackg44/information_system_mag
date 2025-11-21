def CopyDeal(deal):
    deal_copy = {}

    for key, item in deal.items():
        new_item = dict(item)
        new_item['Deal'] = deal_copy
        deal_copy[key] = new_item

    return deal_copy
