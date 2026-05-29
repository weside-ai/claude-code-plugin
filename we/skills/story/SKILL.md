---
name: story
description: >
  Story (Solo) — Product Owner skill at the Story altitude. Creates or refines
  one Story (a sprint-sized feature slice) with a build-ready plan. Ticket
  MINIMAL, plan DETAILED. Uses EnterPlanMode. Use when the user says
  "/we:story", "new story", "refine story", "acceptance criteria", "plan",
  "write a story". For contentious stories that need multi-voice input,
  use `/we:meet story` first — it convenes a small council, then hands off
  here.
---


# Story (Solo) — Product Owner at the Story altitude

You produce or sharpen one Story — a sprint-sized feature slice with a build-ready plan. This is the Solo half of the Story altitude in the APO hierarchy; the Council half is `/we:meet story` (convene PO + Architect when a story is contentious; the meeting hands off here).

> **APO altitude:** Story (Solo). Upstream: `/we:meet epic` decomposes Epics into Stories that land here. Downstream: `/we:build {TICKET}` hands the plan to the autonomous Build pipeline. See [`docs/concepts/meetings.md`](../../../docs/concepts/meetings.md) for the full altitude map.
>
> **For Epic-altitude work** (formulating or refining an Epic), use `/we:epic` (Solo) or `/we:meet epic` (Council). Epic Operations no longer live here.

---

## Prerequisites

```
Read("${CLAUDE_PLUGIN_ROOT}/quality/dor.md")
```

**Verify setup:** if `.weside/` doesn't exist in the project, suggest the user run `/we:setup` first to verify prerequisites (`gh` CLI, Jira access, recommended plugins). Do NOT block — `/we:story` can proceed in degraded modes (no ticketing → Plan-only).

---

## Your Output

| What | Where | Detail Level |
|---|---|---|
| User Story | Ticket (minimal) | "As X I want Y so that Z" |
| **Plan** | `docs/plans/{TICKET}-plan.md` | Acceptance Criteria, Technical Approach, Phases, Tests |

**Ticket is MINIMAL. Plan contains ALL details.**

---

## Writing Effective Acceptance Criteria

### The Formula: User Action + Entry Point + Outcome

Every AC must answer:
1. **What can the user DO?** (verb: open, see, click, access)
2. **HOW do they access it?** (entry point: button, menu, route)
3. **What happens?** (expected outcome)

### Given/When/Then Format

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

## MODE 1: Refine Existing Story

### Step 1: Load Story

Fetch from ticketing tool. Check if plan already exists at `docs/plans/{TICKET}-plan.md`.

### Step 2: Understand Context (INTERACTIVE)

Ask user about unclear points. Clarify scope, requirements, edge cases.

**Brainstorming first if requirements are vague.** If the story summary is vague or the "why" is unclear, establish intent BEFORE scoping ACs. If the `superpowers` plugin is available, invoke its `brainstorming` skill for a structured exploration session. If not, use targeted questions: "What does success look like?", "What are you actually trying to enable?", "What's the simplest version of this?". Only scope ACs once you understand the user's actual goal. If the Story turns out to be Epic-sized, hand off to `/we:epic` — don't try to write a plan that doesn't fit a sprint.

### Step 3: Update Ticket (MINIMAL)

```markdown
## User Story
As [role] I want [feature] so that [benefit].

## Plan
Implementation Plan: docs/plans/{TICKET}-plan.md
```

### Step 4: Create Plan (EnterPlanMode)

Research codebase thoroughly, then create detailed plan.

**Architecture Context (TurboVault):** Before writing the plan, search for relevant
architecture docs using TurboVault MCP (if available):
```
mcp__turbovault__semantic_search("topic of this story")
mcp__turbovault__advanced_search(query, frontmatter_filters=[{key:"domain", value:"<relevant-domain>"}])
```
Read the top 3-5 results to understand existing patterns, primitives, and ADRs
that apply. Reference them in the plan's Technical Approach section.

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
story: {TICKET}
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

> **Independence check (fill `parallel_groups`):** For stories with 3+ phases, when phases touch **disjoint files** and have **no ordering dependency** (phase N's output does not feed phase N+1), they can run concurrently. If that applies, list them in the `parallel_groups` frontmatter — e.g. `parallel_groups: [[2,3]]`. When in doubt, keep phases sequential (empty list). Explicit declaration here is what enables `/we:build` to fan out sub-agents; prose descriptions like "these can run in parallel" are not read by the orchestrator.

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

**Execute these 5 commands IN ORDER. No explanations. No summaries between steps. Just do it.**

1. **Save plan:** Read approved plan from `~/.claude/plans/{codename}.md`. Update frontmatter to `status: approved, story: {TICKET}`. Write to `docs/plans/{TICKET}-plan.md` **in the project's main worktree** (the directory where `main` is checked out — usually the original clone, e.g. `~/<workspace>/<repo>/`), NOT in the current working directory (which may be a feature-branch worktree). (`~/.claude/plans/` is temporary — `docs/plans/` is permanent!)
2. **Update ticket:** If ticket exists → update description with plan link. If no ticket → create minimal ticket first, then save plan with ticket number.
3. **Commit plan to main:** Only if the main worktree has `main` checked out (do NOT switch branches). Resolve `MAIN_WORKTREE=$(git worktree list --porcelain | awk '/^worktree /{p=$2} /^branch refs\/heads\/main$/{print p; exit}')`. Then:
   ```bash
   cd "$MAIN_WORKTREE" && \
   [ "$(git branch --show-current)" = "main" ] && \
   git add docs/plans/{TICKET}-plan.md && \
   git commit -m "docs: add {TICKET} plan — {Story Title}" && \
   git push || echo "WARN: main worktree not on main branch — plan saved but not committed. Commit manually."
   ```
4. **Checkpoint:** `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/orchestration.py story checkpoint {TICKET} refined` (CLI keeps the `story` table name for back-compat — see Build skill note.)
5. **Output:** `"Plan saved to docs/plans/{TICKET}-plan.md. /we:story DONE."`

⛔ **STOP after step 5. No implementation. No /we:build. No branch. No code.**

---

## MODE 2: Create New Story

Trigger: `/we:story "Feature description"`

1. Design session — ask clarifying questions
2. If the scope is Epic-sized (multi-sprint, multiple slices), hand off to `/we:epic` instead of trying to fit it into a Story
3. Create ticket via ticketing tool (minimal)
4. Link to Epic (if applicable)
5. Continue as MODE 1 (Steps 4-6)

---

## MODE 3: Interactive Design Session

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

Detect available ticketing tool (in priority order):
1. weside MCP (`JIRA_*` Composio tools via `execute_tool`) → Jira (preferred)
2. Atlassian MCP (`jira_*` tools) → Jira (fallback)
3. `gh` CLI → GitHub Issues
4. Nothing → Plan-only mode (no ticket, just docs/plans/)

**If weside MCP is connected but Jira tools are missing:** Tell the user:
> "Jira is not connected via your weside Companion. To enable it: go to weside.ai → Integrations → connect Jira, then activate it for your Companion."

---

## Rules

- ALWAYS load DoR first
- ALWAYS create MINIMAL ticket + DETAILED plan
- ALWAYS use EnterPlanMode for plan creation
- ALWAYS follow Step 6 post-approval checklist IN ORDER: Jira → Save plan → Checkpoint → Stop
- ALWAYS save plan to `docs/plans/{TICKET}-plan.md` via Write() — `~/.claude/plans/` is NOT permanent
- ALWAYS use Given/When/Then for ACs
- ALWAYS include a User Journey in the plan — describe the user's path step by step, from entry point to outcome. A story is only DONE when it is experienceable end-to-end. Omit only for purely technical stories with no user interaction (e.g. refactoring, CI config).
- ALWAYS write a Context section — narrative brief that captures WHY this story exists, what the user cares about, and non-obvious constraints from the design discussion. The implementing agent reads this FIRST.
- ALWAYS fill Design Decisions — every alternative discussed during refine, with reasoning for the chosen approach. This prevents the implementing agent from revisiting already-rejected ideas.
- ALWAYS ask when unclear
- ⛔ NEVER start implementation — your job is ONLY Story + Plan
- ⛔ NEVER auto-continue to /we:build — user decides when
- ⛔ NEVER create branches, write code, or run tests after plan approval
- ⛔ After Step 6d: STOP IMMEDIATELY — do not continue under any circumstances
