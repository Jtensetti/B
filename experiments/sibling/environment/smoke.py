"""Exercise the collector with real Claude Code and a local deterministic transport. No solver data."""
import json
import os
import subprocess
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from uuid import uuid4

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from collect_c import collect


class Messages(BaseHTTPRequestHandler):
    """Request six next calls, then end the session. Output usage is fixed."""

    def do_POST(self):
        if self.path.split("?")[0] != "/v1/messages":
            self.send_error(404)
            return
        request = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        calls = sum(block.get("type") == "tool_result" for msg in request["messages"]
                    if isinstance(msg["content"], list) for block in msg["content"])
        key = uuid4().hex
        message = {"id": "msg_" + key, "type": "message", "role": "assistant", "model": request["model"],
                   "content": [], "stop_reason": None, "stop_sequence": None,
                   "usage": {"input_tokens": 10, "output_tokens": 0}}
        if calls < 6:
            block = {"type": "tool_use", "id": "toolu_" + key, "name": "Bash", "input": {}}
            delta = {"type": "input_json_delta", "partial_json": json.dumps(
                {"command": "./next", "description": "Record a transport test snapshot"})}
            reason = "tool_use"
        else:
            block = {"type": "text", "text": ""}
            delta = {"type": "text_delta", "text": "DONE"}
            reason = "end_turn"
        events = [
            {"type": "message_start", "message": message},
            {"type": "content_block_start", "index": 0, "content_block": block},
            {"type": "content_block_delta", "index": 0, "delta": delta},
            {"type": "content_block_stop", "index": 0},
            {"type": "message_delta", "delta": {"stop_reason": reason, "stop_sequence": None},
             "usage": {"output_tokens": 4}},
            {"type": "message_stop"},
        ]
        response = "".join(f"event: {e['type']}\ndata: {json.dumps(e)}\n\n" for e in events).encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Content-Length", str(len(response)))
        self.end_headers()
        self.wfile.write(response)


def main():
    with ThreadingHTTPServer(("127.0.0.1", 0), Messages) as server, tempfile.TemporaryDirectory() as tmp:
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        image = "b-sibling-local-transport"
        dockerfile = (f"FROM b-sibling-c:0.32\n"
                      f"ENV ANTHROPIC_BASE_URL=http://127.0.0.1:{server.server_port}\n")
        subprocess.run(["docker", "build", "-t", image, "-"], input=dockerfile, text=True, check=True)
        root = Path(tmp)
        steps = root / "state" / "steps"
        steps.mkdir(parents=True)
        for n in range(1, 6):
            (steps / f"change{n}.md").write_text(f"Transport test step {n}.")
        os.environ["ANTHROPIC_API_KEY"] = "local-transport-test"
        try:
            collect(root, "py1", image, "claude-haiku-4-5-20251001", "host", "ANTHROPIC_API_KEY")
            summary = json.loads((root / "transcripts" / "py1.json").read_text())
            assert summary["output_tokens"] == summary["reported_result_tokens"] == 28, summary
            assert sorted(p.name for p in (root / "state/snapshots/py1").iterdir()) == [
                f"step{n}" for n in range(6)]
        except BaseException:
            for name in ("py1.stderr", "py1.stream.jsonl"):
                path = root / "transcripts" / name
                if path.exists():
                    print(path.read_text()[-4000:], file=sys.stderr)
            raise
        finally:
            server.shutdown()
            thread.join()


if __name__ == "__main__":
    main()
