import copy

from loadline.core.sandbox_policy import apply_sandbox_policy, closure_started_set


def test_started_none_matches_golden():
    compose = {
        "services": {
            "web": {"image": "x", "ports": ["8000:8000"]},
            "db": {"image": "postgres:16"},
        }
    }
    before = copy.deepcopy(compose)
    a = apply_sandbox_policy(copy.deepcopy(before), run_network="loadline_run")
    b = apply_sandbox_policy(copy.deepcopy(before), run_network="loadline_run", started_services=None)
    assert a.action == b.action == "rewrite"
    assert a.plan == b.plan
    assert [ (d.rule, d.summary) for d in a.diffs ] == [ (d.rule, d.summary) for d in b.diffs ]


def test_closure_starts_target_deps_and_hostname_token():
    compose = {
        "services": {
            "app": {
                "build": ".",
                "depends_on": ["db"],
                "environment": {"DOWNSTREAM_URL": "http://downstream:9000/api"},
            },
            "db": {"image": "postgres:16"},
            "downstream": {"build": "./downstream"},
            "proxy": {"image": "nginx"},
        }
    }
    started = closure_started_set(compose, "app")
    assert "app" in started
    assert "db" in started
    assert "downstream" in started
    assert "proxy" not in started


def test_closure_no_substring_match():
    compose = {
        "services": {
            "app": {"build": ".", "environment": {"URL": "http://myapp:8000/x"}},
            "myapp": {"image": "x"},
        }
    }
    started = closure_started_set(compose, "app")
    # "app" must not match inside "myapp" token; myapp only starts if whole token equals.
    # Here env contains myapp as whole token, so myapp SHOULD start (whole token).
    assert "myapp" in started
    # Negative: env with application should not start app via substring.
    compose2 = {
        "services": {
            "worker": {"build": ".", "environment": {"URL": "http://application:8000/x"}},
            "app": {"image": "x"},
        }
    }
    started2 = closure_started_set(compose2, "worker")
    assert "app" not in started2


def test_closure_outside_violation_becomes_note():
    compose = {
        "services": {
            "web": {"build": "."},
            "evil": {"image": "x", "privileged": True},
        }
    }
    res = apply_sandbox_policy(
        compose, run_network="loadline_run", started_services={"web"}
    )
    assert res.action == "rewrite"
    assert "evil" in res.not_started
    assert any("evil" in n for n in res.notes) or any("evil" in d.summary for d in res.diffs)
    assert "web" in (res.plan.get("services") or {})


def test_closure_inside_violation_still_refuses():
    compose = {
        "services": {
            "web": {"build": ".", "privileged": True},
            "db": {"image": "postgres:16"},
        }
    }
    res = apply_sandbox_policy(
        compose, run_network="loadline_run", started_services={"web", "db"}
    )
    assert res.action == "refuse"


def test_closure_does_not_scan_command():
    compose = {
        "services": {
            "web": {"build": ".", "command": "curl http://proxy:8000/x", "environment": {}},
            "proxy": {"image": "nginx"},
        }
    }
    started = closure_started_set(compose, "web")
    # Command mentions proxy but env does not → proxy not started.
    assert "proxy" not in started


def test_fastapi_closure_starts_backend_db_only():
    compose = {
        "services": {
            "backend": {"build": ".", "depends_on": ["db"]},
            "db": {"image": "postgres:16"},
            "proxy": {"image": "nginx"},
        }
    }
    started = closure_started_set(compose, "backend")
    assert started == {"backend", "db"}
