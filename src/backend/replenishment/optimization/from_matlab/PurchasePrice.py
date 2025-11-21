from .CurrentMOQ import CurrentMOQ

def PurchasePrice(item, moq):
    cur_moq = CurrentMOQ(item, moq)
    prices = item['PurchasePrices']
    MOQs = item['MOQs']
    return prices[MOQs.index(cur_moq)]
    