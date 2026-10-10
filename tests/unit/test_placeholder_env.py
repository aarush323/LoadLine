from loadline.core.env_policy import apply_env_policy


def test_placeholder_true_gives_nonempty_and_limitation_no_stub():
    outcome = apply_env_policy({"STRIPE_SECRET_KEY": {"placeholder": True}})
    assert outcome.env["STRIPE_SECRET_KEY"] != ""
    assert any("dependency not replaced" in line for line in outcome.limitations)
    assert not any("stub" in line.lower() for line in outcome.limitations)


def test_literal_stripe_still_cleared():
    outcome = apply_env_policy({"STRIPE_SECRET_KEY": "sk_live_abcdefghijklmnop"})
    assert outcome.env["STRIPE_SECRET_KEY"] == ""
    assert not outcome.needs_input
