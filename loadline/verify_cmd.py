"""loadline verify: replay the cited k6 call and open a PR only if that metric moved."""

from __future__ import annotations

import difflib
import json
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any, Callable

import yaml

from loadline.paths import loadline_home
from loadline.verification import (
    judge_replay,
    metrics_from_experiment,
    patch_rejection,
    path_rejected,
    range_covered,
)

_FENCE = re.compile(r"```(?:ya?ml)?\s*\n(loadline_fix:\n.*?)(?:```|\Z)", re.S | re.I)
_METRICS = frozenset({"p95_ms", "error_rate", "achieved_rps"})
_HEALTHY_P95_MS = 50.0
_HEALTHY_ERROR_RATE = 0.05

PatchRunner = Callable[[dict[str, Any], str, dict[str, Any]], str]
ReplayRunner = Callable[[Path, dict[str, Any]], dict[str, Any]]
PushRunner = Callable[[Path, dict[str, Any]], tuple[bool, str | None]]


def parse_fix_fence(report_text: str) -> dict[str, Any] | None:
    matches = list(_FENCE.finditer(report_text or ""))
    if not matches:
        return None
    loaded = yaml.safe_load(matches[-1].group(1))
    if not isinstance(loaded, dict):
        return None
    fix = loaded.get("loadline_fix")
    return fix if isinstance(fix, dict) else None


def _load_reads(run_dir: Path) -> list[dict[str, Any]]:
    path = run_dir / "reads.jsonl"
    if not path.is_file():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        item = json.loads(line)
        if isinstance(item, dict):
            rows.append(item)
    return rows


def _contract_error(run_dir: Path, fix: dict[str, Any] | None) -> str | None:
    if not fix:
        return "report has no loadline_fix fence"
    required = (
        "experiment_id",
        "operation_id",
        "metric",
        "direction",
        "control_operation_id",
        "path",
        "start_line",
        "end_line",
    )
    missing = [key for key in required if fix.get(key) in (None, "")]
    if missing:
        return f"fence missing {missing}"
    metric = str(fix["metric"])
    direction = str(fix["direction"])
    if metric not in _METRICS:
        return "metric is not measured"
    expected = "increase" if metric == "achieved_rps" else "decrease"
    if direction != expected:
        return "direction does not match the metric"
    path = str(fix["path"])
    if path_rejected(path):
        return path_rejected(path)
    exp_path = run_dir / "experiments" / f"{fix['experiment_id']}.json"
    if not exp_path.is_file():
        return "experiment file is missing"
    experiment = json.loads(exp_path.read_text(encoding="utf-8"))
    ops = (experiment.get("output") or {}).get("operations") or {}
    if not isinstance(ops, dict) or str(fix["operation_id"]) not in ops:
        return "operation is missing from the experiment"
    row = ops[str(fix["operation_id"])]
    if not isinstance(row, dict) or row.get(metric) is None:
        return "per-operation metric is missing"
    try:
        start = int(fix["start_line"])
        end = int(fix["end_line"])
    except (TypeError, ValueError):
        return "line range is not numeric"
    if end < start:
        return "line range is empty"
    if not range_covered(path, start, end, _load_reads(run_dir)):
        return "path is not covered by reads.jsonl"
    return None


def _cited_was_healthy(experiment: dict[str, Any], operation_id: str, metric: str) -> bool:
    """A stored call that already looked fine is not turned into a harder replay."""
    if metric != "p95_ms":
        return False
    row = metrics_from_experiment(experiment, operation_id)
    p95 = row.get("p95_ms")
    err = row.get("error_rate")
    if p95 is None or err is None:
        return False
    dropped = int((experiment.get("output") or {}).get("dropped_iterations") or 0)
    return float(p95) < _HEALTHY_P95_MS and float(err) < _HEALTHY_ERROR_RATE and dropped == 0


def _endpoint(experiment: dict[str, Any], operation_id: str) -> dict[str, Any]:
    for ep in (experiment.get("input") or {}).get("endpoints") or []:
        if isinstance(ep, dict) and str(ep.get("id")) == operation_id:
            return {"method": ep.get("method") or "GET", "path": ep.get("path") or ""}
    return {"method": "", "path": ""}


def _snippet(repo: Path, path: str, start: int, end: int) -> str:
    target = repo / path
    if not target.is_file():
        return ""
    lines = target.read_text(encoding="utf-8", errors="ignore").splitlines()
    start = max(1, int(start) - 20)
    end = min(len(lines), int(end) + 20)
    return "\n".join(f"{i}:{lines[i - 1]}" for i in range(start, end + 1))


def _git(repo: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        check=check,
        capture_output=True,
        text=True,
    )


def _is_loadline_hint(path: str) -> bool:
    return path.replace("\\", "/").strip('"') in {".loadline.yaml"}


def _line_ending_only_dirty(repo: Path) -> bool:
    unstaged = _git(repo, "diff", "--ignore-cr-at-eol", "--stat", check=False).stdout.strip()
    staged = _git(repo, "diff", "--cached", "--ignore-cr-at-eol", "--stat", check=False).stdout.strip()
    return not unstaged and not staged


def _restore_line_ending_only_changes(repo: Path) -> None:
    _git(repo, "checkout", "--", ".", check=False)


def _worktree_blocks_patch(repo: Path) -> bool:
    out = _git(repo, "status", "--porcelain", check=False).stdout
    blocking: list[str] = []
    untracked: list[str] = []
    for line in out.splitlines():
        path = line[3:].strip()
        if " -> " in path:
            path = path.split(" -> ", 1)[1]
        if _is_loadline_hint(path):
            continue
        if line.startswith("??"):
            untracked.append(path)
            continue
        blocking.append(path)
    if untracked:
        return True
    if not blocking:
        return False
    if _line_ending_only_dirty(repo):
        _restore_line_ending_only_changes(repo)
        return False
    return True


def _is_loadline_repo(repo: Path) -> bool:
    here = Path(__file__).resolve().parents[1]
    return repo.resolve() == here.resolve()


def _blank_doc(run_id: str, fix: dict[str, Any] | None, experiment: dict[str, Any] | None) -> dict[str, Any]:
    fix = fix or {}
    experiment = experiment or {}
    tool_input = experiment.get("input") or {}
    op_id = str(fix.get("operation_id") or "")
    before = metrics_from_experiment(experiment, op_id) if experiment else {}
    control_id = str(fix.get("control_operation_id") or "")
    control_before = metrics_from_experiment(experiment, control_id) if experiment and control_id else {}
    if not control_before.get("p95_ms") and control_before.get("error_rate") is None:
        control_before = {}
    return {
        "schema_version": "loadline-verification/1",
        "source_run_id": run_id,
        "experiment_id": str(fix.get("experiment_id") or ""),
        "operation_id": op_id,
        "control_operation_id": control_id,
        "metric": str(fix.get("metric") or ""),
        "direction": str(fix.get("direction") or ""),
        "rate": tool_input.get("rate"),
        "duration_s": tool_input.get("duration_s"),
        "endpoint": _endpoint(experiment, op_id) if experiment else {},
        "before": {"experiment_id": str(fix.get("experiment_id") or ""), **before},
        "after": {},
        "control_before": control_before,
        "control_after": {},
        "verdict": "no_verifiable_fix",
        "reason": "",
        "pr_opened": False,
        "pr_url": None,
        "branch": "",
        "patch_paths": [],
        "replay_run_id": "",
    }


def render_comparison(doc: dict[str, Any]) -> str:
    before = doc.get("before") or {}
    after = doc.get("after") or {}
    control_before = doc.get("control_before") or {}
    control_after = doc.get("control_after") or {}
    endpoint = doc.get("endpoint") or {}
    call = f"{endpoint.get('method') or ''} {endpoint.get('path') or ''}".strip()
    control_name = str(doc.get("control_operation_id") or "")

    def ms(value: Any) -> str:
        if value is None or value == "":
            return "not measured"
        return f"{float(value):.0f} ms"

    def rate(value: Any) -> str:
        if value is None or value == "":
            return "not measured"
        return f"{float(value):.2f}"

    lines = [
        "",
        "## Verification",
        "",
        f"Verdict: {doc.get('verdict')}",
        "",
        "| | Before | After |",
        "|---|---|---|",
        f"| Experiment | {doc.get('experiment_id')} | {(after.get('experiment_id') or '')} |",
        f"| Call | {call} | {call} |",
        f"| Offered rate | {doc.get('rate')} req/s | {doc.get('rate')} req/s |",
        f"| Duration | {doc.get('duration_s')} s | {doc.get('duration_s')} s |",
        f"| p95 | {ms(before.get('p95_ms'))} | {ms(after.get('p95_ms'))} |",
        f"| Error rate | {rate(before.get('error_rate'))} | {rate(after.get('error_rate'))} |",
        f"| Achieved | {rate(before.get('achieved_rps'))} req/s | {rate(after.get('achieved_rps'))} req/s |",
        (
            f"| Control {control_name} p95 | {ms(control_before.get('p95_ms'))} | "
            f"{ms(control_after.get('p95_ms'))} |"
        ),
        "",
        (
            f"Before numbers are copied from experiments/{doc.get('experiment_id')}.json. "
            "After numbers are copied from the replay experiment. "
            "The investigator's earlier prose is not a measurement."
        ),
        "",
    ]
    if doc.get("reason"):
        lines.insert(5, str(doc["reason"]))
        lines.insert(6, "")
    return "\n".join(lines)


def render_pr_body(doc: dict[str, Any]) -> str | None:
    if doc.get("verdict") != "improved":
        return None
    before = doc.get("before") or {}
    after = doc.get("after") or {}
    endpoint = doc.get("endpoint") or {}
    metric = str(doc.get("metric") or "p95_ms")
    call = f"{endpoint.get('method') or 'GET'} {endpoint.get('path') or ''}".strip()
    sentence = (
        f"{call} {metric} moved from {before.get(metric)} to {after.get(metric)} "
        f"at {doc.get('rate')} req/s for {doc.get('duration_s')} s."
    )
    return "\n".join(
        [
            sentence,
            "",
            render_comparison(doc).strip(),
            "",
            f"Source run: {doc.get('source_run_id')}",
            f"Branch: {doc.get('branch')}",
            f"Paths: {', '.join(doc.get('patch_paths') or [])}",
        ]
    )


def _append_report(path: Path, section: str) -> None:
    existing = path.read_text(encoding="utf-8") if path.is_file() else ""
    marker = "\n## Verification\n"
    if marker in f"\n{existing}":
        existing = existing.split("\n## Verification", 1)[0].rstrip() + "\n"
    path.write_text(existing.rstrip() + "\n" + section, encoding="utf-8")


def _write_doc(run_dir: Path, doc: dict[str, Any]) -> None:
    (run_dir / "verification.json").write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    _append_report(run_dir / "report.md", render_comparison(doc))
    print(render_comparison(doc))


def _repo_from_run(run_dir: Path) -> Path | None:
    profile = run_dir / "profile.json"
    if not profile.is_file():
        return None
    data = json.loads(profile.read_text(encoding="utf-8"))
    root = data.get("root") if isinstance(data, dict) else None
    if not isinstance(root, str) or not root:
        return None
    path = Path(root)
    return path if path.is_dir() else None


def _snippet_lines(snippet: str) -> list[tuple[int, str]]:
    rows: list[tuple[int, str]] = []
    for line in (snippet or "").splitlines():
        if ":" not in line:
            continue
        number, text = line.split(":", 1)
        try:
            rows.append((int(number), text))
        except ValueError:
            continue
    return rows


def _strip_replacement(text: str) -> str:
    raw = (text or "").strip()
    fenced = re.search(r"```(?:python|py)?\s*\n(.*?)```", raw, re.S)
    if fenced:
        raw = fenced.group(1).strip()
    return raw.replace("\r\n", "\n")


def build_range_diff(path: str, snippet: str, start: int, end: int, replacement: str) -> str:
    """Turn a cited-range replacement into a unified diff. Models do not have to emit diff syntax."""
    rows = _snippet_lines(snippet)
    if not rows:
        return ""
    new_body = _strip_replacement(replacement)
    if not new_body:
        return ""
    new_lines = new_body.splitlines()
    old_window = [text for _n, text in rows]
    window_start = rows[0][0]
    prefix = [text for n, text in rows if n < start]
    suffix = [text for n, text in rows if n > end]
    new_window = prefix + new_lines + suffix
    if new_window == old_window:
        return ""
    diff = "".join(
        difflib.unified_diff(
            [f"{line}\n" for line in old_window],
            [f"{line}\n" for line in new_window],
            fromfile=f"a/{path}",
            tofile=f"b/{path}",
            n=3,
        )
    )
    if not diff:
        return ""
    offset = window_start - 1

    def _shift(match: re.Match[str]) -> str:
        old_start = int(match.group(1)) + offset
        old_count = match.group(2) or "1"
        new_start = int(match.group(3)) + offset
        new_count = match.group(4) or "1"
        return f"@@ -{old_start},{old_count} +{new_start},{new_count} @@"

    diff = re.sub(r"@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@", _shift, diff)
    if not diff.startswith("diff --git "):
        diff = f"diff --git a/{path} b/{path}\n{diff}"
    return diff if diff.endswith("\n") else diff + "\n"


def default_patch_diff(contract: dict[str, Any], snippet: str, before: dict[str, Any]) -> str:
    from pydantic import BaseModel, Field
    from pydantic_ai import Agent
    from pydantic_ai.usage import UsageLimits

    from loadline.investigator.run import _default_investigator_model

    class CitedReplacement(BaseModel):
        replacement: str = Field(
            description="New source for contract start_line through end_line only. No line numbers, no diff."
        )

    path = str(contract.get("path") or "file")
    try:
        start = int(contract["start_line"])
        end = int(contract["end_line"])
    except (KeyError, TypeError, ValueError):
        return ""
    prompt = (
        "Return replacement source for the cited line range only. "
        "Change the smallest region that explains the cited metric at the process's current configuration. "
        "If the snippet holds a scarce resource (connection, lock, session) across an await, close that scope before the await. "
        "Do not rely on flipping an environment flag that a runtime file already sets. "
        "Do not edit Compose, Dockerfiles, environment files, or hint files.\n\n"
        f"Contract:\n{json.dumps(contract, indent=2)}\n\n"
        f"Before numbers from the experiment file:\n{json.dumps(before, indent=2)}\n\n"
        f"Snippet with line numbers:\n{snippet}\n"
    )
    agent = Agent(
        _default_investigator_model(),
        system_prompt=prompt,
        output_type=CitedReplacement,
    )
    result = agent.run_sync(
        "Return the replacement source for the cited range.",
        usage_limits=UsageLimits(request_limit=6, total_tokens_limit=None),
    )
    replacement = getattr(result.output, "replacement", None)
    if not isinstance(replacement, str) or not replacement.strip():
        return ""
    return build_range_diff(path, snippet, start, end, replacement)


def _default_replay(repo: Path, tool_input: dict[str, Any]) -> dict[str, Any]:
    from loadline.adapters.runtime.boot_teardown import teardown_boot_outcome
    from loadline.adapters.runtime.compose_boot import boot_repository
    from loadline.core.ledger import Ledger
    from loadline.investigator.deps import InvestigationDeps
    from loadline.investigator.k6_tool import run_k6

    outcome = boot_repository(repo, teardown=False, require_auth=False)
    if outcome.status != "booted" or not outcome.boot or not outcome.run_id:
        return {
            "status": "remeasure_blocked",
            "summary": (outcome.blocker or {}).get("summary") or outcome.status,
        }
    try:
        run_dir = Path(outcome.boot["run_dir"])
        deps = InvestigationDeps(
            repo_root=repo,
            run_dir=run_dir,
            run_id=outcome.run_id,
            ledger=Ledger.open(run_dir, outcome.run_id),
            graph=None,
            boot=outcome.boot,
            allowed_hosts=frozenset(s["name"] for s in outcome.boot["services"] if s.get("name")),
            network=str(outcome.boot.get("network") or ""),
        )
        result = run_k6(
            deps,
            list(tool_input.get("endpoints") or []),
            float(tool_input["rate"]),
            int(tool_input["duration_s"]),
            auth=tool_input.get("auth") if isinstance(tool_input.get("auth"), dict) else None,
        )
        if result.get("error"):
            return {"status": "remeasure_blocked", "summary": str(result["error"])}
        exp_id = str(result.get("experiment_id") or "")
        exp_path = run_dir / "experiments" / f"{exp_id}.json"
        experiment = json.loads(exp_path.read_text(encoding="utf-8"))
        return {
            "status": "ok",
            "experiment": experiment,
            "run_id": outcome.run_id,
            "run_dir": str(run_dir),
        }
    finally:
        teardown_boot_outcome(outcome, repo)


def _gh_argv() -> list[str] | None:
    for candidate in (
        "gh",
        "gh.exe",
        "/mnt/c/Program Files/GitHub CLI/gh.exe",
        str(Path.home() / ".local/bin/gh"),
    ):
        path = Path(candidate)
        if candidate in {"gh", "gh.exe"}:
            found = shutil.which(candidate)
            if found:
                return [found]
            continue
        if path.is_file():
            return [str(path)]
    return None


def _default_push(repo: Path, doc: dict[str, Any]) -> tuple[bool, str | None]:
    branch = _git(repo, "rev-parse", "--abbrev-ref", "HEAD", check=False).stdout.strip()
    if branch in {"main", "master"} or not branch.startswith("loadline/verify-"):
        return False, None
    remote = _git(repo, "remote", "get-url", "origin", check=False)
    if remote.returncode != 0:
        return False, None
    pushed = _git(repo, "push", "-u", "origin", "HEAD", check=False)
    if pushed.returncode != 0:
        detail = (pushed.stderr or pushed.stdout or "git push failed").strip()
        print(f"error: git push failed ({detail.splitlines()[-1] if detail else 'unknown'})", flush=True)
        return False, None
    gh = _gh_argv()
    if not gh:
        print("error: gh is not installed; wrote pr-body.md", flush=True)
        return False, None
    body = render_pr_body(doc) or ""
    created = subprocess.run(
        [*gh, "pr", "create", "--title", "Loadline: cited metric moved", "--body", body],
        cwd=str(repo),
        capture_output=True,
        text=True,
        check=False,
    )
    if created.returncode != 0:
        detail = (created.stderr or created.stdout or "gh pr create failed").strip()
        print(f"error: gh pr create failed ({detail.splitlines()[-1] if detail else 'unknown'})", flush=True)
        return False, None
    url = (created.stdout or "").strip().splitlines()
    return True, url[-1] if url else None


def _apply_patch(repo: Path, diff_text: str, branch: str) -> tuple[str | None, str]:
    original = _git(repo, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
    if _git(repo, "rev-parse", "--verify", branch, check=False).returncode == 0:
        if original == branch:
            main = _git(repo, "symbolic-ref", "refs/remotes/origin/HEAD", check=False).stdout.strip()
            fallback = main.rsplit("/", 1)[-1] if main else "main"
            _git(repo, "checkout", fallback, check=False)
            original = _git(repo, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
        _git(repo, "branch", "-D", branch, check=False)
    _git(repo, "checkout", "-b", branch)
    proc = subprocess.run(
        ["git", "-C", str(repo), "apply", "--check", "-"],
        input=diff_text,
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        _git(repo, "checkout", original, check=False)
        _git(repo, "branch", "-D", branch, check=False)
        return original, (proc.stderr or proc.stdout or "git apply --check failed").strip()
    applied = subprocess.run(
        ["git", "-C", str(repo), "apply", "-"],
        input=diff_text,
        capture_output=True,
        text=True,
        check=False,
    )
    if applied.returncode != 0:
        _git(repo, "checkout", "--", ".", check=False)
        _git(repo, "checkout", original, check=False)
        _git(repo, "branch", "-D", branch, check=False)
        return original, (applied.stderr or "git apply failed").strip()
    return original, ""


def _commit_patch(repo: Path, path: str) -> None:
    _git(repo, "add", "--", path)
    env = os.environ.copy()
    env["GIT_AUTHOR_NAME"] = "loadline"
    env["GIT_AUTHOR_EMAIL"] = "loadline-verify@example.com"
    env["GIT_COMMITTER_NAME"] = "loadline"
    env["GIT_COMMITTER_EMAIL"] = "loadline-verify@example.com"
    subprocess.run(
        ["git", "-C", str(repo), "commit", "-m", "Apply the cited source change."],
        check=True,
        capture_output=True,
        text=True,
        env=env,
    )


def _abort_branch(repo: Path, original: str, branch: str) -> None:
    _git(repo, "reset", "--hard", "HEAD", check=False)
    _git(repo, "checkout", original, check=False)
    _git(repo, "branch", "-D", branch, check=False)


def verify_run(
    run_dir: Path,
    *,
    open_pr: bool = True,
    allow_loadline_repo: bool = False,
    patch_runner: PatchRunner | None = None,
    replay_runner: ReplayRunner | None = None,
    push_runner: PushRunner | None = None,
) -> int:
    run_dir = run_dir.resolve()
    home = loadline_home().resolve()
    if not str(run_dir).startswith(str(home)):
        print(f"error: run_dir is outside {home}", flush=True)
        return 2
    if not (run_dir / "experiments").is_dir():
        print("error: experiments directory is missing", flush=True)
        return 2

    run_id = run_dir.name
    report_path = run_dir / "report.md"
    report_text = report_path.read_text(encoding="utf-8") if report_path.is_file() else ""
    fix = parse_fix_fence(report_text)
    problem = _contract_error(run_dir, fix)
    if problem or fix is None:
        doc = _blank_doc(run_id, fix, None)
        doc["reason"] = problem or "report has no loadline_fix fence"
        _write_doc(run_dir, doc)
        return 0

    exp_path = run_dir / "experiments" / f"{fix['experiment_id']}.json"
    experiment = json.loads(exp_path.read_text(encoding="utf-8"))
    doc = _blank_doc(run_id, fix, experiment)
    repo = _repo_from_run(run_dir)
    if repo is None:
        doc["reason"] = "profile.json has no repository root"
        _write_doc(run_dir, doc)
        return 0
    if _is_loadline_repo(repo) and not allow_loadline_repo:
        print("error: refusing to patch the Loadline repository", flush=True)
        return 2
    if _git(repo, "rev-parse", "--is-inside-work-tree", check=False).returncode != 0:
        print("error: target is not a git repository", flush=True)
        return 2
    if _worktree_blocks_patch(repo):
        print("error: target worktree is dirty", flush=True)
        return 2

    if _cited_was_healthy(experiment, str(fix["operation_id"]), str(fix["metric"])):
        doc["verdict"] = "hypothesis_failed"
        doc["reason"] = "stored experiment did not show a failure; the replay rate was not raised"
        _write_doc(run_dir, doc)
        return 0

    runner = patch_runner if patch_runner is not None else default_patch_diff
    snippet = _snippet(repo, str(fix["path"]), int(fix["start_line"]), int(fix["end_line"]))
    diff_text = runner(fix, snippet, metrics_from_experiment(experiment, str(fix["operation_id"])))
    (run_dir / "patch.diff").write_text(diff_text or "", encoding="utf-8")
    rejected = patch_rejection(diff_text or "", str(fix["path"]))
    if rejected:
        doc["reason"] = rejected
        _write_doc(run_dir, doc)
        return 0

    branch = f"loadline/verify-{run_id}"
    doc["branch"] = branch
    doc["patch_paths"] = [str(fix["path"])]
    original, apply_err = _apply_patch(repo, diff_text, branch)
    if apply_err:
        doc["verdict"] = "remeasure_blocked"
        doc["reason"] = apply_err
        doc["branch"] = ""
        doc["patch_paths"] = []
        _write_doc(run_dir, doc)
        return 0

    tool_input = dict(experiment.get("input") or {})
    replay = replay_runner if replay_runner is not None else _default_replay
    replayed = replay(repo, tool_input)
    if replayed.get("status") != "ok":
        _abort_branch(repo, original, branch)
        doc["verdict"] = "remeasure_blocked"
        doc["reason"] = str(replayed.get("summary") or "boot failed")
        doc["branch"] = ""
        doc["patch_paths"] = []
        _write_doc(run_dir, doc)
        return 0

    after = replayed["experiment"]
    verify_id = f"exp-k6-verify-{str(fix['experiment_id']).removeprefix('exp-k6-')}"
    after = dict(after)
    after["experiment_id"] = verify_id
    replay_run_dir = Path(str(replayed.get("run_dir") or run_dir))
    exp_dir = replay_run_dir / "experiments"
    exp_dir.mkdir(parents=True, exist_ok=True)
    (exp_dir / f"{verify_id}.json").write_text(json.dumps(after, indent=2) + "\n", encoding="utf-8")

    cited_after = metrics_from_experiment(after, str(fix["operation_id"]))
    control_id = str(fix["control_operation_id"])
    control_after = metrics_from_experiment(after, control_id)
    if control_after.get("p95_ms") is None and control_after.get("error_rate") is None:
        control_after_arg = None
        control_before_arg = None
    else:
        control_after_arg = control_after
        control_before_arg = doc["control_before"] or None
    verdict = judge_replay(
        metric=str(fix["metric"]),
        cited_before=doc["before"],
        cited_after=cited_after,
        control_before=control_before_arg,
        control_after=control_after_arg,
    )
    doc["verdict"] = verdict
    doc["after"] = {"experiment_id": verify_id, **cited_after}
    doc["control_after"] = control_after if control_after_arg else {}
    doc["replay_run_id"] = str(replayed.get("run_id") or "")
    _commit_patch(repo, str(fix["path"]))

    if open_pr and verdict == "improved":
        push = push_runner if push_runner is not None else _default_push
        opened, url = push(repo, doc)
        doc["pr_opened"] = opened
        doc["pr_url"] = url
        if not opened:
            body = render_pr_body(doc)
            if body:
                (run_dir / "pr-body.md").write_text(body, encoding="utf-8")
    if replay_run_dir.resolve() != run_dir.resolve():
        _append_report(replay_run_dir / "report.md", render_comparison(doc))
    _write_doc(run_dir, doc)
    return 0
