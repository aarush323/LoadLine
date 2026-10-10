"""loadline skills status|install|uninstall."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from loadline.paths import loadline_home
from loadline.skills.bundle import read_canonical_skill, skill_content_hash
from loadline.skills.manifest import InstalledSkillFile, SkillsManifest
from loadline.skills.paths import HOST_AGENTS, install_targets


@dataclass
class SkillsResult:
    code: int
    lines: list[str]


def _user_home(home: Path | None) -> Path:
    if home is not None:
        return home.expanduser().resolve()
    import os

    return Path(os.environ.get("HOME", str(Path.home()))).expanduser().resolve()


def _install_one(
    target: Path,
    content: str,
    *,
    force: bool,
    manifest: SkillsManifest,
) -> SkillsResult:
    target = target.resolve()
    if target.is_file():
        existing = target.read_text(encoding="utf-8")
        if existing == content:
            return SkillsResult(0, [f"unchanged: {target}"])
        managed = target in manifest.paths()
        if not force and not managed:
            return SkillsResult(
                2,
                [
                    f"refused: {target} exists and was not installed by Loadline (use --force to overwrite)",
                ],
            )
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return SkillsResult(0, [f"installed: {target}"])


def skills_install(
    *,
    host_all: bool = False,
    force: bool = False,
    dest_root: Path | None = None,
    home: Path | None = None,
) -> SkillsResult:
    try:
        content = read_canonical_skill()
    except FileNotFoundError as exc:
        return SkillsResult(2, [str(exc)])
    digest = skill_content_hash(content)
    uhome = _user_home(home)
    manifest = SkillsManifest.load()
    lines: list[str] = []
    code = 0
    new_files: list[InstalledSkillFile] = []
    for host, path in install_targets(home=uhome, host_all=host_all, dest_root=dest_root):
        result = _install_one(path, content, force=force, manifest=manifest)
        lines.extend(result.lines)
        if result.code != 0:
            code = result.code
            continue
        new_files.append(InstalledSkillFile(path=str(path.resolve()), host=host))

    if code == 0 and new_files:
        merged = {str(p.path): p for p in manifest.files}
        for item in new_files:
            merged[item.path] = item
        manifest.files = list(merged.values())
        manifest.content_hash = digest
        manifest.save()
    return SkillsResult(code, lines)


def skills_status(
    *,
    host_all: bool = False,
    dest_root: Path | None = None,
    home: Path | None = None,
) -> SkillsResult:
    try:
        content = read_canonical_skill()
    except FileNotFoundError as exc:
        return SkillsResult(2, [str(exc)])
    digest = skill_content_hash(content)
    manifest = SkillsManifest.load()
    lines = [
        f"canonical_hash: {digest}",
        f"manifest: {SkillsManifest.manifest_path()}",
        f"manifest_files: {len(manifest.files)}",
    ]
    for host, path in install_targets(home=_user_home(home), host_all=host_all, dest_root=dest_root):
        if not path.is_file():
            lines.append(f"{host}: missing ({path})")
            continue
        on_disk = path.read_text(encoding="utf-8")
        state = "ok" if on_disk == content else "drift"
        managed = path.resolve() in {p.resolve() for p in manifest.paths()}
        lines.append(f"{host}: {state} managed={managed} ({path})")
    return SkillsResult(0, lines)


def skills_uninstall(
    *,
    host_all: bool = False,
    dest_root: Path | None = None,
    home: Path | None = None,
) -> SkillsResult:
    manifest = SkillsManifest.load()
    candidates = list(manifest.files)
    if dest_root is not None:
        dest_file = install_targets(dest_root=dest_root)[0][1].resolve()
        candidates = [f for f in candidates if Path(f.path).resolve() == dest_file]
    elif not host_all:
        candidates = [f for f in candidates if f.host == HOST_AGENTS]

    lines: list[str] = []
    removed: set[Path] = set()
    for entry in candidates:
        path = Path(entry.path)
        if not path.is_file():
            lines.append(f"already absent: {path}")
            continue
        path.unlink()
        removed.add(path.resolve())
        lines.append(f"removed: {path}")
        parent = path.parent
        if parent.is_dir() and not any(parent.iterdir()):
            parent.rmdir()

    if removed:
        manifest.files = [f for f in manifest.files if Path(f.path).resolve() not in removed]
        if not manifest.files:
            manifest.content_hash = ""
        manifest.save()
    elif not lines:
        lines.append("nothing to uninstall")
    return SkillsResult(0, lines)


def main_skills(argv: list[str]) -> int:
    import argparse
    import os

    parser = argparse.ArgumentParser(prog="loadline skills")
    sub = parser.add_subparsers(dest="action", required=True)
    for name in ("status", "install", "uninstall"):
        p = sub.add_parser(name)
        p.add_argument("--host", choices=["default", "all"], default="default")
        p.add_argument("--dest", type=Path, default=None, help="Skills parent directory (for tests)")
        if name == "install":
            p.add_argument("--force", action="store_true")
    args = parser.parse_args(argv)
    home = Path(os.environ.get("HOME", str(Path.home()))).expanduser().resolve()
    host_all = args.host == "all"
    if args.action == "status":
        result = skills_status(host_all=host_all, dest_root=args.dest, home=home)
    elif args.action == "install":
        result = skills_install(
            host_all=host_all,
            force=args.force,
            dest_root=args.dest,
            home=home,
        )
    else:
        result = skills_uninstall(host_all=host_all, dest_root=args.dest, home=home)
    for line in result.lines:
        print(line)
    return result.code
