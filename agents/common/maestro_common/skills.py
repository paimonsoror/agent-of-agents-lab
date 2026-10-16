"""Loader for agentskills.io-style skill bundles (ADR-0007).

A skill is a directory with a SKILL.md (YAML frontmatter + Markdown body) and an optional
references/ folder. The full body of every configured skill goes into the system prompt;
references are listed by name and read on demand through the `read_reference` tool.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

_NAME_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n(.*)$", re.DOTALL)


class SkillError(ValueError):
    pass


@dataclass(frozen=True)
class Skill:
    name: str
    description: str
    body: str
    path: Path
    metadata: dict[str, str] = field(default_factory=dict)
    references: tuple[str, ...] = ()

    @property
    def version(self) -> str:
        return str(self.metadata.get("version", "0"))

    @property
    def domain(self) -> str:
        return str(self.metadata.get("domain", ""))


def load_skill(path: Path) -> Skill:
    """Parse one skill directory, enforcing the parts of the spec that matter at runtime."""
    skill_md = path / "SKILL.md"
    if not skill_md.is_file():
        raise SkillError(f"{path}: missing SKILL.md")
    match = _FRONTMATTER_RE.match(skill_md.read_text(encoding="utf-8"))
    if not match:
        raise SkillError(f"{skill_md}: missing YAML frontmatter")
    front = yaml.safe_load(match.group(1)) or {}
    body = match.group(2).strip()

    name = str(front.get("name", ""))
    description = str(front.get("description", "")).strip()
    if not _NAME_RE.match(name) or len(name) > 64:
        raise SkillError(f"{skill_md}: invalid name {name!r}")
    if name != path.name:
        raise SkillError(f"{skill_md}: name {name!r} must match directory {path.name!r}")
    if not description or len(description) > 1024:
        raise SkillError(f"{skill_md}: description must be 1-1024 characters")
    if body.count("\n") > 500:
        raise SkillError(f"{skill_md}: body exceeds 500 lines; move detail into references/")

    metadata = {str(k): str(v) for k, v in (front.get("metadata") or {}).items()}
    refs_dir = path / "references"
    references = tuple(sorted(p.name for p in refs_dir.glob("*.md"))) if refs_dir.is_dir() else ()
    return Skill(name=name, description=description, body=body, path=path, metadata=metadata, references=references)


def load_skills(names: tuple[str, ...] | list[str], skills_dir: str | Path) -> list[Skill]:
    root = Path(skills_dir)
    return [load_skill(root / n) for n in names]


def read_reference(skill: Skill, file: str) -> str:
    """Return one reference file. Rejects anything outside the skill's references/ folder."""
    if file not in skill.references:
        raise SkillError(f"{skill.name}: unknown reference {file!r}; available: {list(skill.references)}")
    return (skill.path / "references" / file).read_text(encoding="utf-8")


def render_system_prompt(skills: list[Skill]) -> str:
    """The stable, cacheable part of a system prompt: every skill's full instructions."""
    parts: list[str] = []
    for s in skills:
        refs = "\n".join(f"- {r}" for r in s.references) or "- (none)"
        parts.append(
            f"<skill name=\"{s.name}\" version=\"{s.version}\">\n"
            f"{s.body}\n\n"
            f"Reference files you may read with read_reference(skill=\"{s.name}\", file=...):\n{refs}\n"
            f"</skill>"
        )
    return "\n\n".join(parts)
