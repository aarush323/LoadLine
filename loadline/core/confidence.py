"""Finding confidence from S,M,X,K,R,V booleans (tech_doc.md §12.2). V is always false in v1."""

from __future__ import annotations


def confidence(s: bool, m: bool, x: bool, k: bool, r: bool, v: bool) -> float:
    if not s:
        return 0.0
    c = 0.40
    if m:
        c = 0.50
    if m and x:
        c = 0.65
    if m and x and k:
        c = 0.85
    if not r:
        c = min(c, 0.65)
    if v and m and x and k and r:
        c = 0.95
    return c
