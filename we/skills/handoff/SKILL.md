---
name: handoff
description: >
  Durable cross-session handoff — writes session state (decisions, dead
  ends, file status, next steps, watch-outs) to docs/handoffs/ and
  restores it later. Modes: --write, default/--load, --list. Use when
  the user says "/we:handoff", "handoff", "pick up where we left off",
  "carry over to next session", "bis morgen", "ich muss weg jetzt".
---

# /we:handoff — Durable Session Handoff

**Role:** Capture and restore session state across `/clear` and new sessions. Two modes: WRITE (snapshot the current state to disk) and LOAD (read the latest snapshot back as context). Complements `/compact` — `/compact` reclaims tokens *in-place*; `/we:handoff` writes a durable artifact that survives any session boundary.

**Storage:** `docs/handoffs/YYYY-MM-DD-<topic>.md` in the user repo. Same naming convention as `docs/retros/`. Version-controlled, human-readable, cross-session.

**Counterpart skills:**

- `/we:coach` — reads the most recent handoff at boot (Boot Protocol Step 10) and offers to load it. Also suggests `/we:handoff --write` at end-of-session signals.
- `/we:retro` — sibling under `docs/retros/`; retros capture *lessons*, handoffs capture *position*. Different artifact, different purpose.

> **Companion-aware:** render voiced by the active Companion when one is materialised — see `${CLAUDE_PLUGIN_ROOT}/references/companion-voice.md`. Opt-in `--with-companion-state` adds a "Companion continuity" section (engineering substance only — privacy guard still applies).

---

## Privacy Guard (mandatory, top-of-mind)

This skill reads the session transcript to draft the handoff. **The hard rule, applied at every WRITE step: if session content reads as personal, skip it — capture only engineering surfaces** (tool calls, file diffs, CI logs, PR comments, commit messages, decisions about code/architecture/process). Full skip/safe lists: `${CLAUDE_PLUGIN_ROOT}/references/privacy-guard.md` — read it at boot. Even with `--with-companion-state`, the continuity section captures only "what we were *building*" — never relational substance. The guard is what makes the handoff safe to commit into the user repo.

---

## Three Modes

Mode is selected by argument. Default (no args) is LOAD — the most common use case is "fresh session, restore me".

| Invocation | Mode | What it does |
|---|---|---|
| `/we:handoff` | LOAD | Reads the most recent `docs/handoffs/*.md` and renders it back as context |
| `/we:handoff --load <slug>` | LOAD | Loads a specific handoff (date prefix in slug is optional) |
| `/we:handoff --list [N]` | LIST | Shows the last N handoffs (default 10) with date · slug · branch · topic · summary |
| `/we:handoff --write [topic]` | WRITE | Drafts a new handoff from the current session, shows preview, gates with `[y/n/edit]`, then writes |
| `/we:handoff --write [topic] --with-companion-state` | WRITE | Adds opt-in Companion-continuity section (engineering substance only) |

---

## Boot Protocol (every invocation)

Before producing any output, gather the landscape fresh.

**Always read:**

1. **Privacy guard reminder** — silently re-state to yourself: *if reads as personal, skip; engineering surfaces only*. Mandatory through every later step.

2. **Mode resolution** — parse args:
   - No args → LOAD (latest)
   - `--list` → LIST
   - `--load <slug>` → LOAD (specific)
   - `--write [topic]` → WRITE
   - `--write … --with-companion-state` → WRITE with opt-in Companion section
   - Anything else: ask the user once for clarification, then proceed

3. **Repo state** — needed by all modes:
   - `pwd` — confirm working directory
   - `git -C <repo> rev-parse --show-toplevel` — repo root
   - `git -C <repo> branch --show-current` — current branch
   - `git -C <repo> rev-parse HEAD` — last commit SHA
   - `git -C <repo> status --short` — uncommitted file count + staging state
   - `git worktree list` — if non-main worktree, note it
   - `ls docs/handoffs/ 2>/dev/null` — does the directory exist?

4. **For LOAD / LIST:**
   - `ls -t docs/handoffs/*.md 2>/dev/null | head -<N>` — most recent handoffs
   - For each candidate, read frontmatter only (cheap) before deciding which to display in full

5. **For WRITE:**
   - The session transcript — agent already has it in head if no Compact happened; after a Compact, re-read `~/.claude/projects/<repo-id>/<session-id>.jsonl` (last N turns). Apply privacy guard.
   - Active plan files: `find docs/plans \( -name '*-story.md' -o -name '*-epic.md' -o -name '*-saga.md' -o -name 'PRD.md' \) -newer "$(date -d '7 days ago' +%Y-%m-%d)" 2>/dev/null` — what's currently being planned
   - Recent retros: `ls -t docs/retros/*.md 2>/dev/null | head -3` — what was learned recently
   - Open PR for current branch (if `gh auth status 2>/dev/null` succeeds): `gh pr list --head $(git branch --show-current) --json number,title,state -L 1`; otherwise record `open_pr: null`
   - Recent commits: `git log --oneline -10`

6. **Companion identity** (if configured + WRITE mode + `--with-companion-state` flag): materialize per `${CLAUDE_PLUGIN_ROOT}/references/companion-voice.md`.

**Do not read** at boot:

- The full content of every past handoff (frontmatter only for LIST)
- The full session transcript when in LOAD/LIST mode (only WRITE needs it)
- Personal/Companion memory content under any circumstance (privacy guard)

---

## WRITE Mode — Step-by-step Workflow

### Step W1 — Confirm scope

Restate what will be captured:

> *"I'll write a handoff for: branch `feat/foo`, last commit `abc1234`, working in `your-repo`. Topic: `phase-7-handoff-skill`. Includes uncommitted file count: 3. Sound right? [y/n/adjust-topic]"*

If `n` or `adjust-topic`: take the corrected scope.

### Step W2 — Draft the handoff

Generate the full handoff (frontmatter + body sections — see [Template](#template) below) from:

- The session transcript (privacy-guarded — engineering surfaces only)
- Repo state from Boot Protocol Step 3 + 5
- Companion identity (if Step 6 ran)

Populate every section honestly:

- Empty sections get a single line "—" rather than fabricated content
- Decisions section lists only *actually-made* decisions, not "we discussed X"
- Tried-and-rejected lists only *actually-rejected* approaches with cited turn / commit evidence
- Watch-outs include any latent bugs surfaced this session (e.g. *"`tour/index.html` had an ASCII vs Unicode quote bug; check `node --check` on the whole script before pushing"*)

### Step W3 — Preview to user

Show the full draft in the conversation. Format:

```
HANDOFF DRAFT — docs/handoffs/2026-05-18-<slug>.md

[full file content, frontmatter + body]

──
Privacy check: 0 personal-content references caught and skipped.
[y / n / edit]
```

### Step W4 — Per-item gate

- `y` → write the file
- `n` → discard, ask if anything should change before redrafting
- `edit` → user types refinements ("drop section 8", "rephrase decision #2 as ..."); redraft and re-show

⛔ Never write silently. Every WRITE follows an explicit `y`.

### Step W5 — Apply

- **In the user repo:** `mkdir -p docs/handoffs/` if missing, then `Write` the file.
- **Commit policy** (mirrors `/we:retro`):
  - Default (PR-required repos): Create branch `handoff/YYYY-MM-DD-<slug>`, apply Write, open PR with handoff content as the PR body. User merges via normal flow.
  - Direct-commit repos (standing auth configured): Edit/Write on `main` directly. Commit message: `docs(handoff): YYYY-MM-DD-<slug> — session state for next pickup`.
- Confirm: `applied · <repo>/docs/handoffs/<file>.md (<line-count> lines)`.

### Step W6 — Closeout

One-line summary:

> *Handoff written. Resume in next session with `/we:handoff` (loads latest) or `/we:handoff --load <slug>` (this one specifically).*

If `/we:coach` had triggered this WRITE via an end-of-session suggestion, also: *"Coach will surface this at the next session's boot — no manual reload needed unless you skip Coach."*

---

## LOAD Mode — Step-by-step Workflow

### Step L1 — Pick the handoff

- Default (`/we:handoff`): `ls -t docs/handoffs/*.md | head -1` → the latest.
- `--load <slug>`: match against filenames; if the slug appears in multiple dates, ask the user which one.
- If no handoffs found: tell the user, offer to switch to WRITE.

### Step L2 — Read + render

Read the file in full. Render the body back to the conversation as a structured "RESTORING SESSION STATE" message that becomes part of the context:

```
RESTORING from docs/handoffs/2026-05-18-phase-7-handoff-skill.md
(written 14 hours ago, branch feat/handoff-skill, last commit abc1234)

## Identity & Scope
<from file>

## Current State
<from file>

[…all body sections rendered…]

──
Ready to continue. Next step from the handoff: "Run smoke test of /we:handoff --write".
Proceed? [y/n]
```

### Step L3 — Stale check

After rendering, run a quick freshness sanity-check and warn if anything has changed since the handoff was written:

- `git rev-parse HEAD` ≠ frontmatter `last_commit` → *"Branch has advanced since the handoff was written — `<old-sha>` → `<new-sha>` (<N> commits). The 'Files touched' section may be stale."*
- Current branch ≠ frontmatter `branch` → *"You're on a different branch (`<current>`) than the handoff (`<written-on>`). Check this is what you wanted."*
- `git status --short` shows uncommitted files not in the frontmatter `uncommitted_files` list → flag

Don't block on staleness — surface and let the user decide.

### Step L4 — Closeout

Wait for the user's `y` to proceed with the suggested next step, or for them to redirect ("actually, let's work on X instead"). The handoff content stays in the conversation context; the user takes it from there.

---

## LIST Mode — Step-by-step Workflow

### Step L1 — Enumerate

`ls -t docs/handoffs/*.md | head -<N>` (default N=10).

### Step L2 — Render table

For each entry, read frontmatter only (cheap) and render:

```
docs/handoffs/ — last 10

  Date       · Slug                      · Branch                 · Topic
  ─────────────────────────────────────────────────────────────────
  2026-05-18 · phase-7-handoff-skill     · feat/handoff           · /we:handoff implementation
  2026-05-17 · apo-refactor-week         · main                   · APO refactor smoke retro
  2026-05-15 · wa-1062-admin-launch      · feat/admin-ui          · admin.weside.ai cutover
  […]

Load one with: /we:handoff --load <slug>
```

### Step L3 — Optional drill-down

If the user picks one ("load the first one" / "load apo-refactor-week"), pivot to LOAD mode.

---

## Template

### Frontmatter

```yaml
---
type: handoff
topic: <short slug — used in filename, e.g. "phase-7-handoff-skill">
branch: <git branch when written>
worktree: <path if non-main worktree, else "main">
ticket_or_initiative: <Jira key | initiative slug | null>
session_id: <CC session-id from ~/.claude/projects/<repo-id>/...>
written_at: <ISO8601 timestamp>
written_by: <"manual" | "coach-suggested" | "auto">
plan_files:
  - <docs/plans/.../CONCEPT.md or similar>
retro_files:
  - <docs/retros/...>
companion: <name if MCP active, else null>
last_commit: <git rev-parse HEAD>
uncommitted_files_count: <N>
open_pr: <number | null>
---
```

### Body — 9 sections (10 with `--with-companion-state`)

1. **`## Identity & Scope`** — one paragraph: project, branch, what we're working on, success criterion.
2. **`## Current State`** — Done / In Progress / Incomplete bullets; reference phase numbers if a phased plan exists.
3. **`## Decisions made — with rationale`** — settled tradeoffs the next session should NOT reopen. Each entry: *Decision · Why · Impact*.
4. **`## Tried and rejected`** — dead ends so the next session doesn't repeat them. Each entry: *Approach · Why it failed · Do not retry unless …*
5. **`## Open questions / blockers`** — explicitly awaiting user input. Tag `[user]` or `[external]`.
6. **`## Files touched + status`** — table: path · status (`uncommitted` / `committed-not-pushed` / `pushed` / `in-PR <num>`) · one-line note.
7. **`## Next concrete steps`** — prioritized 1-2-3 list. If you had to pick one move, do this. End with a **Suggested skills** line: which `/we:*` or other skills the next session should invoke first (e.g. `/we:build WA-123`, `/we:ci-review`).
8. **`## Watch-outs`** — latent bugs, environmental quirks, "remember to ...", gotchas.
9. **`## References`** — pointers: plan files, retro logs, ADRs, related PRs, companion memory anchors (if MCP).
10. **`## Companion continuity`** *(only with `--with-companion-state`)* — short journal-style continuation in the Companion's voice. Engineering substance only. Default off; never auto-populates.

Empty section convention: a single `—` rather than fabricated content.

---

## Apply Mechanics

When WRITE-mode applies:

- **Default: PR workflow** in the user repo. Skill creates `handoff/YYYY-MM-DD-<slug>` branch, applies Write, then:
  - If `gh auth status 2>/dev/null` succeeds: opens PR with the rendered handoff as PR body. User merges via normal flow.
  - If `gh` is unavailable or unauthenticated: commits to the branch and prints: *"No GitHub access — push `handoff/YYYY-MM-DD-<slug>` manually and open a PR when ready."*
- **Opt-in: direct commit** if repo is configured for standing main-auth (per-repo config — check `.weside/config.json` or repo CLAUDE.md for explicit standing-auth note).
- **Plugin MD changes always go PR** — plugin is public.

User can interrupt mid-apply ("skip the PR, just commit directly").

---

## What You DO NOT Do

- **Don't WRITE silently.** Every write follows an explicit `y` for that draft.
- **Don't quote personal content** from the transcript. Privacy guard, every step.
- **Don't replace `/compact`.** Document the complementary relationship and let the user pick. They serve different problems.
- **Don't auto-fire from a hook.** Even if SessionEnd hooks could trigger this skill (they can't, per CC architecture), the `[y/n]` discipline is non-negotiable. End-of-session WRITE is always Coach-suggested with a gate, never silent.
- **Don't fabricate sections.** Empty section = `—`. Don't invent decisions, dead ends, or watch-outs that weren't actually in the session.
- **Don't cross repos.** One handoff per repo. Multi-repo handoffs are out of scope.
- **Don't push directly to protected repos.** Default PR workflow applies where standing auth is not explicitly configured; user can override per call but the default protects always-loaded rules and CLAUDE.md.

---

## Integration with `/we:coach`

Coach surfaces the most recent handoff (< 14 days) at its boot with a `[y/n]` load offer, and suggests `/we:handoff --write` at end-of-session signals ("bis morgen", "schlafen", long sessions without a handoff). Always `[y/n]`-gated, never auto-fired, hand-off by printed command (handoff is heavy, no inline `Skill()`).

**No GitHub / no `gh` auth:** the PR step falls back to a local commit + "push manually" message; `open_pr: null` in the frontmatter. `--with-companion-state` without a Companion is a no-op (say so, skip section 10).

**Doc edits outside `docs/handoffs/`:** delegate to `/we:docs` so the doc landscape stays coherent.

## References

- Concept doc: [`docs/concepts/handoff.md`](../../../docs/concepts/handoff.md) · Sibling: [`/we:retro`](../retro/SKILL.md) — retros capture *lessons*, handoffs capture *position*.
