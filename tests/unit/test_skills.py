from pathlib import Path

import pytest

from loadline.core.leakage import _forbidden_tokens
from loadline.skills.bundle import canonical_skill_path, read_canonical_skill
from loadline.skills.commands import skills_install, skills_status, skills_uninstall
from loadline.skills.manifest import SkillsManifest
from loadline.skills.paths import dest_skill_file


@pytest.fixture
def skill_home(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("LOADLINE_HOME", str(tmp_path / "loadline"))
    return tmp_path


def test_skill_has_six_sections_and_description():
    text = read_canonical_skill()
    assert "load-testing" in text.lower() or "load-testing" in text
    assert "scalability investigation" in text.lower()
    for n in range(1, 7):
        assert f"## {n}." in text
    repo_skill = Path(__file__).resolve().parents[2] / "skills" / "loadline-run" / "SKILL.md"
    assert repo_skill.read_text(encoding="utf-8") == text or canonical_skill_path().read_text() == text


def test_skill_has_no_fixture_tokens():
    text = read_canonical_skill()
    root = Path(__file__).resolve().parents[2]
    for token in _forbidden_tokens(root):
        assert token not in text


def test_install_idempotent(skill_home: Path):
    dest = skill_home / "skills-root"
    first = skills_install(dest_root=dest)
    second = skills_install(dest_root=dest)
    assert first.code == 0
    assert second.code == 0
    assert any("installed" in line or "unchanged" in line for line in first.lines)
    assert any("unchanged" in line for line in second.lines)
    target = dest_skill_file(dest)
    assert target.is_file()


def test_install_refuses_unrelated_file(skill_home: Path):
    dest = skill_home / "skills-root"
    target = dest_skill_file(dest)
    target.parent.mkdir(parents=True)
    target.write_text("unrelated skill content\n", encoding="utf-8")
    result = skills_install(dest_root=dest)
    assert result.code == 2
    assert "refused" in result.lines[0]
    assert target.read_text().startswith("unrelated")


def test_install_force_overwrites_unrelated(skill_home: Path):
    dest = skill_home / "skills-root"
    target = dest_skill_file(dest)
    target.parent.mkdir(parents=True)
    target.write_text("unrelated\n", encoding="utf-8")
    result = skills_install(dest_root=dest, force=True)
    assert result.code == 0
    assert read_canonical_skill() in target.read_text()


def test_uninstall_removes_only_manifest_files(skill_home: Path):
    dest = skill_home / "skills-root"
    skills_install(dest_root=dest)
    target = dest_skill_file(dest)
    stray = dest / "other-skill" / "SKILL.md"
    stray.parent.mkdir(parents=True)
    stray.write_text("keep me", encoding="utf-8")
    manifest = SkillsManifest.load()
    assert manifest.files
    result = skills_uninstall(dest_root=dest)
    assert result.code == 0
    assert not target.is_file()
    assert stray.is_file()
    assert SkillsManifest.load().files == []


def test_host_all_installs_agents_and_claude(skill_home: Path):
    result = skills_install(host_all=True)
    assert result.code == 0
    agents = skill_home / ".agents" / "skills" / "loadline-run" / "SKILL.md"
    claude = skill_home / ".claude" / "skills" / "loadline-run" / "SKILL.md"
    assert agents.is_file() and claude.is_file()
    manifest = SkillsManifest.load()
    assert len(manifest.files) == 2


def test_skills_status_reports_ok(skill_home: Path):
    skills_install(dest_root=skill_home / "skills-root")
    status = skills_status(dest_root=skill_home / "skills-root")
    assert status.code == 0
    assert any("ok" in line for line in status.lines)


def test_cli_skills_install(skill_home: Path, monkeypatch):
    from loadline.cli import main

    dest = skill_home / "skills-root"
    code = main(["skills", "install", "--dest", str(dest)])
    assert code == 0
    assert dest_skill_file(dest).is_file()
