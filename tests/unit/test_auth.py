from loadline.core.auth import require_model_auth
from loadline.settings import get_settings


def test_missing_model(monkeypatch):
    get_settings.cache_clear()
    monkeypatch.delenv("LOADLINE_MODEL", raising=False)
    err = require_model_auth()
    assert err and err.env_var == "LOADLINE_MODEL"


def test_openrouter_key(monkeypatch):
    monkeypatch.setenv("LOADLINE_MODEL", "openrouter:deepseek/deepseek-v4.1-flash")
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    err = require_model_auth()
    assert err and err.env_var == "OPENROUTER_API_KEY"
