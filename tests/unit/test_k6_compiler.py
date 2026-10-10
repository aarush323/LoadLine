from loadline.adapters.generator.k6_compiler import compile_plan


def test_compiler_rejects_external_url():
    plan = {
        "mix": [
            {
                "weight": 1,
                "op": {
                    "id": "x",
                    "service": "evil",
                    "port": 443,
                    "selector": {"method": "GET", "path": "/"},
                },
            }
        ],
        "shape": {"rate": 2, "warmup": 1, "duration": 2},
    }
    result = compile_plan(plan, frozenset({"web"}))
    assert hasattr(result, "message")


def test_compiler_accepts_sandbox_url():
    plan = {
        "mix": [
            {
                "weight": 1,
                "op": {
                    "id": "health",
                    "service": "web",
                    "port": 8000,
                    "selector": {"method": "GET", "path": "/health"},
                },
            }
        ],
        "shape": {"rate": 2, "warmup": 1, "duration": 2},
    }
    script, digest = compile_plan(plan, frozenset({"web"}))
    assert "http://web:8000/health" in script
    assert len(digest) == 64
    assert "http_req_duration{operation:health}" in script
    assert "preAllocatedVUs: 50" in script


def test_compiler_prealloc_scales_with_rate():
    plan = {
        "mix": [
            {
                "weight": 1,
                "op": {
                    "id": "h",
                    "service": "web",
                    "port": 8000,
                    "selector": {"method": "GET", "path": "/"},
                },
            }
        ],
        "shape": {"rate": 200, "duration": 10},
    }
    script, _ = compile_plan(plan, frozenset({"web"}))
    assert "preAllocatedVUs: 200" in script
    assert "maxVUs: 400" in script


def test_compiler_auth_setup_emits_setup_function():
    plan = {
        "mix": [
            {
                "weight": 1,
                "op": {
                    "id": "items",
                    "service": "web",
                    "port": 8000,
                    "selector": {"method": "GET", "path": "/items"},
                    "use_auth": True,
                },
            }
        ],
        "shape": {"rate": 2, "duration": 5},
        "auth": {
            "method": "POST",
            "path": "/login",
            "body_encoding": "form",
            "token_field": "access_token",
            "service": "web",
            "port": 8000,
        },
    }
    script, _ = compile_plan(
        plan,
        frozenset({"web"}),
        auth_secrets={"username": "admin@example.com", "password": "secret"},
    )
    assert "export function setup()" in script
    assert "admin@example.com" in script
    assert "useAuth" in script
    assert "Bearer" in script
