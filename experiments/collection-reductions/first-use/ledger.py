def ledger(records: list[dict[str, int]], allowance: int) -> dict[str, int]:
    incomplete = 0
    over = 0
    extra = 0
    for record in records:
        if "gross" not in record or "tare" not in record:
            incomplete += 1
            continue
        excess = record["gross"] - record["tare"] - allowance
        if excess > 0:
            over += 1
            extra += excess
    return {"weighed": len(records), "incomplete": incomplete, "over": over, "extra": extra}
