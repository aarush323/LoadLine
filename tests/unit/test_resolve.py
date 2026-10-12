from pathlib import Path

import yaml

from loadline.adapters.runtime.compose_boot import _health_url, _infer_app_service
from loadline.config.resolve import resolve


def _write_repo(tmp_path: Path, compose: dict, hints_text: str | None = None) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir(exist_ok=True)
    (repo / "compose.yaml").write_text(yaml.safe_dump(compose))
    if hints_text is not None:
        (repo / ".loadline.yaml").write_text(hints_text)
    return repo


def test_resolve_service_matches_infer(tmp_path: Path):
    compose = {
        "services": {
            "web": {"image": "nginx"},
            "backend": {
                "build": ".",
                "healthcheck": {"test": "curl -f http://localhost:8000/health/"},
            },
        }
    }
    repo = _write_repo(tmp_path, compose)
    cfg = resolve(repo)
    assert cfg.error is None
    assert cfg.blocker is None
    assert cfg.target is not None
    assert cfg.target.service == _infer_app_service(compose, cfg.hints)


def test_resolve_port_path_match_health_url(tmp_path: Path):
    compose = {
        "services": {
            "backend": {
                "build": ".",
                "healthcheck": {"test": ["CMD", "curl", "-f", "http://localhost:8000/api/v1/utils/health-check/"]},
            }
        }
    }
    repo = _write_repo(tmp_path, compose)
    cfg = resolve(repo)
    assert cfg.target is not None
    port, path = _health_url(cfg.target.service, cfg.hints, compose["services"][cfg.target.service])
    assert cfg.target.port == port
    assert cfg.target.health_path == path
    assert cfg.target.origin == f"http://{cfg.target.service}:{port}{path}"


def test_resolve_tie_or_zero_does_not_guess(tmp_path: Path):
    # Zero candidates: only db image, no build/ports.
    compose = {"services": {"db": {"image": "postgres:16"}}}
    repo = _write_repo(tmp_path, compose)
    cfg = resolve(repo)
    assert cfg.target is None
    assert cfg.blocker is not None
    assert "No application service found in compose." in cfg.blocker["summary"]


def test_resolve_hints_app_service_wins(tmp_path: Path):
    compose = {
        "services": {
            "web": {"image": "nginx"},
            "backend": {
                "build": ".",
                "healthcheck": {"test": "curl -f http://localhost:8000/health/"},
            },
        }
    }
    repo = _write_repo(tmp_path, compose, 'schema_version: "1"\napp_service: web\n')
    cfg = resolve(repo)
    assert cfg.target is not None
    assert cfg.target.service == "web"
    assert cfg.target.service == _infer_app_service(compose, cfg.hints)
