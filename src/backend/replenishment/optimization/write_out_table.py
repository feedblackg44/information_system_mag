import pandas as pd
import os


def write_out_table(table_out, table_in, second_table, third_table, out_name):
    if os.path.exists(out_name):
        os.remove(out_name)

    with pd.ExcelWriter(out_name, engine='openpyxl') as writer:
        table_out.to_excel(writer, sheet_name='Sheet1', index=False)
        table_in.to_excel(writer, sheet_name='Sheet2', index=False)
        second_table.to_excel(writer, sheet_name='Sheet3', index=False)
        third_table.to_excel(writer, sheet_name='Sheet4', index=False)
