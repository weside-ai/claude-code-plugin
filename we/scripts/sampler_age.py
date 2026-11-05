#!/usr/bin/env python3
"""The sampler's pulse: is the flow log's newest line younger than ``flow.stale_min``?

Usage:
  sampler_age.py [--max-min N] [--log-dir DIR] [--tz TZ]

Prints one verdict line and exits with its code:

- ``sampler: ok (<ts>)``, exit 0: the newest line (today's or yesterday's file, ``flow_log.newest``)
  is at most ``N`` minutes old;
- ``sampler: stale since <N> min (last line <ts>)``, exit 1;
- ``sampler: stale, no line today or yesterday in <dir>``, exit 1;
- ``sampler: not bound (flow.log_dir unset)``, exit 0: the crew binds no sampler, nothing to check.

``N`` defaults to the crew's ``flow.stale_min``; ``--log-dir`` and ``--tz`` default to the crew's
``flow.log_dir`` and ``sla.tz`` (``flow_log.configured``). Callers: ``/we:standup``, a workspace
health check, and the prompt hook ``hooks/sampler_on_prompt.py`` (through ``verdict``).
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

_HERE = str(Path(__file__).resolve().parent)
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import flow_log  # noqa: E402


def verdict(log_dir, tz, max_min, now=None):
    """(exit code, line, episode): ``episode`` names the stale episode (the last line's ``ts``, or
    ``none-<UTC date>`` without a line); None when not bound."""
    if log_dir is None:
        return 0, "sampler: not bound (flow.log_dir unset)", None
    now = now or datetime.now(timezone.utc)
    found = flow_log.newest(log_dir, tz, now)
    if found is None:
        return (
            1,
            f"sampler: stale, no line today or yesterday in {log_dir}",
            f"none-{now.strftime('%Y-%m-%d')}",
        )
    ts, age = found
    if age > float(max_min) * 60:
        return 1, f"sampler: stale since {age // 60} min (last line {ts})", ts
    return 0, f"sampler: ok ({ts})", ts


def main(argv=None):
    p = argparse.ArgumentParser(prog="sampler_age.py", description="The sampler's pulse.")
    p.add_argument("--max-min", dest="max_min", type=float)
    p.add_argument("--log-dir", dest="log_dir")
    p.add_argument("--tz")
    args = p.parse_args(argv)
    log_dir, tz, flow, _crew = flow_log.configured()
    log_dir = Path(args.log_dir).expanduser() if args.log_dir else log_dir
    max_min = args.max_min if args.max_min is not None else flow["stale_min"]
    code, line, _episode = verdict(log_dir, args.tz or tz, max_min)
    print(line)
    return code


if __name__ == "__main__":
    sys.exit(main())
