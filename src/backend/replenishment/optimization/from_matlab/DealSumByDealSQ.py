import math

def DealSumByDealSQ(deal):
    return sum(math.ceil(item['SystemSuggestedQuantity']) for item in deal.values())
