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
   LOADER=$(ls -d ~/.claude/plugins/cache/weside-ai/we/*/scripts/load-rules.py | sort -V | tail -1)
   ```

   Nothing found → the `we` plugin is not installed here; say so instead of proceeding
   without the rules.

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
