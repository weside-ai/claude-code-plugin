---
name: codex-task
description: Send a task directly to Codex (gpt-5-codex) via the official Codex plugin runtime. Foreground by default; --background detaches the job (poll with /codex:status, read with /codex:result). Requires the openai/codex-plugin-cc plugin to be installed.
argument-hint: '[--background] <task text>'
allowed-tools: Bash(node:*), Bash(ls:*)
---

# /we:codex-task

Send a task to Codex through the `codex-companion.mjs task` runtime — write-capable,
runs in this repo, and streams phase updates into the shared Codex job-state
(so `/codex:status` and `/codex:result` see it).

Codex is an **optional** execution backend (the official Codex plugin,
[openai/codex-plugin-cc](https://github.com/openai/codex-plugin-cc)). This skill
only works when that plugin is installed; the `we` plugin never hard-depends on it.

> **For orchestrated multi-chunk work**, use `/we:orchestrate` — it dispatches
> workers (Codex or otherwise) with proper chunking, integration, and CI. This skill
> is for **direct, one-off Codex tasks** outside the orchestration pipeline.

---

## Steps

### 1. Resolve the runtime

```bash
CODEX_COMPANION=$(ls -d ~/.claude/plugins/cache/openai-codex/codex/*/scripts/codex-companion.mjs | sort -V | tail -1)
```

If this returns nothing, the Codex plugin is not installed. Stop and tell the user.

### 2. Parse arguments

Pull out `--background` (and the no-op `--foreground`) as execution control;
everything else is the task prompt text. Keep the prompt text exactly as written.

### 3. Dispatch

**Foreground (default):** run and return Codex's stdout verbatim — no summary,
no commentary, do not act on what Codex reports.

```bash
node "$CODEX_COMPANION" task --write --cwd "$(pwd)" "<prompt text>"
```

**Background (`--background` present):** the companion **detaches the job itself**
and registers it in the shared Codex job-state. Run it in **Bash foreground** —
`--background` returns immediately with a `task-…` id, so it does not block the turn:

```bash
node "$CODEX_COMPANION" task --write --background --cwd "$(pwd)" "<prompt text>"
```

After launching background: tell the user "Codex task started. Progress: `/codex:status`, result: `/codex:result`."

> ⚠️ **Single-detach rule:** Do NOT also pass Bash `run_in_background: true` when
> using `--background`. Combining both double-detaches: the job is orphaned, the work
> never runs, and `/codex:status` cannot see it. Pick exactly one.
> Full mechanics: [`references/codex-dispatch.md`](../../references/codex-dispatch.md).

---

## Rules

- The prompt may be multi-line; pass it as a single argument.
- Do not add review/build instructions of your own — forward the user's intent.
- If no task text remains after stripping flags, ask the user what the task is.
