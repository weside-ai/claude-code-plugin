"""plan_push.py: plan commits land on the default branch by push, or are refused untouched.

Each case builds a bare remote, a clone and a detached scratch worktree of it in `tmp_path`; the
secret scan is a fake scanner that flags the made-up token pattern `FAKE-SECRET-<digits>` and
writes a gitleaks-format report. No network, no real secret.

Run: `python3 -m pytest -q we/scripts/test_plan_push.py`
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import plan_push

FAKE_SCANNER = r"""
import json, re, subprocess, sys
rng, report = sys.argv[1], sys.argv[2]
log = subprocess.run(["git", "log", "-p", "--format=commit %H", rng],
                     capture_output=True, text=True, check=True).stdout
found, commit, path, line = [], "", "", 0
for raw in log.splitlines():
    if raw.startswith("commit "):
        commit = raw.split()[1]
    elif raw.startswith("+++ b/"):
        path = raw[6:]
    elif raw.startswith("@@"):
        line = int(re.search(r"\+(\d+)", raw).group(1)) - 1
    elif raw.startswith("+") and not raw.startswith("+++"):
        line += 1
        if re.search(r"FAKE-SECRET-\d+", raw):
            found.append({"File": path, "StartLine": line, "RuleID": "fake-rule",
                          "Commit": commit, "Secret": raw[1:], "Match": raw[1:]})
json.dump(found, open(report, "w"))
print("leak:", *[f["Secret"] for f in found])
sys.exit(1 if found else 0)
"""


def git(cwd: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=cwd, check=True, capture_output=True, text=True
    ).stdout


def write(root: Path, rel: str, text: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def commit(root: Path, rel: str, text: str, msg: str = "docs: plan") -> None:
    write(root, rel, text)
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", msg)


def configure(root: Path) -> None:
    git(root, "config", "user.email", "t@example.invalid")
    git(root, "config", "user.name", "t")


FAKE_GH = r"""#!PYTHON
# A fake `gh` for the docs-push.yml route: `workflow run` plays the workflow against the bare
# remote and records a run; `run list` / `run view` answer from that record. The outcome of each
# dispatch comes from the JSON list in $FAKE_GH_PLAN (landed, path, scan, race, other).
import json, os, subprocess, sys
state = os.environ["FAKE_GH_STATE"]
runs = json.load(open(state)) if os.path.exists(state) else []
args = sys.argv[1:]
def steps(failed):
    names = ["Validate input", "Check range", "Secret scan", "Mint token", "Push"]
    out, hit = [], False
    for name in names:
        conclusion = "failure" if name == failed else ("skipped" if hit else "success")
        hit = hit or name == failed
        out.append({"name": name, "conclusion": conclusion})
    return out
if args[:2] == ["workflow", "run"]:
    sha = args[args.index("-f") + 1].split("=", 1)[1]
    plan = json.load(open(os.environ["FAKE_GH_PLAN"]))
    outcome = plan[min(len(runs), len(plan) - 1)]
    remote = os.environ["FAKE_GH_REMOTE"]
    # the workflow fetches the SHA from the docs-push branch the caller pushed
    branches = subprocess.run(["git", "-C", remote, "branch", "--list", "docs-push/*"],
                              capture_output=True, text=True).stdout
    assert f"docs-push/{sha}" in branches, branches
    failed, log = None, ""
    if outcome == "race":
        subprocess.run([sys.executable, os.environ["FAKE_GH_RACER"]], check=True)
        failed, log = "Push", "Push\tmain moved"
    elif outcome == "path":
        failed, log = "Check range", "Check range\toutside the docs paths: apps/x.py"
    elif outcome == "scan":
        failed, log = "Secret scan", "Secret scan\tdocs/plans/x.md:3 aws-access-token"
    elif outcome == "other":
        failed, log = "Mint token", "Mint token\tbad credentials"
    else:
        subprocess.run(["git", "-C", remote, "update-ref", "refs/heads/main", sha], check=True)
    runs.append({"databaseId": 100 + len(runs), "displayTitle": f"docs-push {sha}",
                 "url": f"https://example.invalid/runs/{100 + len(runs)}", "status": "completed",
                 "conclusion": "failure" if failed else "success",
                 "jobs": [{"steps": steps(failed)}], "log": log})
    json.dump(runs, open(state, "w"))
elif args[:2] == ["run", "list"]:
    print(json.dumps([{k: r[k] for k in ("databaseId", "displayTitle", "url")} for r in runs]))
elif args[:2] == ["run", "view"]:
    run = next(r for r in runs if str(r["databaseId"]) == args[2])
    print(run["log"] if "--log-failed" in args else json.dumps(run))
else:
    sys.exit(f"fake gh: unexpected {args}")
"""


class World:
    def __init__(self, tmp: Path, plans: dict, crew: dict | None, workflow: bool = False) -> None:
        self.tmp, self.remote, self.clone = tmp, tmp / "remote.git", tmp / "clone"
        self.scratch = tmp / "scratch"
        git(tmp, "init", "-q", "--bare", "-b", "main", str(self.remote))
        git(tmp, "clone", "-q", str(self.remote), str(self.clone))
        configure(self.clone)
        scanner = tmp / "fake_scanner.py"
        scanner.write_text(FAKE_SCANNER)
        plans = {"secret_scan": f"{sys.executable} {scanner} {{range}} {{report}}", **plans}
        write(self.clone, ".weside/config.json", json.dumps({"plans": plans}))
        if crew is not None:
            crew = {"version": 2, "roles": {}, "members": {}, **crew}
            write(self.clone, ".weside/crew.json", json.dumps(crew))
            for rel in (crew.get("files") or {}).values():
                write(self.clone, rel, "x\n")
        if workflow:
            write(self.clone, ".github/workflows/docs-push.yml", "name: docs-push\n")
        commit(self.clone, "README.md", "x\n", "init")
        git(self.clone, "push", "-q", "origin", "HEAD:main")
        git(self.clone, "worktree", "add", "-q", "--detach", str(self.scratch), "origin/main")

    def remote_head(self) -> str:
        return git(self.remote, "log", "-1", "--format=%s", "main").strip()

    def other_push(self, rel: str) -> None:
        """A second session lands a plan of its own on the remote."""
        other = self.tmp / "other"
        if not other.exists():
            git(self.tmp, "clone", "-q", str(self.remote), str(other))
            configure(other)
        git(other, "pull", "-q", "--rebase")
        commit(other, rel, "other\n", f"docs: {rel}")
        git(other, "push", "-q", "origin", "HEAD:main")


@pytest.fixture()
def make(tmp_path, monkeypatch):
    def build(
        plans: dict | None = None, crew: dict | None = None, workflow: bool = False
    ) -> World:
        world = World(tmp_path, plans or {}, crew, workflow)
        monkeypatch.chdir(world.scratch)
        return world

    return build


def test_lands_plan_with_its_planned_receipt(make, capsys):
    world = make(crew={"oracles": {"receipt_dir": ".weside/verify"}})
    write(world.scratch, ".weside/verify/ACME-1.yaml", "state: planned\nchecks: []\n")
    commit(world.scratch, "docs/plans/ACME-1-story.md", "# plan\n", "docs(ACME-1): plan")

    assert plan_push.main([]) == 0
    out = capsys.readouterr().out
    assert out.splitlines()[0].startswith("landed on main: ")
    assert "A\tdocs/plans/ACME-1-story.md" in out
    assert "A\t.weside/verify/ACME-1.yaml" in out
    assert world.remote_head() == "docs(ACME-1): plan"


def test_a_crew_pointing_outside_weside_still_names_its_receipt_dir(make, capsys):
    """The base's `.weside/` alone is unpacked: `files.goals` elsewhere must not void the crew."""
    world = make(
        crew={"files": {"goals": "docs/goals.md"}, "oracles": {"receipt_dir": ".weside/verify"}}
    )
    write(world.scratch, ".weside/verify/ACME-1.yaml", "state: planned\nchecks: []\n")
    commit(world.scratch, "docs/plans/ACME-1-story.md", "# plan\n", "docs(ACME-1): plan")

    assert plan_push.main([]) == 0, capsys.readouterr().out
    assert world.remote_head() == "docs(ACME-1): plan"


def merge_range(world: World, case: str) -> None:
    """A plan commit plus a merge of a side branch, the merge kept by `rebase.rebaseMerges`.

    `git log --name-only` lists no file of a merge commit and a plain rebase flattens it; only
    the tree diff sees what the merge commit itself adds (the evil merge).
    """
    git(world.scratch, "config", "rebase.rebaseMerges", "true")
    git(world.scratch, "checkout", "-q", "-b", "side")
    side = "apps/x.py" if case == "merge brings code" else "docs/plans/ACME-2-story.md"
    commit(world.scratch, side, "print(1)\n", "side")
    git(world.scratch, "checkout", "-q", "--detach", "origin/main")
    commit(world.scratch, "docs/plans/ACME-1-story.md", "# plan\n")
    git(world.scratch, "merge", "-q", "--no-ff", "--no-commit", "side")
    if case == "evil merge":
        write(world.scratch, "apps/x.py", "print(1)\n")
        git(world.scratch, "add", "-A")
    git(world.scratch, "commit", "-q", "--no-edit")


@pytest.mark.parametrize(
    "case, needle",
    [
        ("code path", "src/app.py"),
        ("merge brings code", "apps/x.py"),
        ("evil merge", "apps/x.py"),
        ("docs merge", "refused: a merge commit in the range"),
        ("config widens itself", ".weside/config.json"),
        ("armed receipt", ".weside/verify/ACME-1.yaml"),
        ("receipt without plan", ".weside/verify/ACME-1.yaml"),
        ("dirty", "dirty"),
        ("nothing", "nothing to land"),
        ("main worktree", "main worktree"),
        ("no scanner", "no secret scanner"),
        ("scanner missing", "secret scan did not run"),
    ],
)
def test_refuses_and_pushes_nothing(make, capsys, monkeypatch, case, needle):
    world = make(crew={"oracles": {"receipt_dir": ".weside/verify"}})
    plan = ("docs/plans/ACME-1-story.md", "# plan\n")
    if case == "code path":
        write(world.scratch, "src/app.py", "print(1)\n")
        commit(world.scratch, *plan)
    elif case in ("merge brings code", "evil merge", "docs merge"):
        merge_range(world, case)
    elif case == "config widens itself":
        wide = {"plans": {"push_paths": ["**"], "secret_scan": "none"}}
        write(world.scratch, ".weside/config.json", json.dumps(wide))
        write(world.scratch, "src/app.py", "print(1)\n")
        commit(world.scratch, *plan)
    elif case == "armed receipt":
        write(world.scratch, ".weside/verify/ACME-1.yaml", "checks: []\n")
        commit(world.scratch, *plan)
    elif case == "receipt without plan":
        commit(world.scratch, ".weside/verify/ACME-1.yaml", "state: planned\n")
    elif case == "dirty":
        commit(world.scratch, *plan)
        write(world.scratch, "docs/plans/ACME-2-story.md", "# draft\n")
    elif case == "main worktree":
        commit(world.clone, *plan)
        monkeypatch.chdir(world.clone)
    elif case == "no scanner":
        write(world.scratch, ".weside/config.json", json.dumps({"plans": {}}))
        git(world.scratch, "add", "-A")
        git(world.scratch, "commit", "-q", "-m", "drop scanner")
        git(world.scratch, "push", "-q", "origin", "HEAD:main")
        commit(world.scratch, *plan)
        monkeypatch.setattr(plan_push.shutil, "which", lambda _name: None)
    elif case == "scanner missing":
        absent = {"plans": {"secret_scan": "no-such-scanner-xyz git {range}"}}
        write(world.scratch, ".weside/config.json", json.dumps(absent))
        git(world.scratch, "add", "-A")
        git(world.scratch, "commit", "-q", "-m", "absent scanner")
        git(world.scratch, "push", "-q", "origin", "HEAD:main")
        commit(world.scratch, *plan)
    before = world.remote_head()

    # A scan refusal must not share 1 with a path refusal: a caller lands a 1 by PR.
    scan_cases = ("no scanner", "scanner missing")
    expected = plan_push.SCAN_REFUSED if case in scan_cases else plan_push.REFUSED
    assert plan_push.main([]) == expected == (4 if case in scan_cases else 1)
    err = capsys.readouterr().err
    assert needle in err
    paths_cases = ("code path", "config widens itself", "merge brings code", "evil merge")
    if case in (*paths_cases, "armed receipt", "receipt without plan"):
        assert "land these by PR" in err
    if case in paths_cases:
        assert "refused: paths outside plans.push_paths" in err
    assert world.remote_head() == before


def test_secret_finding_names_file_and_line_never_the_value(make, capsys):
    world = make()
    commit(world.scratch, "docs/plans/ACME-1-story.md", "# plan\n\ntoken FAKE-SECRET-12345\n")

    assert plan_push.main([]) == plan_push.SCAN_REFUSED == 4
    captured = capsys.readouterr()
    assert "docs/plans/ACME-1-story.md:3  (fake-rule, commit " in captured.err
    assert "FAKE-SECRET" not in captured.err + captured.out
    assert world.remote_head() == "init"


def test_retries_after_a_concurrent_push(make, capsys, monkeypatch):
    world = make()
    commit(world.scratch, "docs/plans/ACME-1-story.md", "# plan\n", "docs(ACME-1): plan")
    real_push, calls = plan_push.push, []

    def racing_push(remote, branch):
        calls.append(branch)
        if len(calls) == 1:
            world.other_push("docs/plans/ACME-2-story.md")
        return real_push(remote, branch)

    monkeypatch.setattr(plan_push, "push", racing_push)

    assert plan_push.main([]) == 0
    assert len(calls) == 2
    log = git(world.remote, "log", "--format=%s", "main").splitlines()
    assert log[:2] == ["docs(ACME-1): plan", "docs: docs/plans/ACME-2-story.md"]
    assert "A\tdocs/plans/ACME-1-story.md" in capsys.readouterr().out


def test_server_rejection_exits_with_its_own_code(make, capsys):
    world = make()
    hook = world.remote / "hooks" / "pre-receive"
    hook.write_text("#!/bin/sh\necho 'protected branch' >&2\nexit 1\n")
    hook.chmod(0o755)
    commit(world.scratch, "docs/plans/ACME-1-story.md", "# plan\n")

    assert plan_push.main([]) == plan_push.REJECTED
    assert "this repo takes no direct push; land by PR" in capsys.readouterr().err
    assert world.remote_head() == "init"


def rejected(reason: str, remote_lines: str = "") -> subprocess.CompletedProcess:
    """What `git push --porcelain` returns when GitHub rejects the ref."""
    out = f"To github.com:acme/app.git\n!\tHEAD:refs/heads/main\t[remote rejected] ({reason})\nDone\n"
    return subprocess.CompletedProcess([], 1, out, remote_lines)


def test_a_lost_ref_lock_is_a_race_and_lands_on_the_next_try(make, capsys, monkeypatch):
    world = make()
    commit(world.scratch, "docs/plans/ACME-1-story.md", "# plan\n", "docs(ACME-1): plan")
    real_push, calls = plan_push.push, []

    def locked_once(remote, branch):
        calls.append(branch)
        if len(calls) == 1:
            world.other_push("docs/plans/ACME-2-story.md")
            return rejected("cannot lock ref 'refs/heads/main': is at 1a2b but expected 3c4d")
        return real_push(remote, branch)

    monkeypatch.setattr(plan_push, "push", locked_once)

    assert plan_push.main([]) == 0
    assert len(calls) == 2
    assert world.remote_head() == "docs(ACME-1): plan"


def test_a_named_ruleset_stays_no_direct_push_and_prints_the_ref_line(make, capsys, monkeypatch):
    world = make()
    commit(world.scratch, "docs/plans/ACME-1-story.md", "# plan\n")
    gh013 = (
        "remote: error: GH013: Repository rule violations found for refs/heads/main.\n"
        "remote: - Changes must be made through a pull request.\n"
    )
    monkeypatch.setattr(
        plan_push,
        "push",
        lambda *_: rejected("push declined due to repository rule violations", gh013),
    )

    assert plan_push.main([]) == plan_push.REJECTED
    err = capsys.readouterr().err
    assert "this repo takes no direct push; land by PR" in err
    assert (
        "server: !\tHEAD:refs/heads/main\t[remote rejected] "
        "(push declined due to repository rule violations)"
    ) in err
    assert world.remote_head() == "init"


def test_an_unknown_server_rejection_fails_without_the_pr_way(make, capsys):
    world = make()
    hook = world.remote / "hooks" / "pre-receive"
    hook.write_text("#!/bin/sh\necho 'quota exceeded' >&2\nexit 1\n")
    hook.chmod(0o755)
    commit(world.scratch, "docs/plans/ACME-1-story.md", "# plan\n")

    assert plan_push.main([]) == plan_push.FAILED
    err = capsys.readouterr().err
    assert "land by PR" not in err
    assert "server: !\tHEAD:refs/heads/main\t[remote rejected] (pre-receive hook declined)" in err


def test_the_ref_line_is_redacted_and_cut():
    token = "ghs_" + "A" * 36
    line = plan_push.ref_line(
        f"!\tHEAD:refs/heads/main\t[remote rejected] ({token} {'x' * 400})\n"
    )
    assert token not in line and "[REDACTED]" in line
    assert len(line) == len("server: ") + plan_push.REF_LINE_MAX


@pytest.fixture()
def fake_gh(make, tmp_path, monkeypatch):
    """A world whose main carries docs-push.yml, and a fake `gh` playing the given outcomes."""

    def build(*outcomes: str) -> World:
        world = make(workflow=True)
        bin_dir = tmp_path / "bin"
        bin_dir.mkdir()
        gh = bin_dir / "gh"
        gh.write_text(FAKE_GH.replace("PYTHON", sys.executable, 1))
        gh.chmod(0o755)
        racer = tmp_path / "racer.py"
        racer.write_text(
            "import sys\n"
            f"sys.path.insert(0, {str(Path(__file__).resolve().parent)!r})\n"
            "from pathlib import Path\n"
            "import test_plan_push as t\n"
            "w = t.World.__new__(t.World)\n"
            f"w.tmp, w.remote = Path({str(tmp_path)!r}), Path({str(world.remote)!r})\n"
            "w.other_push('docs/plans/ACME-2-story.md')\n"
        )
        plan = tmp_path / "gh_plan.json"
        plan.write_text(json.dumps(list(outcomes)))
        monkeypatch.setenv("PATH", f"{bin_dir}:{os.environ['PATH']}")
        monkeypatch.setenv("FAKE_GH_STATE", str(tmp_path / "gh_runs.json"))
        monkeypatch.setenv("FAKE_GH_PLAN", str(plan))
        monkeypatch.setenv("FAKE_GH_REMOTE", str(world.remote))
        monkeypatch.setenv("FAKE_GH_RACER", str(racer))
        monkeypatch.setattr(plan_push, "POLL", 0)
        return world

    return build


def docs_push_branches(world: World) -> str:
    return git(world.remote, "branch", "--list", "docs-push/*").strip()


def test_workflow_route_lands_through_the_dispatched_run(fake_gh, capsys):
    world = fake_gh("landed")
    commit(world.scratch, "docs/plans/ACME-1-story.md", "# plan\n", "docs(ACME-1): plan")

    assert plan_push.main([]) == 0, capsys.readouterr().err
    out = capsys.readouterr().out
    assert out.splitlines()[0].startswith("landed on main: ")
    assert "A\tdocs/plans/ACME-1-story.md" in out
    assert world.remote_head() == "docs(ACME-1): plan"
    assert docs_push_branches(world) == ""


@pytest.mark.parametrize(
    "outcome, code, needle",
    [
        ("path", plan_push.REFUSED, "outside the docs paths: apps/x.py"),
        ("scan", plan_push.SCAN_REFUSED, "step Secret scan"),
        ("other", plan_push.FAILED, "failed in step Mint token: https://example.invalid/runs/"),
    ],
)
def test_workflow_route_maps_the_failed_step(fake_gh, capsys, outcome, code, needle):
    world = fake_gh(outcome)
    commit(world.scratch, "docs/plans/ACME-1-story.md", "# plan\n", "docs(ACME-1): plan")

    assert plan_push.main([]) == code
    err = capsys.readouterr().err
    assert needle in err
    assert world.remote_head() == "init"
    assert docs_push_branches(world) == ""


def test_workflow_route_rebases_and_dispatches_again_when_main_moved(fake_gh, capsys):
    world = fake_gh("race", "landed")
    commit(world.scratch, "docs/plans/ACME-1-story.md", "# plan\n", "docs(ACME-1): plan")

    assert plan_push.main([]) == 0, capsys.readouterr().err
    runs = json.loads(Path(os.environ["FAKE_GH_STATE"]).read_text())
    assert len(runs) == 2 and runs[0]["displayTitle"] != runs[1]["displayTitle"]
    log = git(world.remote, "log", "--format=%s", "main").splitlines()
    assert log[:2] == ["docs(ACME-1): plan", "docs: docs/plans/ACME-2-story.md"]
    assert docs_push_branches(world) == ""


def test_workflow_route_refuses_the_evil_merge_before_any_dispatch(fake_gh, capsys):
    world = fake_gh("landed")
    merge_range(world, "evil merge")

    assert plan_push.main([]) == plan_push.REFUSED
    assert "refused: paths outside plans.push_paths" in capsys.readouterr().err
    assert not Path(os.environ["FAKE_GH_STATE"]).exists()
    assert world.remote_head() == "init"


def test_workflow_route_keeps_the_branch_of_a_run_past_the_wait_cap(fake_gh, capsys, monkeypatch):
    world = fake_gh("path")
    runs = Path(os.environ["FAKE_GH_STATE"])
    real_gh = plan_push.gh

    def running(*args):
        out = real_gh(*args)
        if args[:2] == ("run", "view") and "--json" in args:
            out.stdout = json.dumps({**json.loads(out.stdout), "status": "in_progress"})
        return out

    monkeypatch.setattr(plan_push, "gh", running)
    monkeypatch.setattr(plan_push, "WAIT_CAP", 0)
    commit(world.scratch, "docs/plans/ACME-1-story.md", "# plan\n", "docs(ACME-1): plan")

    assert plan_push.main([]) == plan_push.FAILED
    err = capsys.readouterr().err
    assert "still running" in err and "https://example.invalid/runs/" in err
    assert len(json.loads(runs.read_text())) == 1
    assert docs_push_branches(world).startswith("docs-push/")


@pytest.mark.parametrize(
    "url, repo",
    [
        ("https://github.com/acme/docs.git", ["--repo", "acme/docs"]),
        ("git@github.com:acme/docs.git", ["--repo", "acme/docs"]),
        ("/srv/git/remote.git", []),
    ],
)
def test_gh_is_pinned_to_the_remote_it_pushed_to(make, url, repo):
    world = make()
    git(world.scratch, "remote", "set-url", "origin", url)
    plan_push.pin_repo("origin")
    assert repo == plan_push.REPO
    plan_push.REPO[:] = []
