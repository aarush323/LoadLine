from loadline.core.sandbox_policy import apply_sandbox_policy


def test_refuse_privileged():
    compose = {"services": {"web": {"image": "x", "privileged": True}}}
    result = apply_sandbox_policy(compose, run_network="loadline_run")
    assert result.action == "refuse"


def test_relative_init_sql_mount_does_not_drop_db():
    compose = {
        "x_loadline_app": "app",
        "services": {
            "db": {
                "image": "postgres:16-alpine",
                "volumes": ["./db/init.sql:/docker-entrypoint-initdb.d/init.sql:ro"],
            },
            "app": {"build": ".", "depends_on": {"db": {"condition": "service_healthy"}}},
        },
    }
    result = apply_sandbox_policy(compose, run_network="loadline_run")
    assert result.action == "rewrite"
    assert "db" in result.plan["services"]
    assert "app" in result.plan["services"]


def test_docker_sock_on_app_is_still_refused():
    compose = {
        "x_loadline_app": "app",
        "services": {"app": {"build": ".", "volumes": ["/var/run/docker.sock:/var/run/docker.sock"]}},
    }
    result = apply_sandbox_policy(compose, run_network="loadline_run")
    assert result.action == "refuse"
    assert result.blocker_code == "policy_refused"


def test_rewrite_ports_and_internal_network():
    compose = {"services": {"web": {"image": "x", "ports": ["8000:8000"]}}}
    result = apply_sandbox_policy(compose, run_network="loadline_run")
    assert result.action == "rewrite"
    assert result.plan["services"]["web"]["ports"] == []
    assert result.plan["networks"]["loadline_run"]["internal"] is True
