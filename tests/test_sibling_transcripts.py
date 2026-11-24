"""A live Claude Code assistant event can precede its final token usage."""
import importlib.util
import json
from pathlib import Path

import pytest

MODULE = Path(__file__).resolve().parents[1] / "experiments/sibling/transcripts.py"
spec = importlib.util.spec_from_file_location("sibling_transcripts", MODULE)
transcripts = importlib.util.module_from_spec(spec)
spec.loader.exec_module(transcripts)


def write_events(path, events):
    path.write_text("".join(json.dumps(event) + "\n" for event in events))


def test_grading_uses_finalized_usage_and_keeps_the_historical_sum(tmp_path):
    journal, stream = tmp_path / "solver.output", tmp_path / "solver.stream.jsonl"
    message = {"id": "msg1", "model": "test-haiku", "usage": {"output_tokens": 7}}
    event = {"type": "assistant", "sessionId": "one", "message": message}
    result = {"type": "result", "session_id": "one", "is_error": False, "usage": {"output_tokens": 7}}
    write_events(journal, [event, event])
    write_events(stream, [{"type": "assistant", "message": {**message, "usage": {"output_tokens": 0}}}, result])
    assert transcripts.measure(journal, stream) == {
        "session_id": "one", "output_tokens": 14, "unique_message_tokens": 7, "reported_result_tokens": 7, "models": ["test-haiku"]}
    write_events(stream, [{**result, "session_id": "other"}])
    with pytest.raises(ValueError, match="session IDs"):
        transcripts.measure(journal, stream)
    write_events(stream, [{**result, "is_error": True}])
    with pytest.raises(ValueError, match="successful final result"):
        transcripts.measure(journal, stream)
