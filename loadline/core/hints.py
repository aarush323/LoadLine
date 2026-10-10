"""Strict .loadline.yaml parser (tech_doc.md §16.3). Phase 1: delegates to config schema."""

from __future__ import annotations

from loadline.config.schema import ALLOWED_KEYS, EXTENDED_ALLOWED_KEYS, LoadlineHints, load_hints

__all__ = ["ALLOWED_KEYS", "EXTENDED_ALLOWED_KEYS", "LoadlineHints", "load_hints"]
