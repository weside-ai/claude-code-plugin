"""context_load.py against a scratch repo, home and Claude config dir: the counted parts from disk,
the rest from a transcript (sizes only), memory by size only, duplicates, the report and its delta."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import context_load as cl
import crew as crewlib
import pytest
import render_process

HERE = Path(__file__).parent
SHARED = "A sentence long enough to count, standing verbatim in two loaded files of the repo."
FROM_MEMORY = "A sentence the memory index and the instruction file share, long enough to count."
TRANSCRIPT = [
    {"type": "custom-title", "customTitle": "PROJ-1-build"},
    {
        "type": "attachment",
        "attachment": {
            "type": "hook_additional_context",
            "content": ["You are a worker: you execute one chunk"],
        },
    },
    {"type": "attachment", "attachment": {"type": "skill_listing", "content": "S" * 300}},
    {
        "type": "attachment",
        "attachment": {"type": "mcp_instructions_delta", "addedBlocks": ["M" * 40]},
    },
    {
        "type": "api-request-shape",
        "shape": {
            "system": [{"type": "text", "text": "SYSTEM-TEXT " * 10}],
            "tools": [{"name": "Read", "description": "TOOL-TEXT", "input_schema": {}}],
        },
    },
    {"type": "user", "message": {"content": "hi"}},
    {
        "type": "assistant",
        "message": {
            "usage": {
                "input_tokens": 10,
                "cache_creation_input_tokens": 2_000,
                "cache_read_input_tokens": 38_000,
                "output_tokens": 99,
            }
        },
    },
    {"type": "assistant", "message": {"usage": {"input_tokens": 5}}},
]


def world(tmp_path, monkeypatch, transcript=True):
    repo, home, cfg = tmp_path / "repo", tmp_path / "home", tmp_path / "cfg"
    (repo / ".weside" / "optimization").mkdir(parents=True)
    (repo / ".claude" / "rules").mkdir(parents=True)
    home.mkdir()
    shutil.copy(HERE / "fixtures" / "crew-v2-generic.json", repo / ".weside" / "crew.json")
    (repo / "AGENTS.md").write_text(f"# Repo\n\n{SHARED}\n\n{FROM_MEMORY}\n")
    (repo / ".claude" / "rules" / "a.md").write_text(f"# Rule\n\n{SHARED}\n")
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    project = cfg / "projects" / cl.project_slug(repo.resolve())
    (project / "memory").mkdir(parents=True)
    (project / "memory" / "MEMORY.md").write_text(f"MEMORY-TEXT\n{FROM_MEMORY}\n")
    if transcript:
        (project / "s1.jsonl").write_text("\n".join(json.dumps(e) for e in TRANSCRIPT) + "\n")
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(cfg))
    return repo, home


def run(repo, home, capsys, *extra):
    assert cl.main(["--from", str(repo), "--home", str(home), "--role", "worker", *extra]) == 0
    return capsys.readouterr()


def test_worker_table_sums_the_gate_count_and_transcript_sizes_without_memory(
    tmp_path, monkeypatch, capsys
):
    repo, home = world(tmp_path, monkeypatch)
    out = run(repo, home, capsys).out
    crew_path, crew = crewlib.find_and_load(repo)
    [total] = render_process.total_rows(crew_path, crew, "worker", home)
    memory = 0  # a worker starts with auto memory off
    shape = next(e for e in TRANSCRIPT if e["type"] == "api-request-shape")["shape"]
    system = len(shape["system"][0]["text"])
    tools = len(json.dumps(shape["tools"][0]))
    real = total.total + memory + system + tools + 300 + 40
    assert f"measured start: 40,010 tokens (estimated sum {cl.tokens(real):,})" in out
    assert (
        f"the budget gate counts {total.total:,} chars (≈ {cl.tokens(total.total):,} tokens)"
        f" of a measured start of 40,010 tokens ({cl.tokens(total.total) * 100 // 40_010} % counted)"
    ) in out
    assert "transcript: s1.jsonl" in out
    for text in ("MEMORY-TEXT", "SYSTEM-TEXT", "TOOL-TEXT", "SSSS"):
        assert text not in out, text


@pytest.mark.parametrize("context", [None, {}, {"auto_memory": "shared"}])
def test_a_worker_memory_row_is_always_off(tmp_path, monkeypatch, capsys, context):
    """Every worker starts with auto memory off: the row must not count MEMORY.md's size."""
    repo, home = world(tmp_path, monkeypatch)
    if context is not None:
        (repo / ".weside" / "config.json").write_text(
            json.dumps({"workers": {"context": context}})
        )
    out = run(repo, home, capsys).out
    [row] = [x for x in out.splitlines() if x.startswith("MEMORY.md ")]
    assert [c.strip() for c in row.split("  ") if c.strip()][1:3] == [cl.MEMORY_OFF, "0"], row
    assert out.rstrip().endswith(cl.FOOTER)


def test_without_a_transcript_the_parts_read_na_and_the_sum_is_a_floor(
    tmp_path, monkeypatch, capsys
):
    repo, home = world(tmp_path, monkeypatch, transcript=False)
    resumed = [{"type": "assistant", "message": {"usage": {"input_tokens": 1}}}, *TRANSCRIPT]
    project = tmp_path / "cfg" / "projects" / cl.project_slug(repo.resolve())
    (project / "resumed.jsonl").write_text("\n".join(json.dumps(e) for e in resumed) + "\n")
    out = run(repo, home, capsys).out
    assert f"transcript: {cl.NA}" in out and "the table sums ≥ " in out
    assert "measured start: n/a tokens" in out


def test_duplicates_quote_repo_files_and_never_the_memory_index(tmp_path, monkeypatch, capsys):
    repo, home = world(tmp_path, monkeypatch)
    out = run(repo, home, capsys).out
    [line] = [x for x in out.splitlines() if x.startswith("- ")]
    assert line == f'- "{SHARED[: cl.QUOTE]}" — AGENTS.md · .claude/rules/a.md'
    assert FROM_MEMORY[:30] not in out


def test_md_writes_the_report_and_the_next_run_shows_the_delta(
    tmp_path, monkeypatch, capsys, late_utc_clock
):
    repo, home = world(tmp_path, monkeypatch)
    (repo / ".weside" / "config.json").write_text(json.dumps({"time": {"zone": "Europe/Berlin"}}))
    run(repo, home, capsys, "--md")
    [report] = (repo / ".weside" / "optimization" / "reports").glob("context-*.md")
    assert report.name == "context-2026-11-22.md"  # the day in time.zone, not UTC's 21st
    report.rename(report.with_name("context-2000-01-01.md"))
    with (repo / "AGENTS.md").open("a") as fh:
        fh.write("x" * 10)
    out = run(repo, home, capsys).out
    [row] = [x for x in out.splitlines() if x.startswith("instructions AGENTS.md")]
    assert row.split()[-1] == "+10"


def test_a_repo_pointing_at_a_foreign_crew_measures_itself(tmp_path, monkeypatch, capsys):
    """Repo B's config points at repo A's crew file: B's master and worker are measured in B
    (its chain, rules, memory, transcripts), a member working in A is one line."""
    a, home = world(tmp_path, monkeypatch)
    b = tmp_path / "b"
    (b / ".weside").mkdir(parents=True)
    (b / ".claude" / "rules").mkdir(parents=True)
    (b / ".weside" / "config.json").write_text(json.dumps({"crew": "../repo/.weside/crew.json"}))
    (b / "AGENTS.md").write_text("# B\n\n" + "b" * 77 + "\n")
    (b / ".claude" / "rules" / "b.md").write_text("# B rule\n\n" + "r" * 33 + "\n")
    subprocess.run(["git", "init", "-q", str(b)], check=True)
    cfg = Path(cl.claude_home.config_dir())
    project = cfg / "projects" / cl.project_slug(b.resolve())
    (project / "memory").mkdir(parents=True)
    (project / "memory" / "MEMORY.md").write_text("B-MEMORY\n")
    (project / "b1.jsonl").write_text("\n".join(json.dumps(e) for e in TRANSCRIPT) + "\n")
    argv = ["--from", str(b), "--home", str(home), "--role", "worker", "--role", "product"]
    assert cl.main([*argv, "--md"]) == 0
    captured = capsys.readouterr()
    out = captured.out
    assert "| instructions AGENTS.md | disk | 83 |" in out  # B's own, not A's
    assert "| rules without paths (1) | disk | 44 |" in out
    assert "| MEMORY.md | off (worker settings) | 0 |" in out  # a worker loads none
    assert "transcript: b1.jsonl" in out
    assert "product Ada: works in repo, measured there" in out
    assert "no optimization store" in captured.err
    assert not (a / ".weside" / "optimization" / "reports").exists()
