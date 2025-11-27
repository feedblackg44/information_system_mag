import numpy as np
from .Profit import Profit


def GetDealToMOQ(deal, desired_moq):
    items, incorrect_items = [], []
    for item in deal.values():
        if Profit(item, desired_moq) > 0 and item['AverageDailySales'] > 0 and item['BestSuggestedQuantity'] < item['CanBeSoldTotal']:
            items.append(item)
        else:
            incorrect_items.append(item)

    ads = np.array((item['AverageDailySales'] for item in items), dtype=float)

    if ads.sum() == 0 or not items:
        items = list(deal.values())
        incorrect_items = []
        ads = np.array((item['AverageDailySales'] for item in items), dtype=float)
        incorrect_amounts = 0

    invs = np.array((item['Inventory'] for item in items), dtype=int)
    min_q = np.array((item['SystemSuggestedQuantity'] for item in items), dtype=int)
    incorrect_amounts = np.array((item['BestSuggestedQuantity'] for item in incorrect_items), dtype=int)

    desired_moq += invs.sum() - incorrect_amounts.sum()

    x = min_q + invs
    
    diff = int(desired_moq - x.sum())

    def func_correct(a, b, diff=diff):
        return a + b if diff > 0 else a - b
    
    if diff != 0:
        dfs = x / ads
        for _ in range(diff):
            mean_dfs = dfs.mean()
            mean2_dfs = (dfs ** 2).mean()
            
            new_mean = func_correct(mean_dfs, 1 / (len(dfs) * ads))
            new_mean2 = func_correct(mean2_dfs, (2 * dfs + 1 / ads) / (len(dfs) * ads))
            new_var = new_mean2 - new_mean ** 2

            best_idx = np.argmin(new_var)
            
            x[best_idx] = func_correct(x[best_idx], 1)
            dfs[best_idx] = func_correct(dfs[best_idx], 1 / ads[best_idx])

    x -= invs

    for item, qty in zip(items, x):
        item['BestSuggestedQuantity'] = qty
