"""lens_verdict.py: the panel's dispatch entries, the closed verdict file, the green rule (missing,
stale, red, refuted), the T2 red arm, the forbidden keys and the sample counter."""

from __future__ import annotations

import io
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import lens_verdict as lv
import pytest

SCRIPT = Path(__file__).resolve().parent / "lens_verdict.py"
SEED = (
    Path(__file__).resolve().parents[2]
    / "tests"
    / "lens-corpus"
    / "architecture"
    / "unframed-error-detail"
)
KEY = "PROJ-1"
HEAD = "a" * 40
CREW = {
    "version": 2,
    "roles": {"product": "ada", "architecture": "vic", "acceptance": "tess"},
    "members": {
        "ada": {"name": "Ada", "workplace": "."},
        "vic": {"name": "Vic", "workplace": "."},
        "tess": {"name": "Tess", "workplace": "."},
    },
    "lenses": {
        "product": {"questions": "lenses/product.md", "t2_questions": "lenses/product-t2.md"},
        "architecture": {"keeper": "vic", "sample": 2, "registry": "lenses/registry.md"},
    },
}
GREEN = '```json\n{"findings": []}\n```'


def _git(root: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)


@pytest.fixture
def repo(tmp_path, monkeypatch):
    root = tmp_path / "repo"
    (root / "docs" / "plans").mkdir(parents=True)
    (root / ".weside").mkdir()
    (root / "lenses").mkdir()
    for name in ("product.md", "product-t2.md", "registry.md"):
        (root / "lenses" / name).write_text("- a question\n")
    (root / ".weside" / "crew.json").write_text(json.dumps(CREW))
    (root / "docs" / "plans" / f"{KEY}-story.md").write_text("# Plan\n")
    _git(root, "init", "-q")
    _git(
        root,
        "-c",
        "user.name=t",
        "-c",
        "user.email=t@example.com",
        "commit",
        "-qm",
        "x",
        "--allow-empty",
    )
    gh_dir = tmp_path / "bin"
    gh_dir.mkdir()
    (gh_dir / "gh").write_text('#!/bin/sh\ncat "$FAKE_GH_HEAD"\n')
    (gh_dir / "gh").chmod(0o755)
    head_file = tmp_path / "head"
    head_file.write_text(HEAD + "\n")
    monkeypatch.setenv("PATH", f"{gh_dir}{os.pathsep}{os.environ['PATH']}")
    monkeypatch.setenv("FAKE_GH_HEAD", str(head_file))
    monkeypatch.chdir(root)
    return root


def run(*argv: str, stdin: str = "") -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    old = sys.stdout, sys.stderr
    sys.stdout, sys.stderr = out, err
    try:
        code = lv.main(list(argv), io.StringIO(stdin))
    finally:
        sys.stdout, sys.stderr = old
    return code, out.getvalue(), err.getvalue()


def answer(*findings: dict) -> str:
    return "Prose before.\n```json\n" + json.dumps({"findings": list(findings)}) + "\n```\n"


def blocking(arm: dict | None = None, severity: str = "BLOCKING") -> dict:
    f = {"severity": severity, "claim": "c", "where": "a.py:1", "question": "q"}
    if arm is not None:
        f["red_arm"] = arm
    return f


def verdict_file(root: Path, vid: str) -> Path:
    return root / ".git" / "we-lens" / f"{vid}.json"


# --- AC1: dispatch entries ---------------------------------------------------------------------


def test_plan_ready_prints_one_entry_per_ready_lens_in_crew_order(repo):
    code, out, err = run("plan", "ready", KEY)
    assert code == 0, err
    shown = json.loads(out)
    blob = subprocess.run(
        ["git", "hash-object", f"docs/plans/{KEY}-story.md"],
        capture_output=True,
        text=True,
        check=False,
    ).stdout.strip()
    assert shown["id"] == f"ready-{KEY}" and shown["bound_to"] == {"plan_blob": blob}
    assert [e["lens"] for e in shown["entries"]] == ["product", "architecture", "acceptance"]
    product, arch, acc = shown["entries"]
    assert product["agent"] == "we:lens-product"
    assert product["questions"] == str((repo / "lenses" / "product.md").resolve())
    assert arch["registry"] == str((repo / "lenses" / "registry.md").resolve())
    assert acc["questions"] is None  # no binding: the agent's generic questions
    assert product["plan"] == str(repo / "docs" / "plans" / f"{KEY}-story.md")
    assert product["plan_blob"] == blob and product["id"] == f"ready-{KEY}"
    stored = json.loads(verdict_file(repo, f"ready-{KEY}").read_text())
    assert stored["expected"] == ["product", "architecture", "acceptance"]
    assert stored["verdicts"] == {}


def test_plan_t2_binds_the_head_and_hands_out_the_t2_question_files(repo):
    code, out, err = run("plan", "t2", "7")
    assert code == 0, err
    product = json.loads(out)["entries"][0]
    assert product["questions"] == str((repo / "lenses" / "product-t2.md").resolve())
    assert product["head"] == HEAD and product["pr"] == 7 and product["id"] == "t2-pr7"


def test_plan_without_a_plan_file_or_a_head_is_refused(repo, monkeypatch):
    code, _, err = run("plan", "ready", "PROJ-2")
    assert code == 1 and "plan docs/plans/PROJ-2-story.md: missing" in err
    monkeypatch.setenv("FAKE_GH_HEAD", str(repo / "nope"))
    code, _, err = run("plan", "t2", "7")
    assert code == 1 and "panel t2-pr7: head unknown" in err


def test_a_verdict_id_that_is_no_subject_is_a_usage_error(repo):
    code, _, err = run("check", "../../etc")
    assert code == 2 and "expected ready-<KEY> or t2-pr<N>" in err


def test_plan_ready_with_plan_binds_that_file_through_write_and_check(repo):
    """Regression: `plan ready KEY --plan PATH` ended with exit 2 and an empty message."""
    other = repo / "plans" / "story.md"
    other.parent.mkdir()
    other.write_text("# Plan elsewhere\n")
    code, out, err = run("plan", "ready", KEY, "--plan", "plans/story.md")
    assert code == 0, err
    entry = json.loads(out)["entries"][0]
    assert entry["plan"] == str(repo / "plans" / "story.md")
    assert json.loads(verdict_file(repo, f"ready-{KEY}").read_text())["plan"] == "plans/story.md"
    for lens in ("product", "architecture", "acceptance"):
        assert run("write", f"ready-{KEY}", lens, stdin=GREEN)[0] == 0
    assert run("check", f"ready-{KEY}")[0] == 0
    other.write_text("# Plan elsewhere, edited\n")
    code, out, _ = run("check", f"ready-{KEY}")
    assert code == 1 and f"panel ready-{KEY}: stale (bound to" in out


def test_plan_outside_the_repo_or_an_unknown_option_names_itself(repo, tmp_path):
    code, _, err = run("plan", "ready", KEY, "--plan", str(tmp_path / "x.md"))
    assert code == 2 and "--plan" in err and "not inside the repo" in err
    code, _, err = run("plan", "ready", KEY, "--plna", "x")
    assert code == 2 and "unknown option --plna" in err and "Usage:" in err
    code, _, err = run("plan", "ready")
    assert code == 2 and "plan: wrong arguments" in err and "lens_verdict.py plan ready" in err
    code, _, err = run("check", f"ready-{KEY}", "--plan", "x.md")
    assert code == 2 and "--plan (only for plan ready)" in err


# --- AC2: missing, stale, green ----------------------------------------------------------------


def test_two_of_three_is_red_with_the_missing_lens_named(repo):
    run("plan", "ready", KEY)
    run("write", f"ready-{KEY}", "product", stdin=GREEN)
    run("write", f"ready-{KEY}", "architecture", stdin=GREEN)
    code, out, _ = run("check", f"ready-{KEY}")
    assert code == 1
    assert "lens acceptance: missing" in out.splitlines()
    assert out.splitlines()[-1] == f"panel ready-{KEY}: red"


def test_three_green_bound_to_the_current_blob_is_green(repo):
    run("plan", "ready", KEY)
    for lens in ("product", "architecture", "acceptance"):
        assert run("write", f"ready-{KEY}", lens, stdin=GREEN)[0] == 0
    code, out, _ = run("check", f"ready-{KEY}")
    assert code == 0, out
    assert out.splitlines()[-1] == f"panel ready-{KEY}: green"


def test_a_plan_edited_after_the_panel_is_stale_and_red(repo):
    run("plan", "ready", KEY)
    for lens in ("product", "architecture", "acceptance"):
        run("write", f"ready-{KEY}", lens, stdin=GREEN)
    (repo / "docs" / "plans" / f"{KEY}-story.md").write_text("# Plan, edited\n")
    code, out, _ = run("check", f"ready-{KEY}")
    assert code == 1
    assert any(line.startswith(f"panel ready-{KEY}: stale (bound to") for line in out.splitlines())
    code, _, err = run("write", f"ready-{KEY}", "product", stdin=GREEN)
    assert code == 1 and "stale (start a fresh panel with plan)" in err


def test_a_new_head_makes_a_t2_panel_stale(repo, tmp_path):
    run("plan", "t2", "7")
    for lens in ("product", "architecture", "acceptance"):
        run("write", "t2-pr7", lens, stdin=GREEN)
    assert run("check", "t2-pr7")[0] == 0
    (tmp_path / "head").write_text("b" * 40)
    code, out, _ = run("check", "t2-pr7")
    assert code == 1 and "panel t2-pr7: stale (bound to aaaaaaaa, now bbbbbbbb)" in out


def test_no_panel_and_an_unreadable_file_are_red(repo):
    code, out, _ = run("check", f"ready-{KEY}")
    assert code == 1 and f"panel ready-{KEY}: not started (run plan)" in out
    verdict_file(repo, f"ready-{KEY}").parent.mkdir(parents=True, exist_ok=True)
    verdict_file(repo, f"ready-{KEY}").write_text("{not json")
    code, out, _ = run("check", f"ready-{KEY}")
    assert code == 1 and f"panel ready-{KEY}: verdict file unreadable" in out


@pytest.mark.parametrize(
    ("severity", "verdict"), [("BLOCKING", "red"), ("WARNING", "red"), ("NOTE", "green")]
)
def test_a_ready_finding_turns_its_lens_red_unless_it_is_a_note(repo, severity, verdict):
    run("plan", "ready", KEY)
    code, out, err = run(
        "write", f"ready-{KEY}", "product", stdin=answer(blocking(severity=severity))
    )
    assert code == 0, err
    assert out.strip() == f"lens product: {verdict}"


def test_a_ready_finding_needs_its_question_line(repo):
    run("plan", "ready", KEY)
    f = blocking()
    del f["question"]
    code, _, err = run("write", f"ready-{KEY}", "product", stdin=answer(f))
    assert code == 1 and "findings[0].question: needs text" in err


def test_a_stored_verdict_is_recomputed_not_trusted(repo):
    run("plan", "ready", KEY)
    for lens in ("product", "architecture", "acceptance"):
        run("write", f"ready-{KEY}", lens, stdin=GREEN)
    path = verdict_file(repo, f"ready-{KEY}")
    doc = json.loads(path.read_text())
    doc["verdicts"]["product"]["findings"] = [{**blocking(), "status": "refuted"}]
    path.write_text(json.dumps(doc))
    code, out, _ = run("check", f"ready-{KEY}")
    assert code == 1 and "lens product: red (BLOCKING a.py:1)" in out


def test_failed_records_the_lens_red(repo):
    run("plan", "t2", "7")
    code, out, _ = run("write", "t2-pr7", "architecture", "--failed", "finding without red arm")
    assert code == 0 and out.strip() == "lens architecture: red"
    _, out, _ = run("check", "t2-pr7")
    assert "lens architecture: red (finding without red arm)" in out


def test_an_answer_without_json_leaves_the_lens_missing(repo):
    run("plan", "ready", KEY)
    code, _, err = run("write", f"ready-{KEY}", "product", stdin="I found nothing worth a JSON.")
    assert code == 1 and "no parseable answer: the lens stays missing" in err
    assert "lens product: missing" in run("check", f"ready-{KEY}")[1]


def test_the_last_top_level_object_counts_not_a_nested_one(repo):
    run("plan", "ready", KEY)
    text = '{"findings": [{"severity": "NOTE", "claim": "old"}]} then\n' + answer(
        blocking(severity="NOTE")
    )
    assert run("write", f"ready-{KEY}", "product", stdin=text)[0] == 0
    stored = json.loads(verdict_file(repo, f"ready-{KEY}").read_text())
    assert stored["verdicts"]["product"]["findings"][0]["claim"] == "c"


def test_text_is_capped_and_stripped_of_control_characters(repo):
    run("plan", "ready", KEY)
    f = {**blocking(severity="NOTE"), "claim": "x\x1b[31m" + "y" * 900}
    run("write", f"ready-{KEY}", "product", stdin=answer(f))
    claim = json.loads(verdict_file(repo, f"ready-{KEY}").read_text())["verdicts"]["product"][
        "findings"
    ][0]["claim"]
    assert len(claim) == lv.TEXT_CHARS and "\x1b" not in claim


def test_a_lens_outside_the_panel_is_refused(repo):
    run("plan", "ready", KEY)
    code, _, err = run("write", f"ready-{KEY}", "security", stdin=GREEN)
    assert code == 1 and f"lens security: not expected in panel ready-{KEY}" in err


# --- AC3: the T2 red arm, with the seed case -----------------------------------------------------


def seed_answers() -> dict[str, str]:
    return json.loads((SEED / "panel.json").read_text())["answers"]


def test_the_seed_panel_without_its_red_arm_is_refused_naming_the_finding(repo):
    """The control: the recorded architecture answer, arm stripped, must go red."""
    run("plan", "t2", "7")
    body = lv.parse_answer(seed_answers()["architecture"])
    stripped = [{k: v for k, v in f.items() if k != "red_arm"} for f in body["findings"]]
    assert stripped != body["findings"]
    code, _, err = run("write", "t2-pr7", "architecture", stdin=answer(*stripped))
    assert code == 1
    assert "findings[0] (BLOCKING: The 4xx response body" in err
    assert err.strip().endswith("finding without red arm")


def test_the_seed_panel_with_its_red_arm_stands_and_turns_the_panel_red(repo):
    run("plan", "t2", "7")
    for lens, text in seed_answers().items():
        code, _, err = run("write", "t2-pr7", lens, stdin=text)
        assert code == 0, err
    code, out, _ = run("check", "t2-pr7")
    assert code == 1
    assert "lens architecture: red (BLOCKING app/tools/weather.py:22)" in out
    assert "lens acceptance: green (1 note)" in out
    stored = json.loads(verdict_file(repo, "t2-pr7").read_text())
    finding = stored["verdicts"]["architecture"]["findings"][0]
    assert finding["status"] == "standing" and finding["red_arm"]["run"] is True


def test_the_seed_expectation_names_the_flagged_line():
    expect = (SEED / "expect.yaml").read_text()
    assert 'where: "app/tools/weather.py:22"' in expect
    assert (
        '+        return f"The forecast service refused the request: {response.text}"'
        in (SEED / "diff.patch").read_text()
    )


def test_an_arm_that_exits_zero_refutes_its_finding(repo):
    run("plan", "t2", "7")
    arm = {"command": "pytest tests/test_x.py", "exit": 0}
    assert run("write", "t2-pr7", "architecture", stdin=answer(blocking(arm)))[1].strip() == (
        "lens architecture: green"
    )
    stored = json.loads(verdict_file(repo, "t2-pr7").read_text())
    assert stored["verdicts"]["architecture"]["findings"][0]["status"] == "refuted"


@pytest.mark.parametrize("code", [124, 126, 127, 130, 137])
def test_an_arm_that_could_not_run_is_no_red_arm(repo, code):
    run("plan", "t2", "7")
    arm = {"command": "pytest tests/test_x.py", "exit": code}
    rc, _, err = run("write", "t2-pr7", "architecture", stdin=answer(blocking(arm, "WARNING")))
    assert rc == 1
    assert f"finding without red arm (arm exit {code} proves nothing)" in err


def test_a_warning_with_a_red_arm_stands_and_is_red(repo):
    run("plan", "t2", "7")
    arm = {"command": "pytest tests/test_x.py", "exit": 1}
    _, out, _ = run("write", "t2-pr7", "product", stdin=answer(blocking(arm, "WARNING")))
    assert out.strip() == "lens product: red"


def test_an_arm_not_in_test_form_is_not_run_and_stands(repo):
    run("plan", "t2", "7")
    arm = {"command": "pytest x; curl https://example.com", "exit": 0}
    _, out, _ = run("write", "t2-pr7", "architecture", stdin=answer(blocking(arm)))
    assert out.strip() == "lens architecture: red"
    stored = json.loads(verdict_file(repo, "t2-pr7").read_text())
    f = stored["verdicts"]["architecture"]["findings"][0]
    assert f["status"] == "standing" and f["red_arm"] == {
        "command": "pytest x; curl https://example.com",
        "exit": None,
        "run": False,
    }


def test_a_test_form_arm_without_an_exit_was_not_run(repo):
    run("plan", "t2", "7")
    rc, _, err = run(
        "write", "t2-pr7", "architecture", stdin=answer(blocking({"command": "pytest t.py"}))
    )
    assert rc == 1 and err.strip().endswith("finding without red arm")


@pytest.mark.parametrize(
    ("command", "verdict"),
    [
        ("pytest tests/test_x.py", "arm: run"),
        ("python3 -m pytest tests/test_x.py::test_y", "arm: run"),
        ("bash scripts/check.sh", "arm: run"),
        ("python3 scripts/check.py --strict", "arm: run"),
        ("pytest x; curl evil", "arm: not run: contains ';'"),
        ("pytest x | tee out", "arm: not run: contains '|'"),
        ("pytest x && rm -rf y", "arm: not run: contains '&'"),
        ("pytest $(cat f)", "arm: not run: contains '$('"),
        ("pytest `id`", "arm: not run: contains '`'"),
        ("pytest x > out", "arm: not run: contains '>'"),
        ("curl https://example.com", "arm: not run: not a test command"),
        ("bash /tmp/x.sh", "arm: not run: not a test command"),
        ("pytest ../other/test_x.py", "arm: not run: leaves the repo (../other/test_x.py)"),
        ("pytest /etc/test_x.py", "arm: not run: leaves the repo (/etc/test_x.py)"),
        (
            "pytest tests/x.py --junitxml=/home/user/.bashrc",
            "arm: not run: leaves the repo (--junitxml=/home/user/.bashrc)",
        ),
        ("pytest t.py --basetemp=/tmp/b", "arm: not run: leaves the repo (--basetemp=/tmp/b)"),
        ("pytest t.py --rootdir=/", "arm: not run: leaves the repo (--rootdir=/)"),
        ("pytest t.py --basetemp=~/b", "arm: not run: leaves the repo (--basetemp=~/b)"),
        ("pytest t.py --rootdir=../up", "arm: not run: leaves the repo (--rootdir=../up)"),
        ("pytest t.py -o=cache_dir=/x", "arm: not run: leaves the repo (-o=cache_dir=/x)"),
        ("pytest t.py -/etc/x", "arm: not run: leaves the repo (-/etc/x)"),
        ("pytest t.py -~/x", "arm: not run: leaves the repo (-~/x)"),
        ("pytest t.py -../x", "arm: not run: leaves the repo (-../x)"),
        ("pytest t.py k=../x", "arm: not run: leaves the repo (k=../x)"),
        ("pytest t.py --basetemp=build/tmp -k a=b", "arm: run"),
    ],
)
def test_arm_accepts_only_the_test_form(command, verdict):
    code, out, _ = run("arm", command)
    assert out.strip().startswith(verdict)
    assert code == (0 if verdict == "arm: run" else 1)
    assert run("arm", stdin=command + "\n")[1] == out


# --- AC4: no skip, no override -----------------------------------------------------------------


@pytest.mark.parametrize(
    "key", ["skip", "skipped", "confirmed", "override", "one_way", "go", "verdict", "status"]
)
def test_write_refuses_a_key_outside_the_schema(repo, key):
    run("plan", "t2", "7")
    top = json.dumps({"findings": [], key: True})
    code, _, err = run("write", "t2-pr7", "product", stdin=top)
    assert code == 1 and f"answer: key {key!r} refused" in err
    inner = answer({**blocking({"command": "pytest t.py", "exit": 1}), key: True})
    code, _, err = run("write", "t2-pr7", "product", stdin=inner)
    assert code == 1 and f"findings[0]: key {key!r} refused" in err


@pytest.mark.parametrize("key", ["skip", "skipped", "confirmed", "override", "one_way", "go"])
@pytest.mark.parametrize("level", ["file", "verdict", "finding", "arm"])
def test_check_refuses_a_stored_key_outside_the_schema(repo, key, level):
    run("plan", "t2", "7")
    for lens in ("product", "architecture", "acceptance"):
        run("write", "t2-pr7", lens, stdin=answer(blocking({"command": "pytest t.py", "exit": 0})))
    assert run("check", "t2-pr7")[0] == 0
    path = verdict_file(repo, "t2-pr7")
    doc = json.loads(path.read_text())
    target = {
        "file": doc,
        "verdict": doc["verdicts"]["product"],
        "finding": doc["verdicts"]["product"]["findings"][0],
        "arm": doc["verdicts"]["product"]["findings"][0]["red_arm"],
    }[level]
    target[key] = True
    path.write_text(json.dumps(doc))
    code, out, _ = run("check", "t2-pr7")
    assert code == 1 and f"key {key!r} refused" in out


# --- AC6: samples --------------------------------------------------------------------------------


def test_every_nth_green_verdict_is_a_sample_until_read(repo):
    for i in range(1, 5):
        (repo / "docs" / "plans" / f"PROJ-{i}-story.md").write_text("# P\n")
        run("plan", "ready", f"PROJ-{i}")
        _, out, _ = run("write", f"ready-PROJ-{i}", "architecture", stdin=GREEN)
        assert out.strip() == "lens architecture: green" + (" (sample)" if i % 2 == 0 else "")
    _, out, _ = run("samples", "--keeper", "vic")
    assert out.splitlines() == ["ready-PROJ-2\tarchitecture", "ready-PROJ-4\tarchitecture"]
    assert run("samples", "--keeper", "ada")[1] == ""
    code, out, _ = run("sampled", "ready-PROJ-2", "architecture")
    assert code == 0 and out.strip() == "sample ready-PROJ-2 architecture: read"
    assert run("samples")[1].splitlines() == ["ready-PROJ-4\tarchitecture"]
    stored = json.loads(verdict_file(repo, "ready-PROJ-2").read_text())
    assert stored["verdicts"]["architecture"]["sampled"] is True
    code, _, err = run("sampled", "ready-PROJ-2", "architecture")
    assert code == 1 and "sample ready-PROJ-2 architecture: none open" in err


def test_the_done_sample_key_leaves_the_lens_counter_alone(repo):
    """`acceptance.done_sample` is board.py's Done-row sample; the acceptance lens keeps
    `lenses.acceptance.sample` (default 5), so a done_sample of 1 samples no lens verdict."""
    crew = json.loads(json.dumps(CREW))
    crew["acceptance"] = {"done_sample": 1}
    (repo / ".weside" / "crew.json").write_text(json.dumps(crew))
    for i in range(1, 5):
        (repo / "docs" / "plans" / f"PROJ-{i}-story.md").write_text("# P\n")
        run("plan", "ready", f"PROJ-{i}")
        _, out, _ = run("write", f"ready-PROJ-{i}", "acceptance", stdin=GREEN)
        assert out.strip() == "lens acceptance: green"
        _, out, _ = run("write", f"ready-PROJ-{i}", "architecture", stdin=GREEN)
        assert out.strip() == "lens architecture: green" + (" (sample)" if i % 2 == 0 else "")


def test_a_rewrite_of_the_same_lens_counts_once_and_red_counts_never(repo):
    run("plan", "ready", KEY)
    run("write", f"ready-{KEY}", "architecture", stdin=GREEN)
    run("write", f"ready-{KEY}", "architecture", stdin=GREEN)
    run("write", f"ready-{KEY}", "architecture", stdin=answer(blocking()))
    lines = (repo / ".git" / "we-lens" / "samples.jsonl").read_text().splitlines()
    assert len(lines) == 1


# --- the CLI, isolated, as the skill and board.py run it ------------------------------------------


def test_the_cli_runs_isolated(repo):
    out = subprocess.run(
        [sys.executable, "-I", str(SCRIPT), "plan", "ready", KEY],
        capture_output=True,
        text=True,
        cwd=repo,
        check=False,
    )
    assert out.returncode == 0, out.stderr
    assert len(json.loads(out.stdout)["entries"]) == 3


def test_plan_without_a_crew_file_uses_the_generic_lenses(repo):
    """A repo without a crew (the plugin's users outside a crew) gets the default panel with the
    agents' generic questions instead of a crash on the empty crew."""
    (repo / ".weside" / "crew.json").unlink()
    code, out, err = run("plan", "ready", KEY)
    assert code == 0, err
    shown = json.loads(out)
    assert [e["lens"] for e in shown["entries"]] == ["product", "architecture", "acceptance"]
    assert all(e["agent"].startswith("we:lens-") for e in shown["entries"])


# --- the panel comment a repo's self-merge judge reads -----------------------------------------

JUDGE = json.loads(
    (Path(__file__).resolve().parent / "fixtures" / "brake-self-merge" / "judge.json").read_text()
)


@pytest.fixture
def gh_comment(repo, tmp_path, monkeypatch):
    """A fake gh: `pr comment` stores the body (or fails with FAKE_GH_FAIL), anything else prints
    the head."""
    posted = tmp_path / "posted.txt"
    gh_dir = tmp_path / "bin2"
    gh_dir.mkdir()
    (gh_dir / "gh").write_text(
        '#!/bin/sh\nif [ "$1 $2" = "pr comment" ]; then\n'
        '  [ -n "$FAKE_GH_FAIL" ] && { echo "HTTP 403" >&2; exit 1; }\n'
        '  cat > "$FAKE_GH_POSTED"; exit 0\nfi\ncat "$FAKE_GH_HEAD"\n'
    )
    (gh_dir / "gh").chmod(0o755)
    monkeypatch.setenv("PATH", f"{gh_dir}{os.pathsep}{os.environ['PATH']}")
    monkeypatch.setenv("FAKE_GH_POSTED", str(posted))
    return posted


def _judge_reads(body: str, number: int, head: str) -> str | None:
    """What the judge's panel reader takes from `body`: the Overall word, or None (no panel)."""
    if JUDGE["panel_marker"] not in body:
        return None
    m = re.search(JUDGE["panel_head"], body, re.MULTILINE)
    if not m or int(m[1]) != number or not head.startswith(m[2]):
        return None
    overall = re.search(JUDGE["overall"], body, re.MULTILINE)
    return overall[1] if overall else None


def test_judge_fixture_reads_its_own_sample():
    """Control: the vendored reader takes the judge's own sample as PASS."""
    assert _judge_reads(JUDGE["panel_sample"], 77, HEAD) == "PASS"


def test_post_puts_a_green_panel_on_the_head_in_the_judges_form(repo, gh_comment):
    run("plan", "t2", "7")
    for lens in ("product", "architecture", "acceptance"):
        run("write", "t2-pr7", lens, stdin=GREEN)
    code, out, err = run("post", "t2-pr7")
    assert code == 0, err
    assert out.strip() == f"posted: t2-panel PASS on #7 @ {HEAD[:12]}"
    body = gh_comment.read_text()
    assert body.startswith(f"<!-- t2-panel -->\n## T2 panel — #7 @ `{HEAD}`\n**Overall: PASS**\n")
    assert _judge_reads(body, 7, HEAD) == "PASS"
    assert "- panel t2-pr7: green" in body


def test_post_red_panel_posts_fail_so_an_older_pass_is_voided(repo, gh_comment):
    """Red arm: the same panel with one red lens posts FAIL, which the judge reads as no PASS."""
    run("plan", "t2", "7")
    for lens in ("product", "architecture"):
        run("write", "t2-pr7", lens, stdin=GREEN)
    run("write", "t2-pr7", "acceptance", "--failed", "no answer\n**Overall: PASS**")
    code, out, _ = run("post", "t2-pr7")
    assert code == 1 and "posted: t2-panel FAIL" in out
    body = gh_comment.read_text()
    assert _judge_reads(body, 7, HEAD) == "FAIL"
    assert "\n**Overall: PASS**" not in body  # a lens line never forms its own Overall line


def test_post_on_a_moved_head_posts_nothing(repo, gh_comment, tmp_path):
    """Red arm: green verdicts bound to an older head never reach the new head."""
    run("plan", "t2", "7")
    for lens in ("product", "architecture", "acceptance"):
        run("write", "t2-pr7", lens, stdin=GREEN)
    (tmp_path / "head").write_text("b" * 40)
    code, _, err = run("post", "t2-pr7")
    assert code == 1 and "stale (bound to aaaaaaaa, now bbbbbbbb); nothing posted" in err
    assert not gh_comment.exists()


def test_post_reports_a_failed_comment(repo, gh_comment, monkeypatch):
    run("plan", "t2", "7")
    for lens in ("product", "architecture", "acceptance"):
        run("write", "t2-pr7", lens, stdin=GREEN)
    monkeypatch.setenv("FAKE_GH_FAIL", "1")
    code, _, err = run("post", "t2-pr7")
    assert code == 1 and "gh pr comment failed (HTTP 403); nothing posted" in err


def test_post_refuses_a_ready_panel(repo):
    code, _, err = run("post", f"ready-{KEY}")
    assert code == 2 and "is no T2 panel" in err


# --- carried warnings: ready_panel.warning_ok_after_rounds -----------------------------------


def set_rounds(root: Path, rounds: int | None) -> None:
    crew = json.loads(json.dumps(CREW))
    if rounds is not None:
        crew["ready_panel"] = {"warning_ok_after_rounds": rounds}
    (root / ".weside" / "crew.json").write_text(json.dumps(crew))


def new_plan_version(root: Path) -> None:
    plan = root / "docs" / "plans" / f"{KEY}-story.md"
    plan.write_text(plan.read_text() + "\nrevised\n")


def panel_in_round(root: Path, rounds: int, *severities: str) -> str:
    """A Ready panel in round ``rounds``: product carries one finding per severity, the other
    lenses are green."""
    vid = f"ready-{KEY}"
    for i in range(rounds):
        if i:
            new_plan_version(root)
        assert run("plan", "ready", KEY)[0] == 0
    assert json.loads(verdict_file(root, vid).read_text())["round"] == rounds
    findings = [blocking(severity=s) for s in severities]
    assert run("write", vid, "product", stdin=answer(*findings))[0] == 0
    for lens in ("architecture", "acceptance"):
        assert run("write", vid, lens, stdin=GREEN)[0] == 0
    return vid


def test_a_round_is_a_new_plan_version_never_a_restart(repo):
    vid = f"ready-{KEY}"
    run("plan", "ready", KEY)
    run("plan", "ready", KEY)
    assert json.loads(verdict_file(repo, vid).read_text())["round"] == 1
    new_plan_version(repo)
    run("plan", "ready", KEY)
    assert json.loads(verdict_file(repo, vid).read_text())["round"] == 2


def test_a_file_without_round_counts_as_round_one(repo):
    vid = f"ready-{KEY}"
    run("plan", "ready", KEY)
    path = verdict_file(repo, vid)
    doc = json.loads(path.read_text())
    del doc["round"]
    path.write_text(json.dumps(doc))
    assert "lens product: missing" in run("check", vid)[1]
    new_plan_version(repo)
    run("plan", "ready", KEY)
    assert json.loads(path.read_text())["round"] == 2


@pytest.mark.parametrize("value", [0, "2", True])
def test_a_round_that_is_no_number_of_at_least_one_is_refused(repo, value):
    vid = f"ready-{KEY}"
    run("plan", "ready", KEY)
    path = verdict_file(repo, vid)
    doc = json.loads(path.read_text())
    doc["round"] = value
    path.write_text(json.dumps(doc))
    code, out, _ = run("check", vid)
    assert code == 1 and "round needs a number of at least 1" in out


def test_without_the_key_a_warning_stays_red_in_any_round(repo):
    set_rounds(repo, None)
    vid = panel_in_round(repo, 3, "WARNING")
    green, lines, carried = lv.check_panel(repo, vid)
    assert not green and carried == []
    assert lines[-1] == f"panel {vid}: red"


def test_from_round_n_a_warning_only_panel_is_green_with_its_warnings_carried(repo):
    set_rounds(repo, 2)
    vid = panel_in_round(repo, 2, "WARNING", "NOTE")
    code, out, _ = run("check", vid)
    assert code == 0
    assert "lens product: green (warnings carried: WARNING a.py:1)" in out
    assert out.splitlines()[-1] == f"panel {vid}: green (warnings carried)"
    assert lv.check_panel(repo, vid)[2] == [{"lens": "product", "claim": "c", "where": "a.py:1"}]
    assert (
        json.loads(verdict_file(repo, vid).read_text())["verdicts"]["product"]["verdict"] == "red"
    )


def test_before_round_n_a_warning_only_panel_stays_red(repo):
    set_rounds(repo, 2)
    vid = panel_in_round(repo, 1, "WARNING")
    green, lines, carried = lv.check_panel(repo, vid)
    assert not green and carried == []
    assert "lens product: red (WARNING a.py:1)" in lines


@pytest.mark.parametrize("severities", [("BLOCKING",), ("WARNING", "BLOCKING")])
def test_a_blocking_stays_red_after_round_n(repo, severities):
    set_rounds(repo, 2)
    vid = panel_in_round(repo, 3, *severities)
    green, lines, carried = lv.check_panel(repo, vid)
    assert not green and carried == []
    assert lines[-1] == f"panel {vid}: red"


def test_a_failed_lens_stays_red_after_round_n(repo):
    set_rounds(repo, 1)
    vid = f"ready-{KEY}"
    run("plan", "ready", KEY)
    run("write", vid, "product", "--failed", "the agent stopped")
    for lens in ("architecture", "acceptance"):
        run("write", vid, lens, stdin=GREEN)
    assert lv.check_panel(repo, vid)[:1] == (False,)


def test_carried_warnings_are_cleared_when_the_panel_is_red_elsewhere(repo):
    set_rounds(repo, 1)
    vid = f"ready-{KEY}"
    run("plan", "ready", KEY)
    run("write", vid, "product", stdin=answer(blocking(severity="WARNING")))
    run("write", vid, "architecture", stdin=answer(blocking()))
    run("write", vid, "acceptance", stdin=GREEN)
    assert lv.check_panel(repo, vid)[0::2] == (False, [])


def test_a_t2_panel_never_carries_a_warning(repo):
    set_rounds(repo, 1)
    vid = "t2-pr7"
    run("plan", "t2", "7")
    assert "round" not in json.loads(verdict_file(repo, vid).read_text())
    warning = blocking({"command": "pytest tests/test_x.py::test_y", "exit": 1}, "WARNING")
    run("write", vid, "product", stdin=answer(warning))
    for lens in ("architecture", "acceptance"):
        run("write", vid, lens, stdin=GREEN)
    green, lines, carried = lv.check_panel(repo, vid)
    assert not green and carried == []
    assert "lens product: red (WARNING a.py:1)" in lines


# --- derived round: a verdict file of 8.10.0 or older (no ``round``) -------------------------


def legacy_run(root: Path, lens: str = "product") -> str:
    """A Ready run as 8.10.0 wrote it: the panel file without ``round``, and one green lens
    verdict, which appends its ``samples.jsonl`` line bound to the plan blob."""
    vid = f"ready-{KEY}"
    assert run("plan", "ready", KEY)[0] == 0
    assert run("write", vid, lens, stdin=GREEN)[0] == 0
    path = verdict_file(root, vid)
    doc = json.loads(path.read_text())
    doc.pop("round", None)
    path.write_text(json.dumps(doc))
    return vid


def commit_plan(root: Path) -> None:
    _git(root, "add", "-A")
    _git(root, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "draft")


def test_derived_round_without_evidence_stays_one(repo):
    """Red arm: a file without ``round`` and no logged run on another blob is round 1."""
    vid = f"ready-{KEY}"
    run("plan", "ready", KEY)
    run("write", vid, "product", "--failed", "no answer")
    doc = json.loads(verdict_file(repo, vid).read_text())
    del doc["round"]
    verdict_file(repo, vid).write_text(json.dumps(doc))
    assert lv.round_of(repo, vid) == (1, None)
    assert "round" not in run("check", vid)[1]


def test_derived_round_counts_two_logged_runs_on_two_blobs(repo):
    legacy_run(repo)
    new_plan_version(repo)
    vid = legacy_run(repo)
    round_, origin = lv.round_of(repo, vid)
    assert round_ == 2 and origin.startswith("derived: 2 plan blobs with logged lens verdicts: ")
    assert f"panel {vid}: round 2 ({origin})" in run("check", vid)[1]


def test_derived_round_counts_two_runs_on_one_blob_once(repo):
    """Red arm: a restart on the same plan blob is no round."""
    legacy_run(repo, "product")
    vid = legacy_run(repo, "architecture")
    assert lv.round_of(repo, vid) == (1, None)


def test_a_draft_commit_without_a_run_never_counts(repo):
    legacy_run(repo)
    new_plan_version(repo)
    commit_plan(repo)  # a draft between two panels: committed, never paneled
    new_plan_version(repo)
    vid = legacy_run(repo)
    assert lv.round_of(repo, vid)[0] == 2


def test_derived_round_carries_warnings_and_seeds_the_next_round(repo):
    set_rounds(repo, 2)
    legacy_run(repo)
    new_plan_version(repo)
    vid = legacy_run(repo)
    run("write", vid, "product", stdin=answer(blocking(severity="WARNING")))
    run("write", vid, "architecture", stdin=GREEN)
    run("write", vid, "acceptance", stdin=GREEN)
    code, out, _ = run("check", vid)
    assert code == 0 and "panel ready-" in out and "green (warnings carried)" in out
    new_plan_version(repo)
    run("plan", "ready", KEY)
    doc = json.loads(verdict_file(repo, vid).read_text())
    assert doc["round"] == 3 and doc["round_derived"].startswith("derived: 2 plan blobs")
    assert lv.round_of(repo, vid) == (3, doc["round_derived"])


def test_round_derived_is_refused_on_a_t2_panel(repo):
    run("plan", "t2", "7")
    path = verdict_file(repo, "t2-pr7")
    doc = json.loads(path.read_text())
    doc["round_derived"] = "derived: forged"
    path.write_text(json.dumps(doc))
    code, out, _ = run("check", "t2-pr7")
    assert code == 1 and "round_derived needs a string (ready only)" in out
