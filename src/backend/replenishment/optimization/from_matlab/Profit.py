from .PurchasePrice import PurchasePrice

def Profit(item, moq):
    price = PurchasePrice(item, moq)
    sale_price = item['SalePrice']
    return sale_price - price