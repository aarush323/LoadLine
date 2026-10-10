from pathlib import Path
from unittest.mock import patch

import yaml


def test_no_import_in_run_or_boot():
    run_src = (Path("loadline/run_pipeline.py")).read_text()
    boot_src = (Path("loadline/boot.py")).read_text()
    cli_src = (Path("loadline/cli.py")).read_text()
    assert "loadline.load" not in run_src
    assert "loadline.load" not in boot_src
    assert "loadline.load" in cli_src


def test_unambiguous_no_login_does_not_construct_agent(tmp_path: Path):
    from loadline.config.resolve import ResolvedConfig
    from loadline.config.target import Target
    from loadline.load.agent import should_call_agent

    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "compose.yaml").write_text(yaml.safe_dump({"services": {"web": {"build": ".", "ports": ["8000:8000"]}}}))
    (repo / "app.py").write_text("def health(): return 'ok'\n")
    cfg = ResolvedConfig(
        hints=None,
        compose_file="compose.yaml",
        target=Target(service="web", port=8000, health_path="/health", origin="http://web:8000/health"),
        blocker=None,
        error=None,
        prepare=[],
        auth={},
        start_set="all",
    )
    assert should_call_agent(cfg, repo) is False


def test_login_route_with_empty_auth_calls_agent(tmp_path: Path):
    from loadline.config.resolve import ResolvedConfig
    from loadline.config.target import Target
    from loadline.load.agent import should_call_agent

    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "compose.yaml").write_text(yaml.safe_dump({"services": {"web": {"build": "."}}}))
    (repo / "app.py").write_text("@app.post('/login')\ndef login(): pass\n")
    cfg = ResolvedConfig(
        hints=None,
        compose_file="compose.yaml",
        target=Target(service="web", port=8000, health_path="/health", origin="http://web:8000/health"),
        blocker=None,
        error=None,
        prepare=[],
        auth={},
        start_set="all",
    )
    assert should_call_agent(cfg, repo) is True


def test_empty_prepare_auth_calls_boot_with_old_args(tmp_path: Path):
    from loadline.adapters.runtime import boot_and_prepare as bap
    from loadline.adapters.runtime.compose_boot import BootOutcome
    from loadline.config.resolve import ResolvedConfig

    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "compose.yaml").write_text(yaml.safe_dump({"services": {"web": {"image": "x"}}}))
    booted = BootOutcome(status="booted", exit_code=0, boot={"health": {"url": "http://web:8000/h"}}, run_id="r1")
    cfg = ResolvedConfig(hints=None, compose_file="compose.yaml", target=None, blocker=None, error=None, prepare=[], auth={}, start_set="all")
    captured: dict = {}

    def fake_boot(r, *, hints=None, teardown=True, require_auth=True, progress=None):
        captured.update({"hints": hints, "teardown": teardown, "require_auth": require_auth, "progress": progress})
        return booted

    with patch("loadline.adapters.runtime.boot_and_prepare.boot_repository", side_effect=fake_boot):
        out = bap.boot_and_prepare(repo, hints=None, config=cfg, teardown=False, require_auth=False, progress=None)
    assert out is booted
    assert captured["teardown"] is False
    assert captured["require_auth"] is False


def test_try_boot_capped_at_5(tmp_path: Path):
    from loadline.adapters.runtime.compose_boot import BootOutcome
    from loadline.load.tools import TryBootCap

    cap = TryBootCap(limit=5)
    repo = tmp_path / "repo"
    repo.mkdir()
    booted = BootOutcome(status="booted", exit_code=0, boot={}, run_id="r1")
    with patch("loadline.adapters.runtime.boot_and_prepare.boot_and_prepare", return_value=booted):
        for _ in range(5):
            cap.try_boot(repo, None)
        res = cap.try_boot(repo, None)
    assert res.get("capped") is True


def test_run_ignores_generated_when_target_exists(tmp_path: Path, monkeypatch):
    # Resolve returns target → run ignores generated file (zero-config preserved).
    from loadline.config.fingerprint import config_dir_for_repo

    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "compose.yaml").write_text(yaml.safe_dump({"services": {"web": {"build": ".", "ports": ["8000:8000"]}}}))
    monkeypatch.setenv("LOADLINE_HOME", str(tmp_path / "home"))
    gen_dir = config_dir_for_repo(repo)
    gen_dir.mkdir(parents=True)
    (gen_dir / "loadline.yaml").write_text(
        yaml.safe_dump({"app_service": "evil", "container_port": 9999, "health_path": "/evil"})
    )
    from loadline.config.resolve import resolve

    cfg = resolve(repo)
    # Detection finds a target (web), so run must ignore evil generated file.
    assert cfg.target is not None
    assert cfg.target.service != "evil"
