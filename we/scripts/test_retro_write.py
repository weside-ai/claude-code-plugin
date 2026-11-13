"""retro_write.py: an inbox entry is created exclusively or gains evidence, never overwritten."""

from __future__ import annotations

import threading
from pathlib import Path

import pytest
import retro_write as rw

BODY = """---
key: gap--agents-md
pattern: gap
target: AGENTS.md
target_repo: this
action: add
confidence: Medium
source: retro
---

The proposed line.

## Evidence

- {line}
"""


def body(line):
    return BODY.format(line=line)


def test_a_new_key_is_created_and_a_second_writer_appends(tmp_path):
    out = rw.write(tmp_path, body("2026-11-13 retro | session a: first"), "2026-11-13")
    path = tmp_path / "2026-11-13-gap--agents-md.md"
    assert out == f"created {path}"
    out = rw.write(tmp_path, body("2026-11-14 retro | session b: second"), "2026-11-14")
    assert out == f"appended 1 evidence line(s) to {path}"
    assert not (tmp_path / "2026-11-14-gap--agents-md.md").exists()
    assert rw.evidence_lines(path.read_text()) == [
        "- 2026-11-13 retro | session a: first",
        "- 2026-11-14 retro | session b: second",
    ]
    assert "The proposed line." in path.read_text()


def test_a_known_line_is_not_appended_twice(tmp_path):
    rw.write(tmp_path, body("2026-11-13 retro | session a: first"), "2026-11-13")
    out = rw.write(tmp_path, body("2026-11-13 retro | session a: first"), "2026-11-13")
    assert out.startswith("appended 0 evidence line(s)")


def test_evidence_goes_under_its_section_not_after_a_later_one(tmp_path):
    path = tmp_path / "2026-11-01-gap--agents-md.md"
    path.write_text(body("old") + "\n## Note\n\nkept below\n")
    rw.write(tmp_path, body("new"), "2026-11-13")
    text = path.read_text()
    assert text.index("- new") < text.index("## Note") and text.endswith("kept below\n")


def test_parallel_writers_keep_every_line(tmp_path):
    """A dozen sessions of a broadcast retro wrote one key within a minute; the last `cat >`
    won. Red arm: with a plain overwrite only one evidence line survives."""
    lines = [f"2026-11-13 retro | session s{i}: fact {i}" for i in range(12)]
    threads = [
        threading.Thread(target=rw.write, args=(tmp_path, body(line), "2026-11-13"))
        for line in lines
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    [path] = list(tmp_path.glob("*.md"))
    assert sorted(rw.evidence_lines(path.read_text())) == sorted(f"- {x}" for x in lines)


def test_a_second_writer_between_create_and_write_keeps_its_line(tmp_path, monkeypatch):
    """Two writers of one key: the second runs while the first has opened its file and not yet
    written it. Red arm: an O_EXCL create leaves the name empty in that gap, the second appends to
    it, and the first then writes its body over the appended line."""
    real_fdopen, ran = rw.os.fdopen, []

    def between(fd, *args, **kwargs):
        if not ran:
            ran.append(None)  # the second writer's own open passes straight through
            ran[0] = rw.write(tmp_path, body("2026-11-13 retro | session b: second"), "2026-11-13")
        return real_fdopen(fd, *args, **kwargs)

    monkeypatch.setattr(rw.os, "fdopen", between)
    out = rw.write(tmp_path, body("2026-11-13 retro | session a: first"), "2026-11-13")
    monkeypatch.undo()
    path = tmp_path / "2026-11-13-gap--agents-md.md"
    assert ran == [f"created {path}"]
    assert out == f"appended 1 evidence line(s) to {path}"
    assert [p.name for p in tmp_path.iterdir()] == [path.name]
    assert rw.evidence_lines(path.read_text()) == [
        "- 2026-11-13 retro | session b: second",
        "- 2026-11-13 retro | session a: first",
    ]


@pytest.mark.parametrize(
    "text, reason",
    [
        ("no frontmatter\n\n## Evidence\n\n- x\n", "no frontmatter"),
        ("---\npattern: gap\n---\n\n## Evidence\n\n- x\n", "no `key:`"),
        ("---\nkey: gap--x\n---\n\nbody only\n", "no `- …` line under `## Evidence`"),
    ],
)
def test_a_body_without_key_or_evidence_is_refused(tmp_path, text, reason):
    f = tmp_path / "body.md"
    f.write_text(text)
    assert rw.main([str(tmp_path / "inbox"), str(f)]) == 2
    assert not (tmp_path / "inbox").exists() or not list((tmp_path / "inbox").iterdir())
    with pytest.raises(rw.WriteError, match=reason.replace("`", ".").replace("…", ".")):
        rw.write(tmp_path / "inbox", text, "2026-11-13")


def test_the_cli_prints_the_result(tmp_path, capsys):
    f = tmp_path / "body.md"
    f.write_text(body("x"))
    assert rw.main([str(tmp_path / "inbox"), str(f), "--date", "2026-11-13"]) == 0
    assert capsys.readouterr().out.strip() == (
        f"created {Path(tmp_path / 'inbox' / '2026-11-13-gap--agents-md.md')}"
    )
