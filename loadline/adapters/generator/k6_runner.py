"""Run pinned k6 in Docker on the sandbox network (tech_doc.md §7.3, §9)."""

from __future__ import annotations

import subprocess
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from loadline.adapters.generator.k6_compiler import CompileError, compile_plan
from loadline.adapters.generator.k6_summary import K6Summary, parse_handle_summary, successful_request_count
from loadline.adapters.observability.docker_stats import StatsCollector
from loadline.constants import GEN_CPUS, GEN_MEM, K6_IMAGE_DIGEST
from loadline.core.hints import DEFAULT_SLO_ERR_RATE, DEFAULT_SLO_P95_MS
from loadline.core.verdict import StepMetrics, compute_verdict

_generator_lock = threading.Lock()


@dataclass
class K6RunResult:
    summary: K6Summary
    exit_code: int
    stdout_path: Path
    stderr: str
    verdict: str
    successful_samples: int
    calibration: dict[str, Any] | None = None


def _k6_image() -> str:
    if not K6_IMAGE_DIGEST or "@" not in K6_IMAGE_DIGEST:
        raise RuntimeError("K6_IMAGE_DIGEST must be a pinned digest")
    return K6_IMAGE_DIGEST


def run_k6_plan(
    *,
    plan: dict[str, Any],
    allowed_hosts: frozenset[str],
    network: str,
    run_id: str,
    run_dir: Path,
    wave_name: str = "step",
    timeout_s: int = 600,
    stats_collector: StatsCollector | None = None,
    auth_secrets: dict[str, str] | None = None,
    slo_p95_ms: float | None = None,
    slo_err_rate: float | None = None,
) -> K6RunResult:
    compiled = compile_plan(plan, allowed_hosts, auth_secrets=auth_secrets)
    if isinstance(compiled, CompileError):
        summary = K6Summary(parse_ok=False, error=compiled.message)
        out = _write_outputs(run_dir, wave_name, "", "", summary)
        return K6RunResult(
            summary=summary,
            exit_code=1,
            stdout_path=out,
            stderr=compiled.message,
            verdict="generator_failed",
            successful_samples=0,
        )

    script, _plan_hash = compiled
    waves = run_dir / "waves" / wave_name
    waves.mkdir(parents=True, exist_ok=True)
    (waves / "plan.json").write_text(__import__("json").dumps(plan, indent=2))

    with _generator_lock:
        if stats_collector:
            stats_collector.start()
        try:
            proc = subprocess.run(
                [
                    "docker",
                    "run",
                    "--rm",
                    "-i",
                    "--network",
                    network,
                    "--label",
                    f"loadline.run={run_id}",
                    "--cpus",
                    str(GEN_CPUS),
                    "--memory",
                    GEN_MEM,
                    "-e",
                    "HTTP_PROXY=",
                    "-e",
                    "HTTPS_PROXY=",
                    "-e",
                    "http_proxy=",
                    "-e",
                    "https_proxy=",
                    _k6_image(),
                    "run",
                    "-",
                ],
                input=script,
                capture_output=True,
                text=True,
                timeout=timeout_s,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            stderr = (exc.stderr or "") if isinstance(exc.stderr, str) else ""
            if not stderr and exc.stdout and isinstance(exc.stdout, str):
                stderr = exc.stdout[:2000]
            summary = K6Summary(parse_ok=False, error=f"k6 docker timed out after {timeout_s}s")
            stdout_path = _write_outputs(run_dir, wave_name, "", stderr, summary)
            return K6RunResult(
                summary=summary,
                exit_code=124,
                stdout_path=stdout_path,
                stderr=stderr or summary.error or "",
                verdict="generator_failed",
                successful_samples=0,
            )
        finally:
            if stats_collector:
                stats_collector.stop()

    stdout = proc.stdout or ""
    stderr = proc.stderr or ""
    summary = parse_handle_summary(stdout)
    stdout_path = _write_outputs(run_dir, wave_name, stdout, stderr, summary)
    samples = successful_request_count(summary) if summary.parse_ok else 0
    shape = plan.get("shape") or {}
    target_rate = float(shape.get("rate") or 1)
    achieved = summary.throughput_rps or 0.0
    metrics = StepMetrics(
        telemetry_coverage=0.95,
        host_cpu=0.0,
        host_memory_pressure=False,
        host_port_or_fd_exhaustion=False,
        dropped_iteration_ratio=(summary.dropped_iterations / max(1, samples + summary.dropped_iterations)),
        vu_cap_hit=False,
        generator_cpu_ratio=0.0,
        target_healthy=True,
        generator_ok=proc.returncode == 0,
        parse_ok=summary.parse_ok,
        achieved_rate_ratio=achieved / target_rate if target_rate else 0.0,
        has_drop_signal=summary.dropped_iterations > 0,
        p95_ms=summary.p95_ms,
        p99_ms=summary.p99_ms if samples >= 1000 else None,
        err_rate=summary.err_rate or 0.0,
        slo_p95_ms=float(slo_p95_ms) if slo_p95_ms is not None else DEFAULT_SLO_P95_MS,
        slo_err_rate=float(slo_err_rate) if slo_err_rate is not None else DEFAULT_SLO_ERR_RATE,
        successful_samples=samples,
        probe_p95_ms=None,
        probe_baseline_p95_ms=None,
    )
    verdict = compute_verdict(metrics)
    if verdict not in ("pass", "fail"):
        verdict = f"invalid({verdict})"
    return K6RunResult(
        summary=summary,
        exit_code=proc.returncode,
        stdout_path=stdout_path,
        stderr=stderr,
        verdict=verdict,
        successful_samples=samples,
    )


def _write_outputs(run_dir: Path, wave_name: str, stdout: str, stderr: str, summary: K6Summary) -> Path:
    waves = run_dir / "waves" / wave_name
    waves.mkdir(parents=True, exist_ok=True)
    stdout_path = waves / "k6.stdout"
    stdout_path.write_text(stdout)
    (waves / "k6.stderr").write_text(stderr)
    if summary.raw_json:
        (waves / "k6.summary.json").write_text(__import__("json").dumps(summary.raw_json, indent=2))
    return stdout_path
