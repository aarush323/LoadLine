"""Provisioning, doctor, and graph analysis. Downloads are mocked except the integration test."""

from __future__ import annotations

import hashlib
import io
import json
import os
import stat
import tarfile
from pathlib import Path

import pytest

from loadline.cli import main
from loadline.entire_runtime import install
from loadline.entire_runtime.analyze import analyze_repository
from loadline.entire_runtime.errors import DownloadError, GitIncompatible, IntegrityError, PlatformUnsupported
from loadline.entire_runtime.graph import GraphClient
from loadline.entire_runtime.install import Toolchain, ensure_toolchain
from loadline.entire_runtime.manifest import CLI_SHA256, GRAPH_SHA256

SCRIPT = """#!/bin/sh
printf '%s\\n' "$*" >> "$LOADLINE_FAKE_LOG"
if [ "$1" = "version" ]; then
  echo "Entire CLI 0.11.4"
  exit 0
fi
if [ "$1" = "graph" ] && [ "$2" = "version" ]; then
  echo "v0.4.0"
  exit 0
fi
if [ "$1" = "graph" ] && [ "$2" = "help" ]; then
  printf '%s\\n' "  search           Find code"
  exit 0
fi
if [ "$1" = "graph" ] && [ "$2" = "capabilities" ]; then
  echo '{"supported_relation_types":["CALLS","HANDLES_ROUTE"]}'
  exit 0
fi
if [ "$1" = "graph" ] && [ "$2" = "edges" ] && [ "$3" = "--help" ]; then
  echo "--worktree"
  exit 0
fi
if [ "$1" = "graph" ] && [ "$2" = "edges" ]; then
  echo '{"relation":"HANDLES_ROUTE","file":"app.py","path":"/health"}'
  exit 0
fi
if [ "$1" = "graph" ] && [ "$2" = "search" ]; then
  echo '{"results":[{"file_path":"app.py","start_line":1,"end_line":2}]}'
  exit 0
fi
if [ "$1" = "graph" ] && [ "$2" = "query" ]; then
  echo '{"results":[{"file_path":"app.py","start_line":1,"end_line":2}]}'
  exit 0
fi
exit 0
"""


class FakeDownloader:
    def __init__(self, payloads: dict[str, bytes], *, fail_times: int = 0) -> None:
        self.payloads = payloads
        self.fail_times = fail_times
        self.calls: list[str] = []

    def get(self, url: str) -> bytes:
        self.calls.append(url)
        if self.fail_times:
            self.fail_times -= 1
            raise DownloadError("network down", repair="retry")
        for name, payload in self.payloads.items():
            if url.endswith(name):
                return payload
        raise DownloadError(f"unexpected {url}", repair="retry")


def _archive(name: str, body: bytes) -> bytes:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as tar:
        info = tarfile.TarInfo(name)
        info.size = len(body)
        info.mode = 0o755
        tar.addfile(info, io.BytesIO(body))
    return buffer.getvalue()


def _pin(monkeypatch: pytest.MonkeyPatch, cli_bytes: bytes, graph_bytes: bytes) -> None:
    monkeypatch.setitem(CLI_SHA256, "linux_amd64", hashlib.sha256(cli_bytes).hexdigest())
    monkeypatch.setitem(GRAPH_SHA256, "linux_amd64", hashlib.sha256(graph_bytes).hexdigest())


def _hide_existing(monkeypatch: pytest.MonkeyPatch, tmp: Path) -> None:
    empty = tmp / "empty-path"
    empty.mkdir()
    # Hide user Entire installs but keep git for require_git().
    monkeypatch.setenv("PATH", str(empty) + os.pathsep + "/usr/bin")
    monkeypatch.setenv("LOADLINE_HOME", str(tmp / "home"))


@pytest.fixture
def pinned(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    body = SCRIPT.encode()
    cli = _archive("entire", body)
    graph = _archive("entire-graph", body)
    _pin(monkeypatch, cli, graph)
    _hide_existing(monkeypatch, tmp_path)
    monkeypatch.setenv("LOADLINE_FAKE_LOG", str(tmp_path / "calls.log"))
    return cli, graph


def test_fresh_install_is_idempotent(pinned, tmp_path: Path) -> None:
    cli, graph = pinned
    downloader = FakeDownloader(
        {"entire_linux_amd64.tar.gz": cli, "entire-graph_0.4.0_linux_amd64.tar.gz": graph}
    )
    first = ensure_toolchain(system="linux", machine="x86_64", downloader=downloader)
    second = ensure_toolchain(system="linux", machine="x86_64", downloader=downloader)
    assert first.source == "managed"
    assert first.cli_version == "0.11.4"
    assert first.graph_version == "0.4.0"
    assert second.entire == first.entire
    assert len(downloader.calls) == 2
    assert (tmp_path / "home" / "entire" / "install.json").is_file()


def test_reuses_compatible_existing_install(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    bindir = tmp_path / "bin"
    bindir.mkdir()
    binary = bindir / "entire"
    binary.write_text("#!/bin/sh\nif [ \"$1\" = version ]; then echo 'Entire CLI 0.11.4'; exit 0; fi\necho 'v0.4.0'\n")
    binary.chmod(0o755)
    before = binary.stat().st_mtime_ns
    monkeypatch.setenv("PATH", f"{bindir}{os.pathsep}/usr/bin")
    downloader = FakeDownloader({})
    found = ensure_toolchain(system="linux", machine="x86_64", downloader=downloader)
    assert found.source == "existing"
    assert found.entire == binary
    assert downloader.calls == []
    assert binary.stat().st_mtime_ns == before


def test_incompatible_existing_is_not_overwritten(pinned, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    cli, graph = pinned
    bindir = tmp_path / "bin"
    bindir.mkdir()
    binary = bindir / "entire"
    binary.write_text("#!/bin/sh\necho 'Entire CLI 9.9.9'\n")
    binary.chmod(0o755)
    monkeypatch.setenv("PATH", f"{bindir}{os.pathsep}{os.environ['PATH']}")
    downloader = FakeDownloader(
        {"entire_linux_amd64.tar.gz": cli, "entire-graph_0.4.0_linux_amd64.tar.gz": graph}
    )
    found = ensure_toolchain(system="linux", machine="x86_64", downloader=downloader)
    assert found.source == "managed"
    assert binary.read_text().startswith("#!/bin/sh")
    assert "9.9.9" in binary.read_text()


def test_missing_git(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(install, "git_version", lambda: None)
    with pytest.raises(GitIncompatible):
        ensure_toolchain(system="linux", machine="x86_64")


def test_unsupported_platform(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(install, "git_version", lambda: (2, 43, 0))
    with pytest.raises(PlatformUnsupported) as caught:
        ensure_toolchain(system="freebsd", machine="x86_64")
    assert "not claimed" in caught.value.repair


def test_integrity_failure_leaves_no_binary(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _hide_existing(monkeypatch, tmp_path)
    monkeypatch.setitem(CLI_SHA256, "linux_amd64", "0" * 64)
    downloader = FakeDownloader({"entire_linux_amd64.tar.gz": b"not-the-archive"})
    with pytest.raises(IntegrityError):
        ensure_toolchain(system="linux", machine="x86_64", downloader=downloader)
    cli_bin = tmp_path / "home" / "entire" / "cli" / "v0.11.4" / "entire"
    assert not cli_bin.is_file()


def test_network_error_is_recoverable(pinned, tmp_path: Path) -> None:
    cli, graph = pinned
    downloader = FakeDownloader(
        {"entire_linux_amd64.tar.gz": cli, "entire-graph_0.4.0_linux_amd64.tar.gz": graph},
        fail_times=1,
    )
    with pytest.raises(DownloadError):
        ensure_toolchain(system="linux", machine="x86_64", downloader=downloader)
    found = ensure_toolchain(system="linux", machine="x86_64", downloader=downloader)
    assert found.source == "managed"
    assert len(downloader.calls) == 3


def test_interrupted_partial_is_not_a_ready_install(pinned, tmp_path: Path) -> None:
    cli, graph = pinned
    home = tmp_path / "home" / "entire"
    home.mkdir(parents=True)
    partial_dir = home / "staging"
    partial_dir.mkdir()
    (partial_dir / "entire_linux_amd64.tar.gz.partial").write_bytes(b"partial")
    downloader = FakeDownloader(
        {"entire_linux_amd64.tar.gz": cli, "entire-graph_0.4.0_linux_amd64.tar.gz": graph}
    )
    found = ensure_toolchain(system="linux", machine="x86_64", downloader=downloader)
    assert found.entire.is_file()
    assert not (partial_dir / "entire_linux_amd64.tar.gz.partial").exists()


def test_doctor_reports_versions(pinned, capsys: pytest.CaptureFixture[str]) -> None:
    cli, graph = pinned
    downloader = FakeDownloader(
        {"entire_linux_amd64.tar.gz": cli, "entire-graph_0.4.0_linux_amd64.tar.gz": graph}
    )
    original = ensure_toolchain

    def patched(*args, **kwargs):
        kwargs.setdefault("downloader", downloader)
        kwargs.setdefault("system", "linux")
        kwargs.setdefault("machine", "x86_64")
        return original(*args, **kwargs)

    install_module = __import__("loadline.cli", fromlist=["ensure_toolchain"])
    # doctor imports ensure_toolchain into loadline.cli
    import loadline.cli as cli_mod

    cli_mod.ensure_toolchain = patched
    try:
        code = main(["doctor"])
    finally:
        cli_mod.ensure_toolchain = original
    output = capsys.readouterr().out
    assert code == 0
    assert "entire_cli: 0.11.4" in output
    assert "entire_graph: 0.4.0" in output
    assert "handles_route: True" in output


def _toolchain_from_script(tmp_path: Path, script: str) -> tuple[Toolchain, Path]:
    log = tmp_path / "calls.log"
    binary = tmp_path / "entire"
    binary.write_text(script)
    binary.chmod(binary.stat().st_mode | stat.S_IXUSR)
    os.environ["LOADLINE_FAKE_LOG"] = str(log)
    toolchain = Toolchain(binary, None, "existing", "0.11.4", "0.4.0")
    return toolchain, log


def test_malformed_capabilities_are_degraded(tmp_path: Path) -> None:
    script = SCRIPT.replace(
        '\'{"supported_relation_types":["CALLS","HANDLES_ROUTE"]}\'',
        "'this is not json'",
    )
    toolchain, _log = _toolchain_from_script(tmp_path, script)
    repo = tmp_path / "repo"
    repo.mkdir()
    report = analyze_repository(repo, toolchain=toolchain, client=GraphClient(toolchain, timeout_s=2))
    assert any("capabilities unavailable" in item for item in report.degraded)


def test_timeout(tmp_path: Path) -> None:
    script = "#!/bin/sh\nsleep 5\n"
    toolchain, _log = _toolchain_from_script(tmp_path, script)
    client = GraphClient(toolchain, timeout_s=0.2)
    with pytest.raises(Exception) as caught:
        client.run(["version"])
    assert getattr(caught.value, "timed_out", False) is True


def test_degraded_without_route_relation(tmp_path: Path) -> None:
    script = SCRIPT.replace("HANDLES_ROUTE", "IMPORTS")
    toolchain, log = _toolchain_from_script(tmp_path, script)
    repo = _git_repo(tmp_path / "repo")
    (repo / "app.py").write_text("def health():\n    return 'ok'\n")
    spec = tmp_path / "openapi.json"
    spec.write_text(json.dumps({"paths": {"/health": {"get": {}}}}))
    report = analyze_repository(
        repo,
        openapi=spec,
        live_openapi=True,
        toolchain=toolchain,
        client=GraphClient(toolchain, timeout_s=2),
    )
    assert report.handles_route is False
    assert any("HANDLES_ROUTE" in item for item in report.degraded)
    logged = log.read_text()
    assert "init-agents" not in logged
    assert "--head" not in logged


def test_analyze_reads_source_and_leaves_repo_untouched(tmp_path: Path) -> None:
    toolchain, log = _toolchain_from_script(tmp_path, SCRIPT)
    repo = _git_repo(tmp_path / "app")
    (repo / "app.py").write_text("def health():\n    return 'ok'\n")
    subprocess_commit(repo)
    (repo / "app.py").write_text("def health():\n    return 'changed'\n")
    before = sorted(path.relative_to(repo).as_posix() for path in repo.rglob("*") if path.is_file())
    spec = tmp_path / "openapi.json"
    spec.write_text(json.dumps({"paths": {"/health": {"get": {}}}}))
    report = analyze_repository(
        repo,
        openapi=spec,
        live_openapi=True,
        toolchain=toolchain,
        client=GraphClient(toolchain, timeout_s=2),
    )
    after = sorted(path.relative_to(repo).as_posix() for path in repo.rglob("*") if path.is_file())
    assert before == after
    assert report.routes[0].provenance == "live_openapi"
    assert report.routes[0].source_read is True
    assert report.routes[0].relation == "HANDLES_ROUTE"
    logged = log.read_text()
    assert "--worktree" in logged
    assert "--head" not in logged
    assert "init-agents" not in logged


def test_refuses_init_agents(tmp_path: Path) -> None:
    toolchain, _log = _toolchain_from_script(tmp_path, SCRIPT)
    with pytest.raises(Exception):
        GraphClient(toolchain).run(["init-agents"])


def _git_repo(path: Path) -> Path:
    import subprocess

    path.mkdir()
    subprocess.check_call(["git", "init"], cwd=path, stdout=subprocess.DEVNULL)
    subprocess.check_call(["git", "config", "user.email", "t@example.com"], cwd=path)
    subprocess.check_call(["git", "config", "user.name", "t"], cwd=path)
    (path / "README").write_text("x\n")
    subprocess.check_call(["git", "add", "README"], cwd=path)
    subprocess.check_call(["git", "commit", "-m", "init"], cwd=path, stdout=subprocess.DEVNULL)
    return path


def subprocess_commit(repo: Path) -> None:
    import subprocess

    subprocess.check_call(["git", "add", "app.py"], cwd=repo)
    subprocess.check_call(["git", "commit", "-m", "app"], cwd=repo, stdout=subprocess.DEVNULL)


@pytest.mark.integration
def test_official_archives_install(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    if os.environ.get("LOADLINE_ENTIRE_INTEGRATION") != "1":
        pytest.skip("set LOADLINE_ENTIRE_INTEGRATION=1 to download pinned official artifacts")
    _hide_existing(monkeypatch, tmp_path)
    toolchain = ensure_toolchain()
    assert toolchain.source == "managed"
    assert toolchain.cli_version == "0.11.4"
    assert toolchain.graph_version == "0.4.0"
    again = ensure_toolchain()
    assert again.entire == toolchain.entire
