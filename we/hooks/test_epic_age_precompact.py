"""epic_age_precompact.py: the stale-epic flag a master's compaction opens with."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import compact_on_start as cos
import epic_age_precompact as eap
from test_compact_on_start import MASTER, TODAY, UPDATES, Runner, hook, workspace


def test_precompact_flags_a_stale_epic_and_compact_consumes_the_flag(tmp_path):
    root = workspace(tmp_path, UPDATES)
    runner = Runner(root)
    flag = eap.flag(hook(root), MASTER, runner)
    assert flag == tmp_path / "state" / "epic-age" / "sid"
    text, _ = cos.render(hook(root), MASTER, runner)
    assert text.splitlines()[0].startswith("Epic update first: ")
    assert not flag.exists()
    again, _ = cos.render(hook(root), MASTER, runner)
    assert "Epic update first" not in again


def test_precompact_leaves_a_fresh_epic_and_a_non_master_alone(tmp_path):
    root = workspace(tmp_path, [f"{TODAY} — today"])
    assert eap.flag(hook(root), MASTER, Runner(root)) is None
    stale = workspace(tmp_path / "b", UPDATES)
    assert eap.flag(hook(stale), {}, Runner(stale)) is None
    assert eap.flag(hook(stale), {"WESIDE_COMPANION": "Ada"}, Runner(stale)) is None


def test_precompact_flags_a_plan_without_updates_log(tmp_path):
    root = workspace(tmp_path, None)
    assert eap.flag(hook(root), MASTER, Runner(root)) is not None
