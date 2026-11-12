"""statusline.js rate-limit recording and the cswap feed (WE_CSWAP_FEED_ACCOUNTS), against a stub `cswap`.

The format test runs the real `cswap import-usage` in a throwaway HOME when cswap is installed.
"""

import json
import os
import shutil
import subprocess
import time
from pathlib import Path

import pytest
from node_test_procs import real_node, reap

SCRIPT = Path(__file__).parent / "statusline.js"
EMAIL = "setup-token-1@example.test"
OTHER = "setup-token-2@example.test"

NODE = real_node()

pytestmark = pytest.mark.skipif(NODE is None, reason="statusline.js needs node")


@pytest.fixture(autouse=True)
def _no_process_outlives_its_test(tmp_path):
    """Every process a test started (detached refreshes too) ends with it: 0 left, else red."""
    yield
    left = reap(tmp_path)
    assert left == 0, f"{left} processes with HOME under {tmp_path} outlived the test"


def env_for(home, accounts=EMAIL, stub_dir=None):
    env = {k: v for k, v in os.environ.items() if k not in ("CLAUDE_CONFIG_DIR", "XDG_DATA_HOME")}
    env["HOME"] = str(home)
    env["WE_CSWAP_FEED_ACCOUNTS"] = accounts
    if stub_dir:
        env["PATH"] = f"{stub_dir}{os.pathsep}{os.environ['PATH']}"
    return env


def stub_cswap(tmp_path):
    """A `cswap` that logs its argv and stdin, so no test reaches the real store."""
    stub_dir = tmp_path / "bin"
    stub_dir.mkdir()
    stub = stub_dir / "cswap"
    log = tmp_path / "cswap.log"
    stub.write_text(f'#!/bin/sh\necho "$@" > {log}.args\ncat > {log}\n')
    stub.chmod(0o755)
    return stub_dir, log


def write_rl(path, five=None, seven=None, email=EMAIL):
    entry = {"email": email, "organizationUuid": "", "observedAt": time.time() - 20_000}
    entry["fiveHour"] = five
    entry["sevenDay"] = seven
    path.write_text(json.dumps({"schemaVersion": 1, "accounts": {"k": entry}}))


def bind_session(home, session_id, email):
    """The binding the first render of a session writes: the account it started under."""
    folder = home / ".claude" / "we-rl-sessions"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"{session_id}.json").write_text(
        json.dumps({"email": email, "organizationUuid": ""})
    )


def set_active(home, email):
    (home / ".claude.json").write_text(
        json.dumps({"oauthAccount": {"emailAddress": email, "organizationUuid": None}})
    )


def render(home, session_id, rate_limits, stub_dir=None):
    subprocess.run(
        [NODE, str(SCRIPT)],
        input=json.dumps({"session_id": session_id, "rate_limits": rate_limits}),
        env=env_for(home, accounts=f"{EMAIL},{OTHER}", stub_dir=stub_dir),
        text=True,
        timeout=20,
        check=True,
        capture_output=True,
    )


def dry_run(tmp_path, rl_file, accounts=EMAIL):
    out = subprocess.run(
        [NODE, str(SCRIPT), "--feed-cswap", "--dry-run", "--file", str(rl_file)],
        env=env_for(tmp_path, accounts),
        capture_output=True,
        text=True,
        timeout=20,
        check=True,
    ).stdout
    return json.loads(out) if out.strip() else None


def test_reset_passed_reports_zero_without_reset_and_keeps_the_open_window(tmp_path):
    now = time.time()
    rl = tmp_path / "rl.json"
    write_rl(
        rl, five={"pct": 42, "resetsAt": now - 60}, seven={"pct": 61, "resetsAt": now + 86_400}
    )
    doc = dry_run(tmp_path, rl)
    row = doc["accounts"][0]
    assert doc["schemaVersion"] == 1
    assert (
        row["usageStatus"] == "ok"
        and row["usageAgeSeconds"] == 0
        and row["organizationUuid"] == ""
    )
    assert row["usage"]["fiveHour"] == {"pct": 0}
    assert row["usage"]["sevenDay"]["pct"] == 61
    assert row["usage"]["sevenDay"]["resetsAt"].endswith("Z")


def test_weekly_reset_passed_reports_zero_too(tmp_path):
    now = time.time()
    rl = tmp_path / "rl.json"
    write_rl(rl, five={"pct": 10, "resetsAt": now - 7_200}, seven={"pct": 95, "resetsAt": now - 1})
    usage = dry_run(tmp_path, rl)["accounts"][0]["usage"]
    assert usage == {"fiveHour": {"pct": 0}, "sevenDay": {"pct": 0}}


def test_no_file_does_nothing(tmp_path):
    stub_dir, log = stub_cswap(tmp_path)
    (tmp_path / ".claude").mkdir()
    subprocess.run(
        [NODE, str(SCRIPT), "--feed-cswap", "--file", str(tmp_path / "missing.json")],
        env=env_for(tmp_path, stub_dir=stub_dir),
        timeout=20,
        check=True,
    )
    assert not log.exists()
    assert dry_run(tmp_path, tmp_path / "missing.json") is None


def test_unlisted_account_is_not_fed(tmp_path):
    now = time.time()
    rl = tmp_path / "rl.json"
    write_rl(rl, five={"pct": 5, "resetsAt": now + 600}, email="other@example.test")
    assert dry_run(tmp_path, rl) is None


def test_record_merges_the_reading_and_feeds_cswap_once(tmp_path):
    stub_dir, log = stub_cswap(tmp_path)
    (tmp_path / ".claude").mkdir()
    # Only oauthAccount is read; a real .claude.json carries no credential either.
    (tmp_path / ".claude.json").write_text(
        json.dumps({"oauthAccount": {"emailAddress": EMAIL, "organizationUuid": None}})
    )
    reset = int(time.time()) + 3_600
    rate_limits = {
        "five_hour": {"used_percentage": 37.5, "resets_at": reset},
        "seven_day": {"used_percentage": 70, "resets_at": reset + 86_400},
    }
    bind_session(tmp_path, "s1", EMAIL)
    run = [
        NODE,
        str(SCRIPT),
        "--record-rate-limits",
        str(tmp_path / ".claude.json"),
        json.dumps(rate_limits),
        "s1",
    ]
    subprocess.run(run, env=env_for(tmp_path, stub_dir=stub_dir), timeout=20, check=True)

    stored = json.loads((tmp_path / ".claude" / ".we-rate-limits.json").read_text())
    (entry,) = stored["accounts"].values()
    assert entry["email"] == EMAIL and entry["organizationUuid"] == ""
    assert entry["fiveHour"] == {"pct": 37.5, "resetsAt": reset}
    assert log.with_suffix(".log.args").read_text().split() == [
        "import-usage",
        "-",
        "--hold",
        "180",
    ]
    fed = json.loads(log.read_text())
    assert fed["accounts"][0]["usage"]["fiveHour"]["pct"] == 37.5

    # A second session within the minute records but does not feed again.
    log.unlink()
    subprocess.run(run, env=env_for(tmp_path, stub_dir=stub_dir), timeout=20, check=True)
    assert not log.exists()


def test_render_without_the_opt_in_spawns_nothing(tmp_path):
    (tmp_path / ".claude").mkdir()
    payload = json.dumps(
        {"session_id": "s1", "rate_limits": {"five_hour": {"used_percentage": 1, "resets_at": 1}}}
    )
    env = env_for(tmp_path, accounts="")
    subprocess.run(
        [NODE, str(SCRIPT)],
        input=payload,
        env=env,
        text=True,
        timeout=20,
        check=True,
        capture_output=True,
    )
    assert not list((tmp_path / ".claude").glob(".we-rate-limits*"))


@pytest.mark.skipif(not shutil.which("cswap"), reason="format probe needs claude-swap")
def test_document_is_accepted_by_cswap_import_usage(tmp_path):
    """Real `cswap import-usage` against a throwaway store holding one fake account."""
    home = tmp_path / "home"
    store = home / ".local" / "share" / "claude-swap"
    store.mkdir(parents=True)
    (store / "sequence.json").write_text(
        json.dumps(
            {
                "accounts": {
                    "1": {
                        "email": EMAIL,
                        "organizationUuid": "",
                        "organizationName": "",
                        "uuid": "00000000-0000-0000-0000-000000000001",
                        "added": "2026-10-31T00:00:00Z",
                    }
                },
                "activeAccountNumber": 1,
                "sequence": [1],
                "lastUpdated": "2026-10-31T00:00:00Z",
            }
        )
    )
    now = time.time()
    rl = tmp_path / "rl.json"
    write_rl(
        rl, five={"pct": 42, "resetsAt": now - 60}, seven={"pct": 61, "resetsAt": now + 86_400}
    )
    doc = tmp_path / "doc.json"
    doc.write_text(json.dumps(dry_run(tmp_path, rl)))
    env = env_for(home)
    out = subprocess.run(
        ["cswap", "import-usage", str(doc), "--hold", "180"],
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert out.returncode == 0, out.stderr
    assert "1 adopted" in out.stderr
    row = json.loads((store / "cache" / "usage.json").read_text())["accounts"]["1"]
    assert row["lastGood"]["five_hour"] == {"pct": 0.0}
    assert row["lastGood"]["seven_day"]["pct"] == 61.0


def test_render_without_a_reading_leaves_the_slot_free(tmp_path):
    (tmp_path / ".claude").mkdir()
    payload = json.dumps({"session_id": "s1"})
    subprocess.run(
        [NODE, str(SCRIPT)],
        input=payload,
        env=env_for(tmp_path),
        text=True,
        timeout=20,
        check=True,
        capture_output=True,
    )
    assert not list((tmp_path / ".claude").glob(".we-rate-limits*"))


def wait_for(predicate, timeout=10.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(0.05)
    return predicate()


def binding_of(path):
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return {}


def test_a_switch_after_session_start_records_nothing_for_the_new_account(tmp_path):
    """Session starts under A, cswap activates B: its readings never land on B."""
    stub_dir, log = stub_cswap(tmp_path)
    (tmp_path / ".claude").mkdir()
    rl_file = tmp_path / ".claude" / ".we-rate-limits.json"
    binding = tmp_path / ".claude" / "we-rl-sessions" / "sA.json"
    reset = int(time.time()) + 3_600
    reading = {"five_hour": {"used_percentage": 88, "resets_at": reset}}

    set_active(tmp_path, EMAIL)
    render(tmp_path, "sA", {}, stub_dir)  # first render, no reading yet: binds A

    set_active(tmp_path, OTHER)
    render(tmp_path, "sA", reading, stub_dir)
    assert wait_for(lambda: rl_file.exists() or "foreignUntil" in binding_of(binding))
    assert not rl_file.exists(), "a reading of the session under A landed on B"
    assert not log.exists()
    # The slot went back: a session that runs under B records in the same minute.
    render(tmp_path, "sB", {}, stub_dir)
    render(tmp_path, "sB", {"five_hour": {"used_percentage": 3, "resets_at": reset}}, stub_dir)
    assert wait_for(rl_file.exists)
    (entry,) = json.loads(rl_file.read_text())["accounts"].values()
    assert entry["email"] == OTHER and entry["fiveHour"]["pct"] == 3


def test_record_without_a_bound_session_records_nothing(tmp_path):
    (tmp_path / ".claude").mkdir()
    set_active(tmp_path, EMAIL)
    rate_limits = {"five_hour": {"used_percentage": 5, "resets_at": int(time.time()) + 600}}
    subprocess.run(
        [
            NODE,
            str(SCRIPT),
            "--record-rate-limits",
            str(tmp_path / ".claude.json"),
            json.dumps(rate_limits),
            "unbound",
        ],
        env=env_for(tmp_path),
        timeout=20,
        check=True,
    )
    assert not (tmp_path / ".claude" / ".we-rate-limits.json").exists()


def test_a_resumed_session_binds_the_account_its_new_process_runs_under(tmp_path):
    """`--resume` after a switch keeps the session id but runs under B: its readings go to B."""
    stub_dir, _log = stub_cswap(tmp_path)
    (tmp_path / ".claude").mkdir()
    rl_file = tmp_path / ".claude" / ".we-rate-limits.json"
    folder = tmp_path / ".claude" / "we-rl-sessions"
    folder.mkdir()
    # The binding an earlier Claude Code process left under A.
    (folder / "sR.json").write_text(
        json.dumps({"email": EMAIL, "organizationUuid": "", "proc": "1:0"})
    )
    set_active(tmp_path, OTHER)
    reset = int(time.time()) + 3_600
    render(tmp_path, "sR", {"five_hour": {"used_percentage": 9, "resets_at": reset}}, stub_dir)
    assert wait_for(rl_file.exists)
    (entry,) = json.loads(rl_file.read_text())["accounts"].values()
    assert entry["email"] == OTHER
    assert json.loads((folder / "sR.json").read_text())["email"] == OTHER
