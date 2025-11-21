def DaysForSale(item):
    ads = item['AverageDailySales']
    inv = item['Inventory']
    best_sq = item['BestSuggestedQuantity']
    
    if ads != 0:
        return (best_sq + inv) / ads
    return 0