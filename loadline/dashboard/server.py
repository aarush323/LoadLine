"""Served web dashboard (read-only; serves run artifacts over localhost)."""

from __future__ import annotations

import html
import json
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, quote, urlparse

from loadline.dashboard.render import esc, render_run_page
from loadline.paths import loadline_home
from loadline.ui.run_index import age_string, scan_runs


def _verdict_label(summary: Any) -> str:
    verdict = getattr(summary, "verification_verdict", None)
    if verdict:
        return str(verdict).replace("_", " ")
    return "not verified"


def _index_page(home: Path, repo_filter: str | None = None) -> str:
    summaries = scan_runs(home / "runs", repo_filter=repo_filter or None)
    try:
        from loadline.dashboard.render import _DIR as _ddir

        css = (_ddir / "v3_style.css").read_text(encoding="utf-8")
    except OSError:
        css = ""
    filter_value = esc(repo_filter or "")
    filter_form = (
        '<form class="index-filter" method="get" action="/">'
        f'<input type="search" name="repo" value="{filter_value}" '
        'placeholder="Filter by repository…" aria-label="Filter by repository">'
        '<button type="submit" class="btn">Filter</button></form>'
    )
    if summaries:
        rows = "".join(
            f"<tr data-href=\"/runs/{quote(s.run_id)}\" tabindex=\"0\">"
            f"<td class=\"mono\">{esc(s.run_id)}</td>"
            f"<td>{esc(s.repo_name)}</td>"
            f"<td>{esc(s.state.replace('_', ' '))}</td>"
            f"<td>{esc(_verdict_label(s))}</td>"
            f"<td class=\"num\">{esc(f'{s.peak_rps:g} req/s') if s.peak_rps is not None else '—'}</td>"
            f"<td class=\"num\">{s.waves}</td>"
            f"<td class=\"num\">{age_string(s.mtime)}</td></tr>"
            for s in summaries
        )
        table = (
            '<div class="panel"><div class="table-wrap"><table class="ops-table">'
            "<thead><tr><th>Run</th><th>Repository</th><th>State</th><th>Verification</th>"
            "<th>Peak offered</th><th>Waves</th><th>When</th></tr></thead>"
            f"<tbody>{rows}</tbody></table></div></div>"
        )
    else:
        empty = (
            "No runs match this repository filter."
            if repo_filter
            else "No runs recorded yet."
        )
        table = f'<div class="panel"><p class="muted small" style="padding:18px">{esc(empty)}</p></div>'
    return (
        "<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\">"
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        "<title>loadline — runs</title>"
        f"<style>{css}\n.page-narrow{{max-width:1060px;margin:0 auto;padding:34px 28px 60px}}"
        ".run-row{cursor:pointer}tbody tr[data-href]:hover{background:#faf9f4}"
        ".index-filter{display:flex;gap:8px;margin:18px 0 16px;max-width:420px}"
        ".index-filter input{flex:1;min-width:0;padding:8px 10px;border:1px solid var(--rule-strong);"
        "border-radius:7px;background:rgba(255,255,255,.7)}</style></head><body>"
        '<div class="page-narrow"><div class="hero-eyebrow"><span class="eyebrow-line"></span>'
        '<span class="eyebrow">Loadline · run workspace</span></div>'
        '<h1 class="hero-title" style="font-size:38px">Runs carry the <em>evidence.</em></h1>'
        '<p class="hero-sub">Every recorded run across repositories. Select one to open its investigation workspace.</p>'
        f"{filter_form}{table}"
        '<footer class="footer"><span class="footer-brand">Loadline / capacity with evidence</span>'
        f"<span>{len(summaries)} runs · {esc(str(home))}</span></footer></div>"
        "<script>document.querySelectorAll('tr[data-href]').forEach(r=>{"
        "r.addEventListener('click',()=>{location.href=r.dataset.href});"
        "r.addEventListener('keydown',e=>{if(e.key==='Enter'){location.href=r.dataset.href}})})</script>"
        "</body></html>"
    )


class _Handler(BaseHTTPRequestHandler):
    home: Path = loadline_home()

    def log_message(self, *args: Any) -> None:
        pass

    def _send(self, code: int, body: bytes, ctype: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        path = parsed.path
        query = parse_qs(parsed.query)
        if path == "/":
            repo = (query.get("repo") or [""])[0].strip() or None
            self._send(200, _index_page(self.home, repo).encode(), "text/html; charset=utf-8")
            return
        if path == "/api/runs":
            repo = (query.get("repo") or [""])[0].strip() or None
            payload = [
                {"run_id": s.run_id, "repo": s.repo_root, "state": s.state,
                 "peak_rps": s.peak_rps, "waves": s.waves,
                 "verification_verdict": s.verification_verdict}
                for s in scan_runs(self.home / "runs", repo_filter=repo)
            ]
            self._send(200, json.dumps(payload, indent=2).encode(), "application/json")
            return
        parts = [p for p in path.split("/") if p]
        if len(parts) == 2 and parts[0] == "runs":
            run_dir = (self.home / "runs" / parts[1]).resolve()
            if not str(run_dir).startswith(str(self.home.resolve())) or not run_dir.is_dir():
                self._send(404, b"unknown run", "text/plain")
                return
            page = render_run_page(run_dir, run_dir.name, serve=True)
            if not page:
                self._send(404, b"no dashboard for this run", "text/plain")
                return
            self._send(200, page.encode(), "text/html; charset=utf-8")
            return
        if len(parts) == 3 and parts[0] == "artifacts" and parts[2] in ("report.md", "report.json"):
            run_dir = (self.home / "runs" / parts[1]).resolve()
            target = run_dir / parts[2]
            if not str(run_dir).startswith(str(self.home.resolve())) or not target.is_file():
                self._send(404, b"artifact not found", "text/plain")
                return
            ctype = "text/markdown; charset=utf-8" if parts[2].endswith(".md") else "application/json"
            self._send(200, target.read_bytes(), ctype)
            return
        self._send(404, b"not found", "text/plain")


def serve(home: Path, port: int, *, open_browser: bool, run_id: str | None = None) -> int:
    _Handler.home = home
    server = ThreadingHTTPServer(("127.0.0.1", port), _Handler)
    url = f"http://127.0.0.1:{server.server_port}/" + (f"runs/{run_id}" if run_id else "")
    print(f"loadline dashboard: {url}")
    print("serving read-only run artifacts (Ctrl-C to stop)")
    if open_browser:
        threading.Timer(0.4, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0
