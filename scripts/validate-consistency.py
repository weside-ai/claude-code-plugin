#!/usr/bin/env python3
"""Cross-file consistency checks for the plugin's prose layer.

Guards the error classes the 2026-07 consolidation removed, so they cannot
silently return:

3. Command/skill collision — no we/commands/<name>.md may share a name with a
   we/skills/<name>/ directory (documented dispatch-loop anti-pattern).
4. Dead references — every `references/<file>.md` mention, `/we:<name>` or bare
   `we:<name>` mention, and `subagent_type="..."` value must resolve to an existing
   file / skill / command / agent (a bare `we:<name>` to a skill or an agent). Files:
   we/**/*.md, the code files under we/ (`*.py`, `*.ts`, `*.tsx`, `*.js`, `*.json`),
   README.md, docs/*.md (not docs/plans/) and every tour page (tour/**/*.html); a file that is not
   UTF-8 is a finding, not a crash.
5. userConfig readers — every option declared in plugin.json userConfig must
   be referenced somewhere outside plugin.json.
6. Listing budget — `name` + `description` of every skill, agent and command sit in
   every session's context before the user has typed anything. The sum is capped.
7. Indiscretion guard — no credential, personal identifier, or internal weside
   detail in any tracked file of this public repo (a hardcoded password once
   shipped here and had to be rotated).
8. Config schema — every `agents.<key>` a hook or script reads appears in the
   `.weside/config.json` schema block of skills/setup/SKILL.md § 3, and the
   worker-launch placeholders in we/scripts/worker_launch.py are exactly the ones
   references/worker-dispatch.md § Worker launch backend lists.
9. Lens skill — skills/lens/SKILL.md starts the panel through lens_verdict.py and
   dispatches in one message; every default lens in crew.py ships its agent file.
10. Retired — no path in RETIRED_PATHS exists, and no tracked file outside
   docs/plans/ (and RETIRED_ALLOWLIST) names a term of RETIRED_TERMS: the verbs,
   references and council shells the cut to the crew process L0 removed. A
   successor is named instead (master, plan-story, epic-plan, council-member).
11. Install resolver — no file under we/ resolves the plugin by the newest folder of the
   cache (`plugins/cache/weside-ai/we/*`), and every file of RESOLVER_FILES carries the one
   resolver RESOLVER verbatim (a copy in a Markdown list or YAML block indented by 3 or 8 spaces), two crews, AC7.

12. Layout — the `## Layout` block of AGENTS.md names every hook, plugin script, agent,
   process template and repo check file (tests aside).
13. Plugin-root paths — every `${CLAUDE_PLUGIN_ROOT}/<path>` in hooks.json and in a shipped
   file under we/ exists (patterns and tests skipped).
14. Carry ops — every op `ticket_adapter.py` hands a session to carry (its `VALUE_FIELD` keys)
   is shown as `"op": "<name>"` in references/ticketing.md or docs/board.md, so the session
   knows how to carry it with its ticketing tool.
15. Setup humans — the example crew file in we/skills/setup/references/humans.md § Example passes
   `crew.py validate --strict`, shows every `humans` field of crew.py's HUMAN_KEYS (each also named
   in that file's table), and sets `board.jql_scope` wherever it sets `board.signals`.

Stdlib only. Exit 1 on any finding.

Usage:
    python3 scripts/validate-consistency.py
    python3 scripts/validate-consistency.py --root <tree> --check retired --check dead-references
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
WE = REPO / "we"

# Check 10: what the cut to the crew process L0 removed. A tracked file names the successor.
RETIRED_PATHS = (
    "we/skills/saga",
    "we/skills/vision",
    "we/skills/meet",
    "we/skills/story",
    "we/skills/handoff",
    "we/skills/orchestrate",
    "we/skills/refine",
    "we/references/working-mode.md",
    "we/references/apo-hierarchy.md",
    "we/agents/council-architect.md",
    "we/agents/council-legal.md",
    "we/agents/council-marketing.md",
    "we/agents/council-orchestrator.md",
    "we/agents/council-product-owner.md",
    "we/agents/council-sales.md",
    "we/agents/council-scrum-master.md",
    "we/agents/council-security.md",
    "we/agents/council-ux-researcher.md",
    "we/scripts/test_council_shells.py",
)
RETIRED_VERBS = ("orchestrate", "refine", "saga", "vision", "meet", "story", "handoff")
RETIRED_SHELLS = (
    "architect",
    "legal",
    "marketing",
    "orchestrator",
    "product-owner",
    "sales",
    "scrum-master",
    "security",
    "ux-researcher",
)
RETIRED_TERMS = (
    *(f"/we:{verb}" for verb in RETIRED_VERBS),
    *(f"we:{verb}" for verb in RETIRED_VERBS),
    "working-mode.md",
    "apo-hierarchy.md",
    *(f"council-{role}" for role in RETIRED_SHELLS),
)
# Files that name the retired terms on purpose: this checker and the tests that pin it.
RETIRED_ALLOWLIST = {
    "scripts/validate-consistency.py",
    "scripts/test_validate_consistency.py",
    "scripts/test_l0_lines.py",
}
CODE_SUFFIXES = (".py", ".ts", ".tsx", ".js", ".json")
# Bare `we:<token>` that names no skill or agent on purpose: the role-skill stub marker
# (`<!-- we:stub`), and `we:lens-<key>`, the per-repo lens agents a crew file names.
BARE_NOT_A_NAME = re.compile(r"stub|lens-[a-z0-9-]+")


def _is_test_file(path: Path) -> bool:
    """A test builds fixture trees whose `references/` paths exist only in its tmp dir."""
    return path.name.startswith("test_") or ".test." in path.name


# subagent_type values that are Claude Code builtins, not plugin agents
BUILTIN_AGENTS = {"general-purpose", "Explore", "Plan", "claude"}

errors: list[str] = []


def fail(msg: str) -> None:
    errors.append(msg)


def check_command_skill_collision() -> None:
    commands = {p.stem for p in (WE / "commands").glob("*.md")}
    skills = {p.name for p in (WE / "skills").iterdir() if p.is_dir()}
    for name in sorted(commands & skills):
        fail(
            f"'{name}' exists as BOTH we/commands/{name}.md and "
            f"we/skills/{name}/ — dispatch-loop anti-pattern (keep one)"
        )


def mention_files(root: Path) -> list[Path]:
    """The files check 4 reads: we/**/*.md and the code files under we/, the repo README,
    docs/*.md (docs/plans/ is history) and every tour page."""
    we = root / "we"
    files = [
        p
        for p in we.rglob("*")
        if p.is_file()
        and (p.suffix == ".md" or p.suffix in CODE_SUFFIXES)
        and "__pycache__" not in p.parts
        and "node_modules" not in p.parts
    ]
    files += [p for p in (root / "README.md",) if p.is_file()]
    files += sorted((root / "tour").rglob("*.html"))
    files += sorted((root / "docs").glob("*.md"))
    return sorted(set(files))


def check_bare_mentions(rel: Path, text: str, names: set[str]) -> None:
    """A bare `we:<name>` (a Skill call, a flow button, an agent type) must be a skill or an
    agent; `we:dev-*` and `plugin:we:<server>` are a prefix and an MCP server."""
    for m in re.finditer(r"(?<![\w/:-])we:([a-z][a-z0-9-]*)", text):
        name = m.group(1)
        if name.endswith("-") or BARE_NOT_A_NAME.fullmatch(name) or name in names:
            continue
        line = text.count("\n", 0, m.start()) + 1
        fail(f"{rel}:{line}: 'we:{name}' matches no skill or agent")


def check_dead_references(root: Path = REPO) -> None:
    we = root / "we"
    shared_refs = {p.name for p in (we / "references").glob("*.md")}
    skills = {p.name for p in (we / "skills").iterdir() if p.is_dir()}
    commands = {p.stem for p in (we / "commands").glob("*.md")}
    agents = {p.stem for p in (we / "agents").glob("*.md")}

    for path in mention_files(root):
        rel = path.relative_to(root)
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            fail(f"{rel}: not UTF-8 — the mention check cannot read it")
            continue

        # references/<file>.md mentions — resolve against we/references/, a
        # references/ dir next to the mentioning file, or (when the mentioning
        # file itself lives in a references/ dir) a sibling file
        ref_mentions = (
            []
            if _is_test_file(path)
            else re.finditer(r"(?:skills/([a-z0-9<>-]+)/)?references/([a-z0-9-]+\.md)", text)
        )
        for m in ref_mentions:
            skill, name = m.group(1), m.group(2)
            if skill:  # a skill-local reference; `<verb>` means "any skill"
                owners = (
                    sorted(we.glob(f"skills/*/references/{name}"))
                    if "<" in skill
                    else [we / "skills" / skill / "references" / name]
                )
                if not any(o.exists() for o in owners):
                    fail(f"{rel}: reference 'skills/{skill}/references/{name}' does not exist")
                continue
            candidates = [path.parent / "references" / name, path.parent / name]
            if name not in shared_refs and not any(c.exists() for c in candidates):
                fail(f"{rel}: reference 'references/{name}' does not exist")

        # /we:<name> mentions must be a skill or command
        for m in re.finditer(r"/we:([a-z][a-z0-9-]*)", text):
            name = m.group(1)
            if name not in skills and name not in commands:
                line = text.count("\n", 0, m.start()) + 1
                fail(f"{rel}:{line}: '/we:{name}' matches no skill or command")

        check_bare_mentions(rel, text, skills | agents)

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
    6,000 -> 6,400 (7.57.0): the lens panel adds one skill and three lens agents (~390 chars);
    a lens agent must be listed to be spawned by `subagent_type`.
    """
    budget = 6_400
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


def check_lens_skill() -> None:
    """The lens skill starts its panel through lens_verdict.py and dispatches every entry in one
    message (parallel fresh agents); each agent a crew default names ships as a file."""
    skill = WE / "skills" / "lens" / "SKILL.md"
    if not skill.is_file():
        fail("skills/lens/SKILL.md is missing")
        return
    text = skill.read_text(encoding="utf-8")
    for needle in ("lens_verdict.py", "LV plan ready", "LV plan t2", "in one message"):
        if needle not in text:
            fail(f"skills/lens/SKILL.md does not name {needle!r}")
    crew_src = (WE / "scripts" / "crew.py").read_text(encoding="utf-8")
    block = re.search(r'^    "lenses": \{\n(.*?)^    \},', crew_src, re.S | re.M)
    keys = re.findall(r'_lens\("(\w+)"', block.group(1)) if block else []
    if not keys:
        fail("crew.py DEFAULTS names no lens")
    for key in keys:
        if not (WE / "agents" / f"lens-{key}.md").is_file():
            fail(f"crew.py default lens {key!r} ships no agents/lens-{key}.md")
        if f"we:lens-{key}" not in text:
            fail(f"skills/lens/SKILL.md does not name the shipped agent we:lens-{key}")


def check_agents_config() -> None:
    setup = (WE / "skills" / "setup" / "SKILL.md").read_text()
    block = re.search(r"## 3\. `\.weside/config\.json`.*?```json\n(.*?)```", setup, re.S)
    try:
        schema = json.loads(block.group(1)) if block else {}
    except json.JSONDecodeError as exc:
        fail(f"skills/setup/SKILL.md § 3: config block is no JSON ({exc})")
        return
    documented = set(schema.get("agents", {}))
    readers = {}
    for path in sorted((WE / "hooks").glob("*.py")) + sorted((WE / "scripts").glob("*.py")):
        if path.name.startswith("test_"):
            continue
        for key in re.findall(r"agents\.get\(\s*[\"'](\w+)[\"']", path.read_text()):
            readers.setdefault(key, path.relative_to(REPO))
    for key, rel in sorted(readers.items()):
        if key not in documented:
            fail(f"{rel} reads agents.{key}, which skills/setup/SKILL.md § 3 does not list")

    source = (WE / "scripts" / "worker_launch.py").read_text()
    known = re.search(r"^PLACEHOLDERS = \(([^)]*)\)", source, re.M)
    placeholders = set(re.findall(r"\"(\w+)\"", known.group(1))) if known else set()
    dispatch = (WE / "references" / "worker-dispatch.md").read_text()
    section = re.search(r"^## Worker launch backend\n(.*?)(?=^## |\Z)", dispatch, re.S | re.M)
    if not section:
        fail("references/worker-dispatch.md has no § Worker launch backend")
        return
    listed = set(re.findall(r"`\{(\w+)\}`", section.group(1)))
    if not placeholders or listed != placeholders:
        fail(
            "worker-dispatch.md § Worker launch backend lists placeholders "
            f"{sorted(listed)}, worker_launch.py knows {sorted(placeholders)}"
        )


def check_installer_verdicts() -> None:
    """Each installer prints a `VERDICT:` line; /we:setup § 5 branches on its wording.

    Two files, one contract, and no compiler between them: rename a verdict in a
    script and the setup branching stops matching without any test going red.
    """
    skill = WE / "skills" / "setup" / "SKILL.md"
    text = skill.read_text()
    for name in ("install_statusline.py", "install_launcher.py"):
        script = WE / "scripts" / name
        if not script.exists():
            fail(f"we/scripts/{name} missing — /we:setup § 5 calls it")
            continue
        verdicts = set(
            re.findall(r'^VERDICT_[A-Z]+ = "([^"]+)"', script.read_text(), re.MULTILINE)
        )
        if not verdicts:
            fail(f"{name} defines no VERDICT_* constants — /we:setup has nothing to branch on")
            continue
        if f"scripts/{name}" not in text:
            fail(f"we/skills/setup/SKILL.md does not call scripts/{name}")
        for verdict in sorted(verdicts):
            if verdict not in text:
                fail(
                    f"{name} prints VERDICT '{verdict}' which "
                    "we/skills/setup/SKILL.md does not branch on"
                )


def check_instruction_hook_files() -> None:
    """/we:setup installs the gate's pre-commit hook (owned by references/optimization-store.md
    § Gate hook) into user repos; this repo runs the same
    hook. Their `files:` filters are one contract: a file that triggers the gate here must
    trigger it there."""
    pattern = re.compile(r"id: instruction-budget\n(?:.*\n){0,6}?\s*files: (.+)")
    ours = pattern.search((REPO / ".pre-commit-config.yaml").read_text())
    theirs = pattern.search((WE / "references" / "optimization-store.md").read_text())
    if not ours or not theirs:
        fail(
            "instruction-budget hook: `files:` not found in .pre-commit-config.yaml or "
            "optimization-store.md § Gate hook"
        )
    elif ours.group(1).strip() != theirs.group(1).strip():
        fail(
            "instruction-budget hook: `files:` differs between .pre-commit-config.yaml and "
            "we/references/optimization-store.md — keep them identical"
        )


# --- Indiscretion guard -------------------------------------------------------
# One credential leak (a password hardcoded as an os.environ.get default) reached
# this public repo and had to be rotated. These patterns are the classes that must
# never land in a public artefact again. Each entry: (label, regex).
# Deliberately narrow: `/home/user/...` fixtures and api.weside.ai (the public
# product endpoint) are legitimate and must not trip the check.
INDISCRETION_PATTERNS: list[tuple[str, str]] = [
    (
        "hardcoded credential default",
        r"""environ(?:\.get)?\(\s*["'][A-Z_]*(?:PASSWORD|SECRET|TOKEN|API_?KEY)["']\s*,\s*["'][^"']+["']""",
    ),
    (
        "credential literal",
        r"""["'](?:password|passwd|secret|api_?key)["']\s*[:=]\s*["'][^"'{$][^"']{5,}["']""",
    ),
    ("JWT / bearer token", r"eyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}"),
    (
        "provider API key",
        r"\b(?:sk-[A-Za-z0-9]{20,}|ghp_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,}|xox[baprs]-[A-Za-z0-9-]{10,}|AKIA[0-9A-Z]{16})\b",
    ),
    ("personal email address", r"[A-Za-z0-9._%+-]+@(?:gmx\.(?:net|de)|colenet\.de|gmail\.com)"),
    ("internal test account", r"(?:claude-test|nox-acceptance[a-z-]*)@weside\.ai"),
    # `/home/user/`, `/home/dev/` etc. are the docs' generic placeholders; a real
    # login name in a path is what leaks who and where.
    ("developer home path", r"/home/(?!user|dev|me|you|alice|bob|<)[a-z][a-z0-9_-]*/"),
    ("internal host or IP", r"(?:workspace\.weside\.ai|\b46\.224\.112\.\d{1,3}\b)"),
    ("Supabase project ref", r"\b(?:pqykrwpmhjqjhpsnjxbd|yauruvmadvvdravrlixu)\b"),
    ("internal k8s namespace", r"\bweside-(?:production|staging)\b"),
    # Ticket keys in shipped examples use the neutral `PROJ-` placeholder; `WA-`
    # is weside's real Jira prefix and names real internal work.
    ("internal ticket prefix", r"\bWA-(?:\d+|\{|…)"),
    # The same key glued into a session or branch name (`wa1234-build`).
    ("internal ticket key in a name", r"(?i)\bwa\d{3,}"),
    # Private sibling repos of this workspace. `weside-cli` and `weside-mcp` are
    # public product names and stay allowed; examples name a neutral repo instead.
    ("internal repo name", r"\bweside-(?:core|infrastructure)\b|leading-companions"),
]

# Files that document the patterns themselves (the ban list, and this checker).
INDISCRETION_ALLOWLIST = {
    "AGENTS.md",
    "scripts/validate-consistency.py",
    ".claude/rules/plugin-authoring.md",
}


def _tracked_text_files() -> list[Path]:
    """Every git-tracked file, minus binaries and the allowlist."""
    out = subprocess.run(
        ["git", "-C", str(REPO), "ls-files", "-z"],
        capture_output=True,
        text=True,
        check=False,
    ).stdout
    files = []
    for rel in out.split("\0"):
        if not rel or rel in INDISCRETION_ALLOWLIST:
            continue
        path = REPO / rel
        if not path.is_file():
            continue
        try:
            path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        files.append(path)
    return files


def check_no_indiscretions() -> None:
    """No credential, personal identifier, or internal weside detail in a public file.

    This repo is public and published as a Claude Code plugin. A leak here is not
    a lint finding — it is a rotation.
    """
    compiled = [(label, re.compile(pat)) for label, pat in INDISCRETION_PATTERNS]
    for path in _tracked_text_files():
        rel = path.relative_to(REPO).as_posix()
        lines = path.read_text(encoding="utf-8").splitlines()
        for lineno, line in enumerate(lines, 1):
            for label, rx in compiled:
                if rx.search(line):
                    fail(f"{rel}:{lineno} — {label} in a public file")


def _all_files(root: Path) -> list[str]:
    """Tracked files of ``root``, or every file when ``root`` is no git checkout."""
    done = subprocess.run(
        ["git", "-C", str(root), "ls-files", "-z"], capture_output=True, text=True, check=False
    )
    if done.returncode == 0 and (root / ".git").exists():
        return [rel for rel in done.stdout.split("\0") if rel]
    return sorted(p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file())


def check_retired(root: Path = REPO) -> None:
    """No retired path exists, no tracked file outside docs/plans/ names a retired term."""
    for rel in RETIRED_PATHS:
        if (root / rel).exists():
            fail(f"{rel}: retired path still present — delete it, its successor took over")
    pattern = re.compile(
        r"(?<![\w-])(?:" + "|".join(re.escape(term) for term in RETIRED_TERMS) + r")(?![\w-])"
    )
    for rel in _all_files(root):
        if rel.startswith("docs/plans/") or rel in RETIRED_ALLOWLIST:
            continue
        path = root / rel
        if not path.is_file():
            continue
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except (UnicodeDecodeError, OSError):
            continue
        for lineno, line in enumerate(lines, 1):
            for m in pattern.finditer(line):
                fail(f"{rel}:{lineno}: retired name '{m.group(0)}' — name its successor")


ORCHESTRATE_TEMPLATE = "we/templates/orchestrate.md"
_ORCHESTRATE_REF = re.compile(r"orchestrate\.md`?\s*§\s*\*?([A-Z][a-z]+(?:[ -][a-z-]+)*)")


def check_orchestrate_template(root: Path = REPO) -> None:
    """Every `.weside/orchestrate.md` § section a plugin file names is a heading of the template
    `/we:setup` copies, so a fresh crew repo has a place for each fact a skill reads."""
    template = root / ORCHESTRATE_TEMPLATE
    if not template.is_file():
        fail(f"{ORCHESTRATE_TEMPLATE}: missing — /we:setup copies it into a crew repo")
        return
    headings = {
        line.lstrip("#").strip().lower()
        for line in template.read_text(encoding="utf-8").splitlines()
        if line.startswith("## ")
    }
    for path in sorted((root / "we").rglob("*.md")):
        rel = path.relative_to(root).as_posix()
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            for m in _ORCHESTRATE_REF.finditer(line):
                if m.group(1).strip().lower() not in headings:
                    fail(
                        f"{rel}:{lineno}: names `.weside/orchestrate.md` § {m.group(1).strip()}, "
                        f"which {ORCHESTRATE_TEMPLATE} has no heading for"
                    )


# The skills run in every repo that installs the plugin: a decision stamp names its role, not a
# person, and a command the plugin does not ship stays out.
_NOT_NEUTRAL = re.compile(r"\bFoxy\b|`a release\b")


def check_neutral_skills(root: Path = REPO) -> None:
    """No skill names the plugin author's own owner or a command only their repo has."""
    for path in sorted((root / "we" / "skills").rglob("*.md")):
        rel = path.relative_to(root).as_posix()
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            m = _NOT_NEUTRAL.search(line)
            if m:
                fail(
                    f"{rel}:{lineno}: '{m.group(0)}' is one team's history — write `owner` or drop it"
                )


ROOT_CHECKS = {
    "dead-references": check_dead_references,
    "retired": check_retired,
    "orchestrate-template": check_orchestrate_template,
    "neutral-skills": check_neutral_skills,
}


# --- Check 11: the install resolver (two crews, AC7) --------------------------------------------
# Where no ${CLAUDE_PLUGIN_ROOT} exists, the plugin is found through installed_plugins.json: the
# project-scope `we` entry for the directory or its nearest ancestor, else the user-scope one.
RESOLVER = r"""python3 -c 'if True:
    import json, os, sys
    f = os.path.join(os.environ.get("CLAUDE_CONFIG_DIR") or os.path.expanduser("~/.claude"), "plugins", "installed_plugins.json")
    want, run = sys.argv[1], "--exec" in sys.argv[2:3]
    try:
        rows = [e for k, v in json.load(open(f))["plugins"].items() if k.split("@")[0] == "we" for e in v]
    except Exception:
        sys.stderr.write("we plugin: " + f + " not readable; the plugin is not resolved\n")
        sys.exit(0 if run else 1)
    here = os.path.realpath(os.getcwd())
    def holds(e):
        p = os.path.realpath(e.get("projectPath") or "/nonexistent")
        return e.get("scope") in ("project", "local") and (here == p or here.startswith(p.rstrip("/") + "/"))
    near = sorted((e for e in rows if holds(e)), key=lambda e: len(os.path.realpath(e["projectPath"])))
    pick = (near or [e for e in rows if e.get("scope") == "user"] or [None])[-1]
    if pick is None:
        sys.stderr.write("we plugin: no we install in " + f + "\n")
        sys.exit(0 if run else 1)
    path = os.path.join(pick["installPath"], want)
    if run:
        os.execvp(sys.executable, [sys.executable, path] + sys.argv[3:])
    print(path)
'"""
RESOLVER_FILES = (
    "we/scripts/we-worker",
    "we/scripts/wclaude",
    "we/templates/agents-skill/SKILL.md",
    "we/references/optimization-store.md",
)
CACHE_GLOB = "plugins/cache/weside-ai/we/*"


def _dedent(text: str, n: int) -> str:
    pad = " " * n
    return "\n".join(line[n:] if line.startswith(pad) else line for line in text.splitlines())


def check_install_resolver(root: Path = REPO) -> None:
    for path in sorted((root / "we").rglob("*")):
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        if CACHE_GLOB in text:
            fail(
                f"{path.relative_to(root)}: resolves the plugin by the newest cache folder "
                f"({CACHE_GLOB}); use the install resolver (scripts/validate-consistency.py RESOLVER)"
            )
    for rel in RESOLVER_FILES:
        path = root / rel
        text = path.read_text(encoding="utf-8") if path.is_file() else ""
        if not any(RESOLVER in _dedent(text, n) for n in (0, 3, 8)):
            fail(f"{rel}: the install resolver differs from RESOLVER or is missing")


ROOT_CHECKS["install-resolver"] = check_install_resolver


# --- Check 12: AGENTS.md § Layout names every file it maps -------------------------------------
LAYOUT_GLOBS = ("we/hooks/*.py", "we/scripts/*", "we/agents/*.md", "we/process/*.md", "scripts/*")


def check_agents_layout(root: Path = REPO) -> None:
    """Every hook, plugin script, agent, process template and repo check file (tests aside) is
    named in the `## Layout` block of AGENTS.md, by file name or by stem."""
    agents = root / "AGENTS.md"
    if not agents.is_file():
        fail("AGENTS.md: missing, the layout check has nothing to read")
        return
    text = agents.read_text(encoding="utf-8")
    start = text.find("## Layout")
    end = text.find("\n## ", start + 1)
    layout = text[start : end if end != -1 else None] if start != -1 else ""
    if not layout:
        fail("AGENTS.md: no `## Layout` section")
        return
    for pattern in LAYOUT_GLOBS:
        for path in sorted(root.glob(pattern)):
            if not path.is_file() or _is_test_file(path) or path.name.startswith("."):
                continue
            if path.name not in layout and path.stem not in layout:
                fail(f"AGENTS.md § Layout: {path.relative_to(root).as_posix()} is not named")


ROOT_CHECKS["agents-layout"] = check_agents_layout


# --- Check 13: every path under the plugin root exists ------------------------------------------
_PLUGIN_ROOT_PATH = re.compile(r"\$\{?CLAUDE_PLUGIN_ROOT\}?/([A-Za-z0-9_./-]+)")


def check_plugin_root_paths(root: Path = REPO) -> None:
    """Every `${CLAUDE_PLUGIN_ROOT}/<path>` in hooks.json and in a shipped skill, reference,
    agent, role, process file or script names a file of the plugin (a path with `<`, `*` or `{`
    is a pattern and skipped; test files are fixtures). A renamed script otherwise breaks the
    hook or the skill only when it runs."""
    we = root / "we"
    files = [we / "hooks" / "hooks.json"] + [
        p
        for p in sorted(we.rglob("*"))
        if p.is_file()
        and p.suffix in (".md", ".sh", ".py", ".ts", ".tsx", ".json")
        and not _is_test_file(p)
    ]
    seen: set[Path] = set()
    for path in files:
        if path in seen or not path.is_file():
            continue
        seen.add(path)
        text = path.read_text(encoding="utf-8", errors="replace")
        for m in _PLUGIN_ROOT_PATH.finditer(text):
            rel = m.group(1).rstrip(".")
            end = m.end()
            if not rel or (end < len(text) and text[end] in "<*{"):
                continue
            if not (we / rel).exists():
                line = text.count("\n", 0, m.start()) + 1
                fail(
                    f"{path.relative_to(root)}:{line}: '${{CLAUDE_PLUGIN_ROOT}}/{rel}' does not exist"
                )


ROOT_CHECKS["plugin-root-paths"] = check_plugin_root_paths


# --- Check 14: every carry op is documented for the session that carries it -------------------
_VALUE_FIELD = re.compile(r"^VALUE_FIELD = \{([^}]*)\}", re.MULTILINE)


def check_carry_ops(root: Path = REPO) -> None:
    """Each key of `VALUE_FIELD` in we/scripts/ticket_adapter.py appears as `"op": "<key>"` in
    we/references/ticketing.md or we/docs/board.md."""
    adapter = root / "we" / "scripts" / "ticket_adapter.py"
    if not adapter.is_file():
        return
    m = _VALUE_FIELD.search(adapter.read_text(encoding="utf-8"))
    if m is None:
        fail(f"{adapter.relative_to(root)}: no `VALUE_FIELD = {{...}}` line to read the ops from")
        return
    docs = "".join(
        p.read_text(encoding="utf-8")
        for p in (root / "we" / "references" / "ticketing.md", root / "we" / "docs" / "board.md")
        if p.is_file()
    )
    for op in re.findall(r'"([a-z_]+)"\s*:', m.group(1)):
        if f'"op": "{op}"' not in docs:
            fail(
                f'carry op {op!r} (ticket_adapter.VALUE_FIELD) is not shown as "op": "{op}" in '
                "we/references/ticketing.md or we/docs/board.md"
            )


ROOT_CHECKS["carry-ops"] = check_carry_ops


# --- Check 15: /we:setup's humans example is a crew crew.py accepts ------------------------------
SETUP_HUMANS = Path("we/skills/setup/references/humans.md")
_HUMAN_KEYS = re.compile(r"^HUMAN_KEYS = \{([^}]*)\}", re.MULTILINE)


def check_setup_humans(root: Path = REPO) -> None:
    """The § Example block of the setup humans reference validates strict against the tree's
    crew.py and covers every field of its `HUMAN_KEYS`: a field crew.py adds or renames turns this
    red until setup asks for it."""
    ref, crew_py = root / SETUP_HUMANS, root / "we" / "scripts" / "crew.py"
    if not ref.is_file() or not crew_py.is_file():
        return
    text = ref.read_text(encoding="utf-8")
    m = re.search(r"^## Example\n.*?```json\n(.*?)```", text, re.S | re.M)
    if m is None:
        fail(f"{SETUP_HUMANS}: no ```json block under `## Example`")
        return
    try:
        crew = json.loads(m.group(1))
    except json.JSONDecodeError as exc:
        fail(f"{SETUP_HUMANS} § Example: no JSON ({exc})")
        return
    keys = _HUMAN_KEYS.search(crew_py.read_text(encoding="utf-8"))
    if keys is None:
        fail("we/scripts/crew.py: no `HUMAN_KEYS = {...}` to read the humans fields from")
        return
    shown = {
        k
        for entry in (crew.get("humans") or {}).values()
        if isinstance(entry, dict)
        for k in entry
    }
    for key in re.findall(r'"([a-z_]+)"\s*:', keys.group(1)):
        if key not in shown:
            fail(f"{SETUP_HUMANS} § Example: no human shows `{key}` (crew.py HUMAN_KEYS)")
        if f"`{key}`" not in text.split("## Example")[0]:
            fail(f"{SETUP_HUMANS}: `{key}` (crew.py HUMAN_KEYS) is not asked for above § Example")
    board = crew.get("board") or {}
    if board.get("signals") and not board.get("jql_scope"):
        fail(
            f"{SETUP_HUMANS} § Example: board.signals without board.jql_scope (board.py signals refuses)"
        )
    with tempfile.TemporaryDirectory() as tmp:
        (Path(tmp) / ".git").mkdir()
        (Path(tmp) / ".weside").mkdir()
        (Path(tmp) / ".weside" / "crew.json").write_text(m.group(1), encoding="utf-8")
        done = subprocess.run(
            [sys.executable, str(crew_py), "validate", "--strict", "--from", tmp],
            capture_output=True,
            text=True,
            check=False,
        )
    if done.returncode != 0:
        why = (done.stderr.strip().splitlines() or ["no output"])[-1]
        fail(f"{SETUP_HUMANS} § Example: crew.py validate --strict refuses it: {why}")


ROOT_CHECKS["setup-humans"] = check_setup_humans


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", type=Path, help="run the --check checks on this tree")
    parser.add_argument("--check", action="append", choices=sorted(ROOT_CHECKS), default=[])
    args = parser.parse_args(argv)
    if args.root is not None:
        for name in args.check or sorted(ROOT_CHECKS):
            ROOT_CHECKS[name](args.root.resolve())
    else:
        check_command_skill_collision()
        check_dead_references()
        check_userconfig_readers()
        check_listing_budget()
        check_instruction_hook_files()
        check_installer_verdicts()
        check_agents_config()
        check_lens_skill()
        check_no_indiscretions()
        check_retired()
        check_orchestrate_template()
        check_neutral_skills()
        check_install_resolver()
        check_agents_layout()
        check_plugin_root_paths()
        check_carry_ops()
        check_setup_humans()

    if errors:
        print(f"FAILED: {len(errors)} consistency finding(s):\n")
        for e in errors:
            print(f"  - {e}")
        return 1
    print("PASSED: All consistency checks OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
