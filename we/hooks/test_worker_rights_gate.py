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
    "repos": ["acme/app"],
    "pr_ready": True,
    "pr_comment": True,
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


# ---------------------------------------------------------------- AC 5: the rights pass


@pytest.mark.parametrize(
    "command",
    [
        "gh pr ready",
        "gh pr ready 7",
        "/plugin/scripts/pr_ready.sh 7 ready --sha 0123abc",
        "bash pr_ready.sh 7 undo 'waits on the lens — ready when it passes'",
        "gh pr comment --body x",
        "gh pr comment 7 --body x",
        "gh pr comment -R acme/app 7 -b x",
        "gh pr comment https://github.com/acme/app/pull/7 --body x",
        "a release staging",
        'gh pr comment --body "Fixed \\`foo\\` in bar"',
    ],
)
def test_a_held_right_is_allowed_without_a_prompt(world, command):
    prs = json.loads((world["tmp"] / "prs.json").read_text())
    prs["https://github.com/acme/app/pull/7"] = prs["7"]
    (world["tmp"] / "prs.json").write_text(json.dumps(prs))
    decision, reason = hook(world, command)
    assert decision == "allow", reason


def test_a_held_right_in_a_compound_command_only_passes(world):
    assert hook(world, "git status && gh pr ready") == (None, "")


@pytest.mark.parametrize(
    ("command", "why"),
    [
        ("cd /x && gh pr ready 8", "not this branch's PR"),
        ("cd . && gh pr comment 8 --body 'skipped: x'", "not this branch's PR"),
        ("git status; gh pr ready -R acme/other", "another repo"),
        ("true || gh pr comment 8 -b x", "not this branch's PR"),
        ("echo x | gh pr ready 8", "not this branch's PR"),
        ("cd .\ngh pr ready 8", "not this branch's PR"),
        ("gh pr ready && gh pr comment 8 --body x", "not this branch's PR"),
        ("pr_ready.sh 8 ready", "not this branch's PR"),
        ("bash pr_ready.sh -R acme/other 7 ready", "another repo"),
        ("pr_ready.sh --sha 0123abc", "pr_ready.sh without a PR"),
        ("cd . && pr_ready.sh 8 ready", "not this branch's PR"),
    ],
)
def test_a_right_inside_a_command_chain_is_judged_on_its_segment(world, command, why):
    decision, reason = hook(world, command)
    assert decision == "deny" and why in reason, reason


def test_a_release_inside_a_command_chain_is_judged_on_the_branch(world):
    _git(world["repo"], "checkout", "-q", "-b", "feat/other")
    decision, reason = hook(world, "cd . && a release staging rc")
    assert decision == "deny" and f"does not carry the key {KEY}" in reason


@pytest.mark.parametrize(
    ("command", "right"),
    [
        ("env gh pr ready 6999", "pr_ready behind env"),
        ("command gh pr ready 6999", "pr_ready behind command"),
        ("GH_X=1 gh pr ready 6999", "pr_ready behind an assignment"),
        ("timeout 9 gh pr ready 6999", "pr_ready behind timeout"),
        ("nohup gh pr ready 6999", "pr_ready behind nohup"),
        ("exec gh pr ready 6999", "pr_ready behind exec"),
        ("echo 6999 | xargs gh pr ready", "pr_ready behind xargs"),
        ("env gh pr ready 7", "pr_ready behind env"),
        ("env gh pr comment 6999 --body 'Codex #1 skipped: x'", "pr_comment behind env"),
        ("env a release staging rc", "branch_rc behind env"),
        ("bash -c 'a release staging rc'", "branch_rc in bash -c"),
        ("bash -c 'gh pr ready 6999'", "pr_ready in bash -c"),
        ("sh -c 'cd . && gh pr comment 6999 -b x'", "pr_comment in sh -c"),
        ("env bash -lc 'gh pr ready 6999'", "pr_ready in bash -c"),
        ('eval "gh pr ready 6999"', "pr_ready in eval"),
        ("echo `gh pr ready 6999`", "pr_ready in a command substitution"),
        ('echo "$(gh pr ready 6999)"', "pr_ready in a command substitution"),
        ("x=$(gh pr ready 7)", "pr_ready in a command substitution"),
        ("bash -c 'eval \"env gh pr ready 6999\"'", "pr_ready behind env in eval in bash -c"),
    ],
)
def test_a_right_behind_a_wrapper_or_in_a_nested_shell_is_refused(world, command, right):
    """Security card #276 a71e339 WARNING 2: a right holds only as a command of its own."""
    decision, reason = hook(world, command)
    assert decision == "deny", reason
    assert f"not a worker right ({right}: a right only as a command of its own" in reason, reason


@pytest.mark.parametrize(
    "command",
    [
        "{ gh pr ready 8; }",
        "if true; then gh pr ready 8; fi",
        "while false; do gh pr ready 8; done",
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


# ---------------------------------------------------------------- AC 6: the rights' conditions


def test_another_pr_is_denied(world):
    decision, reason = hook(world, "gh pr comment 8 --body x")
    assert (
        decision == "deny"
        and "not this branch's PR" in reason
        and reason.endswith("ask your starter")
    )


def test_a_pr_from_a_fork_is_denied(world):
    decision, reason = hook(world, "gh pr ready 10")
    assert decision == "deny" and "comes from fork/app" in reason


@pytest.mark.parametrize(
    "command",
    [
        "gh pr ready -R acme/other",
        "gh -R acme/other pr comment --body x",
        "gh pr ready --repo=acme/other",
    ],
)
def test_another_repo_is_denied(world, command):
    decision, reason = hook(world, command)
    assert decision == "deny" and "another repo" in reason


def test_the_default_branch_is_denied(world):
    _git(world["repo"], "checkout", "-q", "main")
    decision, reason = hook(world, "gh pr ready")
    assert decision == "deny" and "default branch" in reason


def test_a_branch_without_the_key_is_denied(world):
    _git(world["repo"], "checkout", "-q", "-b", "feat/other")
    decision, reason = hook(world, "a release staging")
    assert decision == "deny" and f"does not carry the key {KEY}" in reason


def test_a_repo_without_rights_is_denied(world):
    repo = make_repo(world["tmp"], name="plain", rights=None)
    decision, reason = hook(world, "gh pr ready", cwd=repo)
    assert decision == "deny" and "grants no worker rights" in reason


def test_a_repo_without_a_crew_is_denied(world):
    repo = make_repo(world["tmp"], name="nocrew", crew=False)
    decision, reason = hook(world, "gh pr comment --body x", cwd=repo)
    assert decision == "deny" and "acme/nocrew grants no worker rights" in reason


def test_a_repo_pointing_at_another_repos_crew_is_denied(world):
    """The infrastructure case: its config.json points `crew` at the core repo's crew file."""
    infra = make_repo(world["tmp"], name="infra", crew=False, branch="main")
    (infra / ".weside").mkdir()
    pointer = os.path.relpath(world["repo"] / ".weside" / "crew.json", infra)
    (infra / ".weside" / "config.json").write_text(json.dumps({"crew": pointer}))
    _git(infra, "add", ".weside")
    _commit(infra, "pointer")
    _publish(infra)
    _git(infra, "checkout", "-q", "-b", BRANCH)
    decision, reason = hook(world, "gh pr ready", cwd=infra)
    assert decision == "deny" and "acme/infra grants no worker rights" in reason


def test_a_right_the_crew_does_not_grant_is_denied(world):
    repo = make_repo(world["tmp"], name="half", rights={"repos": ["acme/half"], "pr_ready": True})
    decision, reason = hook(world, "gh pr comment --body x", cwd=repo)
    assert decision == "deny" and "pr_comment is not granted" in reason
    assert hook(world, "gh pr ready", cwd=repo)[0] == "allow"


def test_a_worker_without_a_key_is_denied(world):
    decision, reason = hook(world, "gh pr ready", WE_STORY_KEY=None)
    assert decision == "deny" and "without a story key" in reason


def test_a_gh_failure_while_resolving_the_pr_denies(world):
    decision, reason = hook(world, "gh pr ready 9")
    assert decision == "deny" and "could not be resolved" in reason


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
    ("ALLOW_COMMIT_TO_MAIN=1 git commit -m x", "main (ALLOW_COMMIT_TO_MAIN)"),
    ("git push origin v1.2.3-rc.1", "guard bypass (git push of the tag v1.2.3-rc.1)"),
    ("git push origin refs/tags/v9", "guard bypass (git push of a tag)"),
    ("git push origin tag v9", "guard bypass (git push of a tag)"),
    ("git push --tags", "guard bypass (git push of a tag)"),
    ("ALLOW_PUSH_WITHOUT_MAIN=1 git push origin HEAD", "guard bypass (ALLOW_PUSH_WITHOUT_MAIN)"),
    ("git push --no-verify origin HEAD", "guard bypass (--no-verify)"),
    ("git commit --no-verify -m x", "guard bypass (--no-verify)"),
    ("git commit -nm x", "guard bypass (git commit -n)"),
    ("git -c core.hooksPath=/dev/null push origin HEAD", "guard bypass (core.hooksPath)"),
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
    ("git push --no-verif origin HEAD", "guard bypass (--no-verify)"),
    ("git config core.hookspath /dev/null", "guard bypass (core.hooksPath)"),
    ('echo "`gh secret list`"', "secrets (gh secret)"),
    ("cd ../main-checkout && git push", None),
    # the never-list through git's own place flags
    ("git --git-dir=.git push origin main", "main (git push to main)"),
    ("git --work-tree . push --delete origin feat/x", "delete (git push --delete)"),
    ("git -C ../main-checkout push", None),
    # a merge other than the line arm_pr.sh prints
    ("gh pr merge 7 --admin", "merge (gh pr merge --admin)"),
    ("gh pr merge 7 --auto --squash", "merge (gh pr merge --auto)"),
    ("gh pr merge 7 --merge", "merge (a worker merges only under build.pr_owner: worker)"),
    (
        "gh pr merge 7 --disable-auto && gh pr merge 7 --squash",
        "merge (gh pr merge only as a command of its own)",
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
        "cat <<'EOF' > body.md\nnever --no-verify here? it is data\nEOF",
        "echo 'literal $(gh secret set X)'",
        "git commit -m \"$(cat <<'EOF'\nfeat: x\n\nnot --no-verify, data\nEOF\n)\" && git log -1",
        "sed -n '1,5p' f; cat > /tmp/x <<EOF\ngh secret set X\nEOF",
    ],
)
def test_data_naming_a_never_item_is_denied_like_the_settings_deny_rules(world, command):
    """No parser tells data from a command: the gate denies what the `--settings` deny globs
    (`Bash(*--no-verify*)`, `Bash(*gh secret *)`) already deny for the same text."""
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
    decision, reason = hook(world, command.format(tree=tree, gitdir=gitdir), cwd=main)
    assert decision == "allow", reason


@pytest.mark.parametrize(
    ("command", "why"),
    [
        # a second push without its own place may run in the cwd, which is on main
        ("git -C {tree} push; git push", "main (a git push from main:"),
        ("git -C {tree} push && git -C {main} push", "main (a git push from main:"),
        ("cd {tree} && git push", "main (a git push from main:"),
        ("git -C {tree} push origin main", "main (git push to main)"),
        ("git -C {tree} push origin HEAD:feat/ABC-99-x", "pushes only branches carrying ABC-12"),
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
    decision, reason = hook(world, text, cwd=main)
    assert decision == "allow", reason


def test_a_push_spelt_apart_is_judged_where_it_runs(world):
    main, _tree = _main_checkout_with_tree(world)
    decision, reason = hook(world, "gi''t push", cwd=main)
    assert decision == "deny" and "main (a git push from main:" in reason, reason


def test_a_tag_is_judged_in_every_place_a_push_runs(world):
    other = make_repo(world["tmp"], name="other", branch="feat/ABC-12-x")
    _git(other, "tag", "v-only-there")
    decision, reason = hook(world, f"git -C {other} push origin v-only-there")
    assert decision == "deny" and "git push of the tag v-only-there" in reason, reason


@pytest.mark.parametrize(
    "command",
    [
        "git --git-dir={other}/.git push origin feat/ABC-12-x",
        "git --work-tree {repo} --git-dir {other}/.git push origin feat/ABC-12-x",
    ],
)
def test_a_push_through_git_dir_reads_the_switch_of_that_repo(world, command):
    # the switch is read with git's own place options: rooted by --show-toplevel, a --git-dir
    # alone read the session's repo as top level and its build.pr_owner opened the other repo
    _pr_owner(world["repo"], "worker")
    other = make_repo(world["tmp"], name="other", owner="evil", branch="feat/ABC-12-x")
    text = command.format(other=other, repo=world["repo"])
    decision, reason = hook(world, text)
    assert decision == "deny" and "another repo than acme/app" in reason, reason
    _pr_owner(other, "worker")
    assert hook(world, text)[0] == "allow"


@pytest.mark.parametrize("switch", [None, "master"])
def test_a_push_into_another_repo_needs_that_repos_own_switch(world, switch):
    _pr_owner(world["repo"], "worker")
    other = make_repo(world["tmp"], name="other", owner="evil", branch="feat/ABC-12-x")
    if switch:
        _pr_owner(other, switch)
    decision, reason = hook(world, f"git -C {other} push origin feat/ABC-12-x")
    assert decision == "deny" and "another repo than acme/app" in reason, reason
    _pr_owner(other, "worker")  # the other repo's own default branch opens it
    assert hook(world, f"git -C {other} push origin feat/ABC-12-x")[0] == "allow"


def test_every_denial_is_one_line_in_brakes_jsonl_without_the_command(world):
    state = world["tmp"] / "state"
    decision, _reason = hook(world, "printf s3cr3t-value | wsec put NAME", WE_STATE_DIR=str(state))
    assert decision == "deny"
    hook(world, "gh pr ready 8", WE_STATE_DIR=str(state))
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
    assert hook(world, "gh pr ready", session="s-w", WE_ROLE=None, WE_STORY_KEY=None)[0] == "allow"
    # the Lead in the same tree is no worker
    assert hook(world, "gh secret set X", session="s-lead", WE_ROLE=None) == (None, "")


@pytest.mark.usefixtures("own_state_dir")
def test_an_error_while_judging_fails_closed(world, monkeypatch, capsys):
    sys.path.insert(0, str(HOOK.parent))
    import worker_rights_gate as gate  # noqa: PLC0415

    def boom(_payload, _env):
        raise RuntimeError("x")

    monkeypatch.setattr(gate, "decide", boom)
    payload = {
        "tool_name": "Bash",
        "tool_input": {"command": "git status"},
        "cwd": str(world["repo"]),
    }
    for role, denied in (("worker", True), ("master", False)):
        monkeypatch.setenv("WE_ROLE", role)
        monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(payload)))
        gate.main()
        assert ("fail closed" in capsys.readouterr().out) is denied


def test_a_broken_crew_costs_the_rights_not_the_worker(world):
    (world["repo"] / ".weside" / "crew.json").write_text(
        json.dumps({**CREW, "worker_rights": {"repos": "acme/app"}})
    )
    _git(world["repo"], "add", ".weside")
    _commit(world["repo"], "broken")
    _publish(world["repo"])
    assert hook(world, "git status") == (None, "")
    assert hook(world, "gh pr ready")[0] == "deny"
    assert hook(world, "gh secret set X")[0] == "deny"


def test_the_worktrees_own_crew_edit_grants_nothing(world):
    repo = make_repo(world["tmp"], name="plain", rights=None)
    (repo / ".weside" / "crew.json").write_text(
        json.dumps({**CREW, "worker_rights": {**RIGHTS, "repos": ["acme/plain"]}})
    )
    decision, reason = hook(world, "gh pr ready", cwd=repo)
    assert decision == "deny" and "grants no worker rights" in reason


def test_a_shorter_key_does_not_own_a_longer_keys_branch(world):
    _git(world["repo"], "checkout", "-q", "-b", "feat/ABC-123-other")
    decision, reason = hook(world, "gh pr ready")
    assert decision == "deny" and "does not carry the key ABC-12" in reason


# ---------------------------------------------------------------- the settings record (AC 8)


def test_settings_grant_exactly_the_repos_rights_and_deny_the_never_list(world):
    doc = wr.settings(world["repo"], KEY)
    assert doc["permissions"]["allow"] == [
        "Bash(gh pr ready*)",
        f"Bash({SCRIPTS / 'pr_ready.sh'} *)",
        f"Bash(bash {SCRIPTS / 'pr_ready.sh'} *)",
        "Bash(gh pr comment*)",
        "Bash(a release staging*)",
    ]
    deny = doc["permissions"]["deny"]
    for rule in (
        "Bash(*gh secret *)",
        "Bash(*git push* main)",
        "Bash(*--no-verify*)",
        "Bash(*secret-pipe.sh*)",
        "Read(//dev/shm/vault-**)",
    ):
        assert rule in deny
    assert doc["env"] == {
        "WE_ROLE": "worker",
        "WE_STORY_KEY": KEY,
        "WESIDE_COMPANION": "",
        "WE_ROLE_ID": "",
        "WE_START": "",
        "WE_WORKER_STARTER": "",
        "WE_STARTER": "",
    }
    assert wr.settings(world["repo"], KEY, starter="Samu")["env"]["WE_STARTER"] == "Samu"
    plain = make_repo(world["tmp"], name="plain", rights=None)
    assert wr.settings(plain, KEY)["permissions"]["allow"] == []


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


MERGE_DENY = "never for a worker (merge (a worker merges only under build.pr_owner: worker))"

RESOLVE = (
    "gh api graphql -f query='mutation($id:ID!){resolveReviewThread(input:{threadId:$id})"
    "{thread{isResolved}}}' -f id=PRRT_1"
)
PR_OWNER_COMMANDS = [
    "git push -u origin feat/ABC-12-hook",
    "git push",
    "git push origin HEAD:wip/ABC-12-hook",
    "gh pr create --title x --body-file b.md",
    "gh pr edit 7 --add-label y --title z",
    "gh pr comment 7 --body x",
    "/plugin/scripts/arm_pr.sh 7 --method squash",
    "gh pr merge 7 --disable-auto",
    RESOLVE,
]


@pytest.mark.parametrize(
    "command", [*PR_OWNER_COMMANDS[:3], "gh pr merge 7 --merge", "arm_pr.sh 7"]
)
def test_under_master_the_pr_owner_rights_stay_out_of_the_gate(world, command):
    _pr_owner(world["repo"], "master")
    decision, reason = hook(world, command)
    if "gh pr merge" in command:  # a worker under master never merges
        assert decision == "deny" and reason.startswith(MERGE_DENY), reason
    else:
        assert (decision, reason) == (None, "")


@pytest.mark.parametrize("command", PR_OWNER_COMMANDS)
def test_under_worker_the_pr_owner_rights_are_allowed(world, command):
    repo = make_repo(
        world["tmp"], name="app2", rights=None
    )  # no worker_rights: the switch opts in
    prs = json.loads((world["tmp"] / "prs.json").read_text())
    prs["7"]["headRepository"]["name"] = "app2"
    (world["tmp"] / "prs.json").write_text(json.dumps(prs))
    _pr_owner(repo, "worker")
    decision, reason = hook(world, command, cwd=repo)
    assert decision == "allow", reason


needs_jq = pytest.mark.skipif(not shutil.which("jq"), reason="the fake gh delegates --jq to jq")
GREEN = [["Tests", "COMPLETED", "SUCCESS", True], ["Claude Review", "COMPLETED", "SUCCESS", True]]


def _merge_line(world, read=None, required=("Tests", "Claude Review"), repo=None, **env):
    """The worker's own merge line on its HEAD, with the PR read and the base's required names
    `arm_pr.sh --check` sees."""
    repo = repo or world["repo"]
    (world["tmp"] / "read.json").write_text(json.dumps(read if read is not None else {}))
    (world["tmp"] / "required.json").write_text(json.dumps(list(required)))
    return hook(
        world,
        f"gh pr merge 7 --merge --match-head-commit {_head(repo)}",
        cwd=repo,
        FAKE_GH_READ=str(world["tmp"] / "read.json"),
        FAKE_GH_REQUIRED=str(world["tmp"] / "required.json"),
        **env,
    )


@needs_jq
def test_under_worker_the_ready_merge_line_on_the_own_head_is_allowed(world):
    _pr_owner(world["repo"], "worker")
    decision, reason = _merge_line(world, {"checks": GREEN})  # every required name green
    assert decision == "allow", reason


@pytest.mark.parametrize(
    ("command", "why"),
    [
        ("gh pr merge 7 --merge", "without --match-head-commit"),
        ("gh pr merge 7 --squash --match-head-commit 0000000", "not this checkout's HEAD"),
        ("gh pr merge 7 --admin --match-head-commit {sha}", "gh pr merge --admin"),
        ("gh pr merge 7 --auto --match-head-commit {sha}", "gh pr merge --auto"),
        ("gh pr merge 7 --disable-auto --merge", "takes no other flag"),
        ("gh pr merge 7 --disable-auto && gh pr merge 7 --squash", "a command of its own"),
        ("gh pr merge 8 --disable-auto", "not this branch's PR"),
        ("bash arm_pr.sh 8", "not this branch's PR"),
        ("arm_pr.sh --repo other/app 7", "another repo"),
        ("git push origin HEAD:feat/ABC-99-other", "pushes only branches carrying ABC-12"),
        ("gh pr create --head feat/ABC-99-other", "its own branch"),
        ("gh pr edit 8 --title x", "not this branch's PR"),
        (
            "gh api graphql -f query='mutation{a:mergePullRequest(input:{}){x} "
            "b:resolveReviewThread(input:{}){y}}'",
            "resolveReviewThread as the only mutation",
        ),
    ],
)
def test_under_worker_the_pr_owner_rights_are_denied_outside_their_conditions(world, command, why):
    _pr_owner(world["repo"], "worker")
    decision, reason = hook(world, command.replace("{sha}", _head(world["repo"])))
    assert decision == "deny" and why in reason, reason


@pytest.mark.parametrize(
    ("command", "item"),
    [
        ("git push origin main", "main (git push to main)"),
        ("gh pr merge 7 --delete-branch --match-head-commit abc1234", "delete (--delete-branch)"),
        ("git push --no-verify", "guard bypass"),
    ],
)
def test_under_worker_the_never_list_still_holds(world, command, item):
    _pr_owner(world["repo"], "worker")
    decision, reason = hook(world, command)
    assert decision == "deny" and item in reason


@pytest.mark.parametrize(
    ("command", "right"),
    [
        ("env gh pr merge 7 --match-head-commit {sha}", "merge behind env"),
        ("bash -c 'gh pr merge 7 --match-head-commit {sha}'", "merge in bash -c"),
        ("GIT_X=1 git push -u origin feat/ABC-12-hook", "push behind an assignment"),
    ],
)
def test_under_worker_a_pr_owner_right_behind_a_wrapper_is_refused(world, command, right):
    _pr_owner(world["repo"], "worker")
    decision, reason = hook(world, command.replace("{sha}", _head(world["repo"])))
    assert decision == "deny" and right in reason, reason


def test_the_worktrees_own_switch_grants_nothing(world):
    _pr_owner(world["repo"], "worker", publish=False)
    assert hook(world, "gh pr merge 7 --merge")[1].startswith(MERGE_DENY)
    assert hook(world, "gh pr edit 7 --title x") == (None, "")


def test_another_switch_value_opens_nothing(world):
    _pr_owner(world["repo"], "everyone")
    assert hook(world, "gh pr merge 7 --merge")[1].startswith(MERGE_DENY)


def test_settings_add_the_pr_owner_rules_only_under_worker(world):
    plain = make_repo(world["tmp"], name="plain", rights=None)
    _pr_owner(plain, "master")
    assert wr.settings(plain, KEY)["permissions"]["allow"] == []
    _pr_owner(plain, "worker")
    assert wr.settings(plain, KEY)["permissions"]["allow"] == list(wr.PR_OWNER_ALLOW)
    allow = wr.settings(world["repo"], KEY)["permissions"]["allow"]
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


ROLE_CHANGES = [
    "unset WE_ROLE; arm_pr.sh 7",
    "export WE_ROLE=master && arm_pr.sh 7",
    "export WE_ROLE=master\narm_pr.sh 7 --method squash",
    "WE_ROLE= bash /plugin/scripts/arm_pr.sh 7",
    "env -u WE_ROLE arm_pr.sh 7",
    "env -i PATH=/usr/bin arm_pr.sh 7",
    "bash -c 'unset WE_\"ROLE\"; arm_pr.sh 7'",
    "declare +x WE_ROLE; eval arm_pr.sh 7",
    "sudo -u x arm_pr.sh 7",
]


@pytest.mark.parametrize("owner", ["master", "worker"])
@pytest.mark.parametrize("command", ROLE_CHANGES)
def test_arm_pr_beside_a_change_of_we_role_is_denied(world, owner, command):
    """Red arm: the gate reads `WE_ROLE` of its own process, `arm_pr.sh` that of the shell the chain
    leaves it; a segment that unsets or exports the variable before the arm passed the gate and
    armed a one-way PR as a session's."""
    _pr_owner(world["repo"], owner)
    decision, reason = hook(world, command)
    assert decision == "deny", reason
    assert "never for a worker (merge (arm_pr.sh beside a change of WE_ROLE))" in reason, reason


@pytest.mark.parametrize(
    "command",
    [
        "grep -n WE_ROLE we/scripts/arm_pr.sh",
        "sed -n 1,9p we/scripts/arm_pr.sh; echo $WE_ROLE",
        "unset WE_ROLE; echo arm_pr.sh",
    ],
)
def test_reading_arm_pr_beside_we_role_passes(world, command):
    assert hook(world, command) == (None, "")


def test_a_spent_hook_deadline_refuses_every_gated_gh_read(world, monkeypatch):
    """The hook passes one deadline to every command of a call: a second `gh pr edit` after the
    first spent the budget refuses instead of running past the hook's timeout (which lets it by)."""
    monkeypatch.setenv("WE_ROLE", "worker")  # the arm right holds only with it
    repo = str(world["repo"])
    _pr_owner(world["repo"], "worker")
    rights = wr.crew_rights(repo)
    argv = ["gh", "pr", "edit", "7", "--title", "x"]
    spent = time.monotonic() - 1
    reason = wr.right_refusal(argv, "pr_edit", rights, KEY, repo, "worker", spent)
    assert reason and "ran past the worker gate's" in reason, reason
    arm = wr.right_refusal(["arm_pr.sh", "7"], "arm", rights, KEY, repo, "worker", spent)
    assert arm and "ran past the worker gate's" in arm, arm
