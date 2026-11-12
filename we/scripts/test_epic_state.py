"""epic_state.py: plan resolution, the Updates Log, story keys, the PR query and staleness."""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import epic_state as es
import pytest


def plans(root: Path, files: dict[str, str]) -> Path:
    (root / "docs" / "plans").mkdir(parents=True, exist_ok=True)
    for name, text in files.items():
        (root / "docs" / "plans" / name).write_text(text)
    return root


EPIC = "---\nticket: PROJ-7\nlinked_epics: [PROJ-70, PROJ-71]\nstatus: in-progress\n---\n"


def test_frontmatter_reads_scalars_and_lists():
    assert es.frontmatter(EPIC) == {
        "ticket": "PROJ-7",
        "linked_epics": ["PROJ-70", "PROJ-71"],
        "status": "in-progress",
    }
    assert es.frontmatter("# no frontmatter") == {}


def test_resolve_by_name_number_epic_field_and_linked_epics(tmp_path):
    root = plans(tmp_path, {"a-epic.md": EPIC, "b-epic.md": "---\nticket: PROJ-8\n---\n"})
    a = (root / "docs/plans/a-epic.md").resolve()
    assert es.resolve({"name": "build-7"}, [root]) == a
    assert es.resolve({"name": "x", "epic": "PROJ-71"}, [root]) == a
    assert es.resolve({"name": "helper-70"}, [root, root]) == a
    with pytest.raises(es.EpicError, match="set `epic` on your board line"):
        es.resolve({"name": "helper"}, [root])
    with pytest.raises(es.EpicError):
        es.resolve({"name": "x-9"}, [root])


def test_two_plans_for_one_number_is_not_found(tmp_path):
    root = plans(tmp_path, {"a-epic.md": EPIC, "c-epic.md": "---\nticket: OTHER-7\n---\n"})
    with pytest.raises(es.EpicError):
        es.resolve({"name": "m-7"}, [root])


def test_updates_log_sorts_both_directions_and_joins_wrapped_lines():
    text = (
        "## Scope\n\n- 2020-01-01 — not a log entry\n\n## Updates Log\n\n"
        "- 2026-01-03 — c\n- 2026-01-01 — a,\n  wrapped\n- **2026-01-02** — b\n\n## After\n"
        "- 2026-01-09 — outside\n"
    )
    assert es.updates_log(text) == [
        ("2026-01-01", "a, wrapped"),
        ("2026-01-02", "b"),
        ("2026-01-03", "c"),
    ]
    assert es.updates_log("## Scope\n") == []


def test_story_keys_of_the_epic(tmp_path):
    root = plans(
        tmp_path,
        {
            "PROJ-8-story.md": "---\nstory: PROJ-8\nepic: PROJ-7\n---\n",
            "PROJ-9-story.md": "---\nepic: PROJ-7\n---\n",
            "PROJ-10-story.md": "---\nepic: PROJ-1\n---\n",
        },
    )
    assert sorted(es.story_keys(root, "PROJ-7")) == ["PROJ-8", "PROJ-9"]


def test_the_search_query_is_cut_at_its_cap():
    keys = [f"PROJ-{i}" for i in range(100)]
    query = es.search_query(keys)
    assert len(query) <= es.QUERY_CAP and query.startswith('"PROJ-0" OR "PROJ-1"')
    assert query.split(" OR ")[-1].endswith('"')


def test_staleness_is_by_date_in_the_crew_zone():
    # 2026-03-10 00:30 in Berlin is still 2026-03-09 in UTC
    now = dt.datetime(2026, 3, 9, 23, 30, tzinfo=dt.timezone.utc)
    assert not es.is_stale("2026-03-09", "Europe/Berlin", now)
    assert es.is_stale("2026-03-08", "Europe/Berlin", now)
    assert not es.is_stale("2026-03-08", "UTC", now)
    assert es.is_stale(None, "UTC", now)
    assert not es.is_stale("2026-03-08", "No/Such_Zone", now)


LINED = (
    "---\nticket: PROJ-7\nline: [PROJ-71, PROJ-72]\nline_goal: exports above 20 %\n"
    "created: 2026-01-01\nstatus: approved\n---\n\n# Epic\n\n## Scope\n\n- [ ] not an extension\n\n"
    "## Extensions\n\n- [ ] PROJ-75 PDF export\n- [x] header text → dropped\n- [ ] rounding\n"
)


def test_finish_line_counts_done_keys_open_extensions_and_age():
    line = es.finish_line(LINED, {"PROJ-71": "done", "PROJ-72": "in_review"}, dt.date(2026, 1, 10))
    assert line == {
        "keys": ["PROJ-71", "PROJ-72"],
        "done": ["PROJ-71"],
        "open": ["PROJ-72"],
        "extensions": 2,
        "age": 9,
        "reached": False,
    }
    assert es.line_summary(line) == "1/2 line done · 2 extensions open · 9 d old"


def test_the_line_is_reached_when_every_key_is_done():
    states = {"PROJ-71": "done", "PROJ-72": "done"}
    line = es.finish_line(LINED, states, dt.date(2026, 1, 10))
    assert line["reached"] and line["open"] == []
    assert es.line_summary(line).endswith(" · finish line reached")


def test_an_epic_without_line_has_no_finish_line():
    assert es.finish_line(EPIC, {}, dt.date(2026, 1, 10)) is None


def test_the_cli_reads_the_board_transitions(tmp_path, capsys):
    board = tmp_path / "board.json"
    board.write_text("{}")
    (tmp_path / "board-transitions.jsonl").write_text(
        '{"key": "PROJ-71", "to": "in_review"}\n{"key": "PROJ-71", "to": "done"}\n'
    )
    epic = tmp_path / "PROJ-7-epic.md"
    epic.write_text(LINED)
    assert es.main(["line", str(epic), "--board", str(board)]) == 0
    out = capsys.readouterr().out.splitlines()
    assert out[0].startswith("1/2 line done · 2 extensions open · ")
    assert out[1] == "open on the line: PROJ-72"
    (tmp_path / "plain-epic.md").write_text(EPIC)
    assert es.main(["line", str(tmp_path / "plain-epic.md"), "--board", str(board)]) == 2
