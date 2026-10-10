"""Provision pinned Entire CLI and Graph into a Loadline-managed directory.

Does not use sudo, does not edit shell startup files, and does not replace an
existing Entire install. A compatible binary already on PATH is reused.
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import platform
import shutil
import stat
import subprocess
import tarfile
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from loadline.entire_runtime.errors import (
    DownloadError,
    GitIncompatible,
    IntegrityError,
    PlatformUnsupported,
)
from loadline.entire_runtime.manifest import (
    CLI_SHA256,
    CLI_VERSION,
    GIT_MIN,
    GRAPH_SHA256,
    GRAPH_VERSION,
    cli_archive_name,
    cli_url,
    declared_platforms,
    graph_archive_name,
    graph_url,
    platform_key,
)

STAMP_NAME = "install.json"
DOWNLOAD_TIMEOUT_S = 120


@dataclass(frozen=True)
class Toolchain:
    entire: Path
    plugin_dir: Path | None
    source: str  # "managed" or "existing"
    cli_version: str
    graph_version: str

    def subprocess_env(self, base: dict[str, str] | None = None) -> dict[str, str]:
        env = dict(base or os.environ)
        env["PATH"] = str(self.entire.parent) + os.pathsep + env.get("PATH", "")
        if self.plugin_dir is not None:
            env["ENTIRE_PLUGIN_DIR"] = str(self.plugin_dir)
        return env


def loadline_home() -> Path:
    override = os.environ.get("LOADLINE_HOME")
    if override:
        return Path(override)
    return Path.home() / ".local" / "share" / "loadline"


def managed_root(home: Path | None = None) -> Path:
    return (home or loadline_home()) / "entire"


class UrlDownloader:
    def get(self, url: str) -> bytes:
        try:
            with urllib.request.urlopen(url, timeout=DOWNLOAD_TIMEOUT_S) as response:
                return response.read()
        except urllib.error.URLError as exc:
            raise DownloadError(
                f"Could not download {url}: {exc.reason}",
                repair="Check the network and run `loadline doctor` again. Nothing was left half-installed.",
            ) from exc


def parse_version(text: str) -> str | None:
    import re

    match = re.search(r"(\d+\.\d+\.\d+)", text)
    return match.group(1) if match else None


def git_version() -> tuple[int, int, int] | None:
    try:
        out = subprocess.check_output(["git", "--version"], text=True, stderr=subprocess.DEVNULL)
    except (OSError, subprocess.CalledProcessError):
        return None
    parsed = parse_version(out)
    if parsed is None:
        return None
    major, minor, patch = (int(part) for part in parsed.split("."))
    return major, minor, patch


def require_git() -> tuple[int, int, int]:
    found = git_version()
    needed = ".".join(str(part) for part in GIT_MIN)
    if found is None:
        raise GitIncompatible(
            "Git is not on PATH.",
            repair=f"Install Git {needed} or newer and run `loadline doctor` again. Entire Graph needs it to inspect repository objects.",
        )
    if found < GIT_MIN:
        have = ".".join(str(part) for part in found)
        raise GitIncompatible(
            f"Git {have} is older than {needed}.",
            repair=f"Upgrade Git to {needed} or newer (the version that added the object protocol Entire Graph uses) and run `loadline doctor` again.",
        )
    return found


def require_platform(system: str | None = None, machine: str | None = None) -> tuple[str, str]:
    system = system if system is not None else platform.system().lower()
    machine = machine if machine is not None else platform.machine()
    found = platform_key(system, machine)
    if found is None:
        raise PlatformUnsupported(
            f"Loadline does not provision Entire on {system}/{machine}.",
            repair=f"Supported platforms: {declared_platforms()}. This machine was not claimed as supported.",
        )
    return found


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _extract_binary(archive: bytes, binary_name: str, dest: Path) -> None:
    try:
        with tarfile.open(fileobj=io.BytesIO(archive), mode="r:gz") as tar:
            member = None
            for item in tar.getmembers():
                if not item.isfile():
                    continue
                parts = Path(item.name).parts
                if ".." in parts or parts[-1] != binary_name:
                    continue
                member = item
                break
            if member is None:
                raise IntegrityError(
                    f"Archive does not contain {binary_name}.",
                    repair="Run `loadline doctor` again. If it repeats, the pinned release layout changed and the manifest must be updated.",
                )
            extracted = tar.extractfile(member)
            if extracted is None:
                raise IntegrityError(
                    f"Could not read {binary_name} from the archive.",
                    repair="Run `loadline doctor` again.",
                )
            payload = extracted.read()
    except tarfile.TarError as exc:
        raise IntegrityError(
            f"Archive for {binary_name} is not a valid tar.gz: {exc}",
            repair="Run `loadline doctor` again. The partial download was discarded.",
        ) from exc
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".tmp")
    tmp.write_bytes(payload)
    tmp.chmod(tmp.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    os.replace(tmp, dest)


def _install_one(
    *,
    url: str,
    archive_name: str,
    expected_sha: str,
    binary_name: str,
    dest: Path,
    downloader: UrlDownloader,
    staging: Path,
) -> None:
    if dest.is_file():
        return
    staging.mkdir(parents=True, exist_ok=True)
    partial = staging / (archive_name + ".partial")
    try:
        data = downloader.get(url)
        partial.write_bytes(data)
        digest = _sha256(data)
        if digest != expected_sha:
            partial.unlink(missing_ok=True)
            dest.unlink(missing_ok=True)
            raise IntegrityError(
                f"Checksum mismatch for {archive_name}.",
                repair="The download did not match the checksum pinned from the official release. Run `loadline doctor` again. The existing Entire install, if any, was not changed.",
            )
        _extract_binary(data, binary_name, dest)
    except DownloadError:
        partial.unlink(missing_ok=True)
        raise
    else:
        partial.unlink(missing_ok=True)


def _read_stamp(root: Path) -> dict:
    path = root / STAMP_NAME
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError:
        return {}


def _write_stamp(root: Path, toolchain: Toolchain) -> None:
    payload = {
        "complete": True,
        "cli_version": toolchain.cli_version,
        "graph_version": toolchain.graph_version,
        "entire": str(toolchain.entire),
        "plugin_dir": str(toolchain.plugin_dir) if toolchain.plugin_dir else None,
    }
    text = json.dumps(payload)
    tmp = root / (STAMP_NAME + ".tmp")
    tmp.write_text(text)
    os.replace(tmp, root / STAMP_NAME)


def _version_of(binary: Path, args: list[str], env: dict[str, str] | None = None) -> str | None:
    try:
        out = subprocess.check_output(
            [str(binary), *args],
            text=True,
            stderr=subprocess.DEVNULL,
            env=env,
            timeout=20,
        )
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return None
    return parse_version(out)


def _existing_toolchain() -> Toolchain | None:
    found = shutil.which("entire")
    if not found:
        return None
    binary = Path(found)
    cli = _version_of(binary, ["version"])
    graph = _version_of(binary, ["graph", "version"])
    if cli != CLI_VERSION or graph != GRAPH_VERSION:
        return None
    return Toolchain(
        entire=binary,
        plugin_dir=None,
        source="existing",
        cli_version=cli,
        graph_version=graph,
    )


def _managed_ready(root: Path) -> Toolchain | None:
    entire = root / "cli" / f"v{CLI_VERSION}" / "entire"
    plugin_dir = root / "plugins" / f"v{GRAPH_VERSION}"
    graph_bin = plugin_dir / "bin" / "entire-graph"
    stamp = _read_stamp(root)
    if not entire.is_file() or not graph_bin.is_file() or not stamp.get("complete"):
        return None
    if stamp.get("cli_version") != CLI_VERSION or stamp.get("graph_version") != GRAPH_VERSION:
        return None
    env = os.environ.copy()
    env["ENTIRE_PLUGIN_DIR"] = str(plugin_dir)
    env["PATH"] = str(entire.parent) + os.pathsep + env.get("PATH", "")
    cli = _version_of(entire, ["version"], env)
    graph = _version_of(entire, ["graph", "version"], env)
    if cli != CLI_VERSION or graph != GRAPH_VERSION:
        return None
    return Toolchain(
        entire=entire,
        plugin_dir=plugin_dir,
        source="managed",
        cli_version=CLI_VERSION,
        graph_version=GRAPH_VERSION,
    )


def ensure_toolchain(
    home: Path | None = None,
    downloader: UrlDownloader | None = None,
    *,
    system: str | None = None,
    machine: str | None = None,
) -> Toolchain:
    """Install or reuse the pinned Entire CLI and Graph plugin."""

    require_git()
    os_name, arch = require_platform(system, machine)
    root = managed_root(home)
    root.mkdir(parents=True, exist_ok=True)

    existing = _existing_toolchain()
    if existing is not None and not _inside(existing.entire, root):
        return existing

    ready = _managed_ready(root)
    if ready is not None:
        return ready

    stamp = _read_stamp(root)
    if stamp.get("cli_version") not in (None, CLI_VERSION):
        shutil.rmtree(root / "cli", ignore_errors=True)
    if stamp.get("graph_version") not in (None, GRAPH_VERSION):
        shutil.rmtree(root / "plugins", ignore_errors=True)

    fetcher = downloader or UrlDownloader()
    key = f"{os_name}_{arch}"
    cli_dest = root / "cli" / f"v{CLI_VERSION}" / "entire"
    plugin_dir = root / "plugins" / f"v{GRAPH_VERSION}"
    graph_dest = plugin_dir / "bin" / "entire-graph"
    staging = root / "staging"
    if staging.exists():
        shutil.rmtree(staging)
    _install_one(
        url=cli_url(os_name, arch),
        archive_name=cli_archive_name(os_name, arch),
        expected_sha=CLI_SHA256[key],
        binary_name="entire",
        dest=cli_dest,
        downloader=fetcher,
        staging=staging,
    )
    _install_one(
        url=graph_url(os_name, arch),
        archive_name=graph_archive_name(os_name, arch),
        expected_sha=GRAPH_SHA256[key],
        binary_name="entire-graph",
        dest=graph_dest,
        downloader=fetcher,
        staging=staging,
    )
    shutil.rmtree(staging, ignore_errors=True)
    toolchain = Toolchain(
        entire=cli_dest,
        plugin_dir=plugin_dir,
        source="managed",
        cli_version=CLI_VERSION,
        graph_version=GRAPH_VERSION,
    )
    _write_stamp(root, toolchain)
    return toolchain


def _inside(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
    except ValueError:
        return False
    return True
