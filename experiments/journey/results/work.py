"""Aggregate work per solver and step from subagent transcripts. Prints numbers only."""
import json, re, sys
from datetime import datetime

AGENTS = {"b1": "a0f5a787d15c5015b", "b2": "aae5f78009280c5f2", "py1": "a74a3601e53f0da66", "py2": "aa1d11adc948035bb"}
BASE = "/tmp/claude-0/-home-user-B/bc1bd2a3-1ba0-5a86-9b4b-8c9b2f90e18b/tasks/"


def text_of(content):
    if isinstance(content, str):
        return content
    return " ".join(c.get("text", "") for c in content if isinstance(c, dict) and c.get("type") == "text")


def analyse(agent):
    steps = {}
    step = None
    for line in open(BASE + agent + ".output"):
        try:
            d = json.loads(line)
        except ValueError:
            continue
        msg = d.get("message") if isinstance(d.get("message"), dict) else {}
        when = d.get("timestamp")
        if d.get("type") == "user" and msg.get("role") == "user":
            body = msg.get("content", "")
            body = body if isinstance(body, str) else json.dumps(body)
            found = re.search(r"Step (\d) of the trial", body) or (
                None if d.get("isMeta") else re.search(r"# Step (\d)", text_of(msg.get("content", ""))))
            if found:
                step = int(found.group(1))
                steps.setdefault(step, {"tool_calls": 0, "output_tokens": 0, "input_tokens": 0,
                                        "start": when, "end": when, "assistant_turns": 0})
        if step is None:
            continue
        row = steps[step]
        row["end"] = when or row["end"]
        if d.get("type") == "assistant":
            usage = msg.get("usage") or {}
            row["output_tokens"] += usage.get("output_tokens", 0)
            row["input_tokens"] += (usage.get("input_tokens", 0) + usage.get("cache_read_input_tokens", 0)
                                    + usage.get("cache_creation_input_tokens", 0))
            row["assistant_turns"] += 1
            for c in msg.get("content", []) if isinstance(msg.get("content"), list) else []:
                if isinstance(c, dict) and c.get("type") == "tool_use":
                    row["tool_calls"] += 1
    for row in steps.values():
        a, b = (datetime.fromisoformat(x.replace("Z", "+00:00")) for x in (row.pop("start"), row.pop("end")))
        row["seconds"] = round((b - a).total_seconds())
    return steps


out = {name: analyse(agent) for name, agent in AGENTS.items()}
print(json.dumps(out, indent=1))
