"""session_tokens.py on fixture transcripts and fixture plans.

Run: `python3 -m pytest -q we/scripts/test_session_tokens.py`
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import session_tokens as st

SID = "fbae4d4e-1111-2222-3333-444455556666"
TEMPLATE = "claude --bg -n {name} --agent {agent} {brief}"
PLAN = "# Plan: X\n\n## Context\n\nText.\n\n## Documentation Impact\n\n- none\n"


def _assistant(mid: str, model: str = "model-a", **usage: int) -> str:
    return json.dumps(
        {"type": "assistant", "message": {"id": mid, "model": model, "usage": usage}}
    )


def _usage(i: int, o: int, r: int, w: int) -> dict:
    return {
        "input_tokens": i,
        "output_tokens": o,
        "cache_read_input_tokens": r,
        "cache_creation_input_tokens": w,
    }


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    (root / "docs" / "plans").mkdir(parents=True)
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    return root


def _config(repo: Path, worker_launch: str | None) -> None:
    (repo / ".weside").mkdir(exist_ok=True)
    cfg = {} if worker_launch is None else {"agents": {"worker_launch": worker_launch}}
    (repo / ".weside" / "config.json").write_text(json.dumps(cfg))


def _plan(repo: Path, text: str = PLAN) -> Path:
    plan = repo / "docs" / "plans" / "KEY-1-story.md"
    plan.write_text(text)
    return plan


def _transcript(config_dir: Path, lines: list[str], sub: str | None = None) -> None:
    project = config_dir / "projects" / "-some-project"
    if sub is None:
        path = project / f"{SID}.jsonl"
    else:
        path = project / SID / "subagents" / f"{sub}.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n")


def _env(config_dir: Path, sid: str | None = SID) -> dict:
    env = {"CLAUDE_CONFIG_DIR": str(config_dir)}
    if sid is not None:
        env["CLAUDE_CODE_SESSION_ID"] = sid
    return env


def _log(plan: Path) -> list[str]:
    text = plan.read_text()
    section = text.split("## Updates Log", 1)[1]
    return [row for row in section.splitlines() if row.startswith("- ")]


def test_own_session_counts_each_message_once_and_adds_subagents(repo, tmp_path):
    _config(repo, TEMPLATE)
    cfg = tmp_path / "cfg"
    _transcript(
        cfg,
        [
            json.dumps({"type": "user", "message": {"content": "hi"}}),
            _assistant("m1", **_usage(1, 10, 100, 1000)),
            _assistant("m1", **_usage(1, 10, 100, 1000)),  # streamed repeat
            _assistant("m2", model="model-b", **_usage(2, 20, 200, 2000)),
            "{not json",
        ],
    )
    _transcript(cfg, [_assistant("s1", **_usage(3, 30, 300, 3000))], sub="agent-x")
    plan = _plan(repo)

    line = st.run(plan, "refine", _env(cfg), today="2026-11-03")

    assert line == (
        "- 2026-11-03 refine tokens: in=6 out=60 cache_read=600 cache_write=6000"
        " models=model-a,model-b session=fbae4d4e skipped=1"
    )
    assert _log(plan) == [line]


def test_subagent_mode_writes_absent_never_zero(repo, tmp_path):
    for value in (None, "subagent"):
        _config(repo, value)
        cfg = tmp_path / "cfg"
        _transcript(cfg, [_assistant("m1", **_usage(1, 1, 1, 1))])
        plan = _plan(repo)
        line = st.run(plan, "refine", _env(cfg), today="2026-11-03")
        assert line == "- 2026-11-03 refine tokens: absent (subagent: no own session id)"
        assert "=0" not in plan.read_text()


def test_no_config_file_is_subagent(repo, tmp_path):
    plan = _plan(repo)
    line = st.run(plan, "refine", _env(tmp_path / "cfg"), today="2026-11-03")
    assert line.endswith("absent (subagent: no own session id)")


@pytest.mark.parametrize(
    "sid, reason",
    [(None, "no session id"), ("unknown-session", "no session transcript")],
)
def test_missing_transcript_is_absent(repo, tmp_path, sid, reason):
    _config(repo, TEMPLATE)
    plan = _plan(repo)
    line = st.run(plan, "refine", _env(tmp_path / "cfg", sid), today="2026-11-03")
    assert line == f"- 2026-11-03 refine tokens: absent ({reason})"


def test_transcript_without_usage_is_absent_not_zero(repo, tmp_path):
    _config(repo, TEMPLATE)
    cfg = tmp_path / "cfg"
    _transcript(cfg, ["{broken", json.dumps({"type": "user"})])
    plan = _plan(repo)
    line = st.run(plan, "refine", _env(cfg), today="2026-11-03")
    assert line.endswith("absent (no assistant usage in transcript, skipped=1)")


def test_invalid_worker_launch_is_absent_and_exits_zero(repo, tmp_path, monkeypatch):
    _config(repo, "claude {nope}")
    plan = _plan(repo)
    for key, value in _env(tmp_path / "cfg").items():
        monkeypatch.setenv(key, value)
    assert st.main(["--plan", str(plan), "--step", "refine"]) == 0
    (line,) = _log(plan)
    assert "refine tokens: absent (worker_launch unreadable:" in line
    assert line.count(")") == 1  # the reader cuts the reason at the first `)`


def test_section_appended_at_end_then_second_line_after_first(repo, tmp_path):
    _config(repo, TEMPLATE)
    plan = _plan(repo)
    env = _env(tmp_path / "cfg", None)
    first = st.run(plan, "refine", env, today="2026-11-03")
    second = st.run(plan, "refine", env, today="2026-11-04")
    text = plan.read_text()
    assert text.endswith(f"## Updates Log\n\n{first}\n{second}\n")
    assert text.index("## Documentation Impact") < text.index("## Updates Log")


def test_existing_section_in_the_middle_keeps_the_next_header(repo, tmp_path):
    _config(repo, TEMPLATE)
    plan = _plan(
        repo,
        "# Plan\n\n## Updates Log\n\nStarted.\n\n## Out of scope\n\n- x\n",
    )
    line = st.run(plan, "refine", _env(tmp_path / "cfg", None), today="2026-11-03")
    assert plan.read_text() == (
        f"# Plan\n\n## Updates Log\n\nStarted.\n\n{line}\n\n## Out of scope\n\n- x\n"
    )


def test_line_parses_with_the_documented_grammar(repo, tmp_path):
    """The grammar of story-plan.md § Updates Log lines, as a reader would apply it."""
    grammar = re.compile(
        r"^- \d{4}-\d{2}-\d{2} [a-z][a-z0-9_-]* tokens: "
        r"(absent \([^)]+\)|in=\d+ out=\d+ cache_read=\d+ cache_write=\d+( [a-z_]+=\S+)*)$"
    )
    _config(repo, TEMPLATE)
    cfg = tmp_path / "cfg"
    _transcript(cfg, [_assistant("m1", **_usage(1, 2, 3, 4))])
    measured = st.run(_plan(repo), "refine", _env(cfg), today="2026-11-03")
    absent = st.run(_plan(repo), "refine", _env(cfg, None), today="2026-11-03")
    assert grammar.match(measured), measured
    assert grammar.match(absent), absent
