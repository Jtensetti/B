"""Read the registered whole-run token measure and audit a task C CLI transcript."""
import json


def measure(path):
    events = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    if (not events or events[-1].get("type") != "result"
            or events[-1].get("is_error") is not False):
        raise ValueError(f"{path.name}: no successful final result")
    messages = [e["message"] for e in events if e.get("type") == "assistant"]
    total = 0
    by_id = {}
    models = set()
    for message in messages:
        usage = message.get("usage", {}).get("output_tokens")
        if type(usage) is not int or usage < 0 or not message.get("id"):
            raise ValueError(f"{path.name}: missing assistant token usage or message ID")
        if usage:
            models.add(message["model"])
        total += usage  # identical to the summation used in A and B
        by_id[message["id"]] = max(usage, by_id.get(message["id"], 0))
    if not total or not models or any("haiku" not in m.lower() for m in models):
        raise ValueError(f"{path.name}: missing Haiku usage")
    return {"output_tokens": total, "unique_message_tokens": sum(by_id.values()),
            "reported_result_tokens": events[-1].get("usage", {}).get("output_tokens"),
            "models": sorted(models)}
