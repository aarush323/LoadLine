"""Shared boot readiness: budget, HTTP wait, evidence, compose-up classification."""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Literal

READINESS_SLACK_S = 15.0
READINESS_CAP_S = 180.0
READINESS_MIN_S = 30.0
HEALTH_POLL_S = 2.0
NO_HEALTHCHECK_SLICE_S = 15.0
DOCKERFILE_DEFAULT_BUDGET_S = 60.0
COMPOSE_UP_TRANSIENT_ATTEMPTS = 3
COMPOSE_UP_BACKOFF_S = 5.0

_DURATION_RE = re.compile(r"^(?P<num>\d+(?:\.\d+)?)(?P<unit>s|m|h)?$", re.I)
_USERINFO_RE = re.compile(r"([a-z][a-z0-9+.-]*://)([^/\s@]+)@", re.I)
_BEARER_RE = re.compile(r"Bearer\s+\S+", re.I)

FailureClass = Literal["transient", "deterministic"]

# Config and build mistakes. Checked before pull/network flakes so a build log
# that merely mentions a timeout is not retried.
_DETERMINISTIC_MARKERS = (
    "variable is not set",
    "missing a value",
    "required variable",
    "invalid interpolation",
    "yaml:",
    "parse error",
    "unknown flag",
    "unknown shorthand",
    "undefined service",
    "is not defined",
    "permission denied",
    "policy refused",
    "invalid compose",
)

_TRANSIENT_MARKERS = (
    "i/o timeout",
    "tls handshake timeout",
    "context deadline exceeded",
    "client.timeout exceeded",
    "connection reset",
    "network is unreachable",
    "temporary failure",
    "toomanyrequests",
    "error pulling",
    "failed to pull",
    "dial tcp",
    "unexpected eof",
    "request canceled",
    "failed to resolve",
    "no such host",
    "registry-1.docker.io",
)

_BUILD_MARKERS = (
    "failed to solve",
    "error building",
    "the dockerfile",
    "executor failed",
)


def duration_seconds(value: Any) -> float:
    if value is None:
        return 0.0
    if isinstance(value, bool):
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    match = _DURATION_RE.match(text)
    if not match:
        return 0.0
    num = float(match.group("num"))
    unit = (match.group("unit") or "s").lower()
    if unit == "m":
        return num * 60.0
    if unit == "h":
        return num * 3600.0
    return num


def depends_on_service_names(svc: dict[str, Any]) -> list[str]:
    depends_on = svc.get("depends_on")
    if depends_on is None:
        return []
    if isinstance(depends_on, list):
        return [str(name) for name in depends_on]
    if isinstance(depends_on, dict):
        return [str(name) for name in depends_on]
    return []


def depends_on_closure(plan: dict[str, Any], app_service: str) -> list[str]:
    """App service, then transitive depends_on names. Conditions are ignored."""
    services = plan.get("services") or {}
    if not isinstance(services, dict):
        return [app_service]
    seen: list[str] = []
    queue = [app_service]
    while queue:
        name = queue.pop(0)
        if name in seen:
            continue
        seen.append(name)
        spec = services.get(name)
        if isinstance(spec, dict):
            for dep in depends_on_service_names(spec):
                if dep not in seen:
                    queue.append(dep)
    return seen


def direct_depends_on(plan: dict[str, Any], app_service: str) -> list[str]:
    services = plan.get("services") or {}
    spec = services.get(app_service) if isinstance(services, dict) else None
    if not isinstance(spec, dict):
        return []
    return depends_on_service_names(spec)


def _positive_seconds(value: Any, default: float) -> float:
    seconds = duration_seconds(value)
    if seconds <= 0:
        return default
    return seconds


def healthcheck_budget_s(svc: dict[str, Any]) -> float:
    """start_period + (interval + timeout) × retries. No healthcheck → 15s."""
    hc = svc.get("healthcheck")
    if not hc or not isinstance(hc, dict):
        return NO_HEALTHCHECK_SLICE_S
    start = duration_seconds(hc.get("start_period", 0))
    interval = _positive_seconds(hc.get("interval", "5s"), 5.0)
    if "timeout" in hc:
        timeout = duration_seconds(hc.get("timeout"))
        if timeout < 0:
            timeout = 5.0
    else:
        timeout = 5.0
    try:
        retries = int(hc.get("retries", 3))
    except (TypeError, ValueError):
        retries = 3
    if retries < 0:
        retries = 3
    return start + (interval + timeout) * retries


def compute_readiness_budget_s(plan: dict[str, Any], app_service: str) -> float:
    services = plan.get("services") or {}
    if not isinstance(services, dict):
        return READINESS_MIN_S
    names = depends_on_closure(plan, app_service)
    budgets: list[float] = []
    for name in names:
        spec = services.get(name)
        if isinstance(spec, dict):
            budgets.append(healthcheck_budget_s(spec))
        else:
            budgets.append(healthcheck_budget_s({}))
    base = max(budgets) if budgets else healthcheck_budget_s({})
    total = base + READINESS_SLACK_S
    return min(READINESS_CAP_S, max(READINESS_MIN_S, total))


def dockerfile_readiness_budget_s() -> float:
    return min(READINESS_CAP_S, max(READINESS_MIN_S, DOCKERFILE_DEFAULT_BUDGET_S))


@dataclass(frozen=True)
class ProbeResult:
    ok: bool
    exit_code: int
    http_code: int | None = None
    detail: str = ""


@dataclass(frozen=True)
class HealthWaitResult:
    ready: bool
    elapsed_s: float
    budget_s: float
    polls: int
    last_probe: ProbeResult | None


_LOG_ERROR_MARKERS = (
    "validationerror",
    "valueerror",
    "pydantic",
    "field required",
    "changethis",
    "error:",
    "exception",
)


_COMPOSE_UP_ERROR_MARKERS = ("error", "failed", "conflict", "fatal", "denied")


def excerpt_compose_up_output(text: str, *, max_chars: int = 800) -> str:
    """Prefer error-bearing lines from compose up; otherwise the last lines."""
    raw = (text or "").strip()
    if not raw:
        return ""
    lines = raw.splitlines()
    hits: list[str] = []
    seen: set[str] = set()
    for ln in lines:
        low = ln.lower()
        if any(marker in low for marker in _COMPOSE_UP_ERROR_MARKERS) and ln not in seen:
            hits.append(ln)
            seen.add(ln)
    if hits:
        return "\n".join(hits)[:max_chars]
    return "\n".join(lines[-12:])[:max_chars]


def excerpt_boot_log(text: str, *, tail_lines: int = 12, max_chars: int = 3000) -> str:
    """Prefer error-bearing lines from a long traceback; otherwise keep a short tail."""
    raw = (text or "").strip()
    if not raw:
        return ""
    lines = raw.splitlines()
    hits = [ln for ln in lines if any(marker in ln.lower() for marker in _LOG_ERROR_MARKERS)]
    if hits:
        seen: set[str] = set()
        picked: list[str] = []
        for ln in hits:
            if ln in seen:
                continue
            seen.add(ln)
            picked.append(ln)
        tail = lines[-tail_lines:] if len(lines) > tail_lines else lines
        for ln in tail:
            if ln not in seen:
                picked.append(ln)
                seen.add(ln)
        return "\n".join(picked)[:max_chars]
    tail = "\n".join(lines[-40:])
    return tail[:max_chars]


def log_has_boot_error(text: str) -> bool:
    lower = (text or "").lower()
    return any(marker in lower for marker in _LOG_ERROR_MARKERS)


def wait_until_http_ready(
    probe: Callable[[], ProbeResult],
    budget_s: float,
    *,
    poll_s: float = HEALTH_POLL_S,
    monotonic: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
    on_poll: Callable[[float, float], None] | None = None,
    abort_check: Callable[[], bool] | None = None,
) -> HealthWaitResult:
    """Poll until HTTP 2xx or the budget elapses. Non-2xx stays inside the window."""
    start = monotonic()
    deadline = start + budget_s
    polls = 0
    last: ProbeResult | None = None
    while monotonic() < deadline:
        if abort_check is not None and abort_check():
            break
        polls += 1
        last = probe()
        if last.ok:
            return HealthWaitResult(
                ready=True,
                elapsed_s=monotonic() - start,
                budget_s=budget_s,
                polls=polls,
                last_probe=last,
            )
        now = monotonic()
        if on_poll is not None:
            on_poll(now - start, budget_s)
        remaining = deadline - monotonic()
        if remaining <= 0:
            break
        sleep(min(poll_s, remaining))
    return HealthWaitResult(
        ready=False,
        elapsed_s=monotonic() - start,
        budget_s=budget_s,
        polls=polls,
        last_probe=last,
    )


def classify_compose_up_failure(stderr: str) -> FailureClass:
    text = (stderr or "").lower()
    if any(marker in text for marker in _DETERMINISTIC_MARKERS):
        return "deterministic"
    if any(marker in text for marker in _TRANSIENT_MARKERS):
        return "transient"
    if any(marker in text for marker in _BUILD_MARKERS):
        return "deterministic"
    return "deterministic"


@dataclass(frozen=True)
class ComposeUpFailure:
    n: int
    output: str
    failure_class: FailureClass


def compose_up_with_retries(
    run_up: Callable[[], Any],
    *,
    max_attempts: int = COMPOSE_UP_TRANSIENT_ATTEMPTS,
    backoff_s: float = COMPOSE_UP_BACKOFF_S,
    sleep: Callable[[float], None] = time.sleep,
) -> tuple[Any, list[ComposeUpFailure]]:
    """Run compose up. Transient failures retry on the same plan; deterministic ones do not."""
    failures: list[ComposeUpFailure] = []
    last: Any = None
    attempts = max(1, max_attempts)
    for n in range(1, attempts + 1):
        last = run_up()
        returncode = int(getattr(last, "returncode", 1))
        if returncode == 0:
            return last, failures
        output = str(getattr(last, "stderr", None) or getattr(last, "stdout", None) or "")
        klass = classify_compose_up_failure(output)
        failures.append(ComposeUpFailure(n=n, output=output, failure_class=klass))
        if klass != "transient" or n >= attempts:
            return last, failures
        sleep(backoff_s)
    return last, failures


def redact_evidence_text(text: str) -> str:
    redacted = _BEARER_RE.sub("Bearer [redacted]", text or "")
    return _USERINFO_RE.sub(r"\1[redacted]@", redacted)


@dataclass
class BootEvidence:
    health_url: str
    budget_s: float
    elapsed_s: float
    ps_text: str = ""
    ps_heading: str = "compose ps"
    logs: dict[str, str] = field(default_factory=dict)
    last_probe: ProbeResult | None = None

    def first_line(self) -> str:
        line = (
            f"health {self.health_url} budget={self.budget_s:.0f}s elapsed={self.elapsed_s:.0f}s"
        )
        if self.last_probe is not None:
            line += f" probe_exit={self.last_probe.exit_code}"
            if self.last_probe.http_code is not None:
                line += f" http={self.last_probe.http_code}"
        return line

    def summary_text(self) -> str:
        lines = [self.first_line()]
        if self.ps_text:
            lines.append(f"{self.ps_heading}:")
            lines.append(self.ps_text[:2000])
        items = list(self.logs.items())
        app_name = items[0][0] if items else None
        app_has_error = bool(items) and log_has_boot_error(items[0][1])
        for name, text in items:
            if not text:
                continue
            if app_has_error and name != app_name:
                continue
            lines.append(f"logs {name}:")
            lines.append(excerpt_boot_log(text))
        return redact_evidence_text("\n".join(lines))[:8000]

    def as_dict(self) -> dict[str, Any]:
        probe: dict[str, Any] | None = None
        if self.last_probe is not None:
            probe = {
                "ok": self.last_probe.ok,
                "exit_code": self.last_probe.exit_code,
                "http_code": self.last_probe.http_code,
                "detail": redact_evidence_text(self.last_probe.detail)[:500],
            }
        return {
            "health_url": self.health_url,
            "budget_s": self.budget_s,
            "elapsed_s": self.elapsed_s,
            "ps": redact_evidence_text(self.ps_text)[:2000],
            "logs": {
                name: redact_evidence_text(excerpt_boot_log(text))[:3000]
                for name, text in self.logs.items()
            },
            "last_probe": probe,
        }


def health_timeout_blocker(evidence: BootEvidence) -> dict[str, Any]:
    return {
        "code": "health_timeout",
        "summary": evidence.summary_text(),
        "evidence": evidence.as_dict(),
        "retryable": True,
        "security": False,
        "user_can_provide": [],
        "remediation": [],
    }
