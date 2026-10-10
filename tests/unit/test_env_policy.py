from loadline.core.env_policy import apply_env_policy, load_repo_dotenv, parse_dotenv_text
from loadline.core.sandbox_policy import apply_sandbox_policy


def test_optional_sentry_dsn_placeholder_passes():
    outcome = apply_env_policy({"SENTRY_DSN": "${SENTRY_DSN:-}"})
    assert not outcome.needs_input
    assert outcome.env["SENTRY_DSN"] == ""
    assert not outcome.generated_secrets


def test_required_compose_reference_generates_local_secret_when_missing():
    outcome = apply_env_policy({"POSTGRES_PASSWORD": "${POSTGRES_PASSWORD:?Variable not set}"})
    assert not outcome.needs_input
    assert outcome.env["POSTGRES_PASSWORD"]
    assert outcome.env["POSTGRES_PASSWORD"] != "changethis"
    assert "POSTGRES_PASSWORD" in outcome.generated_secrets


def test_literal_stripe_key_cleared_not_needs_input():
    outcome = apply_env_policy({"STRIPE_SECRET_KEY": "sk_live_abcdefghijklmnop"})
    assert not outcome.needs_input
    assert outcome.env["STRIPE_SECRET_KEY"] == ""
    assert outcome.replacements
    assert not outcome.generated_secrets


def test_prod_url_rewritten():
    outcome = apply_env_policy({"API_URL": "https://service.prod.amazonaws.com/v1"})
    assert not outcome.needs_input
    assert "sandbox.invalid" in outcome.env["API_URL"]
    assert outcome.replacements


def test_short_local_config_unchanged():
    outcome = apply_env_policy({"POSTGRES_DB": "app"})
    assert outcome.env["POSTGRES_DB"] == "app"
    assert not outcome.replacements


def test_stripe_literal_cleared_in_sandbox_policy():
    compose = {
        "services": {
            "web": {
                "image": "x",
                "environment": {"STRIPE_SECRET_KEY": "sk_live_abcdefghijklmnop"},
            }
        }
    }
    result = apply_sandbox_policy(compose, run_network="loadline_run")
    assert result.action == "rewrite"
    assert result.plan["services"]["web"]["environment"]["STRIPE_SECRET_KEY"] == ""


def test_placeholder_secrets_shared_across_services_and_embedded_urls():
    dotenv = parse_dotenv_text(
        "SECRET_KEY=changethis\nPOSTGRES_PASSWORD=changethis\nPROJECT_NAME=Demo\n"
    )
    generated: dict[str, str] = {}
    compose = {
        "services": {
            "db": {
                "image": "postgres:18",
                "environment": {"POSTGRES_PASSWORD": "${POSTGRES_PASSWORD:?set}"},
            },
            "api": {
                "image": "api",
                "environment": {
                    "SECRET_KEY": "${SECRET_KEY:?set}",
                    "PROJECT_NAME": "${PROJECT_NAME:?set}",
                    "DATABASE_URL": "postgresql://postgres:${POSTGRES_PASSWORD:?set}@db:5432/app",
                },
            },
        }
    }
    result = apply_sandbox_policy(compose, run_network="loadline_run", repo_dotenv=dotenv)
    assert result.action == "rewrite"
    db_pw = result.plan["services"]["db"]["environment"]["POSTGRES_PASSWORD"]
    api_secret = result.plan["services"]["api"]["environment"]["SECRET_KEY"]
    db_url = result.plan["services"]["api"]["environment"]["DATABASE_URL"]
    assert db_pw and db_pw != "changethis"
    assert api_secret != db_pw
    assert api_secret != "changethis"
    assert db_pw in db_url
    assert result.plan["services"]["api"]["environment"]["PROJECT_NAME"] == "Demo"


def test_openai_required_without_value_needs_input():
    outcome = apply_env_policy({"OPENAI_API_KEY": "${OPENAI_API_KEY:?required}"})
    assert outcome.needs_input
    assert "OPENAI_API_KEY" in (outcome.needs_input_summary or "")


def test_resolved_literals_not_compose_refs():
    dotenv = parse_dotenv_text("SECRET_KEY=changethis\n")
    outcome = apply_env_policy(
        {"SECRET_KEY": "${SECRET_KEY:?Variable not set}"},
        repo_dotenv=dotenv,
    )
    assert "${" not in outcome.env["SECRET_KEY"]
    assert outcome.env["SECRET_KEY"] != "changethis"


def test_load_repo_dotenv_reads_target_file(tmp_path):
    (tmp_path / ".env").write_text("SECRET_KEY=changethis\nFOO=bar\n")
    assert load_repo_dotenv(tmp_path)["FOO"] == "bar"
