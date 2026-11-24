"""Collect the registered task C runs, with the step controller outside each solver container."""
import argparse
import json
import os
import shlex
import socketserver
import subprocess
import tempfile
import threading
from pathlib import Path
from uuid import uuid4

from checks import CHECK
from next import advance
from transcripts import measure

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
FROZEN = "01a91593241803567c35534acbe3e041d4936b11"
RUN = {"b": "b run main.bee", "py": "python main.py", "ts": "node main.ts", "go": "go run .",
       "rs": "cargo run -q --release", "cs": "dotnet run -c Release --project app/App.csproj"}
LANGUAGE = {"b": "B", "py": "typed Python", "ts": "TypeScript", "go": "Go", "rs": "Rust", "cs": "C#"}
NEXT_CLIENT = '''#!/usr/bin/env python3
import socket
import sys
with socket.socket(socket.AF_UNIX) as s:
    s.connect("/control/next.sock")
    s.sendall(b"next\\n")
    sys.stdout.buffer.write(s.makefile("rb").read())
'''


def frozen(path):
    return subprocess.check_output(["git", "-C", REPO, "show", f"{FROZEN}:{path}"])


def setup_workspace(root, solver):
    ws = root / solver
    # An existing workspace is evidence of an attempt, including an interrupted one.
    ws.mkdir()
    task = "experiments/sibling/task-c"
    files = subprocess.check_output(["git", "-C", REPO, "ls-tree", "-r", "--name-only", FROZEN,
                                     f"{task}/libs"], text=True).splitlines()
    for path in files:
        dest = ws / Path(path).relative_to(task)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(frozen(path))
    (ws / "BRIEF.md").write_bytes(frozen(f"{task}/steps/build.md"))
    if solver[:-1] == "b":
        (ws / "for-models.md").write_bytes(frozen("docs/for-models.md"))
    (ws / "next").write_text(NEXT_CLIENT)
    (ws / "next").chmod(0o755)
    return ws


def prompt(language):
    return (f"Implement the build in BRIEF.md in {LANGUAGE[language]}. Your working directory is /work. "
            "Use only this workspace and the provided libraries and tools. You may wrap, call or port "
            "libraries. Do not search for the trial, its other submissions or later changes. "
            + ("Read the supplied for-models.md guide. " if language == "b" else "")
            + f"Run with {RUN[language]}. Check with {shlex.join(CHECK[language])}. "
            "Run ./next after the build and after each finished change. Each call records your current "
            "program for grading and gives the next instruction. Stop when ./next returns END.")


def collect(root, solver, image, model, network, credential):
    ws = setup_workspace(root, solver)
    transcripts = root / "transcripts"
    transcripts.mkdir(exist_ok=True)
    instructions = prompt(solver[:-1])
    (transcripts / f"{solver}.prompt").write_text(instructions)
    session = str(uuid4())
    cli = ["claude", "-p", "--session-id", session, "--model", model, "--output-format", "stream-json", "--verbose",
           "--tools", "Bash,Read,Edit,Write,Glob,Grep", "--allowedTools", "Bash,Read,Edit,Write,Glob,Grep",
           "--strict-mcp-config", "--mcp-config", '{"mcpServers":{}}']
    startup = ('set -eu; mkdir -p "$HOME/.cache"; cp -r /opt/seed-cache "$HOME/.cache/b"; cp -a /opt/deps/node_modules .; '
               'exec "$@"')
    with tempfile.TemporaryDirectory(prefix="sibling-control-", dir="/tmp") as control:
        class Next(socketserver.StreamRequestHandler):
            def handle(self):
                if self.rfile.readline(16) == b"next\n":
                    reply = advance(root / "state", ws)
                    self.wfile.write((reply + "\n").encode())
        with socketserver.UnixStreamServer(str(Path(control) / "next.sock"), Next) as server:
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            cidfile = Path(control) / "cid"
            cmd = ["docker", "run", "--cidfile", str(cidfile), "-i", "--init", "--network", network,
                   "--user", f"{os.getuid()}:{os.getgid()}", "-e", "HOME=/tmp/solver-home",
                   "-e", credential, "-e", "CLAUDE_CONFIG_DIR=/tmp/solver-config",
                   "-e", "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1",
                   "-v", f"{ws}:/work", "-v", f"{control}:/control:ro",
                   "-w", "/work", image, "sh", "-c", startup, "sh", *cli]
            try:
                with (transcripts / f"{solver}.stream.jsonl").open("xb") as out, (
                        transcripts / f"{solver}.stderr").open("xb") as err:
                    p = subprocess.run(cmd, input=instructions.encode(), stdout=out, stderr=err)
                if cidfile.is_file():
                    container = cidfile.read_text().strip()
                    journal = f"/tmp/solver-config/projects/-work/{session}.jsonl"
                    subprocess.run(["docker", "cp", f"{container}:{journal}",
                                    str(transcripts / f"{solver}.output")], check=True)
            finally:
                server.shutdown()
                thread.join()
                if cidfile.is_file():
                    subprocess.run(["docker", "rm", "-f", cidfile.read_text().strip()], check=True)
    usage = measure(transcripts / f"{solver}.output", transcripts / f"{solver}.stream.jsonl")
    snaps = root / "state" / "snapshots" / solver
    if (p.returncode or not snaps.is_dir()
            or {s.name for s in snaps.iterdir()} != {f"step{n}" for n in range(6)}):
        raise SystemExit(f"{solver} incomplete. The attempt and transcript are retained at {root}.")
    (transcripts / f"{solver}.json").write_text(json.dumps({**usage, "exit": p.returncode}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_dir", type=Path)
    parser.add_argument("--model", required=True, help="Claude Haiku model ID")
    parser.add_argument("--network", required=True, help="Docker network restricted to model and registry egress")
    parser.add_argument("--image", default="b-sibling-c:0.32")
    args = parser.parse_args()
    credential = next((k for k in ("ANTHROPIC_API_KEY", "CLAUDE_CODE_OAUTH_TOKEN") if os.environ.get(k)), None)
    if not credential or "haiku" not in args.model.lower():
        parser.error("Provide a Haiku model and authenticated Claude Code environment")
    info = json.loads(subprocess.check_output(["docker", "image", "inspect", args.image]))[0]
    if info["Config"]["Labels"].get("org.opencontainers.image.revision") != FROZEN:
        parser.error("Build the registered image with environment/build.sh")
    root = args.run_dir.resolve()
    root.mkdir(parents=True, exist_ok=True)
    config = {"model": args.model, "image": info["Id"], "compiler": FROZEN, "network": args.network}
    config_file = root / "collection.json"
    if config_file.exists() and json.loads(config_file.read_text()) != config:
        parser.error("The recorded collection configuration differs")
    config_file.write_text(json.dumps(config, indent=2))
    steps = root / "state" / "steps"
    steps.mkdir(parents=True, exist_ok=True)
    for n in range(1, 6):
        (steps / f"change{n}.md").write_bytes(frozen(f"experiments/sibling/task-c/steps/change{n}.md"))
    roster = {f"{lang}{n}": f"{lang}{n}" for lang in CHECK for n in range(1, 4)}
    (root / "agents.json").write_text(json.dumps(roster))
    for solver in roster:
        if (root / "transcripts" / f"{solver}.json").is_file():
            continue
        if (root / solver).exists():
            parser.error(f"Unfinished attempt for {solver} requires adjudication before collection resumes")
        collect(root, solver, info["Id"], args.model, args.network, credential)


if __name__ == "__main__":
    main()
