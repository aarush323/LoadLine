"""Read-only repository discovery (S2). No containers, no CI execution."""

from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path
from typing import Any, Iterator

import yaml

from loadline.core.target_guard import classify_url

COMPOSE_NAMES = ("compose.yaml", "compose.yml", "docker-compose.yaml", "docker-compose.yml")
OPENAPI_GLOBS = ("openapi.json", "openapi.yaml", "swagger.json", "docs/openapi.json")
SKIP_DIR_NAMES = frozenset(
    {".git", "node_modules", ".venv", "venv", "__pycache__", ".tox", "dist", "build", ".pytest_cache"}
)
MANIFEST_FILES = (
    "pyproject.toml",
    "package.json",
    "go.mod",
    "Cargo.toml",
    "requirements.txt",
    "Pipfile",
    "pom.xml",
    "build.gradle",
)
CLIENT_LIBRARY_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("postgres", re.compile(r"\b(psycopg2?|asyncpg|pg8000|sqlalchemy.*postgres)\b", re.I)),
    ("mysql", re.compile(r"\b(mysqlclient|pymysql|aiomysql|mariadb)\b", re.I)),
    ("mongo", re.compile(r"\b(pymongo|motor|mongodb)\b", re.I)),
    ("redis", re.compile(r"\b(redis|aioredis|hiredis)\b", re.I)),
)


def _iter_repo_files(root: Path, *, suffixes: tuple[str, ...] = (), limit: int = 500) -> Iterator[Path]:
    count = 0
    root = root.resolve()
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [name for name in dirnames if name not in SKIP_DIR_NAMES]
        for name in filenames:
            if count >= limit:
                return
            path = Path(dirpath) / name
            if suffixes and path.suffix not in suffixes and path.name not in suffixes:
                continue
            count += 1
            yield path


def _git_meta(root: Path) -> dict[str, Any]:
    try:
        sha = subprocess.check_output(
            ["git", "-C", str(root), "rev-parse", "HEAD"],
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
        dirty = bool(
            subprocess.check_output(
                ["git", "-C", str(root), "status", "--porcelain"],
                text=True,
                stderr=subprocess.DEVNULL,
            ).strip()
        )
        return {"sha": sha, "dirty": dirty}
    except (OSError, subprocess.CalledProcessError):
        return {"sha": None, "dirty": None}


_COMPOSE_MAX_DEPTH = 6
_COMPOSE_MAX_FILES = 20


def _is_present_file(path: Path) -> bool:
    try:
        return path.is_file()
    except OSError:
        return False


def _find_compose(root: Path) -> list[str]:
    found: list[str] = []
    seen: set[str] = set()
    for name in COMPOSE_NAMES:
        if _is_present_file(root / name):
            found.append(name)
            seen.add(name)
    for path in _iter_repo_files(root, limit=400):
        if len(found) >= _COMPOSE_MAX_FILES:
            break
        rel = path.relative_to(root)
        if len(rel.parts) - 1 > _COMPOSE_MAX_DEPTH:
            continue
        if path.name not in COMPOSE_NAMES:
            continue
        rel_s = rel.as_posix()
        if rel_s in seen:
            continue
        found.append(rel_s)
        seen.add(rel_s)
    return found


def _find_dockerfiles(root: Path) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for name in ("Dockerfile",):
        if _is_present_file(root / name):
            out.append(name)
            seen.add(name)
    for path in _iter_repo_files(root, limit=200):
        if path.name == "Dockerfile" or path.name.endswith(".Dockerfile"):
            rel = path.relative_to(root).as_posix()
            if rel not in seen:
                out.append(rel)
                seen.add(rel)
        if len(out) >= 20:
            break
    return out[:20]


def ensure_launch_files(
    root: Path,
    profile: dict[str, Any],
    *,
    compose_file: str | None = None,
    dockerfile: str | None = None,
) -> dict[str, Any]:
    """Re-stat well-known and hinted launch files after a walk miss or flake."""
    root = root.resolve()
    compose = [str(item) for item in (profile.get("compose_files") or []) if item]
    docker = [str(item) for item in (profile.get("dockerfiles") or []) if item]

    def add_compose(rel: str) -> None:
        if rel and _is_present_file(root / rel) and rel not in compose:
            compose.append(rel)

    def add_docker(rel: str) -> None:
        if rel and _is_present_file(root / rel) and rel not in docker:
            docker.append(rel)

    add_compose(compose_file or "")
    add_docker(dockerfile or "")
    for name in COMPOSE_NAMES:
        add_compose(name)
    add_docker("Dockerfile")
    out = dict(profile)
    out["compose_files"] = compose
    out["dockerfiles"] = docker
    return out


def _find_openapi(root: Path) -> list[str]:
    hits: list[str] = []
    for pattern in OPENAPI_GLOBS:
        p = root / pattern
        if p.is_file():
            hits.append(str(p.relative_to(root)))
    for path in _iter_repo_files(root, suffixes=(".json", ".yaml", ".yml"), limit=300):
        name = path.name.lower()
        if name in ("openapi.json", "openapi.yaml", "swagger.json", "swagger.yaml"):
            rel = str(path.relative_to(root))
            if rel not in hits:
                hits.append(rel)
    return hits[:15]


def _find_manifests(root: Path) -> list[dict[str, str]]:
    found: list[dict[str, str]] = []
    for name in MANIFEST_FILES:
        p = root / name
        if p.is_file():
            found.append({"path": name, "kind": name})
    req_dir = root / "requirements"
    if req_dir.is_dir():
        for p in sorted(req_dir.glob("*.txt"))[:10]:
            found.append({"path": str(p.relative_to(root)), "kind": "requirements.txt"})
    return found


def _languages_and_build_systems(root: Path, manifests: list[dict[str, str]]) -> tuple[list[str], list[str]]:
    exts = {".py": "python", ".js": "javascript", ".ts": "typescript", ".go": "go", ".rs": "rust", ".java": "java"}
    langs: set[str] = set()
    builds: set[str] = set()
    for m in manifests:
        kind = m["kind"]
        if kind == "pyproject.toml":
            builds.add("python-pyproject")
            langs.add("python")
        elif kind == "package.json":
            builds.add("nodejs-npm")
            langs.add("javascript")
        elif kind == "go.mod":
            builds.add("go-modules")
            langs.add("go")
        elif kind == "Cargo.toml":
            builds.add("cargo")
            langs.add("rust")
        elif kind in ("requirements.txt", "Pipfile"):
            builds.add("python-pip")
            langs.add("python")
    for path in _iter_repo_files(root, limit=400):
        if path.suffix in exts:
            langs.add(exts[path.suffix])
        if len(langs) >= 10:
            break
    return sorted(langs), sorted(builds)


def _dockerfile_entrypoints(root: Path, dockerfiles: list[str]) -> list[dict[str, str]]:
    entries: list[dict[str, str]] = []
    for rel in dockerfiles:
        path = root / rel
        try:
            lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
        except OSError:
            continue
        for line in lines:
            stripped = line.strip()
            if stripped.upper().startswith(("CMD ", "ENTRYPOINT ")):
                entries.append(
                    {
                        "source": "dockerfile",
                        "path": rel,
                        "detail": stripped,
                    }
                )
    return entries


def _package_json_entrypoints(root: Path) -> list[dict[str, str]]:
    path = root / "package.json"
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    scripts = data.get("scripts") or {}
    if not isinstance(scripts, dict):
        return []
    return [
        {"source": "package.json", "path": "package.json", "detail": f"{name}: {cmd}"}
        for name, cmd in sorted(scripts.items())
        if isinstance(cmd, str)
    ][:30]


def _compose_entrypoints(root: Path, compose_files: list[str]) -> list[dict[str, str]]:
    entries: list[dict[str, str]] = []
    for rel in compose_files:
        path = root / rel
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except (OSError, yaml.YAMLError):
            continue
        services = data.get("services") or {}
        if not isinstance(services, dict):
            continue
        for svc_name, svc in services.items():
            if not isinstance(svc, dict):
                continue
            cmd = svc.get("command")
            if cmd:
                entries.append(
                    {
                        "source": "compose",
                        "path": rel,
                        "detail": f"service {svc_name}: {cmd!r}",
                    }
                )
    return entries


def _pyproject_entrypoints(root: Path) -> list[dict[str, str]]:
    path = root / "pyproject.toml"
    if not path.is_file():
        return []
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return []
    entries: list[dict[str, str]] = []
    if re.search(r"\[project\.scripts\]", text) or re.search(r"\[tool\.poetry\.scripts\]", text):
        for line in text.splitlines():
            if "=" in line and not line.strip().startswith("#"):
                m = re.match(r'\s*([a-zA-Z0-9_.-]+)\s*=\s*["\']', line)
                if m and m.group(1) not in ("requires", "dependencies"):
                    entries.append(
                        {"source": "pyproject.toml", "path": "pyproject.toml", "detail": line.strip()}
                    )
    main_match = re.search(r'\[project\.scripts\]\s*\n((?:\s*\w+.*\n)*)', text)
    return entries[:20]


def _discover_entrypoints(root: Path, compose_files: list[str], dockerfiles: list[str]) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    out.extend(_dockerfile_entrypoints(root, dockerfiles))
    out.extend(_package_json_entrypoints(root))
    out.extend(_compose_entrypoints(root, compose_files))
    out.extend(_pyproject_entrypoints(root))
    return out


def _dependency_clients(root: Path, manifests: list[dict[str, str]]) -> list[dict[str, str]]:
    hits: list[dict[str, str]] = []
    paths_to_scan = [root / m["path"] for m in manifests]
    for path in _iter_repo_files(root, suffixes=(".toml", ".txt", ".json", ".lock"), limit=80):
        if path not in paths_to_scan:
            paths_to_scan.append(path)
    for path in paths_to_scan:
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")[:50_000]
        except OSError:
            continue
        rel = str(path.relative_to(root)) if path.is_relative_to(root) else path.name
        for client, pattern in CLIENT_LIBRARY_PATTERNS:
            if pattern.search(text):
                hits.append({"library": client, "evidence_path": rel})
    deduped: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for h in hits:
        key = (h["library"], h["evidence_path"])
        if key not in seen:
            seen.add(key)
            deduped.append(h)
    return deduped


def _request_tests(root: Path) -> list[dict[str, str]]:
    found: list[dict[str, str]] = []
    for path in _iter_repo_files(root, limit=500):
        rel = str(path.relative_to(root))
        name = path.name.lower()
        if name.startswith("test_") and path.suffix == ".py":
            found.append({"path": rel, "kind": "pytest_module"})
        elif path.suffix == ".http":
            found.append({"path": rel, "kind": "http_file"})
        elif "postman" in name and path.suffix == ".json":
            found.append({"path": rel, "kind": "postman_collection"})
        elif path.suffix in (".bru",) or name.endswith(".bruno.json"):
            found.append({"path": rel, "kind": "bruno"})
        if len(found) >= 40:
            break
    return found


def _ci_workflows(root: Path) -> list[dict[str, Any]]:
    wf_dir = root / ".github" / "workflows"
    if not wf_dir.is_dir():
        return []
    workflows: list[dict[str, Any]] = []
    for path in sorted(wf_dir.glob("*.yml")) + sorted(wf_dir.glob("*.yaml")):
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except (OSError, yaml.YAMLError):
            continue
        if not isinstance(data, dict):
            continue
        jobs = data.get("jobs") or {}
        job_summaries: list[dict[str, Any]] = []
        if isinstance(jobs, dict):
            for job_name, job in jobs.items():
                if not isinstance(job, dict):
                    continue
                services = list((job.get("services") or {}).keys()) if isinstance(job.get("services"), dict) else []
                steps = job.get("steps") or []
                run_cmds = []
                for step in steps:
                    if isinstance(step, dict) and step.get("run"):
                        run_cmds.append(str(step["run"])[:200])
                job_summaries.append(
                    {
                        "name": job_name,
                        "runs_on": job.get("runs-on"),
                        "services": services,
                        "run_commands": run_cmds[:5],
                    }
                )
        workflows.append(
            {
                "path": str(path.relative_to(root)),
                "jobs": job_summaries,
                "evidence_only": True,
            }
        )
    return workflows


def _scan_external_urls(root: Path) -> list[dict[str, str]]:
    url_re = re.compile(r"https?://[^\s\"'<>]+")
    refs: list[dict[str, str]] = []
    seen: set[str] = set()
    scan_paths: list[Path] = []
    for path in _iter_repo_files(root, suffixes=(".md", ".yaml", ".yml", ".json", ".toml", ".py"), limit=200):
        scan_paths.append(path)
    for path in scan_paths:
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")[:80_000]
        except OSError:
            continue
        for match in url_re.findall(text):
            url = match.rstrip(").,]")
            if url in seen:
                continue
            seen.add(url)
            classified = classify_url(url)
            refs.append({"url": classified.raw, "kind": classified.kind, "host": classified.host})
            if len(refs) >= 60:
                return refs
    return refs


def _architecture_notes(root: Path, compose_files: list[str], dockerfiles: list[str]) -> list[dict[str, str]]:
    notes: list[dict[str, str]] = []
    for rel in compose_files:
        try:
            data = yaml.safe_load((root / rel).read_text(encoding="utf-8")) or {}
        except (OSError, yaml.YAMLError):
            continue
        services = data.get("services") or {}
        if not isinstance(services, dict):
            continue
        for name, svc in services.items():
            if isinstance(svc, dict) and svc.get("platform"):
                notes.append({"source": rel, "detail": f"service {name} platform={svc['platform']}"})
    for rel in dockerfiles:
        try:
            text = (root / rel).read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for line in text.splitlines():
            if "--platform=" in line or line.strip().upper().startswith("FROM --platform"):
                notes.append({"source": rel, "detail": line.strip()[:200]})
    return notes


def _contradictions(
    compose_files: list[str],
    dockerfiles: list[str],
    manifests: list[dict[str, str]],
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    if len(compose_files) > 1:
        items.append(
            {
                "kind": "multiple_compose_files",
                "detail": compose_files,
                "message": "More than one compose file; boot ranks the file that contains an HTTP app.",
            }
        )
    if compose_files and dockerfiles:
        items.append(
            {
                "kind": "compose_and_dockerfile",
                "detail": {"compose_files": compose_files, "dockerfiles": dockerfiles},
                "message": "Both Compose and Dockerfile paths exist; runtime adapter prefers Compose when booting.",
            }
        )
    kinds = {m["kind"] for m in manifests}
    if "pyproject.toml" in kinds and "requirements.txt" in kinds:
        items.append(
            {
                "kind": "dual_python_manifests",
                "detail": ["pyproject.toml", "requirements.txt"],
                "message": "Both pyproject and requirements manifests present; both are recorded.",
            }
        )
    return items


def discover_profile(root: Path) -> dict[str, Any]:
    root = root.resolve()
    compose_files = _find_compose(root)
    dockerfiles = _find_dockerfiles(root)
    manifests = _find_manifests(root)
    languages, build_systems = _languages_and_build_systems(root, manifests)
    external_urls = _scan_external_urls(root)
    profile = {
        "schema_version": 1,
        "root": str(root),
        "vcs": _git_meta(root),
        "languages": languages,
        "build_systems": build_systems,
        "manifests": manifests,
        "compose_files": compose_files,
        "dockerfiles": dockerfiles,
        "openapi_files": _find_openapi(root),
        "external_urls": external_urls,
        "external_refs": [u["url"] for u in external_urls],
        "entrypoints": _discover_entrypoints(root, compose_files, dockerfiles),
        "dependency_clients": _dependency_clients(root, manifests),
        "request_tests": _request_tests(root),
        "ci_workflows": _ci_workflows(root),
        "architecture": _architecture_notes(root, compose_files, dockerfiles),
        "contradictions": _contradictions(compose_files, dockerfiles, manifests),
    }
    return profile


def discover_capabilities(profile: dict[str, Any]) -> dict[str, Any]:
    blockers: list[dict[str, Any]] = []
    if not profile.get("compose_files") and not profile.get("dockerfiles"):
        blockers.append(
            {
                "code": "no_entrypoint",
                "summary": "No Compose file or Dockerfile was found.",
                "evidence": [],
                "user_can_provide": ["compose_file", "dockerfile"],
                "unblocks": [],
            }
        )
    runtime_level = "ready" if profile.get("compose_files") or profile.get("dockerfiles") else "unsupported"
    workload_level = "ready" if profile.get("openapi_files") else "degraded"
    if profile.get("request_tests") and not profile.get("openapi_files"):
        workload_level = "degraded"
    return {
        "schema_version": 1,
        "runtime": {"level": runtime_level, "adapter_id": "compose", "reasons": [], "missing": []},
        "workload": {
            "protocol": {"level": workload_level, "adapter_id": "http_openapi", "reasons": [], "missing": []},
        },
        "observability": {},
        "codeintel": {"default": {"level": "ready", "adapter_id": "entire", "reasons": [], "missing": []}},
        "blockers": blockers,
        "contradictions": profile.get("contradictions") or [],
        "attempts": [],
    }


def load_compose(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text()) or {}
    if not isinstance(data, dict):
        raise ValueError("compose file must be a mapping")
    return data
