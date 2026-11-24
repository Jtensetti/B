"""Native check commands fixed in task A's registration."""
import subprocess
import sys

CHECK = {
    "b": ["b", "check", "--strict", "main.bee"],
    "py": ["mypy", "--strict", "main.py"],
    "ts": ["tsc", "--strict", "--noEmit", "--types", "node", "main.ts"],
    "go": ["go", "vet", "."],
    "rs": ["cargo", "build"],
    "cs": ["dotnet", "build", "app"],
}

RUN = {
    "b": ["b", "run", "main.bee"],
    "py": [sys.executable, "main.py"],
    "ts": ["node", "main.ts"],
    "go": ["go", "run", "."],
    "rs": ["cargo", "run", "-q", "--release"],
    "cs": ["dotnet", "run", "-c", "Release", "--project", "app/App.csproj"],
}


def check(language, workspace, timeout=600):
    command = CHECK[language]
    try:
        p = subprocess.run(command, cwd=workspace, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                           text=True, errors="replace", timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"command": command, "exit": None, "diagnostic": str(exc)}
    return {"command": command, "exit": p.returncode, "diagnostic": p.stdout}
