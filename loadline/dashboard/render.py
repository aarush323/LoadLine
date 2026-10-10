"""Render the web dashboard from run artifacts (read-only, never writes runs).

Single-file HTML out: the v3 mock's CSS/JS with every illustrative value
replaced by measured run evidence. Gaps render as "Not measured".
"""

from __future__ import annotations

import html
import json
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
            selected = " selected" if op == worst_op else ""
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


def render_run_page(run_dir: Path, run_id: str | None, *, serve: bool = True) -> str:
    """Full single-file dashboard HTML; empty string when nothing to show."""
    run_dir = Path(run_dir)
    if not run_dir.is_dir():
        return ""
    ledger = _ledger_events(run_dir)
    waves = _waves(ledger)
    report = _read_json(run_dir / "report.json")
    if report is None and not waves and not ledger:
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
    if worst_op is not None and worst_op in op_ids:
        # The highest-pressure op must survive the 4-node graph cap below.
        op_ids = [worst_op] + [o for o in op_ids if o != worst_op]

    state = ""
    if isinstance(report, dict):
        state = str(report.get("run_state") or "")
    if not state:
        for e in reversed(ledger):
            if e.get("kind") == "report_written":
                state = str(e.get("run_state") or "")
                break
    state = state or ("completed" if waves else "unknown")
    state_label = {"completed": "Complete", "investigation_incomplete": "Investigation incomplete"}.get(state, state.replace("_", " ").title())
    state_bad = state not in ("completed",)

    # ---------------- hero ----------------
    if waves and worst_op is not None:
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
        hero_title = "No load was measured on this run."
        hero_sub = "The ledger holds no k6 waves. Interpret run state and coverage below."
    chips = "".join(
        [_chip(f"RUN {rid}"), _chip(repo_name)]
        + ([_chip(f"COMMIT {sha}")] if sha else [])
        + ([_chip(f"{len(waves)} K6 WAVES")] if waves else [])
        + [_chip(state_label.upper())]
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
    if findings:
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
    graph_svg = _graph_svg(graph, op_ids, op_labels, op_p95, exp_of, worst_op) if op_ids else '<div class="graph-canvas"><p class="muted small" style="padding:18px">No operations were load-tested on this run.</p></div>'
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
            "foot": "Measured operation · selected" if op_id == worst_op else "Measured operation",
            "finding": (findings[0].get("symptom") or findings[0].get("mechanism") or "Finding recorded.") if findings else "No finding was recorded on this run.",
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
    worst_node = f"op_{op_ids[:4].index(worst_op)}" if worst_op in op_ids[:4] else None
    if worst_node is not None and worst_node in node_data:
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
    else:
        finding_id, finding_state = "—", "none recorded"
        finding_title = "No finding was recorded on this run."
        finding_body = "The ledger holds measurements but no agent finding. Interpret the curves directly."
        finding_links = "".join(f'<span class="evidence-link">{esc(w.get("experiment_id") or "")}</span>' for w in waves[:3])
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
        ops_rows.append(
            f'<tr class="{"active-row" if idx == 0 else ""}" data-op="{idx}" tabindex="0">'
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
    out = out.replace("__STATE_PILL__",
                      f"<i class=\"state-dot\"></i> {esc(state_label)}" if not state_bad
                      else f"<span class=\"state bad\"><i class=\"state-dot\"></i> {esc(state_label)}</span>")
    out = out.replace("__REPO_NAME__", esc(repo_name))
    out = out.replace("__REPO_META__", esc(f"{repo_root} · {sha or 'no sha'}"))
    out = out.replace("__NAV_COUNT__", nav_count)
    out = out.replace("__HERO_EYEBROW__", esc(f"Run · {_fmt_date(first_ts)} · {repo_name}"))
    out = out.replace("__HERO_TITLE__", hero_title)
    out = out.replace("__HERO_SUB__", esc(hero_sub))
    out = out.replace("__META_CHIPS__", chips)
    out = out.replace("__METRICS__", metrics)
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
    facts = "".join(
        f'<div class="fact"><span>{label}</span><strong{" class=\"hot\"" if hot_key and default_inspect.get(hot_key) not in (None, "Not measured") and hot else ""}>{esc(default_inspect.get(key, ""))}</strong></div>'
        for label, key, hot_key, hot in (
            ("Operation p95 at peak", "p95", "hot", bool(default_inspect.get("hot"))),
            ("Evidence anchors", "evidence", None, False),
        )
    )
    out = out.replace("__INSPECT_FACTS__", facts)
    out = out.replace("__FINDING_ID__", esc(finding_id))
    out = out.replace("__FINDING_STATE__", esc(finding_state))
    out = out.replace("__FINDING_TITLE__", esc(finding_title))
    out = out.replace("__FINDING_BODY__", esc(finding_body))
    out = out.replace("__FINDING_LINKS__", finding_links)
    out = out.replace("__INSPECT_RELATION__", esc(default_inspect.get("relation", "")))
    out = out.replace("__INSPECT_TIMING__", esc(default_inspect.get("timing", "")))
    out = out.replace("__INSPECT_FOOT__", esc(default_inspect.get("foot", "")))
    out = out.replace("__OPS_ROWS__", "".join(ops_rows))
    out = out.replace("__OPS_FOOT_L__", esc(ops_foot))
    out = out.replace("__TRAIL_EVENTS__", trail_html)
    out = out.replace("__EVIDENCE_ROWS__", "".join(ev_rows))
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
