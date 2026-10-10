from loadline.core.sandbox_policy import apply_sandbox_policy


def test_refuse_privileged():
    compose = {"services": {"web": {"image": "x", "privileged": True}}}
    result = apply_sandbox_policy(compose, run_network="loadline_run")
    assert result.action == "refuse"


def test_rewrite_ports_and_internal_network():
    compose = {"services": {"web": {"image": "x", "ports": ["8000:8000"]}}}
    result = apply_sandbox_policy(compose, run_network="loadline_run")
    assert result.action == "rewrite"
    assert result.plan["services"]["web"]["ports"] == []
    assert result.plan["networks"]["loadline_run"]["internal"] is True
