"""Model and API-key preflight (tech_doc.md §16.4)."""

from __future__ import annotations

import os
from dataclasses import dataclass

@dataclass(frozen=True)
class AuthPreflightError:
    message: str
    env_var: str


def _model_spec() -> tuple[str, str] | AuthPreflightError:
    model = os.environ.get("LOADLINE_MODEL", "").strip()
    if not model:
        return AuthPreflightError(
            "LOADLINE_MODEL is not set.",
            "LOADLINE_MODEL",
        )
    if ":" not in model:
        return AuthPreflightError(
            "LOADLINE_MODEL must be provider:model-id (e.g. openrouter:deepseek/deepseek-v4.1-flash).",
            "LOADLINE_MODEL",
        )
    provider, _model_id = model.split(":", 1)
    provider = provider.lower()
    if provider == "openai":
        return ("OPENAI_API_KEY", model)
    if provider == "anthropic":
        return ("ANTHROPIC_API_KEY", model)
    if provider == "openrouter":
        return ("OPENROUTER_API_KEY", model)
    return AuthPreflightError(
        f"Unsupported provider prefix '{provider}' in LOADLINE_MODEL.",
        "LOADLINE_MODEL",
    )


def require_model_auth() -> AuthPreflightError | None:
    spec = _model_spec()
    if isinstance(spec, AuthPreflightError):
        return spec
    env_var, _model = spec
    if not os.environ.get(env_var, "").strip():
        return AuthPreflightError(
            f"{env_var} is not set (required for {os.environ.get('LOADLINE_MODEL', '')}).",
            env_var,
        )
    return None
