"""A stand-in for a repo's receipt check: prints ``<plan stem>.out`` next to the plan and exits 1
when a line of it is no ``warning:``; appends its argv as one JSON line to ``argv.log``."""

import json
import sys
from pathlib import Path

with open("argv.log", "a", encoding="utf-8") as log:
    log.write(json.dumps(sys.argv[1:]) + "\n")
plan = Path(sys.argv[1])
out = plan.with_suffix(".out")
lines = out.read_text(encoding="utf-8").splitlines() if out.is_file() else []
for line in lines:
    print(line)
sys.exit(1 if any(not line.startswith("warning:") for line in lines) else 0)
