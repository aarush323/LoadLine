from loadline.core.experiment_policy import ExperimentContext, admit


def test_refine_admitted_without_prior_request():
    ctx = ExperimentContext(refine_requested=False, refinements_done=99)
    result = admit("refine", ctx)
    assert result.admitted


def test_refine_admitted_after_many_refinements():
    ctx = ExperimentContext(refine_requested=True, refinements_done=100)
    result = admit("refine", ctx)
    assert result.admitted


def test_isolate_admitted_with_one_operation():
    ctx = ExperimentContext(operations_count=1, rate_rps=10_000, rate_cap=1)
    result = admit("isolate", ctx)
    assert result.admitted


def test_rate_above_stored_cap_still_admitted():
    ctx = ExperimentContext(rate_rps=500, rate_cap=2)
    result = admit("rate_step", ctx)
    assert result.admitted
