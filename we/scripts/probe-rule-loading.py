#!/usr/bin/env python3
"""Record what Claude Code really loads, as golden fixtures for `rule_loading.py`.

Each case builds a throwaway git repo with ONE rule whose body carries a random code word,
asks `claude -p` to read one file, and records whether the code word reached the model. The
matcher test (`test_rule_loading.py`) replays the committed fixtures; CI never runs this probe,
because it needs a logged-in `claude` and costs one Haiku call per case.

Usage: probe-rule-loading.py [--out FILE] [--jobs N] [--only ID ...]
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import secrets
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

DEFAULT_OUT = Path(__file__).with_name("fixtures") / "rule-loading.json"
MODEL = "haiku"

# (id, frontmatter block or None for no frontmatter, file to read). The probe writes the rule
# as `.claude/rules/probe.md`; `{fm}` is placed between the opening and closing `---`. A case
# whose frontmatter must stay unterminated sets the block to start with "!open\n".
CASES: list[tuple[str, str | None, str]] = [
    ("always-on", None, "other/x.md"),
    ("star-same-dir", 'paths:\n  - "src/*.py"', "src/mod.py"),
    ("star-not-deeper", 'paths:\n  - "src/*.py"', "src/deep/mod.py"),
    ("root-star-not-nested", 'paths:\n  - "*.md"', "docs/a.md"),
    ("root-star-root", 'paths:\n  - "*.md"', "README.md"),
    ("dstar-zero-dirs", 'paths:\n  - "dir/**/*.py"', "dir/x.py"),
    ("dstar-leading-root", 'paths:\n  - "**/*.ts"', "a.ts"),
    ("dstar-leading-deep", 'paths:\n  - "**/*.ts"', "x/y/a.ts"),
    ("question-mark", 'paths:\n  - "src/?.py"', "src/a.py"),
    ("comma-string-hit", 'paths: "src/*.ts, lib/**"', "lib/x/y.md"),
    ("comma-string-miss", 'paths: "src/*.ts, lib/**"', "other/z.ts"),
    ("inline-list", 'paths: ["src/**", "lib/*.py"]', "lib/a.py"),
    ("brace-hit", 'paths:\n  - "src/**/*.{ts,tsx}"', "src/a/b.tsx"),
    ("brace-miss", 'paths:\n  - "src/**/*.{ts,tsx}"', "src/a.js"),
    ("brace-nested", 'paths:\n  - "{a,b}/{c,d}/*.{ts,tsx}"', "b/d/x.ts"),
    (
        "brace-over-budget",
        'paths:\n  - "{a,b,c,d,e,f,g,h,i,j}/{a,b,c,d,e,f,g,h,i,j}/{a,b,c,d,e,f,g,h,i,j}/{x,y}"',
        "a/b/c/x",
    ),
    ("invalid-bracket", 'paths:\n  - "src/[z-a].py"', "src/a.py"),
    ("unclosed-bracket", 'paths:\n  - "photos [2024/**"', "photos [2024/a.png"),
    ("globs-key", 'globs:\n  - "src/**"', "other/x.md"),
    ("broken-yaml-unrelated", "paths: [src/**", "other/x.md"),
    ("unquoted-star-unrelated", "paths:\n  - **/*.py", "other/x.md"),
    ("unquoted-star-hit", "paths:\n  - **/*.py", "x/y.py"),
    ("unterminated-unrelated", '!open\npaths:\n  - "src/**"', "other/x.md"),
    ("broken-yaml-scoped", "paths: [src/**", "src/a.py"),
    ("broken-yaml-elsewhere", 'description: a: b: c\npaths:\n  - "src/**"', "other/x.md"),
    ("unquoted-plain-scalar", "paths: src/*.py", "src/deep/mod.py"),
    ("unquoted-star-scalar", "paths: *.md", "docs/x.txt"),
    ("basename-deep", 'paths:\n  - "*.py"', "a/b/c.py"),
    ("bare-name-dir", 'paths:\n  - "docs"', "docs/a.md"),
    ("slash-anchored", 'paths:\n  - "src/a.py"', "x/src/a.py"),
    ("trailing-slash-dir", 'paths:\n  - "src/"', "src/a.py"),
    ("leading-slash", 'paths:\n  - "/src/*.py"', "src/a.py"),
    ("negation", 'paths:\n  - "src/**"\n  - "!src/gen/**"', "src/gen/x.py"),
    ("unquoted-star-scalar-hit", "paths: *.md", "docs/x.md"),
    ("colon-value-scoped", 'description: a: b: c\npaths:\n  - "src/**"', "src/a.py"),
    ("unfixable-yaml-unrelated", 'paths:\n  - "src/**"\n  - *.md', "other/x.txt"),
    ("empty-list", "paths: []", "other/x.md"),
    ("empty-string", 'paths: ""', "other/x.md"),
    ("negation-keeps-rest", 'paths:\n  - "src/**"\n  - "!src/gen/**"', "src/app/x.py"),
]

PROMPT = (
    "Use the Read tool to read the file `{file}`. Then check every instruction, system "
    "reminder and context block you have received in this conversation. If any of them "
    "contains a code word that starts with `PROBE-` followed by digits, reply with exactly "
    "that code word. Otherwise reply with exactly NONE. Do nothing else."
)


def rule_text(frontmatter: str | None, word: str) -> str:
    body = f"# Probe rule\n\nThe code word is {word}.\n"
    if frontmatter is None:
        return body
    if frontmatter.startswith("!open\n"):
        return "---\n" + frontmatter.removeprefix("!open\n") + "\n" + body
    return f"---\n{frontmatter}\n---\n{body}"


def run_case(case: tuple[str, str | None, str], timeout: int) -> dict:
    case_id, frontmatter, target = case
    word = f"PROBE-{secrets.randbelow(10**8):08d}"
    text = rule_text(frontmatter, word)
    with tempfile.TemporaryDirectory(prefix="we-rule-probe-") as tmp:
        root = Path(tmp)
        (root / ".claude" / "rules").mkdir(parents=True)
        (root / ".claude" / "rules" / "probe.md").write_text(text, encoding="utf-8")
        (root / target).parent.mkdir(parents=True, exist_ok=True)
        (root / target).write_text("A plain file with no instructions.\n", encoding="utf-8")
        subprocess.run(["git", "init", "-q"], cwd=root, check=True)
        subprocess.run(["git", "add", "-A"], cwd=root, check=True)
        subprocess.run(
            [
                *("git", "-c", "user.name=probe", "-c", "user.email=probe@example.invalid"),
                *("commit", "-qm", "probe"),
            ],
            cwd=root,
            check=True,
        )
        result = subprocess.run(
            [
                *("claude", "-p", "--model", MODEL, "--permission-mode", "plan"),
                *("--setting-sources", "project", "--strict-mcp-config"),
                PROMPT.format(file=target),
            ],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    answer = result.stdout.strip()
    return {
        "id": case_id,
        "rule": text.replace(word, "PROBE-<word>"),
        "read": target,
        "loaded": word in answer,
        "answer": "<word>" if word in answer else answer[:80],
        "exit": result.returncode,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--jobs", type=int, default=4)
    parser.add_argument("--timeout", type=int, default=180)
    parser.add_argument("--only", nargs="*", help="case ids to (re-)record")
    args = parser.parse_args()

    cases = [c for c in CASES if not args.only or c[0] in args.only]
    with ThreadPoolExecutor(max_workers=args.jobs) as pool:
        results = list(pool.map(lambda c: run_case(c, args.timeout), cases))

    failed = [r for r in results if r["exit"] != 0]
    for record in results:
        print(f"{record['id']:28} loaded={record['loaded']!s:5} answer={record['answer']}")
    if failed:
        print(f"{len(failed)} case(s) failed to run; nothing written", file=sys.stderr)
        return 1

    existing = {}
    if args.only and args.out.exists():
        existing = {c["id"]: c for c in json.loads(args.out.read_text())["cases"]}
    for record in results:
        record.pop("exit")
        existing[record["id"]] = record
    version = subprocess.run(
        ["claude", "--version"], capture_output=True, text=True, check=False
    ).stdout.strip()
    payload = {
        "claude_code": version,
        "model": MODEL,
        "recorded": dt.datetime.now(dt.UTC).date().isoformat(),
        "cases": [existing[c[0]] for c in CASES if c[0] in existing],
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {len(payload['cases'])} cases to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
