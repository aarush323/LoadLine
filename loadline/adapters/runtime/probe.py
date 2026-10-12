"""Auth probe from container network (Phase 7)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def _is_negative_ok(status: int) -> bool:
    if status in (401, 403):
        return True
    if 300 <= status < 400:
        return True
    return False


def _status_class(status: int | None) -> str:
    if status is None:
        return "none"
    if 200 <= status < 300:
        return "2xx"
    if 300 <= status < 400:
        return "3xx"
    if status in (401, 403):
        return "auth"
    if 400 <= status < 500:
        return "4xx"
    if 500 <= status < 600:
        return "5xx"
    return str(status)


def detect_login_routes(repo: Path) -> list[str]:
    """Best-effort login-like route evidence (no shell)."""
    hits: list[str] = []
    patterns = ("/login", "/token", "/auth", "password", "access_token")
    try:
        for path in repo.rglob("*.py"):
            if ".venv" in path.parts or ".git" in path.parts:
                continue
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")[:100_000]
            except OSError:
                continue
            low = text.lower()
            for pat in patterns:
                if pat in low:
                    hits.append(f"{path.relative_to(repo)}:{pat}")
                    break
            if len(hits) >= 10:
                break
    except (OSError, ValueError):
        pass
    return hits


def probe_profile(
    *,
    network: str,
    service: str,
    port: int,
    profile_name: str,
    profile_cfg: dict[str, Any],
    credentials: dict[str, str],
    expected_meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Run positive then negative request. Returns dict with verified/limitation/blocker."""
    from loadline.adapters.runtime.docker_runner import docker_cmd, probe_image

    method = str(profile_cfg.get("method") or "POST").upper()
    path = str(profile_cfg.get("path") or "")
    encoding = str(profile_cfg.get("body_encoding") or "form")
    token_field = str(profile_cfg.get("token_field") or "access_token")
    verify_path = profile_cfg.get("verify")
    if not path:
        return {"verified": False, "limitation": "auth_unverified", "detail": "no login path"}
    url = f"http://{service}:{port}{path}"
    username = credentials.get("username") or ""
    password = credentials.get("password") or ""
    if encoding == "form":
        data = f"username={username}&password={password}"
        ctype = "application/x-www-form-urlencoded"
    else:
        data = json.dumps({"username": username, "password": password})
        ctype = "application/json"
    # Positive: login.
    proc = docker_cmd(
        [
            "run",
            "--rm",
            "--network",
            network,
            probe_image(),
            "curl",
            "-sS",
            "-o",
            "/tmp/body",
            "-w",
            "%{http_code}",
            "--max-time",
            "10",
            "-X",
            method,
            "-H",
            f"Content-Type: {ctype}",
            "-d",
            data,
            url,
        ],
        timeout=60,
    )
    try:
        positive_status = int((proc.stdout or "").strip().splitlines()[-1].strip())
    except (IndexError, ValueError):
        positive_status = 0
    if not (200 <= positive_status < 300):
        # Positive failed: check against expected meta.
        if expected_meta:
            exp_class = expected_meta.get("status_class")
            if exp_class and exp_class != _status_class(positive_status):
                return {
                    "verified": False,
                    "blocker": {
                        "code": "auth_failed",
                        "summary": f"auth probe positive {positive_status} disagrees with recorded {exp_class}",
                        "retryable": False,
                        "security": False,
                        "user_can_provide": [],
                        "remediation": [],
                    },
                }
        return {
            "verified": False,
            "blocker": {
                "code": "auth_failed",
                "summary": f"auth probe login failed: {positive_status}",
                "retryable": False,
                "security": False,
                "user_can_provide": [],
                "remediation": [],
            },
        }
    # Verify path handling.
    if not verify_path:
        return {"verified": False, "limitation": "auth_unverified", "positive_status": positive_status}
    verify_url = f"http://{service}:{port}{verify_path}"
    # Negative: same verify without token.
    neg = docker_cmd(
        [
            "run",
            "--rm",
            "--network",
            network,
            probe_image(),
            "curl",
            "-sS",
            "-o",
            "/dev/null",
            "-w",
            "%{http_code}",
            "--max-time",
            "10",
            verify_url,
        ],
        timeout=60,
    )
    try:
        negative_status = int((neg.stdout or "").strip().splitlines()[-1].strip())
    except (IndexError, ValueError):
        negative_status = 0
    if _is_negative_ok(negative_status):
        result: dict[str, Any] = {"verified": True, "positive_status": positive_status, "negative_status": negative_status}
        if expected_meta:
            exp_class = expected_meta.get("status_class")
            if exp_class and exp_class != _status_class(positive_status):
                result = {
                    "verified": False,
                    "blocker": {
                        "code": "auth_failed",
                        "summary": f"auth probe status class changed: {positive_status} vs {exp_class}",
                        "retryable": False,
                        "security": False,
                        "user_can_provide": [],
                        "remediation": [],
                    },
                }
        return result
    # Negative returned 200 → warning, not verified.
    return {
        "verified": False,
        "warning": f"negative probe returned {negative_status}, expected 401/403/3xx",
        "positive_status": positive_status,
        "negative_status": negative_status,
    }
