import math
from .DealSumByDealSQ import DealSumByDealSQ
from .MinMOQByDeal import MinMOQByDeal


def ValidMOQs(deal):
    min_moq = MinMOQByDeal(deal)
    cbst = sum(math.floor(max(item['CanBeSoldTotal'], item['SystemSuggestedQuantity'])) for item in deal.values())
    new_moqs = {moq for item in deal.values() for moq in (item['MOQs'] + [DealSumByDealSQ(deal)]) if min_moq <= moq <= cbst}
    
    if not new_moqs:
        new_moqs = {min_moq}

    return sorted(new_moqs)
