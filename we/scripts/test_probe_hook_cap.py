"""probe-hook-cap.py: the committed fixture is the probe's output, AUTHORING.md states it, and the
crew process gate sits below every size the probe saw arrive whole."""

from __future__ import annotations

import importlib.util
import json
import re
from pathlib import Path

import render_process

HERE = Path(__file__).resolve().parent
FIXTURE = json.loads((HERE / "fixtures" / "hook-cap.json").read_text())
AUTHORING = (HERE.parent / "AUTHORING.md").read_text()
_spec = importlib.util.spec_from_file_location("probe_hook_cap", HERE / "probe-hook-cap.py")
probe = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(probe)


def test_the_fixture_replays_through_the_probe_summary():
    assert FIXTURE["cap"] == probe.summary(FIXTURE["cases"], "context")
    assert FIXTURE["cap_plain"] == probe.summary(FIXTURE["cases"], "plain")
    ids = [c["id"] for c in FIXTURE["cases"]]
    assert ids == [case_id for case_id, _, _ in probe.CASES]
    for case in FIXTURE["cases"]:
        for hook in case["hooks"]:
            assert hook["whole"] == (hook["start"] and hook["end"])


def test_authoring_states_the_fixture():
    row = re.search(
        r"SessionStart hook output \(Claude Code ([\d.]+), `claude -p`, probed (\d{4}-\d\d-\d\d)"
        r"[^)]*\): `additionalContext`\s+arrived whole up to ([\d,]+) chars, judged per (\w+)",
        AUTHORING,
    )
    assert row, "AUTHORING.md § Measured facts lacks the hook cap row"
    version, recorded, whole, per = row.groups()
    assert version == FIXTURE["claude_code"] and recorded == FIXTURE["recorded"]
    assert int(whole.replace(",", "")) == FIXTURE["cap"]["whole_max"]
    assert per == FIXTURE["cap"]["per"]
    cut = FIXTURE["cap"]["cut_min"]
    assert ("no cut found" in AUTHORING) == (cut is None)
    assert f"gated at {render_process.BUDGET:,} chars" in AUTHORING


def test_the_gate_is_below_the_recorded_cap():
    cap = FIXTURE["cap"]
    assert cap["whole_max"] >= render_process.BUDGET
    assert cap["cut_min"] is None or cap["cut_min"] > render_process.BUDGET


def test_payload_and_classify():
    text = probe.payload(10_000, "START-00000001", "END-00000002")
    assert len(text) == 10_000
    assert text.startswith("START-00000001\n") and text.endswith("\nEND-00000002")
    cut = probe.classify(10_000, "S", "E", {"S"})
    assert cut == {"chars": 10_000, "start": True, "end": False, "whole": False}
    cases = [
        {"id": "a", "form": "context", "hooks": [probe.classify(9_000, "S", "E", {"S", "E"})]},
        {"id": "b", "form": "context", "hooks": [cut]},
        {"id": "c", "form": "context", "hooks": [cut, cut]},
    ]
    assert probe.summary(cases) == {"whole_max": 9_000, "cut_min": 10_000, "per": "event"}
