#!/usr/bin/env python3
"""Cross-file consistency checks for the plugin's prose layer.

Guards the error classes the 2026-07 consolidation removed, so they cannot
silently return:

1. STORY_PHASES mirror  — every phase name in orchestration.py appears in
   build/SKILL.md, and every `story checkpoint <ticket> <phase>` literal in
   markdown names a real phase.
2. Command/skill collision — no we/commands/<name>.md may share a name with a
   we/skills/<name>/ directory (documented dispatch-loop anti-pattern).
3. Dead references — every `references/<file>.md` mention, `/we:<name>`
   mention, and `subagent_type="..."` value in we/**/*.md must resolve to an
   existing file / skill / command / agent.
4. userConfig readers — every option declared in plugin.json userConfig must
   be referenced somewhere outside plugin.json.

Stdlib only. Exit 1 on any finding.

Usage:
    python3 scripts/validate-consistency.py
"""

import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
WE = REPO / "we"

# subagent_type values that are Claude Code builtins, not plugin agents
BUILTIN_AGENTS = {"general-purpose", "Explore", "Plan", "claude"}

errors: list[str] = []


def fail(msg: str) -> None:
    errors.append(msg)


def md_files() -> list[Path]:
    return sorted(WE.rglob("*.md"))


def check_story_phases() -> None:
    orch = (WE / "scripts" / "orchestration.py").read_text()
    match = re.search(r"STORY_PHASES = \[(.*?)\]", orch, re.DOTALL)
    if not match:
        fail("orchestration.py: STORY_PHASES list not found")
        return
    phases = re.findall(r'"([a-z_]+)"', match.group(1))

    build = (WE / "skills" / "build" / "SKILL.md").read_text()
    for phase in phases:
        if phase not in build:
            fail(
                f"STORY_PHASES mirror: phase '{phase}' from orchestration.py "
                "does not appear in we/skills/build/SKILL.md"
            )

    # Any checkpoint literal used in markdown must be a real phase
    for path in md_files():
        text = path.read_text()
        for m in re.finditer(r"story checkpoint\s+\S+\s+([a-z_]+)", text):
            if m.group(1) not in phases:
                fail(
                    f"{path.relative_to(REPO)}: checkpoint '{m.group(1)}' "
                    "is not in orchestration.py STORY_PHASES"
                )


def check_command_skill_collision() -> None:
    commands = {p.stem for p in (WE / "commands").glob("*.md")}
    skills = {p.name for p in (WE / "skills").iterdir() if p.is_dir()}
    for name in sorted(commands & skills):
        fail(
            f"'{name}' exists as BOTH we/commands/{name}.md and "
            f"we/skills/{name}/ — dispatch-loop anti-pattern (keep one)"
        )


def check_dead_references() -> None:
    shared_refs = {p.name for p in (WE / "references").glob("*.md")}
    skills = {p.name for p in (WE / "skills").iterdir() if p.is_dir()}
    commands = {p.stem for p in (WE / "commands").glob("*.md")}
    agents = {p.stem for p in (WE / "agents").glob("*.md")}

    for path in md_files():
        text = path.read_text()
        rel = path.relative_to(REPO)

        # references/<file>.md mentions — resolve against we/references/, a
        # references/ dir next to the mentioning file, or (when the mentioning
        # file itself lives in a references/ dir) a sibling file
        for m in re.finditer(r"references/([a-z0-9-]+\.md)", text):
            name = m.group(1)
            candidates = [path.parent / "references" / name, path.parent / name]
            if name not in shared_refs and not any(c.exists() for c in candidates):
                fail(f"{rel}: reference 'references/{name}' does not exist")

        # /we:<name> mentions must be a skill or command
        for m in re.finditer(r"/we:([a-z][a-z0-9-]*)", text):
            name = m.group(1)
            if name not in skills and name not in commands:
                fail(f"{rel}: '/we:{name}' matches no skill or command")

        # subagent_type values must exist (plugin agents or builtins)
        for m in re.finditer(r'subagent_type="([^"]+)"', text):
            name = m.group(1).removeprefix("we:")
            if name not in agents and m.group(1) not in BUILTIN_AGENTS:
                fail(f"{rel}: subagent_type '{m.group(1)}' matches no agent")


def check_userconfig_readers() -> None:
    manifest = WE / ".claude-plugin" / "plugin.json"
    options = json.loads(manifest.read_text()).get("userConfig", {})
    corpus = ""
    for path in list(REPO.rglob("*.md")) + list(REPO.rglob("*.py")) + list(REPO.rglob("*.json")):
        if path == manifest or "__pycache__" in path.parts or ".git" in path.parts:
            continue
        try:
            corpus += path.read_text()
        except (UnicodeDecodeError, OSError):
            continue
    for key in options:
        if key not in corpus:
            fail(
                f"plugin.json userConfig option '{key}' is read by no file — "
                "wire it up or remove it"
            )


def main() -> int:
    check_story_phases()
    check_command_skill_collision()
    check_dead_references()
    check_userconfig_readers()

    if errors:
        print(f"FAILED: {len(errors)} consistency finding(s):\n")
        for e in errors:
            print(f"  - {e}")
        return 1
    print("PASSED: All consistency checks OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
