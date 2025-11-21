from .PurchasePrice import PurchasePrice


def ItemBudget(item, moq):
    best_sq = item['BestSuggestedQuantity']
    purchase_price = PurchasePrice(item, moq)
    return best_sq * purchase_price