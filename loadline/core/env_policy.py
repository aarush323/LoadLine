"""SandboxPolicy rule 7 — env URLs and credentials (tech_doc.md §7.4, §7.6)."""

from __future__ import annotations

import re
import secrets
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from loadline.core.target_guard import classify_url

_COMPOSE_ENV_REF = re.compile(
    r"^\$\{([^}:]+)(?::-(?P<default>[^}]*))?(?::\?(?P<err>[^}]*))?\}$"
)
_COMPOSE_ENV_INLINE = re.compile(
    r"\$\{([^}:]+)(?::-(?P<default>[^}]*))?(?::\?(?P<err>[^}]*))?\}"
)

_LITERAL_SECRET_PREFIXES = (
    "sk_live_",
    "sk_test_",
    "sk-live-",
    "sk-test-",
    "ghp_",
    "gho_",
    "github_pat_",
    "xoxb-",
    "xoxp-",
    "xoxa-",
    "AKIA",
    "rk_live_",
    "rk_test_",
)

_PLACEHOLDER_SECRETS = frozenset(
    {
        "",
        "changethis",
        "change-me",
        "changeme",
        "password",
        "secret",
        "replace-me",
        "your-secret",
        "todo",
        "example",
        "xxx",
    }
)

_THIRD_PARTY_KEY_EXACT = frozenset({"SENTRY_DSN"})
_THIRD_PARTY_KEY_PREFIXES = ("STRIPE_", "OPENAI_", "AWS_", "GITHUB_", "TWILIO_", "SENDGRID_")

_LOCAL_SECRET_KEY_RE = re.compile(r"(SECRET|PASSWORD|TOKEN|_KEY$)", re.I)

# Kafka and similar: listener maps are config, not credentials.
_BROKER_LISTENER_SCHEME = re.compile(
    r"(?:^|[,\s])(?:PLAINTEXT|SSL|SASL_SSL|SASL_PLAINTEXT)://",
    re.I,
)


@dataclass(frozen=True)
class EnvPolicyOutcome:
    env: dict[str, str]
    needs_input: bool = False
    needs_input_summary: str | None = None
    replacements: list[tuple[str, str, str]] = ()  # key, before, after
    generated_secrets: list[str] = ()
    limitations: tuple[str, ...] = ()


def _parse_env(env: Any) -> dict[str, str]:
    if isinstance(env, dict):
        return {str(k): str(v) for k, v in env.items()}
    if isinstance(env, list):
        out: dict[str, str] = {}
        for item in env:
            if isinstance(item, str) and "=" in item:
                key, val = item.split("=", 1)
                out[key] = val
        return out
    return {}


def load_repo_dotenv(repo: Path) -> dict[str, str]:
    """Load target-repo `.env` only. Never reads the host process environment."""
    path = repo / ".env"
    if not path.is_file():
        return {}
    return parse_dotenv_text(path.read_text())


def parse_dotenv_text(text: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if "=" not in stripped:
            continue
        key, val = stripped.split("=", 1)
        key = key.strip()
        val = val.strip()
        if len(val) >= 2 and val[0] == val[-1] and val[0] in "\"'":
            val = val[1:-1]
        out[key] = val
    return out


def _is_compose_reference(value: str) -> bool:
    return _COMPOSE_ENV_REF.match(value.strip()) is not None


def _is_url_value(value: str) -> bool:
    return value.startswith("http://") or value.startswith("https://")


def _is_third_party_env_key(name: str) -> bool:
    upper = name.upper()
    if upper in _THIRD_PARTY_KEY_EXACT:
        return True
    return any(upper.startswith(prefix) for prefix in _THIRD_PARTY_KEY_PREFIXES)


def _is_local_secret_key(name: str) -> bool:
    if _is_third_party_env_key(name):
        return False
    return bool(_LOCAL_SECRET_KEY_RE.search(name))


def is_placeholder_secret(value: str) -> bool:
    return value.strip().lower() in _PLACEHOLDER_SECRETS


def _var_names_in_value(value: str) -> list[str]:
    return [m.group(1) for m in _COMPOSE_ENV_INLINE.finditer(value)]


def _lookup_var(name: str, effective: dict[str, str], *, default: str | None, required: bool) -> tuple[str, bool]:
    """Return (value, needs_input)."""
    if name in effective and effective[name].strip():
        return effective[name], False
    if default is not None:
        return default, False
    if required:
        if _is_third_party_env_key(name):
            return "", True
        if _is_local_secret_key(name):
            return effective.get(name, ""), False
        return "", True
    return effective.get(name, ""), False


def _interpolate_value(value: str, effective: dict[str, str]) -> tuple[str, bool, str | None]:
    if _COMPOSE_ENV_REF.match(value.strip()):
        match = _COMPOSE_ENV_REF.match(value.strip())
        assert match is not None
        name = match.group(1)
        default = match.group("default")
        required = match.group("err") is not None
        resolved, needs = _lookup_var(name, effective, default=default, required=required)
        if needs:
            return "", True, f"environment variable {name} requires user input"
        return resolved, False, None

    needs_input = False
    summary: str | None = None

    def repl(match: re.Match[str]) -> str:
        nonlocal needs_input, summary
        name = match.group(1)
        default = match.group("default")
        required = match.group("err") is not None
        resolved, needs = _lookup_var(name, effective, default=default, required=required)
        if needs:
            needs_input = True
            summary = f"environment variable {name} requires user input"
            return ""
        return resolved

    out = _COMPOSE_ENV_INLINE.sub(repl, value)
    return out, needs_input, summary


def _is_broker_listener_config(key: str, value: str) -> bool:
    upper = key.upper()
    if "LISTENER" in upper or "ADVERTISED" in upper:
        return True
    return bool(_BROKER_LISTENER_SCHEME.search(value))


def _looks_like_literal_credential(value: str) -> bool:
    text = value.strip()
    if not text or _is_compose_reference(text):
        return False
    if _is_url_value(text):
        return False
    if _BROKER_LISTENER_SCHEME.search(text):
        return False
    if text.startswith(("postgresql://", "postgres://", "mysql://", "redis://", "amqp://")):
        return False
    for prefix in _LITERAL_SECRET_PREFIXES:
        if text.startswith(prefix):
            return True
    if len(text) < 16:
        return False
    has_upper = any(c.isupper() for c in text)
    has_lower = any(c.islower() for c in text)
    has_digit = any(c.isdigit() for c in text)
    return has_upper and has_lower and has_digit


def _rewrite_url_value(value: str) -> tuple[str, bool]:
    """Return (new_value, changed). External production URLs become sandbox placeholders."""
    ref = classify_url(value)
    if ref.kind == "external":
        return f"http://sandbox.invalid/{secrets.token_urlsafe(8)}", True
    parsed = urlparse(value)
    host = (parsed.hostname or "").lower()
    if host in ("localhost", "127.0.0.1"):
        return f"http://sandbox.invalid/{secrets.token_urlsafe(8)}", True
    return value, False


def _ensure_generated_for_placeholders(
    parsed: dict[str, str], dotenv: dict[str, str], generated: dict[str, str]
) -> list[str]:
    created: list[str] = []
    names: set[str] = set()
    for raw in parsed.values():
        names.update(_var_names_in_value(raw))
    names.update(parsed.keys())

    for name in names:
        if not _is_local_secret_key(name):
            continue
        dotenv_val = dotenv.get(name, "")
        if name in generated:
            continue
        if is_placeholder_secret(dotenv_val):
            generated[name] = secrets.token_urlsafe(32)
            created.append(name)
    for key, raw in parsed.items():
        if not _is_local_secret_key(key):
            continue
        interim, _, _ = _interpolate_value(raw, {**dotenv, **generated})
        if is_placeholder_secret(interim) and key not in generated:
            generated[key] = secrets.token_urlsafe(32)
            created.append(key)
    return created


def apply_env_policy(
    env: Any,
    *,
    repo_dotenv: dict[str, str] | None = None,
    generated: dict[str, str] | None = None,
    placeholders: dict[str, Any] | set[str] | list[str] | None = None,
) -> EnvPolicyOutcome:
    # New placeholder shape: env value may be {"placeholder": True} (from yaml).
    # Collect placeholder keys without breaking old string shape.
    placeholder_keys: set[str] = set()
    if isinstance(placeholders, dict):
        for k, v in placeholders.items():
            if isinstance(v, dict) and v.get("placeholder"):
                placeholder_keys.add(str(k))
            elif v is True:
                placeholder_keys.add(str(k))
    elif isinstance(placeholders, (set, list, tuple)):
        placeholder_keys.update(str(k) for k in placeholders)
    raw_env_dict = env if isinstance(env, dict) else {}
    for k, v in (raw_env_dict.items() if isinstance(raw_env_dict, dict) else []):
        if isinstance(v, dict) and v.get("placeholder"):
            placeholder_keys.add(str(k))
    parsed = _parse_env(env)
    # _parse_env stringifies dict values; restore placeholder markers as empty for now.
    for k in list(placeholder_keys):
        if k in parsed:
            parsed[k] = ""
    if not parsed and not placeholder_keys:
        return EnvPolicyOutcome(env={})

    dotenv = dict(repo_dotenv or {})
    gen_store = generated if generated is not None else {}
    generated_keys = _ensure_generated_for_placeholders(parsed, dotenv, gen_store)
    effective = {**dotenv, **gen_store}

    out: dict[str, str] = {}
    replacements: list[tuple[str, str, str]] = []
    limitations: list[str] = []
    needs_input = False
    needs_summary: str | None = None

    for key, raw in parsed.items():
        if key in placeholder_keys:
            # Placeholder: non-empty in-memory value, limitation, no stub word.
            out[key] = f"placeholder-{key}-value"
            limitations.append(f"dependency not replaced: {key}")
            continue
        before = raw
        resolved, need, msg = _interpolate_value(raw, effective)
        if need:
            needs_input = True
            needs_summary = msg or needs_summary

        if _is_third_party_env_key(key) or key.upper() == "SMTP_PASSWORD":
            if _looks_like_literal_credential(resolved) or any(
                resolved.startswith(p) for p in _LITERAL_SECRET_PREFIXES
            ):
                if resolved:
                    replacements.append((key, resolved, ""))
                resolved = ""
            elif resolved and not is_placeholder_secret(resolved):
                replacements.append((key, resolved, ""))
                resolved = ""

        if _is_url_value(resolved):
            rewritten, changed = _rewrite_url_value(resolved)
            if changed:
                replacements.append((key, resolved, rewritten))
            resolved = rewritten

        if (
            not _is_broker_listener_config(key, resolved)
            and not _is_local_secret_key(key)
            and not _is_third_party_env_key(key)
            and _looks_like_literal_credential(resolved)
        ):
            replacements.append((key, resolved, ""))
            resolved = ""

        if resolved != before:
            replacements.append((key, before, resolved))
        out[key] = resolved

    # Ensure placeholder keys absent from parsed (e.g. empty env) still get values.
    for key in placeholder_keys:
        if key not in out:
            out[key] = f"placeholder-{key}-value"
            limitations.append(f"dependency not replaced: {key}")

    return EnvPolicyOutcome(
        env=out,
        needs_input=needs_input,
        needs_input_summary=needs_summary,
        replacements=replacements,
        generated_secrets=generated_keys,
        limitations=tuple(limitations),
    )
