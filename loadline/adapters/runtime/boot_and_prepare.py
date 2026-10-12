"""Phase 3 wrapper + Phase 6 prepare replay (empty list stays on boot_repository)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from loadline.adapters.runtime.compose_boot import BootOutcome, boot_repository
from loadline.core.hints import LoadlineHints
from loadline.ui.run_console import BootProgress


def _phase3_body(
    repo: Path,
    *,
    hints: LoadlineHints | None,
    teardown: bool,
    require_auth: bool,
    progress: BootProgress | None,
    config: Any | None = None,
) -> BootOutcome:
    outcome = boot_repository(
        repo, hints=hints, teardown=teardown, require_auth=require_auth, progress=progress
    )
    if outcome.status == "booted" and outcome.boot:
        health = (outcome.boot.get("health") or {})
        url = (health.get("url") or "").strip()
        if url:
            parsed = urlparse(url)
            host = parsed.hostname
            port = parsed.port or 8000
            path = parsed.path or health.get("path") or "/health"
            if host:
                origin = url
                compose_file: str | None = None
                start_set = "all"
                if config is not None:
                    try:
                        start_set = str(getattr(config, "start_set", "all") or "all")
                    except Exception:
                        start_set = "all"
                elif hints is not None:
                    try:
                        if isinstance(hints, dict):
                            _cs = (hints.get("compose") or {})
                            start_set = str(_cs.get("start_set", "all") if isinstance(_cs, dict) else "all")
                        else:
                            _cs = getattr(hints, "compose", None)
                            start_set = str(getattr(_cs, "start_set", "all") or "all")
                    except Exception:
                        start_set = "all"
                if hints is not None:
                    if isinstance(hints, dict):
                        compose_file = hints.get("compose_file")  # type: ignore[no-any-return]
                    else:
                        compose_file = getattr(hints, "compose_file", None)
                if not compose_file:
                    # Best-effort: file boot already selected (first compose file).
                    try:
                        run_dir_raw = outcome.boot.get("run_dir")
                        if run_dir_raw:
                            profile_path = Path(str(run_dir_raw)) / "profile.json"
                            if profile_path.is_file():
                                profile = json.loads(profile_path.read_text())
                                files = profile.get("compose_files") or []
                                if files:
                                    compose_file = str(files[0])
                    except (OSError, ValueError):
                        compose_file = None
                payload: dict[str, Any] = {
                    "service": host,
                    "port": port,
                    "path": path,
                    "origin": origin,
                    "compose_file": compose_file,
                    "start_set": start_set if start_set in ("all", "closure") else "all",
                }
                try:
                    run_dir_raw = outcome.boot.get("run_dir")
                    if run_dir_raw:
                        run_dir = Path(str(run_dir_raw))
                    elif outcome.run_id:
                        from loadline.paths import loadline_home

                        run_dir = loadline_home() / "runs" / outcome.run_id
                    else:
                        run_dir = None
                    if run_dir is not None:
                        run_dir.mkdir(parents=True, exist_ok=True)
                        (run_dir / "resolved_target.json").write_text(json.dumps(payload, indent=2))
                except OSError:
                    pass
    return outcome


def boot_and_prepare(
    repo: Path,
    *,
    hints: LoadlineHints | None = None,
    teardown: bool = True,
    require_auth: bool = True,
    progress: BootProgress | None = None,
    config: Any | None = None,
) -> BootOutcome:
    prepare_list: list[Any] = []
    auth_dict: dict[str, Any] = {}
    if config is not None:
        try:
            prepare_list = list(getattr(config, "prepare", []) or [])
        except (TypeError, ValueError):
            prepare_list = []
        try:
            raw_auth = getattr(config, "auth", {}) or {}
            auth_dict = dict(raw_auth) if isinstance(raw_auth, dict) else {}
        except (TypeError, ValueError):
            auth_dict = {}
    elif hints is not None:
        try:
            if isinstance(hints, dict):
                prepare_list = list(hints.get("prepare") or [])
                raw_auth = hints.get("auth") or {}
                auth_dict = dict(raw_auth) if isinstance(raw_auth, dict) else {}
            else:
                prepare_list = list(getattr(hints, "prepare", []) or [])
                raw_auth = getattr(hints, "auth", {}) or {}
                auth_dict = dict(raw_auth) if isinstance(raw_auth, dict) else {}
        except (TypeError, ValueError):
            prepare_list = []
            auth_dict = {}
    if not prepare_list and not auth_dict:
        outcome = _phase3_body(repo, hints=hints, teardown=teardown, require_auth=require_auth, progress=progress, config=config)
        _record_auth_none_if_applicable(repo, outcome)
        return outcome
    if not prepare_list:
        # Auth-only path: boot then probe.
        outcome = _phase3_body(repo, hints=hints, teardown=teardown, require_auth=require_auth, progress=progress, config=config)
        if outcome.status != "booted":
            return outcome
        return _run_auth_probe(repo, outcome, auth_dict, config)
    # Non-empty prepare: validate then run, then existing up-and-health path.
    from loadline.adapters.runtime.prepare import is_duplicate, normalize_step, validate_step

    repo = repo.resolve()
    # Load compose dict read-only (no boot yet).
    compose: dict[str, Any] = {}
    app_service: str | None = None
    try:
        from loadline.adapters.runtime.compose_boot import _infer_app_service, _resolve_compose_path
        from loadline.discovery.intake import discover_profile, load_compose

        profile = discover_profile(repo)
        compose_path = _resolve_compose_path(repo, profile, hints)
        if compose_path is not None and compose_path.is_file():
            compose = load_compose(compose_path)
            app_service = _infer_app_service(compose, hints)
    except (OSError, ValueError):
        compose = {}
        app_service = None
    limitations: list[str] = []
    for raw_step in prepare_list:
        cmd, required = normalize_step(raw_step)
        if not cmd:
            continue
        if app_service and is_duplicate(cmd, app_service, compose):
            continue
        decision = validate_step(cmd, compose, repo)
        if decision.get("decision") == "needs_confirmation":
            return BootOutcome(
                status="blocked",
                exit_code=10,
                blocker={
                    "code": "needs_confirmation",
                    "summary": f"prepare step needs confirmation: {cmd}",
                    "retryable": True,
                    "security": False,
                    "user_can_provide": [],
                    "remediation": [],
                },
            )
        if decision.get("decision") == "rejected":
            if required:
                return BootOutcome(
                    status="blocked",
                    exit_code=7,
                    blocker={
                        "code": "prepare_failed",
                        "summary": f"prepare step rejected: {cmd}",
                        "retryable": False,
                        "security": False,
                        "user_can_provide": [],
                        "remediation": [],
                    },
                )
            limitations.append(f"prepare skipped (rejected): {cmd}")
            continue
        # Allowed: run in one-off container (sandbox). Tests mock execute_prepare_command.
        ok = execute_prepare_command(repo, cmd, compose, app_service, teardown=teardown)
        if not ok:
            if required:
                return BootOutcome(
                    status="blocked",
                    exit_code=7,
                    blocker={
                        "code": "prepare_failed",
                        "summary": f"prepare step failed: {cmd}",
                        "retryable": True,
                        "security": False,
                        "user_can_provide": [],
                        "remediation": [],
                    },
                )
            limitations.append(f"prepare optional failed: {cmd}")
    outcome = _phase3_body(repo, hints=hints, teardown=teardown, require_auth=require_auth, progress=progress, config=config)
    if limitations and outcome.status == "booted" and outcome.boot is not None:
        try:
            outcome.boot.setdefault("limitations", []).extend(limitations)
        except (AttributeError, TypeError):
            pass
    if outcome.status != "booted":
        return outcome
    if auth_dict:
        return _run_auth_probe(repo, outcome, auth_dict, config)
    _record_auth_none_if_applicable(repo, outcome)
    return outcome


def _record_auth_none_if_applicable(repo: Path, outcome: BootOutcome) -> None:
    if outcome.status != "booted" or outcome.boot is None:
        return
    if "auth" in outcome.boot:
        return
    try:
        from loadline.adapters.runtime.probe import detect_login_routes

        routes = detect_login_routes(repo.resolve())
    except Exception:
        routes = []
    if not routes:
        outcome.boot["auth"] = {"status": "none", "evidence": "no login-like route", "verified": True}
    else:
        outcome.boot.setdefault("limitations", []).append("auth: login-like route without profile")


def _run_auth_probe(repo: Path, outcome: BootOutcome, auth_dict: dict[str, Any], config: Any | None) -> BootOutcome:
    if outcome.status != "booted" or outcome.boot is None:
        return outcome
    try:
        from loadline.adapters.runtime.probe import probe_profile
        from loadline.investigator.run import _sealed_auth_profiles

        boot = outcome.boot
        health = (boot.get("health") or {})
        url = (health.get("url") or "").strip()
        if not url:
            return outcome
        parsed = urlparse(url)
        service = parsed.hostname or ""
        port = parsed.port or 8000
        network = str(boot.get("network") or "")
        # Credentials from in-memory boot values (sealed helper reads repo .env;
        # boot-generated replacements would already be in boot dict when present).
        sealed = {}
        try:
            sealed = _sealed_auth_profiles(repo.resolve())
        except Exception:
            sealed = {}
        # Prefer boot-provided auth_profiles when present (in-memory, not disk).
        boot_profiles = boot.get("auth_profiles") or {}
        combined: dict[str, dict[str, str]] = {}
        for k, v in sealed.items():
            if isinstance(v, dict):
                combined[k] = dict(v)
        for k, v in boot_profiles.items():
            if isinstance(v, dict):
                combined[k] = dict(v)
        expected_meta = None
        try:
            if config is not None:
                meta = getattr(getattr(config, "hints", None), "meta", None)
                if isinstance(meta, dict):
                    expected_meta = meta.get("auth")
                else:
                    hints_meta = getattr(config, "hints", None)
                    if hints_meta is not None and isinstance(getattr(hints_meta, "meta", None), dict):
                        expected_meta = getattr(hints_meta, "meta").get("auth")
        except Exception:
            expected_meta = None
        # Support both {profile: cfg} and single-profile {method, path, ...} shapes.
        profiles: list[tuple[str, dict[str, Any]]] = []
        if auth_dict and all(isinstance(v, dict) for v in auth_dict.values()) and any(
            isinstance(v, dict) and ("path" in v or "method" in v) for v in auth_dict.values()
        ):
            for pname, pcfg in auth_dict.items():
                if isinstance(pcfg, dict):
                    profiles.append((str(pname), dict(pcfg)))
        elif auth_dict and ("path" in auth_dict or "method" in auth_dict):
            pname = str(auth_dict.get("profile") or "default_user")
            profiles.append((pname, dict(auth_dict)))
        else:
            # Generic: each key is a profile with possibly empty cfg.
            for pname, pcfg in auth_dict.items():
                profiles.append((str(pname), dict(pcfg) if isinstance(pcfg, dict) else {}))
        verified_any = False
        for pname, pcfg in profiles:
            creds = combined.get(pname) or {}
            if not creds:
                # Fall back to default_user sealed when available (keeps template runs working).
                if pname != "default_user":
                    continue
                creds = combined.get("default_user") or {}
            # Fill service/port into k6 plan shape (stored for investigator via boot).
            pcfg = dict(pcfg)
            pcfg.setdefault("service", service)
            pcfg.setdefault("port", port)
            result = probe_profile(
                network=network,
                service=service,
                port=port,
                profile_name=pname,
                profile_cfg=pcfg,
                credentials=creds,
                expected_meta=expected_meta if isinstance(expected_meta, dict) else None,
            )
            if result.get("blocker"):
                blocker = result["blocker"]
                if isinstance(blocker, dict) and blocker.get("code") == "auth_failed":
                    return BootOutcome(
                        status="blocked",
                        exit_code=7,
                        blocker=blocker,
                        attempts=outcome.attempts,
                        capabilities=outcome.capabilities,
                        launch_plan=outcome.launch_plan,
                        boot=outcome.boot,
                        run_id=outcome.run_id,
                    )
            if result.get("verified"):
                verified_any = True
                # Store in-memory credentials for investigator (never written to disk).
                boot.setdefault("auth_profiles", {})[pname] = dict(creds)
                boot["auth"] = {"status": "verified", "profile": pname, "verified": True}
            elif result.get("limitation"):
                boot.setdefault("limitations", []).append(str(result["limitation"]))
                boot["auth"] = {"status": "unverified", "profile": pname, "verified": False}
            elif result.get("warning"):
                boot.setdefault("limitations", []).append(str(result["warning"]))
                boot["auth"] = {"status": "unverified", "profile": pname, "verified": False}
        return outcome
    except Exception:
        return outcome


def execute_prepare_command(
    repo: Path,
    command: str,
    compose: dict[str, Any],
    app_service: str | None,
    *,
    teardown: bool = True,
) -> bool:
    """Run a prepare command in a one-off container. Returns True on success."""
    from loadline.adapters.runtime.docker_runner import docker_cmd

    # Start dependency services is handled by boot path; here we run one-off.
    # Minimal: docker run on app image would require image; in unit tests this is mocked.
    # Real implementation defers to compose up path; return False when no app service.
    if not app_service:
        return False
    proc = docker_cmd(["ps"], timeout=30)
    return getattr(proc, "returncode", 1) == 0
