import numpy as np
from .Profit import Profit


def GetDealToMOQ(deal, desired_moq):
    # Отбираем релевантные товары
    items, incorrect_items = [], []
    for item in deal.values():
        if Profit(item, desired_moq) > 0 and item['AverageDailySales'] > 0 and item['BestSuggestedQuantity'] < item['CanBeSoldTotal']:
            items.append(item)
        else:
            incorrect_items.append(item)

    ads = np.array([item['AverageDailySales'] for item in items], dtype=float)

    if ads.sum() == 0 or not items:
        items = list(deal.values())
        incorrect_items = []
        ads = np.array([item['AverageDailySales'] for item in items], dtype=float)
        incorrect_amounts = 0

    invs = np.array([item['Inventory'] for item in items], dtype=int)
    min_q = np.array([item['SystemSuggestedQuantity'] for item in items], dtype=int)
    incorrect_amounts = np.array([item['BestSuggestedQuantity'] for item in incorrect_items], dtype=int)

    desired_moq += invs.sum() - incorrect_amounts.sum()

    # Пропорциональное распределение
    # c = desired_moq / ads.sum()
    # x = np.floor(ads * c).astype(int)
    # x = np.maximum(x, min_q + invs)
    x = min_q + invs
    
    diff = int(desired_moq - x.sum())
    
    # if diff > 0 and diff >= len(x):
    #     x += 1
    # elif diff > 0:
    #     residuals = ads * c - x
    #     # priority = (1 - residuals) / ads
    #     x[np.argpartition(-residuals, diff)[:diff]] += 1

    func_correct = lambda a, b, diff=diff: a + b if diff > 0 else a - b
    
    if diff != 0:
        z = x / ads
        for _ in range(diff):
            mean_z = z.mean()
            mean2_z = (z ** 2).mean()
            
            new_mean = func_correct(mean_z, 1 / (len(z) * ads))
            new_mean2 = func_correct(mean2_z, (2 * z + 1 / ads) / (len(z) * ads))
            new_var = new_mean2 - new_mean ** 2

            best_idx = np.argmin(new_var)
            
            x[best_idx] = func_correct(x[best_idx], 1)
            z[best_idx] = func_correct(z[best_idx], 1 / ads[best_idx])

    # Учитываем наличие на складе
    x -= invs

    # Применяем рассчитанные количества
    for item, qty in zip(items, x):
        item['BestSuggestedQuantity'] = qty
