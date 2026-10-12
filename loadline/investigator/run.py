"""Run the Investigator agent."""

from __future__ import annotations

import os

os.environ.setdefault("PYDANTIC_AI_NO_BANNER", "1")

import asyncio
import json
import logging
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic_ai.models.test import TestModel

from loadline.core.ledger import Ledger
from loadline.entire_runtime.graph import GraphClient
from loadline.entire_runtime.install import ensure_toolchain
from loadline.core.env_policy import load_repo_dotenv
from loadline.investigator.agent_factory import build_investigator_agent, default_usage_limits, wrap_agent
from loadline.investigator.deps import InvestigationDeps, ReadRange
from loadline.investigator.prompt import load_investigator_prompt
from loadline.ui.agent_trace import format_stream_event
from pydantic_ai.run import AgentRunResultEvent

logger = logging.getLogger(__name__)

USER_PROMPT = (
    "The app is booted. Find which endpoints break under load and why, from the code and from run_k6. "
    "Use a small smoke run_k6, then raise offered rate in roughly doubling steps with a cheap health path in the same call. "
    "Stop when p95 jumps, drops appear, or vus_max_reached — do not chase noisy single-step reversals with many more experiments. "
    "Respect run_k6 rate and experiment limits in the tool response. "
    "End the report with a loadline_fix fence citing the saturation experiment and the handler you read."
)


@dataclass
class InvestigationResult:
    run_id: str
    run_dir: Path
    status: str
    reason: str | None = None
    agent_output: str | None = None


def write_agent_report(
    run_dir: Path,
    run_id: str,
    markdown: str,
    *,
    run_state: str = "completed",
) -> Path:
    """Persist the agent's markdown as report.md (not template-rendered)."""
    md_path = run_dir / "report.md"
    md_path.write_text(markdown)
    json_path = run_dir / "report.json"
    json_path.write_text(
        json.dumps({"run_state": run_state, "source": "investigator_agent"}, indent=2),
        encoding="utf-8",
    )
    ledger = Ledger.open(run_dir, run_id)
    ledger.append(
        "report_written",
        evidence_ids=[],
        run_state=run_state,
        paths={"report_md": str(md_path), "report_json": str(json_path)},
    )
    return md_path


def persist_reads(run_dir: Path, ranges: list[ReadRange]) -> Path:
    """Write one JSON object per successful read_file. Replay does not invent ranges."""
    path = run_dir / "reads.jsonl"
    lines: list[str] = []
    for index, item in enumerate(ranges, start=1):
        evidence_id = item.evidence_id or f"ev-read-{index}"
        lines.append(
            json.dumps(
                {
                    "path": item.path,
                    "start_line": item.start_line,
                    "end_line": item.end_line,
                    "evidence_id": evidence_id,
                },
                separators=(",", ":"),
            )
        )
    path.write_text(("\n".join(lines) + "\n") if lines else "", encoding="utf-8")
    return path


def _sealed_auth_profiles(repo_root: Path) -> dict[str, dict[str, str]]:
    env = load_repo_dotenv(repo_root)
    username = (env.get("FIRST_SUPERUSER") or "").strip()
    password = (env.get("FIRST_SUPERUSER_PASSWORD") or "").strip()
    if username and password:
        return {"default_user": {"username": username, "password": password}}
    return {}


async def _run_agent_with_trace(
    agent: Any,
    deps: InvestigationDeps,
    limits: Any,
    console: Any | None,
) -> Any:
    result = None
    verbose = bool(console and getattr(console, "verbose", False))
    async with agent.run_stream_events(USER_PROMPT, deps=deps, usage_limits=limits) as events:
        async for event in events:
            if isinstance(event, AgentRunResultEvent):
                result = event.result
                if console and verbose and result is not None:
                    usage = getattr(result, "usage", None)
                    if usage is not None:
                        console.investigate_event("agent", f"usage {usage}")
                break
            if console:
                line = format_stream_event(event, verbose=verbose)
                if line:
                    style = None
                    if "error" in line.lower():
                        style = "red"
                    console.investigate_event("agent", line, style=style)
    if result is None:
        raise RuntimeError("investigator agent finished without a result")
    return result


def _dirty(repo: Path) -> bool:
    try:
        out = subprocess.check_output(["git", "-C", str(repo), "status", "--porcelain"], text=True)
        return bool(out.strip())
    except (OSError, subprocess.CalledProcessError):
        return False


def _openrouter_model_from_env() -> Any:
    import os

    spec = os.environ.get("LOADLINE_MODEL", "").strip()
    if not spec.startswith("openrouter:"):
        raise RuntimeError("LOADLINE_MODEL must be set to openrouter:<model-id> for live runs")
    from pydantic_ai.models.openrouter import OpenRouterModel

    model_id = spec.split(":", 1)[1]
    return OpenRouterModel(model_id)


def _default_investigator_model() -> Any:
    import os

    spec = os.environ.get("LOADLINE_MODEL", "").strip()
    if spec.startswith("openrouter:"):
        return _openrouter_model_from_env()
    return TestModel(
        call_tools=[],
        custom_output_text="no endpoints were load-tested in this dry run.",
    )


async def run_investigation(
    *,
    repo_root: Path,
    run_dir: Path,
    run_id: str,
    model: Any | None = None,
    boot: dict[str, Any] | None = None,
    allowed_hosts: frozenset[str] | None = None,
    network: str | None = None,
    usage_limits: Any | None = None,
    fast: bool = False,
    console: Any | None = None,
) -> InvestigationResult:
    repo_root = repo_root.resolve()
    prompt_root = Path(__file__).resolve().parents[2]
    prompt = load_investigator_prompt(prompt_root)

    ledger = Ledger.open(run_dir, run_id)
    if console is not None and hasattr(console, "ledger_event"):
        ledger.on_event = console.ledger_event
    graph_client: GraphClient | None = None
    graph_degraded = False
    try:
        toolchain = ensure_toolchain()
        graph_client = GraphClient(toolchain)
    except Exception:
        graph_degraded = True

    boot_rec = boot or {}
    hosts = allowed_hosts if allowed_hosts is not None else frozenset(
        s.get("name") for s in boot_rec.get("services") or [] if s.get("name")
    )
    net = network or str(boot_rec.get("network") or "")

    deps = InvestigationDeps(
        repo_root=repo_root,
        run_dir=run_dir,
        run_id=run_id,
        ledger=ledger,
        graph=graph_client,
        graph_degraded=graph_degraded,
        dirty_worktree=_dirty(repo_root),
        boot=boot_rec,
        allowed_hosts=hosts,
        network=net,
        auth_profiles={**_sealed_auth_profiles(repo_root), **(boot_rec.get("auth_profiles") or {})},
        console=console,
        fast=fast,
    )

    resolved_model = model if model is not None else _default_investigator_model()
    agent = build_investigator_agent(resolved_model, prompt)
    agent = wrap_agent(agent, run_id=run_id, fast=fast)
    limits = usage_limits if usage_limits is not None else default_usage_limits()

    outcome: InvestigationResult
    try:
        import neatlogs

        from loadline.neatlogs_setup import neatlogs_initialized

        if neatlogs_initialized():
            with neatlogs.trace("loadline run", kind="WORKFLOW"):
                result = await _run_agent_with_trace(agent, deps, limits, console)
        else:
            result = await _run_agent_with_trace(agent, deps, limits, console)
        text = str(result.output)
        write_agent_report(run_dir, run_id, text)
        outcome = InvestigationResult(run_id, run_dir, "completed", agent_output=text)
    except Exception as exc:
        reason = f"{type(exc).__name__}: {exc}"
        logger.exception("investigator failed")
        ledger.append("investigation_incomplete", evidence_ids=[], reason=reason)
        write_agent_report(
            run_dir,
            run_id,
            f"# Investigation incomplete\n\n{reason}\n",
            run_state="investigation_incomplete",
        )
        outcome = InvestigationResult(run_id, run_dir, "investigation_incomplete", reason=reason)
    persist_reads(run_dir, deps.read_ranges)
    return outcome


def run_investigation_sync(**kwargs: Any) -> InvestigationResult:
    return asyncio.run(run_investigation(**kwargs))
