from loadline.core.target_guard import assert_sandbox_target, classify_url


def test_external_refused():
    err = assert_sandbox_target("https://api.amazonaws.com/x", frozenset({"web"}))
    assert err is not None


def test_allowed_service():
    err = assert_sandbox_target("http://web:8000/health", frozenset({"web"}))
    assert err is None


def test_localhost_refused():
    assert classify_url("http://127.0.0.1:8000").kind == "local_dev"
