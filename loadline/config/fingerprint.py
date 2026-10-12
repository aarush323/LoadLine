"""Fingerprint for generated configs (Phase 5)."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any


def _hash_file(path: Path, h: Any) -> None:
    try:
        h.update(path.read_bytes())
    except OSError:
        pass
    h.update(b"\x00")
    h.update(str(path.name).encode())
    h.update(b"\x00")


def fingerprint_repo(
    repo: Path,
    compose_file: str | None,
    *,
    evidence: list[str] | None = None,
) -> str:
    repo = repo.resolve()
    h = hashlib.sha256()
    if compose_file:
        cf = (repo / compose_file) if not Path(compose_file).is_absolute() else Path(compose_file)
        if cf.is_file():
            _hash_file(cf, h)
            # Dockerfiles next to compose file.
            for candidate in cf.parent.glob("Dockerfile*"):
                if candidate.is_file():
                    _hash_file(candidate, h)
            # Also Dockerfiles at repo root.
            for candidate in repo.glob("Dockerfile*"):
                if candidate.is_file() and candidate not in list(cf.parent.glob("Dockerfile*")):
                    _hash_file(candidate, h)
        h.update(compose_file.encode())
        h.update(b"\x00")
    else:
        for candidate in repo.glob("Dockerfile*"):
            if candidate.is_file():
                _hash_file(candidate, h)
    example = repo / ".env.example"
    if example.is_file():
        _hash_file(example, h)
    for rel in evidence or []:
        p = (repo / rel) if not Path(rel).is_absolute() else Path(rel)
        if p.is_file():
            _hash_file(p, h)
        else:
            h.update(str(rel).encode())
            h.update(b"\x00")
    return h.hexdigest()[:32]


def repo_key(repo: Path) -> str:
    resolved = repo.resolve()
    digest = hashlib.sha256(str(resolved).encode()).hexdigest()[:12]
    safe = "".join(c if c.isalnum() or c in ("-", "_") else "_" for c in resolved.name)
    safe = safe[:40] or "repo"
    return f"{safe}-{digest}"


def config_dir_for_repo(repo: Path, home: Path | None = None) -> Path:
    from loadline.paths import loadline_home

    base = home if home is not None else loadline_home()
    return base / "configs" / repo_key(repo)


def check_fingerprint_warning(repo: Path) -> str | None:
    """Return warning string when stored fingerprint mismatches current. None otherwise."""
    import yaml

    cfg_path = config_dir_for_repo(repo) / "loadline.yaml"
    if not cfg_path.is_file():
        return None
    try:
        data = yaml.safe_load(cfg_path.read_text()) or {}
    except (OSError, yaml.YAMLError):
        return None
    if not isinstance(data, dict):
        return None
    meta = data.get("meta") or {}
    stored = meta.get("fingerprint") if isinstance(meta, dict) else None
    if not stored:
        return None
    compose_file = data.get("compose_file")
    if isinstance(data.get("compose"), dict):
        files = (data["compose"].get("files") or [])
        if files and not compose_file:
            compose_file = files[0] if isinstance(files[0], str) else None
    evidence: list[str] = []
    if isinstance(meta, dict):
        ev = meta.get("evidence")
        if isinstance(ev, list):
            evidence = [str(x) for x in ev if isinstance(x, str)]
    current = fingerprint_repo(repo, compose_file if isinstance(compose_file, str) else None, evidence=evidence)
    if current != stored:
        return f"warning: fingerprint mismatch for {repo} (config may be stale; still booting via detection)"
    return None
