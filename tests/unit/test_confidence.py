from itertools import product

from loadline.core.confidence import confidence


def test_confidence_matrix_64():
    expected = {}
    for s, m, x, k, r, v in product([False, True], repeat=6):
        expected[(s, m, x, k, r, v)] = confidence(s, m, x, k, r, v)
    # spot checks from contract
    assert confidence(True, False, False, False, True, False) == 0.40
    assert confidence(True, True, True, True, True, False) == 0.85
    assert confidence(True, True, True, True, False, False) == 0.65
    assert confidence(False, True, True, True, True, False) == 0.0
    assert len(expected) == 64
