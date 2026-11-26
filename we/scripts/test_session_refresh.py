"""session_refresh.py and plugin_install.py: the roll-call of live sessions' plugin versions, the
version source, the refresh plan and the trigger rule."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
import plugin_install
import session_refresh as sr

NOW = 2_000_000_000.0
DAY_MS = 86_400_000


def version_dir(cache: Path, version: str, l0: str = "L0 text") -> Path:
    root = cache / version
    for part, text in (("process", l0), ("roles", "card"), ("hooks", "hook")):
        (root / part).mkdir(parents=True, exist_ok=True)
        (root / part / "f.md").write_text(text)
    (root / ".claude-plugin").mkdir(exist_ok=True)
    (root / ".claude-plugin" / "plugin.json").write_text(json.dumps({"version": version}))
    return root


def config(tmp_path: Path, installed: str = "9.4.0") -> tuple[dict, Path]:
    cfg = tmp_path / "cfg"
    cache = cfg / "plugins" / "cache" / "pub" / "we"
    version_dir(cache, installed, "L0 new")
    entry = {"scope": "user", "version": installed, "installPath": str(cache / installed)}
    (cfg / "plugins").mkdir(parents=True, exist_ok=True)
    (cfg / "plugins" / "installed_plugins.json").write_text(
        json.dumps({"version": 2, "plugins": {"we@pub": [entry]}})
    )
    return {"CLAUDE_CONFIG_DIR": str(cfg), "HOME": str(tmp_path)}, cache


def roll(
    tmp_path,
    rows,
    loaded,
    markers=None,
    environs=None,
    monkeypatch=None,
    env=None,
    cc=None,
    cc_new=None,
):
    monkeypatch.setattr(sr.worker_launch, "_pid_lives", lambda _pid: True)
    monkeypatch.setattr(plugin_install, "loaded_versions", lambda pid, _roots: loaded.get(pid, []))
    markers = markers or {}
    environs = environs or {}
    return {
        r["name"]: r
        for r in sr.roll_call(
            rows,
            env,
            NOW,
            read_marker=markers.get,
            read_env=environs.get,
            state=tmp_path / "state",
            read_claude_code=(cc or {}).get,
            claude_code=lambda: cc_new,
        )
    }


def row(name, pid, status="idle", kind="interactive", cwd="/w", days=1.0, **extra):
    return {
        "name": name,
        "pid": pid,
        "status": status,
        "kind": kind,
        "cwd": cwd,
        "sessionId": f"sid-{name}",
        "startedAt": (NOW * 1000) - days * DAY_MS,
        **extra,
    }


def test_list_marks_behind_at_rest_and_busy_with_live_worker(tmp_path, monkeypatch):
    env, cache = config(tmp_path)
    version_dir(cache, "8.48.0", "L0 old")
    rows = [
        row("Ada", 11),
        row("lead-1", 12, status="busy", cwd="/lead"),
        row("KEY-1-build", 13, kind="background", status="busy", cwd="/tree", state="working"),
    ]
    markers = {"/tree": {"name": "KEY-1-build", "starter": "lead-1"}}
    environs = {11: {"WE_ROLE_ID": "product"}, 12: {"WE_ROLE": "master"}}
    loaded = {11: ["8.46.0", "8.48.0"], 12: ["9.4.0"], 13: ["9.4.0"]}
    out = roll(tmp_path, rows, loaded, markers, environs, monkeypatch, env)

    ada, lead, worker = out["Ada"], out["lead-1"], out["KEY-1-build"]
    assert (ada["role"], ada["loaded"], ada["installed"]) == ("product", "8.48.0", "9.4.0")
    assert ada["behind"] == "yes" and ada["at_rest"] and ada["due"] == "changed process"
    assert (lead["behind"], lead["at_rest"], lead["workers"]) == ("no", False, ["KEY-1-build"])
    assert (worker["role"], worker["state"], worker["due"]) == ("worker", "busy", "")
    assert sr.line(lead).endswith("at_rest=no (workers: KEY-1-build)")


def test_queued_start_and_unknown_version_keep_a_session_from_rest(tmp_path, monkeypatch):
    env, _ = config(tmp_path)
    queue = tmp_path / "state" / "queue"
    queue.mkdir(parents=True)
    (queue / "KEY-2-a.json").write_text(
        json.dumps({"name": "KEY-2-a", "starter": "Ada", "waiter_pid": os.getpid()})
    )
    out = roll(
        tmp_path, [row("Ada", 11), row("Bo", 12)], {11: ["8.0.0"]}, None, None, monkeypatch, env
    )
    assert out["Ada"]["queued"] == ["KEY-2-a"] and not out["Ada"]["at_rest"]
    assert (out["Bo"]["loaded"], out["Bo"]["behind"], out["Bo"]["role"]) == ("?", "?", "?")


def test_trigger_b_age_when_watched_folders_are_equal(tmp_path, monkeypatch):
    env, cache = config(tmp_path, "9.4.1")
    version_dir(cache, "9.4.0", "L0 new")  # same process/, roles/, hooks/ as 9.4.1
    rows = [row("Young", 11, days=1), row("Old", 12, days=4)]
    out = roll(tmp_path, rows, {11: ["9.4.0"], 12: ["9.4.0"]}, None, None, monkeypatch, env)
    assert out["Young"]["behind"] == "yes" and out["Young"]["due"] == ""
    assert out["Old"]["due"] == "started 4.0 days ago"


def test_trigger_a_without_the_old_folder_counts_minor_bumps_only():
    assert sr.changed(None, None, "9.3.1", "9.4.0") == list(sr.WATCHED)
    assert sr.changed(None, None, "9.4.0", "9.4.1") == []


def test_refresh_days_reads_the_crew(tmp_path):
    root = tmp_path / "repo"
    (root / ".weside").mkdir(parents=True)
    (root / ".git").mkdir()
    crew = {"version": 2, "roles": {"coordinator": "a"}, "members": {"a": {"name": "A"}}}
    (root / ".weside" / "crew.json").write_text(json.dumps(crew))
    assert sr.refresh_days(str(root)) == sr.DEFAULT_DAYS
    crew["sessions"] = {"refresh_after_days": 7}
    (root / ".weside" / "crew.json").write_text(json.dumps(crew))
    assert sr.refresh_days(str(root)) == 7


# --- the version source ------------------------------------------------------------------------


def test_loaded_versions_reads_in_use_marks_of_this_process_only(tmp_path):
    cache = tmp_path / "cache"
    me = os.getpid()
    start = plugin_install.proc_start(me)
    if start is None:
        pytest.skip("no /proc")
    for version, proc in (("8.46.0", start), ("8.48.0", start), ("9.0.0", "1")):
        (cache / version / ".in_use").mkdir(parents=True)
        (cache / version / ".in_use" / str(me)).write_text(
            json.dumps({"pid": me, "procStart": proc})
        )
    # 9.0.0 names this pid with another start time: a reused pid, not this process
    assert plugin_install.loaded_versions(me, [cache]) == ["8.46.0", "8.48.0"]
    assert plugin_install.loaded_versions("x", [cache]) == []


def test_install_for_prefers_the_nearest_project_entry(tmp_path):
    entries = [
        {"scope": "user", "version": "9.4.0", "installPath": "/c/9.4.0"},
        {"scope": "user", "version": "9.10.0", "installPath": "/c/9.10.0"},
        {"scope": "project", "projectPath": str(tmp_path), "version": "8.1.0"},
        {"scope": "local", "projectPath": str(tmp_path / "a"), "version": "8.2.0"},
    ]
    (tmp_path / "a" / "b").mkdir(parents=True)
    pick = plugin_install.install_for
    assert pick(tmp_path / "a" / "b", entries=entries)["version"] == "8.2.0"
    assert pick(tmp_path, entries=entries)["version"] == "8.1.0"
    assert pick("/", entries=entries)["version"] == "9.10.0"


# --- the plan ----------------------------------------------------------------------------------


def rec(name, role="product", kind="interactive", cwd="/w", **extra):
    base = {
        "name": name,
        "role": role,
        "kind": kind,
        "cwd": cwd,
        "id": "",
        "session_id": f"sid-{name}",
        "loaded": "8.48.0",
        "installed": "9.4.0",
        "state": "idle",
        "behind": "yes",
        "at_rest": True,
        "workers": [],
        "queued": [],
        "due": "",
    }
    return {**base, **extra}


def crew_repo(tmp_path):
    root = tmp_path / "repo"
    (root / ".weside").mkdir(parents=True)
    (root / ".git").mkdir()
    crew = {
        "version": 2,
        "roles": {"coordinator": "lead", "product": "po"},
        "members": {"lead": {"name": "Lea"}, "po": {"name": "Ada"}},
        "labels": {"ready": "bereit"},
    }
    (root / ".weside" / "crew.json").write_text(json.dumps(crew))
    return root


def test_plan_for_a_crew_role_names_the_launcher(tmp_path):
    root = crew_repo(tmp_path)
    text = sr.plan("Ada", [rec("Ada", cwd=str(root))])
    assert "1. SendMessage to Ada: Plugin refresh: you run we 8.48.0, 9.4.0 is installed." in text
    assert "reply `bereit`" in text and "2. Wait for its reply `bereit`." in text
    assert "`/exit`" in text
    assert "start.py launch product --fresh" in text
    assert "wclaude --start --role product --fresh" in text
    assert "we-worker" not in text
    lea = sr.plan("Lea", [rec("Lea", role="coordinator", cwd=str(root))])
    assert "wclaude --start --fresh" in lea and "start.py launch" not in lea


def test_plan_without_a_crew_role_starts_plain_claude(tmp_path):
    text = sr.plan(
        "scratch", [rec("scratch", role="?", kind="background", id="ab12", cwd=str(tmp_path))]
    )
    assert "claude stop ab12" in text
    assert (
        f'cd {tmp_path} && claude --name scratch "Fresh start: before anything else, read your state'
        in text
    )


@pytest.mark.parametrize(
    "record, reason",
    [
        (rec("W", role="worker"), "is a worker"),
        (rec("A", behind="no"), "is not behind"),
        (rec("A", at_rest=False, state="busy", workers=["K-1"]), "not at rest (busy, K-1)"),
    ],
)
def test_plan_refuses(record, reason):
    with pytest.raises(sr.PlanError, match=reason.replace("(", r"\(").replace(")", r"\)")):
        sr.plan(record["name"], [record])


def test_handover_runs_the_installed_role_hook_once_and_never_hands_on(tmp_path):
    env, cache = config(tmp_path)
    new = cache / "9.4.0"
    own = version_dir(tmp_path / "own", "9.3.0")
    (new / "hooks" / "role_on_start.py").write_text(
        "import json, os, sys\n"
        "data = json.load(sys.stdin)\n"
        "ctx = 'CARD ' + data['source'] + ' ' + os.environ['WE_HANDOVER_FROM']\n"
        "print(json.dumps({'hookSpecificOutput': {'additionalContext': ctx}}))\n"
    )
    env = {**env, "CLAUDE_PLUGIN_ROOT": str(own)}
    hook_input = {"source": "compact", "cwd": str(tmp_path)}
    got = plugin_install.handover("role_on_start.py", hook_input, env)
    assert got == ("CARD compact 9.3.0", "9.3.0", "9.4.0")
    assert (
        plugin_install.handover("role_on_start.py", {**hook_input, "source": "clear"}, env) is None
    )
    assert (
        plugin_install.handover(
            "role_on_start.py", hook_input, {**env, "WE_HANDOVER_FROM": "9.3.0"}
        )
        is None
    )


def test_a_background_crew_member_is_no_worker_and_can_be_due(tmp_path, monkeypatch):
    env, cache = config(tmp_path)
    version_dir(cache, "8.48.0", "L0 old")
    state = tmp_path / "state"
    state.mkdir()
    (state / "Ada.settings.json").write_text(
        json.dumps({"env": {"WE_ROLE": "master", "WE_ROLE_ID": "product"}})
    )
    rows = [row("Ada", 11, kind="background"), row("KEY-3-a", 12, kind="background")]
    out = roll(tmp_path, rows, {11: ["8.48.0"], 12: ["8.48.0"]}, None, None, monkeypatch, env)
    assert (out["Ada"]["role"], out["Ada"]["due"]) == ("product", "changed process")
    assert (out["KEY-3-a"]["role"], out["KEY-3-a"]["due"]) == ("worker", "")


def test_trigger_c_an_older_claude_code_is_due_at_rest_never_for_a_worker(tmp_path, monkeypatch):
    """Numbers, not strings: 2.1.99 is older than 2.1.332. Equal or unreadable raises nothing."""
    env, _ = config(tmp_path)
    rows = [
        row("Old", 11),
        row("Same", 12),
        row("Blind", 13),
        row("Busy", 14, status="busy"),
        row("KEY-4-a", 15, kind="background"),
    ]
    loaded = {pid: ["9.4.0"] for pid in (11, 12, 13, 14, 15)}  # no plugin reason
    cc = {11: "2.1.99", 12: "2.1.332", 14: "2.1.99", 15: "2.1.99"}
    out = roll(tmp_path, rows, loaded, None, None, monkeypatch, env, cc, "2.1.332")
    assert out["Old"]["due"] == "Claude Code 2.1.99 older than installed 2.1.332"
    assert sr.line(out["Old"]).endswith("due: Claude Code 2.1.99 older than installed 2.1.332")
    assert [out[n]["due"] for n in ("Same", "Blind", "Busy", "KEY-4-a")] == ["", "", "", ""]
    assert out["Blind"]["claude_code"] == "?"
    out = roll(tmp_path, rows[:1], loaded, None, None, monkeypatch, env, cc, None)
    assert out["Old"]["due"] == ""  # the installed version unreadable


def test_claude_code_versions_come_from_the_binary_path(tmp_path, monkeypatch):
    assert sr._version_of_binary("/u/.local/share/claude/versions/2.1.332") == "2.1.332"
    assert sr._version_of_binary("/u/claude/versions/2.1.330 (deleted)") == "2.1.330"
    assert sr._version_of_binary("/usr/bin/node") is None
    assert sr.claude_code_of(-1) is None
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    target = tmp_path / "versions" / "2.1.400"
    target.parent.mkdir()
    target.write_text("#!/bin/sh\n")
    target.chmod(0o755)
    (bin_dir / "claude").symlink_to(target)
    monkeypatch.setenv("PATH", str(bin_dir))
    assert sr.installed_claude_code() == "2.1.400"
    (bin_dir / "claude").unlink()
    (bin_dir / "claude").write_text("#!/bin/sh\necho '2.1.401 (Claude Code)'\n")
    (bin_dir / "claude").chmod(0o755)
    assert sr.installed_claude_code() == "2.1.401"
