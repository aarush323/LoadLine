from loadline.core.prediction_evaluator import score_prediction, within_noise


def test_within_noise_relative():
    assert within_noise(100, 105, "ms")
    assert not within_noise(100, 120, "ms")


def test_changes_by_inconclusive_inside_noise():
    assert score_prediction("changes_by", 100, 102, "ms", samples=200, valid_verdict=True) == "inconclusive"


def test_unchanged_confirmed_inside_noise():
    assert score_prediction("unchanged", 100, 101, "ms", samples=200, valid_verdict=True) == "confirmed"


def test_low_samples_inconclusive():
    assert score_prediction("gt", 1, 2, "ms", samples=50, valid_verdict=True) == "inconclusive"
