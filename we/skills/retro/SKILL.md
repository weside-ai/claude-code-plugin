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
session's transcript instead of this one) · `--key <KEY>` (a ticket or epic across every session and
PR that names it, § Gather) · `--focus "<question>"` (the question an owner asked: every finding says
how it answers it, the close line answers it) · `--auto` (§ Auto mode: asks nothing, writes entries only) ·
`--broadcast ["<focus>"]` (an orchestrator's crew-wide retro, § Broadcast) · `--collect` (what a session
runs on a broadcast's brief, § Broadcast).

## Where entries go

- The repo's `.weside/optimization/inbox/`, also for a finding about a plugin file (`target_repo: plugin`).
- No store: manual → ask once whether to create it (`/we:setup` § Instruction loop), declined →
  print the findings only; `--auto` → write nothing and end with one line saying so.
- The plugin's own checkout (`origin` matches `repository` in `plugin.json`): print the findings, write nothing.
- `--auto` and `--collect`: the staging dir, store reference § Staging.

## Auto mode

`/we:master` and `/we:merged` each decide by their own criteria whether a cycle earns a retro,
then dispatch it here the same way:

1. Run `bash ${CLAUDE_PLUGIN_ROOT}/scripts/retro_claim.sh <N>` from the repo: `covered: …` (exit 1)
   → skip; `claimed <path>` (exit 0) → the claim exists outside the repo, go on. Never compute the
   path yourself: a guessed path misses the real claims.
2. Dispatch `Agent(subagent_type="we:dev-medium", description="retro-<N>", run_in_background=true)`
   (no `name`: `teammate_gate.py`) with the brief "Use the Skill tool with skill `we:retro` and args
   `--auto --pr <N> --session $CLAUDE_CODE_SESSION_ID`. Work from <main checkout path>." The caller
   does not wait for it.

## Broadcast

One retro across every running session, decided in one PR instead of one per session. Recipients,
the caller's own part and tracking: `${CLAUDE_PLUGIN_ROOT}/references/broadcast.md`. Without a
focus at most once a week: when the charter's `last_broadcast:` on the default branch is under
seven days old, ask the caller once for a focus before the briefs; none given → say in one line
that no broadcast goes out, and stop.

1. **Brief.** Each recipient gets: "Run `/we:retro --collect` on your own session, focus:
   <focus>. At most two entries, the most important first; `nothing` is the expected answer.
   Reply to <orchestrator's name> with one line `RETRO · <your name> · <a> add, <r> remove:
   <keys>` or `RETRO · <your name> · nothing`. On the critical path, finish your current step
   first." Without a focus the brief asks two questions of equal rank: what did you load, follow
   or wait on this cycle that did not help, and what would you delete; which lived practice beats
   the documented one and would be lost on a restart. No one-off incidents, nothing a rule says.
2. **Own retro.** Run `--collect` on your own session with the same focus; your `RETRO · …` line is
   a row like the others.
3. **Decide.** In one worktree off fresh `origin/<default>`: move the staging dir's entries into
   `inbox/` (the move empties staging), run `/we:optimize` there, set the charter's
   `last_broadcast:` to today, commit one PR. Right before the commit, read staging again: a
   receiver that appended an evidence line after the move found no file and staged a new one under
   the same key: fold its evidence lines into that key's worktree entry, then remove it from staging.

`--collect` (the receiver): Gather and Findings on its own session, scoped to the focus, at most
two entries. Write only to the staging dir, deduplicated by key against staging and the main checkout's `inbox/`
(§ Write step 1); no commit, no branch, no PR. Close with exactly the one `RETRO · …` line, sent
by `SendMessage` to the orchestrator (the orchestrator's own run keeps it as its row).

## Gather (parallel)

- The transcript: in context, or `~/.claude/projects/<repo-id>/<session>.jsonl` (after a compaction,
  or the `--session` id), scoped to this cycle. Look for user corrections, nudges ("go on"), stops
  that announced instead of acting, avoidable questions, loops on one problem, false "green" reports,
  expensive tool calls (one output over ~10k tokens, an MCP loaded and never used), information the
  session lacked and had to guess (logs, staging data, a ticket it could not read), and instruction
  text it loaded or followed, or a wait it sat out, that changed nothing.
- `--key <KEY>`: every PR that names it (`gh pr list --state all --search <KEY>`, for an epic each
  story key of its plan too), the commits on `origin/<default>` that name it, its plan and Updates
  Log, and the transcripts under `~/.claude/projects/*/` that name it (privacy guard first); one
  session's view of a ticket misses the scope that grew across sessions.
- Flow, not only conversation: per waiting stretch who waited on whom and how long (the board's
  transitions and questions logs where a crew keeps them, else the transcript times), PRs per
  ticket and titles counting parts ("part N", "Teil N"), heads per PR, and ticket state against git
  (`board.py check`, a merged PR under a ticket still Selected).
- With authenticated `gh`: `gh pr view <N> --json commits,reviews,comments,statusCheckRollup`,
  `gh pr checks <N>`, the failing part of each red run (`gh run view <id> --log-failed`). Without
  `gh`: `git log --oneline origin/<default>..HEAD` and say that PR/CI data is missing.
- The instruction files that loaded: `AGENTS.md` / `CLAUDE.md`, `.claude/rules/**` (frontmatter and
  first lines), the skills the cycle ran.
- `~/.claude/we-timing/<session>.jsonl` for the cycle's session (the `--session` id, else this one;
  kept 45 days; missing → say so): its `InstructionsLoaded` lines name the rule files that loaded and why, its `PreToolUse` (`skill`) and `UserPromptExpansion` lines the skills that ran;
  cite them as evidence instead of inferring from `paths:` frontmatter.

## Findings

Each friction: what happened, the evidence (transcript turn, duration, commit range or run id), the
root cause, and the instruction line that caused it, or that was missing. A process finding (who
waits on whom, a wake window, a crew setting) is kept: its target is the crew file
(`.weside/crew.json`), the process L0 (`plugin:process/L0.md`) or the role file that sets it. Only a
friction no file in the repo or the plugin could change is dropped.

Map each to an entry: target file (path-bound rule > always-loaded instruction file > crew file or
role file > `docs/` > plugin file, the L0 included), pattern (`gap` for a missing instruction, `remove` for one that did not help; otherwise the audit id it matches, e.g.
`G2-volatile` for a line the code contradicts, `G2-conflict` for two files that disagree,
`G2-recency` for a rule that steered the session around a problem that was not there), action and
confidence (High when the transcript shows the user correcting it, else Medium). A rule only a
reviewer has to enforce targets the reviewer's question file (the lens agent, the review workflow's
prompt), never the worker brief: the builder carries the most context, the reviewer reads only the diff.

| Good target | Bad target |
|---|---|
| "Worker forgets type hints" → a question in the architecture lens's file, or a lint gate | the same finding → one more line in the worker brief, which every build then loads |

The entry body carries the proposed lines. Evidence line: `- <date> retro PR #<N> | session <id>: <fact>`.

## Write

1. Per finding, its key per the store reference § Inbox entry (stable keys: inbox, staging and
   `LEDGER.md` on the same target file first); a target outside the repo is `target: ~/<path>`.
   Every entry, new or a repeat, goes through `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/retro_write.py <dir> <body-file>`
   (the whole entry written to the scratchpad first): it creates the file exclusively or appends the evidence lines
   to the file that holds the key. Never `cat >` or the Write tool into the inbox: parallel writers of one broadcast
   lose each other's entries.
2. Commit per `${CLAUDE_PLUGIN_ROOT}/references/optimization-store.md` § Layout (where store commits land), except `--auto` and `--collect` in staging.
3. Close with one line: entries created, entries repeated (with their new counts), where they are;
   with `--focus`, a second line answering the question.
