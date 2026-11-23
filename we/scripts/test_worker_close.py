"""worker_close.py (`we-worker close`): one closing step after a merge.

Each case builds a bare origin `<tmp>/acme/app.git`, its main checkout with a crew, a story plan
and an epic plan, and a worker's worktree whose branch is pushed; GitHub is the fake `gh` in
`fixtures/close` (its PRs in a JSON file), `claude agents` the board fixtures' fake. No real
worktree, branch or ticket outside `tmp_path` is touched.

Run: `python3 -m pytest -q we/scripts/test_worker_close.py`
"""

from __future__ import annotations

import datetime as dt
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import worker_close  # noqa: E402
import worker_launch as wl  # noqa: E402

KEY = "PROJ-12"
TODAY = dt.date(2026, 11, 18)
CREW = HERE / "fixtures" / "crew-v2-generic.json"
STORY = f"""---
type: story-plan
story: {KEY}
epic: PROJ-1
---

# {KEY} export

### Phase 1: export
- **Files:** `src/export.py`
"""
EPIC = """---
type: epic-plan
epic: PROJ-1-epic
ticket: PROJ-1
updated: 2026-11-01
---

# Epic

## Updates Log

- 2026-11-01 — PROJ-11 merged (PR #3); none
"""


def git(cwd: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=cwd, check=True, capture_output=True, text=True
    ).stdout.strip()


class World:
    def __init__(self, tmp: Path, monkeypatch) -> None:
        self.tmp = tmp
        self.origin = tmp / "acme" / "app.git"
        self.top = tmp / "app"
        self.state = tmp / "state"
        self.workers = tmp / "workers"
        self.workers.mkdir()
        git(tmp, "init", "-q", "--bare", "-b", "main", str(self.origin))
        git(tmp, "clone", "-q", str(self.origin), str(self.top))
        git(self.top, "config", "user.email", "t@example.invalid")
        git(self.top, "config", "user.name", "t")
        (self.top / ".weside").mkdir()
        shutil.copy(CREW, self.top / ".weside" / "crew.json")
        self.write("docs/plans/PROJ-1-epic.md", EPIC)
        self.write(f"docs/plans/{KEY}-story.md", STORY)
        self.commit("plans")
        git(self.top, "push", "-q", "origin", "HEAD:main")
        git(self.top, "remote", "set-head", "origin", "main")
        self.gh = {"own": "acme/app", "prs": {"acme/app": []}, "fail": []}
        self.agents = []
        for name, value in {
            "PATH": f"{HERE / 'fixtures' / 'close'}{os.pathsep}{HERE / 'fixtures' / 'board'}"
            f"{os.pathsep}{os.environ['PATH']}",
            "FAKE_GH": str(tmp / "gh.json"),
            "FAKE_GH_LOG": str(tmp / "gh-calls.jsonl"),
            "FAKE_AGENTS": str(tmp / "agents.json"),
            "WE_STATE_DIR": str(self.state),
            "WE_WORKER_STATE_DIR": str(self.workers),
            "CLAUDE_CODE_SESSION_ID": "sid-1",
            "WE_ROLE": "master",
        }.items():
            monkeypatch.setenv(name, value)
        monkeypatch.delenv("WESIDE_COMPANION", raising=False)
        monkeypatch.chdir(self.top)
        self.save()

    def write(self, rel: str, text: str, root: Path | None = None) -> None:
        path = (root or self.top) / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)

    def commit(self, msg: str, root: Path | None = None) -> str:
        git(root or self.top, "add", "-A")
        git(root or self.top, "commit", "-q", "-m", msg)
        return git(root or self.top, "rev-parse", "HEAD")

    def save(self) -> None:
        (self.tmp / "gh.json").write_text(json.dumps(self.gh))
        rows = [{"sessionId": "sid-1", "name": "lead-12", "pid": os.getpid()}, *self.agents]
        (self.tmp / "agents.json").write_text(json.dumps(rows))

    def worker(self, name: str = f"{KEY}-w", branch: str = f"feat/{KEY}-export") -> Path:
        tree = self.tmp / f"app-{name}"
        git(self.top, "worktree", "add", "-q", "-b", branch, str(tree), "origin/main")
        git(tree, "config", "user.email", "t@example.invalid")
        git(tree, "config", "user.name", "t")
        self.write("src/export.py", "x = 1\n", tree)
        oid = self.commit("feat: export", tree)
        git(tree, "push", "-q", "origin", f"HEAD:refs/heads/{branch}")
        wl.write_marker(tree, name=name, key=KEY, role="worker")
        for suffix in (".settings.json", ".json"):
            (self.workers / f"{name}{suffix}").write_text("{}")
        self.pr(7, "MERGED", branch, oid)
        return tree

    def pr(self, number, state, branch, oid="0" * 40, repo="acme/app", title=None) -> None:
        self.gh["prs"].setdefault(repo, []).append(
            {
                "number": number,
                "state": state,
                "title": title or f"feat({KEY}): export",
                "headRefName": branch,
                "headRefOid": oid,
                "url": f"https://github.com/{repo}/pull/{number}",
                "mergedAt": "2026-11-18T09:00:00Z" if state == "MERGED" else None,
            }
        )
        self.save()

    def transitions(self) -> list:
        path = self.state / "board-transitions.jsonl"
        return [json.loads(x) for x in path.read_text().splitlines()] if path.exists() else []

    def remote_branches(self) -> str:
        return git(self.origin, "branch", "--list")


@pytest.fixture
def world(tmp_path, monkeypatch):
    return World(tmp_path, monkeypatch)


def close(*argv: str) -> int:
    return worker_close.main(list(argv), today=TODAY)


class TestClose:
    def test_a_merged_story_moves_once_tears_down_and_names_the_epic_line(self, world, capsys):
        tree = world.worker()
        assert close(KEY) == 0, capsys.readouterr()
        out = capsys.readouterr().out
        [row] = world.transitions()
        assert (row["to"], row["by"], row["caller"]) == ("in_review", "we-worker close", "lead-12")
        assert row["pr"] == ["https://github.com/acme/app/pull/7"]
        assert not tree.exists()
        assert "feat/PROJ-12-export" not in git(world.top, "branch", "--list")
        assert "feat/PROJ-12-export" not in world.remote_branches()
        # the starter log outlives the worker's files (worker_launch.record_launch)
        assert [p.name for p in world.workers.iterdir()] in ([], ["launched.jsonl"])
        assert f"- 2026-11-18 — {KEY} merged (PR #7); none" in out
        assert out.splitlines()[-1] == f"close {KEY}: done"
        # idempotent: a second call moves nothing again and finds nothing to remove
        assert close(KEY) == 0
        out = capsys.readouterr().out
        assert len(world.transitions()) == 1
        assert f"in_review: {KEY} is in_review already" in out and "trees: none left" in out

    def test_a_merged_rule_change_gets_one_board_news_line(self, world, capsys):
        world.worker()
        world.gh["prs"]["acme/app"][-1].update(
            files=[{"path": ".claude/rules/x.md"}, {"path": "src/export.py"}],
            body="Tightens the export rule.",
        )
        world.save()
        assert close(KEY, "--keep-worktrees") == 0, capsys.readouterr()
        assert (
            "news: R-app-7 rules changed: app#7 merged (1 rule file(s))" in capsys.readouterr().out
        )
        board_file = json.loads((world.state / "board.json").read_text())
        [item] = [n for n in board_file["news"] if n["id"] == "R-app-7"]
        assert item["body"].splitlines()[0] == "Tightens the export rule."
        assert close(KEY, "--keep-worktrees") == 0
        assert "news:" not in capsys.readouterr().out

    def test_the_epic_line_lands_by_push_once(self, world, capsys):
        cfg = {"plans": {"land": "push", "secret_scan": "none"}}
        world.write(".weside/config.json", json.dumps(cfg))
        world.commit("config")
        git(world.top, "push", "-q", "origin", "HEAD:main")
        world.worker()
        assert close(KEY) == 0, capsys.readouterr()
        epic = git(world.top, "show", "origin/main:docs/plans/PROJ-1-epic.md")
        assert epic.endswith(
            "- 2026-11-01 — PROJ-11 merged (PR #3); none\n- 2026-11-18 — PROJ-12 merged (PR #7); none"
        )
        assert "updated: 2026-11-18" in epic
        capsys.readouterr()
        assert close(KEY) == 0
        assert "epic: the line is already in docs/plans/PROJ-1-epic.md" in capsys.readouterr().out

    def test_a_follow_up_pr_after_in_review_is_named_and_moves_nothing(self, world, capsys):
        world.worker()
        assert close(KEY, "--keep-worktrees") == 0
        world.pr(9, "MERGED", "fix/PROJ-12-again")
        capsys.readouterr()
        assert close(KEY, "--keep-worktrees") == 0
        assert "follow-up PRs: #9" in capsys.readouterr().out
        assert len(world.transitions()) == 1


class TestRefusals:
    def test_a_pr_that_is_not_merged_stops_before_anything(self, world, capsys):
        tree = world.worker()
        world.pr(8, "OPEN", "feat/PROJ-12-more")
        assert close(KEY, "--pr", "8") == 1
        assert "PR 8 is OPEN, not merged; nothing is torn down" in capsys.readouterr().err
        assert world.transitions() == [] and tree.exists()

    def test_an_open_pr_with_the_key_holds_in_review(self, world, capsys):
        world.worker()
        world.pr(8, "OPEN", "feat/PROJ-12-more")
        assert close(KEY) == 1
        out = capsys.readouterr().out
        assert (
            "refused: in_review: open PR carries the key: https://github.com/acme/app/pull/8"
            in out
        )
        assert world.transitions() == []
        assert "epic:" not in out

    def test_a_repo_of_the_plan_without_a_merged_pr_holds_in_review(self, world, capsys):
        world.write(f"docs/plans/{KEY}-story.md", STORY + "\n### Phase 2: lib\n- **Repo:** lib\n")
        world.commit("plan")
        git(world.top, "push", "-q", "origin", "HEAD:main")
        world.worker()
        assert close(KEY) == 1
        assert "refused: in_review: no merged PR in acme/lib" in capsys.readouterr().out
        assert world.transitions() == []
        world.pr(3, "MERGED", "feat/PROJ-12-lib", repo="acme/lib")
        assert close(KEY) == 0
        assert len(world.transitions()[0]["pr"]) == 2
        assert "merged (PRs #7, acme/lib#3)" in capsys.readouterr().out

    @pytest.mark.parametrize("url", ["https://github.com/acme/lib", "../lib.git"])
    def test_a_submodule_landed_by_fast_forward_counts_as_landed(self, world, capsys, url):
        sub = "1" * 40
        world.write(f"docs/plans/{KEY}-story.md", STORY + "\n### Phase 2: lib\n- **Repo:** lib\n")
        world.write(".gitmodules", f'[submodule "lib"]\n\tpath = lib\n\turl = {url}\n')
        world.commit("plan")
        git(world.top, "push", "-q", "origin", "HEAD:main")
        world.worker()
        git(world.top, "update-index", "--add", "--cacheinfo", f"160000,{sub},lib")
        git(world.top, "commit", "-q", "-m", "feat: pin lib")
        merge = git(world.top, "rev-parse", "HEAD")
        git(world.top, "push", "-q", "origin", "HEAD:main")
        world.gh["prs"]["acme/app"][0]["mergeCommit"] = {"oid": merge}
        world.save()
        assert close(KEY) == 1
        assert "refused: in_review: no merged PR in acme/lib" in capsys.readouterr().out
        world.gh["on_default"] = {"acme/lib": [sub]}
        world.save()
        assert close(KEY) == 0
        out = capsys.readouterr().out
        assert "in_review: acme/lib landed by fast-forward at 1111111 (gitlink)" in out
        assert len(world.transitions()) == 1

    def test_gh_unreadable_holds_in_review_and_guesses_nothing(self, world, capsys):
        world.write(f"docs/plans/{KEY}-story.md", STORY + "\n### Phase 2: lib\n- **Repo:** lib\n")
        world.commit("plan")
        git(world.top, "push", "-q", "origin", "HEAD:main")
        world.worker()
        world.gh["fail"] = ["acme/lib"]
        world.save()
        assert close(KEY) == 1
        assert (
            "in_review: gh unreadable for acme/lib (HTTP 502: gh broke)" in capsys.readouterr().out
        )
        assert world.transitions() == []

    def test_a_dirty_tree_stays_and_is_named(self, world, capsys):
        tree = world.worker()
        (tree / "src" / "export.py").write_text("x = 2\n")
        (tree / "WORKER-REPORT.md").write_text("report\n")
        assert close(KEY) == 1
        assert f"keep {tree}: uncommitted changes: M src/export.py" in capsys.readouterr().out
        assert tree.exists() and "feat/PROJ-12-export" in world.remote_branches()
        assert len(world.transitions()) == 1  # the story moved; only the tree stayed

    def test_an_unmerged_branch_stays_and_is_named(self, world, capsys):
        tree = world.worker()
        world.write("src/later.py", "y = 1\n", tree)
        world.commit("feat: after the merge", tree)
        assert close(KEY) == 1
        out = capsys.readouterr().out
        assert f"keep {tree}: feat/PROJ-12-export is not merged" in out
        assert "feat/PROJ-12-export" in git(world.top, "branch", "--list")

    def test_a_living_worker_keeps_its_tree(self, world, capsys):
        tree = world.worker()
        world.agents = [{"sessionId": "w", "name": f"{KEY}-w", "pid": os.getpid()}]
        world.save()
        assert close(KEY) == 1
        assert f"keep {tree}: {KEY}-w still runs there" in capsys.readouterr().out
        assert (world.workers / f"{KEY}-w.settings.json").exists()

    def test_another_living_worker_on_the_key_holds_in_review_and_the_teardown_runs(
        self, world, capsys
    ):
        tree = world.worker()
        world.agents = [
            {"sessionId": "w2", "name": f"{KEY}-api", "pid": os.getpid()},
            {"sessionId": "w3", "name": f"{KEY}-dead", "pid": 999_999_999},
            {"sessionId": "w4", "name": "PROJ-120-x", "pid": os.getpid()},
        ]
        world.save()
        assert close(KEY) == 1
        out = capsys.readouterr().out
        assert f"held: {KEY}-api still work on {KEY}; run close again when they end" in out
        assert world.transitions() == [] and "epic:" not in out
        assert not tree.exists()  # the finished tree still goes

    def test_the_worker_being_closed_and_the_caller_do_not_hold(self, world, capsys):
        world.worker()
        world.agents = [{"sessionId": "w", "name": f"{KEY}-w", "pid": os.getpid()}]
        world.save()
        assert close(KEY, "--pr", "7", "--keep-worktrees") == 0, capsys.readouterr()
        assert world.transitions()[0]["to"] == "in_review"

    def test_a_queued_start_on_the_key_holds_in_review(self, world, capsys):
        world.worker()
        queue = world.workers / "queue"
        queue.mkdir()
        doc = {
            "name": f"{KEY}-ui",
            "tree": str(world.top),
            "queued_at": 1,
            "waiter_pid": os.getpid(),
        }
        (queue / f"{KEY}-ui.json").write_text(json.dumps(doc))
        assert close(KEY, "--keep-worktrees") == 1
        assert f"held: {KEY}-ui (queued) still work on {KEY}" in capsys.readouterr().out
        assert world.transitions() == []
        doc["waiter_pid"] = 0  # a queue entry without a living waiter holds nothing
        (queue / f"{KEY}-ui.json").write_text(json.dumps(doc))
        assert close(KEY, "--keep-worktrees") == 0

    def test_claude_agents_unreadable_holds_in_review(self, world, capsys, monkeypatch):
        world.worker()
        monkeypatch.setenv("FAKE_AGENTS_EXIT", "1")
        assert close(KEY) == 1
        assert "held: claude agents unreadable" in capsys.readouterr().out
        assert world.transitions() == []

    def test_no_story_plan_on_the_default_branch_moves_nothing(self, world, capsys):
        git(world.top, "rm", "-q", f"docs/plans/{KEY}-story.md")
        world.commit("drop plan")
        git(world.top, "push", "-q", "origin", "HEAD:main")
        world.write(f"docs/plans/{KEY}-story.md", STORY)  # a local copy names nothing
        tree = world.worker()
        assert close(KEY) == 1
        out = capsys.readouterr().out
        assert f"held: no story plan for {KEY} on origin/main" in out
        assert f"move {KEY} to In Review yourself once every repo landed: python3 " in out
        assert f"board.py move {KEY} in_review --pr https://github.com/acme/app/pull/7" in out
        assert world.transitions() == [] and not tree.exists()

    def test_a_remote_branch_with_an_open_pr_stays(self, world):
        world.pr(5, "OPEN", "feat/shared")
        line = worker_close.remote_branch(world.top, "feat/shared", "main", set())
        assert line == "keep origin/feat/shared: open PR https://github.com/acme/app/pull/5"

    def test_the_remote_branch_at_the_merged_head_is_deleted(self, world):
        world.worker()
        oids = {world.gh["prs"]["acme/app"][0]["headRefOid"]}
        line = worker_close.remote_branch(world.top, f"feat/{KEY}-export", "main", oids)
        assert line == f"deleted origin/feat/{KEY}-export"
        assert f"feat/{KEY}-export" not in world.remote_branches()

    def test_a_commit_pushed_after_the_merge_keeps_the_remote_branch(self, world, capsys):
        tree = world.worker()
        world.write("src/late.py", "y = 2\n", tree)
        late = world.commit("feat: late", tree)
        git(tree, "push", "-q", "origin", f"HEAD:refs/heads/feat/{KEY}-export")
        git(tree, "reset", "-q", "--hard", "HEAD~1")  # pushed from elsewhere: the tree is merged
        assert close(KEY) == 0
        out = capsys.readouterr().out
        branch = f"feat/{KEY}-export"
        assert f"keep origin/{branch}: 1 commit(s) after the merged head ({late[:7]})" in out
        assert git(world.origin, "rev-parse", f"refs/heads/{branch}") == late

    def test_an_unreadable_remote_keeps_the_remote_branch(self, world):
        world.worker()
        oids = {world.gh["prs"]["acme/app"][0]["headRefOid"]}
        git(world.top, "remote", "set-url", "origin", str(world.tmp / "gone.git"))
        line = worker_close.remote_branch(world.top, f"feat/{KEY}-export", "main", oids)
        assert line.startswith(f"keep origin/feat/{KEY}-export: remote head unreadable (")
        git(world.top, "remote", "set-url", "origin", str(world.origin))
        assert f"feat/{KEY}-export" in world.remote_branches()

    def test_another_keys_tree_is_not_the_storys(self, world):
        world.worker()
        other = world.tmp / "app-PROJ-120"
        git(world.top, "worktree", "add", "-q", "-b", "feat/PROJ-120-x", str(other), "origin/main")
        assert close(KEY) == 0
        assert other.exists()


class TestSweep:
    def test_lists_a_merged_pr_whose_marker_lies_and_closes_it_with_apply(self, world, capsys):
        tree = world.worker()
        assert close("--sweep") == 0
        out = capsys.readouterr().out
        assert f"close {KEY} --pr https://github.com/acme/app/pull/7 ({tree}, {KEY}-w gone)" in out
        assert tree.exists() and world.transitions() == []
        assert close("--sweep", "--apply") == 0
        assert not tree.exists() and world.transitions()[0]["to"] == "in_review"

    def test_another_living_worker_holds_the_sweep(self, world, capsys):
        world.worker()
        world.agents = [{"sessionId": "w2", "name": f"{KEY}-api", "pid": os.getpid()}]
        world.save()
        assert close("--sweep") == 0
        assert f"  held: {KEY}-api still work on {KEY}" in capsys.readouterr().out
        assert close("--sweep", "--apply") == 1
        assert world.transitions() == []


def test_with_line_puts_a_newest_first_log_on_top():
    text = "# E\n\n## Updates Log\n\n- 2026-11-02 — B\n- 2026-11-01 — A\n\n## Next\n"
    lines = worker_close.with_line(text, "- 2026-11-18 — C", TODAY).splitlines()
    assert lines[4:7] == ["- 2026-11-18 — C", "- 2026-11-02 — B", "- 2026-11-01 — A"]


def test_we_worker_close_reaches_the_script(world):
    world.worker()
    done = subprocess.run(
        ["bash", str(HERE / "we-worker"), "close", "--sweep"],
        cwd=world.top,
        capture_output=True,
        text=True,
        check=False,
    )
    assert done.returncode == 0, done.stderr
    assert done.stdout.startswith(f"close {KEY} --pr https://github.com/acme/app/pull/7")
