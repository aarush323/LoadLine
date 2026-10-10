from pathlib import Path
from unittest.mock import patch

from loadline.adapters.runtime.boot_and_prepare import boot_and_prepare
from loadline.adapters.runtime.compose_boot import BootOutcome


def _booted_outcome(tmp_path: Path) -> BootOutcome:
    run_dir = tmp_path / "run1"
    run_dir.mkdir()
    (run_dir / "profile.json").write_text('{"compose_files": ["compose.yaml"]}')
    boot = {
        "health": {"url": "http://web:8000/health", "path": "/health"},
        "run_dir": str(run_dir),
        "services": [{"name": "web"}],
    }
    return BootOutcome(status="booted", exit_code=0, boot=boot, run_id="r1")


def test_passthrough_and_writes_target(tmp_path: Path):
    outcome = _booted_outcome(tmp_path)
    captured: dict = {}

    def fake_boot(repo, *, hints=None, teardown=True, require_auth=True, progress=None):
        captured.update({"hints": hints, "teardown": teardown, "require_auth": require_auth, "progress": progress})
        return outcome

    with patch(
        "loadline.adapters.runtime.boot_and_prepare.boot_repository", side_effect=fake_boot
    ):
        hints = {"marker": 1}
        progress = object()
        got = boot_and_prepare(
            tmp_path, hints=hints, teardown=False, require_auth=False, progress=progress  # type: ignore[arg-type]
        )
    assert got is outcome
    assert captured["hints"] is hints
    assert captured["teardown"] is False
    assert captured["require_auth"] is False
    assert captured["progress"] is progress
    data_path = Path(outcome.boot["run_dir"]) / "resolved_target.json"
    assert data_path.is_file()
    import json

    payload = json.loads(data_path.read_text())
    assert payload["service"] == "web"
    assert payload["port"] == 8000
    assert payload["path"] == "/health"
    assert payload["origin"] == "http://web:8000/health"
    assert payload["start_set"] == "all"
    assert "username" not in payload and "password" not in payload


def test_no_write_when_blocked(tmp_path: Path):
    blocked = BootOutcome(status="blocked", exit_code=10, blocker={"code": "x"}, run_id="r2")
    with patch(
        "loadline.adapters.runtime.boot_and_prepare.boot_repository", return_value=blocked
    ):
        got = boot_and_prepare(tmp_path, teardown=True, require_auth=False, progress=None)
    assert got is blocked
    # No run_dir to write; ensure no crash and no file in tmp.
    assert not (tmp_path / "resolved_target.json").exists()
