"""zentrale.py: the gh cache through a fake `gh` on PATH, the gaps, the schemas, read-only, fast."""

from __future__ import annotations

import functools
import hashlib
import json
import os
import subprocess
import sys
from datetime import timedelta
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))
import accounts  # noqa: E402
import ci_state  # noqa: E402
import gh_source  # noqa: E402
import open_ends  # noqa: E402
import zentrale  # noqa: E402
from test_open_ends import UNTIL, ctx, make_board, pr, question  # noqa: E402

FAKE_GH = r"""#!/usr/bin/env python3
import json, os, sys
d = os.environ["FAKE_GH_DIR"]
with open(os.path.join(d, "calls"), "a") as fh:
    fh.write(" ".join(sys.argv[1:]) + "\n")
if open(os.path.join(d, "mode")).read().strip() == "rate":
    sys.stderr.write("API rate limit exceeded\n")
    sys.exit(1)
body = json.loads(sys.stdin.read() or "{}")
name = "list" if "pullRequests(" in body.get("query", "") else "states"
print(open(os.path.join(d, name + ".json")).read())
"""


@pytest.fixture
def world(tmp_path, monkeypatch):
    """A crew repo with a stamped board, a fake gh and an empty state dir."""
    repo = tmp_path / "repo"
    (repo / ".weside").mkdir(parents=True)
    state = tmp_path / "state"
    state.mkdir()
    crew = {
        "version": 2,
        "roles": {"coordinator": "coord"},
        "members": {"coord": {"name": "Coord"}},
    }
    (repo / ".weside" / "crew.json").write_text(json.dumps(crew))
    monkeypatch.setenv("WE_STATE_DIR", str(state))
    make_board(state, owner_queue=[question("Q4", 50, key_title="tit\x1b[31mle\x07")])
    gh = tmp_path / "gh-bin"
    gh.mkdir()
    (gh / "gh").write_text(FAKE_GH)
    (gh / "gh").chmod(0o755)
    (gh / "mode").write_text("ok")
    one = pr(22, [ctx("test", conclusion="FAILURE", done="2026-04-01T11:30:00Z")])
    (gh / "list.json").write_text(
        json.dumps(
            {
                "data": {
                    "repository": {
                        "defaultBranchRef": {
                            "name": "main",
                            "target": {
                                "oid": "d" * 40,
                                "statusCheckRollup": {
                                    "state": "SUCCESS",
                                    "contexts": {"nodes": []},
                                },
                            },
                        },
                        "pullRequests": {"nodes": [{"number": 22}]},
                    }
                }
            }
        )
    )
    (gh / "states.json").write_text(json.dumps({"data": {"repository": {"pr22": one}}}))
    monkeypatch.setenv("FAKE_GH_DIR", str(gh))
    monkeypatch.setenv("PATH", f"{gh}{os.pathsep}{os.environ['PATH']}")
    return {"repo": repo, "state": state, "gh": gh, "cache": tmp_path / "cache"}


# build binds `ci_source.CACHE` as its default at import: a CLI test hands its own cache in
BUILD = zentrale.build


def zbuild(w, until=UNTIL, **kw):
    kw.setdefault("cswap", str(w["gh"] / "no-cswap"))
    return zentrale.build(
        until=until,
        cwd=w["repo"],
        cache=w["cache"],
        agents=[],
        repos=["acme/app"],
        gh_reader=lambda *_a: ["test"],
        **kw,
    )


def gh_calls(w) -> int:
    path = w["gh"] / "calls"
    return len(path.read_text().splitlines()) if path.exists() else 0


# --- AC 9 ------------------------------------------------------------------------------------


def test_cache_and_unread_sources(world):
    first = zbuild(world)
    asked = gh_calls(world)
    assert asked == 2  # the PR list, then the PR states
    assert [r["item"] for r in first["sections"]["red"]] == ["acme/app#22"]
    (world["gh"] / "mode").write_text("rate")
    second = zbuild(world, UNTIL + timedelta(seconds=20))
    assert gh_calls(world) == asked  # inside the TTL GitHub is not asked
    assert second["sources"]["github acme/app"] == first["sources"]["github acme/app"]
    assert first["sources"]["github acme/app"]["fetched_at"]
    assert (world["cache"].stat().st_mode & 0o777) == 0o700
    third = zbuild(world, UNTIL + timedelta(seconds=gh_source.TTL_S + 5))
    assert "PRs acme/app: not read (gh: API rate limit exceeded)" in third["gaps"]
    assert third["sources"]["github acme/app"]["gap"] == "gh: API rate limit exceeded"
    assert [r["item"] for r in third["sections"]["owner"]] == ["Q4"]  # the board sections stay
    for name in ("board", "github acme/app", "main", "sessions", "accounts"):
        src = third["sources"][name]
        assert src["fetched_at"] or src["gap"], name


def test_cli_exits_zero_on_unread_sources(world, monkeypatch, capsys):
    (world["gh"] / "mode").write_text("rate")
    monkeypatch.chdir(world["repo"])
    monkeypatch.setattr(zentrale.worker_launch, "sessions", list)
    monkeypatch.setattr(gh_source, "repos_of", lambda *_a: ["acme/app"])
    monkeypatch.setattr(zentrale, "build", functools.partial(BUILD, cache=world["cache"]))
    assert zentrale.main(["--json", "--until", "2026-04-01T12:00:00Z"]) == 0
    doc = json.loads(capsys.readouterr().out)
    assert any(g.startswith("PRs acme/app: not read") for g in doc["gaps"])


# --- flow.repos ---------------------------------------------------------------------------------

FAKE_GH_BY_REPO = r"""#!/usr/bin/env python3
import json, os, sys
d = os.environ["FAKE_GH_DIR"]
body = json.loads(sys.stdin.read() or "{}")
name = body.get("variables", {}).get("name", "")
with open(os.path.join(d, "calls"), "a") as fh:
    fh.write(name + "\n")
kind = "list" if "pullRequests(" in body.get("query", "") else "states"
path = os.path.join(d, name + "." + kind + ".json")
empty = {"list": {"data": {"repository": {"pullRequests": {"nodes": []}}}},
         "states": {"data": {"repository": {}}}}
print(open(path).read() if os.path.exists(path) else json.dumps(empty[kind]))
"""


def git_repo(path: Path, origin: str) -> None:
    path.mkdir(parents=True, exist_ok=True)
    for args in (["init", "-q"], ["remote", "add", "origin", origin]):
        subprocess.run(["git", "-C", str(path), *args], check=True)


@pytest.fixture
def crew_repos(world):
    """The world's crew repo with origin acme/app; the fake gh has PR #7 only in acme/infra."""
    git_repo(world["repo"], "https://github.com/acme/app.git")
    gh = world["gh"]
    (gh / "gh").write_text(FAKE_GH_BY_REPO)
    seven = pr(7, [], body="Story: ABC-7\n\nuser merge: secrets\n")
    (gh / "infra.list.json").write_text(
        json.dumps({"data": {"repository": {"pullRequests": {"nodes": [{"number": 7}]}}}})
    )
    (gh / "infra.states.json").write_text(json.dumps({"data": {"repository": {"pr7": seven}}}))
    return world


def write_crew(w, **flow) -> None:
    crew = {
        "version": 2,
        "roles": {"coordinator": "coord"},
        "members": {"coord": {"name": "Coord"}},
        **({"flow": flow} if flow else {}),
    }
    (w["repo"] / ".weside" / "crew.json").write_text(json.dumps(crew))


def zentrale_cli(w, monkeypatch, capsys, cache: str) -> dict:
    monkeypatch.chdir(w["repo"])
    monkeypatch.setattr(zentrale.worker_launch, "sessions", list)
    monkeypatch.setattr(zentrale, "build", functools.partial(BUILD, cache=w["cache"] / cache))
    monkeypatch.setattr(gh_source.fr, "required_checks", lambda *_a: [])
    monkeypatch.setattr(accounts, "read", lambda *_a: {"state": "ok", "accounts": []})
    assert zentrale.main(["--json", "--until", "2026-04-01T12:00:00Z"]) == 0
    return json.loads(capsys.readouterr().out)


def test_flow_repos_feed_the_owner_section(crew_repos, monkeypatch, capsys):
    """AC 1: the real `repos_of` reads `flow.repos`; without the key acme/infra is never asked."""
    write_crew(crew_repos, repos=["acme/infra"])
    named = zentrale_cli(crew_repos, monkeypatch, capsys, "with")
    assert "acme/infra#7" in [r["item"] for r in named["sections"]["owner"]]
    assert "github acme/infra" in named["sources"]
    write_crew(crew_repos)
    (crew_repos["gh"] / "calls").unlink()
    plain = zentrale_cli(crew_repos, monkeypatch, capsys, "without")
    assert "acme/infra#7" not in [r["item"] for r in plain["sections"]["owner"]]
    assert "github acme/infra" not in plain["sources"]
    assert (crew_repos["gh"] / "calls").read_text().split() == ["app"]


def test_repos_of_orders_origin_then_flow_repos_then_extra_repos_each_once(world):
    """`flow.repos` goes through `norm_slug`: a spelling of the origin's slug adds nothing."""
    git_repo(world["repo"], "git@github.com:Acme/App.git")
    git_repo(world["repo"].parent / "zed", "https://github.com/acme/zed")
    crew_path = world["repo"] / ".weside" / "crew.json"
    crew = {
        "members": {"coord": {"name": "Coord", "workplace": ".", "extra_repos": ["../zed"]}},
        "flow": {"repos": ["ACME/app.git", "acme/infra", "acme/zed", "acme/infra"]},
    }
    assert gh_source.repos_of(crew_path, crew) == ["acme/app", "acme/infra", "acme/zed"]
    del crew["flow"]
    assert gh_source.repos_of(crew_path, crew) == ["acme/app", "acme/zed"]


# --- warning 2: the first draw waits on no slow source --------------------------------------


def test_fast_build_reads_no_slow_source(world):
    def boom(*_a, **_k):
        raise AssertionError("a slow source was read")

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(gh_source, "read_all", boom)
        mp.setattr(ci_state, "main_state", boom)
        mp.setattr(accounts, "read", boom)
        cold = zbuild(world, fast=True)
    assert {"github: loading", "main: loading", "accounts: loading"} <= set(cold["gaps"])
    assert [r["item"] for r in cold["sections"]["owner"]] == ["Q4"]
    zbuild(world)  # a full build keeps its slow answers
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(gh_source, "read_all", boom)
        warm = zbuild(world, fast=True)
    assert [r["item"] for r in warm["sections"]["red"]] == ["acme/app#22"]
    assert warm["sources"]["github acme/app"]["fetched_at"]


# --- AC 10 -----------------------------------------------------------------------------------

SNAPSHOT = {
    "zentrale": [
        "schema_version",
        "project",
        "built_at",
        "fast",
        "header",
        "gaps",
        "sources",
        "sections",
    ],
    "sections": ["owner", "red", "waiting", "working", "ci", "accounts"],
    "row": [*open_ends.ROW_FIELDS, "age"],
    "open_ends": [
        "schema_version",
        "project",
        "built_at",
        "header",
        "gaps",
        "attribution",
        "rows",
    ],
    "ci": ["repos", "locks"],
    "accounts": ["schema_version", "state", "gap", "accounts", "red"],
    "account": list(accounts.ALLOWED),
}


def tree_digest(folder: Path) -> dict:
    return {
        str(p.relative_to(folder)): (
            hashlib.sha256(p.read_bytes()).hexdigest(),
            p.stat().st_mtime_ns,
        )
        for p in sorted(folder.rglob("*"))
        if p.is_file()
    }


def test_schema_snapshots_read_only(world, tmp_path):
    before = tree_digest(world["state"])
    doc = zbuild(world)
    assert tree_digest(world["state"]) == before  # board and logs untouched
    assert list(doc) == SNAPSHOT["zentrale"] and doc["schema_version"] == zentrale.SCHEMA_VERSION
    assert list(doc["sections"]) == SNAPSHOT["sections"]
    for key in ("owner", "red"):
        for r in doc["sections"][key]:
            assert list(r) == SNAPSHOT["row"]
    assert list(doc["sections"]["ci"]) == SNAPSHOT["ci"]
    opened = open_ends.build(None, None, {}, UNTIL)
    assert list(opened) == SNAPSHOT["open_ends"] and opened["schema_version"] == 1
    payload = {
        "schemaVersion": 1,
        "storeOnly": True,
        "accounts": [{"email": "a@example.com", "usageStatus": "ok"}],
    }
    fake = tmp_path / "cswap"
    fake.write_text(f"#!/bin/sh\necho '{json.dumps(payload)}'\n")
    fake.chmod(0o755)
    acc = accounts.read(str(fake))
    assert list(acc) == SNAPSHOT["accounts"] and list(acc["accounts"][0]) == SNAPSHOT["account"]
    # control characters in a title arrive stripped
    [q4] = doc["sections"]["owner"]
    assert q4["title"] == "title"
    assert q4["age"] == "0h50"  # crew_view.age_text, the one age format
    assert open_ends.clean("a\x1b[2Jb\x9bc\x00d") == "abcd"


def test_no_reader_has_a_writing_verb():
    """No reader names a board write, a log append or a cswap/gh verb that changes state."""
    banned = (
        "write_board",
        "append_",
        "record_transition",
        "enablePullRequestAutoMerge",
        "mutation",
        "cswap switch",
        '"switch"',
        "--token-status",
    )
    # the event poller and tail are writers by design: their own files under the crew's events
    # folder, the board only through `board.py news worker` (test_event_routes covers it)
    writers = ("event_poller.py", "event_tail.py")
    for path in HERE.glob("*.py"):
        if path.name.startswith("test_") or path.name in writers:
            continue
        text = path.read_text()
        for word in banned:
            assert word not in text, f"{path.name}: {word}"
