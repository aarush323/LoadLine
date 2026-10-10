"""Pinned Entire CLI and Graph releases.

Checksums were copied from the published ``checksums.txt`` of each stable
release on 2026-10-10. Runtime never resolves a floating tag.

CLI: https://github.com/entireio/cli/releases/tag/v0.11.4
Graph: https://github.com/entireio/entire-graph/releases/tag/v0.4.0
"""

from __future__ import annotations

GIT_MIN = (2, 36, 0)

# (sys.platform, machine) -> (os, arch) used in upstream asset names.
SUPPORTED_PLATFORMS: dict[tuple[str, str], tuple[str, str]] = {
    ("linux", "x86_64"): ("linux", "amd64"),
    ("linux", "aarch64"): ("linux", "arm64"),
    ("darwin", "x86_64"): ("darwin", "amd64"),
    ("darwin", "arm64"): ("darwin", "arm64"),
}

CLI_VERSION = "0.11.4"
GRAPH_VERSION = "0.4.0"

CLI_SHA256 = {
    "darwin_amd64": "74ff766a6877741ece7f100b2c428bd5d748899018f464a6ea6fa397b33da345",
    "darwin_arm64": "6636dd5bf1b2ff9a9c52d4ea1ad936799ada962142f0f5e5c3c8611f3acd347b",
    "linux_amd64": "b93634124bf51bc5e07156d92b53853d124325a3ff9af60c4960307bf8eb870f",
    "linux_arm64": "389274ce4bfc0813fe5d6ac0cc8b270beddfa025340e4506f4807dab7798f447",
}

GRAPH_SHA256 = {
    "darwin_amd64": "6545545ed0818ad05602920ea7dfdd9e7fe07ac4cc7697961e30cee03cdfe978",
    "darwin_arm64": "a808a76238881de6e4fa2ea4768de52a4bd3599d2eb35855d7db4cdf3ab23cfa",
    "linux_amd64": "24e3edef9d580158e4f125c50950fc4a41865b975d32ab4142d944c88eb9bc95",
    "linux_arm64": "d2aecc39e886bd8a8a3616a8c8af4fcf6764e31b90975c4f3fdb5af5e873bf98",
}


def platform_key(system: str, machine: str) -> tuple[str, str] | None:
    return SUPPORTED_PLATFORMS.get((system, machine))


def cli_archive_name(os_name: str, arch: str) -> str:
    return f"entire_{os_name}_{arch}.tar.gz"


def graph_archive_name(os_name: str, arch: str) -> str:
    return f"entire-graph_{GRAPH_VERSION}_{os_name}_{arch}.tar.gz"


def cli_url(os_name: str, arch: str) -> str:
    name = cli_archive_name(os_name, arch)
    return f"https://github.com/entireio/cli/releases/download/v{CLI_VERSION}/{name}"


def graph_url(os_name: str, arch: str) -> str:
    name = graph_archive_name(os_name, arch)
    return f"https://github.com/entireio/entire-graph/releases/download/v{GRAPH_VERSION}/{name}"


def declared_platforms() -> str:
    names = [f"{os_name}/{arch}" for os_name, arch in SUPPORTED_PLATFORMS.values()]
    return ", ".join(names)
