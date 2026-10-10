"""Run the pinned Entire Graph commands. No shell, no init-agents."""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field

from loadline.entire_runtime.errors import GraphInvocationError
from loadline.entire_runtime.install import Toolchain

ALLOWED = frozenset(
    {"help", "version", "capabilities", "doctor", "search", "query", "def", "neighbors", "impact", "edges"}
)
DEFAULT_TIMEOUT_S = 60
DEFAULT_MAX_BYTES = 256_000


@dataclass
class GraphOutput:
    args: list[str]
    text: str
    timed_out: bool = False
    truncated: bool = False
    ok: bool = True
    data: object | None = None
    records: list[dict] = field(default_factory=list)


class GraphClient:
    def __init__(self, toolchain: Toolchain, *, timeout_s: float = DEFAULT_TIMEOUT_S, max_bytes: int = DEFAULT_MAX_BYTES) -> None:
        self.toolchain = toolchain
        self.timeout_s = timeout_s
        self.max_bytes = max_bytes
        self._help: str | None = None

    def run(self, args: list[str]) -> GraphOutput:
        if not args or args[0] not in ALLOWED:
            raise GraphInvocationError(f"Refusing graph command {args!r}.")
        if "init-agents" in args:
            raise GraphInvocationError("Refusing to modify a repository's agent instructions.")
        command = [str(self.toolchain.entire), "graph", *args]
        try:
            completed = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=self.timeout_s,
                env=self.toolchain.subprocess_env(),
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise GraphInvocationError(
                f"entire graph {' '.join(args)} timed out after {self.timeout_s}s.",
                timed_out=True,
            ) from exc
        text = completed.stdout or ""
        truncated = False
        if len(text.encode()) > self.max_bytes:
            text = text.encode()[: self.max_bytes].decode(errors="ignore")
            truncated = True
        output = GraphOutput(args=args, text=text, truncated=truncated, ok=completed.returncode == 0 and not truncated)
        if not output.ok:
            output.text = text or (completed.stderr or "")
            return output
        fmt = None
        if "--format" in args:
            fmt = args[args.index("--format") + 1]
        elif "--json" in args:
            fmt = "json"
        if fmt == "json":
            try:
                output.data = json.loads(text)
            except json.JSONDecodeError:
                output.ok = False
        elif fmt == "ndjson":
            records: list[dict] = []
            for line in text.splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    item = json.loads(line)
                except json.JSONDecodeError:
                    output.ok = False
                    break
                if isinstance(item, dict):
                    records.append(item)
            output.records = records
        return output

    def help_text(self) -> str:
        if self._help is None:
            result = self.run(["help"])
            self._help = result.text
        return self._help

    def ranked_command(self) -> str:
        text = self.help_text()

        def listed(name: str) -> bool:
            for line in text.splitlines():
                stripped = line.strip()
                if stripped == name or stripped.startswith(name + " ") or stripped.startswith(name + "\t"):
                    return True
            return False

        if listed("query"):
            return "query"
        if listed("search"):
            return "search"
        raise GraphInvocationError("Pinned Entire Graph exposes neither query nor search.")

    def edges_supports_worktree(self) -> bool:
        result = self.run(["edges", "--help"])
        return "--worktree" in result.text

    def capabilities(self) -> dict:
        result = self.run(["capabilities", "--json"])
        if not result.ok or not isinstance(result.data, dict):
            raise GraphInvocationError("entire graph capabilities --json was not valid JSON.")
        return result.data
