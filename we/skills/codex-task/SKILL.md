---
name: codex-task
description: >
  Sends one task to Codex via the Codex plugin runtime; --background detaches it. Ends with the
  Codex subscription (at the latest 11.10.2026). Trigger: "/we:codex-task".
argument-hint: '[--background] <task text>'
allowed-tools: Bash(node:*), Bash(ls:*)
---

# /we:codex-task

Ends with the Codex subscription: cancelled 27.09.2026, runs until 11.10.2026 at the latest; delete
this skill then. Codex is no dispatch backend for `/we:orchestrate` (decision 27.09.2026).

1. Resolve the runtime:
   `CODEX_COMPANION=$(ls -d ~/.claude/plugins/cache/openai-codex/codex/*/scripts/codex-companion.mjs | sort -V | tail -1)`.
   Empty → the Codex plugin is not installed; say so and stop.
2. Strip `--background` (and the no-op `--foreground`); the rest is the task text, passed unchanged
   as one argument. No text left → ask what the task is. Add no instructions of your own.
3. Foreground: `node "$CODEX_COMPANION" task --write --cwd "$(pwd)" "<task>"` and return its stdout
   verbatim, without acting on it.
4. Background: `node "$CODEX_COMPANION" task --write --background --cwd "$(pwd)" "<task>"` as a
   normal foreground Bash call; it returns a `task-…` id at once. Do not also set
   `run_in_background: true`: the double detach orphans the job and `/codex:status` never sees it.
   Then tell the user: progress `/codex:status`, result `/codex:result`.
