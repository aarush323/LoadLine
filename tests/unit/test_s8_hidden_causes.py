from loadline.core.report_model import primary_attribution_blocks_app_bottleneck
from tests.eval.acceptance import (
    competing_hypotheses_allow_findings,
    generator_bound_finding_allowed,
    misleading_comment_finding_allowed,
)
from tests.eval.oracle_io import load_sealed_oracle


def test_misleading_comment_cannot_become_finding_without_confirmed_prediction():
    oracle = load_sealed_oracle("hidden-misleading-comment.sealed.yaml")
    finding = {
        "mechanism": "N+1 query on every request per code comment",
        "symptom": "latency",
        "observed_facts": ["comment says obvious bottleneck"],
    }
    assert not misleading_comment_finding_allowed(
        finding, [], decoy_substrings=oracle["decoy_comment_substrings"]
    )
    events = [{"kind": "prediction_scored", "outcome": "confirmed", "prediction_id": "p1"}]
    assert misleading_comment_finding_allowed(
        finding, events, decoy_substrings=oracle["decoy_comment_substrings"]
    )


def test_generator_bound_attribution_blocks_application_bottleneck_finding():
    oracle = load_sealed_oracle("hidden-generator-bound.sealed.yaml")
    finding = {"mechanism": "The application bottleneck is synchronous IO in the handler."}
    assert primary_attribution_blocks_app_bottleneck(oracle["primary_attribution"], finding["mechanism"])
    assert not generator_bound_finding_allowed(oracle["primary_attribution"], finding)
    neutral = {"mechanism": "Generator saturation limited achieved rate; app CPU not established."}
    assert generator_bound_finding_allowed(oracle["primary_attribution"], neutral)


def test_competing_hypotheses_stay_hypotheses_until_prediction_confirmed():
    oracle = load_sealed_oracle("hidden-competing-hypotheses.sealed.yaml")
    findings = [{"mechanism": "cpu-bound handler loop"}]
    assert not competing_hypotheses_allow_findings(
        findings, [], competing_mechanisms=oracle["competing_mechanisms"]
    )
    ledger_events = [
        {"kind": "hypothesis", "mechanism_label": "cpu-bound", "status": "proposed"},
        {"kind": "hypothesis", "mechanism_label": "dependency-bound", "status": "proposed"},
    ]
    assert not competing_hypotheses_allow_findings(
        findings, ledger_events, competing_mechanisms=oracle["competing_mechanisms"]
    )
    ledger_events.append({"kind": "prediction_scored", "outcome": "confirmed", "prediction_id": "d1"})
    assert competing_hypotheses_allow_findings(
        findings, ledger_events, competing_mechanisms=oracle["competing_mechanisms"]
    )
