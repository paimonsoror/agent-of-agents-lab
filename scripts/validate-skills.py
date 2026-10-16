#!/usr/bin/env python3
"""Validate every skill bundle under a directory against the agentskills.io spec (ADR-0007).

Checks: SKILL.md exists; YAML frontmatter with `name` (1-64 chars, lowercase/digits/hyphens,
no leading/trailing/double hyphen, equal to the directory name) and `description` (1-1024 chars);
body <= 500 lines; `metadata` values are strings; references/ contains only .md files.
Usage: validate-skills.py <skills-dir>   (exit 1 on any problem)
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

NAME_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
FRONT_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n(.*)$", re.DOTALL)


def parse_frontmatter(text: str) -> tuple[dict, str] | None:
    m = FRONT_RE.match(text)
    if not m:
        return None
    front: dict = {}
    current_map: dict | None = None
    for raw in m.group(1).splitlines():
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        if raw.startswith((" ", "\t")) and current_map is not None:
            k, _, v = raw.strip().partition(":")
            current_map[k.strip()] = v.strip().strip('"').strip("'")
            continue
        k, _, v = raw.partition(":")
        v = v.strip()
        if v == "":
            current_map = {}
            front[k.strip()] = current_map
        else:
            current_map = None
            front[k.strip()] = v.strip('"').strip("'")
    return front, m.group(2)


def validate(skill_dir: Path) -> list[str]:
    errors: list[str] = []
    md = skill_dir / "SKILL.md"
    if not md.is_file():
        return [f"{skill_dir}: missing SKILL.md"]
    parsed = parse_frontmatter(md.read_text(encoding="utf-8"))
    if parsed is None:
        return [f"{md}: missing YAML frontmatter (--- ... ---)"]
    front, body = parsed
    name = str(front.get("name", ""))
    desc = str(front.get("description", ""))
    if not (1 <= len(name) <= 64) or not NAME_RE.match(name):
        errors.append(f"{md}: invalid name {name!r}")
    if name != skill_dir.name:
        errors.append(f"{md}: name {name!r} must equal directory name {skill_dir.name!r}")
    if not (1 <= len(desc) <= 1024):
        errors.append(f"{md}: description must be 1-1024 characters (got {len(desc)})")
    if body.count("\n") > 500:
        errors.append(f"{md}: body has more than 500 lines; move detail into references/")
    meta = front.get("metadata")
    if meta is not None and not isinstance(meta, dict):
        errors.append(f"{md}: metadata must be a mapping")
    compat = front.get("compatibility")
    if compat and len(str(compat)) > 500:
        errors.append(f"{md}: compatibility exceeds 500 characters")
    refs = skill_dir / "references"
    if refs.exists():
        for f in refs.iterdir():
            if f.is_file() and f.suffix != ".md":
                errors.append(f"{f}: references/ should contain Markdown files only")
    return errors


def main() -> int:
    root = Path(sys.argv[1] if len(sys.argv) > 1 else "skills")
    if not root.is_dir():
        print(f"skills directory not found: {root}", file=sys.stderr)
        return 1
    dirs = sorted(p for p in root.iterdir() if p.is_dir() and not p.name.startswith("."))
    errors = [e for d in dirs for e in validate(d)]
    for e in errors:
        print(f"ERROR {e}", file=sys.stderr)
    if not dirs:
        print(f"no skills found under {root}", file=sys.stderr)
        return 1
    print(f"validated {len(dirs)} skill(s): {', '.join(d.name for d in dirs)}" + (" — FAILED" if errors else " — OK"))
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
