"""resolve() matches today's picker (Phase 2). No boot, no disk writes."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from loadline.adapters.runtime.compose_boot import (
    _health_url,
    _infer_app_service,
    _resolve_compose_path,
)
from loadline.config.target import Target
from loadline.core.hints import load_hints
from loadline.core.hints import LoadlineHints
from loadline.discovery.intake import discover_profile, load_compose


@dataclass(frozen=True)
class ResolvedConfig:
    hints: LoadlineHints | None
    compose_file: str | None
    target: Target | None = None
    blocker: dict[str, Any] | None = None
    error: str | None = None
    prepare: list[Any] = field(default_factory=list)
    auth: dict[str, Any] = field(default_factory=dict)
    start_set: Literal["all", "closure"] = "all"


def _no_service_blocker() -> dict[str, Any]:
    return {
        "code": "needs_input",
        "summary": "No application service found in compose.",
        "retryable": False,
        "security": False,
        "user_can_provide": ["app_service"],
        "remediation": [{"kind": "hint", "field": "app_service", "reason": "Name the HTTP app service"}],
    }


def resolve(repo: Path) -> ResolvedConfig:
    repo = repo.resolve()
    hints, hints_error = load_hints(repo / ".loadline.yaml")
    if hints_error:
        return ResolvedConfig(
            hints=None,
            compose_file=None,
            target=None,
            blocker=None,
            error=hints_error,
            prepare=[],
            auth={},
            start_set="all",
        )
    profile = discover_profile(repo)
    compose_path = _resolve_compose_path(repo, profile, hints)
    if compose_path is None:
        return ResolvedConfig(
            hints=hints,
            compose_file=None,
            target=None,
            blocker={
                "code": "blocked",
                "summary": "No compose file found.",
                "retryable": False,
                "security": False,
                "user_can_provide": ["compose_file"],
                "remediation": [],
            },
            error=None,
            prepare=list(hints.prepare) if hints and hints.prepare else [],
            auth=dict(hints.auth) if hints and hints.auth else {},
            start_set=hints.compose.start_set if hints and hints.compose else "all",
        )
    raw = load_compose(compose_path)
    app_service = _infer_app_service(raw, hints)
    if not app_service:
        return ResolvedConfig(
            hints=hints,
            compose_file=str(compose_path.relative_to(repo)) if compose_path.is_relative_to(repo) else str(compose_path),
            target=None,
            blocker=_no_service_blocker(),
            error=None,
            prepare=list(hints.prepare) if hints and hints.prepare else [],
            auth=dict(hints.auth) if hints and hints.auth else {},
            start_set=hints.compose.start_set if hints and hints.compose else "all",
        )
    services = raw.get("services") or {}
    spec = services.get(app_service) if isinstance(services, dict) else None
    spec = spec if isinstance(spec, dict) else {}
    port, health_path = _health_url(app_service, hints, spec)
    origin = f"http://{app_service}:{port}{health_path}"
    target = Target(service=app_service, port=port, health_path=health_path, origin=origin)
    try:
        rel = str(compose_path.relative_to(repo))
    except ValueError:
        rel = str(compose_path)
    return ResolvedConfig(
        hints=hints,
        compose_file=rel,
        target=target,
        blocker=None,
        error=None,
        prepare=list(hints.prepare) if hints and hints.prepare else [],
        auth=dict(hints.auth) if hints and hints.auth else {},
        start_set=hints.compose.start_set if hints and hints.compose else "all",
    )
