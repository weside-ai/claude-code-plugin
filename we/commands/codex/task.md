---
description: Send a write-capable task to Codex (gpt-5-codex). Foreground by default, --background to detach (poll with /codex:status, read with /codex:result).
argument-hint: '[--background] <task text>'
allowed-tools: Bash(node:*), Bash(ls:*)
---

Send a task to Codex through the same `codex-companion.mjs task` runtime the
`/codex:rescue` subagent uses — write-capable, runs in this repo, and streams
phase updates into the shared Codex job-state (so `/codex:status` and
`/codex:result` see it).

Codex is an **optional** execution backend (the official Codex plugin,
[openai/codex-plugin-cc](https://github.com/openai/codex-plugin-cc)). This
command only works when that plugin is installed; the `we` plugin never
hard-depends on it.

Raw arguments: `$ARGUMENTS`

Resolve the companion script (latest installed version):

```bash
CODEX_COMPANION=$(ls -d ~/.claude/plugins/cache/openai-codex/codex/*/scripts/codex-companion.mjs | sort -V | tail -1)
```

Parse `$ARGUMENTS`: pull out `--background` (and the no-op `--foreground`) as
execution control; everything else is the task prompt text. Keep the prompt
text exactly as written.

**Foreground (default):** run and return Codex's stdout verbatim — no summary,
no commentary, do not act on what Codex reports.

```bash
node "$CODEX_COMPANION" task --write --cwd "$(pwd)" "<prompt text>"
```

**Background (`--background` present):** the companion **detaches the job itself**
and registers it in the shared Codex job-state (that is what `/codex:status` and
`/codex:result` read). Run it in **Bash foreground** — `--background` returns
immediately with a `task-…` id, so it does not block your turn:

```bash
node "$CODEX_COMPANION" task --write --background --cwd "$(pwd)" "<prompt text>"
```

⚠️ **Do NOT also pass Bash `run_in_background: true` here.** Combining the two
detach mechanisms double-detaches: the companion's job is orphaned (the work
never runs, the worktree stays empty) and `/codex:status` cannot see it. Pick
exactly one backgrounding mechanism — for `--background`, that is the companion's,
and the Bash call stays foreground. This single-detach rule is the canonical
dispatch contract: [`${CLAUDE_PLUGIN_ROOT}/references/codex-dispatch.md`](../../references/codex-dispatch.md).

After launching, tell the user: "Codex task started in the background. Progress: `/codex:status`, result: `/codex:result`."

> **If you instead need to keep working while a *foreground* companion call runs**
> (e.g. orchestrating a long chunk and you want the harness completion-notification
> rather than `/codex:status`), omit `--background` and wrap the **foreground**
> command in Bash `run_in_background: true`. That is the other valid single-detach
> shape. Never `--background` **and** Bash background together.

Rules:

- The prompt may be multi-line; pass it as a single argument.
- Do not add review/build instructions of your own — forward the user's intent.
- If no task text remains after stripping flags, ask the user what the task is.
