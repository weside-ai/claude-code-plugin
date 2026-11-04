"""compact_on_start.py and epic_age_precompact.py: the board line, the questions, the epic block
for a master, the pin reload, the budget, and the stale-epic flag."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPTS = HERE.parent / "scripts"
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(SCRIPTS))

import compact_on_start as cos  # noqa: E402
import epic_state  # noqa: E402

GENERIC = SCRIPTS / "fixtures" / "crew-v2-generic.json"
TODAY = epic_state.today("Europe/Berlin").isoformat()
PR = {
    "number": 41,
    "title": "PROJ-8 the first story",
    "url": "https://example.invalid/pr/41",
    "repository": {"nameWithOwner": "acme/app"},
}


def plan(updates: list[str] | None) -> str:
    text = "---\nepic: proj\nticket: PROJ-7\nstatus: in-progress\n---\n\n# Epic\n\n## Scope\n\nx\n"
    if updates is not None:
        text += "\n## Updates Log\n\n" + "".join(f"- {u}\n" for u in updates)
    return text


def workspace(tmp_path: Path, updates: list[str] | None, board: dict | None = None) -> Path:
    root = tmp_path / "repo"
    (root / ".weside").mkdir(parents=True)
    (root / "docs" / "plans").mkdir(parents=True)
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    data = json.loads(GENERIC.read_text())
    data["board"] = {"file": str(tmp_path / "state" / "board.json")}
    (root / ".weside" / "crew.json").write_text(json.dumps(data))
    (root / "docs" / "plans" / "proj-epic.md").write_text(plan(updates))
    for key in ("PROJ-8", "PROJ-9"):
        story = f"---\nstory: {key}\nepic: PROJ-7\n---\n"
        (root / "docs" / "plans" / f"{key}-story.md").write_text(story)
    (root / "docs" / "plans" / "PROJ-99-story.md").write_text("---\nepic: PROJ-1\n---\n")
    (tmp_path / "state").mkdir()
    board = board or {
        "sessions": [{"name": "proj-7", "session_id": "sid", "now": "building PROJ-8"}],
        "owner_queue": [
            {
                "id": "Q1",
                "session": "proj-7",
                "key": "PROJ-8",
                "ask": "Ship it?",
                "recommendation": "yes",
            }
        ],
    }
    (tmp_path / "state" / "board.json").write_text(json.dumps(board))
    return root


class Runner:
    """Stub for git, gh and tmux; records every command."""

    def __init__(self, root: Path, gh_ok: bool = True) -> None:
        self.root, self.gh_ok, self.calls = root, gh_ok, []

    def __call__(self, cmd, **_kw):
        self.calls.append(cmd)
        out, rc = "", 0
        if cmd[:3] == ["git", "rev-parse", "--show-toplevel"]:
            out = str(self.root)
        elif cmd[:3] == ["git", "remote", "get-url"]:
            out = "git@github.com:acme/app.git\n"
        elif cmd[:3] == ["gh", "search", "prs"]:
            out, rc = (json.dumps([PR]), 0) if self.gh_ok else ("", 1)
        return subprocess.CompletedProcess(cmd, rc, out, "")


MASTER = {"WE_ROLE": "master"}
UPDATES = [
    "2026-01-03 — third",
    "2026-01-01 — first",
    "2026-01-04 — fourth, newest",
    "2026-01-02 — second",
]


def hook(root: Path, **extra) -> dict:
    return {"session_id": "sid", "source": "compact", "cwd": str(root), **extra}


def test_master_gets_board_line_questions_epic_state_and_memory_hint(tmp_path):
    root = workspace(tmp_path, UPDATES)
    runner = Runner(root)
    text, err = cos.render(hook(root), MASTER, runner)
    assert err is None
    assert text.startswith("Context restored after compaction:")
    assert "- now: building PROJ-8" in text
    assert "- Q1 PROJ-8 · Ship it? · Advice: yes" in text and "(waiting for Hal)" in text
    epic = root / "docs" / "plans" / "proj-epic.md"
    assert f"Your epic PROJ-7: {epic.resolve()} (status: in-progress)" in text
    log = text.split("Updates Log, last 3 by date:\n")[1].split("\nOpen PRs")[0]
    assert log.splitlines() == [
        "- 2026-01-02 — second",
        "- 2026-01-03 — third",
        "- 2026-01-04 — fourth, newest",
    ]
    assert "- acme/app#41 PROJ-8 the first story https://example.invalid/pr/41" in text
    assert text.endswith(cos.MEMORY)
    [gh] = [c for c in runner.calls if c[0] == "gh"]
    assert gh[-1].startswith('"PROJ-7" OR ')
    assert sorted(gh[-1].split(" OR ")) == ['"PROJ-7"', '"PROJ-8"', '"PROJ-9"']
    assert "--owner" in gh and gh[gh.index("--owner") + 1] == "acme"
    assert "Epic update first" not in text


def test_gh_failure_says_unknown(tmp_path):
    root = workspace(tmp_path, UPDATES)
    text, _ = cos.render(hook(root), MASTER, Runner(root, gh_ok=False))
    assert "Open PRs: unknown (gh failed)." in text


def test_a_non_master_gets_no_epic_block(tmp_path):
    root = workspace(tmp_path, UPDATES)
    text, _ = cos.render(hook(root), {}, Runner(root))
    assert "Your epic" not in text and "- now: building PROJ-8" in text


def test_an_unresolvable_epic_names_the_fix(tmp_path):
    board = {"sessions": [{"name": "helper", "session_id": "sid"}], "owner_queue": []}
    root = workspace(tmp_path, UPDATES, board)
    text, _ = cos.render(hook(root), MASTER, Runner(root))
    assert "epic plan not found: set `epic` on your board line" in text


def test_pin_gets_identity_and_role_skill_reload_and_no_crew_nothing(tmp_path):
    root = workspace(tmp_path, UPDATES)
    skill = root / ".claude" / "skills" / "acme-ada" / "SKILL.md"
    skill.parent.mkdir(parents=True)
    skill.write_text("---\nname: acme-ada\n---\n")
    text, _ = cos.render(hook(root), {"WESIDE_COMPANION": "Ada"}, Runner(root))
    assert "invoke the Skill tool with `acme-ada` (your role skill)" in text
    assert "You are the companion Ada" in text
    assert "we:materialize" not in text, "the generic crew has no weside account"
    bare = tmp_path / "bare"
    subprocess.run(["git", "init", "-q", str(bare)], check=True)
    assert cos.render(hook(bare), MASTER, Runner(bare)) == (None, None)
    assert cos.render(hook(root, agent_type="x"), MASTER, Runner(root)) == (None, None)


def test_a_40kb_board_line_stays_in_budget_and_keeps_instructions_and_questions(tmp_path):
    line = {"name": "proj-7", "session_id": "sid", "now": "x" * 20_000, "note": "y" * 20_000}
    queue = [
        {"id": f"Q{i}", "session": "proj-7", "key": "PROJ-8", "ask": "a" * 400} for i in range(5)
    ]
    root = workspace(tmp_path, UPDATES, {"sessions": [line], "owner_queue": queue})
    data = json.loads((root / ".weside" / "crew.json").read_text())
    data["weside_account"] = True
    (root / ".weside" / "crew.json").write_text(json.dumps(data))
    text, err = cos.render(
        hook(root), {"WE_ROLE": "master", "WESIDE_COMPANION": "Ada"}, Runner(root)
    )
    assert err is None and len(text) <= 9_500
    assert "we:materialize" in text and text.endswith(cos.MEMORY)
    assert all(f"- Q{i} PROJ-8 · {'a' * 400}" in text for i in range(5))


def test_the_hooks_run_as_scripts(tmp_path):
    bare = tmp_path / "bare"
    subprocess.run(["git", "init", "-q", str(bare)], check=True)
    for name in ("compact_on_start.py", "epic_age_precompact.py"):
        done = subprocess.run(
            [sys.executable, str(HERE / name)],
            input=json.dumps(hook(bare)),
            capture_output=True,
            text=True,
            check=False,
        )
        assert done.returncode == 0 and done.stdout == "", name
