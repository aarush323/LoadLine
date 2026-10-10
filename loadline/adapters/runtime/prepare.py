"""Prepare replay (Phase 6). No shell; verbatim matching only."""

from __future__ import annotations

from pathlib import Path
from typing import Any


def _cmd_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        return " ".join(str(x) for x in value)
    return str(value)


def _collect_service_texts(compose: dict[str, Any]) -> list[str]:
    out: list[str] = []
    services = compose.get("services") or {}
    if not isinstance(services, dict):
        return out
    for svc in services.values():
        if not isinstance(svc, dict):
            continue
        out.append(_cmd_text(svc.get("command")))
        out.append(_cmd_text(svc.get("entrypoint")))
    return [t for t in out if t.strip()]


def _script_refs(texts: list[str], repo: Path) -> list[str]:
    """Return file contents for .sh paths referenced verbatim in service texts."""
    contents: list[str] = []
    for text in texts:
        for token in text.replace(";", " ").replace("&&", " ").split():
            token = token.strip().strip("'\"")
            if token.endswith(".sh"):
                # Handle paths like scripts/prestart.sh, ./scripts/prestart.sh, /app/scripts/x.sh
                candidate = (repo / token.lstrip("/")).resolve() if not Path(token).is_absolute() else Path(token)
                # Also try repo-relative without leading ./
                if not candidate.is_file():
                    stripped = token.lstrip("./")
                    candidate = (repo / stripped).resolve()
                if candidate.is_file():
                    try:
                        contents.append(candidate.read_text())
                    except OSError:
                        pass
    return contents


def _makefile_recipes(repo: Path) -> list[str]:
    out: list[str] = []
    for name in ("Makefile", "makefile", "GNUmakefile"):
        p = repo / name
        if not p.is_file():
            continue
        try:
            text = p.read_text()
        except OSError:
            continue
        # Recipe lines are indented (tab) under targets; also include all lines for verbatim match.
        out.append(text)
        for line in text.splitlines():
            if line.startswith("\t"):
                out.append(line.strip())
    return out


def _readme_text(repo: Path) -> str:
    for name in ("README.md", "README.rst", "README.txt", "README"):
        p = repo / name
        if p.is_file():
            try:
                return p.read_text()
            except OSError:
                return ""
    return ""


def validate_step(command: str, compose: dict[str, Any], repo: Path) -> dict[str, Any]:
    """Decide if a prepare command may run. No shell executed here."""
    cmd = (command or "").strip()
    if not cmd:
        return {"decision": "rejected", "reason": "empty command"}
    service_texts = _collect_service_texts(compose)
    script_contents = _script_refs(service_texts, repo)
    make_recipes = _makefile_recipes(repo)
    # Allowed sources: service command, entrypoint, script contents, one-shot service command, Makefile.
    # One-shot services are just services; their commands already in service_texts.
    for source in service_texts + script_contents + make_recipes:
        if cmd in source:
            return {"decision": "allowed"}
    readme = _readme_text(repo)
    if readme and cmd in readme:
        return {"decision": "needs_confirmation", "reason": "found only in README"}
    return {"decision": "rejected", "reason": "not found in allowed sources"}


def is_duplicate(command: str, app_service: str | None, compose: dict[str, Any]) -> bool:
    """True when app command/entrypoint or a one-shot service already contains the command."""
    cmd = (command or "").strip()
    if not cmd:
        return False
    services = compose.get("services") or {}
    if not isinstance(services, dict):
        return False
    # App service.
    if app_service and app_service in services:
        svc = services[app_service]
        if isinstance(svc, dict):
            if cmd in _cmd_text(svc.get("command")) or cmd in _cmd_text(svc.get("entrypoint")):
                return True
    # One-shot services that will start: any other service whose command contains it.
    for name, svc in services.items():
        if name == app_service:
            continue
        if not isinstance(svc, dict):
            continue
        if cmd in _cmd_text(svc.get("command")):
            return True
    return False


def normalize_step(step: Any) -> tuple[str, bool]:
    """Return (command, required). String steps are required."""
    if isinstance(step, str):
        return step.strip(), True
    if isinstance(step, dict):
        cmd = str(step.get("command") or step.get("run") or "").strip()
        required = step.get("required", True)
        if "optional" in step:
            required = not bool(step.get("optional"))
        return cmd, bool(required)
    return "", True
