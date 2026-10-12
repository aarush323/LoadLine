"""Interactive Loadline workspace (TTY only). Calls existing load/run/verify."""

from __future__ import annotations

import sys
from collections.abc import Callable
from pathlib import Path
from typing import TextIO

from loadline.run_pipeline import RunPipelineResult, emit_run_result, run_loadline
from loadline.ui.render import is_tty
from loadline.ui.run_console import RunConsole
from loadline.ui.toggle import toggle_choice

PINK = "#F5A3C7"
PURPLE = "#C77DFF"
VIOLET = "#8872B5"

LoadFn = Callable[[Path], int]
RunFn = Callable[[Path], RunPipelineResult]
VerifyFn = Callable[[Path, bool], int]
PathFn = Callable[[Path], Path | None]
ToggleFn = Callable[[str, list[str]], int | None]


def workspace_available(stdin: TextIO | None = None, stdout: TextIO | None = None) -> bool:
    return is_tty(stdin or sys.stdin) and is_tty(stdout or sys.stdout)


def render_home(repo: Path, *, file: TextIO | None = None) -> str:
    """Return the home panel text (also printed)."""
    from rich.console import Console
    from rich.panel import Panel
    from rich.text import Text

    body = Text()
    body.append("LOADLINE", style=f"bold {PINK}")
    body.append("\n")
    body.append("capacity with evidence", style=f"italic {VIOLET}")
    body.append("\n\n")
    body.append(
        "Point it at a runnable repository. Loadline boots it, measures under load,\n"
        "and writes an evidence-backed report.\n",
        style="white",
    )
    body.append("\n")
    body.append("Repository\n", style=f"bold {PURPLE}")
    body.append(str(repo), style=PINK)
    body.append("\n\n")
    body.append("enter", style=f"bold {PINK}")
    body.append(" load   ", style="dim")
    body.append("q", style=f"bold {PINK}")
    body.append(" quit   ·  loadline run / verify still work as commands", style="dim")
    panel = Panel(
        body,
        border_style=PURPLE,
        padding=(1, 2),
        title="[bold]loadline[/bold]",
        title_align="left",
        subtitle="local workspace",
        subtitle_align="right",
    )
    console = Console(file=file or sys.stderr, highlight=False, color_system="truecolor")
    console.print(panel)
    return str(repo)


def ask_repo_path(default: Path, *, input_fn: Callable[[str], str] | None = None) -> Path | None:
    prompt = f"Repository path [{default}]: "
    try:
        raw = input_fn(prompt) if input_fn is not None else input(prompt)
    except EOFError:
        return None
    text = (raw or "").strip()
    if text.lower() in ("q", "quit"):
        return None
    if not text:
        return default
    return Path(text)


def run_session(
    repo: Path,
    *,
    load_fn: LoadFn | None = None,
    run_fn: RunFn | None = None,
    verify_fn: VerifyFn | None = None,
    toggle_fn: ToggleFn | None = None,
) -> int:
    """Load → optional run → optional verify. Uses the run_dir from this run only."""
    from loadline.load_cmd import load_repository
    from loadline.verify_cmd import verify_run

    load = load_fn or load_repository
    run = run_fn or _run_investigation
    verify = verify_fn or (lambda path, open_pr: verify_run(path, open_pr=open_pr))
    choose = toggle_fn or (lambda q, opts: toggle_choice(q, opts, default=0))

    print("— load —", file=sys.stderr)
    load_code = load(repo)
    if load_code != 0:
        print("Load did not finish. Investigation was not started.", file=sys.stderr)
        return load_code

    run_pick = choose("Load finished. Run the investigation?", ["Yes", "No"])
    if run_pick != 0:
        print("Stopped after load.", file=sys.stderr)
        return 0

    print("— run —", file=sys.stderr)
    result = run(repo)
    if result.exit_code != 0 or result.run_dir is None:
        print(
            f"Run did not finish (status={result.status or 'unknown'}). Verify was not started.",
            file=sys.stderr,
        )
        return result.exit_code if result.exit_code else 2

    rid = result.run_id or result.run_dir.name
    pr_pick = choose(
        f"Verify run {rid}?",
        ["With pull request", "Without pull request"],
    )
    if pr_pick is None:
        print("Stopped before verify.", file=sys.stderr)
        return 0
    open_pr = pr_pick == 0
    print("— verify —", file=sys.stderr)
    verify_code = verify(result.run_dir, open_pr)
    print(
        f"run_id: {rid}\n"
        f"run_dir: {result.run_dir}\n"
        "dashboard: loadline dashboard --serve",
        file=sys.stderr,
    )
    return verify_code


def _run_investigation(repo: Path) -> RunPipelineResult:
    console = RunConsole(json_mode=False, quiet=False, verbose=False, no_color=False)
    result = run_loadline(repo, require_auth=True, console=console)
    emit_run_result(result, console, print_report=True)
    return result


def run_workspace(
    *,
    default_repo: Path | None = None,
    normalize: Callable[[Path | str], Path] | None = None,
    ask_path: PathFn | None = None,
    load_fn: LoadFn | None = None,
    run_fn: RunFn | None = None,
    verify_fn: VerifyFn | None = None,
    toggle_fn: ToggleFn | None = None,
    draw: bool = True,
) -> int:
    def _plain(path: Path | str) -> Path:
        return Path(path).expanduser().resolve()

    norm = normalize or _plain
    start = norm(default_repo if default_repo is not None else Path.cwd())
    if draw:
        render_home(start)
    chosen = ask_path(start) if ask_path is not None else ask_repo_path(start)
    if chosen is None:
        return 0
    repo = norm(chosen)
    if not repo.exists():
        print(f"error: repository path does not exist: {repo}", file=sys.stderr)
        return 2
    return run_session(
        repo,
        load_fn=load_fn,
        run_fn=run_fn,
        verify_fn=verify_fn,
        toggle_fn=toggle_fn,
    )
