#!/usr/bin/env python3
"""Age out a hook's per-session files: the hook that writes them calls ``prune`` after a write.

Per-session state (``~/.claude/we-timing/<session>.jsonl``, ``<state dir>/conflict-gate/<session>.json``)
grows by one file per session and nothing else removes it. ``prune(folder, pattern)`` deletes the
files matching ``pattern`` whose mtime is older than ``MAX_AGE_DAYS`` (30), at most once per
``EVERY_S`` (one day) per folder: the folder's ``.pruned`` file stamps the last sweep. Never raises:
a sweep that fails leaves the files for the next one.
"""

from __future__ import annotations

import contextlib
import time
from pathlib import Path

MAX_AGE_DAYS = 30
EVERY_S = 86_400
STAMP = ".pruned"


def prune(
    folder: Path,
    pattern: str,
    max_age_days: float = MAX_AGE_DAYS,
    every_s: float = EVERY_S,
    now: float | None = None,
) -> int:
    """Delete stale files under ``folder``; return how many went (0 when the sweep was skipped)."""
    now = time.time() if now is None else now
    stamp = folder / STAMP
    removed = 0
    with contextlib.suppress(OSError):
        if stamp.exists() and now - stamp.stat().st_mtime < every_s:
            return 0
        stamp.touch()
        cutoff = now - max_age_days * 86_400
        for path in folder.glob(pattern):
            with contextlib.suppress(OSError):
                if path.is_file() and path.stat().st_mtime < cutoff:
                    path.unlink()
                    removed += 1
    return removed
