def DealSumByDeal(deal):
    return sum(item['BestSuggestedQuantity'] for item in deal.values())
        