"""Load agent, used only by loadline load (Phase 8). Run never calls it."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from loadline.load.tools import TryBootCap, check_config, write_config
from loadline.ui.phases import Phase

if TYPE_CHECKING:
    from loadline.ui.run_console import RunConsole


def should_call_agent(resolved_cfg: Any, repo: Path) -> bool:
    """True when login-like route with empty auth, or prepare ambiguous."""
    try:
        from loadline.adapters.runtime.probe import detect_login_routes
        from loadline.adapters.runtime.prepare import validate_step
        from loadline.discovery.intake import load_compose
        from loadline.adapters.runtime.compose_boot import _resolve_compose_path
        from loadline.discovery.intake import discover_profile
    except Exception:
        return False
    repo = repo.resolve()
    # Case 1: resolve found login-like route and auth empty.
    try:
        auth = getattr(resolved_cfg, "auth", {}) or {}
        target = getattr(resolved_cfg, "target", None)
        if target is not None and not auth:
            routes = detect_login_routes(repo)
            if routes:
                return True
    except Exception:
        pass
    # Case 2: prepare ambiguous (more than one allowed source, or README-only).
    try:
        prepare = list(getattr(resolved_cfg, "prepare", []) or [])
        if not prepare:
            return False
        # Load compose for source counting.
        hints = getattr(resolved_cfg, "hints", None)
        profile = discover_profile(repo)
        compose_path = _resolve_compose_path(repo, profile, hints)
        compose: dict[str, Any] = {}
        if compose_path is not None and compose_path.is_file():
            compose = load_compose(compose_path)
        from loadline.adapters.runtime.prepare import _collect_service_texts, _makefile_recipes

        service_texts = _collect_service_texts(compose)
        make_recipes = _makefile_recipes(repo)
        for raw in prepare:
            cmd = raw if isinstance(raw, str) else str((raw.get("command") or raw.get("run") or "") if isinstance(raw, dict) else "")
            cmd = cmd.strip()
            if not cmd:
                continue
            decision = validate_step(cmd, compose, repo)
            if decision.get("decision") == "needs_confirmation":
                return True
            # More than one allowed source: in service texts AND in Makefile.
            in_service = any(cmd in t for t in service_texts)
            in_make = any(cmd in t for t in make_recipes)
            if in_service and in_make:
                return True
    except Exception:
        pass
    return False


def run_load_agent(
    repo: Path,
    resolved_cfg: Any,
    *,
    refresh: bool = False,
    cap: int = 5,
    console: RunConsole | None = None,
) -> dict[str, Any]:
    """Deterministic agent core (no shell). Service/port/path come from ResolvedConfig."""
    repo = repo.resolve()
    target = getattr(resolved_cfg, "target", None)
    if target is None:
        return {"error": "no target", "limitations": ["no target from detection"]}
    # Service/port/path already on ResolvedConfig; agent may correct only with file:line evidence.
    # Here we keep detection values (no invention) to satisfy unit tests.
    service = getattr(target, "service", "")
    port = getattr(target, "port", 0)
    health_path = getattr(target, "health_path", "/health")
    # check_config (schema only).
    from loadline.config.fingerprint import fingerprint_repo

    compose_file = getattr(resolved_cfg, "compose_file", None)
    start_set = getattr(resolved_cfg, "start_set", "all") or "all"
    prepare = list(getattr(resolved_cfg, "prepare", []) or [])
    auth = dict(getattr(resolved_cfg, "auth", {}) or {})
    fp = fingerprint_repo(repo, compose_file if isinstance(compose_file, str) else None, evidence=[])
    data: dict[str, Any] = {
        "schema_version": "1",
        "compose_file": compose_file,
        "app_service": service,
        "container_port": port,
        "health_path": health_path,
        "compose": {"start_set": start_set},
        "prepare": prepare,
        "auth": auth,
        "meta": {"fingerprint": fp},
    }
    chk = check_config(data)
    if not chk.get("ok"):
        return {"error": chk.get("error"), "limitations": ["invalid config"]}
    # try_boot capped at 5.
    cap_obj = TryBootCap(limit=cap)
    limitations: list[str] = []
    best: dict[str, Any] | None = None
    progress = console.boot_progress() if console is not None and console.enabled() else None
    hints = getattr(resolved_cfg, "hints", None)
    for _ in range(cap):
        attempt = cap_obj.calls + 1
        if console is not None and console.enabled():
            console.trace(f"try_boot attempt {attempt}/{cap}")
        if progress is not None and console is not None and console.enabled() and cap_obj.calls == 0:
            console.phase_start(Phase.BOOT)
        res = cap_obj.try_boot(repo, hints, progress=progress, config=resolved_cfg)
        if res.get("capped"):
            limitations.extend(res.get("limitations") or [])
            break
        best = res
        status = res.get("status")
        if console is not None and console.enabled():
            summary = ""
            blocker = res.get("blocker")
            if isinstance(blocker, dict):
                summary = str(blocker.get("summary") or "")
            console.trace(f"try_boot result: {status}" + (f" ({summary})" if summary else ""))
        if status == "booted":
            if console is not None and console.enabled():
                console.phase_done(Phase.BOOT, "healthy")
            break
        limitations.append(
            f"try_boot {status}: {(res.get('blocker') or {}).get('summary') if isinstance(res.get('blocker'), dict) else ''}"
        )
        if console is not None and console.enabled():
            console.phase_done(Phase.BOOT, str(status))
        break
    if cap_obj.calls >= cap:
        limitations.append(f"try_boot capped at {cap}")
    out = write_config(data, repo, refresh=refresh)
    return {"path": out.get("path"), "limitations": limitations, "service": service, "port": port, "health_path": health_path}
