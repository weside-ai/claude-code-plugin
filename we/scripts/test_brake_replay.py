"""brake_replay.py: a fixture brake log and transcript give the expected counts."""

from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import brake_replay

SID = "s-1"


def _ts(minutes_ago: int) -> str:
    when = dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=minutes_ago)
    return when.strftime("%Y-%m-%dT%H:%M:%SZ")


def _deny(item: str, sid: str = SID, minutes_ago: int = 5) -> dict:
    return {
        "ts": _ts(minutes_ago),
        "type": "deny",
        "gate": "worker_rights_gate",
        "item": item,
        "session_id": sid,
    }


def _call(n: int, command: str, reason: str) -> list[dict]:
    use = {"type": "tool_use", "id": f"t{n}", "name": "Bash", "input": {"command": command}}
    result = {
        "type": "tool_result",
        "tool_use_id": f"t{n}",
        "is_error": True,
        "content": f"PreToolUse:Bash hook error: {reason}: ask your starter",
    }
    return [
        {"type": "assistant", "message": {"content": [use]}},
        {"type": "user", "message": {"content": [result]}},
    ]


def test_a_fixture_log_gives_logged_recovered_and_still_denied(tmp_path, monkeypatch, capsys):
    gone = "never for a worker (guard bypass (--no-verify))"
    stays = "never for a worker (secrets (gh secret))"
    comment = "not a worker right (acme/app grants no worker rights (crew worker_rights.repos))"
    state = tmp_path / "state"
    state.mkdir()
    rows = [
        _deny(gone),
        _deny(stays),
        _deny(comment),
        _deny(stays, sid="s-gone"),  # its transcript is gone: unrecovered
        _deny(stays, minutes_ago=60 * 24 * 30),  # outside the window
        {"ts": _ts(5), "type": "crash", "gate": "worker_rights_gate", "error": "X"},
    ]
    (state / "brakes.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
    lines = [
        *_call(1, "git push --no-verify origin HEAD", gone),
        *_call(2, "git status", "something else"),
        *_call(3, "gh secret list", stays),
        *_call(4, "gh pr comment 8 --body x", comment),
    ]
    project = tmp_path / "projects" / "-tmp-app"
    project.mkdir(parents=True)
    (project / f"{SID}.jsonl").write_text("".join(json.dumps(x) + "\n" for x in lines))
    monkeypatch.setenv("WE_STATE_DIR", str(state))
    monkeypatch.chdir(tmp_path)
    crew = tmp_path / "crew.json"
    crew.write_text(json.dumps({"worker_rights": {"deny_text": []}}))
    args = ["--projects", str(tmp_path / "projects"), "--crew", str(crew), "--json"]
    assert brake_replay.main(args) == 0
    out = capsys.readouterr().out
    result = json.loads(out)
    assert (result["logged"], result["recovered"], result["still_denied"]) == (4, 3, 1)
    assert result["still_denied_items"] == {"never for a worker (secrets (gh secret))": 1}
    assert set(result["now_pass"]) == {
        gone,
        "not a worker right (<ref> grants no worker rights (crew worker_rights.repos))",
    }
    assert "gh secret list" not in out and "--no-verify origin" not in out
    assert (state / "brakes.jsonl").read_text().count("\n") == len(rows)  # the replay logs nothing


def test_kind_drops_the_values_an_item_names():
    assert brake_replay.kind("never for a worker (crew deny_text (/dev/shm/x-))") == (
        "never for a worker (crew deny_text)"
    )
    assert (
        brake_replay.kind(
            "not a worker right (PR 7 is not this branch's PR (its head is feat/AB-1-x))"
        )
        == "not a worker right (PR N is not this branch's PR"
    )
    assert brake_replay.kind("never for a worker (secrets (crew deny_commands: vault put))") == (
        "never for a worker (secrets (crew deny_commands))"
    )
    tag = brake_replay.kind("never for a worker (guard bypass (git push of the tag v1.2))")
    assert "v1.2" not in tag
