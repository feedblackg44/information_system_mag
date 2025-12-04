from datetime import datetime
import math
import os
import tkinter as tk
from tkinter import filedialog, simpledialog

from .beautify import beautify
from .fill_formulas import main as fill_formulas
from .from_matlab.GetAllDealVariants import GetAllDealVariants
from .map_to_table import map_to_table
from .prepare_file import main as prepare_file
from .solver import optimize_efficiency
from .write_out_table import write_out_table


def main():
    root = tk.Tk()
    root.withdraw()

    output_func = print

    file_path = filedialog.askopenfilename(
        initialdir=".",
        title="Select a .xlsx file",
        filetypes=(("Excel files", "*.xlsx"), ("All files", "*.*")),
    )

    if file_path:
        output_func(f"Selected file: {file_path}")
    else:
        output_func("No file selected.")
        exit(1)

    max_investment_period = simpledialog.askinteger(
        "Input",
        "Enter the maximum investment period (in days):", 
        minvalue=1
    )
    
    output_func("Processing the selected file...")
    
    sorted_data = prepare_file(file_path)
    
    output_func(f"Calculating variants for {max_investment_period} days...")

    order, *_ = beautify(sorted_data, max_investment_period)
    
    output_func(f"Found {len(order)} deals after beautification.")
    
    output_func("Calculating all deal variants...")
    time_now = datetime.now()
    deals_variants_all = {idx: GetAllDealVariants(deal) for idx, deal in order.items()}
    output_func(f"Time taken for calculating deal variants: {datetime.now() - time_now}")

    min_budget = 0
    max_budget = 0
    for deal_variants in deals_variants_all.values():
        first_deal = deal_variants[0]
        min_budget += first_deal['budget']
        last_deal = deal_variants[-1]
        max_budget += last_deal['budget']

    min_budget = math.ceil(min_budget)
    max_budget = math.ceil(max_budget)

    budget = None
    while True:
        try:
            budget = simpledialog.askinteger(
                "Input", 
                f"Enter the budget (min: {min_budget}, max: {max_budget}):", 
                minvalue=min_budget, 
                maxvalue=max_budget
            )
            budget = int(budget) if budget is not None else None
        except ValueError:
            output_func("Invalid budget input. Please enter a valid number.")
            budget = None
        except TypeError:
            output_func("Budget input cancelled. Exiting.")
            exit(1)

        if budget is not None:
            break

    output_func(f"Finding solution for budget: {budget}...")

    time_now = datetime.now()
    optimal_solution = optimize_efficiency(deals_variants_all, budget)
    output_func(f"Time taken for optimization: {datetime.now() - time_now}")
    
    if optimal_solution is None:
        output_func("No optimal solution found with the given budget.")
        exit(1)

    correct_variant = optimal_solution['selection']
    efficiency = optimal_solution['total_efficiency']
    budget_used = optimal_solution['total_budget_used']

    order_keys = list(order.keys())
    correct_order = {}
    for gp_variant in correct_variant:
        group_idx = gp_variant['group']
        variant_idx = gp_variant['variant']
        deal_key = order_keys[group_idx]
        correct_order[deal_key] = deals_variants_all[deal_key][variant_idx]['deal']

    output_folder = filedialog.askdirectory(
        title="Select output folder",
        initialdir="."
    )

    if not output_folder:
        output_folder = "output/"

    if not os.path.exists(output_folder):
        os.makedirs(output_folder, exist_ok=True)

    part1 = os.path.splitext(os.path.basename(file_path))[0]
    output_file_path = os.path.join(
        output_folder, 
        f"{part1} {max_investment_period} days "
        f"(P - {round(efficiency)}, B - {round(budget_used)}) "
        f"{datetime.today().strftime('%d.%m.%Y')}"
    )

    table_out, second_table, third_table = map_to_table(correct_order, efficiency, max_investment_period)
    write_out_table(table_out, sorted_data, second_table, third_table, output_file_path + ".xlsx")

    output_func(f"Output written to {output_file_path}.xlsx")

    output_func("Filling formulas in the output file...")
    fill_formulas(output_file_path + ".xlsx", echo=True)


if __name__ == "__main__":
    main()
