"""The plugin's workflows never start a cold-start model run: no workflow invokes
tests/coldstart/run.py, only the two review workflows start a model (through claude-code-action),
coldstart-receipt.yml reads nothing but the repo and the event, and no workflow runs on
pull_request_target."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml")

REPO = Path(__file__).resolve().parent.parent
WORKFLOWS = sorted((REPO / ".github" / "workflows").glob("*.yml"))
MODEL_WORKFLOWS = {"claude-code-review.yml", "claude.yml"}
RECEIPT = REPO / ".github" / "workflows" / "coldstart-receipt.yml"
STARTS_A_MODEL = re.compile(
    r"anthropics/claude-code-action|(^|[\s;&|(])claude\s+(-p|--print)\b|@anthropic-ai/claude-code"
    r"|api\.anthropic\.com",
    re.MULTILINE,
)


def _load(path: Path) -> dict:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if True in data:  # PyYAML reads the bare key `on` as a boolean
        data["on"] = data.pop(True)
    return data


def _steps(data: dict) -> list[dict]:
    return [s for job in (data.get("jobs") or {}).values() for s in job.get("steps") or []]


def models_started(texts: dict[str, str]) -> set[str]:
    return {name for name, text in texts.items() if STARTS_A_MODEL.search(text)}


def test_no_workflow_invokes_the_harness():
    for path in WORKFLOWS:
        assert "tests/coldstart/run.py" not in path.read_text(), path.name


def test_only_the_two_review_workflows_start_a_model():
    texts = {p.name: p.read_text() for p in WORKFLOWS}
    assert models_started(texts) == MODEL_WORKFLOWS


def test_the_model_detector_sees_a_harness_style_call():
    """Red arm: a workflow running a cold claude -p session is caught."""
    assert models_started({"x.yml": "run: |\n  env -u X claude -p --plugin-dir we 'q'\n"}) == {
        "x.yml"
    }
    assert models_started({"y.yml": "run: python3 tests/coldstart/receipt_gate.py"}) == set()


def test_no_workflow_runs_on_pull_request_target():
    for path in WORKFLOWS:
        on = _load(path)["on"]
        assert "pull_request_target" not in (on if isinstance(on, (dict, list)) else [on]), (
            path.name
        )


def test_the_receipt_workflow_reads_only_the_repo_and_the_event():
    text = RECEIPT.read_text()
    data = _load(RECEIPT)
    assert data["permissions"] == {"contents": "read"}
    for job in data["jobs"].values():
        assert job.get("permissions") in (None, {"contents": "read"})
    assert "secrets." not in text
    assert set(data["on"]["pull_request"]["types"]) == {
        "opened",
        "synchronize",
        "reopened",
        "edited",
    }


def test_the_receipt_workflow_passes_the_body_only_through_env():
    steps = _steps(_load(RECEIPT))
    for step in steps:
        assert "${{" not in str(step.get("run", "")), step.get("name")
    [gate] = [s for s in steps if "receipt_gate.py" in str(s.get("run", ""))]
    assert gate["env"]["PR_BODY"] == "${{ github.event.pull_request.body }}"


def test_the_receipt_job_is_named_for_the_required_check():
    assert list(_load(RECEIPT)["jobs"]) == ["coldstart-receipt"]
    assert _load(RECEIPT)["jobs"]["coldstart-receipt"]["name"] == "coldstart-receipt"
