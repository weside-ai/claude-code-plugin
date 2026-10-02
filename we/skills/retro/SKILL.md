---
name: retro
description: >
  Retrospective on a session or PR cycle: frictions from transcript + gh become optimization inbox
  entries. Triggers: "/we:retro", "retro", "post-mortem".
---

# /we:retro

1. Apply `${CLAUDE_PLUGIN_ROOT}/references/privacy-guard.md` at every step that reads the transcript.
2. A retro captures; it never edits a rule, skill, instruction file or source file. Each finding
   becomes an inbox entry per `${CLAUDE_PLUGIN_ROOT}/references/optimization-store.md`, and
   `/we:optimize` decides it later.
3. Create no ticket unless the user asks.

Invocation: `/we:retro` (this branch and its last PR) · `--pr <N>` · `--session <id>` (read that
session's transcript instead of this one) · `--auto` (run by `/we:orchestrate` or `/we:merged` in the
background: asks nothing, writes entries only).

## Where entries go

- The repo's `.weside/optimization/inbox/`, also for a finding about a plugin file (`target_repo: plugin`).
- No store: manual → ask once whether to create it (`/we:setup` § Instruction loop), declined →
  print the findings only; `--auto` → write nothing and end with one line saying so.
- The plugin's own checkout (`origin` matches `repository` in `plugin.json`): print the findings, write nothing.
- `--auto` in a repo whose instruction files grant no direct docs commit → the staging directory
  from the store reference.

## Gather (parallel)

- The transcript: in context, or `~/.claude/projects/<repo-id>/<session>.jsonl` (after a compaction,
  or the `--session` id), scoped to this cycle. Look for user corrections, nudges ("go on"), stops
  that announced instead of acting, avoidable questions, loops on one problem, false "green" reports.
- With authenticated `gh`: `gh pr view <N> --json commits,reviews,comments,statusCheckRollup`,
  `gh pr checks <N>`, the failing part of each red run (`gh run view <id> --log-failed`). Without
  `gh`: `git log --oneline origin/<default>..HEAD` and say that PR/CI data is missing.
- The instruction files that loaded: `AGENTS.md` / `CLAUDE.md`, `.claude/rules/**` (frontmatter and
  first lines), the skills the cycle ran.

## Findings

Each friction: what happened, the evidence (transcript turn, duration, commit range or run id), the
root cause, and the instruction line that caused it, or that was missing. A friction with no
instruction-file remedy is dropped.

Map each to an entry: target file (path-bound rule > always-loaded instruction file > `docs/` >
plugin file), pattern (`gap` for a missing instruction; otherwise the audit id it matches, e.g.
`G2-volatile` for a line the code contradicts, `G2-conflict` for two files that disagree,
`G2-recency` for a rule that steered the session around a problem that was not there), action and
confidence (High when the transcript shows the user correcting it, else Medium). The entry body
carries the proposed lines. Evidence line: `- <date> retro PR #<N> | session <id>: <fact>`.

## Write

1. Per finding, `ls .weside/optimization/inbox/*-<key>.md`: a hit gains an evidence line, none
   gets a new file.
2. Commit per `${CLAUDE_PLUGIN_ROOT}/references/plan-commit.md`, except `--auto` in staging.
3. Close with one line: entries created, entries repeated (with their new counts), where they are.
