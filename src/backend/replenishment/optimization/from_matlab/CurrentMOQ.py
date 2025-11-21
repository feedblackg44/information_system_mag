from .DealSumByDeal import DealSumByDeal

def CurrentMOQ(item, moq_):
    MOQs = item['MOQs']
    moq = MOQs[0]

    if moq_ < 1:
        deal_sum = DealSumByDeal(item['Deal'])
    else:
        deal_sum = moq_

    for m in MOQs:
        if deal_sum >= m:
            moq = m

    return moq
