"""lens_verdict.py § Carried panel (Q480): a green T2 panel on an older head holds for a new head
whose delta touches no file the PR's class hit, classified by the merge hook's own runner
(risk_runner.py) on a real git history with an origin."""

from __future__ import annotations

import io
import json
import os
import subprocess
import sys
from pathlib import Path

import lens_verdict as lv
import pytest

CREW = {
    "version": 2,
    "roles": {"product": "ada", "architecture": "vic", "acceptance": "tess"},
    "members": {
        "ada": {"name": "Ada", "workplace": "."},
        "vic": {"name": "Vic", "workplace": "."},
        "tess": {"name": "Tess", "workplace": "."},
    },
}
RULES = "[t2]\npath risky/**\n"
GREEN = '```json\n{"findings": []}\n```'
LENSES = ("product", "architecture", "acceptance")


def git(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(root), "-c", "user.name=t", "-c", "user.email=t@example.com", *args],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def commit(root: Path, files: dict[str, str], msg: str) -> str:
    for name, text in files.items():
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_text(text)
    git(root, "add", "-A")
    git(root, "commit", "-qm", msg)
    return git(root, "rev-parse", "HEAD")


@pytest.fixture
def pr(tmp_path, monkeypatch):
    """A repo with an origin: main carries the crew and `[t2] risky/**`; branch `feat` has one
    commit on `risky/a.py` (the PR is T2). Returns a dict with the root, the first head and a
    `point(sha)` that moves the fake PR head."""
    origin = tmp_path / "origin.git"
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(origin)], check=True)
    root = tmp_path / "repo"
    root.mkdir()
    git(root, "init", "-q", "-b", "main")
    git(root, "remote", "add", "origin", str(origin))
    commit(root, {".weside/crew.json": json.dumps(CREW), ".weside/risk-paths": RULES}, "main")
    git(root, "push", "-q", "origin", "main")
    git(root, "checkout", "-q", "-b", "feat")
    old = commit(root, {"risky/a.py": "x = 1\n"}, "risky change")
    head_file = tmp_path / "head"
    gh_dir = tmp_path / "bin"
    gh_dir.mkdir()
    posted = tmp_path / "posted.txt"
    (gh_dir / "gh").write_text(
        '#!/bin/sh\nif [ "$1 $2" = "pr comment" ]; then cat > "$FAKE_GH_POSTED"; exit 0; fi\n'
        'cat "$FAKE_GH_HEAD"\n'
    )
    (gh_dir / "gh").chmod(0o755)
    monkeypatch.setenv("PATH", f"{gh_dir}{os.pathsep}{os.environ['PATH']}")
    monkeypatch.setenv("FAKE_GH_HEAD", str(head_file))
    monkeypatch.setenv("FAKE_GH_POSTED", str(posted))
    monkeypatch.chdir(root)

    def point(sha: str) -> None:
        head_file.write_text(sha + "\n")

    point(old)
    return {"root": root, "old": old, "point": point, "posted": posted}


def run(*argv: str, stdin: str = "") -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    saved = sys.stdout, sys.stderr
    sys.stdout, sys.stderr = out, err
    try:
        code = lv.main(list(argv), io.StringIO(stdin))
    finally:
        sys.stdout, sys.stderr = saved
    return code, out.getvalue(), err.getvalue()


def green_panel() -> None:
    assert run("plan", "t2", "7")[0] == 0
    for lens in LENSES:
        assert run("write", "t2-pr7", lens, stdin=GREEN)[0] == 0
    assert run("check", "t2-pr7")[0] == 0


def test_a_t0_delta_carries_the_panel(pr):
    green_panel()
    new = commit(pr["root"], {"docs/notes.md": "receipt\n"}, "receipt only")
    pr["point"](new)
    code, out, _ = run("check", "t2-pr7")
    assert code == 0, out
    assert f"panel t2-pr7: carried from {pr['old'][:8]} to {new[:8]}" in out
    assert "touches no risk path, T0" in out
    assert out.rstrip().endswith("panel t2-pr7: green")
    assert lv.check_t2(pr["root"], "t2-pr7")[2] == pr["old"]


def test_a_delta_on_a_risk_path_needs_the_full_panel(pr):
    """Red arm: the same move with the delta on `risky/` stays stale."""
    green_panel()
    new = commit(pr["root"], {"risky/a.py": "x = 2\n"}, "risky again")
    pr["point"](new)
    code, out, _ = run("check", "t2-pr7")
    assert code == 1
    assert f"stale (bound to {pr['old'][:8]}, now {new[:8]})" in out
    assert f"not carried (delta {pr['old'][:8]}..{new[:8]} touches risky/a.py)" in out
    assert lv.check_t2(pr["root"], "t2-pr7")[2] is None


def test_a_new_risk_file_in_the_delta_is_not_carried(pr):
    green_panel()
    new = commit(pr["root"], {"risky/b.py": "y = 1\n"}, "another risky file")
    pr["point"](new)
    code, out, _ = run("check", "t2-pr7")
    assert code == 1 and "touches risky/b.py" in out


def test_without_an_earlier_panel_nothing_carries(pr):
    new = commit(pr["root"], {"docs/notes.md": "receipt\n"}, "receipt only")
    pr["point"](new)
    code, out, _ = run("check", "t2-pr7")
    assert code == 1 and "panel t2-pr7: red" in out and "carried" not in out


def test_a_panel_on_a_head_that_is_no_ancestor_does_not_carry(pr):
    """A panel bound to a commit outside the PR's history (another branch) never carries."""
    git(pr["root"], "checkout", "-q", "-b", "side", "main")
    side = commit(pr["root"], {"risky/a.py": "x = 9\n"}, "side")
    pr["point"](side)
    green_panel()
    git(pr["root"], "checkout", "-q", "feat")
    new = commit(pr["root"], {"docs/notes.md": "receipt\n"}, "receipt only")
    pr["point"](new)
    code, out, _ = run("check", "t2-pr7")
    assert code == 1
    assert f"not carried ({side[:8]} is no ancestor of {new[:8]})" in out


def test_a_clean_merge_of_main_carries(pr):
    """Main moved on `risky/` itself; merging it in changes no file the PR hit."""
    green_panel()
    root = pr["root"]
    git(root, "checkout", "-q", "main")
    commit(root, {"risky/c.py": "z = 1\n"}, "main moves")
    git(root, "push", "-q", "origin", "main")
    git(root, "checkout", "-q", "feat")
    git(root, "merge", "-q", "--no-edit", "main")
    new = git(root, "rev-parse", "HEAD")
    pr["point"](new)
    code, out, _ = run("check", "t2-pr7")
    assert code == 0, out
    assert "carried from" in out


def test_a_merge_that_keeps_the_branch_side_of_a_hit_file_does_not_carry(pr):
    """T2 panel on #203: main changes a file the PR hit; the merge keeps the branch's side, so the
    file is not in old..new, yet the PR's diff now undoes main's change. Not carried."""
    green_panel()
    root = pr["root"]
    git(root, "checkout", "-q", "main")
    commit(root, {"risky/a.py": "x = 5  # main tightens\n"}, "main tightens")
    git(root, "push", "-q", "origin", "main")
    git(root, "checkout", "-q", "feat")
    git(root, "merge", "-q", "--no-edit", "-X", "ours", "main")
    new = git(root, "rev-parse", "HEAD")
    assert git(root, "diff", "--name-only", pr["old"], new) == ""
    pr["point"](new)
    code, out, _ = run("check", "t2-pr7")
    assert code == 1, out
    assert "main changed risky/a.py" in out


def test_a_red_panel_is_never_carried(pr):
    assert run("plan", "t2", "7")[0] == 0
    for lens in LENSES[:2]:
        run("write", "t2-pr7", lens, stdin=GREEN)
    run("write", "t2-pr7", "acceptance", "--failed", "no answer")
    new = commit(pr["root"], {"docs/notes.md": "receipt\n"}, "receipt only")
    pr["point"](new)
    code, out, _ = run("check", "t2-pr7")
    assert code == 1 and "carried from" not in out


def test_post_names_the_new_head_and_the_carry(pr):
    green_panel()
    new = commit(pr["root"], {"docs/notes.md": "receipt\n"}, "receipt only")
    pr["point"](new)
    code, out, err = run("post", "t2-pr7")
    assert code == 0, err
    assert out.strip() == f"posted: t2-panel PASS on #7 @ {new[:12]}"
    body = pr["posted"].read_text()
    assert body.startswith(f"<!-- t2-panel -->\n## T2 panel — #7 @ `{new}`\n**Overall: PASS**\n")
    assert f"carried from {pr['old'][:8]} to {new[:8]}" in body


def _rules_on_main(pr, files: dict[str, str]) -> None:
    """Land new rules on origin/main and merge them into the PR branch (a clean merge)."""
    root = pr["root"]
    git(root, "checkout", "-q", "main")
    commit(root, files, "rules")
    git(root, "push", "-q", "origin", "main")
    git(root, "checkout", "-q", "feat")


def test_a_one_way_pr_never_carries_its_panel(pr):
    """T2 panel on #203: a one-way PR's panel opens its self-merge window, so each head needs a
    fresh one, even when the delta touches no hit file."""
    _rules_on_main(pr, {".weside/risk-paths": "[money]\npath risky/**\n"})
    root = pr["root"]
    git(root, "merge", "-q", "--no-edit", "main")
    pr["point"](git(root, "rev-parse", "HEAD"))
    green_panel()
    new = commit(root, {"docs/notes.md": "receipt\n"}, "receipt only")
    pr["point"](new)
    code, out, _ = run("check", "t2-pr7")
    assert code == 1
    assert "a one-way PR never carries its panel" in out


def test_a_class_without_hit_lines_carries_nothing(pr, tmp_path):
    script = "#!/bin/sh\necho T2\necho 'review: standard'\n"
    _rules_on_main(
        pr,
        {
            "bin/classify.sh": script,
            ".weside/crew.json": json.dumps({**CREW, "risk": {"command": "bin/classify.sh"}}),
        },
    )
    root = pr["root"]
    git(root, "merge", "-q", "--no-edit", "main")
    pr["point"](git(root, "rev-parse", "HEAD"))
    green_panel()
    new = commit(root, {"docs/notes.md": "receipt\n"}, "receipt only")
    pr["point"](new)
    code, out, _ = run("check", "t2-pr7")
    assert code == 1 and "names no file it hit" in out


def test_a_classifier_failure_carries_nothing(pr):
    _rules_on_main(
        pr,
        {
            "bin/classify.sh": "#!/bin/sh\necho broken >&2\nexit 2\n",
            ".weside/crew.json": json.dumps({**CREW, "risk": {"command": "bin/classify.sh"}}),
        },
    )
    root = pr["root"]
    git(root, "merge", "-q", "--no-edit", "main")
    pr["point"](git(root, "rev-parse", "HEAD"))
    green_panel()
    new = commit(root, {"docs/notes.md": "receipt\n"}, "receipt only")
    pr["point"](new)
    code, out, _ = run("check", "t2-pr7")
    assert code == 1 and "the PR's class is not computed" in out
