"""Secret-shaped value redaction for plans and logs."""

from __future__ import annotations

import re

REDACTED = "[redacted]"

_SECRET_KEY_RE = re.compile(
    r"(password|passwd|secret|token|api[_-]?key|authorization|credential|private[_-]?key)",
    re.I,
)
_BEARER_RE = re.compile(r"Bearer\s+[A-Za-z0-9._\-+/=]+", re.I)
_ENV_SECRET_RE = re.compile(r"^[A-Za-z0-9_]{16,}$")


def is_secret_key(name: str) -> bool:
    return bool(_SECRET_KEY_RE.search(name))


_CONN_RE = re.compile(r"^[a-z][a-z0-9+.-]*://[^/]*@", re.I)


def redact_value(key: str, value: str) -> str:
    if is_secret_key(key):
        return REDACTED
    if _CONN_RE.match(value):
        return REDACTED
    if _BEARER_RE.search(value):
        return REDACTED
    if key.upper().endswith("_KEY") and _ENV_SECRET_RE.match(value):
        return REDACTED
    return value


def redact_env(env: dict[str, str]) -> dict[str, str]:
    return {k: redact_value(k, v) for k, v in env.items()}
