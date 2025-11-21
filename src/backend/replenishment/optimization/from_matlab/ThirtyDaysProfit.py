from .Profit import Profit


def ThirtyDaysProfit(item, moq):
    avg_daily_sales = item['AverageDailySales']
    inventory = item['Inventory']
    best_sq = item['BestSuggestedQuantity']
    profit = Profit(item, moq)
    
    quantity = min(best_sq, max(30 * avg_daily_sales - inventory, 0))
    if profit < 0 and quantity > 0:
        return 100 / (profit * quantity)
    return profit * quantity
        