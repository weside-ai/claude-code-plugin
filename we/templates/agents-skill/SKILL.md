---
name: claude-rules
description: Load the `.claude/rules` guidance that applies to the files you are about to touch; use before planning, editing, reviewing, testing or deploying in this repo.
---

# Rules

This repo keeps binding guidance in `.claude/rules/**`. Claude Code loads it by itself.
Every other agent has to ask for it — that is what this skill is for.

## Workflow

1. Read the repo's `AGENTS.md`. It is the instruction file for every agent.
2. Resolve the loader once:

   ```bash
   # we-install-resolver: the install Claude Code uses in this directory (project scope first)
   LOADER=$(python3 -c 'if True:
       import json, os, sys
       f = os.path.join(os.environ.get("CLAUDE_CONFIG_DIR") or os.path.expanduser("~/.claude"), "plugins", "installed_plugins.json")
       want, run = sys.argv[1], "--exec" in sys.argv[2:3]
       try:
           rows = [e for k, v in json.load(open(f))["plugins"].items() if k.split("@")[0] == "we" for e in v]
       except Exception:
           sys.stderr.write("we plugin: " + f + " not readable; the plugin is not resolved\n")
           sys.exit(0 if run else 1)
       here = os.path.realpath(os.getcwd())
       def holds(e):
           p = os.path.realpath(e.get("projectPath") or "/nonexistent")
           return e.get("scope") in ("project", "local") and (here == p or here.startswith(p.rstrip("/") + "/"))
       near = sorted((e for e in rows if holds(e)), key=lambda e: len(os.path.realpath(e["projectPath"])))
       pick = (near or [e for e in rows if e.get("scope") == "user"] or [None])[-1]
       if pick is None:
           sys.stderr.write("we plugin: no we install in " + f + "\n")
           sys.exit(0 if run else 1)
       path = os.path.join(pick["installPath"], want)
       if run:
           os.execvp(sys.executable, [sys.executable, path] + sys.argv[3:])
       print(path)
   ' scripts/load-rules.py)
   ```

   Empty, with one line naming `installed_plugins.json` → the `we` plugin is not installed
   here; say so instead of proceeding without the rules.

3. Load what applies to the files you are about to touch — **before** the first edit,
   because `--changed` has nothing to report until something has already changed:

   ```bash
   python3 "$LOADER" path/to/file.py another/file.ts
   ```

   Mid-task, against what you have already changed:

   ```bash
   python3 "$LOADER" --changed
   ```

4. Follow the always-on rules and every path-matched rule. They outrank your defaults.

## When a rule seems not to apply

```bash
python3 "$LOADER" --explain path/to/file.py
```

prints, per rule, whether it is always-on, which glob matched, or how many patterns were
tried without a hit — and it names frontmatter defects (`globs:` instead of `paths:`, an
unterminated block) rather than silently treating the rule as always-on.

## Notes

- A rule without `paths:` loads always; one with `paths:` loads for matching files.
- Treat `.claude/commands` and `.claude/skills` as workflow documentation unless your
  runtime exposes them natively.
- In a git worktree, check `pwd`, `git branch --show-current` and `git status --short`
  inside that worktree before editing, and use absolute paths for writes.
