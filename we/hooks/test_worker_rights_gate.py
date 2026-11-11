"""worker_rights_gate.py as a hook: throwaway repos, a crew file and a fake `gh` on PATH."""

from __future__ import annotations

import json
import os
import subprocess
import sys
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
FAKE_GH = r"""#!/usr/bin/env python3
import json, os, sys
args = sys.argv[1:]
with open(os.environ["FAKE_GH_LOG"], "a") as fh:
    fh.write(json.dumps(args) + "\n")
if args[:2] == ["pr", "view"]:
    pr = json.load(open(os.environ["FAKE_GH_PRS"])).get(args[2])
    if pr is None:
        print("no pull requests found", file=sys.stderr); sys.exit(1)
    print(json.dumps(pr)); sys.exit(0)
sys.exit(0)
"""


def _git(cwd, *args):
    subprocess.run(["git", "-C", str(cwd), *args], check=True, capture_output=True)


def make_repo(tmp_path: Path, name="app", rights=RIGHTS, branch=BRANCH, crew=True, owner="acme"):
    repo = tmp_path / name
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
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
        "i",
    )
    _git(repo, "remote", "add", "origin", f"git@github.com:{owner}/{name}.git")
    _git(repo, "update-ref", "refs/remotes/origin/main", "HEAD")
    _git(repo, "symbolic-ref", "refs/remotes/origin/HEAD", "refs/remotes/origin/main")
    _git(repo, "tag", "v1.2.3-rc.1")
    if branch != "main":
        _git(repo, "checkout", "-q", "-b", branch)
    if crew:
        (repo / ".weside").mkdir()
        body = {**CREW, "worker_rights": rights} if rights is not None else CREW
        (repo / ".weside" / "crew.json").write_text(json.dumps(body))
    return repo


@pytest.fixture
def world(tmp_path):
    bindir = tmp_path / "bin"
    bindir.mkdir()
    (bindir / "gh").write_text(FAKE_GH)
    (bindir / "gh").chmod(0o755)
    prs = {
        "7": {
            "headRefName": BRANCH,
            "headRepository": {"name": "app"},
            "headRepositoryOwner": {"login": "acme"},
        },
        "8": {
            "headRefName": "feat/ABC-99-other",
            "headRepository": {"name": "app"},
            "headRepositoryOwner": {"login": "acme"},
        },
        "10": {
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
        "gh pr comment --body x",
        "gh pr comment 7 --body x",
        "gh pr comment -R acme/app 7 -b x",
        "gh pr comment https://github.com/acme/app/pull/7 --body x",
        "a release staging",
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
    infra = make_repo(world["tmp"], name="infra", crew=False)
    (infra / ".weside").mkdir()
    pointer = os.path.relpath(world["repo"] / ".weside" / "crew.json", infra)
    (infra / ".weside" / "config.json").write_text(json.dumps({"crew": pointer}))
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
    ("git push origin refs/tags/v9", "guard bypass (git push of the tag refs/tags/v9)"),
    ("git push origin tag v9", "guard bypass (git push of a tag)"),
    ("git push --tags", "guard bypass (git push --tags: a tag)"),
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
        "secrets (gh secret in inline code)",
    ),
    (
        'node -e \'require("child_process").execSync("git push origin main")\'',
        "main (git push to main in inline code)",
    ),
    ('eval "$CMD"', "unreadable command: eval of a non-literal argument"),
    ("eval 'gh secret set X'", "secrets (gh secret)"),
    ('source "$F"', "unreadable command: source of a non-literal argument"),
    ("echo 'unclosed", "unreadable command: unparsable"),
]


@pytest.mark.parametrize("command,item", NEVER, ids=[c for c, _ in NEVER])
def test_the_never_list_is_denied_for_a_worker(world, command, item):
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
        "cat <<'EOF' > body.md\nnever --no-verify here? it is data\nEOF",
        "git commit -m 'main and master'",
        "grep -rn secret src/",
    ],
)
def test_ordinary_work_passes(world, command):
    assert hook(world, command) == (None, "")


def test_a_bare_push_from_main_is_denied(world):
    _git(world["repo"], "checkout", "-q", "main")
    decision, reason = hook(world, "git push")
    assert decision == "deny" and "main (a bare git push from main)" in reason


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


def test_an_error_while_judging_fails_closed(world):
    (world["repo"] / ".weside" / "crew.json").write_text("{not json")
    decision, reason = hook(world, "git status")
    assert decision == "deny" and "fail closed" in reason
    assert hook(world, "git status", WE_ROLE="master") == (None, "")


# ---------------------------------------------------------------- the settings record (AC 8)


def test_settings_grant_exactly_the_repos_rights_and_deny_the_never_list(world):
    doc = wr.settings(world["repo"], KEY)
    assert doc["permissions"]["allow"] == [
        "Bash(gh pr ready*)",
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
    assert doc["env"] == {"WE_ROLE": "worker", "WE_STORY_KEY": KEY}
    plain = make_repo(world["tmp"], name="plain", rights=None)
    assert wr.settings(plain, KEY)["permissions"]["allow"] == []
