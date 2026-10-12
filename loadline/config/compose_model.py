"""Compose model, not used by boot (Phase 4)."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Any

import yaml

from loadline.adapters.runtime.docker_runner import docker_cmd


def collect_env_files(compose_dict: dict[str, Any]) -> list[str]:
    out: list[str] = []
    services = compose_dict.get("services") or {}
    if not isinstance(services, dict):
        return out
    for svc in services.values():
        if not isinstance(svc, dict):
            continue
        ef = svc.get("env_file")
        if ef is None:
            continue
        if isinstance(ef, str):
            out.append(ef)
        elif isinstance(ef, list):
            for item in ef:
                if isinstance(item, str):
                    out.append(item)
                elif isinstance(item, dict) and "path" in item:
                    out.append(str(item["path"]))
    return out


def resolve_files(
    repo: Path, base_file: Path, compose_section: Any | None
) -> list[Path]:
    files: list[str] = []
    if compose_section is not None:
        if isinstance(compose_section, dict):
            raw = compose_section.get("files") or []
        else:
            raw = getattr(compose_section, "files", []) or []
        if isinstance(raw, list):
            files = [str(x) for x in raw if isinstance(x, str) and str(x).strip()]
    if files:
        return [(repo / f) for f in files]
    return [base_file]


def restricted_env() -> dict[str, str]:
    env: dict[str, str] = {}
    if os.environ.get("PATH"):
        env["PATH"] = os.environ["PATH"]
    for key in ("DOCKER_HOST", "DOCKER_CERT_PATH", "DOCKER_TLS_VERIFY", "DOCKER_CONTEXT"):
        if os.environ.get(key):
            env[key] = os.environ[key]
    return env


def ensure_runtime_env(
    repo: Path, run_dir: Path, compose_dict: dict[str, Any]
) -> tuple[dict[str, Any], Path]:
    """Rewrite missing env_file entries via .env.example copy. Never writes into repo."""
    run_dir.mkdir(parents=True, exist_ok=True)
    env_files = collect_env_files(compose_dict)
    runtime = yaml.safe_load(yaml.safe_dump(compose_dict)) or {}
    rewritten: Path | None = None
    for ef in env_files:
        candidate = (repo / ef).resolve() if not Path(ef).is_absolute() else Path(ef)
        try:
            inside_repo = candidate.is_relative_to(repo.resolve())
        except (OSError, ValueError):
            inside_repo = False
        exists = candidate.is_file() if inside_repo or Path(ef).is_absolute() else (repo / ef).is_file()
        if exists:
            continue
        example = repo / ".env.example"
        if example.is_file():
            if rewritten is None:
                rewritten = run_dir / ".env.rewritten"
                rewritten.write_text(example.read_text())
            # Rewrite only this env_file entry to absolute rewritten path.
            services = runtime.get("services") or {}
            for svc in services.values():
                if not isinstance(svc, dict):
                    continue
                cur = svc.get("env_file")
                if cur == ef:
                    svc["env_file"] = str(rewritten)
                elif isinstance(cur, list):
                    svc["env_file"] = [str(rewritten) if x == ef else x for x in cur]
    # --env-file selection.
    repo_env = repo / ".env"
    if repo_env.is_file():
        env_arg = repo_env
    elif rewritten is not None and rewritten.is_file():
        env_arg = rewritten
    else:
        empty = run_dir / ".env.empty"
        if not empty.is_file():
            empty.write_text("")
        env_arg = empty
    return runtime, env_arg


def build_compose_command(repo: Path, files: list[Path], env_file: Path) -> list[str]:
    cmd: list[str] = ["compose"]
    for f in files:
        cmd.extend(["-f", str(f)])
    cmd.extend(["--project-directory", str(repo)])
    cmd.extend(["--env-file", str(env_file)])
    cmd.extend(["config", "--no-interpolate"])
    return cmd


def run_compose_config(repo: Path, files: list[Path], env_file: Path, *, timeout: int = 60) -> Any:
    cmd = build_compose_command(repo, files, env_file)
    # Explicit restricted env: PATH + docker socket vars only.
    return subprocess.run(
        ["docker", *cmd],
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
        env=restricted_env(),
    )


def _is_named_volume(src: str) -> bool:
    # Named volumes have no slash and are not . or absolute.
    if not src or src in (".", "./"):
        return False
    if src.startswith(("/", "./", "../", "~")):
        return False
    if "/" in src:
        return False
    return True


def validate_resolved_paths(
    repo: Path,
    run_dir: Path,
    resolved: dict[str, Any],
    *,
    allowed_run_path: Path | None = None,
) -> dict[str, Any] | None:
    """Return blocker dict when a started service escapes the repo. None means ok."""
    repo_r = repo.resolve()
    run_r = run_dir.resolve()
    services = resolved.get("services") or {}
    if not isinstance(services, dict):
        return None
    for name, svc in services.items():
        if not isinstance(svc, dict):
            continue
        # Build context.
        build = svc.get("build")
        ctx: str | None = None
        if isinstance(build, str):
            ctx = build
        elif isinstance(build, dict) and isinstance(build.get("context"), str):
            ctx = build["context"]
        if ctx:
            if _is_named_volume(ctx):
                pass
            else:
                p = Path(ctx)
                abs_p = p if p.is_absolute() else (repo_r / ctx).resolve()
                try:
                    in_repo = abs_p.is_relative_to(repo_r)
                except (OSError, ValueError):
                    in_repo = False
                try:
                    in_run = abs_p.is_relative_to(run_r)
                except (OSError, ValueError):
                    in_run = False
                if in_run and allowed_run_path is not None:
                    try:
                        if abs_p.resolve() != allowed_run_path.resolve() and not abs_p.resolve().is_relative_to(
                            allowed_run_path.resolve() if allowed_run_path.is_dir() else allowed_run_path.parent
                        ):
                            pass
                    except (OSError, ValueError):
                        pass
                    # Only the rewritten env file may live under run dir; build ctx may not.
                    return {
                        "code": "compose_invalid",
                        "summary": f"service {name} build context escapes repo: {ctx}",
                        "retryable": False,
                        "security": False,
                        "user_can_provide": [],
                        "remediation": [],
                    }
                if not in_repo:
                    return {
                        "code": "compose_invalid",
                        "summary": f"service {name} build context escapes repo: {ctx}",
                        "retryable": False,
                        "security": False,
                        "user_can_provide": [],
                        "remediation": [],
                    }
        # Bind mounts.
        for vol in svc.get("volumes") or []:
            src: str | None = None
            if isinstance(vol, str):
                parts = vol.split(":")
                if len(parts) >= 2 and parts[0]:
                    src = parts[0]
                else:
                    continue
            elif isinstance(vol, dict) and vol.get("type") == "bind":
                src = str(vol.get("source") or "")
            else:
                continue
            if not src:
                continue
            if _is_named_volume(src):
                continue
            p = Path(src)
            if not p.is_absolute():
                # Relative bind like ./db/init.sql stays under repo — ok.
                abs_p = (repo_r / src).resolve()
                try:
                    if abs_p.is_relative_to(repo_r):
                        continue
                except (OSError, ValueError):
                    pass
                return {
                    "code": "compose_invalid",
                    "summary": f"service {name} bind mount escapes repo: {src}",
                    "retryable": False,
                    "security": False,
                    "user_can_provide": [],
                    "remediation": [],
                }
            else:
                try:
                    in_repo = abs_p.is_relative_to(repo_r) if (abs_p := p.resolve()) else False
                except (OSError, ValueError):
                    in_repo = False
                try:
                    in_run = p.resolve().is_relative_to(run_r)
                except (OSError, ValueError):
                    in_run = False
                if in_run and allowed_run_path is not None:
                    try:
                        if p.resolve() == allowed_run_path.resolve():
                            continue
                    except (OSError, ValueError):
                        pass
                    return {
                        "code": "compose_invalid",
                        "summary": f"service {name} bind mount escapes repo: {src}",
                        "retryable": False,
                        "security": False,
                        "user_can_provide": [],
                        "remediation": [],
                    }
                if not in_repo:
                    return {
                        "code": "compose_invalid",
                        "summary": f"service {name} bind mount escapes repo: {src}",
                        "retryable": False,
                        "security": False,
                        "user_can_provide": [],
                        "remediation": [],
                    }
    return None


def docker_compose_config(
    repo: Path,
    base_file: Path,
    compose_section: Any | None,
    run_dir: Path,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None, list[str]]:
    """Run `docker compose config` with explicit -f and restricted env.

    Returns (resolved_dict, blocker, command_used).
    """
    raw_text = base_file.read_text() if base_file.is_file() else "{}"
    import yaml as _yaml

    raw = _yaml.safe_load(raw_text) or {}
    files = resolve_files(repo, base_file, compose_section)
    runtime, env_arg = ensure_runtime_env(repo, run_dir, raw)
    cmd = build_compose_command(repo, files, env_arg)
    proc = docker_cmd(cmd, timeout=60)
    # Note: docker_cmd helper inherits env; restricted env is enforced in
    # run_compose_config for the real config path. Tests fake docker_cmd
    # to assert -f / --project-directory / --env-file presence.
    if getattr(proc, "returncode", 1) != 0:
        return None, {
            "code": "compose_invalid",
            "summary": (getattr(proc, "stderr", "") or "compose config failed")[:500],
            "retryable": False,
            "security": False,
            "user_can_provide": [],
            "remediation": [],
        }, cmd
    try:
        resolved = _yaml.safe_load(getattr(proc, "stdout", "") or "") or {}
    except _yaml.YAMLError as exc:
        return None, {
            "code": "compose_invalid",
            "summary": str(exc)[:500],
            "retryable": False,
            "security": False,
            "user_can_provide": [],
            "remediation": [],
        }, cmd
    blocker = validate_resolved_paths(repo, run_dir, resolved, allowed_run_path=env_arg)
    if blocker:
        return None, blocker, cmd
    return resolved, None, cmd
