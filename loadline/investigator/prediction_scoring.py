"""Score structured predictions after measurements (tech_doc.md §11.4)."""

from __future__ import annotations

from typing import Any

from loadline.core.prediction_evaluator import Comparator
from loadline.core.predictions import KNOWN_READOUTS, PredictionSpec, score_prediction_ledger
from loadline.core.step_readouts import load_baseline_readouts
from loadline.investigator.deps import InvestigationDeps


def _baseline_for(pred: dict[str, Any], baseline: dict[str, dict[str, Any]], observed: dict[str, Any]) -> float | None:
    against = pred.get("against") or "baseline"
    if against == "baseline":
        row = baseline.get(pred["readout"])
        return float(row["value"]) if row and row.get("value") is not None else None
    row = observed.get(pred["readout"])
    return float(row["value"]) if row and row.get("value") is not None else None


def score_predictions_for_outcome(deps: InvestigationDeps, outcome: dict[str, Any]) -> list[dict[str, Any]]:
    observed = outcome.get("readouts") or {}
    if not observed:
        return []
    baseline = load_baseline_readouts(deps.run_dir)
    scored: list[dict[str, Any]] = []
    for hi, hyp in enumerate(deps.hypotheses):
        for pi, pred in enumerate(hyp.get("predictions") or []):
            key = f"h{hi}-p{pi}"
            if key in deps.scored_prediction_keys:
                continue
            readout = pred.get("readout")
            if readout not in KNOWN_READOUTS:
                ev = score_prediction_ledger(
                    deps.ledger,
                    PredictionSpec(
                        prediction_id=key,
                        readout=str(readout),
                        comparator="unchanged",
                        baseline=0.0,
                        observed=0.0,
                        unit="",
                        samples=0,
                        valid_verdict=False,
                    ),
                )
                scored.append({"prediction_id": key, "ledger": ev})
                deps.scored_prediction_keys.add(key)
                continue
            obs_row = observed.get(readout)
            if not obs_row:
                continue
            base_val = _baseline_for(pred, baseline, observed)
            if base_val is None:
                continue
            comparator = pred.get("comparator") or "unchanged"
            if comparator not in ("gt", "lt", "ge", "le", "within", "changes_by", "unchanged"):
                comparator = "unchanged"
            ev = score_prediction_ledger(
                deps.ledger,
                PredictionSpec(
                    prediction_id=key,
                    readout=readout,
                    comparator=comparator,  # type: ignore[arg-type]
                    baseline=base_val,
                    observed=float(obs_row["value"]),
                    unit=str(obs_row.get("unit") or ""),
                    samples=int(obs_row.get("samples") or 0),
                    valid_verdict=bool(obs_row.get("valid_verdict")),
                    magnitude=pred.get("magnitude"),
                ),
            )
            deps.scored_prediction_keys.add(key)
            scored.append({"prediction_id": key, "ledger": ev, "outcome": ev.get("outcome")})
    return scored
