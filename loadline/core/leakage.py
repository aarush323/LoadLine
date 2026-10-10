"""test_no_fixture_leakage scanner (tech_doc.md §18.4)."""

from __future__ import annotations

from pathlib import Path


def _forbidden_tokens(repo_root: Path) -> tuple[str, ...]:
    path = repo_root / "tests" / "data" / "forbidden_tokens.txt"
    if not path.is_file():
        return ()
    return tuple(line.strip() for line in path.read_text().splitlines() if line.strip())


def scan_loadline_package(root: Path) -> list[str]:
    loadline = root / "loadline"
    tokens = _forbidden_tokens(root)
    hits: list[str] = []
    for path in loadline.rglob("*"):
        if path.suffix not in {".py", ".md"}:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        for token in tokens:
            if token in text:
                hits.append(f"{path.relative_to(root)}: contains {token!r}")
    inv = root / "agents" / "investigator_prompt.md"
    if inv.is_file():
        text = inv.read_text(encoding="utf-8", errors="ignore")
        for token in tokens:
            if token in text:
                hits.append(f"agents/investigator_prompt.md: contains {token!r}")
    return hits
