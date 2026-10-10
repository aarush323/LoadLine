from loadline.adapters.runtime.launch_plan import export_launch_plan, redact_compose_doc


def test_launch_plan_redacts_secrets():
    plan = {
        "x_loadline_app": "web",
        "services": {
            "web": {
                "image": "x",
                "environment": {"DATABASE_URL": "postgresql://app:secret@db:5432/app"},
            },
            "db": {
                "image": "postgres:16",
                "environment": {"POSTGRES_PASSWORD": "supersecret123456", "POSTGRES_USER": "app"},
            },
        },
    }
    exported = export_launch_plan(plan, run_network="net1", diffs=[])
    by_name = {s["name"]: s for s in exported["services"]}
    assert by_name["db"]["spec"]["environment"]["POSTGRES_PASSWORD"] == "[redacted]"
    assert by_name["web"]["spec"]["environment"]["DATABASE_URL"] == "[redacted]"
    assert by_name["db"]["spec"]["environment"]["POSTGRES_USER"] == "app"


def test_redact_compose_doc_for_disk_artifact():
    doc = {
        "services": {
            "web": {"environment": {"DATABASE_URL": "postgresql://app:secret@db:5432/app"}},
        }
    }
    redacted = redact_compose_doc(doc)
    assert redacted["services"]["web"]["environment"]["DATABASE_URL"] == "[redacted]"
