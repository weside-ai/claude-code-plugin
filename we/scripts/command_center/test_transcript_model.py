"""transcript.session_model: the model a session ran on comes from its transcript, never a guess."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import transcript


def _write(projects: Path, sid: str, entries: list[dict]) -> None:
    folder = projects / "-repo"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"{sid}.jsonl").write_text("".join(json.dumps(e) + "\n" for e in entries))


def _assistant(model: str) -> dict:
    return {
        "type": "assistant",
        "message": {"model": model, "content": [{"type": "text", "text": "x"}]},
    }


def test_the_newest_real_model_wins_over_a_synthetic_limit_entry(tmp_path):
    # a brief asked for opus, the session switched: the transcript names what answered
    _write(
        tmp_path,
        "s-1",
        [
            _assistant("claude-opus-5-5"),
            {"type": "user", "message": {"content": "go on"}},
            _assistant("claude-sonnet-5-5"),
            _assistant("<synthetic>"),  # a usage limit's entry names no model
        ],
    )
    assert transcript.session_model(tmp_path, "s-1") == "claude-sonnet-5-5"
    assert transcript.model_line(tmp_path, "s-1") == "Model: claude-sonnet-5-5"


def test_an_unread_model_is_named_absent_with_its_reason(tmp_path):
    _write(tmp_path, "s-2", [{"type": "user", "message": {"content": "hi"}}])
    assert transcript.model_line(tmp_path, None) == "Model: absent (no CLAUDE_CODE_SESSION_ID)"
    assert transcript.model_line(tmp_path, "s-x") == "Model: absent (no transcript)"
    assert (
        transcript.model_line(tmp_path, "s-2") == "Model: absent (no assistant entry with a model)"
    )
    assert transcript.session_model(tmp_path, "../etc") is None  # never a path
