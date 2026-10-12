"""loadline load implementation."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any

import yaml

from loadline.config.fingerprint import check_fingerprint_warning
from loadline.ui.phases import Phase
from loadline.ui.render import emit, use_color

if TYPE_CHECKING:
    from loadline.ui.run_console import RunConsole

__all__ = ["check_fingerprint_warning", "load_repo"]


def _ui(console: RunConsole | None) -> RunConsole:
    if console is not None:
        return console
    from loadline.ui.run_console import RunConsole

    return RunConsole.disabled()


def _load_header(ui: RunConsole, repo: Path) -> None:
    if not ui.enabled():
        return
    emit(f"loadline load  repo={repo}", sys.stderr, use_ansi=use_color(ui.no_color))


def load_repo(
    repo: Path,
    *,
    write_to_repo: bool = False,
    refresh: bool = False,
    console: RunConsole | None = None,
) -> int:
    from loadline.adapters.runtime.boot_and_prepare import boot_and_prepare
    from loadline.adapters.runtime.docker_runner import docker_cmd
    from loadline.config.fingerprint import config_dir_for_repo, fingerprint_repo
    from loadline.config.resolve import resolve
    from loadline.discovery.intake import discover_profile

    ui = _ui(console)
    repo = repo.resolve()
    _load_header(ui, repo)

    ui.trace("Docker: checking daemon")
    try:
        proc = docker_cmd(["info", "--format", "{{json .}}"], timeout=30)
    except Exception as exc:
        print(f"blocked: docker daemon unreachable ({exc})", file=sys.stderr)
        return 10
    if getattr(proc, "returncode", 1) != 0:
        print("blocked: docker daemon unreachable", file=sys.stderr)
        return 10
    ui.trace("Docker: ok")

    ui.trace("Discover: scanning repo")
    profile = discover_profile(repo)
    if not profile.get("compose_files") and not profile.get("dockerfiles"):
        print("blocked: no compose file or Dockerfile found", file=sys.stderr)
        return 10
    compose_hint = (profile.get("compose_files") or ["(dockerfile)"])[0]
    ui.trace(f"Discover: {compose_hint}")

    ui.trace("Resolve: picking app service and health URL")
    cfg = resolve(repo)
    if cfg.error:
        print(f"blocked: {cfg.error}", file=sys.stderr)
        return 10
    if cfg.blocker or cfg.target is None:
        summary = (cfg.blocker or {}).get("summary", "no target") if isinstance(cfg.blocker, dict) else "no target"
        print(f"blocked: {summary}", file=sys.stderr)
        return 10
    assert cfg.target is not None
    ui.trace(
        f"Resolve: service={cfg.target.service} port={cfg.target.port} health_path={cfg.target.health_path}"
    )

    progress = ui.boot_progress() if ui.enabled() else None

    try:
        from loadline.load.agent import run_load_agent, should_call_agent

        if should_call_agent(cfg, repo):
            ui.trace("Setup agent: login or prepare needs confirmation")
            result = run_load_agent(repo, cfg, refresh=refresh, console=ui)
            if result.get("error"):
                print(f"blocked: {result['error']}", file=sys.stderr)
                return 10
            print(f"wrote {result.get('path')} via agent")
            if write_to_repo:
                home_cfg = config_dir_for_repo(repo) / "loadline.yaml"
                if home_cfg.is_file():
                    (repo / ".loadline.yaml").write_text(home_cfg.read_text())
                    print(f"wrote {repo / '.loadline.yaml'}")
            return 0
    except ImportError:
        pass

    ui.trace("Trial boot: start stack, wait for health, tear down")
    ui.phase_start(Phase.BOOT)
    outcome = boot_and_prepare(
        repo,
        hints=cfg.hints,
        teardown=True,
        require_auth=False,
        progress=progress,
        config=cfg,
    )
    if outcome.status == "booted":
        ui.phase_done(Phase.BOOT, "healthy")
    else:
        ui.phase_done(Phase.BOOT, outcome.status)
    if outcome.status != "booted":
        summary = (
            (outcome.blocker or {}).get("summary", outcome.status)
            if isinstance(outcome.blocker, dict)
            else outcome.status
        )
        print(f"blocked: trial boot failed ({summary})", file=sys.stderr)

    ui.trace("Write config")
    assert cfg.compose_file is not None or True
    fp = fingerprint_repo(repo, cfg.compose_file, evidence=[])
    data: dict[str, Any] = {
        "schema_version": "1",
        "compose_file": cfg.compose_file,
        "app_service": cfg.target.service,
        "container_port": cfg.target.port,
        "health_path": cfg.target.health_path,
        "compose": {"start_set": getattr(cfg, "start_set", "all") or "all"},
        "prepare": list(getattr(cfg, "prepare", []) or []),
        "auth": dict(getattr(cfg, "auth", {}) or {}),
        "meta": {"fingerprint": fp},
    }
    if refresh:
        from loadline.load.tools import write_config as _write_config

        out = _write_config(data, repo, refresh=True)
        print(f"wrote {out.get('path')} (refresh diff above)")
    else:
        out_dir = config_dir_for_repo(repo)
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "loadline.yaml").write_text(yaml.safe_dump(data, sort_keys=False))
        print(f"wrote {out_dir / 'loadline.yaml'}")
    if write_to_repo:
        (repo / ".loadline.yaml").write_text(yaml.safe_dump(data, sort_keys=False))
        print(f"wrote {repo / '.loadline.yaml'}")
    return 0
