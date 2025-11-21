def sort_and_find_indexes(a, f) -> tuple[list, int, int]:
    f_values = {key: f(value) for key, value in a.items()}

    pairs = sorted(f_values.items(), key=lambda x: x[1], reverse=True)

    total_sum = sum(f_values.values())
    target_85 = 0.85 * total_sum
    target_95 = 0.95 * total_sum

    current_sum = 0
    index_85 = -1
    index_95 = -1

    for i, (_, value) in enumerate(pairs):
        current_sum += value
        if index_85 == -1 and current_sum >= target_85:
            index_85 = i
        if index_95 == -1 and current_sum >= target_95:
            index_95 = i
            break

    sorted_keys = [key for key, _ in pairs]
    return sorted_keys, index_85, index_95
