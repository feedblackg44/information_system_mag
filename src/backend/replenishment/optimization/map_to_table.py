import math

import pandas as pd

from .sort_and_find_indexes import sort_and_find_indexes


def map_to_table(order, fbest, max_investment_period):
    sorted_keys, index85, index95 = sort_and_find_indexes(
        order,
        lambda cur_deal: sum([cur_item['SalePrice'] * cur_item['AverageDailySales']
                              for cur_item in cur_deal.values()])
    )

    for i, deal_name in enumerate(sorted_keys):
        values = order[deal_name].values()
        if i <= index85:
            for item in values:
                item['ABC'] = 'A'
        elif i <= index95:
            for item in values:
                item['ABC'] = 'B'

    str_period = f"Can be sold in {math.ceil(max_investment_period)} days"
    columns = ['Deal ID', 'Item No', 'Item Name',
               'Used Minimum Order Quantity', 'Deal Sum',
               'Purchase Price', 'Sale Price', 'Profit',
               'Average Daily Sales', 'Inventory',
               'Can be sold in credit terms', str_period,
               'System Suggested Quantity', 'Best suggested quantity',
               'Days For Sale', 'Item Budget', 'Total Item Sales',
               'Total Item Profit', '30 Days Profit', '30 Days Sales',
               'Weighted Average 30 Day Profit Margin',
               'Effectiveness', 'Average Effectiveness', 'AddToTotal']
    table_out = {col: [] for col in columns}

    columns2 = ['Deal ID', 'ABC']
    second_table = {col: [] for col in columns2}

    columns3 = ['Max Period']
    third_table = {col: [] for col in columns3}
    third_table['Max Period'].append(max_investment_period)

    for deal_name, items in order.items():
        for _, item in items.items():
            item_num = item['ItemNo']
            item_num = int(item_num.replace('x', '')) \
                if isinstance(item_num, str) and item_num.startswith('x') else item_num
            table_out['Deal ID'].append(item['DealName'])
            table_out['Item No'].append(item_num)
            table_out['Item Name'].append(item['ItemName'])
            table_out['Used Minimum Order Quantity'].append(0)
            table_out['Deal Sum'].append(0)
            table_out['Purchase Price'].append(0)
            table_out['Sale Price'].append(item['SalePrice'])
            table_out['Profit'].append(0)
            table_out['Average Daily Sales'].append(item['AverageDailySales'])
            table_out['Inventory'].append(item['Inventory'])
            table_out['Can be sold in credit terms'].append(0)
            table_out[str_period].append(0)
            table_out['System Suggested Quantity'].append(item['SystemSuggestedQuantity'])
            table_out['Best suggested quantity'].append(item['BestSuggestedQuantity'])
            table_out['Days For Sale'].append(0)
            table_out['Item Budget'].append(0)
            table_out['Total Item Sales'].append(0)
            table_out['Total Item Profit'].append(0)
            table_out['30 Days Profit'].append(0)
            table_out['30 Days Sales'].append(0)
            table_out['Weighted Average 30 Day Profit Margin'].append(0)
            table_out['Effectiveness'].append(0)
            table_out['Average Effectiveness'].append(fbest)
            table_out['AddToTotal'].append(0)

            second_table['Deal ID'].append(item['DealName'])
            second_table['ABC'].append(item['ABC'])

    return pd.DataFrame(table_out), pd.DataFrame(second_table), pd.DataFrame(third_table)