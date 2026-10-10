from pathlib import Path

from loadline.core.ledger import Ledger
from loadline.core.predictions import PredictionSpec, score_prediction_ledger
from loadline.core.prediction_evaluator import score_prediction


def test_unknown_readout_rejected_in_ledger(tmp_path: Path):
    ledger = Ledger.open(tmp_path, "run1")
    ev = score_prediction_ledger(
        ledger,
        PredictionSpec(
            prediction_id="p1",
            readout="unknown_metric",
            comparator="unchanged",
            baseline=1.0,
            observed=1.0,
            unit="ms",
            samples=200,
            valid_verdict=True,
        ),
    )
    assert ev["kind"] == "prediction_rejected"


def test_changes_by_inconclusive_wiring():
    assert score_prediction("changes_by", 100, 105, "ms", samples=200, valid_verdict=True) == "inconclusive"


def test_unchanged_confirmed_wiring():
    assert score_prediction("unchanged", 100, 105, "ms", samples=200, valid_verdict=True) == "confirmed"


def test_scored_prediction_writes_ledger(tmp_path: Path):
    ledger = Ledger.open(tmp_path, "run1")
    ev = score_prediction_ledger(
        ledger,
        PredictionSpec(
            prediction_id="p2",
            readout="p95_ms",
            comparator="unchanged",
            baseline=100.0,
            observed=105.0,
            unit="ms",
            samples=200,
            valid_verdict=True,
        ),
    )
    assert ev["kind"] == "prediction_scored"
    assert ev["outcome"] == "confirmed"
