#!/usr/bin/env python3
"""Record where Claude Code cuts a SessionStart hook's output, as a golden fixture.

Each case starts ``claude -p`` in a throwaway directory with a ``--settings`` file whose
SessionStart hooks each print exactly N chars of context between a start and an end marker (random
code words), as JSON ``additionalContext`` (form ``context``, what the plugin's hooks print) or as
plain stdout (form ``plain``), and asks the model which markers it received. A case runs ``RUNS``
times: the end word seen in any run proves the hook arrived whole (an eight-digit random word is
not guessed); the start word without the end word in every run is a preview. The case with two
hooks in one event tells whether the cap counts per hook or per event. ``test_probe_hook_cap.py``
replays the committed fixture, ``AUTHORING.md`` § Measured facts states the result, and the L0
gate (``render_process.BUDGET``) must sit below it. CI never runs this probe: it needs a
logged-in ``claude`` and costs one Haiku call per run.

Usage: probe-hook-cap.py [--out FILE] [--timeout S] [--runs N]
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import secrets
import subprocess
import sys
import tempfile
from pathlib import Path

DEFAULT_OUT = Path(__file__).with_name("fixtures") / "hook-cap.json"
MODEL = "haiku"
RUNS = 3
# (case id, chars per hook, form): one hook per size, two hooks in one event, plain stdout
CASES: list[tuple[str, tuple[int, ...], str]] = [
    ("one-9500", (9_500,), "context"),
    ("one-9895", (9_895,), "context"),
    ("one-10000", (10_000,), "context"),
    ("one-10095", (10_095,), "context"),
    ("one-12000", (12_000,), "context"),
    ("one-20000", (20_000,), "context"),
    ("one-50000", (50_000,), "context"),
    ("two-9895", (9_895, 9_895), "context"),
    ("plain-9500", (9_500,), "plain"),
    ("plain-12000", (12_000,), "plain"),
]
PROMPT = (
    "Check the context the SessionStart hooks gave you in this conversation. It may contain code "
    "words that start with `START-` or `END-` followed by digits. Reply with exactly one line: "
    "every such code word you received, separated by single spaces, or NONE. Do nothing else."
)
WORD = re.compile(r"\b(?:START|END)-\d{8}\b")


def payload(chars: int, start: str, end: str) -> str:
    """Context of exactly ``chars`` chars: the start word, filler lines, the end word."""
    head, tail = f"{start}\n", f"\n{end}"
    room = chars - len(head) - len(tail)
    line = "filler text for the hook cap probe, no instruction here.\n"
    body = (line * (room // len(line) + 1))[:room]
    return head + body + tail


def classify(chars: int, start: str, end: str, seen: set[str]) -> dict:
    whole = start in seen and end in seen
    return {"chars": chars, "start": start in seen, "end": end in seen, "whole": whole}


def summary(cases: list[dict], form: str = "context") -> dict:
    """The cap the cases of ``form`` bound: the largest whole size, the smallest cut size, and for
    two hooks in one event whether the cap counts per hook or per event."""
    mine = [c for c in cases if c.get("form", "context") == form]
    singles = [c["hooks"][0] for c in mine if len(c["hooks"]) == 1]
    whole = [h["chars"] for h in singles if h["whole"]]
    cut = [h["chars"] for h in singles if h["start"] and not h["end"]]
    pair = next((c for c in mine if len(c["hooks"]) > 1), None)
    per = None
    if pair is not None:
        per = "hook" if all(h["whole"] for h in pair["hooks"]) else "event"
    return {
        "whole_max": max(whole) if whole else None,
        "cut_min": min(cut) if cut else None,
        "per": per,
    }


def _settings(root: Path, sizes: tuple[int, ...], words: list[tuple[str, str]], form: str) -> Path:
    hooks = []
    for i, (chars, (start, end)) in enumerate(zip(sizes, words)):
        text = payload(chars, start, end)
        if form == "context":
            out = {
                "hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": text}
            }
            text = json.dumps(out)
        (root / f"hook{i}.out").write_text(text, encoding="utf-8")
        hooks.append({"type": "command", "command": f"cat {root / f'hook{i}.out'}"})
    settings = root / "settings.json"
    settings.write_text(json.dumps({"hooks": {"SessionStart": [{"hooks": hooks}]}}))
    return settings


def _ask(settings: Path, cwd: Path, timeout: int) -> subprocess.CompletedProcess:
    return subprocess.run(
        [
            *("claude", "-p", "--model", MODEL, "--permission-mode", "plan"),
            *("--setting-sources", "project", "--strict-mcp-config"),
            *("--settings", str(settings), PROMPT),
        ],
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


def run_case(case_id: str, sizes: tuple[int, ...], form: str, timeout: int, runs: int) -> dict:
    words = [
        (f"START-{secrets.randbelow(10**8):08d}", f"END-{secrets.randbelow(10**8):08d}")
        for _ in sizes
    ]
    known = {w for pair in words for w in pair}
    seen: set[str] = set()
    valid = True
    with tempfile.TemporaryDirectory(prefix="we-hook-cap-") as tmp:
        root = Path(tmp)
        settings = _settings(root, sizes, words, form)
        for _ in range(runs):
            result = _ask(settings, root, timeout)
            found = set(WORD.findall(result.stdout))
            valid = valid and result.returncode == 0 and found <= known
            valid = valid and bool(found or "NONE" in result.stdout)
            seen |= found
    return {
        "id": case_id,
        "form": form,
        "runs": runs,
        "hooks": [classify(c, s, e, seen) for c, (s, e) in zip(sizes, words)],
        "exit": 0 if valid else 2,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--timeout", type=int, default=180)
    parser.add_argument("--runs", type=int, default=RUNS)
    args = parser.parse_args()
    results = [run_case(i, sizes, form, args.timeout, args.runs) for i, sizes, form in CASES]
    for record in results:
        marks = " ".join(
            f"{h['chars']}:{'whole' if h['whole'] else 'cut' if h['start'] else 'none'}"
            for h in record["hooks"]
        )
        print(f"{record['id']:12} {marks}")
    if any(r["exit"] for r in results):
        print("a case answered neither its code words nor NONE; nothing written", file=sys.stderr)
        return 1
    for record in results:
        record.pop("exit")
    version = subprocess.run(
        ["claude", "--version"], capture_output=True, text=True, check=False
    ).stdout.strip()
    data = {
        "claude_code": version.split()[0] if version else "",
        "recorded": dt.datetime.now(dt.timezone.utc).date().isoformat(),
        "model": MODEL,
        "cases": results,
        "cap": summary(results, "context"),
        "cap_plain": summary(results, "plain"),
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {args.out}: context {data['cap']}, plain {data['cap_plain']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
