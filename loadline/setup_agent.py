"""Setup agent: read config, retry boot, write .loadline.yaml. No load generation."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field
from pydantic_ai import Agent, RunContext
from pydantic_ai.usage import UsageLimits

from loadline.adapters.runtime.compose_boot import BootOutcome, boot_repository
from loadline.core.hints import load_hints

SETUP_WRITABLE = frozenset(
    {
        "schema_version",
        "compose_file",
        "dockerfile",
        "app_service",
        "container_port",
        "health_path",
        "compose_profile",
    }
)
MAX_HINT_WRITES = 2
MAX_BOOTS = 3

_READ_SUFFIXES = {".py", ".go", ".ts", ".js", ".mjs", ".md"}
_SETUP_PROMPT = (
    "The repository did not boot. You may read config files and write .loadline.yaml, then boot again. "
    "You must not edit Compose files, Dockerfiles, or application source. You must not run a load test. "
    "Writable keys are schema_version, compose_file, dockerfile, app_service, container_port, "
    "health_path, and compose_profile. The env key is not writable. "
    "If the blocker is a security refusal, stop. After two hint writes, stop."
)


class HintWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = "1"
    compose_file: str | None = None
    dockerfile: str | None = None
    app_service: str | None = None
    container_port: int | None = Field(default=None, ge=1, le=65535)
    health_path: str | None = None
    compose_profile: str | None = None


@dataclass
class SetupState:
    repo: Path
    outcome: BootOutcome
    writes: int = 0
    boots: int = 1


def _denied_config_path(repo: Path, rel: str) -> str | None:
    if not rel or Path(rel).is_absolute():
        return "path must be repo-relative"
    target = (repo / rel).resolve()
    root = repo.resolve()
    if not str(target).startswith(str(root)):
        return "path outside repository"
    name = target.name
    lowered = name.lower()
    if lowered == ".env" or lowered.endswith(".pem") or "id_rsa" in lowered or "credentials" in lowered:
        return "path denied"
    if name in {".loadline.yaml", ".env.example"} or name.upper().startswith("README"):
        return None
    if name in {"compose.yaml", "compose.yml", "docker-compose.yaml", "docker-compose.yml"}:
        return None
    if name in {
        "compose.override.yaml",
        "compose.override.yml",
        "docker-compose.override.yaml",
        "docker-compose.override.yml",
    }:
        return None
    if name == "Dockerfile" or name.startswith("Dockerfile.") or name.endswith(".Dockerfile"):
        return None
    if target.suffix.lower() in _READ_SUFFIXES:
        return None
    return "path is not config or a route file"


def hints_from_boot(boot: dict[str, Any]) -> dict[str, Any]:
    """Hint document for a boot that already succeeded. Never includes env."""
    doc: dict[str, Any] = {"schema_version": "1"}
    for key in ("compose_file", "dockerfile", "app_service", "compose_profile"):
        value = boot.get(key)
        if isinstance(value, str) and value:
            doc[key] = value
    port = boot.get("container_port")
    if isinstance(port, int):
        doc["container_port"] = port
    health = boot.get("health") if isinstance(boot.get("health"), dict) else {}
    path = health.get("path") if isinstance(health, dict) else None
    if isinstance(path, str) and path.startswith("/"):
        doc["health_path"] = path
    return doc


def write_hints_file(repo: Path, payload: dict[str, Any]) -> tuple[bool, str]:
    unknown = set(payload) - SETUP_WRITABLE
    if unknown:
        return False, f"keys not writable: {sorted(unknown)}"
    try:
        hint = HintWrite.model_validate(payload)
    except Exception as exc:
        return False, str(exc)
    if hint.health_path is not None and not hint.health_path.startswith("/"):
        return False, "health_path must start with /"
    doc = hint.model_dump(exclude_none=True)
    doc["schema_version"] = "1"
    text = yaml.safe_dump(doc, sort_keys=False)
    if "docker.sock" in text or "privileged" in text:
        return False, "refused"
    tmp = repo / ".loadline.yaml.tmp"
    tmp.write_text(text, encoding="utf-8")
    _hints, err = load_hints(tmp)
    if err:
        tmp.unlink(missing_ok=True)
        return False, err
    tmp.replace(repo / ".loadline.yaml")
    return True, ""


def build_setup_agent(model: Any) -> Agent[SetupState, str]:
    agent: Agent[SetupState, str] = Agent(
        model,
        system_prompt=_SETUP_PROMPT,
        output_type=str,
        deps_type=SetupState,
    )

    @agent.tool(name="read_config")
    def read_config(ctx: RunContext[SetupState], path: str = "") -> dict[str, Any]:
        repo = ctx.deps.repo
        blocker = ctx.deps.outcome.blocker
        if not path:
            names = []
            for candidate in (
                "compose.yaml",
                "compose.yml",
                "docker-compose.yaml",
                "docker-compose.yml",
                "compose.override.yaml",
                "compose.override.yml",
                "docker-compose.override.yaml",
                "docker-compose.override.yml",
                "Dockerfile",
                ".loadline.yaml",
                ".env.example",
                "README.md",
            ):
                if (repo / candidate).is_file():
                    names.append(candidate)
            return {
                "files": names,
                "blocker": blocker,
                "config_schema": "loadline-hints/1",
                "writable_keys": sorted(SETUP_WRITABLE),
            }
        denied = _denied_config_path(repo, path)
        if denied:
            return {"error": denied}
        target = repo / path
        if not target.is_file():
            return {"error": "file not found"}
        return {"path": path, "text": target.read_text(encoding="utf-8", errors="ignore")[:65536], "blocker": blocker}

    @agent.tool(name="try_boot")
    def try_boot(ctx: RunContext[SetupState]) -> dict[str, Any]:
        if ctx.deps.boots >= MAX_BOOTS:
            return {"error": "boot limit reached", "blocker": ctx.deps.outcome.blocker}
        ctx.deps.boots += 1
        outcome = boot_repository(ctx.deps.repo, teardown=True, require_auth=False)
        ctx.deps.outcome = outcome
        return {
            "status": outcome.status,
            "exit_code": outcome.exit_code,
            "blocker": outcome.blocker,
            "boot": outcome.boot,
        }

    @agent.tool(name="write_hints")
    def write_hints(ctx: RunContext[SetupState], payload: HintWrite) -> dict[str, Any]:
        blocker = ctx.deps.outcome.blocker or {}
        if blocker.get("security"):
            return {"error": "security blocker; refusing to write hints"}
        if ctx.deps.writes >= MAX_HINT_WRITES:
            return {"error": "hint write limit reached"}
        ok, err = write_hints_file(ctx.deps.repo, payload.model_dump(exclude_none=True))
        if not ok:
            return {"error": err}
        ctx.deps.writes += 1
        return {"wrote": ".loadline.yaml", "writes": ctx.deps.writes}

    return agent


def default_setup_model() -> Any:
    from loadline.investigator.run import _openrouter_model_from_env

    return _openrouter_model_from_env()


def run_setup_agent(repo: Path, outcome: BootOutcome, *, model: Any | None = None) -> BootOutcome:
    state = SetupState(repo=repo.resolve(), outcome=outcome, boots=1)
    resolved = model if model is not None else default_setup_model()
    agent = build_setup_agent(resolved)
    summary = (outcome.blocker or {}).get("summary") or outcome.status
    try:
        agent.run_sync(
            f"Boot status is {outcome.status}. Blocker: {summary}. Fix only .loadline.yaml if a hint can.",
            deps=state,
            usage_limits=UsageLimits(request_limit=8),
        )
    except Exception as exc:
        if state.outcome.blocker is not None:
            state.outcome.blocker = dict(state.outcome.blocker)
            state.outcome.blocker["setup_error"] = f"{type(exc).__name__}: {exc}"
        return state.outcome
    return state.outcome
