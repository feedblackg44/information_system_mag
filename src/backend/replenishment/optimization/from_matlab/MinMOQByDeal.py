from .DealSumByDealSQ import DealSumByDealSQ


def MinMOQByDeal(deal):
    min_moq = DealSumByDealSQ(deal)

    for item in deal.values():
        p_p = item["PurchasePrices"]
        sale_price = item["SalePrice"]
        MOQs = item["MOQs"]
        if sale_price <= p_p[0] and item["SystemSuggestedQuantity"] > 0:
            index = 0
            for k in range(len(p_p) - 1, -1, -1):
                if sale_price > p_p[k]:
                    index = k
            min_moq = MOQs[index] if MOQs[index] > min_moq else min_moq

    return min_moq
