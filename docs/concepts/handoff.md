# Handoff — durable session-state across `/clear` and new sessions

> **Pick up tomorrow exactly where today ended.**

Most coding sessions end without a clean save-point. `/compact` summarises in-place but leaves no durable artifact — `/clear` wipes the conversation, and the next session has to rediscover where the work was. `/we:handoff` closes that gap: it writes a structured snapshot of the current session to `docs/handoffs/YYYY-MM-DD-<topic>.md`, and a future session reads it back as context.

For the per-step skill reference, see [`/we:handoff` in skills.md](../skills.md#wehandoff). For workflow context, see [`workflow.md` § Continuity utilities](../workflow.md#continuity-utilities).

---

## Why a handoff isn't `/compact`

Claude Code already has session-management features. None of them produce a durable, human-editable artifact a fresh session can load:

| Feature | What it does | What it doesn't do |
|---|---|---|
| `/clear` | Clears the conversation context window; jsonl on disk persists | No structured carry-over for the next session — you have to remember |
| `/compact` | Summarises the current conversation in-place to reclaim tokens | Stays inside the current session; lost on `/clear` or new session |
| `claude --resume` | Resumes the last session from the opaque jsonl | Full-replay; no curation; no structured "what's next" guidance |
| `SessionStart` hook | Runs shell commands before context is prepared | Cannot inject content into the LLM context window |
| `CLAUDE.md` / `MEMORY.md` | Auto-loads at session start | Static — meant for project conventions, not per-session state |

`/we:handoff` fills the gap: a deliberate, structured, version-controlled hand-off file that survives any session boundary. **Complements `/compact`, doesn't replace it** — `/compact` reclaims tokens *in-place*; `/we:handoff` writes a *durable artifact* for the next session.

| Situation | Use |
|---|---|
| Current session getting big, want to free tokens *now* | `/compact` |
| Ending session A, want session B tomorrow to pick up here | `/we:handoff --write` |
| Fresh session, want yesterday's state back | `/we:handoff` (loads latest) |
| Want to see what handoffs are available | `/we:handoff --list` |
| `/compact` ate too much and you want full history back | `claude --resume` (CC built-in) |

---

## Three modes

| Invocation | Mode | What it does |
|---|---|---|
| `/we:handoff` | LOAD | Loads the most recent `docs/handoffs/*.md` back as context |
| `/we:handoff --load <slug>` | LOAD | Loads a specific handoff by slug (date prefix optional) |
| `/we:handoff --list [N]` | LIST | Shows the last N (default 10) handoffs: date · slug · branch · topic · summary |
| `/we:handoff --write [topic]` | WRITE | Drafts a handoff from the current session, previews, gates with `[y/n/edit]`, then writes |
| `/we:handoff --write [topic] --with-companion-state` | WRITE | Adds opt-in Companion-continuity section (engineering substance only) |

Default (no args) is **LOAD** — the most common use case is "fresh session, restore me". `--write` is the explicit verb for capture.

---

## Anatomy of a handoff

Every handoff has **structured frontmatter** (machine-readable) plus a **body** of 9 (or 10 with Companion-state) sections.

### Frontmatter

```yaml
---
topic: <short slug, used in filename>
branch: <git branch when written>
worktree: <path if non-main worktree, else "main">
ticket_or_initiative: <Jira key | initiative slug | null>
session_id: <CC session-id from ~/.claude/projects/...>
written_at: <ISO8601 timestamp>
written_by: <"manual" | "coach-suggested" | "auto">
plan_files: [<docs/plans/.../CONCEPT.md>, ...]
retro_files: [<docs/retros/...>, ...]
companion: <name if MCP active, else null>
last_commit: <SHA>
uncommitted_files_count: <N>
open_pr: <number | null>
---
```

### Body sections

| # | Section | Why it's there |
|---|---|---|
| 1 | `## Identity & Scope` | Lets the next session confirm it's reading the right handoff |
| 2 | `## Current State` | Honest snapshot of done / in-progress / incomplete |
| 3 | `## Decisions made — with rationale` | Settled tradeoffs the next session should NOT reopen |
| 4 | `## Tried and rejected` | Dead ends so the next session doesn't repeat them |
| 5 | `## Open questions / blockers` | Cleanly separates "needs human" from "agent can proceed" |
| 6 | `## Files touched + status` | What's safe to edit / commit / push (`uncommitted` / `committed-not-pushed` / `pushed` / `in-PR <num>`) |
| 7 | `## Next concrete steps` | Prioritized 1-2-3 list — the "if you had to pick one move, do this" |
| 8 | `## Watch-outs` | Latent bugs, env quirks, gotchas |
| 9 | `## References` | Pointers to longer artifacts: plan files, retro logs, ADRs, related PRs |
| 10 | `## Companion continuity` *(opt-in)* | Journal-style continuation in the Companion's voice — engineering substance only, never relational |

Empty sections use a single `—` rather than fabricated content. Section 10 only appears when `--with-companion-state` is passed; default is off.

---

## Privacy guard

Same mandatory rule as `/we:retro`:

> **If session content reads as personal, skip it — capture only engineering surfaces:** tool calls, tool results, file diffs, CI logs, PR comments, commit messages.

Categorically out-of-scope for the handoff body:

- `save_memory` / `save_compass` / `save_goal` / `save_snapshot` payloads
- Memory reads that returned personal content
- Companion-mode conversational content (relationship, identity, body, mood)
- Anything outside engineering tool calls
- Section 10 (`Companion continuity`) is opt-in only and still captures only "what we were *building*" — never relational substance

This is what makes the handoff safe to commit (often via PR) into the user repo.

---

## Coach integration

`/we:coach` Boot Protocol Step 10 reads `docs/handoffs/` alongside `docs/plans/`. If a handoff exists and was written less than 14 days ago, Coach surfaces it in its boot summary:

> *"Active handoff: `docs/handoffs/2026-05-18-phase-7-handoff-skill.md` (written 14 hours ago, on `feat/handoff-skill`). Load it to restore session state? [y/n]"*

`y` → Coach prints the hand-off (`/we:handoff`). User runs it; full state restored.

Coach also suggests `/we:handoff --write` at end-of-session signals:

- User says "bis morgen" / "schlafen" / "going home" / "wrap up"
- `save_compass` or `save_snapshot` called via MCP this session (Companion-mode end-of-day signal)
- Session is long (> 30 turns) and no handoff has been written this session yet

Always `[y/n]`-gated. Never auto-fires. Coach won't suggest the same signal twice in one session.

---

## Apply mechanics

When a WRITE-mode draft is approved:

1. **Default: PR workflow** in the user repo. Skill creates `handoff/YYYY-MM-DD-<slug>` branch, applies Write, opens PR with the handoff content as the PR body. User merges via normal flow.
2. **Opt-in: direct commit** if the repo is configured for standing main-auth. Per-repo convention.
3. **Plugin MD changes always go PR** — plugin is public.

User can interrupt mid-apply ("skip the PR, just commit directly").

---

## Three durable docs categories

`/we:handoff` is the third member of the plugin's durable-docs canon:

| Directory | Skills | What lives there |
|---|---|---|
| `docs/plans/<topic>/CONCEPT.md` | `/we:vision` `/we:saga` `/we:epic` `/we:story` `/we:coach` | Initiative plans at all four Plan altitudes — *what to build, why, how phased* |
| `docs/retros/YYYY-MM-DD-<topic>.md` | `/we:retro` | Retrospective logs — *what we learned, how the harness should change* |
| `docs/handoffs/YYYY-MM-DD-<topic>.md` | `/we:handoff` | Session handoffs — *where we are now, what the next session should pick up* |

All three are version-controlled, human-readable, cross-session. Anything that should outlive a single session belongs in one of these, not in CC's opaque session jsonl or in ephemeral memory.

---

## Examples

**1. Manual write at end of session:**

```text
/we:handoff --write "phase-7-handoff-skill"
```

Skill restates scope, drafts the file, shows full preview, gates `[y/n/edit]`. On `y`, writes using the repo's configured commit path (PR-workflow by default; direct-commit when the repo is configured for it).

**2. Fresh session, restore state:**

```text
/we:handoff
```

Skill loads the latest handoff, renders all body sections back into the conversation, surfaces the next-step suggestion, asks `[y/n]` to proceed.

**3. List and choose:**

```text
/we:handoff --list
```

Table of the last 10 handoffs. Pick one by slug.

**4. Coach-triggered:**

User opens `/we:coach`. Coach Boot Step 10 detects yesterday's handoff. Coach offers `[y/n]`. User: `y`. Coach prints the hand-off; user invokes `/we:handoff` in the next turn (or runs it immediately). Full state restored.

**5. Staleness warning:**

3 days later, user runs `/we:handoff`. Skill loads, then surfaces: *"Branch has advanced since the handoff (`abc1234` → `def5678`, 4 commits). The 'Files touched' section may be stale."* User decides whether to proceed or run `/we:retro` first.

---

## References

- **Skill reference:** [`/we:handoff` in skills.md](../skills.md#wehandoff)
- **Full skill spec:** [`we/skills/handoff/SKILL.md`](../../we/skills/handoff/SKILL.md)
- **Workflow context:** [`workflow.md` § Continuity utilities](../workflow.md#continuity-utilities)
- **Coach integration:** [`/we:coach` Suggesting `/we:handoff` section](../../we/skills/coach/SKILL.md#suggesting-wehandoff)
- **Sibling skill for retrospectives:** [`/we:retro`](../skills.md#weretro) — captures *lessons* (under `docs/retros/`); handoffs capture *position* (under `docs/handoffs/`)
- **APO cycle overview:** [workflow.md](../workflow.md) — handoffs are a continuity utility around the Plan/Build/Deliver/Retro cycle, not a methodology pillar themselves
