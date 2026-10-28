#!/usr/bin/env python3
"""Stop hook: a reply in another language than the `language` setting is sent back once.

Prose does not hold the reply language against a stream of English tool results: on 18.10.2026 a
session that had the setting, an AGENTS.md line and a memory note answered 40 of 68 texts in
English after five corrections by the user. This hook enforces it at the turn boundary.

  * `language` comes from Claude Code's settings (user, then project, then project-local; the last
    one set wins). Absent, or a language without a word list below → no-op.
  * The last assistant text loses fenced code, inline code, URLs, paths, table rows and quotes.
    What is left counts as prose; technical terms in English stay allowed.
  * Threshold: at least MIN_WORDS prose words, at least MIN_FOREIGN function words of one other
    language, and more than RATIO times the function words of the configured one. A German reply
    with English terms has German function words and passes.
  * One block per turn: no block while `stop_hook_active` is set. Never on SubagentStop (workers
    report in English). Fail-open on every error.
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

MIN_WORDS = 25
MIN_FOREIGN = 6
RATIO = 2

# Function words only, none shared between the lists (`in`, `was`, `also`, `will` are left out).
FUNCTION_WORDS = {
    "german": {
        "der",
        "die",
        "das",
        "und",
        "ist",
        "nicht",
        "ich",
        "ein",
        "eine",
        "mit",
        "auf",
        "für",
        "den",
        "dem",
        "des",
        "sind",
        "wird",
        "auch",
        "noch",
        "wie",
        "sich",
        "zu",
        "von",
        "bei",
        "oder",
        "aber",
        "dass",
        "du",
        "wir",
        "im",
        "nach",
        "schon",
        "jetzt",
        "kein",
        "keine",
    },
    "english": {
        "the",
        "and",
        "is",
        "are",
        "not",
        "this",
        "that",
        "with",
        "for",
        "of",
        "to",
        "it",
        "be",
        "on",
        "has",
        "have",
        "which",
        "when",
        "there",
        "but",
        "or",
        "you",
        "we",
        "they",
        "from",
        "by",
        "at",
        "its",
        "now",
        "no",
    },
}
ALIASES = {"deutsch": "german", "de": "german", "en": "english"}

_FENCE = re.compile(r"^(```|~~~).*?^\1[^\n]*$", re.MULTILINE | re.DOTALL)
_INLINE = re.compile(r"`[^`\n]*`")
_URL = re.compile(r"https?://\S+")
_PATHLIKE = re.compile(r"\S*[/\\]\S*|\S+\.\w{1,5}\b")
_WORD = re.compile(r"[^\W\d_]+(?:'[^\W\d_]+)?", re.UNICODE)


def _settings_language(cwd: str | None) -> str | None:
    paths = [Path.home() / ".claude" / "settings.json"]
    if cwd:
        paths += [
            Path(cwd) / ".claude" / "settings.json",
            Path(cwd) / ".claude" / "settings.local.json",
        ]
    language = None
    for path in paths:
        try:
            value = json.loads(path.read_text(encoding="utf-8")).get("language")
        except (OSError, ValueError, AttributeError):
            continue
        if isinstance(value, str) and value.strip():
            language = value.strip()
    return language


def prose_words(text: str) -> list[str]:
    text = _FENCE.sub(" ", text)
    lines = [line for line in text.splitlines() if not line.lstrip().startswith(("|", ">"))]
    text = "\n".join(lines)
    text = _INLINE.sub(" ", text)
    text = _URL.sub(" ", text)
    text = _PATHLIKE.sub(" ", text)
    return [w.lower() for w in _WORD.findall(text)]


def wrong_language(text: str, language: str) -> str | None:
    """The other language the prose is in, or None."""
    target = ALIASES.get(language.lower(), language.lower())
    if target not in FUNCTION_WORDS:
        return None
    words = prose_words(text)
    if len(words) < MIN_WORDS:
        return None
    own = sum(w in FUNCTION_WORDS[target] for w in words)
    for other, vocab in FUNCTION_WORDS.items():
        if other == target:
            continue
        foreign = sum(w in vocab for w in words)
        if foreign >= MIN_FOREIGN and foreign > RATIO * own:
            return other
    return None


def decide(payload: dict) -> str | None:
    if payload.get("hook_event_name", "Stop") != "Stop" or payload.get("agent_id"):
        return None
    if payload.get("stop_hook_active"):
        return None
    text = payload.get("last_assistant_message") or ""
    language = _settings_language(payload.get("cwd") or os.getcwd())
    if not text or not language:
        return None
    other = wrong_language(text, language)
    if other is None:
        return None
    return (
        f"Reply in {language}: your last message is in {other.capitalize()}. Write it again in "
        f"{language}; technical terms and identifiers stay as they are."
    )


def main() -> None:
    try:
        reason = decide(json.load(sys.stdin))
    except Exception:
        return
    if reason:
        print(json.dumps({"decision": "block", "reason": reason}))


if __name__ == "__main__":
    main()
