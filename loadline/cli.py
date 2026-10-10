"""Loadline CLI."""

from __future__ import annotations

import argparse
import json
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
from loadline.ui.run_console import RunConsole


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


def report_show(run_dir: Path, *, as_json: bool = False) -> int:
    run_dir = run_dir.resolve()
    md = run_dir / "report.md"
    js = run_dir / "report.json"
    home = loadline_home().resolve()
    if not str(run_dir).startswith(str(home)):
        print(f"warning: run_dir is outside {home}", file=sys.stderr)
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
        help="Short baseline warmup/measure durations (harness and integration tests).",
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
    report_p = sub.add_parser("report", help="Show a finished run report.")
    report_sub = report_p.add_subparsers(dest="report_cmd")
    show_p = report_sub.add_parser("show", help="Print report.md from a run directory.")
    show_p.add_argument("run_dir", type=Path)
    show_p.add_argument("--json", action="store_true", help="Print report.json instead.")
    skills_p = sub.add_parser("skills")
    skills_p.add_argument("skills_args", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    if args.version:
        print(__version__)
        return 0
    if args.command == "doctor":
        return doctor(cleanup=args.cleanup, check_model=args.check_model)
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
            args.repo.resolve(),
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
    if args.command == "report" and args.report_cmd == "show":
        return report_show(args.run_dir, as_json=args.json)
    if args.command == "skills":
        from loadline.skills.commands import main_skills

        return main_skills(args.skills_args or ["status"])
    parser.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
