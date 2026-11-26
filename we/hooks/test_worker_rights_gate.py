"""worker_rights_gate.py as a hook: throwaway repos, a crew file and a fake `gh` on PATH."""

from __future__ import annotations

import io
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest

HOOK = Path(__file__).with_name("worker_rights_gate.py")
SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))
import worker_rights as wr  # noqa: E402

KEY = "ABC-12"
BRANCH = f"feat/{KEY}-hook"
RIGHTS = {
    "branch_rc": "a release staging",
    "deny_commands": ["secret-pipe.sh", "wsec put"],
    "deny_text": ["/dev/shm/vault-", "token-file.json"],
}
CREW = {"version": 2, "roles": {"product": "po"}, "members": {"po": {"name": "Ada"}}}

# `gh pr view <sel> --repo <r> --json …`: the PR table in $FAKE_GH_PRS, exit 1 for an unknown one.
# `arm_pr.sh --check` reads: the PR (GraphQL, `--jq` through jq) from $FAKE_GH_READ, the head being
# the checkout's HEAD unless the read names one; the base's required names from $FAKE_GH_REQUIRED.
# A read of {"fail": "<error>"} exits 1 with that error.
FAKE_GH = r"""#!/usr/bin/env python3
import json, os, subprocess, sys
args = sys.argv[1:]
with open(os.environ["FAKE_GH_LOG"], "a") as fh:
    fh.write(json.dumps(args) + "\n")
jq = args[args.index("--jq") + 1] if "--jq" in args else None
def out(obj):
    if jq is None:
        print(json.dumps(obj)); sys.exit(0)
    sys.exit(subprocess.run(["jq", "-r", jq], input=json.dumps(obj), text=True).returncode)
def load(var, default):
    return json.load(open(os.environ[var])) if os.environ.get(var) else default
if args[:2] == ["pr", "view"]:
    pr = json.load(open(os.environ["FAKE_GH_PRS"])).get(args[2])
    if pr is None:
        print("no pull requests found", file=sys.stderr); sys.exit(1)
    print(json.dumps(pr)); sys.exit(0)
if args[:2] == ["api", "graphql"] and not any(a.startswith("query=mutation") for a in args):
    s = load("FAKE_GH_READ", {})
    if "fail" in s:
        print(s["fail"], file=sys.stderr); sys.exit(1)
    head = s.get("head") or subprocess.run(
        ["git", "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    nodes = [{"__typename": "CheckRun", "name": n, "status": st, "conclusion": c, "isRequired": r}
             for n, st, c, r in s.get("checks", [])]
    out({"data": {"repository": {"pullRequest": {
        "id": "PR_7", "state": "OPEN", "isDraft": False, "headRefOid": head,
        "baseRefName": "main", "mergeStateStatus": s.get("merge", "CLEAN"),
        "reviewDecision": s.get("review"),
        "labels": {"nodes": [{"name": n} for n in s.get("labels", [])]},
        "commits": {"nodes": [{"commit": {"oid": head,
            "statusCheckRollup": {"contexts": {"nodes": nodes}}}}]}}}}})
if args[:1] == ["api"] and "/rules/branches/" in args[1]:
    out([{"type": "required_status_checks", "parameters": {"required_status_checks":
        [{"context": c} for c in load("FAKE_GH_REQUIRED", [])]}}])
if args[:1] == ["api"] and "/branches/" in args[1]:
    out({"name": "main", "protection": {"required_status_checks": {"contexts": []}}})
sys.exit(0)
"""


def _git(cwd, *args):
    subprocess.run(["git", "-C", str(cwd), *args], check=True, capture_output=True)


def make_repo(tmp_path: Path, name="app", rights=RIGHTS, branch=BRANCH, crew=True, owner="acme"):
    repo = tmp_path / name
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    if crew:
        (repo / ".weside").mkdir()
        body = {**CREW, "worker_rights": rights} if rights is not None else CREW
        (repo / ".weside" / "crew.json").write_text(json.dumps(body))
        _git(repo, "add", ".weside")
    _commit(repo)
    _git(repo, "remote", "add", "origin", f"git@github.com:{owner}/{name}.git")
    _publish(repo)
    _git(repo, "symbolic-ref", "refs/remotes/origin/HEAD", "refs/remotes/origin/main")
    _git(repo, "tag", "v1.2.3-rc.1")
    if branch != "main":
        _git(repo, "checkout", "-q", "-b", branch)
    return repo


def _commit(repo, message="i"):
    _git(
        repo,
        "-c",
        "user.email=t@t",
        "-c",
        "user.name=t",
        "commit",
        "-q",
        "--allow-empty",
        "-m",
        message,
    )


def _publish(repo):
    """The current commit becomes origin's default branch (what the gate reads the crew from)."""
    _git(repo, "update-ref", "refs/remotes/origin/main", "HEAD")


@pytest.fixture
def world(tmp_path):
    bindir = tmp_path / "bin"
    bindir.mkdir()
    (bindir / "gh").write_text(FAKE_GH)
    (bindir / "gh").chmod(0o755)
    prs = {
        "7": {
            "number": 7,
            "headRefName": BRANCH,
            "headRepository": {"name": "app"},
            "headRepositoryOwner": {"login": "acme"},
        },
        "8": {
            "number": 8,
            "headRefName": "feat/ABC-99-other",
            "headRepository": {"name": "app"},
            "headRepositoryOwner": {"login": "acme"},
        },
        "10": {
            "number": 10,
            "headRefName": BRANCH,
            "headRepository": {"name": "app"},
            "headRepositoryOwner": {"login": "fork"},
        },
    }
    (tmp_path / "prs.json").write_text(json.dumps(prs))
    env = {k: v for k, v in os.environ.items() if not k.startswith(("WE_", "CLAUDE"))}
    env.update(
        PATH=f"{bindir}{os.pathsep}{os.environ['PATH']}",
        FAKE_GH_PRS=str(tmp_path / "prs.json"),
        FAKE_GH_LOG=str(tmp_path / "gh.log"),
        WE_ROLE="worker",
        WE_STORY_KEY=KEY,
        HOME=str(tmp_path / "home"),
        GIT_SSH_COMMAND="false",  # arm_pr.sh fetches the base; the fake origin answers nothing
    )
    return {"tmp": tmp_path, "env": env, "repo": make_repo(tmp_path)}


def hook(world, command, cwd=None, session="s-1", **env):
    payload = {
        "tool_name": "Bash",
        "tool_input": {"command": command},
        "cwd": str(cwd or world["repo"]),
        "session_id": session,
    }
    run_env = {**world["env"], **env}
    for k, v in list(run_env.items()):
        if v is None:
            del run_env[k]
    out = subprocess.run(
        [sys.executable, str(HOOK)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        env=run_env,
        timeout=60,
        check=False,
    )
    assert out.returncode == 0, out.stderr
    if not out.stdout.strip():
        return None, ""
    spec = json.loads(out.stdout)["hookSpecificOutput"]
    return spec["permissionDecision"], spec["permissionDecisionReason"]


# ---------------------------------------------------------------- what the gate leaves alone


@pytest.mark.parametrize(
    "command",
    [
        "gh pr ready",
        "gh pr ready 8",
        "/plugin/scripts/pr_ready.sh 8 ready --sha 0123abc",
        "gh pr comment 8 --body x",
        "gh pr comment 12 -R acme/other --body x",
        "gh pr comment 8 --delete-last --yes",
        "a release staging rc",
        "env gh pr ready 8",
        "bash -c 'gh pr comment 8 -b x'",
    ],
)
def test_ready_comment_and_branch_rc_stay_out_of_the_gate(world, command):
    """Rows R1 to R5 and N7 are gone: a comment or a ready flag changes no code and no prod, so
    the gate gives no decision and `settings` allows them; a crew granting nothing changes that
    not."""
    _git(world["repo"], "checkout", "-q", "main")  # the default branch was a refusal (R4)
    assert hook(world, command, WE_STORY_KEY=None) == (None, "")


@pytest.mark.parametrize("owner", ["master", "worker"])
def test_a_held_right_is_allowed_without_a_prompt(world, owner):
    _pr_owner(world["repo"], owner)
    decision, reason = hook(world, "gh pr merge 7 --disable-auto")
    assert decision == "allow", reason
    if owner == "worker":
        assert hook(world, "/plugin/scripts/arm_pr.sh 7 --method squash")[0] == "allow"
        assert hook(world, "gh pr edit 7 --add-label y --title z")[0] == "allow"


def test_a_held_right_in_a_compound_command_only_passes(world):
    assert hook(world, "git status && gh pr merge 7 --disable-auto") == (None, "")


@pytest.mark.parametrize(
    ("command", "why"),
    [
        ("cd /x && gh pr merge 8 --disable-auto", "not this branch's PR"),
        ("git status; gh pr merge -R acme/other 7 --disable-auto", "another repo"),
        ("true || gh pr merge 7 --squash", "without --match-head-commit"),
        ("echo x | gh pr merge 7 --disable-auto --merge", "takes no other flag"),
        ("cd .\ngh pr merge 10 --disable-auto", "comes from fork/app"),
        ("cd . && gh pr merge 9 --disable-auto", "could not be resolved"),
    ],
)
def test_a_right_inside_a_command_chain_is_judged_on_its_segment(world, command, why):
    decision, reason = hook(world, command)
    assert decision == "deny" and why in reason, reason


@pytest.mark.parametrize(
    ("command", "right"),
    [
        ("env arm_pr.sh 7", "arm behind env"),
        ("X=1 arm_pr.sh 7", "arm behind an assignment"),
        ("timeout 9 arm_pr.sh 7", "arm behind timeout"),
        ("bash -c 'arm_pr.sh 7'", "arm in bash -c"),
        ('eval "arm_pr.sh 7"', "arm in eval"),
        ('echo "$(arm_pr.sh 7)"', "arm in a command substitution"),
    ],
)
def test_a_right_behind_a_wrapper_or_in_a_nested_shell_is_refused(world, command, right):
    """Security card #276 a71e339 WARNING 2: an arm holds only as a command of its own (R1b)."""
    _pr_owner(world["repo"], "worker")
    decision, reason = hook(world, command)
    assert decision == "deny", reason
    assert f"not a worker right ({right}: a right only as a command of its own" in reason, reason


@pytest.mark.parametrize(
    "command",
    [
        "env gh pr merge 7 --squash",
        "timeout 9 gh pr merge 7 --disable-auto",
        "bash -c 'gh pr merge 7 --squash'",
        'eval "gh pr merge 7 --squash"',
        "echo `gh pr merge 7 --squash`",
    ],
)
def test_a_hidden_merge_is_a_never_item_for_every_owner(world, command):
    for owner in ("master", "worker"):
        _pr_owner(world["repo"], owner)
        decision, reason = hook(world, command)
        assert decision == "deny", reason
        assert "merge (gh pr merge only as a visible part of the command)" in reason, reason


@pytest.mark.parametrize(
    "command",
    [
        "{ gh pr merge 8 --disable-auto; }",
        "if true; then gh pr merge 8 --disable-auto; fi",
        "while false; do gh pr merge 8 --disable-auto; done",
    ],
)
def test_a_right_after_a_shell_keyword_is_judged(world, command):
    decision, reason = hook(world, command)
    assert decision == "deny" and "not this branch's PR" in reason, reason


@pytest.mark.parametrize(
    "command",
    [
        "env FOO=1 pytest -q",
        "bash -c 'pytest -q'",
        "timeout 9 pytest -q",
        "GIT_EDITOR=true git rebase --continue",
        "if true; then gh pr ready 7; fi",
        "gh pr create --body-file - <<'EOF'\nrefuses `env gh pr ready 8` and `bash -c`\nEOF",
        "git commit -m 'refuse `gh pr ready` behind env'",
    ],
)
def test_ordinary_wrapped_work_passes(world, command):
    assert hook(world, command) == (None, "")


@pytest.mark.parametrize("owner", ["master", "worker"])
def test_a_merge_part_in_a_chain_is_no_never_item(world, owner):
    """Red arm: a fix round's `cd <tree> && … --disable-auto` and the `ready` line in a chain were
    "never for a worker" (N23), so the starter relayed each one. A visible part is judged like any
    right now; a hidden one beside it still refuses."""
    _pr_owner(world["repo"], owner)
    for command in ("cd . && gh pr merge 7 --disable-auto", "cd . && gh pr merge 7 --squash"):
        assert wr.never(command, str(world["repo"]), {}) is None, command
    command = "cd . && gh pr merge 7 --disable-auto && bash -c 'gh pr merge 7 --squash'"
    assert wr.never(command, str(world["repo"]), {}) == (
        "merge (gh pr merge only as a visible part of the command)"
    )


# ---------------------------------------------------------------- AC 7: the never-list

NEVER = [
    ("gh secret set TOKEN", "secrets (gh secret)"),
    ("gh secret list", "secrets (gh secret)"),
    ("gh variable set X --body 1", "secrets (gh variable)"),
    ("gh api -X PUT repos/acme/app/actions/secrets/X", "secrets (gh api write"),
    ("gh api repos/acme/app/environments/prod -f wait_timer=0", "secrets (gh api write"),
    ("gh api --method=PATCH repos/acme/app/actions/variables/X", "secrets (gh api write"),
    ("secret-pipe.sh NAME", "secrets (crew deny_commands: secret-pipe.sh)"),
    ("bash scripts/secret-pipe.sh NAME", "secrets (crew deny_commands: secret-pipe.sh)"),
    ("echo v | wsec put NAME", "secrets (crew deny_commands: wsec put)"),
    ("gh repo delete acme/app --yes", "delete (gh repo delete)"),
    ("gh release delete v1", "delete (gh release delete)"),
    ("gh api -X DELETE repos/acme/app/git/refs/heads/x", "delete (gh api with method DELETE)"),
    ("gh api --method DELETE repos/acme/app/hooks/1", "delete (gh api with method DELETE)"),
    ("gh pr close 7 --delete-branch", "delete (--delete-branch)"),
    ("git push --delete origin feat/x", "delete (git push --delete)"),
    ("git push origin -d feat/x", "delete (git push --delete)"),
    ("git push origin :feat/x", "delete (git push :feat/x)"),
    ("git push origin main", "main (git push to main)"),
    ("git push origin HEAD:main", "main (git push to main)"),
    ("git push origin +HEAD:refs/heads/main", "main (git push to main)"),
    ("git push origin feat/x:master", "main (git push to master)"),
    ("git push --all origin", "main (git push --all)"),
    ("git push origin v1.2.3-rc.1", "guard bypass (git push of the tag v1.2.3-rc.1)"),
    ("git push origin refs/tags/v9", "guard bypass (git push of a tag)"),
    ("git push origin tag v9", "guard bypass (git push of a tag)"),
    ("git push --tags", "guard bypass (git push of a tag)"),
    ("git commit --no-verify -m x", "guard bypass (git commit --no-verify)"),
    ("git commit -m x --no-verif", "guard bypass (git commit --no-verify)"),
    ("git -C . commit --no-verify -m x", "guard bypass (git commit --no-verify)"),
    ("git commit -nm x", "guard bypass (git commit -n)"),
    ("git -c core.hooksPath=/dev/null commit -m x", "guard bypass (core.hooksPath on a commit)"),
    ("SKIP=gitleaks git commit -m x", "guard bypass (SKIP=gitleaks)"),
    ("SKIP=ruff-format,gitleaks git commit -m x", "guard bypass (SKIP=gitleaks)"),
    ('SKIP="gitleaks" git commit -m x', "guard bypass (SKIP=gitleaks)"),
    ("export SKIP=gitleaks; git add a && git commit -m x", "guard bypass (SKIP=gitleaks)"),
    ("cat /dev/shm/vault-1000/x.json", "crew deny_text (/dev/shm/vault-)"),
    ("jq . ~/token-file.json", "crew deny_text (token-file.json)"),
    # every form a worker types
    ("git status && gh secret set X", "secrets (gh secret)"),
    ("true; gh secret set X", "secrets (gh secret)"),
    ("echo x | gh secret set X", "secrets (gh secret)"),
    ("bash -c 'gh secret set X'", "secrets (gh secret)"),
    ('sh -c "git push origin main"', "main (git push to main)"),
    ('echo "$(gh secret set X)"', "secrets (gh secret)"),
    ("echo `gh api -X DELETE repos/a/b`", "delete (gh api with method DELETE)"),
    ("env GH_DEBUG=1 timeout 30 gh secret set X", "secrets (gh secret)"),
    ("bash <<'EOF'\ngh secret set X\nEOF", "secrets (gh secret)"),
    (
        'python3 -c \'import subprocess; subprocess.run(["gh", "secret", "set", "X"])\'',
        "secrets (gh secret)",
    ),
    (
        'node -e \'require("child_process").execSync("git push origin main")\'',
        "main (git push to main)",
    ),
    ("eval 'gh secret set X'", "secrets (gh secret)"),
    # review round 1
    ("git push origin \\\n  main", "main (git push to main)"),
    ("cat <<EOF\n$(gh secret list)\nEOF", "secrets (gh secret)"),
    ("nice -n 5 git push origin main", "main (git push to main)"),
    ("stdbuf -oL gh secret list", "secrets (gh secret)"),
    ("time -p gh secret list", "secrets (gh secret)"),
    ("command -p gh secret list", "secrets (gh secret)"),
    ("git push origin 'refs/heads/*:refs/heads/*'", "main (git push of a ref pattern"),
    ("git push --dele origin feat/x", "delete (git push --delete)"),
    ('echo "`gh secret list`"', "secrets (gh secret)"),
    ("cd ../main-checkout && git push", None),
    # the never-list through git's own place flags
    ("git --git-dir=.git push origin main", "main (git push to main)"),
    ("git --work-tree . push --delete origin feat/x", "delete (git push --delete)"),
    ("git -C ../main-checkout push", None),
    # a merge past the checks, or one no part shows
    ("gh pr merge 7 --admin", "merge (gh pr merge --admin)"),
    ("gh pr merge 7 --auto --squash", "merge (gh pr merge --auto)"),
    (
        "gh pr merge 7 --disable-auto && bash -c 'gh pr merge 7 --squash'",
        "merge (gh pr merge only as a visible part of the command)",
    ),
]


@pytest.mark.parametrize("command,item", NEVER, ids=[c for c, _ in NEVER])
def test_the_never_list_is_denied_for_a_worker(world, command, item):
    if item is None:  # the push runs in the tree a `cd` or `git -C` names, here on main
        main = make_repo(world["tmp"], name="main-checkout", branch="main")
        command = command.replace("../main-checkout", str(main))
        item = "main (a git push from main:"
    decision, reason = hook(world, command)
    assert decision == "deny", reason
    assert reason.startswith(f"never for a worker ({item}") and reason.endswith("ask your starter")


@pytest.mark.parametrize("command,item", NEVER[:12], ids=[c for c, _ in NEVER[:12]])
def test_a_master_is_not_touched(world, command, item):
    assert hook(world, command, WE_ROLE="master") == (None, "")


@pytest.mark.parametrize(
    "command",
    [
        "git push origin HEAD",
        "git push -u origin feat/ABC-12-hook",
        "git push origin HEAD:refs/heads/feat/ABC-12-hook",
        "gh pr view 7 --json state",
        "gh api repos/acme/app/environments",
        "gh pr create --body-file b.md",
        "git commit -m 'main and master'",
        "git push origin HEAD:refs/heads/feat/ABC-12-mainline",
        'git commit -m "Fixed \\`foo\\` in bar"',
        "git commit -m 'drop `git push --delete` from the docs'",
        "grep -rn secret src/",
        "gh pr create --title x --body \"$(cat <<'EOF'\n## Verification\nEOF\n)\"",
        "for f in a b; do echo $f; done",
        "[[ -f x ]] && echo $((1+2))",
        "python3 - <<'EOF'\nprint(1)\nEOF",
        'grep -c x <<<"$y"',
        "python3 -m pytest -q we/hooks 2>&1 | tail -3",
        "git fetch -q origin && git rebase origin/main",
    ],
)
def test_ordinary_work_passes(world, command):
    assert hook(world, command) == (None, "")


@pytest.mark.parametrize(
    "command",
    [
        "cat <<'EOF' > body.md\nnever gh secret set here? it is data\nEOF",
        "echo 'literal $(gh secret set X)'",
        "git commit -m \"$(cat <<'EOF'\nfeat: x\n\nnot gh secret set, data\nEOF\n)\" && git log -1",
        "git commit -m 'drop --no-verify from the docs'",
        "sed -n '1,5p' f; cat > /tmp/x <<EOF\ngh secret set X\nEOF",
    ],
)
def test_data_naming_a_never_item_is_denied_like_the_settings_deny_rules(world, command):
    """No parser tells data from a command: the gate denies what the `--settings` deny globs
    (`Bash(*git*commit*--no-verify*)`, `Bash(*gh secret *)`) already deny for the same text."""
    assert hook(world, command)[0] == "deny"


@pytest.mark.parametrize(
    "refspec",
    [
        "+main",
        '"main"',
        "'main'",
        '"+main"',
        "+refs/heads/main",
        '"refs/heads/main"',
        'HEAD:"main"',
        "+HEAD:main",
        "HEAD:main",
        "refs/heads/main",
        ":main",
        "+master",
    ],
)
def test_a_push_to_main_in_any_refspec_spelling_is_denied(world, refspec):
    decision, reason = hook(world, f"git push origin {refspec}")
    assert decision == "deny" and "never for a worker" in reason, reason


@pytest.mark.parametrize("refspec", ["+feat/ABC-12-main", '"feat/ABC-12-x"', "+HEAD:mainline"])
def test_a_push_to_a_branch_merely_named_like_main_passes(world, refspec):
    assert hook(world, f"git push origin {refspec}")[0] != "deny"


@pytest.mark.parametrize(
    "command",
    [
        'git push origin +m"ain"',
        'git push origin "+ma"in',
        'git push origin +HEAD:ma"in"',
        "git push -f origin m'ain'",
        "git push origin HEAD:refs/heads/ma'in'",
        "git push origin ma\\in",
        "git push origin HEAD:mai''n",
        "git push origin m$'a'in",
        "cd /x && git push origin +ma''in",
        'eval "git push origin +ma""in"',
    ],
)
def test_a_push_to_main_with_quotes_inside_the_name_is_denied(world, command):
    """Security card #276 a71e339: the shell joins the quoted pieces, git receives `main`."""
    decision, reason = hook(world, command)
    assert decision == "deny" and "never for a worker (main (git push to main)" in reason, reason


@pytest.mark.parametrize(
    "command",
    [
        "git push -u origin fix/ABC-1-x",
        "git push origin HEAD",
        "git push origin main-fix",
        "git push origin maintenance",
        "git push origin 'main-fix'",
        'git push origin HEAD:"maintenance"',
    ],
)
def test_a_feature_push_passes_the_normalised_text(world, command):
    assert hook(world, command) == (None, "")


def test_a_bare_push_from_main_is_denied(world):
    _git(world["repo"], "checkout", "-q", "main")
    decision, reason = hook(world, "git push")
    assert decision == "deny" and "main (a git push from main:" in reason


def _main_checkout_with_tree(world, owner="worker"):
    """A repo whose session cwd is its main checkout on main and whose worker tree is a worktree on
    the worker's branch (Kiska 21.11.: a worker started from the shared main checkout)."""
    main = make_repo(world["tmp"], name="core", branch="main")
    if owner:
        _pr_owner(main, owner)
    tree = world["tmp"] / "core-tree"
    _git(main, "worktree", "add", "-q", "-b", "feat/ABC-12-tree", str(tree))
    return main, tree


@pytest.mark.parametrize(
    "command",
    [
        "git -C {tree} push -u origin feat/ABC-12-tree",
        "git -C {tree} push",
        "git --git-dir={gitdir} --work-tree {tree} push origin HEAD",
    ],
)
def test_a_push_is_judged_in_the_tree_git_runs_it_in(world, command):
    main, tree = _main_checkout_with_tree(world)
    gitdir = subprocess.run(
        ["git", "-C", str(tree), "rev-parse", "--absolute-git-dir"],
        capture_output=True, text=True, check=True,
    ).stdout.strip()  # fmt: skip
    # a push is no right: the gate gives no decision
    assert hook(world, command.format(tree=tree, gitdir=gitdir), cwd=main) == (None, "")


@pytest.mark.parametrize(
    ("command", "why"),
    [
        # a second push without its own place may run in the cwd, which is on main
        ("git -C {tree} push; git push", "main (a git push from main:"),
        ("git -C {tree} push && git -C {main} push", "main (a git push from main:"),
        ("cd {tree} && git push", "main (a git push from main:"),
        ("git -C {tree} push origin main", "main (git push to main)"),
    ],
)
def test_a_push_from_a_main_checkout_stays_denied_outside_its_own_tree(world, command, why):
    main, tree = _main_checkout_with_tree(world)
    decision, reason = hook(world, command.format(tree=tree, main=main), cwd=main)
    assert decision == "deny" and why in reason, reason
    if why.startswith("main (a git push from"):  # the refusal names the form that passes
        assert "one `git -C <own worktree> push …`, without `2>&1`, `&&`" in reason, reason


@pytest.mark.parametrize(
    "command",
    [
        "export GIT_DIR={main}/.git; git -C {tree} push origin HEAD",
        "GIT_DIR={main}/.git; git -C {tree} push origin HEAD",
        "env GIT_WORK_TREE={main} git -C {tree} push origin HEAD",
        "GIT_INDEX_FILE={main}/.git/index git -C {tree} push origin HEAD",
    ],
)
def test_a_push_with_a_redirected_repo_is_judged_in_the_cwd(world, command):
    """`git -C <tree>` names the tree, but GIT_DIR and its kin decide which repo git pushes: an
    environment is a prefix or a segment of its own, so no simple push form, so the cwd (on main)
    stays in the check."""
    main, tree = _main_checkout_with_tree(world)
    text = command.format(tree=tree, main=main)
    decision, reason = hook(world, text, cwd=main)
    assert decision == "deny" and "main (a git push from main:" in reason, reason
    assert str(main) in wr._push_dirs(text, str(main))


def test_a_text_that_only_names_git_dir_is_no_refusal(world):
    """The gate judges the code, not the text: a commit message naming GIT_DIR is data."""
    _pr_owner(world["repo"], "worker")
    text = "git commit -m 'drop GIT_DIR from the env' && git push origin feat/ABC-12-hook"
    # a held right in a chain only passes this gate: no denial, no allow
    assert hook(world, text) == (None, "")


@pytest.mark.parametrize(
    ("command", "owner"),
    [
        # T2 panel round 3: a path `git` behind a valid push was not counted; the one row where
        # the owner splits the bypass, so it runs under both
        ("git -C {tree} push origin feat/ABC-12-tree; eval /usr/bin/git push", "master"),
        ("git -C {tree} push origin feat/ABC-12-tree; eval /usr/bin/git push", "worker"),
        # a relative `git` behind a valid push
        ("git -C {tree} push origin feat/ABC-12-tree && ./git push", "worker"),
        # any second segment, a harmless one too, keeps the cwd in
        ("git -C {tree} push origin feat/ABC-12-tree && echo done", "worker"),
        # a second line is a second segment
        ("git -C {tree} push origin feat/ABC-12-tree\ngit status", "worker"),
        # a push inside a nested shell
        ("bash -c 'git push'", "worker"),
        # a config option that moves the work tree
        ("git -c core.worktree={tree} -C {tree} push origin feat/ABC-12-tree", "worker"),
        # the `command` builtin in front of git
        ("command git -C {tree} push origin feat/ABC-12-tree", "worker"),
        # a backslash that skips an alias
        ("\\git -C {tree} push origin feat/ABC-12-tree", "worker"),
        # an absolute path to git
        ("/usr/bin/git -C {tree} push origin feat/ABC-12-tree", "worker"),
        # an environment assignment in front of git (GIT_DIR=…)
        ("X=1 git -C {tree} push origin feat/ABC-12-tree", "worker"),
        # a variable the gate cannot expand
        ("git -C $TREE push origin feat/ABC-12-tree", "worker"),
        # an open quote: the `shlex` error
        ("git -C '{tree} push origin feat/ABC-12-tree", "worker"),
    ],
)
def test_only_one_simple_push_leaves_the_cwd_out(world, command, owner):
    """Vyra's contract: the cwd drops out only for exactly one `git [-C|--git-dir|--work-tree]…
    push` segment; anything else, a `shlex` error included, is judged with the cwd (main here)."""
    main, tree = _main_checkout_with_tree(world, owner=owner)
    decision, reason = hook(world, command.format(tree=tree), cwd=main)
    assert decision == "deny" and "main (a git push from main:" in reason, reason


def test_cumulative_c_dirs_are_resolved_against_the_cwd(world):
    """`git -C a -C b push` runs in `a/b`: the main checkout there is refused."""
    (world["tmp"] / "a").mkdir()
    main = make_repo(world["tmp"] / "a", name="b", branch="main")
    _pr_owner(main, "worker")
    decision, reason = hook(world, "git -C a -C b push origin HEAD", cwd=world["tmp"])
    assert decision == "deny" and "main (a git push from main:" in reason, reason


def test_a_git_dir_onto_the_main_checkout_is_refused_from_a_worktree(world):
    main, tree = _main_checkout_with_tree(world)
    decision, reason = hook(world, f"git --git-dir={main}/.git push origin HEAD", cwd=tree)
    assert decision == "deny" and "main (a git push from main:" in reason, reason


def test_a_simple_push_through_git_dir_and_work_tree_passes_from_main(world):
    main, tree = _main_checkout_with_tree(world)
    text = f"git --git-dir={tree}/.git --work-tree={tree} push origin feat/ABC-12-tree"
    assert hook(world, text, cwd=main) == (None, "")


def test_a_push_spelt_apart_is_judged_where_it_runs(world):
    main, _tree = _main_checkout_with_tree(world)
    decision, reason = hook(world, "gi''t push", cwd=main)
    assert decision == "deny" and "main (a git push from main:" in reason, reason


def test_a_tag_is_judged_in_every_place_a_push_runs(world):
    other = make_repo(world["tmp"], name="other", branch="feat/ABC-12-x")
    _git(other, "tag", "v-only-there")
    decision, reason = hook(world, f"git -C {other} push origin v-only-there")
    assert decision == "deny" and "git push of the tag v-only-there" in reason, reason


def test_every_denial_is_one_line_in_brakes_jsonl_without_the_command(world):
    state = world["tmp"] / "state"
    decision, _reason = hook(world, "printf s3cr3t-value | wsec put NAME", WE_STATE_DIR=str(state))
    assert decision == "deny"
    hook(world, "gh pr merge 8 --disable-auto", WE_STATE_DIR=str(state))
    hook(world, "git status", WE_STATE_DIR=str(state))  # no denial, no line
    text = (state / "brakes.jsonl").read_text()
    assert "s3cr3t-value" not in text
    first, second = [json.loads(x) for x in text.splitlines()]
    assert set(first) == {"ts", "type", "gate", "item", "name", "key", "session_id", "argv0"}
    assert first["type"] == "deny" and first["gate"] == "worker_rights_gate"
    assert first["item"] == "never for a worker (secrets (crew deny_commands: wsec put))"
    assert first["key"] == KEY and first["argv0"] == "printf" and first["ts"].endswith("Z")
    assert second["item"].startswith("not a worker right (PR 8 is not this branch's PR")
    assert second["argv0"] == "gh"


def test_the_starter_logs_a_card_verdict_and_later_its_outcome(tmp_path, own_state_dir, capsys):
    verdict = tmp_path / "verdict.md"
    verdict.write_text(
        "<!-- security-card-review -->\n## Security card review\n\n**Overall: BLOCKING**\n"
    )
    assert wr.main(["brake", "card", "--pr", "12", "--file", str(verdict)]) == 0
    assert wr.main(["brake", "outcome", "--pr", "12", "--kind", "card", "--danger", "no"]) == 0
    card, outcome = [
        json.loads(x) for x in (own_state_dir / "brakes.jsonl").read_text().splitlines()
    ]
    assert (card["type"], card["verdict"], card["pr"]) == ("card", "BLOCKING", "12")
    assert (outcome["type"], outcome["kind"], outcome["danger"]) == ("outcome", "card", "no")
    verdict.write_text("no verdict here\n")
    assert wr.main(["brake", "card", "--pr", "12", "--file", str(verdict)]) == 2


def test_a_marker_worker_names_its_lead(world):
    gd = subprocess.run(
        ["git", "-C", str(world["repo"]), "rev-parse", "--absolute-git-dir"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    Path(gd, "we-worker.json").write_text(
        json.dumps({"name": "ABC-12-hook", "key": KEY, "lead": "LEAD-1", "session_id": "s-w"})
    )
    decision, reason = hook(
        world, "gh secret set X", session="s-w", WE_ROLE=None, WE_STORY_KEY=None
    )
    assert decision == "deny" and reason.endswith("ask your Lead LEAD-1")
    disarm = "gh pr merge 7 --disable-auto"
    assert hook(world, disarm, session="s-w", WE_ROLE=None, WE_STORY_KEY=None)[0] == "allow"
    # the Lead in the same tree is no worker
    assert hook(world, "gh secret set X", session="s-lead", WE_ROLE=None) == (None, "")


def _crash(world, monkeypatch, command, role="worker"):
    """Run the hook on `command` while `decide` raises."""
    sys.path.insert(0, str(HOOK.parent))
    import worker_rights_gate as gate  # noqa: PLC0415

    def boom(_payload, _env):
        raise RuntimeError("token=s3cr3t")

    monkeypatch.setattr(gate, "decide", boom)
    payload = {"tool_name": "Bash", "tool_input": {"command": command}, "cwd": str(world["repo"])}
    monkeypatch.setenv("WE_ROLE", role)
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(payload)))
    gate.main()


def test_a_crash_fails_open_with_one_stderr_line_and_one_crash_row(
    world, monkeypatch, capsys, own_state_dir
):
    for role in ("worker", "master"):
        _crash(world, monkeypatch, "git status", role)
        out, err = capsys.readouterr()
        assert out == ""  # no decision: the normal permissions judge the call
        assert err.count("\n") == 1 and "RuntimeError" in err
    log = (own_state_dir / "brakes.jsonl").read_text()
    assert "s3cr3t" not in log  # the exception's message never reaches the persistent log
    rows = [json.loads(x) for x in log.splitlines()]
    assert [(r["type"], r["gate"], r["error"]) for r in rows] == [
        ("crash", "worker_rights_gate", "RuntimeError")
    ] * 2
    assert all("outcome" not in r and "item" not in r for r in rows)  # `outcome` judges a line
    assert rows[0]["argv0"] == "git"


@pytest.mark.usefixtures("own_state_dir")
@pytest.mark.parametrize(
    ("command", "item"),
    [
        ("gh secret set X", "secrets"),
        ("gh repo delete acme/app --yes", "delete"),
        ("git push origin --delete feat/x", "delete"),
        ("git push origin HEAD:main", "main"),
        ("gh pr merge 7 --admin", "merge"),
    ],
)
def test_a_crash_still_denies_the_hard_prod_part(world, monkeypatch, capsys, command, item):
    _crash(world, monkeypatch, command)
    out = json.loads(capsys.readouterr().out)["hookSpecificOutput"]
    assert out["permissionDecision"] == "deny"
    assert out["permissionDecisionReason"].startswith(f"never for a worker ({item}")


# ---------------------------------------------------------------- the settings record (AC 8)


def _base_allow():
    script = SCRIPTS / "pr_ready.sh"
    return [
        "Bash(gh pr ready*)",
        f"Bash({script} *)",
        f"Bash(bash {script} *)",
        "Bash(gh pr comment*)",
    ]


def test_settings_allow_ready_and_comment_and_deny_the_never_list(world):
    doc = wr.settings(world["repo"], KEY)
    assert doc["permissions"]["allow"] == [*_base_allow(), "Bash(a release staging*)"]
    deny = doc["permissions"]["deny"]
    for rule in (
        "Bash(*gh secret *)",
        "Bash(*git push* main)",
        "Bash(*git*commit*--no-verify*)",
        "Bash(*core.hooksPath*commit*)",
        "Bash(*SKIP=*gitleaks*commit*)",
        "Bash(*secret-pipe.sh*)",
        "Read(//dev/shm/vault-**)",
    ):
        assert rule in deny
    assert not [r for r in deny if "ALLOW_" in r or r in ("Bash(*--no-verify*)",)]
    assert doc["env"] == {
        "WE_ROLE": "worker",
        "WE_STORY_KEY": KEY,
        "WESIDE_COMPANION": "",
        "WE_ROLE_ID": "",
        "WE_START": "",
        "WE_WORKER_STARTER": "",
        "WE_STARTER": "",
        "WE_WORKER_NAME": "",
        "WE_WORKER_LANE": "build",
    }
    assert wr.settings(world["repo"], KEY, starter="Samu")["env"]["WE_STARTER"] == "Samu"
    plain = make_repo(world["tmp"], name="plain", rights=None)
    assert wr.settings(plain, KEY)["permissions"]["allow"] == _base_allow()


# ---------------------------------------------------------------- the PR owner rights (build.pr_owner)


def _pr_owner(repo, value, publish=True):
    """`build.pr_owner` in the repo's config, committed on the branch; published to origin/main
    (where the gate reads it) unless `publish` is False."""
    (repo / ".weside").mkdir(exist_ok=True)
    (repo / ".weside" / "config.json").write_text(json.dumps({"build": {"pr_owner": value}}))
    _git(repo, "add", ".weside/config.json")
    _commit(repo, "config")
    if publish:
        _publish(repo)


def _head(repo):
    return subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "HEAD"], capture_output=True, text=True, check=True
    ).stdout.strip()


RESOLVE = (
    "gh api graphql -f query='mutation($id:ID!){resolveReviewThread(input:{threadId:$id})"
    "{thread{isResolved}}}' -f id=PRRT_1"
)
# commands the gate no longer judges for any owner (R6, R7): no decision, `settings` allows them
UNJUDGED = [
    "git push -u origin feat/ABC-12-hook",
    "git push",
    "git push origin HEAD:feat/ABC-99-other",
    "gh pr create --title x --body-file b.md",
    "gh pr create --head feat/ABC-99-other",
    "gh pr comment 8 --body x",
    RESOLVE,
]


@pytest.mark.parametrize("owner", ["master", "worker"])
@pytest.mark.parametrize("command", UNJUDGED)
def test_push_create_comment_and_resolve_stay_out_of_the_gate(world, owner, command):
    _pr_owner(world["repo"], owner)
    assert hook(world, command) == (None, "")


@pytest.mark.parametrize("command", ["arm_pr.sh 7", "gh pr edit 8 --remove-label hold"])
def test_under_master_the_pr_owner_rights_stay_out_of_the_gate(world, command):
    _hold_crew(world["repo"])
    _pr_owner(world["repo"], "master")
    assert hook(world, command) == (None, "")


@pytest.mark.parametrize(
    "command",
    [
        "gh pr edit 8 --add-label y --title z",
        "/plugin/scripts/arm_pr.sh 8 --method squash",
        "bash arm_pr.sh 8",
        "arm_pr.sh --repo other/app 7",
        "gh pr merge 7 --disable-auto",
    ],
)
def test_under_worker_the_pr_owner_rights_are_allowed(world, command):
    """R7 (own PR for an edit) and R9 (own PR for an arm) are gone: `arm_pr.sh` keeps hold
    labels and the one-way class itself."""
    _pr_owner(world["repo"], "worker")
    decision, reason = hook(world, command)
    assert decision == "allow", reason


needs_jq = pytest.mark.skipif(not shutil.which("jq"), reason="the fake gh delegates --jq to jq")
GREEN = [["Tests", "COMPLETED", "SUCCESS", True], ["Claude Review", "COMPLETED", "SUCCESS", True]]
MERGE_LINE = "gh pr merge 7 --merge --match-head-commit {sha}"


def _merge_line(
    world, read=None, required=("Tests", "Claude Review"), repo=None, line=None, **env
):
    """The worker's own merge line on its HEAD (or `line` with `{sha}` for it), with the PR read
    and the base's required names `arm_pr.sh --check` sees."""
    repo = repo or world["repo"]
    (world["tmp"] / "read.json").write_text(json.dumps(read if read is not None else {}))
    (world["tmp"] / "required.json").write_text(json.dumps(list(required)))
    return hook(
        world,
        (line or MERGE_LINE).replace("{sha}", _head(repo)),
        cwd=repo,
        FAKE_GH_READ=str(world["tmp"] / "read.json"),
        FAKE_GH_REQUIRED=str(world["tmp"] / "required.json"),
        **env,
    )


@needs_jq
@pytest.mark.parametrize("owner", ["master", "worker"])
def test_the_ready_merge_line_on_the_own_head_is_allowed_for_every_owner(world, owner):
    """R8 holds for every worker (N24 is gone): the merge line's own check holds the PROD facts."""
    _pr_owner(world["repo"], owner)
    decision, reason = _merge_line(world, {"checks": GREEN})  # every required name green
    assert decision == "allow", reason


@pytest.mark.parametrize("owner", ["master", "worker"])
@pytest.mark.parametrize(
    ("command", "why"),
    [
        ("gh pr merge 7 --merge", "without --match-head-commit"),
        ("gh pr merge 7 --squash --match-head-commit 0000000", "not this checkout's HEAD"),
        ("gh pr merge 7 --admin --match-head-commit {sha}", "gh pr merge --admin"),
        ("gh pr merge 7 --auto --match-head-commit {sha}", "gh pr merge --auto"),
        ("gh pr merge 7 --disable-auto --merge", "takes no other flag"),
        ("gh pr merge 7 --disable-auto && gh pr merge 7 --squash", "without --match-head-commit"),
        ("gh pr merge 8 --disable-auto", "not this branch's PR"),
        ("gh pr merge 7 -R acme/other --disable-auto", "another repo"),
    ],
)
def test_the_merge_line_is_denied_outside_its_conditions(world, owner, command, why):
    _pr_owner(world["repo"], owner)
    decision, reason = hook(world, command.replace("{sha}", _head(world["repo"])))
    assert decision == "deny" and why in reason, reason


@pytest.mark.parametrize(
    ("command", "item"),
    [
        ("git push origin main", "main (git push to main)"),
        ("gh pr merge 7 --delete-branch --match-head-commit abc1234", "delete (--delete-branch)"),
        ("git commit --no-verify -m x", "guard bypass"),
    ],
)
def test_under_worker_the_never_list_still_holds(world, command, item):
    _pr_owner(world["repo"], "worker")
    decision, reason = hook(world, command)
    assert decision == "deny" and item in reason


def test_the_worktrees_own_switch_grants_nothing(world):
    _pr_owner(world["repo"], "worker", publish=False)
    assert hook(world, "gh pr edit 7 --title x") == (None, "")
    assert hook(world, "arm_pr.sh 7") == (None, "")


def test_another_switch_value_opens_nothing(world):
    _pr_owner(world["repo"], "everyone")
    assert hook(world, "gh pr edit 7 --title x") == (None, "")


def test_settings_add_the_pr_owner_rules_only_under_worker(world):
    plain = make_repo(world["tmp"], name="plain", rights=None)
    _pr_owner(plain, "master")
    assert wr.settings(plain, KEY)["permissions"]["allow"] == _base_allow()
    _pr_owner(plain, "worker")
    allow = wr.settings(plain, KEY)["permissions"]["allow"]
    assert allow == _base_allow() + [r for r in wr.PR_OWNER_ALLOW if r not in _base_allow()]
    assert allow.count("Bash(gh pr comment*)") == 1


def _hold_crew(repo):
    body = {**CREW, "worker_rights": RIGHTS, "merge": {"hold_labels": ["hold"]}}
    (repo / ".weside" / "crew.json").write_text(json.dumps(body))
    _git(repo, "add", ".weside/crew.json")
    _commit(repo, "hold")
    _publish(repo)


@needs_jq
def test_under_worker_the_merge_line_is_denied_on_a_hold_label(world):
    _hold_crew(world["repo"])
    _pr_owner(world["repo"], "worker")
    decision, reason = _merge_line(world, {"checks": GREEN, "labels": ["hold"]})
    assert decision == "deny" and "refused: label hold — only the human merges it" in reason
    decision, reason = hook(world, "gh pr edit 7 --remove-label hold")
    assert decision == "deny" and "hold label" in reason
    assert hook(world, "gh pr edit 7 --remove-label other")[0] == "allow"


@needs_jq
@pytest.mark.parametrize(
    ("read", "required", "line"),
    [
        (
            {"checks": [GREEN[0], ["Claude Review", "COMPLETED", "FAILURE", True]]},
            ("Tests", "Claude Review"),
            "red: Claude Review on {sha} — not ready",
        ),
        # A required run not registered yet is absent, and absent is not green.
        ({"checks": [GREEN[0]]}, ("Tests", "Claude Review"), "pending: Claude Review on {sha}"),
        # No run of the head registered at all (gh: "no required checks reported").
        ({"checks": []}, ("Tests",), "no checks on {sha} — not ready"),
        (
            {"checks": [GREEN[0], ["Claude Review", "IN_PROGRESS", None, True]]},
            ("Tests", "Claude Review"),
            "pending: Claude Review on {sha}",
        ),
        (
            {"checks": GREEN, "merge": "BLOCKED", "review": "REVIEW_REQUIRED"},
            ("Tests", "Claude Review"),
            "not ready on {sha} (BLOCKED, review REVIEW_REQUIRED)",
        ),
        (
            {"checks": GREEN, "review": "CHANGES_REQUESTED"},
            ("Tests", "Claude Review"),
            "not ready on {sha} (CLEAN, review CHANGES_REQUESTED)",
        ),
        ({"fail": "HTTP 502"}, ("Tests",), "gh failed: HTTP 502"),
        (
            {"checks": GREEN, "head": "c" * 40},
            ("Tests",),
            "refused: head moved {sha} -> " + "c" * 40,
        ),
    ],
    ids=[
        "red",
        "required-absent",
        "no-run-registered",
        "pending",
        "review-required",
        "changes-requested",
        "gh-failure",
        "head-moved",
    ],
)
def test_under_worker_the_merge_line_is_denied_unless_arm_pr_says_ready(
    world, read, required, line
):
    _pr_owner(world["repo"], "worker")
    decision, reason = _merge_line(world, read, required)
    assert decision == "deny", reason
    assert f"arm_pr.sh --check: {line.replace('{sha}', _head(world['repo']))}" in reason, reason


def test_under_worker_the_merge_line_is_denied_when_the_pr_number_is_unreadable(world):
    _pr_owner(world["repo"], "worker")
    prs = json.loads((world["tmp"] / "prs.json").read_text())
    del prs["7"]["number"]
    (world["tmp"] / "prs.json").write_text(json.dumps(prs))
    decision, reason = _merge_line(world, {"checks": GREEN})
    assert decision == "deny" and "the PR number could not be read" in reason, reason


def test_the_merge_line_check_refuses_at_its_deadline_and_kills_the_check_group(
    world, tmp_path, monkeypatch
):
    """Red arm: an `arm_pr.sh --check` that hangs (here with a child of its own) is cut at the
    merge line's one deadline, refused with that reason, and leaves no process behind."""
    pid_file = tmp_path / "child.pid"
    fake = tmp_path / "arm_pr.sh"
    fake.write_text(f"sleep 60 &\necho $! > {pid_file}\nsleep 60\necho 'ready: never'\n")
    monkeypatch.setattr(wr, "ARM_PR", fake)
    started = time.monotonic()
    reason = wr._merge_facts_refusal(7, "acme/app", str(world["repo"]), started + 1.0)
    assert time.monotonic() - started < 5, "the check ran past its deadline"
    assert "arm_pr.sh --check ran past the worker gate's" in reason, reason
    child = int(pid_file.read_text())
    for _ in range(50):  # the killed child is reaped by init; give it a moment
        try:
            os.kill(child, 0)
        except ProcessLookupError:
            break
        time.sleep(0.05)
    else:
        pytest.fail(f"orphan {child} of arm_pr.sh --check survived the timeout")


def test_the_merge_line_check_refuses_once_the_deadline_is_spent(world):
    reason = wr._merge_facts_refusal(7, "acme/app", str(world["repo"]), time.monotonic() - 1)
    assert "ran past the worker gate's" in reason, reason
    assert wr._own_pr("7", "acme/app", BRANCH, str(world["repo"]), time.monotonic() - 1)[0]


def _marker_worker(world, session="s-w"):
    """The `worker_launch.py` marker naming `session` as the worker of this tree."""
    gd = subprocess.run(
        ["git", "-C", str(world["repo"]), "rev-parse", "--absolute-git-dir"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    Path(gd, "we-worker.json").write_text(
        json.dumps({"name": "ABC-12-hook", "key": KEY, "lead": "LEAD-1", "session_id": session})
    )


@needs_jq
@pytest.mark.parametrize("by", ["env", "marker"])
def test_under_worker_the_merge_line_is_denied_on_a_one_way_class(world, by):
    """Red arm (marker): `arm_pr.sh --check` ran with the worker's env, and a worker known by its
    marker only got `ready` for a one-way class, which `arm_pr.sh` no longer refuses by itself."""
    repo = world["repo"]
    (repo / ".weside" / "risk-paths").write_text("[brake-change]\npath src/brake.py\n")
    _git(repo, "add", ".weside/risk-paths")
    _commit(repo, "risk")
    _pr_owner(repo, "worker")
    (repo / "src").mkdir()
    (repo / "src" / "brake.py").write_text("x = 1\n")
    _git(repo, "add", "src/brake.py")
    _commit(repo, "brake")
    env = {}
    if by == "marker":
        _marker_worker(world)
        env = {"session": "s-w", "WE_ROLE": None, "WE_STORY_KEY": None}
    decision, reason = _merge_line(world, {"checks": GREEN}, **env)
    assert decision == "deny" and "refused: one-way brake-change" in reason, reason


def test_a_worker_known_by_its_marker_only_arms_nothing(world):
    """`arm_pr.sh` refuses a worker's one-way class by `WE_ROLE=worker`; without it in the env the
    arm would pass as a session's, so the gate denies the right."""
    _pr_owner(world["repo"], "worker")
    _marker_worker(world)
    decision, reason = hook(world, "arm_pr.sh 7", session="s-w", WE_ROLE=None, WE_STORY_KEY=None)
    assert decision == "deny" and "arm_pr.sh without WE_ROLE=worker" in reason, reason


def test_a_spent_hook_deadline_refuses_every_gated_gh_read(world):
    """The hook passes one deadline to every command of a call: a second merge part after the
    first spent the budget refuses instead of running past the hook's timeout (which lets it by)."""
    spent = time.monotonic() - 1
    argv = ["gh", "pr", "merge", "7", "--disable-auto"]
    reason = wr.right_refusal(argv, "merge", str(world["repo"]), spent)
    assert reason and "ran past the worker gate's" in reason, reason


def test_the_sourced_devbox_env_passes_and_a_never_item_behind_it_does_not(world):
    """The app-verification form a repo prescribes sources its devbox env, alone or before its
    shell check: no decision. The same prefix before a never-list item is denied as before."""
    source = ". " + '"$(' + "a devbox env --path" + ')"'
    assert hook(world, source) == (None, "")
    assert hook(world, source + " && scripts/dev/shell-verify.sh /home") == (None, "")
    decision, reason = hook(world, source + " && cat /dev/shm/" + "vault-1000/x.json")
    assert decision == "deny", reason
    assert reason.startswith("never for a worker (crew deny_text (/dev/shm/vault-)")


# ---------------------------------------------------------------- the deletion test (WA plan rows)

# one denied command per staying `NEVER` row, keyed by its item template: a row added without a
# case here fails `test_every_staying_row_has_a_red_arm`
RED_ARMS = {
    "secrets (gh {0})": "gh secret set X",
    "secrets (gh api write on /{0})": "gh api -X PUT repos/acme/app/actions/secrets/X",
    "delete (gh {0} {1})": "gh release delete v1",
    "delete (gh api with method DELETE)": "gh api -X DELETE repos/acme/app/hooks/1",
    "delete (--delete-branch)": "gh pr close 7 --delete-branch",
    "delete (gh pr close -d)": "gh pr close 7 -d",
    "delete (git push --delete)": "git push origin --delete feat/x",
    "delete (git push {0})": "git push origin :feat/x",
    "main (git push to {0})": "git push origin main",
    "main (git push of a ref pattern)": "git push origin 'refs/heads/*:refs/heads/*'",
    "main (git push {0})": "git push --mirror origin",
    "guard bypass (git push of a tag)": "git push --follow-tags",
    "guard bypass (git commit --no-verify)": "git commit --no-verify -m x",
    "guard bypass (git commit -n)": "git commit -n -m x",
    "guard bypass (core.hooksPath on a commit)": "git -c core.hooksPath=/dev/null commit -m x",
    "guard bypass (SKIP=gitleaks)": "SKIP=gitleaks git commit -m x",
    "merge (gh pr merge {0})": "gh pr merge 7 --admin",
}
# the staying checks outside `NEVER`, each with a command and the start of its denial
EXTRA_ARMS = [
    ("git push", "never for a worker (main (a git push from main:"),  # on main
    ("git push origin v9.9.9", "never for a worker (guard bypass (git push of the tag v9.9.9)"),
    ("cat /dev/shm/vault-1/x", "never for a worker (crew deny_text (/dev/shm/vault-)"),
    ("secret-pipe.sh NAME", "never for a worker (secrets (crew deny_commands: secret-pipe.sh)"),
    (
        "bash -c 'gh pr merge 7 --squash'",
        "never for a worker (merge (gh pr merge only as a visible",
    ),
    ("env arm_pr.sh 7", "not a worker right (arm behind env"),
    ("gh pr merge 7 --squash", "not a worker right (gh pr merge without --match-head-commit"),
    ("gh pr edit 7 --remove-label hold", "not a worker right (gh pr edit --remove-label hold"),
]


def test_every_staying_row_has_a_red_arm(world):
    """AC 1: every staying row of the deletion test denies its command, and a `NEVER` row added
    later without a case here fails."""
    assert {item for item, _pattern in wr.NEVER} == set(RED_ARMS)
    for template, command in RED_ARMS.items():
        found = wr.never(command, str(world["repo"]), {})
        prefix = template.split("{", 1)[0]
        assert found and found.startswith(prefix), (command, found)
    _hold_crew(world["repo"])
    _pr_owner(world["repo"], "worker")
    _git(world["repo"], "tag", "v9.9.9")
    for command, denial in EXTRA_ARMS:
        cwd = world["repo"]
        if command == "git push":
            cwd = make_repo(world["tmp"], name="on-main", branch="main")
        decision, reason = hook(world, command, cwd=cwd)
        assert decision == "deny" and reason.startswith(denial), (command, reason)
    # R9b: an arm by a worker known by its marker only, without the variable `arm_pr.sh` reads
    _marker_worker(world)
    decision, reason = hook(world, "arm_pr.sh 7", session="s-w", WE_ROLE=None, WE_STORY_KEY=None)
    assert decision == "deny" and "arm_pr.sh without WE_ROLE=worker" in reason, reason


# what each deleted row or refusal branch said: none of it is left in the code
REMOVED = [
    "ALLOW_COMMIT_TO_MAIN",
    "ALLOW_PUSH_WITHOUT_MAIN",
    "--delete-last",
    "beside a change of WE_ROLE",
    "merges only under build.pr_owner",
    "only as a command of its own)",
    "grants no worker rights",
    "is not granted in",
    "without a story key",
    "does not carry the key",
    "is the default branch, not the worker's own",
    "pushes only branches carrying",
    "opens the PR of its own branch",
    "resolveReviewThread as the only mutation",
    "a comment in another repo",
    "pr_ready.sh without a PR",
    "and its default branch does not set build.pr_owner",
    "def opted_in",
    "RIGHT_NAMES",
]


def test_every_removed_row_is_gone(world):
    """AC 1: the rows that go are absent from the gate's code, and their commands pass."""
    code = (SCRIPTS / "worker_rights.py").read_text() + HOOK.read_text()
    assert [r for r in REMOVED if r in code] == []
    for command in (
        "gh pr comment 7 --delete-last --yes",  # N7
        "ALLOW_COMMIT_TO_MAIN=1 git commit -m x",  # N13
        "ALLOW_PUSH_WITHOUT_MAIN=1 git push origin HEAD",  # N15
        "git push --no-verify origin HEAD",  # N16 off a commit
        "git -c core.hooksPath=/dev/null diff",  # N17 off a commit
        "unset WE_ROLE; echo arm_pr.sh 7",  # N20
    ):
        assert hook(world, command) == (None, ""), command


@pytest.mark.parametrize(
    "command",
    [
        "SKIP=backend-lock git commit -m x -- a.py",
        "SKIP=ruff-format,mypy git commit -m x",
        "git -c core.hooksPath=/dev/null status",
        "git config --get core.hooksPath",
        f"git push --no-verify origin {BRANCH}",
        "git -c core.hooksPath=/dev/null worktree add ../t -b feat/ABC-12-t",
    ],
)
def test_a_local_hook_skip_is_no_refusal(world, command):
    """AC 2: a skip of a local hook other than the secret scan, a read or a push hurts nothing: no
    decision and no line in the brake log."""
    state = world["tmp"] / "state"
    assert hook(world, command, WE_STATE_DIR=str(state)) == (None, "")
    assert not (state / "brakes.jsonl").exists()


@needs_jq
def test_the_three_brakes_of_the_walk(world):
    """AC 4: the three brakes of the value-stream walk, replayed for a worker whose crew grants
    nothing: the skip reply and the chained push pass, the merge line in its chain is judged by the
    merge line (passes on `ready`, denied on `failed`)."""
    repo = make_repo(world["tmp"], name="infra", rights=None)
    prs = json.loads((world["tmp"] / "prs.json").read_text())
    prs["7"]["headRepository"]["name"] = "infra"
    (world["tmp"] / "prs.json").write_text(json.dumps(prs))
    reply = "gh pr comment 31 -R acme/infra --body 'Codex finding skipped: covered by the test'"
    assert hook(world, reply, cwd=repo) == (None, "")
    assert hook(world, f"git push origin {BRANCH} && {reply}", cwd=repo) == (None, "")
    chain = "gh pr merge 7 --merge --match-head-commit {sha} 2>&1 | tail -2; gh pr view 7"
    assert _merge_line(world, {"checks": GREEN}, repo=repo, line=chain) == (None, "")
    failed = [GREEN[0], ["Claude Review", "COMPLETED", "FAILURE", True]]
    decision, reason = _merge_line(world, {"checks": failed}, repo=repo, line=chain)
    assert decision == "deny" and "arm_pr.sh --check: red: Claude Review" in reason, reason


@needs_jq
def test_a_merge_part_in_a_chain_is_judged_on_its_part(world):
    chain = "gh pr merge 7 --merge --match-head-commit {sha} 2>&1 | tail -2; gh pr view 7"
    assert _merge_line(world, {"checks": GREEN}, line=chain) == (None, "")
    decision, reason = _merge_line(world, {"fail": "HTTP 502"}, line=chain)
    assert decision == "deny" and "gh failed: HTTP 502" in reason, reason
    # red arm: a disarm, then a commit whose message opens a quote on one line and closes it on a
    # later one; read line by line, the disarm's `2>&1` lost its part and the chain was "never"
    commit = (
        'cd . && gh pr merge 7 --disable-auto 2>&1 | tail -1; git commit -q -m "fix: the '
        "member's row\n\nthe body\" > /tmp/c.txt 2>&1 && git log --oneline -1"
    )
    assert hook(world, commit) == (None, "")
    decision, reason = hook(world, "bash -c 'gh pr merge 7 --squash'")
    assert decision == "deny" and "only as a visible part" in reason, reason
