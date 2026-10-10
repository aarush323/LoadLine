"""TargetGuard — sandbox-only URLs (tech_doc.md §7.6)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal
from urllib.parse import urlparse

RefKind = Literal["in_sandbox", "local_dev", "external"]

_PROD_HOST_RE = re.compile(
    r"(amazonaws\.com|azure\.com|googleapis\.com|\.prod\.|production\.)",
    re.I,
)


@dataclass(frozen=True)
class ExternalRef:
    raw: str
    kind: RefKind
    host: str


@dataclass(frozen=True)
class TargetGuardError:
    message: str


def classify_url(url: str) -> ExternalRef:
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if not host:
        return ExternalRef(url, "external", "")
    if host in ("localhost", "127.0.0.1", "0.0.0.0"):
        return ExternalRef(url, "local_dev", host)
    if _PROD_HOST_RE.search(host):
        return ExternalRef(url, "external", host)
    return ExternalRef(url, "in_sandbox", host)


def assert_sandbox_target(url: str, allowed_hosts: frozenset[str]) -> TargetGuardError | None:
    ref = classify_url(url)
    if ref.kind == "external":
        return TargetGuardError(f"external URL refused: {url}")
    if ref.kind == "local_dev":
        return TargetGuardError(f"loopback URL refused: {url}")
    host = (urlparse(url).hostname or "").lower()
    if host not in allowed_hosts:
        return TargetGuardError(f"host {host} is not a service of this run")
    return None
