"""Record of skill files installed by Loadline."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from loadline.paths import loadline_home
from loadline.skills.bundle import SKILL_NAME

MANIFEST_VERSION = 1
MANIFEST_NAME = "skills-install-manifest.json"


@dataclass
class InstalledSkillFile:
    path: str
    host: str

    def to_dict(self) -> dict:
        return {"path": self.path, "host": self.host}


@dataclass
class SkillsManifest:
    version: int = MANIFEST_VERSION
    skill_name: str = SKILL_NAME
    content_hash: str = ""
    files: list[InstalledSkillFile] = field(default_factory=list)

    @classmethod
    def manifest_path(cls, home: Path | None = None) -> Path:
        return (home or loadline_home()) / MANIFEST_NAME

    @classmethod
    def load(cls, home: Path | None = None) -> SkillsManifest:
        path = cls.manifest_path(home)
        if not path.is_file():
            return cls()
        data = json.loads(path.read_text(encoding="utf-8"))
        files = [InstalledSkillFile(**item) for item in data.get("files", [])]
        return cls(
            version=int(data.get("version", MANIFEST_VERSION)),
            skill_name=str(data.get("skill_name", SKILL_NAME)),
            content_hash=str(data.get("content_hash", "")),
            files=files,
        )

    def save(self, home: Path | None = None) -> None:
        path = self.manifest_path(home)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": self.version,
            "skill_name": self.skill_name,
            "content_hash": self.content_hash,
            "files": [f.to_dict() for f in self.files],
        }
        path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    def paths(self) -> list[Path]:
        return [Path(f.path) for f in self.files]
