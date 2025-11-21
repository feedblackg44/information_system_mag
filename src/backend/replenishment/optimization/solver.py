from ortools.sat.python import cp_model


def optimize_efficiency(deals_variants_all, max_budget) -> dict | None:
    model = cp_model.CpModel()

    list_of_deals = list(deals_variants_all.values())
    
    M = len(list_of_deals)
    SCALE = 1000  # если efficiency и budget — float, чтобы сделать целыми

    # Создаём переменные выбора для каждой группы и варианта
    y = []
    for g, group in enumerate(list_of_deals):
        row = []
        for v, variant in enumerate(group):
            row.append(model.NewBoolVar(f"y_{g}_{v}"))
        y.append(row)

    # Ограничение: из каждой группы выбрать ровно один вариант
    for g in range(M):
        model.Add(sum(y[g][v] for v in range(len(list_of_deals[g]))) == 1)

    # Ограничение по бюджету
    total_budget = sum(
        int(round(group[v]["budget"] * SCALE)) * y[g][v]
        for g, group in enumerate(list_of_deals)
        for v in range(len(group))
    )
    model.Add(total_budget <= int(round(max_budget * SCALE)))

    # Целевая функция: максимизировать эффективность
    total_eff = sum(
        int(round(group[v]["efficiency"] * SCALE)) * y[g][v]
        for g, group in enumerate(list_of_deals)
        for v in range(len(group))
    )
    model.Maximize(total_eff)

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = 10
    solver.parameters.num_search_workers = 8
    status = solver.Solve(model)

    text_status: dict = {
        cp_model.OPTIMAL: "OPTIMAL",
        cp_model.FEASIBLE: "FEASIBLE",
        cp_model.INFEASIBLE: "INFEASIBLE",
        cp_model.MODEL_INVALID: "MODEL_INVALID",
        cp_model.UNKNOWN: "UNKNOWN"
    }

    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        print(f"❌ No solution found. Status: {text_status.get(status, 'UNKNOWN')}")
        return None

    result = []
    total_efficiency = 0
    total_budget_used = 0

    for g, group in enumerate(list_of_deals):
        for v, variant in enumerate(group):
            if solver.Value(y[g][v]):
                result.append({
                    "group": g,
                    "variant": v,
                    "budget": variant["budget"],
                    "efficiency": variant["efficiency"],
                    "moq": variant["moq"]
                })
                total_efficiency += variant["efficiency"]
                total_budget_used += variant["budget"]
                break

    print(f"✅ Found {text_status.get(status, 'UNKNOWN')} solution: efficiency={total_efficiency:.4f}, budget={total_budget_used:.2f}")
    return {
        "total_efficiency": total_efficiency,
        "total_budget_used": total_budget_used,
        "selection": result
    }
