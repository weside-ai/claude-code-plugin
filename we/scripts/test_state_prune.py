"""state_prune.prune: stale files go, fresh ones stay, one sweep a day."""

import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "hooks"))
import state_prune
import subagent_timing

DAY = 86_400


def _file(folder: Path, name: str, age_days: float, now: float) -> Path:
    path = folder / name
    path.write_text("x")
    os.utime(path, (now - age_days * DAY, now - age_days * DAY))
    return path


def test_stale_files_go_and_fresh_ones_stay(tmp_path):
    now = 2_000_000_000.0
    old = _file(tmp_path, "a.jsonl", 46, now)
    kept = _file(tmp_path, "d.jsonl", 40, now)  # inside the audit span plus margin
    fresh = _file(tmp_path, "b.jsonl", 2, now)
    other = _file(tmp_path, "c.txt", 99, now)
    assert state_prune.prune(tmp_path, "*.jsonl", now=now) == 1
    assert not old.exists() and fresh.exists() and other.exists() and kept.exists()


def test_one_sweep_a_day(tmp_path):
    now = 2_000_000_000.0
    state_prune.prune(tmp_path, "*.jsonl", now=now)
    os.utime(tmp_path / state_prune.STAMP, (now, now))
    late = _file(tmp_path, "a.jsonl", 50, now)
    assert state_prune.prune(tmp_path, "*.jsonl", now=now + 3600) == 0
    assert late.exists()
    assert state_prune.prune(tmp_path, "*.jsonl", now=now + DAY + 1) == 1


def test_a_missing_folder_is_no_error(tmp_path):
    assert state_prune.prune(tmp_path / "absent", "*.json") == 0


def test_the_timing_hook_ages_out_old_session_files(tmp_path):
    folder = tmp_path / ".claude" / "we-timing"
    folder.mkdir(parents=True)
    old = _file(folder, "gone.jsonl", 60, time.time())
    subagent_timing.record({"session_id": "s1", "hook_event_name": "SubagentStart"}, tmp_path)
    assert not old.exists() and (folder / "s1.jsonl").exists()
