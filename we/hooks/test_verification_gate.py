"""Matrix for the PR verification gate.

Two failure directions cost differently and both are pinned here: a **false
positive** (a command that opens no PR, denied — the class that made the hook
expensive: a heredoc writing a document that quotes `gh pr create`), and a
**false negative** (a claim that ships with no earned receipt — `--fill`, or the
denial message pasted back as its own answer).

Run: `python3 -m pytest we/hooks/test_verification_gate.py`
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

HOOK = Path(__file__).with_name("verification_gate.py")

_spec = importlib.util.spec_from_file_location("verification_gate", HOOK)
gate = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(gate)


RECEIPT = """## Summary

Widgets.

## Verification

**Oracle:** cli
**Seed:** `weside widgets create --json`
**Asserted:** 201 + widget id returned
**Not proven:** device geometry
"""

NO_RECEIPT = "## Summary\n\nWidgets.\n\n## Test Plan\n\nUnit tests pass.\n"

# The hint the gate itself used to print. Pasted back verbatim it must NOT pass.
UNFILLED = """## Verification

**Oracle:** cli | ui | substitute | not-applicable
**Seed:** <copy-pasteable command that puts the system in the asserted state>
**Asserted:** <endpoint + status + field, or route + label + ref>
**Not proven:** <what this oracle cannot show, and who owes it>
"""


@pytest.fixture()
def armed(tmp_path: Path) -> Path:
    """A git repo whose `.weside/config.json` arms the gate."""
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    weside = tmp_path / ".weside"
    weside.mkdir()
    (weside / "config.json").write_text(json.dumps({"verification": {"required": True}}))
    return tmp_path


def refuse(command: str, cwd: Path) -> str | None:
    return gate._refusal(
        {"tool_name": "Bash", "cwd": str(cwd), "tool_input": {"command": command}}
    )


def body_file(root: Path, text: str, name: str = "pr-body.md") -> str:
    (root / name).write_text(text)
    return name


# --- false positives: these open no PR and must never be denied -----------------


def test_heredoc_quoting_the_command_is_not_a_pr(armed: Path) -> None:
    """The observed regression: writing a document that quotes the command."""
    doc = "Example:\n\n```bash\ngh pr create --title 'T' --body 'x'\n```\n"
    command = f"cd {armed} && cat > notes.md <<'WEOF'\n{doc}WEOF"
    assert refuse(command, armed) is None


def test_grepping_for_the_command_is_not_a_pr(armed: Path) -> None:
    assert refuse("rg -n 'gh pr create --body' docs/", armed) is None


def test_echoing_the_command_is_not_a_pr(armed: Path) -> None:
    assert refuse("echo 'gh pr create --body x' >> notes.md", armed) is None


def test_other_gh_verbs_are_not_a_pr_write(armed: Path) -> None:
    assert refuse("gh pr checks 42", armed) is None
    assert refuse("gh pr view 42 --json body", armed) is None


def test_unbalanced_quotes_let_through(armed: Path) -> None:
    assert refuse('gh pr create --body "unbalanced', armed) is None


def test_unreadable_body_file_lets_through(armed: Path) -> None:
    """Unresolvable is not absent — the hook must not guess."""
    assert refuse("gh pr create --body-file typo.md", armed) is None


def test_command_substitution_with_no_heredoc_lets_through(armed: Path) -> None:
    assert refuse('gh pr create --body "$(cat body.md)"', armed) is None


def test_not_armed_repo_lets_everything_through(tmp_path: Path) -> None:
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    name = body_file(tmp_path, NO_RECEIPT)
    assert refuse(f"gh pr create --body-file {name}", tmp_path) is None


def test_non_bash_tool_is_ignored(armed: Path) -> None:
    assert gate._refusal({"tool_name": "Write", "cwd": str(armed), "tool_input": {}}) is None


# --- true positives: a claim with no earned receipt -----------------------------


def test_body_file_without_receipt_is_denied(armed: Path) -> None:
    name = body_file(armed, NO_RECEIPT)
    reason = refuse(f"gh pr create --body-file {name}", armed)
    assert reason is not None
    assert "docs/plans/<TICKET>-story.md" in reason


def test_relative_body_file_is_read_from_the_command_cwd(armed: Path) -> None:
    """`cd x && gh pr create --body-file b.md` must not read the hook's own cwd."""
    name = body_file(armed, NO_RECEIPT)
    assert refuse(f"cd {armed} && gh pr create --body-file {name}", armed) is not None


def test_fill_is_a_claim_with_no_receipt(armed: Path) -> None:
    reason = refuse("gh pr create --fill", armed)
    assert reason is not None
    assert "no body at all" in reason


def test_the_unfilled_template_does_not_pass(armed: Path) -> None:
    """The old denial message, pasted back verbatim, used to satisfy the gate."""
    name = body_file(armed, UNFILLED)
    assert refuse(f"gh pr create --body-file {name}", armed) is not None


def test_a_chosen_oracle_over_placeholders_does_not_pass(armed: Path) -> None:
    half = UNFILLED.replace("cli | ui | substitute | not-applicable", "cli")
    name = body_file(armed, half)
    reason = refuse(f"gh pr create --body-file {name}", armed)
    assert reason is not None
    assert "placeholders" in reason


def test_heading_over_nothing_does_not_pass(armed: Path) -> None:
    name = body_file(armed, "## Verification\n\nTests are green.\n")
    assert refuse(f"gh pr create --body-file {name}", armed) is not None


def test_deep_heading_still_counts(armed: Path) -> None:
    """A receipt one heading level too deep is a receipt, not a violation."""
    name = body_file(armed, RECEIPT.replace("## Verification", "##### Verification"))
    assert refuse(f"gh pr create --body-file {name}", armed) is None


# --- the receipt itself ---------------------------------------------------------


def test_complete_receipt_passes(armed: Path) -> None:
    name = body_file(armed, RECEIPT)
    assert refuse(f"gh pr create --body-file {name}", armed) is None


def test_receipt_inside_a_heredoc_body_passes(armed: Path) -> None:
    command = f"gh pr create --title 'T' --body \"$(cat <<'EOF'\n{RECEIPT}EOF\n)\""
    assert refuse(command, armed) is None


def test_missing_receipt_inside_a_heredoc_body_is_denied(armed: Path) -> None:
    command = f"gh pr create --title 'T' --body \"$(cat <<'EOF'\n{NO_RECEIPT}EOF\n)\""
    assert refuse(command, armed) is not None


def test_not_applicable_needs_no_seed(armed: Path) -> None:
    name = body_file(
        armed, "## Verification\n\n**Oracle:** not-applicable — docs only, no runtime surface.\n"
    )
    assert refuse(f"gh pr create --body-file {name}", armed) is None


def test_after_a_separator_gh_still_counts(armed: Path) -> None:
    name = body_file(armed, NO_RECEIPT)
    assert refuse(f"git push && gh pr create --body-file {name}", armed) is not None


def test_pr_edit_without_a_body_is_not_a_new_claim(armed: Path) -> None:
    assert refuse("gh pr edit 42 --add-label ready", armed) is None


def test_pr_edit_with_a_bodyless_body_is_denied(armed: Path) -> None:
    name = body_file(armed, NO_RECEIPT)
    assert refuse(f"gh pr edit 42 --body-file {name}", armed) is not None


# --- the process contract -------------------------------------------------------


def test_denial_is_emitted_as_a_permission_decision(armed: Path) -> None:
    name = body_file(armed, NO_RECEIPT)
    payload = {
        "tool_name": "Bash",
        "cwd": str(armed),
        "tool_input": {"command": f"gh pr create --body-file {name}"},
    }
    out = subprocess.run(
        [sys.executable, str(HOOK)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        check=True,
    )
    decision = json.loads(out.stdout)["hookSpecificOutput"]
    assert decision["hookEventName"] == "PreToolUse"
    assert decision["permissionDecision"] == "deny"


def test_a_pass_prints_nothing(armed: Path) -> None:
    name = body_file(armed, RECEIPT)
    payload = {
        "tool_name": "Bash",
        "cwd": str(armed),
        "tool_input": {"command": f"gh pr create --body-file {name}"},
    }
    out = subprocess.run(
        [sys.executable, str(HOOK)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        check=True,
    )
    assert out.stdout.strip() == ""


def test_unparseable_stdin_is_silent() -> None:
    out = subprocess.run(
        [sys.executable, str(HOOK)], input="not json", capture_output=True, text=True, check=True
    )
    assert out.stdout.strip() == ""
