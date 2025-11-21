import math

import numpy as np


def beautify(input_table, max_investment_period):
    correct_dict = {}

    deal_names = input_table['Deal ID']
    items_num = input_table['Item No']

    items_name = input_table['Item Name']
    discount_moq = input_table['Minimum Order Quantity']
    purchase_prices = input_table['Purchase Price']
    sale_prices = input_table['Sale Price']
    avg_daily_sales = input_table['Average Daily Sales']
    inventory = input_table['Inventory']
    system_sq = input_table['System Suggested Quantity']
    system_cov_days = input_table['System Coverage Days']
    credit_terms = input_table['Credit Terms']

    items_arr = items_num.unique()
    deals_arr = deal_names.unique()

    items_numbers = np.zeros(items_num.shape, dtype=int)
    for i, item in enumerate(items_arr):
        items_numbers[np.isin(items_num, item)] = i + 1
    items_numbers = [int(i) for i in items_numbers]

    deals_numbers = np.zeros(deal_names.shape, dtype=int)
    for i, deal in enumerate(deals_arr):
        deals_numbers[np.isin(deal_names, deal)] = i + 1
    deals_numbers = [int(i) for i in deals_numbers]

    items = {}

    for i, deal_num in enumerate(deals_numbers):
        if deal_num not in correct_dict:
            correct_dict[deal_num] = {}
        if items_numbers[i] not in correct_dict[deal_num]:
            cur_inventory = max(inventory[i], 0)
            ssq = math.ceil(max(
                system_sq[i], system_cov_days[i] * avg_daily_sales[i] - cur_inventory
            ))
            cur_item = {'ItemNo': items_num[i], 'ItemName': items_name[i],
                        'MOQs': [discount_moq[i]], 'PurchasePrices': [purchase_prices[i]], 'SalePrice': sale_prices[i],
                        'AverageDailySales': avg_daily_sales[i], 'Inventory': cur_inventory,
                        'SystemSuggestedQuantity': ssq, 'BestSuggestedQuantity': ssq,
                        'SystemCoverageDays': system_cov_days[i], 'CreditTerms': credit_terms[i],
                        'MaxInvestmentPeriod': max_investment_period, 'DealName': deal_names[i],
                        'CanBeSoldTotal': max(avg_daily_sales[i] * max_investment_period - cur_inventory, 0),
                        'CanBeSoldCredit': max(avg_daily_sales[i] * credit_terms[i] - cur_inventory, 0), 'ABC': 'C'}
            cur_item['Deal'] = correct_dict[deal_num]

            correct_dict[deal_num][items_numbers[i]] = cur_item
            items[items_numbers[i]] = cur_item
        else:
            MOQs = correct_dict[deal_num][items_numbers[i]]['MOQs']
            MOQs.append(discount_moq[i])
            PurchasePrices = correct_dict[deal_num][items_numbers[i]]['PurchasePrices']
            PurchasePrices.append(purchase_prices[i])
            correct_dict[deal_num][items_numbers[i]]['MOQs'] = MOQs
            correct_dict[deal_num][items_numbers[i]]['PurchasePrices'] = PurchasePrices

    return correct_dict, deals_arr, items_arr, items
