"""SessionStart working-mode core: role per environment, nothing without a crew, a small budget."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

HOOK = Path(__file__).resolve().parent / "working_mode_on_start.py"
sys.path.insert(0, str(HOOK.parent))

import working_mode_on_start as wm  # noqa: E402

# The longest crew we know: names, titles and components of a real twelve-member crew.
CREW = {
    "question_label": "FRAGE",
    "roles": {"product_owner": "pia", "orchestrator": "samu", "hr": "elise", "tester": "smoke"},
    "members": {
        "pia": {
            "name": "Pia",
            "role": "product_owner",
            "title": "Product Owner",
            "components": ["Weside", "Omnilogue", "Community"],
        },
        "samu": {"name": "Samu", "role": "orchestrator", "title": "Orchestrator"},
        "vyra": {
            "name": "Vyra",
            "role": "architect",
            "title": "Architecture (incl. Security)",
            "components": ["Architecture"],
        },
        "elise": {"name": "Elise", "role": "hr"},
        "smoke": {"name": "Smoketest", "role": "tester"},
    },
}


def run(tmp_path, env_extra, crew=CREW, hook_input=None):
    if crew is not None:
        (tmp_path / ".weside").mkdir(exist_ok=True)
        (tmp_path / ".weside" / "crew.json").write_text(json.dumps(crew))
    env = {k: v for k, v in os.environ.items() if k not in ("WE_ROLE", "WESIDE_COMPANION")}
    env.update(env_extra)
    data = {"session_id": "s", "source": "startup", "cwd": str(tmp_path), **(hook_input or {})}
    done = subprocess.run(
        [sys.executable, str(HOOK)],
        input=json.dumps(data),
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert done.returncode == 0, done.stderr
    return (
        json.loads(done.stdout)["hookSpecificOutput"]["additionalContext"] if done.stdout else None
    )


def test_no_crew_no_output(tmp_path):
    assert run(tmp_path, {"WE_ROLE": "master"}, crew=None) is None


def test_named_master_with_role(tmp_path):
    note = run(tmp_path, {"WE_ROLE": "master", "WESIDE_COMPANION": "Vyra"})
    assert "named master, the companion Vyra (Architecture (incl. Security)" in note
    assert "steer no workers" in note
    assert "SendMessage to Samu" in note and "`FRAGE · <KEY>" in note


def test_pin_without_we_role_is_a_named_master(tmp_path):
    note = run(tmp_path, {"WESIDE_COMPANION": "Vyra"})
    assert "named master, the companion Vyra" in note


def test_unnamed_master_and_plain_claude(tmp_path):
    for env in ({"WE_ROLE": "master"}, {}):
        note = run(tmp_path, env)
        assert "unnamed master (build master or helper)" in note


def test_worker_by_env_or_agent(tmp_path):
    assert "a worker" in run(tmp_path, {"WE_ROLE": "worker", "WESIDE_COMPANION": "Vyra"})
    assert "a worker" in run(tmp_path, {"WE_ROLE": "master"}, hook_input={"agent_type": "x"})


def test_orchestrator_keeps_the_board_and_sends_no_question_to_itself(tmp_path):
    note = run(tmp_path, {"WE_ROLE": "master", "WESIDE_COMPANION": "Samu"})
    assert "/board" in note and "SendMessage to Samu" not in note


def test_names_the_reference(tmp_path):
    note = run(tmp_path, {"WE_ROLE": "master"})
    assert str(wm.REFERENCE) in note and wm.REFERENCE.is_file()


def test_budget_for_every_role():
    reference = Path(
        "/home/user/.claude/plugins/cache/weside-ai/we/7.44.0/references/working-mode.md"
    )
    for kind, pin in (("named", "Vyra"), ("named", "Samu"), ("unnamed", ""), ("worker", "")):
        note = wm.core(CREW, kind, pin, reference=reference)
        assert len(note.splitlines()) <= wm.MAX_LINES, note
        assert len(note) <= wm.MAX_CHARS, (len(note), note)


def test_defaults_without_roles_or_label(tmp_path):
    note = run(tmp_path, {}, crew={"members": {}})
    assert "the Orchestrator" in note and "`QUESTION ·" in note
