"""Pins check 10 (retired) and the widened check 4 (dead mentions in code files) of
scripts/validate-consistency.py, on fixture trees and on this repo.

Every red case asserts the message, not only the exit code: a gate that fails for the wrong
reason passes its red arm and still lets the retired name back in.

Run with: python3 -m pytest -q scripts/test_validate_consistency.py
"""

from __future__ import annotations

import subprocess
import sys
from importlib import util
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SCRIPT = REPO / "scripts" / "validate-consistency.py"


def run(root: Path, *checks: str) -> subprocess.CompletedProcess:
    args = [sys.executable, str(SCRIPT), "--root", str(root)]
    for check in checks:
        args += ["--check", check]
    return subprocess.run(args, capture_output=True, text=True, check=False)


def tree(tmp_path: Path, files: dict[str, str | bytes]) -> Path:
    """A minimal plugin tree: one skill `master`, one agent `council-member`, plus ``files``."""
    root = tmp_path / "repo"
    base = {
        "we/skills/master/SKILL.md": "---\nname: master\n---\n",
        "we/agents/council-member.md": "---\nname: council-member\n---\n",
        "we/references/ticketing.md": "# Ticketing\n",
    }
    for rel, body in {**base, **files}.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(body, bytes):
            path.write_bytes(body)
        else:
            path.write_text(body, encoding="utf-8")
    return root


def test_retired_path_present_fails_naming_the_path(tmp_path):
    root = tree(tmp_path, {"we/skills/saga/SKILL.md": "---\nname: saga\n---\n"})
    done = run(root, "retired")
    assert done.returncode == 1, done.stdout
    assert "we/skills/saga: retired path still present" in done.stdout


def test_retired_term_in_a_tracked_file_fails_naming_file_and_line(tmp_path):
    root = tree(tmp_path, {"docs/workflow.md": "# Flow\n\nRun `/we:orchestrate <epic>`.\n"})
    done = run(root, "retired")
    assert done.returncode == 1, done.stdout
    assert "docs/workflow.md:3: retired name '/we:orchestrate'" in done.stdout


def test_every_retired_term_is_caught(tmp_path):
    terms = [
        "/we:refine",
        "we:saga",
        "/we:vision",
        "/we:meet",
        "/we:story",
        "/we:handoff",
        "working-mode.md",
        "apo-hierarchy.md",
        "council-architect",
        "council-ux-researcher",
    ]
    root = tree(tmp_path, {"we/notes.md": "\n".join(terms) + "\n"})
    done = run(root, "retired")
    assert done.returncode == 1
    for line, term in enumerate(terms, 1):
        assert f"we/notes.md:{line}: retired name '{term}'" in done.stdout, term


def test_successor_names_and_history_pass(tmp_path):
    """The successors share a prefix with a retired name and must not trip it; docs/plans/ is
    history and is not scanned."""
    root = tree(
        tmp_path,
        {
            "we/notes.md": "/we:master, /we:plan-story, council-member, epic-plan.md, "
            "a storyboard, we:master\n",
            "docs/plans/old-story.md": "Built by `/we:orchestrate` with `/we:refine`.\n",
        },
    )
    done = run(root, "retired")
    assert done.returncode == 0, done.stdout


def test_dead_mention_in_code_file(tmp_path):
    """A flow button that runs a retired skill is a bare `we:<name>` in a .tsx file."""
    body = "out.push(action('k-build', 'Build', 'we:orchestrate', key))\n"
    root = tree(tmp_path, {"we/hooks/flow/register.tsx": body})
    done = run(root, "dead-references")
    assert done.returncode == 1, done.stdout
    assert (
        "we/hooks/flow/register.tsx:1: 'we:orchestrate' matches no skill or agent" in done.stdout
    )


def test_bare_mentions_that_resolve_or_are_no_name_pass(tmp_path):
    body = (
        "skill('we:master'); agent('we:council-member'); prefix('we:dev-*');\n"
        "server('plugin:we:weside-mcp'); marker('<!-- we:stub'); lens('we:lens-architecture')\n"
    )
    root = tree(tmp_path, {"we/hooks/flow/register.tsx": body, "README.md": "Run `/we:master`.\n"})
    done = run(root, "dead-references")
    assert done.returncode == 0, done.stdout


def test_dead_slash_mention_in_the_readme_and_the_tour(tmp_path):
    root = tree(
        tmp_path,
        {"README.md": "Start with `/we:vision`.\n", "tour/index.html": "<p>/we:saga</p>\n"},
    )
    done = run(root, "dead-references")
    assert done.returncode == 1
    assert "README.md:1: '/we:vision' matches no skill or command" in done.stdout
    assert "tour/index.html:1: '/we:saga' matches no skill or command" in done.stdout


def test_a_non_utf8_tour_page_is_a_finding_not_a_crash(tmp_path):
    root = tree(tmp_path, {"tour/index.html": b"<p>caf\xe9</p>\n"})
    done = run(root, "dead-references")
    assert done.returncode == 1 and "Traceback" not in done.stderr, done.stderr
    assert "tour/index.html: not UTF-8" in done.stdout


def test_retired_paths():
    """This repo: no retired path, the two renamed skills under their new names, no alias."""
    spec = util.spec_from_file_location("validate_consistency", SCRIPT)
    module = util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert not [rel for rel in module.RETIRED_PATHS if (REPO / rel).exists()]
    for name in ("master", "plan-story"):
        text = (REPO / "we" / "skills" / name / "SKILL.md").read_text(encoding="utf-8")
        assert f"\nname: {name}\n" in text and f'"/we:{name}"' in text, name
    assert not (REPO / "we" / "skills" / "orchestrate").exists()
    assert not (REPO / "we" / "skills" / "refine").exists()


def test_retired_and_dead_references_pass_on_this_repo():
    done = run(REPO, "retired", "dead-references")
    assert done.returncode == 0, done.stdout
