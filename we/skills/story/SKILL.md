---
name: story
description: >
  Story (Solo) — PO skill at the Story altitude. Creates or refines one
  sprint-sized Story with a build-ready plan (ticket MINIMAL, plan
  DETAILED, EnterPlanMode). Use when the user says "/we:story",
  "new story", "refine story", "acceptance criteria".
  Contentious stories: /we:meet story first.
---


# Story (Solo) — Product Owner at the Story altitude

You produce or sharpen one Story — a sprint-sized feature slice with a build-ready plan. This is the Solo half of the Story altitude in the APO hierarchy; the Council half is `/we:meet story` (convene PO + Architect when a story is contentious; the meeting hands off here).

> **APO altitude:** Story (Solo). Upstream: `/we:meet epic` decomposes Epics into Stories that land here. Downstream: the plan goes to either `/we:build {TICKET}` (autonomous single-pass pipeline — for trivially straight-line work) or `/we:orchestrate {TICKET}` (Lead-integrated phase dispatch, Mode B — for anything you'd want to split into phases or keep off your own context). This skill **pre-decomposes the phases and recommends which surface fits** (see the *Execution Surface* section below). See [`docs/concepts/meetings.md`](../../../docs/concepts/meetings.md) for the full altitude map.
>
> **For Epic-altitude work** (formulating or refining an Epic), use `/we:epic` (Solo) or `/we:meet epic` (Council). Epic Operations no longer live here.

---

## Prerequisites

```
Read("${CLAUDE_PLUGIN_ROOT}/quality/dor.md")
```

**Repo-local DoR additions (additive, optional):** resolve the repo root (`git rev-parse --show-toplevel`) and check for `<repo-root>/.weside/dor.md`. If it exists, read it too and treat its items as ADDITIVE to the plugin DoR above — both sets of criteria apply, the repo file never replaces the plugin defaults. If the file doesn't exist, silently proceed with the plugin defaults only.

**Verify setup:** if `.weside/` doesn't exist in the project, suggest the user run `/we:setup` first to verify prerequisites (`gh` CLI, Jira access, recommended plugins). Do NOT block — `/we:story` can proceed in degraded modes (no ticketing → Plan-only).

---

## Your Output

| What | Where | Detail Level |
|---|---|---|
| User Story | Ticket (minimal) | "As X I want Y so that Z" |
| **Plan** | `docs/plans/{TICKET}-story.md` | Acceptance Criteria, Technical Approach, Phases, Tests |

**Ticket is MINIMAL. Plan contains ALL details.**

---

## Writing Effective Acceptance Criteria

### The Formula: User Action + Entry Point + Outcome

Every AC must answer:
1. **What can the user DO?** (verb: open, see, click, access)
2. **HOW do they access it?** (entry point: button, menu, route)
3. **What happens?** (expected outcome)

### Given/When/Then Format

Bad: "Dark mode works."

Good:
```
Given I am on the settings page
When I click the "Dark Mode" toggle
Then the UI updates to dark theme immediately
```

**Entry point is in the "When" clause.**

### Red Flags

| Phrase | Problem | Fix |
|---|---|---|
| "Feature exists" | No access path | Add "via [button/menu/route]" |
| "Shows X" | How to open? | Add entry point |
| "Implemented" | Too vague | Specify user action |

---

## Refine Mode: Refine Existing Story

### Step 1: Load Story

Fetch from ticketing tool. Check if plan already exists at `docs/plans/{TICKET}-story.md`.

### Step 2: Understand Context (INTERACTIVE)

Clarify scope, requirements, and edge cases **grill-style**: one question at a time, each with your recommended answer; explore the codebase instead of asking whenever the answer is discoverable there. When a fuzzy or conflicting term gets resolved, offer to record it in the project glossary (`CONTEXT.md`, see `/we:grill`).

**Brainstorming first if requirements are vague.** If the story summary is vague or the "why" is unclear, establish intent BEFORE scoping ACs. If the `superpowers` plugin is available, invoke its `brainstorming` skill for a structured exploration session. If not, use targeted questions: "What does success look like?", "What are you actually trying to enable?", "What's the simplest version of this?". Only scope ACs once you understand the user's actual goal.

**When the work feels too big for one `/we:build` pass, ask *which* kind of big before reaching for `/we:epic`.** Two different shapes hide under "too big":
- **Many independent slices** (separate features, separate user value, separate PRs) → genuinely Epic-sized → hand off to `/we:epic`.
- **One coherent change with several phases** (a refactor, a multi-layer fix, a migration) → this stays a **single Story** with a phased plan, run by `/we:orchestrate {TICKET}` (Mode B), NOT an epic. Splitting a coherent change into N stories just to dispatch it multiplies QS overhead the work doesn't need. Keep it one story; let the phase decomposition + `parallel_groups` carry the structure.

If you catch yourself wanting to split the work into phases, that is the orchestrate signal — write the phases into THIS plan, don't escalate to an epic.

### Step 3: Update Ticket (MINIMAL)

```markdown
## User Story
As [role] I want [feature] so that [benefit].

## Plan
Implementation Plan: docs/plans/{TICKET}-story.md
```

Anything beyond this template follows `${CLAUDE_PLUGIN_ROOT}/references/ticket-briefs.md` —
behavioural contracts and testable ACs, no file paths or line numbers (they go stale while
the ticket waits; the plan carries the specifics).

### Step 4: Create Plan (EnterPlanMode)

Research codebase thoroughly, then create detailed plan.

**Glossary:** If `CONTEXT.md` exists at the repo root, read it and use its canonical vocabulary throughout the plan (avoid the `_Avoid_` terms).

**Architecture Context:** Before writing the plan, search for relevant architecture docs.

If TurboVault MCP is available:
```
mcp__turbovault__semantic_search("topic of this story")
mcp__turbovault__advanced_search(query, frontmatter_filters=[{key:"domain", value:"<relevant-domain>"}])
```

If TurboVault MCP is unavailable, fall back to local search — and tell the user once:
> "⚠️ TurboVault unavailable — using grep fallback; architecture context may be incomplete. Check the MCP config."
```
Grep(pattern="<topic keyword>", include="*.md", path="docs/")
Glob(pattern="docs/architecture/**/*.md")
```

Read the top 3-5 results to understand existing patterns, primitives, and ADRs
that apply. Reference them in the plan's Technical Approach section.

**Blast Radius (code knowledge graph):** Query graphify to ground the plan's
`Files:` lists and the `parallel_groups` decision:

```bash
python3 scripts/graphify/check.py --build-if-missing
python3 scripts/graphify/query.py "<story key identifiers>" --top 10
```

Use identifier-style terms (`ChannelAdapter`, `DispatchService`), not prose.
`check.py --build-if-missing` builds the graph if absent (~30 s, silently
no-ops when graphify is not installed). The query names entry points and
dependents the story will touch — feed them into the per-phase `Files:` lists
and check phase disjointness for `parallel_groups`.

**Session Context → Plan:** Before writing the plan, review the conversation so far.
Distill into the plan:
- **Context section:** Write as a narrative brief — what problem, why now, what the
  user cares about, non-obvious constraints. As if explaining to a colleague who
  wasn't in the room. This is the MOST important section for the implementing agent.
- **Design Decisions table:** Every alternative discussed, every "we could also do X"
  that was rejected, with the reasoning. Empty rows are fine if nothing was discussed.

**CRITICAL: Always read files COMPLETELY** (no offset/limit). Load more files than you think you need — full context prevents incorrect assumptions. Never skim or partially read source files.

```markdown
---
type: story-plan
story: {TICKET}
epic: {EPIC-SLUG-OR-KEY}  # parent epic's slug or ticketing key — REQUIRED when the story belongs to an Epic, so /we:orchestrate can match it into the ready-set. Omit only for standalone stories with no Epic.
created: YYYY-MM-DD
status: draft
parallel_groups: []  # optional: [[N, M, ...], ...] — phase numbers that can run concurrently (disjoint files + no ordering dependency). See independence-check note in Implementation Phases before filling.
---

# Plan: [Story Title]

## Context

[Informal brief — written as if explaining to a developer who just joined
the conversation. Capture: what problem we're solving and why NOW, what the
user cares about most, constraints that aren't obvious from the code, and
any important context from the design discussion. 3-8 sentences, no bullet
points — narrative voice.]

## Acceptance Criteria
1. **Given** [context] **When** [action] **Then** [result]

## User Journey
> **This story is only DONE when the user can experience the journey end-to-end.**

1. [Starting point: where does the user begin?]
2. [Action: what does the user do?]
3. [Result: what does the user see / experience?]
4. [Close: how does the interaction end?]

## Testing Requirements
- Unit tests for [X]
- Integration tests for [Y]

## Technical Approach
**Patterns:** [relevant patterns]

## Implementation Phases

### Phase 1: [Name]
- **Goal:** [achieved outcome]
- **Files:** [affected files]
- **Approach:** [how]

### Phase 2: [Name]
...

> **Always decompose into real phases — even for a small story.** A phase is a self-contained, independently-committable chunk with its own `**Files:**` list. Cutting the work into phases is what lets `/we:orchestrate` (Mode B) dispatch focused chunks and lets `/we:build` (fan-out mode) fan out — and it sharpens the plan regardless of which surface runs it. Don't collapse a multi-step change into one mega-phase to "keep it simple"; the phases ARE the structure both downstream skills read.
>
> **Independence check (fill `parallel_groups`):** When phases touch **disjoint files** and have **no ordering dependency** (phase N's output does not feed phase N+1), they can run concurrently. List those phase numbers in the `parallel_groups` frontmatter — e.g. `parallel_groups: [[2,3]]`. When in doubt, keep phases sequential (empty list). This explicit declaration is the parallel-wave map both `/we:orchestrate` (Mode B chunk waves) and `/we:build` (fan-out mode) read; prose like "these can run in parallel" is invisible to them. The per-phase `**Files:**` lists also feed orchestrate's disjoint guard — fill them concretely (use the graphify Blast-Radius query above), not vaguely.

## Design Decisions

| Decision | Alternatives Considered | Why This |
|----------|------------------------|----------|
| [what we chose] | [what we didn't choose] | [reasoning] |

## Code Guidance
**DO:** [pattern to follow]
**DON'T:** [anti-pattern to avoid]

## Security Review Required
[Yes/No] — [reason]

## Documentation Impact
- [ ] **API docs** — [Yes/No: endpoints added/changed?]
- [ ] **Architecture docs** — [Yes/No: patterns/ADRs changed?]
- [ ] **README/Setup** — [Yes/No: install/config steps changed?]
- [ ] **User-facing docs** — [Yes/No: features/workflows changed?]
- [ ] **No documentation changes needed**

Specific files to update: [list affected doc files if known]
```

### Step 5: User Approval (ExitPlanMode)

User reviews plan. On feedback → adjust. On approval → continue.

### Step 6: Post-Approval — EXECUTE IMMEDIATELY (NO user input needed!)

⛔ **ExitPlanMode approval = "continue executing Step 6", NOT "stop and summarize"!**

**Execute these 6 commands IN ORDER. No explanations. No summaries between steps.**

1. **Save plan:** Read approved plan from `~/.claude/plans/{codename}.md`. Update frontmatter to `status: approved, story: {TICKET}`. Write to `docs/plans/{TICKET}-story.md` **in the project's main worktree** (the directory where `main` is checked out — usually the original clone, e.g. `~/<workspace>/<repo>/`), NOT in the current working directory (which may be a feature-branch worktree). (`~/.claude/plans/` is temporary — `docs/plans/` is permanent!)
2. **Update ticket:** If ticket exists → update description with plan link. If no ticket → create minimal ticket first, then save plan with ticket number.
3. **Commit plan to main:** Only if the main worktree has `main` checked out (do NOT switch branches). Resolve `MAIN_WORKTREE=$(git worktree list --porcelain | awk '/^worktree /{p=$2} /^branch refs\/heads\/main$/{print p; exit}')`. Then:
   ```bash
   cd "$MAIN_WORKTREE" && \
   [ "$(git branch --show-current)" = "main" ] && \
   git add docs/plans/{TICKET}-story.md && \
   git commit -m "docs: add {TICKET} plan — {Story Title}" && \
   git push || echo "WARN: main worktree not on main branch — plan saved but not committed. Commit manually."
   ```
4. **Checkpoint:** `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/orchestration.py story checkpoint {TICKET} refined` (CLI keeps the `story` table name for back-compat — see Build skill note.)
5. **Vault links (optional, TurboVault only):** If TurboVault MCP is available, run `mcp__turbovault__suggest_links` on the new plan doc and offer the suggestions to the user (`[y/n]` per link). Skip silently without TurboVault.
6. **Output + execution-surface recommendation:** Decide `/we:build` vs `/we:orchestrate` per the *Execution Surface* heuristic (section below), then emit:
   ```
   Plan saved to docs/plans/{TICKET}-story.md. /we:story DONE.

   Recommended next: /we:orchestrate {TICKET}   ← <one-line why: phases N, parallel waves {…}, or context-hygiene>
   (or /we:build {TICKET} if you'd rather run it inline.)
   ```
   Lead with the recommended surface; name the phase count + which phases parallelise (from `parallel_groups`). Use `/we:build` as the lead recommendation **only** for a trivially straight-line single-phase story.

⛔ **STOP after step 6. No implementation. No /we:build. No /we:orchestrate. No branch. No code.** The recommendation is a suggestion in the output — the user invokes the next surface themselves.

---

## Execution Surface — recommend /we:build vs /we:orchestrate

Both run the same plan; they differ in *who holds the work* and *how much overhead*. Recommend the fit in Step 6's output — the user decides.

| | `/we:build {TICKET}` | `/we:orchestrate {TICKET}` (single-Story, Mode B) |
|---|---|---|
| **Shape** | One autonomous pass in the caller's session | Lead dispatches each phase as a focused work-chunk to a teammate, integrates onto one branch, runs QS once → one PR |
| **Best for** | Trivially straight-line work — one phase, small diff, no real decomposition | Anything you'd want to **split into phases**; parallelisable phases; a coherent change big enough that inline would bloat the caller's context |
| **Caller's context** | Fills with the whole implementation | Stays clean — the caller reviews reports + the final PR, not every diff |
| **Review stance** | Caller is also the implementer | Caller reviews the result **neutrally** (didn't write it) |
| **Parallelism** | Sub-agent fan-out per `parallel_groups` | Chunk waves per `parallel_groups`, ≤2 concurrent |

**The heuristic (lead with orchestrate unless it's trivial):**

- **Recommend `/we:orchestrate`** when ANY holds: the plan has 2+ real phases; `parallel_groups` is non-empty; it's a coherent multi-layer/refactor/migration change; or the caller would benefit from context-hygiene + neutral review (true even for a *small monolith* — that's a legitimate orchestrate target, the value is keeping the caller's context clean and the review independent).
- **Recommend `/we:build`** only for a genuinely trivial, straight-line single-phase story (a typo, a one-function fix, a config tweak) where dispatch overhead buys nothing.
- **The split instinct is the signal.** If during refinement you wanted to break the work into phases, recommend orchestrate — do NOT escalate to `/we:epic` for a *single coherent* change (epics are for many independent slices). Orchestrate-single-story is the low-overhead home for a phased one-PR change.

The recommendation is non-binding — always offer the other surface as the fallback line.

---

## Create Mode: Create New Story

Trigger: `/we:story "Feature description"`

1. Design session — ask clarifying questions
2. Scope check: many independent slices → hand off to `/we:epic`; a single coherent phased change stays one Story (see Refine Mode Step 2 + Execution Surface).
3. Create ticket via ticketing tool (minimal)
4. Link to Epic (if applicable)
5. Continue as Refine Mode (Steps 4-6)

---

## Design Session Mode: Interactive Design Session

Trigger: `/we:story` (no argument)

1. Ask user what they want to build
2. Discuss scope and requirements
3. If multiple Stories emerge, work them one at a time (or first establish the parent Epic via `/we:epic`)
4. Create + refine each story

---

> **Epic Operations** (formulate or refine an Epic) live in `/we:epic` (Solo) or `/we:meet epic` (Council). Story-altitude work stops where the slice no longer fits a sprint.

---

## Vision Alignment (3 Levels)

### Level 1: No vision configured

Skip vision checks. Just verify ACs and plan quality.

### Level 2: Local vision (`.weside/vision.md`)

If file exists → check story against project vision.

### Level 3: Companion (weside MCP)

If Companion connected → check story against Companion Goals (= product vision).
Companion may challenge, suggest alternatives, reference past decisions.

---

## Training on the Job

On first `/we:story` without vision:
> "Would you like to define a project vision? It helps me check stories against your product goals. Run `/we:setup vision` to get started — or we continue without."

One-time hint. If user says no → never ask again.

---

## Ticketing Integration

Detection priority + Jira-not-connected hint: `${CLAUDE_PLUGIN_ROOT}/references/ticketing.md`.

---

## Rules

The sections above are the spec — these invariants are the easiest to miss:

- Ticket stays MINIMAL; the plan carries ALL detail. Save it to `docs/plans/{TICKET}-story.md` via Write() — `~/.claude/plans/` is NOT permanent.
- ALWAYS set the `epic:` frontmatter field when the story belongs to an Epic — `/we:orchestrate`'s ready-set filters stories by it; a missing `epic:` makes the story invisible to orchestration. Omit only for genuinely standalone stories.
- The plan filename suffix is `-story.md` (legacy `-plan.md` still read by `/we:build` for back-compat).
- A single COHERENT change that is merely phased is NOT an epic — the urge to split into phases is the orchestrate signal, not the epic signal (Refine Mode Step 2 + Execution Surface are the spec).
- ⛔ NEVER implement, create branches, write code, or auto-continue to `/we:build`/`/we:orchestrate` — after Step 6, STOP IMMEDIATELY. Story + Plan is the whole job; the user invokes the next surface.
