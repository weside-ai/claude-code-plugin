import json
import re
from pathlib import Path

HOOKS = json.loads(Path(__file__).with_name("hooks.json").read_text())["hooks"]
BLOCK = (
    "Your turn ended before your final report. Finish the remaining steps of your brief, then "
    "write the report your brief asks for (worker-dispatch.md § Report fields) as your final message."
)


def _gate():
    (group,) = [g for g in HOOKS["SubagentStop"] if g.get("matcher")]
    return group["matcher"], group["hooks"][0]


def test_gate_matches_only_the_dev_workers():
    # The matcher contains ':' and so runs as an unanchored JS regex; re.search mirrors that.
    matcher, _ = _gate()
    hits = {
        t
        for t in (
            "we:dev-medium",
            "we:dev-high",
            "we:explore-medium",
            "we:council-architect",
            "dev-medium",
            "other:we:dev-medium",
            "general-purpose",
        )
        if re.search(matcher, t)
    }
    assert hits == {"we:dev-medium", "we:dev-high"}


def test_gate_is_a_prompt_that_sees_the_message_and_carries_the_block_text():
    _, handler = _gate()
    assert handler["type"] == "prompt"
    assert "$ARGUMENTS" in handler["prompt"] and "last_assistant_message" in handler["prompt"]
    assert BLOCK in handler["prompt"]


def test_measurement_hooks_never_block():
    groups = [*HOOKS["InstructionsLoaded"], *HOOKS["UserPromptExpansion"]]
    groups += [g for g in HOOKS["PreToolUse"] if g.get("matcher") == "Skill"]
    for g in groups:
        (h,) = g["hooks"]
        assert h["async"] is True and h["command"].endswith('hooks/subagent_timing.py"')
