"""tests/coldstart/run.py: the cold session's argv, env and temp repo, the test slot and --jobs,
with a fake ``claude`` on PATH (scripts/fixtures/coldstart/fake_claude.py). The model run itself is
pod-only."""

from __future__ import annotations

import fcntl
import json
import os
import sys
import threading
import time
from pathlib import Path

import pytest

pytest.importorskip("yaml")

REPO = Path(__file__).resolve().parent.parent
FIXTURES = REPO / "scripts" / "fixtures" / "coldstart"
sys.path.insert(0, str(REPO / "tests" / "coldstart"))

import run  # noqa: E402

T2 = "master/t2-oneway-human-merges"
HIT = {"next_verb": "board", "waits": ["human"], "route": "board item", "reason": "one-way"}


def hit_stream(path: Path) -> Path:
    """The recorded transcript with a hit answer for T2 (the recording itself is a miss)."""
    events = [json.loads(line) for line in (FIXTURES / "recorded.jsonl").read_text().splitlines()]
    for event in events:
        if event["type"] == "result":
            event["structured_output"] = HIT
            event["result"] = json.dumps(HIT)
        if event["type"] == "assistant":
            event["message"]["content"][0]["input"] = HIT
    path.write_text("".join(json.dumps(e) + "\n" for e in events))
    return path


@pytest.fixture
def fake(tmp_path, monkeypatch):
    """A fake ``claude`` first on PATH, HOME and TMPDIR apart, the slot on a temp path."""
    bin_dir, log, home, tmp = (tmp_path / n for n in ("bin", "log", "home", "tmp"))
    for d in (bin_dir, log, home, tmp):
        d.mkdir()
    (bin_dir / "claude").symlink_to(FIXTURES / "fake_claude.py")
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
    monkeypatch.setenv("FAKE_CLAUDE_LOG", str(log))
    monkeypatch.setenv("FAKE_CLAUDE_STREAM", str(hit_stream(tmp_path / "hit.jsonl")))
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("TMPDIR", str(tmp))
    monkeypatch.setenv(run.LOCK_ENV, str(tmp_path / "tests.lock"))
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(home / "pinned-profile"))
    monkeypatch.setenv("WESIDE_COMPANION", "Caller")
    monkeypatch.setenv("WE_ROLE", "worker")

    def calls():
        path = log / "calls.jsonl"
        if not path.exists():
            return []
        return [json.loads(line) for line in path.read_text().splitlines()]

    return calls


def test_the_argv_pins_every_isolation_flag(fake):
    assert run.main(["run", T2]) == 0
    [call] = fake()
    argv = call["argv"]
    assert argv[0] == "-p"
    assert argv[argv.index("--plugin-dir") + 1] == str(REPO / "we")
    assert argv[argv.index("--setting-sources") + 1] == ""
    assert "--strict-mcp-config" in argv and "--no-session-persistence" in argv
    assert call["mcp"] == {"mcpServers": {}}, "an empty --mcp-config on a run without mcp:"
    assert argv[argv.index("--model") + 1] == "claude-opus-5-5"
    assert argv[argv.index("--effort") + 1] == "medium"
    assert argv[argv.index("--output-format") + 1] == "stream-json"
    assert argv[argv.index("--tools") + 1] == "Read,Glob,Grep"
    schema = json.loads(argv[argv.index("--json-schema") + 1])
    assert set(schema["required"]) == {"next_verb", "waits", "route", "reason"}
    assert float(argv[argv.index("--max-budget-usd") + 1]) > 0
    assert argv[-1].startswith("PROJ-12 is In Progress")
    for flag in ("--bare", "--settings", "--disable-slash-commands", "--system-prompt-file"):
        assert flag not in argv


def test_the_env_drops_the_callers_pin_and_role_and_adds_the_scenarios(fake):
    run.main(["run", T2, "master/card-cornerstone"])  # the card case misses on this answer
    t2, card = fake()
    for call in (t2, card):
        assert "CLAUDE_CONFIG_DIR" not in call["env"]
        assert call["env"].get("WESIDE_COMPANION") != "Caller"
    assert "WE_ROLE" not in t2["env"], "a scenario without env: runs without the caller's role"
    assert card["env"]["WE_ROLE"] == "master"


def test_the_session_runs_in_a_fresh_git_repo_outside_home_with_crew_and_world(fake, tmp_path):
    assert run.main(["run", T2]) == 0
    [call] = fake()
    cwd = Path(call["cwd"])
    assert call["crew"]["board"]["file"] == str(cwd.parent / "state" / "board.json")
    assert call["crew"]["human"]["name"] == "Hal", "the fixture crew otherwise unchanged"
    assert tmp_path / "tmp" in cwd.parents and tmp_path / "home" not in cwd.parents
    assert call["git"]
    assert call["files"] == [".weside/crew.json", "docs/plans/PROJ-12-story.md"]
    assert not cwd.exists(), "the temp repo is removed after the run"


def test_a_scenario_mcp_key_is_the_only_server_source(tmp_path):
    scn = {
        "mcp": {"x": {"command": "true"}},
        "crew": "we/scripts/fixtures/crew-v2-generic.json",
        "world": {},
        "prompt": "p",
    }
    _, mcp = run.prepare(scn, tmp_path)
    assert json.loads(mcp.read_text()) == {"mcpServers": {"x": {"command": "true"}}}


def test_the_run_prints_one_result_line(fake, capsys):
    assert run.main(["run", T2]) == 0
    assert capsys.readouterr().out.splitlines() == [f"{T2} hit ok tokens=7036", "judge share: 0/1"]


def test_a_failed_session_is_a_miss_naming_the_cause(fake, monkeypatch, capsys):
    monkeypatch.setenv("FAKE_CLAUDE_EXIT", "1")
    assert run.main(["run", T2]) == 1
    assert capsys.readouterr().out.startswith(f"{T2} miss exit 1 ")
    monkeypatch.setenv("FAKE_CLAUDE_EXIT", "0")
    monkeypatch.setenv("FAKE_CLAUDE_STREAM", str(FIXTURES / "no-answer.jsonl"))
    assert run.main(["run", T2]) == 1
    assert "miss no parseable answer" in capsys.readouterr().out


def test_a_user_claude_md_refuses_the_start_naming_the_file(fake, tmp_path, capsys):
    (tmp_path / "home" / ".claude").mkdir()
    (tmp_path / "home" / ".claude" / "CLAUDE.md").write_text("x")
    assert run.main(["run", T2]) == 2
    assert f"{tmp_path}/home/.claude/CLAUDE.md exists" in capsys.readouterr().err
    assert fake() == []


def test_a_tmpdir_under_home_is_refused(fake, tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("TMPDIR", str(tmp_path / "home"))
    assert run.main(["run", T2]) == 2
    assert "lies under HOME" in capsys.readouterr().err
    assert fake() == []


def test_more_than_two_jobs_is_refused(fake, capsys):
    assert run.main(["run", T2, "--jobs", "3"]) == 2
    assert "--jobs 3: at most 2" in capsys.readouterr().err
    assert fake() == []


def test_a_held_slot_makes_the_run_wait_and_say_so(fake, tmp_path, capsys):
    fd = os.open(tmp_path / "tests.lock", os.O_RDWR | os.O_CREAT)
    fcntl.flock(fd, fcntl.LOCK_EX)
    codes = []
    worker = threading.Thread(target=lambda: codes.append(run.main(["run", T2])))
    worker.start()
    time.sleep(1.0)
    assert fake() == [], "no session starts outside the slot"
    assert "waiting for test slot (held by pid" in capsys.readouterr().err
    os.close(fd)
    worker.join(30)
    assert codes == [0] and len(fake()) == 1


def test_a_bad_scenario_stops_before_any_model_call(tmp_path):
    bad = tmp_path / "bad.yaml"
    bad.write_text(
        "id: bad\nrole: master\ncrew: we/scripts/fixtures/crew-v2-generic.json\n"
        "env: {HOME: /x}\nprompt: p\nexpect: {}\n"
    )
    with pytest.raises(run.ScenarioError, match=r"bad\.yaml: env key HOME not allowed"):
        run.load(bad)
    bad.write_text("id: [\n")
    with pytest.raises(run.ScenarioError, match="does not parse"):
        run.load(bad)
