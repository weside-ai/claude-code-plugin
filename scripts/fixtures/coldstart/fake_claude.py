#!/usr/bin/env python3
"""A stand-in for ``claude`` in the harness tests: records argv, env and cwd, replays a transcript.

``FAKE_CLAUDE_LOG``: a directory; each call appends one JSON line ``{argv, env, cwd, files}`` to
``calls.jsonl`` there (``files``: the paths in its cwd). ``FAKE_CLAUDE_STREAM``: the stream-json
file it prints. ``FAKE_CLAUDE_SLEEP``: seconds to sleep first. ``FAKE_CLAUDE_EXIT``: its exit code.
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

log = Path(os.environ["FAKE_CLAUDE_LOG"])
cwd = Path.cwd()
rels = (p.relative_to(cwd).as_posix() for p in cwd.rglob("*") if p.is_file())
files = sorted(r for r in rels if not r.startswith(".git/"))
mcp = sys.argv[sys.argv.index("--mcp-config") + 1] if "--mcp-config" in sys.argv else None
with (log / "calls.jsonl").open("a", encoding="utf-8") as fh:
    fh.write(
        json.dumps(
            {
                "argv": sys.argv[1:],
                "env": dict(os.environ),
                "cwd": str(cwd),
                "files": files,
                "git": (cwd / ".git").is_dir(),
                "mcp": json.loads(Path(mcp).read_text()) if mcp else None,
            }
        )
        + "\n"
    )
time.sleep(float(os.environ.get("FAKE_CLAUDE_SLEEP") or 0))
stream = os.environ.get("FAKE_CLAUDE_STREAM")
if stream:
    sys.stdout.write(Path(stream).read_text(encoding="utf-8"))
sys.exit(int(os.environ.get("FAKE_CLAUDE_EXIT") or 0))
