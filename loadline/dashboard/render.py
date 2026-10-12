"""Render the web dashboard from run artifacts (read-only, never writes runs).

Single-file HTML out: the v3 mock's CSS/JS with every illustrative value
replaced by measured run evidence. Gaps render as "Not measured".
"""

from __future__ import annotations

import html
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_DIR = Path(__file__).resolve().parent


def esc(text: Any) -> str:
    return html.escape(str(text if text is not None else ""), quote=True)


def _ms(value: Any) -> str:
    try:
        return f"{int(round(float(value)))} ms"
    except (TypeError, ValueError):
        return "Not measured"


def _rps(value: Any) -> str:
    try:
        return f"{float(value):g} req/s"
    except (TypeError, ValueError):
        return "Not measured"


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def _parse_ts(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _fmt_date(dt: datetime | None) -> str:
    return dt.strftime("%d %b %Y, %H:%M UTC") if dt else "date not recorded"


def _fmt_time(dt: datetime | None) -> str:
    return dt.strftime("%H:%M:%S") if dt else "—"


def _ledger_events(run_dir: Path) -> list[dict[str, Any]]:
    try:
        lines = (run_dir / "ledger.jsonl").read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    out: list[dict[str, Any]] = []
    for line in lines:
        if not line.strip():
            continue
        try:
            ev = json.loads(line)
        except ValueError:
            continue
        if isinstance(ev, dict):
            out.append(ev)
    return out


def _waves(ledger: list[dict[str, Any]]) -> list[dict[str, Any]]:
    waves = [e for e in ledger if e.get("kind") == "k6_run" and isinstance(e.get("result"), dict)]
    waves.sort(key=lambda e: float((e.get("result") or {}).get("offered_rps") or 0.0))
    return waves


def _op_plans(ledger: list[dict[str, Any]]) -> dict[str, dict[str, str]]:
    """op id -> {method, path} from the persisted k6 plans (latest wins)."""
    out: dict[str, dict[str, str]] = {}
    for e in ledger:
        if e.get("kind") != "k6_run":
            continue
        plan = e.get("plan") if isinstance(e.get("plan"), dict) else {}
        mix = plan.get("mix") if isinstance(plan, dict) else None
        if not isinstance(mix, list):
            continue
        for item in mix:
            op = (item if isinstance(item, dict) else {}).get("op") if isinstance(item, dict) else None
            if not isinstance(op, dict):
                continue
            op_id = str(op.get("id") or "").strip()
            if not op_id:
                continue
            sel = op.get("selector") if isinstance(op.get("selector"), dict) else {}
            out[op_id] = {
                "method": str(sel.get("method") or "GET").upper(),
                "path": str(sel.get("path") or op_id),
            }
    return out


def _nice_ceil(value: float) -> float:
    if value <= 0:
        return 1.0
    import math

    exp = math.floor(math.log10(value))
    for mult in (1, 2, 2.5, 5, 10):
        if value <= mult * (10**exp):
            return mult * (10**exp)
    return 10 * (10**exp)


# ---------------------------------------------------------------- charts ---


def _offered_chart(points: list[tuple[float, float]], peak: float) -> str:
    """points: (x, offered). Shared geometry with the v3 mock."""
    w, h = 1000, 110
    top, bottom, left, right = 20, 102, 70, 969
    ymax = _nice_ceil(max([p[1] for p in points] + [peak, 1.0]))
    n = len(points)

    def x(i: int) -> float:
        return left if n == 1 else left + (right - left) * i / (n - 1)

    def y(v: float) -> float:
        return top + (bottom - top) * (1 - v / ymax)

    grid = "".join(
        f'<line class="gridline" x1="{left}" y1="{gy}" x2="{right}" y2="{gy}"/>'
        for gy in (33, 56, 79)
    )
    ticks = "".join(
        f'<text x="56" y="{gy}" text-anchor="end">{lab}</text>'
        for gy, lab in (
            (36, f"{ymax:g}"),
            (59, f"{ymax * 0.66:g}"),
            (82, f"{ymax * 0.33:g}"),
            (101, "0"),
        )
    )
    d = " ".join(f"{'M' if i == 0 else 'L'}{x(i):.0f} {y(v):.0f}" for i, (_, v) in enumerate(points))
    dots = "".join(f'<circle cx="{x(i):.0f}" cy="{y(v):.0f}" r="3.5" fill="#3e4840" stroke="#fff" stroke-width="1.5"/>' for i, (_, v) in enumerate(points))
    labels = "".join(
        f'<text x="{x(i):.0f}" y="121" text-anchor="middle">{v:g}</text>'
        if (n <= 12 or i == 0 or i == n - 1 or i == n // 2)
        else ""
        for i, (_, v) in enumerate(points)
    )
    return (
        f'<svg class="chart-svg" viewBox="0 0 {w} {h + 22}" role="img" '
        f'aria-label="Offered load across {n} measured waves">'
        f'<text x="14" y="15" class="axis-label">OFFERED LOAD · REQ/S</text>'
        f"{grid}{ticks}"
        f'<path class="load" d="{d}"/>{dots}'
        f'<text x="70" y="121">offered req/s per wave</text>'
        f"{labels}</svg>"
    )


def _latency_chart(
    points: list[tuple[float, float, str, str]], op_label: str
) -> str:
    """points: (x, p95, exp_id, wave). No SLO line: runs record no threshold."""
    h = 132
    top, bottom, left, right = 22, 110, 70, 969
    vals = [p[1] for p in points]
    ymax = _nice_ceil(max(vals + [1.0]))
    n = len(points)

    def x(i: int) -> float:
        return left if n == 1 else left + (right - left) * i / (n - 1)

    def y(v: float) -> float:
        return top + (bottom - top) * (1 - v / ymax)

    grid = "".join(
        f'<line class="gridline" x1="{left}" y1="{gy}" x2="{right}" y2="{gy}"/>'
        for gy in (30, 55, 80, 105)
    )
    ticks = "".join(
        f'<text x="56" y="{gy}" text-anchor="end">{lab}</text>'
        for gy, lab in (
            (33, f"{ymax:g}"),
            (58, f"{ymax * 0.66:g}"),
            (83, f"{ymax * 0.33:g}"),
            (108, "0"),
        )
    )
    d = " ".join(f"{'M' if i == 0 else 'L'}{x(i):.0f} {y(v):.0f}" for i, (__, v, ___, ____) in enumerate(points))
    peak_i = max(range(n), key=lambda i: points[i][1])
    px, pv, pexp, _wave = points[peak_i][0], points[peak_i][1], points[peak_i][2], points[peak_i][3]
    dots = "".join(
        f'<circle class="point" cx="{x(i):.0f}" cy="{y(v):.0f}" r="4.5"/>' if i == peak_i
        else f'<circle cx="{x(i):.0f}" cy="{y(v):.0f}" r="3.5" fill="#b96648" stroke="#fff" stroke-width="1.5"/>'
        for i, (__, v, ___, ____) in enumerate(points)
    )
    bx = min(x(peak_i) + 15, 815)
    callout = (
        f'<rect class="label-box" x="{bx:.0f}" y="26" width="155" height="34" rx="5"/>'
        f'<text x="{bx + 10:.0f}" y="39" class="breach-text">HIGHEST MEASURED</text>'
        f'<text x="{bx + 10:.0f}" y="51">{esc(op_label)} · {esc(pexp)}</text>'
    )
    return (
        f'<svg class="chart-svg" viewBox="0 0 1000 {h}" role="img" '
        f'aria-label="p95 latency for {esc(op_label)} across {n} measured waves, no recorded SLO">'
        f'<text x="14" y="15" class="axis-label">P95 LATENCY · MS · {esc(op_label).upper()}</text>'
        f"{grid}{ticks}"
        f'<path class="latency" d="{d}"/>{dots}{callout}'
        f'<text x="70" y="126">SLO not recorded for this run — measured p95 only</text></svg>'
    )


# ----------------------------------------------------------------- graph ---


def _short_sym(symbol: str, limit: int = 24) -> str:
    symbol = symbol.strip()
    return symbol if len(symbol) <= limit else "…" + symbol[-(limit - 1):]


def build_graph(
    run_dir: Path,
    op_ids: list[str],
    op_labels: dict[str, dict[str, str]],
    worst_op: str | None,
    hypotheses: list[dict[str, Any]],
) -> dict[str, Any]:
    """Focused op→handler neighbourhood from Entire Graph; honest fallback."""
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, str]] = []
    node_data: dict[str, Any] = {}
    mapped = 0
    note = ""
    for i, op_id in enumerate(op_ids[:4]):
        info = op_labels.get(op_id, {"method": "GET", "path": op_id})
        nodes.append({"id": f"op_{i}", "kind": "op", "op": op_id, "label": f"{info['method']} {info['path']}"})
    if len(op_ids) > 4:
        note = f"+{len(op_ids) - 4} more operations (see evidence ledger)"
    # Real resolution happens below with the target repo, kept separate so a
    # graph failure degrades to measured-op nodes instead of breaking render.
    records: list[dict[str, Any]] = []
    graph_err = ""
    try:
        from loadline.entire_runtime.install import ensure_toolchain
        from loadline.entire_runtime.graph import GraphClient

        profile = _read_json(run_dir / "profile.json") or {}
        repo = str(profile.get("root") or "").strip()
        if not repo or not Path(repo).is_dir():
            raise RuntimeError("target repository is not available at render time")
        client = GraphClient(ensure_toolchain())
        caps = client.capabilities()
        relations = list(caps.get("supported_relation_types") or [])
        if "HANDLES_ROUTE" not in relations:
            raise RuntimeError("HANDLES_ROUTE absent from graph capabilities")
        out = client.run(["edges", "--repo", repo, "--format", "ndjson", "--relation", "HANDLES_ROUTE"])
        if not out.ok:
            raise RuntimeError("HANDLES_ROUTE export failed")
        records = [r for r in (out.records or []) if isinstance(r, dict)]
    except Exception as exc:
        graph_err = str(exc)[:140]

    handler_of: dict[str, dict[str, str]] = {}
    if records:
        for i, op_id in enumerate(op_ids[:4]):
            info = op_labels.get(op_id, {"method": "GET", "path": op_id})
            best: dict[str, Any] | None = None
            for rec in records:
                rp = rec.get("route") or rec.get("path") or rec.get("url_path") or ""
                if not isinstance(rp, str) or not rp.strip():
                    continue
                if _route_matches(str(rp), info["path"]):
                    best = rec
                    if str(rp).strip().rstrip("/") == info["path"].rstrip("/"):
                        break
            if best is not None:
                sym = str(best.get("symbol") or best.get("handler") or best.get("name") or "handler")
                fpath = best.get("file") or best.get("file_path") or ""
                line = best.get("line") or best.get("start_line") or ""
                loc = f"{fpath}:{line}" if fpath and line else (str(fpath) or "location not reported")
                handler_of[f"op_{i}"] = {"symbol": sym, "loc": loc}
                mapped += 1

    for op_node, h in handler_of.items():
        sym_id = f"sym_{op_node}"
        nodes.append({"id": sym_id, "kind": "sym", "label": _short_sym(h["symbol"]), "sub": h["loc"]})
        edges.append({"from": op_node, "to": sym_id, "cls": ""})
    for n, hyp in enumerate(hypotheses[:2]):
        hid = f"hyp_{n}"
        nodes.append({"id": hid, "kind": "hyp", "label": f"H-{n + 1:02d} · hypothesis"})
        shown = op_ids[:4]
        if worst_op is not None and worst_op in shown:
            edges.append({"from": hid, "to": f"op_{shown.index(worst_op)}", "cls": "hypothesis"})
    if graph_err and not records:
        meta = f"CODE MAP UNAVAILABLE · {esc(graph_err) if graph_err else 'graph unavailable'}"
        topline = "MAP UNAVAILABLE — MEASURED OPERATIONS ONLY"
        foot = "Static code relations could not be resolved for this run; pressure shown on measured operations only."
    else:
        meta = f"ENTIRE GRAPH · {mapped}/{min(len(op_ids), 4)} OPS MAPPED"
        topline = "MAP / ROUTE-TO-SYMBOL RELATIONS"
        foot = "Measured pressure on selected operation · Static edges ≠ runtime spans"
        if note:
            foot += f" · {note}"
    return {
        "nodes": nodes,
        "edges": edges,
        "handlers": handler_of,
        "mapped": mapped,
        "meta": meta,
        "topline": topline,
        "foot": foot,
        "unavailable": bool(graph_err and not records),
        "unavailable_reason": graph_err,
        "node_data": node_data,
    }


def _route_matches(record_path: str, op_path: str) -> bool:
    import re as _re

    rp = record_path.strip()
    op = op_path.strip()
    if rp.rstrip("/") == op.rstrip("/"):
        return True
    pattern = "^" + _re.escape(rp).replace(_re.escape("{"), "{").replace(_re.escape("}"), "}",) + "$"
    pattern = _re.sub(r"\{[^}]+\}", "[^/]+", pattern)
    try:
        return bool(_re.match(pattern, op))
    except _re.error:
        return False


def _graph_svg(
    graph: dict[str, Any],
    op_ids: list[str],
    op_labels: dict[str, dict[str, str]],
    op_p95: dict[str, float],
    exp_of: dict[str, str],
    worst_op: str | None,
    select_op: str | None = None,
) -> str:
    nodes = graph["nodes"]
    edges = graph["edges"]
    ops = [n for n in nodes if n["kind"] == "op"]
    syms = [n for n in nodes if n["kind"] == "sym"]
    hyps = [n for n in nodes if n["kind"] == "hyp"]
    row_h, x_op, x_sym = 86, 28, 300
    height = max(320, 40 + max(len(ops), len(syms), 1) * row_h + (len(hyps) * 52 if hyps else 0))
    worst_shown = worst_op in op_ids[:4]
    worst_nid = f"op_{op_ids[:4].index(worst_op)}" if worst_shown else ""
    pos: dict[str, tuple[float, float]] = {}
    for i, n in enumerate(ops):
        pos[n["id"]] = (x_op, 44 + i * row_h)
    sym_of = {e["from"]: e["to"] for e in edges if e["to"].startswith("sym_")}
    for i, n in enumerate(syms):
        pos[n["id"]] = (x_sym, 44 + i * row_h)
    hy = 44 + max(len(ops), len(syms), 1) * row_h + 6
    for k, n in enumerate(hyps):
        pos[n["id"]] = (x_sym, hy + k * 52)

    def _w(label: str) -> float:
        return max(118.0, len(label) * 6.4 + 26)

    parts = [
        f'<svg id="main-graph" class="graph-svg" viewBox="0 0 700 {height}" role="img" '
        f'aria-label="Measured operations overlaid on resolved code relations">'
    ]
    for e in edges:
        if e["from"] not in pos or e["to"] not in pos:
            continue
        x1, y1 = pos[e["from"]]
        x2, y2 = pos[e["to"]]
        w1 = _w(next(n["label"] for n in nodes if n["id"] == e["from"]))
        cls = "edge" + (f" {e['cls']}" if e["cls"] else "")
        if e["from"] == worst_nid and e["cls"] != "hypothesis":
            cls += " pressure"
        parts.append(
            f'<path class="{cls}" d="M{x1 + w1:.0f} {y1 + 24:.0f} C{x1 + w1 + 34:.0f} {y1 + 24:.0f} {x2 - 34:.0f} {y2 + 24:.0f} {x2:.0f} {y2 + 24:.0f}"/>'
        )
    for n in nodes:
        x, yy = pos[n["id"]]
        w = _w(n["label"])
        nid = n["id"]
        if n["kind"] == "op":
            op = n["op"]
            info = op_labels.get(op, {"method": "GET", "path": op})
            p95 = op_p95.get(op)
            sub = f"p95 {_ms(p95)} · measured" if p95 is not None else "measured wave · p95 not tagged"
            selected = " selected" if op == (select_op or worst_op) else ""
            press = " api" if op == worst_op else " api"
            parts.append(
                f'<g class="graph-node{press}{selected}" data-node="{nid}" tabindex="0" role="button" aria-label="{esc(info["method"] + " " + info["path"])}">'
                f'<rect x="{x:.0f}" y="{yy:.0f}" width="{w:.0f}" height="57" rx="7"/>'
                f'<text x="{x + 13:.0f}" y="{yy + 19:.0f}">{esc(info["method"] + " " + info["path"])}</text>'
                f'<text x="{x + 13:.0f}" y="{yy + 34:.0f}" class="minor">{esc(sub)}</text>'
                + (f'<text x="{x + 13:.0f}" y="{yy + 47:.0f}" class="minor" style="fill:#ff806c">HIGHEST P95</text>' if op == worst_op else "")
                + "</g>"
            )
        elif n["kind"] == "sym":
            parts.append(
                f'<g class="graph-node" data-node="{nid}" tabindex="0" role="button" aria-label="{esc(n["label"])}">'
                f'<rect x="{x:.0f}" y="{yy:.0f}" width="{w:.0f}" height="52" rx="6"/>'
                f'<text x="{x + 13:.0f}" y="{yy + 20:.0f}">{esc(n["label"])}</text>'
                f'<text x="{x + 13:.0f}" y="{yy + 34:.0f}" class="minor">{esc(n.get("sub", ""))}</text></g>'
            )
        else:
            parts.append(
                f'<g class="graph-node hyp" data-node="{nid}" tabindex="0" role="button" aria-label="Hypothesis, unconfirmed path">'
                f'<rect x="{x:.0f}" y="{yy:.0f}" width="{w:.0f}" height="37" rx="6"/>'
                f'<text x="{x + 12:.0f}" y="{yy + 16:.0f}" style="fill:#e8defc">{esc(n["label"])}</text>'
                f'<text x="{x + 12:.0f}" y="{yy + 28:.0f}" class="minor">unconfirmed path</text></g>'
            )
    parts.append("</svg>")
    return "".join(parts)


# ------------------------------------------------------------------ page ---


def _chip(text: str) -> str:
    return f'<span class="meta-chip"><span class="dot"></span>{esc(text)}</span>'


def _metric(label: str, value: str, unit: str, foot: str, tag: str = "", hot: bool = False) -> str:
    tag_html = f'<span class="mini-tag">{esc(tag)}</span>' if tag else ""
    return (
        f'<div class="metric"><div class="metric-label">{esc(label)}</div>'
        f'<div class="metric-value{" hot" if hot else ""}">{esc(value)}<span class="unit">{esc(unit)}</span></div>'
        f'<div class="metric-foot">{foot}{tag_html}</div></div>'
    )


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    out: list[dict[str, Any]] = []
    for line in lines:
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if isinstance(row, dict):
            out.append(row)
    return out


def _load_experiments(run_dir: Path) -> list[dict[str, Any]]:
    exp_dir = run_dir / "experiments"
    if not exp_dir.is_dir():
        return []
    rows: list[dict[str, Any]] = []
    try:
        children = sorted(exp_dir.glob("*.json"))
    except OSError:
        return []
    for child in children:
        rec = _read_json(child)
        if rec:
            rows.append(rec)
    return rows


def _first_prose(md: str) -> str:
    in_fence = False
    for raw in md.splitlines():
        line = raw.strip()
        if line.startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence or not line:
            continue
        if line.startswith("#") or line.startswith("|") or line.startswith("- ") or line.startswith("* "):
            continue
        cleaned = re.sub(r"\*\*([^*]+)\*\*", r"\1", line)
        cleaned = re.sub(r"`([^`]+)`", r"\1", cleaned)
        return cleaned.strip()
    return ""


def _md_inline(text: str) -> str:
    text = esc(text)
    text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"`([^`]+)`", r"<code>\1</code>", text)
    text = re.sub(
        r"\[([^\]]+)\]\((https?://[^)\s]+)\)",
        r'<a href="\2" rel="noopener noreferrer" target="_blank">\1</a>',
        text,
    )
    return text


def _looks_like_table(lines: list[str], i: int) -> bool:
    if i + 1 >= len(lines):
        return False
    row, sep = lines[i].strip(), lines[i + 1].strip()
    return row.startswith("|") and sep.startswith("|") and re.match(r"^\|?\s*:?-{3,}", sep) is not None


def _md_table(lines: list[str], start: int) -> tuple[str, int]:
    rows: list[list[str]] = []
    i = start
    while i < len(lines) and lines[i].strip().startswith("|"):
        raw = lines[i].strip()
        cells = [c.strip() for c in raw.strip("|").split("|")]
        if i == start + 1 and all(re.match(r"^:?-{3,}:?$", c) for c in cells):
            i += 1
            continue
        rows.append(cells)
        i += 1
    if not rows:
        return "", start + 1
    head, body = rows[0], rows[1:]
    thead = "<tr>" + "".join(f"<th>{_md_inline(c)}</th>" for c in head) + "</tr>"
    tbody = "".join("<tr>" + "".join(f"<td>{_md_inline(c)}</td>" for c in row) + "</tr>" for row in body)
    return f"<table><thead>{thead}</thead><tbody>{tbody}</tbody></table>", i


def _md_to_html(text: str) -> str:
    if not text.strip():
        return ""
    pieces: list[tuple[str, str]] = []
    pos = 0
    for match in re.finditer(r"```[^\n]*\n([\s\S]*?)```", text):
        if match.start() > pos:
            pieces.append(("md", text[pos:match.start()]))
        pieces.append(("code", match.group(1)))
        pos = match.end()
    if pos < len(text):
        pieces.append(("md", text[pos:]))
    html_out: list[str] = []
    for kind, body in pieces:
        if kind == "code":
            html_out.append(f"<pre><code>{esc(body.rstrip())}</code></pre>")
            continue
        lines = body.splitlines()
        i = 0
        para: list[str] = []

        def flush_para() -> None:
            if para:
                html_out.append("<p>" + _md_inline(" ".join(para)) + "</p>")
                para.clear()

        while i < len(lines):
            raw = lines[i]
            stripped = raw.strip()
            if not stripped:
                flush_para()
                i += 1
                continue
            if re.match(r"^\d+ of \d+ excerpts shown\.", stripped):
                flush_para()
                html_out.append(f'<p class="code-condense-note">{esc(stripped)}</p>')
                i += 1
                continue
            if stripped.startswith("#"):
                flush_para()
                hashes = len(stripped) - len(stripped.lstrip("#"))
                level = min(max(hashes, 1), 3)
                title = stripped[hashes:].strip()
                hid = ' id="verification"' if level == 2 and title.lower() == "verification" else ""
                html_out.append(f"<h{level}{hid}>{_md_inline(title)}</h{level}>")
                i += 1
                continue
            if _looks_like_table(lines, i):
                flush_para()
                table, i = _md_table(lines, i)
                html_out.append(table)
                continue
            if stripped.startswith("- ") or stripped.startswith("* "):
                flush_para()
                items: list[str] = []
                while i < len(lines) and (lines[i].strip().startswith("- ") or lines[i].strip().startswith("* ")):
                    items.append(f"<li>{_md_inline(lines[i].strip()[2:])}</li>")
                    i += 1
                html_out.append("<ul>" + "".join(items) + "</ul>")
                continue
            para.append(stripped)
            i += 1
        flush_para()
    return "".join(html_out)


def _call_label(verif: dict[str, Any]) -> str:
    ep = verif.get("endpoint") if isinstance(verif.get("endpoint"), dict) else {}
    method = str(ep.get("method") or "GET").upper()
    path = str(ep.get("path") or "").strip()
    if path:
        return f"{method} {path}"
    return str(verif.get("operation_id") or "cited call")


def _verdict_word(verdict: str) -> str:
    return verdict.replace("_", " ")


def _failed_verdict(verdict: str) -> bool:
    return verdict in ("hypothesis_failed", "regressed_control")


def _blocker_panel_html(blocker: dict[str, Any] | None) -> str:
    if not blocker:
        return ""
    summary = str(blocker.get("summary") or blocker.get("code") or "This run was blocked.")
    security = "This was a security refusal." if blocker.get("security") is True else ""
    return (
        '<section class="section" id="blocked">'
        '<div class="section-head"><div><div class="section-title">Blocked before measurement</div>'
        '<div class="section-desc">The run stopped before load was applied.</div></div></div>'
        f'<div class="panel" style="padding:18px 20px"><p class="hero-sub" style="margin:0">{esc(summary)}</p>'
        + (f'<p class="hero-sub">{esc(security)}</p>' if security else "")
        + "</div></section>"
    )


def _experiments_table_html(exps: list[dict[str, Any]], verif: dict[str, Any] | None) -> str:
    if not exps:
        return ""
    before_id = str((verif or {}).get("experiment_id") or "")
    after = (verif or {}).get("after") if isinstance((verif or {}).get("after"), dict) else {}
    after_id = str(after.get("experiment_id") or "")
    rows: list[str] = []
    for rec in exps:
        eid = str(rec.get("experiment_id") or "")
        inp = rec.get("input") if isinstance(rec.get("input"), dict) else {}
        out = rec.get("output") if isinstance(rec.get("output"), dict) else {}
        eps = inp.get("endpoints") if isinstance(inp.get("endpoints"), list) else []
        ep_txt = ", ".join(
            f"{str(e.get('method') or 'GET').upper()} {e.get('path')}"
            for e in eps
            if isinstance(e, dict)
        ) or "—"
        rate = inp.get("rate", out.get("offered_rps"))
        dur = inp.get("duration_s", out.get("duration_s"))
        ops = out.get("operations") if isinstance(out.get("operations"), dict) else {}
        p95s = " · ".join(
            f"{oid} {_ms(row.get('p95_ms'))}"
            for oid, row in ops.items()
            if isinstance(row, dict) and row.get("p95_ms") is not None
        ) or "—"
        errs = " · ".join(
            f"{oid} {float(row.get('error_rate') or 0):.1%}"
            for oid, row in ops.items()
            if isinstance(row, dict)
        ) or "—"
        dropped = out.get("dropped_iterations")
        mark = ""
        if eid and eid == before_id:
            mark = '<span class="verify-mark before">BEFORE</span>'
        elif eid and eid == after_id:
            mark = '<span class="verify-mark after">AFTER</span>'
        rows.append(
            f"<tr><td class=\"mono\">{esc(eid or '—')}</td><td>{esc(ep_txt)}</td>"
            f"<td class=\"num\">{esc(_rps(rate))}</td>"
            f"<td class=\"num\">{esc(str(dur) + ' s') if dur is not None else '—'}</td>"
            f"<td class=\"num\">{esc(p95s)}</td><td class=\"num\">{esc(errs)}</td>"
            f"<td class=\"num\">{esc(dropped if dropped is not None else '—')}</td>"
            f"<td>{mark}</td></tr>"
        )
    return (
        '<div class="panel exp-table-wrap"><div class="table-wrap"><table class="ops-table">'
        "<thead><tr><th>Experiment</th><th>Endpoints</th><th>Rate</th><th>Duration</th>"
        "<th>p95</th><th>Error rate</th><th>Dropped</th><th></th></tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table></div></div>"
    )


def _hypothesis_html(md: str) -> str:
    para = _first_prose(md)
    if not para:
        return ""
    return (
        '<aside class="hypothesis-box" aria-label="Investigator hypothesis">'
        '<div class="hypothesis-label">Investigator hypothesis</div>'
        f'<p class="hypothesis-prose">{esc(para)}</p></aside>'
    )


_FENCE_RE = re.compile(r"```[^\n]*\n[\s\S]*?```")
_H2_RE = re.compile(r"(?m)^##[ \t]+(.+)$")


def _last_paragraph(prose: str) -> str:
    text = prose.strip()
    if not text:
        return ""
    return re.split(r"\n\s*\n", text)[-1].strip()


def _condense_code_body(body: str) -> tuple[str, int, int]:
    fences = list(_FENCE_RE.finditer(body))
    total = len(fences)
    if total <= 2:
        return body, total, total
    keep = {0, total - 1}
    chunks: list[str] = []
    pos = 0
    for i, match in enumerate(fences):
        prose = body[pos:match.start()]
        if i in keep:
            intro = _last_paragraph(prose)
            if intro:
                chunks.append(intro)
            chunks.append(match.group(0))
        pos = match.end()
    note = f"{len(keep)} of {total} excerpts shown. Full Code section is in report.md."
    chunks.append(note)
    return "\n\n".join(chunks) + "\n", len(keep), total


def _condense_report_code(md: str) -> str:
    matches = list(_H2_RE.finditer(md))
    if not matches:
        return md
    out: list[str] = []
    if matches[0].start() > 0:
        out.append(md[: matches[0].start()])
    for i, match in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(md)
        heading_line = match.group(0)
        title = match.group(1).strip()
        body = md[match.end():end]
        if title.lower() == "code":
            condensed, _kept, _total = _condense_code_body(body)
            body = "\n" + condensed.lstrip("\n")
        elif not body.startswith("\n"):
            body = "\n" + body
        out.append(heading_line + body)
    return "".join(out)


def _has_verification_heading(md: str) -> bool:
    return bool(re.search(r"(?m)^##\s+Verification\s*$", md))


def _report_section_html(md: str, verification: dict[str, Any] | None = None) -> str:
    text = md
    if verification and not _has_verification_heading(text):
        from loadline.verify_cmd import render_comparison

        text = text.rstrip() + "\n" + render_comparison(verification)
    text = _condense_report_code(text)
    if not text.strip():
        return ""
    return (
        '<section class="section" id="report">'
        '<div class="section-head"><div><div class="section-title">Report</div>'
        '<div class="section-desc">Canonical write-up from report.md.</div></div></div>'
        f'<div class="panel report-md">{_md_to_html(text)}</div></section>'
    )


def _nav_report_html(has_report: bool) -> str:
    if not has_report:
        return ""
    return (
        '<a href="#report" data-nav="report" aria-label="Report">'
        '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" aria-hidden="true">'
        '<path d="M7 3.5h7l4 4V20a1.5 1.5 0 0 1-1.5 1.5h-9A1.5 1.5 0 0 1 6 20V5a1.5 1.5 0 0 1 1-1.5Z"/>'
        '<path d="M14 3.5V8h4M9 12h6M9 16h6"/></svg><span>Report</span></a>'
    )


def _snippet_html(repo_root: str, path: str, start: Any, end: Any, limit: int = 24) -> str:
    repo = Path(repo_root) if repo_root else None
    if repo is None or not repo.is_dir():
        return '<p class="inspect-reads">The repository is not available.</p>'
    try:
        start_i = max(1, int(start))
        end_i = max(start_i, int(end))
    except (TypeError, ValueError):
        return ""
    target = (repo / path).resolve()
    try:
        if not str(target).startswith(str(repo.resolve())) or not target.is_file():
            return '<p class="inspect-reads">The repository is not available.</p>'
        lines = target.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return '<p class="inspect-reads">The repository is not available.</p>'
    shown_end = min(end_i, start_i + limit - 1, len(lines))
    chunk = "\n".join(lines[start_i - 1:shown_end])
    header = f"{path}:{start_i}–{shown_end}"
    return f'<pre class="inspect-snippet">{esc(header)}\n{esc(chunk)}</pre>'


def _inspect_reads_html(
    reads: list[dict[str, Any]],
    patch_paths: list[str],
    repo_root: str,
) -> str:
    cited = [p for p in patch_paths if p]
    relevant = [r for r in reads if str(r.get("path") or "") in cited] if cited else []
    if not relevant and not cited:
        return ""
    bits: list[str] = []
    if relevant:
        ranges = "<br>".join(
            f"{esc(r.get('path'))}:{esc(r.get('start_line'))}–{esc(r.get('end_line'))}"
            for r in relevant
        )
        bits.append(f'<div class="inspect-reads">{ranges}</div>')
    if cited:
        first = relevant[0] if relevant else None
        if first is not None:
            bits.append(
                _snippet_html(
                    repo_root,
                    str(first.get("path") or cited[0]),
                    first.get("start_line") or 1,
                    first.get("end_line") or 1,
                )
            )
        elif not repo_root or not Path(repo_root).is_dir():
            bits.append('<p class="inspect-reads">The repository is not available.</p>')
    return "".join(bits)


def render_run_page(run_dir: Path, run_id: str | None, *, serve: bool = True) -> str:
    """Full single-file dashboard HTML; empty string when nothing to show."""
    run_dir = Path(run_dir)
    if not run_dir.is_dir():
        return ""
    ledger = _ledger_events(run_dir)
    waves = _waves(ledger)
    report = _read_json(run_dir / "report.json")
    attempts = _read_json(run_dir / "attempts.json")
    blocker = attempts.get("blocker") if isinstance(attempts, dict) and isinstance(attempts.get("blocker"), dict) else None
    verification = _read_json(run_dir / "verification.json")
    reads = _read_jsonl(run_dir / "reads.jsonl")
    experiments = _load_experiments(run_dir)
    if report is None and not waves and not ledger and not blocker:
        return ""
    rid = run_id or (str(report.get("run_id")) if isinstance(report, dict) and report.get("run_id") else None) or run_dir.name
    profile = _read_json(run_dir / "profile.json") or {}
    repo_root = str(profile.get("root") or "")
    repo_name = Path(repo_root).name if repo_root else "unknown repository"
    vcs = profile.get("vcs") if isinstance(profile.get("vcs"), dict) else {}
    sha = str((vcs or {}).get("sha") or "")[:7]
    first_ts = _parse_ts(ledger[0].get("ts")) if ledger else None
    op_labels = _op_plans(ledger)
    hypotheses = [e for e in ledger if e.get("kind") == "hypothesis"]
    findings = [e for e in ledger if e.get("kind") == "finding"]

    op_ids: list[str] = []
    op_p95: dict[str, float] = {}
    op_err: dict[str, int] = {}
    op_ach: dict[str, float] = {}
    op_off: dict[str, float] = {}
    exp_of: dict[str, str] = {}
    peak_offered = 0.0
    dropped_total = 0
    for w in waves:
        res = w.get("result") or {}
        try:
            peak_offered = max(peak_offered, float(res.get("offered_rps") or 0.0))
        except (TypeError, ValueError):
            pass
        try:
            dropped_total += int(res.get("dropped_iterations") or 0)
        except (TypeError, ValueError):
            pass
        ops = res.get("operations") if isinstance(res.get("operations"), dict) else {}
        for op_id, row in ops.items():
            if not isinstance(row, dict):
                continue
            op_id = str(op_id)
            if op_id not in op_ids:
                op_ids.append(op_id)
            exp_of[op_id] = str(w.get("experiment_id") or "")
            try:
                if row.get("p95_ms") is not None:
                    op_p95[op_id] = max(op_p95.get(op_id, 0.0), float(row["p95_ms"]))
            except (TypeError, ValueError):
                pass
            try:
                op_err[op_id] = max(op_err.get(op_id, 0), int(row.get("error_count") or 0))
            except (TypeError, ValueError):
                pass
    latest = waves[-1].get("result") or {} if waves else {}
    latest_ops = latest.get("operations") if isinstance(latest.get("operations"), dict) else {}
    latest_offered = latest.get("offered_rps")
    for op_id, row in latest_ops.items():
        if isinstance(row, dict):
            try:
                op_ach[str(op_id)] = float(row.get("achieved_rps") or 0.0)
            except (TypeError, ValueError):
                pass
            try:
                op_off[str(op_id)] = float(row.get("offered_rps") or 0.0)
            except (TypeError, ValueError):
                pass
    worst_op = max(op_p95, key=lambda k: op_p95[k]) if op_p95 else (op_ids[0] if op_ids else None)
    cited_op = str(verification.get("operation_id") or "").strip() if verification else ""
    select_op = cited_op if cited_op and cited_op in op_ids else worst_op
    if select_op is not None and select_op in op_ids:
        # Cited (or highest-pressure) op must survive the 4-node graph cap below.
        op_ids = [select_op] + [o for o in op_ids if o != select_op]
    elif worst_op is not None and worst_op in op_ids:
        op_ids = [worst_op] + [o for o in op_ids if o != worst_op]

    state = ""
    if isinstance(report, dict):
        state = str(report.get("run_state") or "")
    if not state:
        for e in reversed(ledger):
            if e.get("kind") == "report_written":
                state = str(e.get("run_state") or "")
                break
    if not state and blocker:
        state = str(blocker.get("code") or "blocked")
    state = state or ("completed" if waves else "unknown")
    verdict = str(verification.get("verdict") or "").strip() if verification else ""
    if verdict:
        state_label = _verdict_word(verdict).title() if "_" in verdict else verdict.replace("_", " ").title()
        if verdict == "improved":
            state_label = "Improved"
        state_bad = _failed_verdict(verdict) or verdict not in ("improved",)
        state_failed = _failed_verdict(verdict)
    else:
        state_label = {"completed": "Complete", "investigation_incomplete": "Investigation incomplete"}.get(state, state.replace("_", " ").title())
        state_bad = state not in ("completed",)
        state_failed = False

    # ---------------- hero ----------------
    if verdict:
        call = _call_label(verification or {})
        before = (verification or {}).get("before") if isinstance((verification or {}).get("before"), dict) else {}
        after = (verification or {}).get("after") if isinstance((verification or {}).get("after"), dict) else None
        cls = "verdict-bad" if state_failed else "verdict-ok"
        hero_title = f"{esc(call)} <em class=\"{cls}\">{esc(_verdict_word(verdict))}</em>."
        if isinstance(after, dict) and after.get("p95_ms") is not None:
            hero_sub = (
                f"p95 {_ms(before.get('p95_ms'))} → {_ms(after.get('p95_ms'))} at "
                f"{_rps((verification or {}).get('rate'))} for {(verification or {}).get('duration_s')} s."
            )
        else:
            hero_sub = f"Cited call {call} · after measurement was not recorded."
    elif waves and worst_op is not None:
        winfo = op_labels.get(worst_op, {"method": "GET", "path": worst_op})
        first_p95 = worst_last_p95 = None
        for w in waves:
            ops = (w.get("result") or {}).get("operations") or {}
            row = ops.get(worst_op) if isinstance(ops, dict) else None
            v = (row or {}).get("p95_ms") if isinstance(row, dict) else None
            try:
                v = float(v) if v is not None else None
            except (TypeError, ValueError):
                v = None
            if v is not None and first_p95 is None:
                first_p95 = v
            if v is not None:
                worst_last_p95 = v
        if first_p95 is not None and worst_last_p95 is not None and len(waves) > 1:
            hero_title = (
                f"{esc(winfo['path'])} p95 climbs from {_ms(first_p95)} "
                f"to <em>{_ms(worst_last_p95)}</em>."
            )
        else:
            hero_title = f"Measured {esc(winfo['path'])} at {_rps(latest_offered)} — worst p95 <em>{_ms(worst_last_p95)}</em>."
        hero_sub = (
            f"{len(waves)} measured k6 waves from {_rps(waves[0].get('result', {}).get('offered_rps'))} "
            f"to {_rps(peak_offered)} · {dropped_total} dropped iterations · "
            "SLO was not recorded for this run, so no breach is claimed."
        )
    else:
        hero_title = "This run did not reach measurement." if blocker else "No load was measured on this run."
        hero_sub = (
            str(blocker.get("summary") or blocker.get("code") or "The run stopped before load was applied.")
            if blocker
            else "The ledger holds no k6 waves. Interpret run state and coverage below."
        )
    pr_url = str((verification or {}).get("pr_url") or "").strip() if verification else ""
    pr_chip = ""
    if pr_url.startswith("https://") or pr_url.startswith("http://"):
        pr_chip = (
            f'<a class="meta-chip pr-link" href="{esc(pr_url)}" rel="noopener noreferrer" target="_blank">'
            '<span class="dot"></span>PULL REQUEST</a>'
        )
    chips = "".join(
        [_chip(f"RUN {rid}"), _chip(repo_name)]
        + ([_chip(f"COMMIT {sha}")] if sha else [])
        + ([_chip(f"{len(waves)} K6 WAVES")] if waves else [])
        + [_chip(state_label.upper())]
        + ([_chip("NOT VERIFIED")] if not verification else [])
        + ([pr_chip] if pr_chip else [])
    )

    # ---------------- metrics ----------------
    if waves:
        m1 = _metric("Peak offered load", f"{peak_offered:g}", "req/s",
                     f"<span>highest tested step</span>", tag="MEASURED")
        wlabel = op_labels.get(worst_op or "", {"path": worst_op or "—"})["path"]
        m2 = _metric("Worst p95 latency", f"{op_p95[worst_op]:.0f}" if worst_op in op_p95 else "—", "ms",
                     f"<span>{esc(wlabel)} · {esc(exp_of.get(worst_op or '', ''))}</span>", tag="MEASURED", hot=True)
        m3 = _metric("Dropped iterations", str(dropped_total), "",
                     f"<span>across {len(waves)} waves</span>", tag="MEASURED", hot=dropped_total > 0)
    else:
        m1 = _metric("Peak offered load", "—", "", "<span>not measured</span>")
        m2 = _metric("Worst p95 latency", "—", "", "<span>not measured</span>")
        m3 = _metric("Dropped iterations", "—", "", "<span>not measured</span>")
    if verification and isinstance((verification or {}).get("before"), dict):
        before = verification.get("before") or {}
        after = verification.get("after") if isinstance(verification.get("after"), dict) else None
        if after is not None and after.get("p95_ms") is not None:
            try:
                cited_val = f"{int(round(float(before.get('p95_ms'))))} → {int(round(float(after.get('p95_ms'))))}"
            except (TypeError, ValueError):
                cited_val = _ms(before.get("p95_ms")).replace(" ms", "")
        else:
            cited_val = _ms(before.get("p95_ms")).replace(" ms", "")
        m4 = _metric(
            "Cited p95",
            cited_val,
            "ms",
            f"<span>{esc(_call_label(verification))} · {esc(_verdict_word(verdict))}</span>",
            tag="VERIFIED",
            hot=state_failed,
        )
    elif findings:
        m4 = _metric("Findings recorded", str(len(findings)), "", f"<span>{len(hypotheses)} hypotheses</span>", tag="RECORDED")
    else:
        m4 = _metric("Findings recorded", "none", "", "<span>measurements only</span>")
    metrics = m1 + m2 + m3 + m4

    # ---------------- charts ----------------
    if waves:
        off_pts = [(i, float((w.get("result") or {}).get("offered_rps") or 0.0)) for i, w in enumerate(waves)]
        offered_svg = _offered_chart(off_pts, peak_offered)
        lat_pts = []
        for i, w in enumerate(waves):
            ops = (w.get("result") or {}).get("operations") or {}
            row = ops.get(worst_op) if isinstance(ops, dict) and worst_op else None
            v = (row or {}).get("p95_ms") if isinstance(row, dict) else None
            try:
                lat_pts.append((i, float(v), str(w.get("experiment_id") or ""), str(w.get("wave") or "")))
            except (TypeError, ValueError):
                continue
        lat_svg = _latency_chart(lat_pts, op_labels.get(worst_op or "", {"path": worst_op or ""})["path"]) if lat_pts else ""
        chart_note = "Investigator k6 waves in offered-load order"
        chart_key = (
            '<span class="key-item"><i class="key-line"></i>Offered load</span>'
            f'<span class="key-item"><i class="key-line rust"></i>p95 {esc(op_labels.get(worst_op or "", {"path": ""})["path"])}</span>'
            '<span class="key-item"><i class="key-line dash"></i>No recorded SLO</span>'
        )
        if lat_pts:
            bi = max(range(len(lat_pts)), key=lambda i: lat_pts[i][1])
            chart_foot_l = (
                "<strong>Measured peak:</strong> "
                f"{esc(op_labels.get(worst_op or '', {'path': ''})['path'])} p95 {_ms(lat_pts[bi][1])} "
                f"at {_rps(off_pts[bi][1])} <span class=\"warning\">({esc(lat_pts[bi][2])})</span>."
            )
        else:
            chart_foot_l = "<strong>Measured peak:</strong> p95 was not tagged on these waves."
        chart_foot_r = "<strong>Interpretation boundary:</strong> correlation over load steps does not assign latency to a specific function."
    else:
        offered_svg = lat_svg = ""
        chart_note = "No waves to plot"
        chart_key = ""
        chart_foot_l = "No k6 waves were recorded on this run."
        chart_foot_r = ""

    # ---------------- graph ----------------
    graph = build_graph(run_dir, op_ids, op_labels, worst_op, hypotheses)
    graph_svg = _graph_svg(graph, op_ids, op_labels, op_p95, exp_of, worst_op, select_op) if op_ids else '<div class="graph-canvas"><p class="muted small" style="padding:18px">No operations were load-tested on this run.</p></div>'
    node_data: dict[str, Any] = {}
    op_nodes: dict[str, str] = {}
    for i, op_id in enumerate(op_ids[:4]):
        nid = f"op_{i}"
        op_nodes[str(i)] = nid
        info = op_labels.get(op_id, {"method": "GET", "path": op_id})
        h = graph["handlers"].get(nid)
        ev = exp_of.get(op_id, "")
        node_data[nid] = {
            "kind": "HTTP operation · Measured",
            "title": f"{info['method']} {info['path']}",
            "source": h["loc"] if h else ("Route mapping unavailable" + (f": {graph['unavailable_reason']}" if graph["unavailable"] else "")),
            "p95": _ms(op_p95.get(op_id)),
            "db": "Not measured",
            "evidence": ev or "no experiment id",
            "relation": ("HANDLES_ROUTE · static" if h else "Unresolved"),
            "timing": "Operation measured",
            "foot": "Measured operation · selected" if op_id == select_op else "Measured operation",
            "finding": (findings[0].get("symptom") or findings[0].get("mechanism") or "Finding recorded.") if findings else "",
            "explain": "Directly observed operation result. It does not attribute latency to neighbouring code nodes.",
            "hot": op_id == worst_op and op_id in op_p95,
        }
    for nid, h in graph["handlers"].items():
        node_data[nid] = {
            "kind": "Symbol · Entire Graph",
            "title": h["symbol"],
            "source": h["loc"],
            "p95": "Not measured",
            "db": "Not measured",
            "evidence": "Graph relation only",
            "relation": "HANDLES_ROUTE · static",
            "timing": "Not measured",
            "foot": "Provider relation · static",
            "finding": "No runtime timing is attached to this symbol.",
            "explain": "The graph supplies a static route-to-symbol relationship. Runtime timing is not attached to this edge.",
        }
    for k in range(min(len(hypotheses), 2)):
        hyp = hypotheses[k]
        node_data[f"hyp_{k}"] = {
            "kind": "Hypothesis · Unconfirmed path",
            "title": f"H-{k + 1:02d} · {str(hyp.get('claim', 'recorded'))[:60]}",
            "source": ", ".join(hyp.get("evidence_ids") or []) or "ledger hypothesis",
            "p95": "See operation",
            "db": "Not measured",
            "evidence": ", ".join(hyp.get("evidence_ids") or []) or "none",
            "relation": "HYPOTHESIS · agent",
            "timing": "Not an edge measurement",
            "foot": "Hypothesis overlay · dashed",
            "finding": str(hyp.get("claim", "recorded"))[:160],
            "explain": "An agent-authored conjecture, not a measured code relationship.",
        }
    select_node = f"op_{op_ids[:4].index(select_op)}" if select_op in op_ids[:4] else None
    worst_node = f"op_{op_ids[:4].index(worst_op)}" if worst_op in op_ids[:4] else None
    if select_node is not None and select_node in node_data:
        default_inspect = node_data[select_node]
    elif worst_node is not None and worst_node in node_data:
        default_inspect = node_data[worst_node]
    elif node_data:
        default_inspect = next(iter(node_data.values()))
    else:
        default_inspect = {"kind": "—", "title": "No nodes", "source": "—", "p95": "—", "db": "—",
                           "evidence": "—", "relation": "—", "timing": "—", "foot": "—",
                           "finding": "—", "explain": "—"}
    if findings:
        f0 = findings[0]
        finding_id = f"F-{(ledger.index(f0) + 1):02d}" if f0 in ledger else "F-01"
        finding_state = "Recorded"
        finding_title = str(f0.get("symptom") or f0.get("mechanism") or "Finding recorded.")
        finding_body = "Agent-recorded finding. Measurements that support it are linked in the evidence ledger."
        finding_links = "".join(
            f'<span class="evidence-link">{esc(e)}</span>' for e in (f0.get("evidence_ids") or [])
        )
        finding_block = (
            f'<div class="finding-mini"><div class="finding-mini-top"><span>{esc(finding_id)}</span>'
            f'<span>·</span><span>{esc(finding_state)}</span></div>'
            f'<h4 id="inspect-finding">{esc(finding_title)}</h4>'
            f'<p id="inspect-explainer">{esc(finding_body)}</p>'
            f'<div class="finding-links">{finding_links}</div></div>'
        )
    else:
        finding_block = ""
    unmapped = sum(1 for i in range(min(len(op_ids), 4)) if f"op_{i}" not in graph["handlers"])
    nav_count = f'<span class="nav-count">{unmapped}</span>' if unmapped and not graph["unavailable"] else ""

    # ---------------- ops table ----------------
    ops_rows = []
    ranked_latest = sorted(
        ((op, row) for op, row in latest_ops.items() if isinstance(row, dict)),
        key=lambda kv: float(kv[1].get("p95_ms") or 0.0),
        reverse=True,
    )
    for idx, (op_id, row) in enumerate(ranked_latest):
        op_id = str(op_id)
        info = op_labels.get(op_id, {"method": "GET", "path": op_id})
        h = graph["handlers"].get(f"op_{op_ids[:4].index(op_id)}") if op_id in op_ids[:4] else None
        src = f"<span class=\"map-state\">Mapped · {esc(h['loc'])}</span>" if h else '<span class="map-state">Source not mapped</span>'
        try:
            err_rate = float(row.get("error_rate") or 0.0)
        except (TypeError, ValueError):
            err_rate = 0.0
        try:
            ach = float(row.get("achieved_rps") or 0.0)
        except (TypeError, ValueError):
            ach = 0.0
        is_worst = bool(ranked_latest) and idx == 0
        is_active = (select_op is not None and op_id == select_op) or (select_op is None and idx == 0)
        ops_rows.append(
            f'<tr class="{"active-row" if is_active else ""}" data-op="{idx}" tabindex="0">'
            f"<td><div class=\"route-cell\"><span class=\"method\">{esc(info['method'])}</span>"
            f"<div><div class=\"route-name\">{esc(info['path'])}</div>"
            f"<div class=\"route-handler\">{esc(op_id)}</div></div></div></td>"
            f"<td>{src}</td>"
            f"<td class=\"num{' hot' if is_worst else ''}\">{_ms(row.get('p95_ms'))}</td>"
            f"<td class=\"num{' hot' if err_rate > 0 else ''}\">{err_rate:.1%}</td>"
            f"<td class=\"num\">{ach:.1f} req/s</td>"
            '<td><span class="map-state">Not scored — no SLO recorded</span></td></tr>'
        )
    if not ops_rows:
        ops_rows.append('<tr><td colspan="6"><span class="map-state">No operations were load-tested on this run.</span></td></tr>')
    # re-key opNodes to table row order
    op_nodes = {}
    for idx, (op_id, _row) in enumerate(ranked_latest):
        op_id = str(op_id)
        if op_id in op_ids[:4]:
            op_nodes[str(idx)] = f"op_{op_ids[:4].index(op_id)}"
    ops_foot = f"{len(ranked_latest)} operations loaded · {_rps(latest_offered)} latest step"

    # ---------------- trail ----------------
    trail = []
    for e in ledger:
        kind = str(e.get("kind") or "")
        ts = _fmt_time(_parse_ts(e.get("ts")))
        if kind == "hypothesis":
            trail.append((ts, "", "Hypothesis recorded", str(e.get("claim", "recorded"))[:220], "HYPOTHESIS", ""))
        elif kind == "k6_run":
            res = e.get("result") or {}
            wops = res.get("operations") if isinstance(res.get("operations"), dict) else {}
            bits = []
            for oid, r in list(wops.items())[:3]:
                if isinstance(r, dict) and r.get("p95_ms") is not None:
                    try:
                        bits.append(f"{oid} {_ms(r['p95_ms'])}")
                    except (TypeError, ValueError):
                        pass
            desc = f"Offered {_rps(res.get('offered_rps'))} · " + (" · ".join(bits) if bits else "ops not tagged")
            try:
                if int(res.get("dropped_iterations") or 0):
                    desc += f" · dropped {int(res['dropped_iterations'])}"
            except (TypeError, ValueError):
                pass
            trail.append((ts, "", f"{e.get('experiment_id') or 'k6'} · measured wave", desc, "MEASURED", ""))
        elif kind == "experiment_rejected":
            trail.append((ts, "rejected", "Experiment rejected before execution", str(e.get("reason", ""))[:220], "REJECTED", "rejected"))
        elif kind == "finding":
            trail.append((ts, "supported", "Finding recorded", str(e.get("symptom") or e.get("mechanism") or "recorded")[:220], "FINDING", "supported"))
        elif kind == "investigation_incomplete":
            trail.append((ts, "rejected", "Investigation stopped", str(e.get("reason", ""))[:220], "STOPPED", "rejected"))
    if verification and verdict:
        before = verification.get("before") if isinstance(verification.get("before"), dict) else {}
        after = verification.get("after") if isinstance(verification.get("after"), dict) else None
        if isinstance(after, dict) and after.get("p95_ms") is not None:
            vdesc = f"{_verdict_word(verdict)} · p95 {_ms(before.get('p95_ms'))} → {_ms(after.get('p95_ms'))}"
        else:
            vdesc = _verdict_word(verdict)
        trail.append(("—", "supported" if verdict == "improved" else "rejected", "Verification recorded", vdesc, "VERIFY", "supported" if verdict == "improved" else "rejected"))
    if not trail:
        trail_html = '<div class="trail-event"><div class="trail-time">—</div><div class="trail-rail"><i class="trail-dot"></i></div><div><div class="trail-title">No material events</div><div class="trail-desc">The ledger holds no hypothesis, wave, or finding events.</div></div><span class="trail-badge">EMPTY</span></div>'
    else:
        trail_html = "".join(
            f'<div class="trail-event"><div class="trail-time">{esc(t)}</div>'
            f'<div class="trail-rail"><i class="trail-dot {dot}"></i></div>'
            f"<div><div class=\"trail-title\">{esc(title)}</div>"
            f"<div class=\"trail-desc\">{esc(desc)}</div></div>"
            f'<span class="trail-badge {cls}">{esc(badge)}</span></div>'
            for t, dot, title, desc, badge, cls in trail
        )

    # ---------------- evidence ----------------
    ev_rows = []
    for w in waves:
        res = w.get("result") or {}
        wops = res.get("operations") if isinstance(res.get("operations"), dict) else {}
        obs = []
        for oid, r in list(wops.items())[:3]:
            if isinstance(r, dict) and r.get("p95_ms") is not None:
                obs.append(f"{oid} p95 = {_ms(r['p95_ms'])}")
        ev_rows.append(
            f"<tr><td class=\"mono\">{esc(w.get('experiment_id') or '?')}</td><td>k6 measurement</td>"
            f"<td>{esc(' · '.join(obs) if obs else 'ops not tagged')} at {_rps(res.get('offered_rps'))}</td>"
            f"<td class=\"mono\">waves/{esc(w.get('wave') or '?')}/k6.summary.json</td>"
            '<td><span class="mini-tag">MEASURED</span></td></tr>'
        )
    for n, f_ in enumerate(findings):
        ev_rows.append(
            f"<tr><td class=\"mono\">F-{n + 1:02d}</td><td>Agent finding</td>"
            f"<td>{esc(str(f_.get('symptom') or f_.get('mechanism') or 'recorded'))[:160]}</td>"
            '<td class="mono">ledger.jsonl</td>'
            '<td><span class="mini-tag neutral">HYPOTHESIS</span></td></tr>'
        )
    for n, h in enumerate(hypotheses):
        ev_rows.append(
            f"<tr><td class=\"mono\">H-{n + 1:02d}</td><td>Hypothesis</td>"
            f"<td>{esc(str(h.get('claim') or 'recorded'))[:160]}</td>"
            '<td class="mono">ledger.jsonl</td>'
            '<td><span class="mini-tag neutral">HYPOTHESIS</span></td></tr>'
        )
    for rec in reads:
        path = str(rec.get("path") or "")
        start, end = rec.get("start_line"), rec.get("end_line")
        eid = str(rec.get("evidence_id") or path or "read")
        ev_rows.append(
            f"<tr><td class=\"mono\">{esc(eid)}</td><td>File read</td>"
            f"<td>{esc(path)}:{esc(start)}–{esc(end)}</td>"
            '<td class="mono">reads.jsonl</td>'
            '<td><span class="mini-tag neutral">READ</span></td></tr>'
        )
    if verification and verdict:
        before = verification.get("before") if isinstance(verification.get("before"), dict) else {}
        after = verification.get("after") if isinstance(verification.get("after"), dict) else None
        obs = _verdict_word(verdict)
        if isinstance(after, dict) and after.get("p95_ms") is not None:
            obs = f"{obs} · {_ms(before.get('p95_ms'))} → {_ms(after.get('p95_ms'))}"
        ev_rows.append(
            f"<tr><td class=\"mono\">verification</td><td>Verify result</td>"
            f"<td>{esc(obs)}</td>"
            '<td class="mono">verification.json</td>'
            '<td><span class="mini-tag green">VERIFIED</span></td></tr>'
        )
    if not ev_rows:
        ev_rows.append('<tr><td colspan="5"><span class="map-state">No evidence rows on this run.</span></td></tr>')

    # ---------------- environment ----------------
    entrypoints = profile.get("entrypoints") if isinstance(profile.get("entrypoints"), list) else []
    langs = profile.get("languages") if isinstance(profile.get("languages"), list) else []
    env_rows = "".join([
        "<tr><td>Target</td><td><span class=\"map-state\">Recorded</span></td>"
        f"<td>{esc(repo_root or 'unknown')} · {esc(', '.join(str(l) for l in langs) or 'language not recorded')} · "
        f"{len(entrypoints)} entrypoints</td></tr>",
        "<tr><td>Isolation</td><td><span class=\"map-state\">Not recorded</span></td>"
        "<td>Run artifacts record no isolation check; interpret as an un isolated lab unless proven otherwise.</td></tr>",
        "<tr><td>Graph coverage</td><td><span class=\"map-state\">"
        + (esc(f"{graph['mapped']} / {min(len(op_ids), 4)} ops") if not graph["unavailable"] else "Unavailable")
        + "</span></td><td>"
        + (esc(graph["unavailable_reason"]) if graph["unavailable"] else "Route-to-symbol mapping resolved at render time.")
        + "</td></tr>",
        "<tr><td>Host saturation</td><td><span class=\"map-state\">Not recorded</span></td>"
        "<td>No host telemetry accompanies investigator waves; saturation can neither be confirmed nor ruled out.</td></tr>",
    ])

    md_text = ""
    try:
        if (run_dir / "report.md").is_file():
            md_text = (run_dir / "report.md").read_text(encoding="utf-8")
    except OSError:
        pass
    evidence_ids = [str(w.get("experiment_id")) for w in waves if w.get("experiment_id")]
    evidence_ids += [f"F-{n + 1:02d}" for n in range(len(findings))]
    evidence_ids += [str(r.get("evidence_id") or r.get("path")) for r in reads if r.get("evidence_id") or r.get("path")]
    if verification:
        evidence_ids.append("verification")
    boot = {
        "runId": rid,
        "graphNodes": node_data,
        "opNodes": op_nodes,
        "evidenceIds": evidence_ids,
        "opCount": len(ranked_latest),
        "reportMd": md_text,
    }

    if serve:
        art_md = f"/artifacts/{rid}/report.md"
        art_json = f"/artifacts/{rid}/report.json"
    else:
        art_md = "report.md"
        art_json = "report.json"

    tpl = (_DIR / "template.html").read_text(encoding="utf-8")
    css = (_DIR / "v3_style.css").read_text(encoding="utf-8")
    js = (_DIR / "v3_app.js").read_text(encoding="utf-8")
    out = tpl
    out = out.replace("__PAGE_TITLE__", esc(f"Loadline — {repo_name} · {rid}"))
    out = out.replace("__CRUMB_RUN__", esc(rid.upper()[:7] if len(rid) > 7 else rid))
    state_cls = "state bad" if state_bad else "state"
    out = out.replace(
        "__STATE_PILL__",
        f'<span class="{state_cls}"><i class="state-dot"></i> {esc(state_label)}</span>',
    )
    out = out.replace("__REPO_NAME__", esc(repo_name))
    out = out.replace("__REPO_META__", esc(f"{repo_root} · {sha or 'no sha'}"))
    out = out.replace("__NAV_COUNT__", nav_count)
    out = out.replace("__NAV_REPORT__", _nav_report_html(bool(md_text.strip()) or bool(verification)))
    out = out.replace("__HERO_EYEBROW__", esc(f"Run · {_fmt_date(first_ts)} · {repo_name}"))
    out = out.replace("__HERO_TITLE__", hero_title)
    out = out.replace("__HERO_SUB__", esc(hero_sub))
    out = out.replace("__HYPOTHESIS__", _hypothesis_html(md_text))
    out = out.replace("__META_CHIPS__", chips)
    out = out.replace("__METRICS__", metrics)
    out = out.replace("__VERIFY_PANEL__", _blocker_panel_html(blocker))
    out = out.replace("__PRESSURE_VIS__", "" if waves else " hidden")
    out = out.replace("__CHART_NOTE__", esc(chart_note))
    out = out.replace("__CHART_KEY__", chart_key)
    out = out.replace("__CHART_OFFERED_SVG__", offered_svg)
    out = out.replace("__CHART_LAT_SVG__", lat_svg)
    out = out.replace("__CHART_FOOT_L__", chart_foot_l)
    out = out.replace("__CHART_FOOT_R__", esc(chart_foot_r))
    out = out.replace("__GRAPH_META__", graph["meta"])
    out = out.replace("__GRAPH_TOPLINE__", esc(graph["topline"]))
    out = out.replace("__GRAPH_SVG__", graph_svg)
    out = out.replace("__GRAPH_FOOT__", esc(graph["foot"]))
    out = out.replace("__INSPECT_KIND__", esc(default_inspect.get("kind", "")))
    out = out.replace("__INSPECT_TITLE__", esc(default_inspect.get("title", "")))
    out = out.replace("__INSPECT_SOURCE__", esc(default_inspect.get("source", "")))
    facts = (
        f'<div class="fact"><span>Operation p95 at peak</span>'
        f'<strong id="inspect-p95"{" class=\"hot\"" if default_inspect.get("hot") else ""}>'
        f'{esc(default_inspect.get("p95", ""))}</strong></div>'
        f'<div class="fact"><span>Evidence anchors</span>'
        f'<strong id="inspect-evidence">{esc(default_inspect.get("evidence", ""))}</strong></div>'
        f'<div class="fact hidden"><span>DB</span><strong id="inspect-db">Not measured</strong></div>'
    )
    patch_paths = []
    if verification and isinstance(verification.get("patch_paths"), list):
        patch_paths = [str(p) for p in verification.get("patch_paths") or [] if p]
    out = out.replace("__INSPECT_FACTS__", facts)
    out = out.replace("__INSPECT_READS__", _inspect_reads_html(reads, patch_paths, repo_root))
    out = out.replace("__FINDING_BLOCK__", finding_block)
    out = out.replace("__INSPECT_RELATION__", esc(default_inspect.get("relation", "")))
    out = out.replace("__INSPECT_TIMING__", esc(default_inspect.get("timing", "")))
    out = out.replace("__INSPECT_FOOT__", esc(default_inspect.get("foot", "")))
    out = out.replace(
        "__FIT_GRAPH_BTN__",
        '<button class="text-action" id="fit-graph">Fit graph <span>↗</span></button>' if op_ids else "",
    )
    out = out.replace(
        "__ALL_OPS_BTN__",
        '<button class="text-action" id="all-operations">All operations <span>↗</span></button>'
        if len(ranked_latest) > 4
        else "",
    )
    out = out.replace("__OPS_ROWS__", "".join(ops_rows))
    out = out.replace("__OPS_FOOT_L__", esc(ops_foot))
    out = out.replace("__EXP_TABLE__", _experiments_table_html(experiments, verification))
    out = out.replace("__TRAIL_EVENTS__", trail_html)
    out = out.replace("__EVIDENCE_ROWS__", "".join(ev_rows))
    out = out.replace("__REPORT_SECTION__", _report_section_html(md_text, verification))
    out = out.replace("__ENV_ROWS__", env_rows)
    out = out.replace(
        "__FOOTER_STATS__",
        esc(f"Graph mapping: {graph['mapped']}/{min(len(op_ids), 4)} · Waves: {len(waves)} · Dropped: {dropped_total}"),
    )
    out = out.replace("__ART_MD__", esc(art_md))
    out = out.replace("__ART_JSON__", esc(art_json))
    out = out.replace("__BOOT_JSON__", json.dumps(boot))
    out = out.replace("__STYLE__", css + "\n.state.bad{color:var(--pressure)}")
    out = out.replace("__APP_JS__", js)
    return out
