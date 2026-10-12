"""Loadline CLI."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from dotenv import load_dotenv

from loadline import __version__
from loadline.boot import analyze_boot_json
from loadline.core.auth import require_model_auth
from loadline.discovery.intake import discover_capabilities, discover_profile
from loadline.entire_runtime.analyze import analyze_repository
from loadline.entire_runtime.errors import EntireSetupError, GraphInvocationError
from loadline.entire_runtime.graph import GraphClient
from loadline.entire_runtime.install import ensure_toolchain, git_version
from loadline.entire_runtime.manifest import CLI_VERSION, GRAPH_VERSION, declared_platforms
from loadline.paths import loadline_home
from loadline.run_pipeline import emit_run_result, run_loadline
from loadline.ui.render import is_tty
from loadline.ui.run_console import RunConsole

_PICKER_LIMIT = 15
_WIN_DRIVE = re.compile(r"^([A-Za-z]):[\\/](.*)$")


def normalize_user_repo_path(raw: Path | str) -> Path:
    """Map a Windows drive path to /mnt/<letter> when that mount exists in WSL."""
    text = "".join(part.strip() for part in str(raw).replace("\r", "\n").split("\n")).strip()
    match = _WIN_DRIVE.match(text)
    if match:
        letter = match.group(1).lower()
        rest = match.group(2).replace("\\", "/")
        mounted = Path(f"/mnt/{letter}") / rest
        literal = Path(text)
        if not literal.exists() and mounted.exists():
            return mounted.resolve()
    return Path(text).resolve()


def _print_setup_error(exc: EntireSetupError) -> int:
    print(f"error: {exc}", file=sys.stderr)
    print(f"repair: {exc.repair}", file=sys.stderr)
    return 2


def doctor(*, cleanup: bool = False, check_model: bool = False) -> int:
    git = git_version()
    if git is None:
        print("git: missing")
        print("repair: Install Git 2.36 or newer. Entire Graph requires it.")
        return 2
    print(f"git: {'.'.join(str(part) for part in git)}")
    print(f"platforms: {declared_platforms()}")
    if check_model:
        print("warning: --check-model may incur provider charges.")
        err = require_model_auth()
        if err:
            print(f"model: missing ({err.env_var})")
            return 2
        print("model: configured")
    if cleanup:
        from loadline.adapters.runtime.docker_runner import docker_cmd

        proc = docker_cmd(["ps", "-aq", "--filter", "label=loadline.run"])
        ids = [x for x in (proc.stdout or "").split() if x]
        if ids:
            docker_cmd(["rm", "-f", *ids])
        for kind in ("network", "volume"):
            proc2 = docker_cmd([kind, "ls", "-q", "--filter", "label=loadline.run"])
            extra = [x for x in (proc2.stdout or "").split() if x]
            if extra:
                docker_cmd(["rm", *extra])
                ids.extend(extra)
        print(f"cleanup: removed {len(ids)} labelled objects")
    try:
        toolchain = ensure_toolchain()
    except EntireSetupError as exc:
        return _print_setup_error(exc)
    print(f"entire_cli: {toolchain.cli_version} ({toolchain.source})")
    print(f"entire_path: {toolchain.entire}")
    print(f"entire_graph: {toolchain.graph_version}")
    if toolchain.cli_version != CLI_VERSION or toolchain.graph_version != GRAPH_VERSION:
        print("error: installed versions do not match the pinned manifest")
        return 2
    try:
        client = GraphClient(toolchain)
        caps = client.capabilities()
    except GraphInvocationError as exc:
        print(f"graph_capabilities: unavailable ({exc})")
        print("repair: Run `loadline doctor` again. Coverage is degraded until capabilities succeed.")
        return 2
    relations = caps.get("supported_relation_types") or []
    print(f"graph_relations: {len(relations)}")
    print(f"handles_route: {'HANDLES_ROUTE' in relations}")
    if "HANDLES_ROUTE" not in relations:
        print("coverage: degraded (HANDLES_ROUTE is absent; route mapping cannot use that relation)")
    else:
        print("coverage: ready")
    print("repair: none")
    return 0


def analyze(
    repo: Path,
    openapi: Path | None,
    live: bool,
    *,
    boot: bool = False,
    as_json: bool = False,
    require_auth: bool = True,
) -> int:
    if boot:
        boot_console = RunConsole(
            json_mode=False,
            quiet=False,
            verbose=False,
            no_color=False,
        )
        doc, code = analyze_boot_json(repo, require_auth=require_auth, console=boot_console)
        print(json.dumps(doc, indent=2))
        return code
    if as_json and not boot:
        profile = discover_profile(repo)
        caps = discover_capabilities(profile)
        print(json.dumps({"profile": profile, "capabilities": caps}, indent=2))
        return 0
    try:
        report = analyze_repository(repo, openapi=openapi, live_openapi=live)
    except EntireSetupError as exc:
        return _print_setup_error(exc)
    except (GraphInvocationError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    payload = {
        "repo": report.repo,
        "entire_cli": report.cli_version,
        "entire_graph": report.graph_version,
        "toolchain": report.toolchain_source,
        "dirty": report.dirty,
        "ranked_command": report.ranked_command,
        "handles_route": report.handles_route,
        "degraded": report.degraded,
        "routes": [
            {
                "method": item.method,
                "path": item.path,
                "provenance": item.provenance,
                "handler_file": item.handler_file,
                "start_line": item.start_line,
                "end_line": item.end_line,
                "source_read": item.source_read,
                "relation": item.relation,
                "note": item.note,
            }
            for item in report.routes
        ],
    }
    print(json.dumps(payload, indent=2))
    return 0


def report_show(run_dir: Path, *, as_json: bool = False, dashboard: bool = False) -> int:
    run_dir = run_dir.resolve()
    md = run_dir / "report.md"
    js = run_dir / "report.json"
    home = loadline_home().resolve()
    if not str(run_dir).startswith(str(home)):
        print(f"warning: run_dir is outside {home}", file=sys.stderr)
    if dashboard and not as_json:
        from loadline.ui.dashboard_tty import build_dashboard_text

        text = build_dashboard_text(run_dir, None)
        if not text.strip():
            print("dashboard: not measured (no run artifacts)", file=sys.stderr)
            return 2
        print(text)
        return 0
    if as_json:
        if not js.is_file():
            print(f"error: missing {js}", file=sys.stderr)
            return 2
        print(js.read_text())
        return 0
    if not md.is_file():
        print(f"error: missing {md}", file=sys.stderr)
        return 2
    print(md.read_text())
    return 0


def dashboard_cmd(
    *,
    run: str | None,
    repo: str | None,
    as_json: bool,
    serve: bool = False,
    port: int = 8123,
    no_browser: bool = False,
    export: Path | None = None,
) -> int:
    """Browse past runs (read-only) and render one terminal dashboard."""
    import sys as _sys

    from loadline.ui.dashboard_tty import build_dashboard_text
    from loadline.ui.run_index import age_string, match_runs, scan_runs

    home = loadline_home().resolve()
    summaries = scan_runs(home / "runs", repo_filter=repo)
    if serve:
        from loadline.dashboard.server import serve as _serve

        picked: str | None = None
        if run:
            hits = match_runs(summaries, run)
            if not hits:
                print(f"error: no run matches {run!r}", file=_sys.stderr)
                return 2
            if len(hits) > 1:
                print(f"error: ambiguous run prefix {run!r}:", file=_sys.stderr)
                for hit in hits[:10]:
                    print(f"  {hit.run_id}  {hit.repo_name}", file=_sys.stderr)
                return 2
            picked = hits[0].run_id
        return _serve(home, port, open_browser=not no_browser, run_id=picked)
    if export is not None:
        from loadline.dashboard.render import render_run_page

        if not run:
            print("error: --export requires --run <id>", file=_sys.stderr)
            return 2
        hits = match_runs(summaries, run)
        if len(hits) != 1:
            print(f"error: no single run matches {run!r}", file=_sys.stderr)
            return 2
        page = render_run_page(hits[0].run_dir, hits[0].run_id, serve=False)
        if not page:
            print("dashboard: not measured (no run artifacts)", file=_sys.stderr)
            return 2
        export.write_text(page, encoding="utf-8")
        print(f"dashboard: wrote {export} ({len(page) // 1024} KB)")
        return 0
    if as_json:
        print(
            json.dumps(
                [
                    {
                        "run_id": s.run_id,
                        "run_dir": str(s.run_dir),
                        "repo": s.repo_root,
                        "state": s.state,
                        "peak_rps": s.peak_rps,
                        "waves": s.waves,
                        "dropped": s.dropped,
                    }
                    for s in summaries
                ],
                indent=2,
            )
        )
        return 0

    def _render(pick_run_id: str, pick_dir: Path) -> int:
        text = build_dashboard_text(pick_dir, pick_run_id, full=True)
        if not text.strip():
            print("dashboard: not measured (no run artifacts)", file=_sys.stderr)
            return 2
        print(text)
        return 0

    if run:
        hits = match_runs(summaries, run)
        if not hits:
            print(f"error: no run matches {run!r}", file=_sys.stderr)
            return 2
        if len(hits) > 1:
            print(f"error: ambiguous run prefix {run!r}:", file=_sys.stderr)
            for hit in hits[:10]:
                print(f"  {hit.run_id}  {hit.repo_name}", file=_sys.stderr)
            return 2
        return _render(hits[0].run_id, hits[0].run_dir)

    if not summaries:
        print("dashboard: no runs recorded yet", file=_sys.stderr)
        return 2
    header = f"  {'#':>3}  {'RUN':<12}  {'REPO':<28}  {'STATE':<24}  {'PEAK':>8}  WAVES  DROPPED  WHEN"
    rows = [header]
    for i, s in enumerate(summaries[:_PICKER_LIMIT], start=1):
        peak = f"{s.peak_rps:g}rps" if s.peak_rps is not None else "-"
        rows.append(
            f"  {i:>3}  {s.run_id:<12}  {s.repo_name[:28]:<28}  {s.state[:24]:<24}  "
            f"{peak:>8}  {s.waves:<5}  {s.dropped:<7}  {age_string(s.mtime)}"
        )
    if len(summaries) > _PICKER_LIMIT:
        rows.append(f"  +{len(summaries) - _PICKER_LIMIT} older (refine with --repo)")
    print("\n".join(rows))
    if not is_tty(_sys.stdin):
        print("pass --run <id> to render (non-interactive output)", file=_sys.stderr)
        return 2
    try:
        choice = input("select [1]: ").strip()
    except EOFError:
        return 2
    except KeyboardInterrupt:
        print("", file=_sys.stderr)
        return 130
    if not choice:
        pick = summaries[0]
    elif choice.isdigit():
        idx = int(choice)
        if idx < 1 or idx > min(len(summaries), _PICKER_LIMIT):
            print(f"error: selection {idx} out of range", file=_sys.stderr)
            return 2
        pick = summaries[idx - 1]
    else:
        hits = match_runs(summaries, choice)
        if len(hits) != 1:
            print(f"error: no single run matches {choice!r}", file=_sys.stderr)
            return 2
        pick = hits[0]
    return _render(pick.run_id, pick.run_dir)


def main(argv: list[str] | None = None) -> int:
    load_dotenv()
    parser = argparse.ArgumentParser(
        prog="loadline",
        description="Capacity investigation for containerized apps. See tech_doc.md §16.2 for exit codes.",
    )
    parser.add_argument("--version", action="store_true")
    sub = parser.add_subparsers(dest="command")
    doc = sub.add_parser("doctor")
    doc.add_argument("--cleanup", action="store_true")
    doc.add_argument("--check-model", action="store_true")
    analyze_parser = sub.add_parser("analyze")
    analyze_parser.add_argument("repo", nargs="?", type=Path, default=Path("."))
    analyze_parser.add_argument("--openapi", type=Path)
    analyze_parser.add_argument("--live-openapi", action="store_true")
    analyze_parser.add_argument("--boot", action="store_true")
    analyze_parser.add_argument("--json", action="store_true")
    run_p = sub.add_parser(
        "run",
        help="Boot target repo, baseline load, and investigate.",
        epilog="Example: loadline run --repo ./myapp",
    )
    run_p.add_argument("--repo", type=Path, default=Path("."))
    run_p.add_argument(
        "--skip-investigator",
        action="store_true",
        help="Skip the LLM investigator (integration tests only).",
    )
    run_p.add_argument(
        "--fast",
        action="store_true",
        help="Shorter investigator load: lower max rate, fewer run_k6 calls, 15s measure cap.",
    )
    run_p.add_argument("--json", action="store_true", help="Emit one JSON object on stdout at end.")
    run_p.add_argument("--quiet", action="store_true", help="Errors only on stderr; hides investigate tool trace.")
    run_p.add_argument(
        "--verbose",
        action="store_true",
        help="Boot sub-steps, longer tool args, and more frequent ledger lines during investigate.",
    )
    run_p.add_argument("--no-color", action="store_true", help="Disable ANSI colors.")
    run_p.add_argument("--no-report-print", action="store_true", help="Do not print report.md to stdout.")
    load_p = sub.add_parser(
        "load",
        help="Figure out config, try a boot, write config, tear down.",
    )
    load_p.add_argument("--repo", type=Path, default=Path("."))
    load_p.add_argument(
        "--write-to-repo",
        action="store_true",
        help="Also copy the generated config to repo .loadline.yaml.",
    )
    load_p.add_argument(
        "--refresh",
        action="store_true",
        help="Write loadline.proposed.yaml and print diff instead of overwriting.",
    )
    load_p.add_argument("--quiet", action="store_true", help="Errors only on stderr; hide progress.")
    report_p = sub.add_parser("report", help="Show a finished run report.")
    report_sub = report_p.add_subparsers(dest="report_cmd")
    show_p = report_sub.add_parser("show", help="Print report.md from a run directory.")
    show_p.add_argument("run_dir", type=Path)
    show_p.add_argument("--json", action="store_true", help="Print report.json instead.")
    show_p.add_argument("--dashboard", action="store_true", help="Render terminal dashboard instead.")
    skills_p = sub.add_parser("skills")
    skills_p.add_argument("skills_args", nargs=argparse.REMAINDER)
    dash_p = sub.add_parser("dashboard", help="Browse past runs and render a terminal dashboard.")
    dash_p.add_argument("--run", help="Run id or unambiguous id prefix.")
    dash_p.add_argument("--repo", help="Filter the picker by repo path substring.")
    dash_p.add_argument("--json", action="store_true", help="Emit the run index as JSON.")
    dash_p.add_argument("--serve", action="store_true", help="Serve the web dashboard on localhost.")
    dash_p.add_argument("--port", type=int, default=8123, help="Port for --serve (default 8123).")
    dash_p.add_argument("--no-browser", action="store_true", help="Do not auto-open a browser with --serve.")
    dash_p.add_argument("--export", type=Path, help="Write a self-contained dashboard HTML file (use with --run).")
    verify_p = sub.add_parser(
        "verify",
        help="Replay the cited k6 call. Open a pull request only if that metric moved.",
    )
    verify_p.add_argument("run_dir", type=Path)
    verify_p.add_argument("--no-pr", action="store_true", help="Write verification.json and do not push.")
    verify_p.add_argument(
        "--i-am-patching-loadline",
        action="store_true",
        help="Allow verify to patch the Loadline repository. The demo does not use this.",
    )
    args = parser.parse_args(argv)
    if args.version:
        print(__version__)
        return 0
    if args.command == "doctor":
        return doctor(cleanup=args.cleanup, check_model=args.check_model)
    if args.command == "load":
        from loadline.load import load_repo

        load_console = RunConsole(quiet=args.quiet, verbose=False, json_mode=False)
        return load_repo(
            normalize_user_repo_path(args.repo),
            write_to_repo=args.write_to_repo,
            refresh=args.refresh,
            console=load_console,
        )
    if args.command == "analyze":
        if args.live_openapi and args.openapi is None:
            print("error: --live-openapi requires --openapi", file=sys.stderr)
            return 2
        return analyze(
            args.repo,
            args.openapi,
            args.live_openapi,
            boot=args.boot,
            as_json=args.json,
            require_auth=args.boot,
        )
    if args.command == "run":
        console = RunConsole(
            json_mode=args.json,
            quiet=args.quiet,
            verbose=args.verbose,
            no_color=args.no_color,
        )
        result = run_loadline(
            normalize_user_repo_path(args.repo),
            skip_investigator=args.skip_investigator,
            fast_baseline=args.fast,
            require_auth=True,
            console=console,
        )
        emit_run_result(
            result,
            console,
            print_report=not args.no_report_print and not args.json,
        )
        return result.exit_code
    if args.command == "verify":
        from loadline.verify_cmd import verify_run

        return verify_run(
            args.run_dir,
            open_pr=not args.no_pr,
            allow_loadline_repo=args.i_am_patching_loadline,
        )
    if args.command == "report" and args.report_cmd == "show":
        return report_show(args.run_dir, as_json=args.json, dashboard=args.dashboard)
    if args.command == "dashboard":
        return dashboard_cmd(
            run=args.run,
            repo=args.repo,
            as_json=args.json,
            serve=args.serve,
            port=args.port,
            no_browser=args.no_browser,
            export=args.export,
        )
    if args.command == "skills":
        from loadline.skills.commands import main_skills

        return main_skills(args.skills_args or ["status"])
    if args.command is None and is_tty(sys.stdin) and is_tty(sys.stdout):
        from loadline.ui.workspace import run_workspace

        return run_workspace(normalize=normalize_user_repo_path)
    parser.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
