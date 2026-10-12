from pathlib import Path

from loadline.core.hints import load_hints


def test_fixture_still_loads():
    hints, err = load_hints(Path("tests/fixtures/fx-docker-http/.loadline.yaml"))
    assert err is None
    assert hints is not None
    assert hints.container_port == 8080
    assert hints.health_path == "/health"


def test_unknown_key_still_errors(tmp_path: Path):
    p = tmp_path / ".loadline.yaml"
    p.write_text('schema_version: "1"\nbogus_key: 1\n')
    hints, err = load_hints(p)
    assert hints is None
    assert err is not None
    assert "unknown keys" in err


def test_old_keys_yield_same_fields(tmp_path: Path):
    p = tmp_path / ".loadline.yaml"
    p.write_text(
        'schema_version: "1"\napp_service: web\ncontainer_port: 8000\nhealth_path: /health\n'
    )
    hints, err = load_hints(p)
    assert err is None
    assert hints is not None
    assert hints.app_service == "web"
    assert hints.container_port == 8000
    assert hints.health_path == "/health"


def test_start_set_omitted_means_all(tmp_path: Path):
    p = tmp_path / ".loadline.yaml"
    p.write_text('schema_version: "1"\n')
    hints, err = load_hints(p)
    assert err is None
    assert hints is not None
    assert hints.compose.start_set == "all"


def test_prepare_omitted_means_empty(tmp_path: Path):
    p = tmp_path / ".loadline.yaml"
    p.write_text('schema_version: "1"\n')
    hints, err = load_hints(p)
    assert err is None
    assert hints is not None
    assert hints.prepare == []
