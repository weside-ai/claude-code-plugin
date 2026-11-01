"""SessionStart working-mode core: kind per environment, a line per role, nothing without a crew."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

HOOK = Path(__file__).resolve().parent / "working_mode_on_start.py"
sys.path.insert(0, str(HOOK.parent))

import working_mode_on_start as wm  # noqa: E402

# A crew as long as a real one: every role held, long titles and several components.
CREW = {
    "question_label": "ASK",
    "roles": {"product_owner": "ana", "orchestrator": "ben", "hr": "cleo", "tester": "dex"},
    "members": {
        "ana": {
            "name": "Ana",
            "role": "product_owner",
            "components": ["App", "Platform Core", "Community"],
        },
        "ben": {"name": "Ben", "role": "orchestrator"},
        "cleo": {"name": "Cleo", "role": "hr"},
        "dex": {"name": "Dexter", "role": "tester"},
        "eva": {
            "name": "Eva",
            "role": "architect",
            "title": "Architecture and Security Review",
            "components": ["Architecture", "Security Engineering"],
        },
        "finn": {"name": "Finn", "role": "ux_researcher"},
        "gus": {"name": "Gus", "role": "security", "on_call": True},
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
    if not done.stdout:
        return None
    return json.loads(done.stdout)["hookSpecificOutput"]["additionalContext"]


def test_no_crew_no_output(tmp_path):
    assert run(tmp_path, {"WE_ROLE": "master"}, crew=None) is None


def test_component_owner(tmp_path):
    note = run(tmp_path, {"WE_ROLE": "master", "WESIDE_COMPANION": "Eva"})
    assert "component owner of Architecture, Security Engineering" in note
    assert "you start no workers" in note
    assert "SendMessage to Ben" in note and "`ASK · <KEY>" in note


def test_one_line_per_role_with_duties(tmp_path):
    note = run(tmp_path, {"WE_ROLE": "master"})
    assert "- Orchestrator: Ben — starts and parks build masters" in note
    assert "- Product Owner: Ana — the WHAT" in note
    assert "- HR: Cleo — " in note
    assert "- Tester: Dexter — staging acceptance; moves a story to Done." in note


def test_role_holder_points_at_its_role_line(tmp_path):
    note = run(tmp_path, {"WE_ROLE": "master", "WESIDE_COMPANION": "Ben"})
    assert "the companion Ben, the Orchestrator (below)" in note
    assert "SendMessage to Ben" not in note and "/board" in note


def test_pin_without_we_role_is_a_named_master(tmp_path):
    assert "named master, the companion Finn" in run(tmp_path, {"WESIDE_COMPANION": "Finn"})


def test_on_call_member(tmp_path):
    note = run(tmp_path, {"WESIDE_COMPANION": "Gus"})
    assert "on call: answer what you were woken for" in note


def test_unknown_pin_asks_the_orchestrator(tmp_path):
    note = run(tmp_path, {"WESIDE_COMPANION": "Zed"})
    assert "not in the crew: ask the Orchestrator" in note and "judge" not in note


def test_unnamed_master_and_plain_claude(tmp_path):
    for env in ({"WE_ROLE": "master"}, {}):
        note = run(tmp_path, env)
        assert "unnamed master (build master or helper)" in note
        assert "epic owner (label `owner-<slug>`), else the component owner" in note


def test_consultation(tmp_path):
    note = run(tmp_path, {"WE_ROLE": "worker", "WESIDE_COMPANION": "Eva"})
    assert "a consultation as the companion Eva" in note and "then end" in note
    assert "SendMessage to Ben" not in note


def test_worker_reports_to_its_starter_only(tmp_path):
    for env, extra in (
        ({"WE_ROLE": "worker"}, None),
        ({"WE_ROLE": "master"}, {"agent_type": "x"}),
    ):
        note = run(tmp_path, env, hook_input=extra)
        assert "a worker" in note and "to your starter" in note
        assert "SendMessage to Ben" not in note


def test_reads_the_reference_as_an_imperative(tmp_path):
    note = run(tmp_path, {"WE_ROLE": "master"})
    assert f"Read {wm.REFERENCE} before routing, starting a session or moving a ticket." in note
    assert wm.REFERENCE.is_file()


def test_budget_for_every_kind():
    reference = Path(
        "/home/user/.claude/plugins/cache/weside-ai/we/9.99.0/references/working-mode.md"
    )
    cases = (
        ("named", "Eva"),
        ("named", "Ben"),
        ("named", "Gus"),
        ("consult", "Eva"),
        ("unnamed", ""),
        ("worker", ""),
    )
    for kind, pin in cases:
        note = wm.core(CREW, kind, pin, reference=reference)
        assert len(note.splitlines()) <= wm.MAX_LINES, note
        assert len(note) <= wm.MAX_CHARS, (len(note), note)


def test_defaults_without_roles_or_label(tmp_path):
    note = run(tmp_path, {}, crew={"members": {}})
    assert "the Orchestrator" in note and "`QUESTION ·" in note
