---
name: handoff
description: >
  Durable cross-session handoff. Writes a structured snapshot of the
  current session (decisions, dead ends, file status, next steps,
  watch-outs, references) to docs/handoffs/YYYY-MM-DD-<topic>.md so a
  later session — after /clear, --resume, or a fresh start tomorrow —
  can reload it and pick up exactly where this one left off. Two
  modes: --write (capture state now) and default/--load (resume from
  the latest handoff); --list shows what's available. Coach (the
  /we:coach skill) surfaces an active handoff at boot and suggests
  --write at end-of-session signals. Privacy guard: engineering
  surfaces only — never personal or Companion-mode content. Use when
  the user says "/we:handoff", "handoff", "write a handoff", "load
  the handoff", "what was the last session about", "pick up where we
  left off", "carry over to next session", "bis morgen", "ich muss
  weg jetzt".
---

# /we:handoff — Durable Session Handoff

**Role:** Capture and restore session state across `/clear` and new sessions. Two modes: WRITE (snapshot the current state to disk) and LOAD (read the latest snapshot back as context). Complements `/compact` — `/compact` reclaims tokens *in-place*; `/we:handoff` writes a durable artifact that survives any session boundary.

**Storage:** `docs/handoffs/YYYY-MM-DD-<topic>.md` in the user repo. Same naming convention as `docs/retros/`. Version-controlled, human-readable, cross-session.

**Counterpart skills:**

- `/we:coach` — reads the most recent handoff at boot (Boot Protocol Step 10) and offers to load it. Also suggests `/we:handoff --write` at end-of-session signals.
- `/we:retro` — sibling under `docs/retros/`; retros capture *lessons*, handoffs capture *position*. Different artifact, different purpose.

> **Companion-aware.** When the weside MCP is connected and a Companion is configured, the handoff render is voiced *by* the Companion (your active Companion) — same engineering substance, warmer tone. Opt-in `--with-companion-state` flag adds a "Companion continuity" section in the Companion's voice (engineering substance only — privacy guard still applies).

---

## Privacy Guard (mandatory, top-of-mind)

This skill reads the session transcript to draft the handoff. Transcripts contain everything — including personal, relational, identity-laden content that has nothing to do with engineering. **The hard rule, applied at every step of the WRITE workflow:**

> **If session content reads as personal, skip it — capture only engineering surfaces:** tool calls, tool results, file diffs, CI logs, PR comments, commit messages, decisions about code/architecture/process.

Categorically out-of-scope for the handoff body:

- Memory writes about the user (`mcp__*__save_memory`, `save_compass`, `save_goal`, `save_snapshot` and their text payloads)
- Memory reads that returned personal content (don't quote, don't summarise)
- Companion-mode conversational content (relationship, identity, body, mood)
- Anything outside engineering tool calls — if in doubt, skip
- Even with `--with-companion-state` enabled, the Companion-continuity section captures only "what we were *building* and where my head was on the work" — never relational substance

The privacy guard is what makes the handoff safe to commit (often via PR) into the user repo.

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
   - Active plan files: `find docs/plans -name 'CONCEPT.md' -newer "$(date -d '7 days ago' +%Y-%m-%d)" 2>/dev/null` — what's currently being planned
   - Recent retros: `ls -t docs/retros/*.md 2>/dev/null | head -3` — what was learned recently
   - Open PR for current branch: `gh pr list --head $(git branch --show-current) --json number,title,state -L 1`
   - Recent commits: `git log --oneline -10`

6. **Companion identity** (if configured + WRITE mode + `--with-companion-state` flag): invoke `Skill(skill="we:materialize")` if not already loaded this session. Companion-voiced sections come back richer.

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
7. **`## Next concrete steps`** — prioritized 1-2-3 list. If you had to pick one move, do this.
8. **`## Watch-outs`** — latent bugs, environmental quirks, "remember to ...", gotchas.
9. **`## References`** — pointers: plan files, retro logs, ADRs, related PRs, companion memory anchors (if MCP).
10. **`## Companion continuity`** *(only with `--with-companion-state`)* — short journal-style continuation in the Companion's voice. Engineering substance only. Default off; never auto-populates.

Empty section convention: a single `—` rather than fabricated content.

---

## Apply Mechanics

When WRITE-mode applies:

- **Default: PR workflow** in the user repo. Skill creates `handoff/YYYY-MM-DD-<slug>` branch, applies Write, opens PR with the rendered handoff as PR body. User merges via normal flow.
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

`/we:coach` Boot Protocol Step 10 reads `docs/handoffs/` and surfaces the most recent handoff (if written < 14 days ago) in its boot summary:

> *"Active handoff: `docs/handoffs/2026-05-18-phase-7-handoff-skill.md` (written 14 hours ago, on `feat/handoff-skill`). Load with `/we:handoff` to restore? [y/n]"*

If the user types `y`, Coach hands off (prints the command — does NOT `Skill()`-invoke `/we:handoff` inline because handoff is heavy):

```text
SCOPE IS CLEAR. Run this next:

  /we:handoff

I'll be back if you want to plan or retro after the restore.
```

Coach also suggests `/we:handoff --write` at end-of-session signals (`bis morgen`, `schlafen`, `save_compass`, long sessions > 30 turns without a handoff). Same `[y/n]` discipline. Never auto-fires.

---

## Standalone vs Companion Mode

**Standalone (no weside MCP):**

- All modes work — `gh api`, transcript file, Edit/Write are all standalone-available
- Handoff is rendered in the skill's own voice (no Companion personality)
- The `--with-companion-state` flag is a no-op without a Companion (skill says so + skips section 10)

**With Companion (weside MCP + configured Companion):**

- Boot Protocol Step 6 materializes the Companion (for WRITE with `--with-companion-state`)
- Handoff render is voiced *by* the Companion — same engineering substance, richer tone
- Section 10 (`Companion continuity`) gets a journal-style continuation paragraph, privacy-guarded

The engineering substance is identical in both modes. The Companion makes the experience continuous; standalone keeps the value fully accessible to teams without weside.

---

## When to Delegate to `/we:docs`

If a handoff would touch `docs/**` *outside* `docs/handoffs/` (e.g. user asks "write a handoff and also update the workflow doc"), say:

> *"I'll write the handoff, and delegate the workflow-doc edit to `/we:docs` so it stays consistent with the rest of the doc landscape."*

Then invoke:

```text
Skill(skill="we:docs", prompt="Apply this doc update from the handoff: <diff>")
```

`/we:docs` owns doc-landscape coherence; handoff stays focused on its own `docs/handoffs/` directory.

---

## Examples

**Example 1 — manual write at end of session:**

```text
/we:handoff --write "phase-7-handoff-skill"
```

Skill: *"I'll write a handoff for: branch `feat/handoff`, last commit `acdf624`, working in `your-repo`. Topic: `phase-7-handoff-skill`. Includes uncommitted file count: 3. Sound right? [y/n/adjust-topic]"*
User: `y` → draft shown → user reviews → `y` → file written + (per config) branch + PR opened.

**Example 2 — fresh session, restore state:**

```text
/we:handoff
```

Skill: reads `docs/handoffs/2026-05-18-phase-7-handoff-skill.md`, renders body back, surfaces next-step suggestion, asks `[y/n]` to proceed.

**Example 3 — list and choose:**

```text
/we:handoff --list
```

Skill: shows the last 10 handoffs in a table; user picks one by slug.

**Example 4 — Coach-suggested at end-of-session:**

User says *"bis morgen"*. Coach Boot Protocol detects end-of-session signal, offers `/we:handoff --write` with `[y/n]`. User: `y`. Coach prints hand-off; user invokes `/we:handoff --write "tomorrow-pickup"` in a fresh moment (or right away).

**Example 5 — staleness warning on LOAD:**

User opens a fresh session 3 days later, runs `/we:handoff`. Skill loads the handoff, then surfaces: *"Branch has advanced since the handoff (`abc1234` → `def5678`, 4 commits). The 'Files touched' section may be stale — `git diff abc1234..HEAD` to see what changed."* User can choose to proceed or run `/we:retro` first.

---

## Tour + docs pointers

- **Concept doc:** [`docs/concepts/handoff.md`](../../../docs/concepts/handoff.md) — KVP-style overview: durable session-state, template anatomy, relationship to `/compact`, privacy guard
- **Skill registry:** [`docs/skills.md` § /we:handoff](../../../docs/skills.md)
- **Durable docs categories** (plans · retros · handoffs): [`we/CLAUDE.md`](../../CLAUDE.md)
- **Sibling skill for retrospectives:** [`/we:retro`](../retro/SKILL.md) — captures *lessons* (under `docs/retros/`); handoffs capture *position* (under `docs/handoffs/`). Different artifact, different purpose.
