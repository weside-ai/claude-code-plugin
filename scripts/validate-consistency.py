#!/usr/bin/env python3
"""Cross-file consistency checks for the plugin's prose layer.

Guards the error classes the 2026-07 consolidation removed, so they cannot
silently return:

1. STORY_PHASES mirror  — every phase name in orchestration.py appears in
   references/integration-pipeline.md, and every `story checkpoint <ticket> <phase>`
   literal in
   markdown names a real phase.
2. EPIC_STATES mirror  — every state in orchestration.py's ladder appears in
   orchestrate/SKILL.md's state table.
3. Command/skill collision — no we/commands/<name>.md may share a name with a
   we/skills/<name>/ directory (documented dispatch-loop anti-pattern).
4. Dead references — every `references/<file>.md` mention, `/we:<name>`
   mention, and `subagent_type="..."` value in we/**/*.md must resolve to an
   existing file / skill / command / agent.
5. userConfig readers — every option declared in plugin.json userConfig must
   be referenced somewhere outside plugin.json.
6. Listing budget — `name` + `description` of every skill, agent and command sit in
   every session's context before the user has typed anything. The sum is capped.

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

    pipeline = (WE / "references" / "integration-pipeline.md").read_text()
    for phase in phases:
        if phase not in pipeline:
            fail(
                f"STORY_PHASES mirror: phase '{phase}' from orchestration.py "
                "does not appear in we/references/integration-pipeline.md"
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


def check_epic_states() -> None:
    """Every rung of EPIC_STATES must appear in orchestrate's state table.

    Same class as the STORY_PHASES mirror: a state added to the executed model
    and not to the prose is a state the Lead never learns to read, and the table
    then quietly documents a smaller ladder than the CLI returns.
    """
    orch = (WE / "scripts" / "orchestration.py").read_text()
    match = re.search(r"EPIC_STATES = \((.*?)\)", orch, re.DOTALL)
    if not match:
        fail("orchestration.py: EPIC_STATES tuple not found")
        return
    states = re.findall(r'"([a-z_]+)"', match.group(1))

    skill = (WE / "skills" / "orchestrate" / "SKILL.md").read_text()
    for state in states:
        if f"`{state}`" not in skill:
            fail(
                f"EPIC_STATES mirror: state '{state}' from orchestration.py "
                "does not appear in we/skills/orchestrate/SKILL.md"
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


def check_listing_budget() -> None:
    """The always-on cost of this plugin: `name` + `description` per entry, summed.

    This text is loaded in every session of every repo that installs the plugin, before
    anything is asked of it — so it is a budget, and a budget without a gate drifts. It
    was 12,188 chars over 46 entries before the 6.0.0 cut and is the reason eight uncalled
    skills were removed. To raise the cap, change the number here in a PR that says why.
    """
    budget = 6_000
    total, entries = 0, 0
    for pattern in ("skills/*/SKILL.md", "agents/*.md", "commands/*.md"):
        for path in sorted(WE.glob(pattern)):
            text = path.read_text(encoding="utf-8")
            found = re.match(r"\A---\r?\n(.*?)\r?\n---\r?\n", text, re.DOTALL)
            if not found:
                fail(
                    f"{path.relative_to(REPO)}: no YAML frontmatter — it carries no listing entry"
                )
                continue
            fm = found.group(1)
            name = re.search(r"^name:\s*(.*)$", fm, re.MULTILINE)
            desc = re.search(
                r"^description:\s*([\s\S]*?)(?=^[A-Za-z_][A-Za-z0-9_-]*\s*:|\Z)", fm, re.MULTILINE
            )
            if desc is None:
                fail(f"{path.relative_to(REPO)}: no description — it would be unlistable")
                continue
            total += len((name.group(1) if name else "") + " ".join(desc.group(1).split()))
            entries += 1
    if total > budget:
        fail(
            f"listing budget: {total} chars over {entries} entries, cap {budget}. "
            "This text loads in every session — cut a description or drop an entry."
        )


def main() -> int:
    check_story_phases()
    check_epic_states()
    check_command_skill_collision()
    check_dead_references()
    check_userconfig_readers()
    check_listing_budget()

    if errors:
        print(f"FAILED: {len(errors)} consistency finding(s):\n")
        for e in errors:
            print(f"  - {e}")
        return 1
    print("PASSED: All consistency checks OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
