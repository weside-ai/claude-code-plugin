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


# --- affected set and digest (throwaway repos, one diff per mapping row) ---------------------

import subprocess  # noqa: E402

import affected  # noqa: E402

SKILL = "---\nname: x\ndescription: >\n  Close out a merged PR.\n---\n\n# x\n"


def _scenario(role: str, routing: bool = False) -> str:
    extra = "routing: true\n" if routing else ""
    return f"id: a\nrole: {role}\ncrew: fx/crew.json\n{extra}prompt: p\nexpect:\n  route: x\n"


@pytest.fixture
def tree(tmp_path):
    """A repo with one master, one worker and one routing scenario on ``base``."""
    root = tmp_path / "r"
    files = {
        "we/process/L0.md": "l0\n",
        "we/hooks/role_on_start.py": "#\n",
        "we/scripts/crew.py": "#\n",
        "we/roles/master.md": "m\n",
        "we/roles/worker.md": "w\n",
        "we/skills/merged/SKILL.md": SKILL,
        "we/skills/other.md": "o\n",
        "fx/crew.json": "{}\n",
        "tests/coldstart/run.py": "#\n",
        "tests/coldstart/schema.json": "{}\n",
        "tests/coldstart/master/a.yaml": _scenario("master"),
        "tests/coldstart/worker/b.yaml": _scenario("worker"),
        "tests/coldstart/worker/route.yaml": _scenario("worker", routing=True),
    }
    for rel, text in files.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(text)

    def git(*args):
        subprocess.run(["git", *args], cwd=root, check=True, capture_output=True)

    git("init", "-q", "-b", "main")
    git("-c", "user.name=t", "-c", "user.email=t@example.invalid", "add", ".")
    git("-c", "user.name=t", "-c", "user.email=t@example.invalid", "commit", "-qm", "base")
    git("branch", "base")

    def change(rel: str, text: str) -> set[str]:
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(text)
        git("add", rel)
        git("-c", "user.name=t", "-c", "user.email=t@example.invalid", "commit", "-qm", rel)
        return affected.affected("base", root)

    change.root = root
    return change


ALL = {"master/a", "worker/b", "worker/route"}


@pytest.mark.parametrize(
    "path",
    [
        "we/process/L0.md",
        "we/hooks/role_on_start.py",
        "we/scripts/crew.py",
        "fx/crew.json",
        "tests/coldstart/run.py",
        "tests/coldstart/schema.json",
    ],
)
def test_a_global_input_affects_every_scenario(tree, path):
    assert tree(path, "changed\n") == ALL


def test_a_role_card_affects_the_scenarios_of_its_role(tree):
    assert tree("we/roles/worker.md", "w2\n") == {"worker/b", "worker/route"}


def test_a_skill_description_affects_the_routing_scenarios(tree):
    assert tree("we/skills/merged/SKILL.md", SKILL.replace("Close out", "Wrap up")) == {
        "worker/route"
    }


def test_a_skill_body_edit_affects_nothing(tree):
    assert tree("we/skills/merged/SKILL.md", SKILL + "more body\n") == set()


def test_a_scenario_file_affects_itself(tree):
    assert tree("tests/coldstart/master/a.yaml", _scenario("master") + "judge: null\n") == {
        "master/a"
    }


def test_an_unrelated_file_affects_nothing(tree):
    assert tree("we/skills/other.md", "o2\n") == set()


def test_the_digest_follows_the_inputs_not_the_commit(tree):
    root = tree.root
    tree("we/roles/master.md", "m2\n")
    first = affected.digest({"master/a"}, root)
    tree("we/skills/other.md", "o3\n")  # a new commit, no input of master/a changed
    assert affected.digest({"master/a"}, root) == first
    tree("we/roles/master.md", "m3\n")
    assert affected.digest({"master/a"}, root) != first
    assert affected.digest({"worker/b"}, root) != affected.digest({"master/a"}, root)


def test_uncommitted_suite_inputs_are_named(tree):
    root = tree.root
    (root / "we/roles/master.md").write_text("dirty\n")
    (root / "notes.txt").write_text("not an input\n")
    assert affected.dirty_inputs(root) == ["we/roles/master.md"]


def test_the_model_pin_is_one_value():
    assert f"{run.MODEL} {run.EFFORT}" == affected.MODEL_PIN


# --- release: caps and the receipt (fake claude) ---------------------------------------------

CAPS = {"release_cap": {"runs": 9, "wall_minutes": 5}, "cost_target_tokens": 10**9}


@pytest.fixture
def released(fake, monkeypatch, capsys):
    """``release`` on a fixed affected set with the given rates table; returns (code, out, block)."""

    def go(ids, table=CAPS):
        monkeypatch.setattr(affected, "affected", lambda _base: set(ids))
        monkeypatch.setattr(affected, "dirty_inputs", list)
        monkeypatch.setattr(run, "rates", lambda: table)
        code = run.main(["release", "--base", "origin/main"])
        out = capsys.readouterr().out
        block = json.loads(
            out.split(run.RECEIPT_MARKER, 1)[1].split("```json", 1)[1].split("```")[0]
        )
        return code, out, block

    return go


def test_release_runs_each_affected_scenario_three_times_and_prints_the_receipt(released, fake):
    code, _, block = released([T2])
    assert code == 0 and len(fake()) == 3
    assert block["status"] == "green" and block["affected"] == [T2]
    row = next(r for r in block["scenarios"] if r["id"] == T2)
    assert row == {"id": T2, "runs": 3, "hits": 3, "gated": True, "status": "run"}
    assert block["digest"] == affected.digest({T2})
    assert block["tokens"] == 3 * 7036 and block["runs"] == 3
    others = [r for r in block["scenarios"] if r["id"] != T2]
    assert len(others) == len(run.scenario_paths()) - 1, "no scenario is left out"
    assert {r["status"] for r in others} == {"unmeasured"}
    for key in ("plugin_version", "model", "wall_s", "base"):
        assert key in block


def test_a_gated_miss_turns_the_receipt_red(released, fake, monkeypatch):
    monkeypatch.setenv("FAKE_CLAUDE_STREAM", str(FIXTURES / "recorded.jsonl"))  # a miss
    code, _, block = released([T2])
    assert code == 1 and block["status"] == "red"
    assert block["reasons"] == [f"gated miss {T2} 0/3"]


def test_an_affected_set_over_the_run_cap_starts_no_session(released, fake):
    code, _, block = released(
        [T2, "master/card-cornerstone", "worker/card-cornerstone", "master/route-merged"]
    )
    assert code == 1 and fake() == []
    assert block["status"] == "red" and block["reasons"][0] == "cap runs 12 > 9"
    assert all(
        r["status"] == "not run" for r in block["scenarios"] if r["id"] in block["affected"]
    )


def test_the_wall_cap_stops_and_marks_the_rest_not_run(released, fake, monkeypatch):
    monkeypatch.setenv("FAKE_CLAUDE_SLEEP", "1")
    table = {"release_cap": {"runs": 9, "wall_minutes": 0.01}}
    code, out, block = released([T2, "master/card-cornerstone"], table)
    assert code == 1 and 1 <= len(fake()) < 6
    assert block["reasons"][0] == "cap wall 0.01 min"
    assert "not run master/card-cornerstone" in block["reasons"]
    assert "not run (wall cap)" in out


def test_no_suite_input_changed_prints_a_receipt_with_zero_runs(released, fake):
    code, out, block = released([])
    assert code == 0 and fake() == []
    assert out.startswith("no suite input changed\n")
    assert (block["status"], block["runs"], block["affected"]) == ("green", 0, [])


def test_tokens_over_the_cost_target_print_one_line_and_do_not_fail(released):
    code, out, _ = released([T2], dict(CAPS, cost_target_tokens=1000))
    assert code == 0
    assert "cost over target: 21108 > 1000" in out.splitlines()


def test_release_refuses_uncommitted_suite_inputs(fake, monkeypatch, capsys):
    monkeypatch.setattr(affected, "dirty_inputs", lambda: ["we/roles/master.md"])
    assert run.main(["release", "--base", "origin/main"]) == 2
    assert "uncommitted suite inputs: we/roles/master.md" in capsys.readouterr().err
    assert fake() == []


# --- measure ---------------------------------------------------------------------------------


def test_measure_writes_rates_and_keeps_caps_and_defects(fake, monkeypatch, tmp_path, capsys):
    rates_file = tmp_path / "rates.json"
    table = {
        "release_cap": {"runs": 69, "wall_minutes": 30},
        "scenarios": {"master/crew-unknown-key": {"defect": "kept"}},
    }
    rates_file.write_text(json.dumps(table))
    monkeypatch.setattr(run, "RATES", rates_file)
    paths = [p for p in run.scenario_paths() if run.sid_of(p) in (T2, "master/crew-unknown-key")]
    monkeypatch.setattr(run, "scenario_paths", lambda: paths)
    assert run.main(["measure", "--runs", "2", "--jobs", "2"]) == 0
    assert len([c for c in fake() if "-p" in c["argv"]]) == 4  # plus one claude --version
    written = json.loads(rates_file.read_text())
    assert written["release_cap"] == table["release_cap"]
    assert written["scenarios"][T2] == {"runs": 2, "hits": 2, "gated": True}
    miss = written["scenarios"]["master/crew-unknown-key"]
    assert (miss["hits"], miss["gated"], miss["defect"]) == (0, False, "kept")
    assert written["suite_tokens_one_run"] == 2 * 7036
    assert written["measured"]["model"] == "claude-opus-5-5 medium"
    assert written["measured"]["digest"] == affected.digest({T2, "master/crew-unknown-key"})
    assert "master/crew-unknown-key 0/2 NOT gated" in capsys.readouterr().out
