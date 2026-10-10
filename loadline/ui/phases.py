"""Run phase identifiers for terminal progress."""

from __future__ import annotations

from enum import Enum


class Phase(str, Enum):
    PREFLIGHT = "preflight"
    BOOT = "boot"
    WORKLOAD = "workload"
    CALIBRATE = "calibrate"
    BASELINE = "baseline"
    LADDER = "ladder"
    INVESTIGATE = "investigate"
    REPORT = "report"
    TEARDOWN = "teardown"


PHASE_LABELS: dict[Phase, str] = {
    Phase.PREFLIGHT: "Preflight",
    Phase.BOOT: "Boot",
    Phase.WORKLOAD: "Discover workload",
    Phase.CALIBRATE: "Calibrate",
    Phase.BASELINE: "Baseline k6",
    Phase.LADDER: "Ladder",
    Phase.INVESTIGATE: "Investigate",
    Phase.REPORT: "Report",
    Phase.TEARDOWN: "Teardown",
}
