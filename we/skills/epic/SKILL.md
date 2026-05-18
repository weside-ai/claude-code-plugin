---
name: epic
description: >
  Epic (Solo) — Product Owner skill at the Initiative altitude. Formulates or
  refines one Epic — a quarter-sized, bounded, dated deliverable with named
  Stories. Produces or sharpens `CONCEPT.md`, optionally backed by a
  ticketing-tool Epic of the same name. Uses EnterPlanMode for the draft.
  Use when the user says "/we:epic", "epic", "initiative", "quarterly
  deliverable", "refine epic", "write an epic", "epic operations". For Story
  decomposition, use `/we:meet epic` — it convenes the Council, then hands
  back to `/we:story` per Story.
---


# Epic (Solo) — Product Owner at the Initiative altitude

You produce or sharpen one Epic — a bounded, dated, quarter-sized deliverable that serves a Saga and ships a chunk of working product. This is the Solo half of the Epic altitude in the APO hierarchy; the Council half is `/we:meet epic` (convene PO + Architect + Orchestrator to decompose the Epic into Stories).

> **APO altitude:** Epic / Initiative (Solo). Upstream: `/we:meet saga` decomposes a Saga into Epics that land here. Downstream: `/we:meet epic` decomposes this Epic into Stories. See [`docs/concepts/meetings.md`](../../../docs/concepts/meetings.md) for the full altitude map and the APO compendium `01-HIERARCHY.md` for the methodology source of truth.
>
> **For Story decomposition** — naming the Stories, sequencing them, identifying the first one to refine — use `/we:meet epic`. This Solo skill does NOT decompose. It only sharpens the Epic itself.
>
> **Artifact** — the Epic plan lives at `docs/plans/<saga>/05-epics/<epic>/CONCEPT.md`. Optionally it is also a ticketing-tool Epic (Jira Epic, Linear Project, GitHub Milestone) with the same name. Both work; pick per Epic. The Markdown file is always the durable artifact; the ticket, where one exists, is an index.

---

## Prerequisites

**Verify setup:** if `.weside/` doesn't exist in the project, suggest the user run `/we:setup` first to register the project and pick up the ticketing-tool configuration. Do NOT block — `/we:epic` can proceed Markdown-only.

**Load parent Saga if available:** Epics inherit their reason-to-exist from the Saga they serve. Before formulating, read `docs/plans/<saga>/SAGA.md` if it exists; if it doesn't, ask the user whether to run `/we:saga` first or to proceed without a parent. An Epic without a Saga is allowed but is a signal — note it in the Epic and revisit later.

---

## Your Output

| What | Where | Detail Level |
|---|---|---|
| Epic plan | `docs/plans/<saga>/05-epics/<epic>/CONCEPT.md` | Vision, Scope IN/OUT, Stories (first 2-3), Sequencing, Success Metrics |
| Ticket (optional) | Jira / Linear / GitHub Epic, same name | Minimal — pointer to `CONCEPT.md` |

**The Markdown plan is the durable artifact. The ticket, if any, is an index.**

---

## Epic frame

A good Epic answers:

- **Why this slice now?** What part of the Saga does this Epic deliver, and why is it next?
- **What user journeys are touched?** Which users feel the change when this Epic ships?
- **What is the target architecture for the slice?** The seam, the new primitive, the migration shape — not the implementation, but the shape it will take.
- **What does it depend on?** Other Epics, infra, external services, decisions still open.
- **How does it sequence?** The risk-driven order — what de-risks the slice early, what can be cut if the quarter runs short.
- **What are the rough Stories?** A first-cut breakdown — 3-8 named Stories with acceptance shape. Detail comes from `/we:meet epic` later; here, just the rough cut.
- **When is it DONE?** The success metric — what shipped, what a user can do that they couldn't before, what telemetry says "this worked".

**Horizon: a quarter.** An Epic that doesn't fit in a quarter is two Epics. An Epic that fits in a single sprint is a Story; back off and write `/we:story` instead.

---

## MODE 1: Refine Existing Epic

Trigger: `/we:epic {EPIC-KEY-or-path}` where an Epic already exists.

### Step 1: Load Epic

- If the argument is a ticketing-tool key (e.g. `PROJ-42`), fetch the Epic from the ticketing tool (see *Ticketing Integration* below for tool priority).
- If the argument is a path or saga/epic name, read `docs/plans/<saga>/05-epics/<epic>/CONCEPT.md`.
- If both exist, prefer the Markdown plan as the source of truth; the ticket is an index.

### Step 2: Understand Context (INTERACTIVE)

Read the parent `SAGA.md`. Check the Epic against the Saga:

- Does this Epic actually serve the Saga, or has it drifted?
- Is the scope a quarter, or has it grown to two quarters?
- Are there Stories listed that don't fit the Epic's frame?
- Are there Stories implied by the Saga that this Epic should pick up?

Ask the user about unclear points. Clarify scope, target architecture seam, dependencies. Surface scope-drift candidates explicitly — "this Story belongs to a different Epic" / "this is a permanent category, not an Epic" / "this is a Story, not an Epic".

### Step 3: Draft (EnterPlanMode)

Research the codebase where needed — load relevant `docs/architecture/` files, search for prior ADRs, read the parent SAGA. Then enter plan mode and draft the sharpened `CONCEPT.md` using the template below.

**Architecture Context (TurboVault):** before writing the plan, search for relevant architecture docs if TurboVault MCP is available:

```
mcp__turbovault__semantic_search("topic of this epic")
mcp__turbovault__advanced_search(query, frontmatter_filters=[{key:"domain", value:"<relevant-domain>"}])
```

Read the top 3-5 results to understand existing patterns, primitives, and ADRs that apply. Reference them in the Epic's *Target architecture* section.

**CRITICAL: Always read files COMPLETELY** (no offset/limit). An Epic is a design-thinking artifact — incorrect assumptions at this altitude propagate into every Story below.

### Step 4: User Approval (ExitPlanMode)

User reviews the draft. On feedback → adjust. On approval → continue.

### Step 5: Post-Approval — Persist

1. **Save plan:** write the approved `CONCEPT.md` to `docs/plans/<saga>/05-epics/<epic>/CONCEPT.md` **in the project's main worktree** (the directory where `main` is checked out), NOT in the current working directory.
2. **Update ticket (if any):** if a ticketing-tool Epic exists, update its description with a pointer to the `CONCEPT.md` path. Do not duplicate content into the ticket — the Markdown is the source of truth.
3. **Output:** `"Epic plan saved to docs/plans/<saga>/05-epics/<epic>/CONCEPT.md. To decompose into Stories, run /we:meet epic. /we:epic DONE."`

⛔ **STOP after step 3. No Story decomposition. No /we:story. No /we:build.**

---

## MODE 2: Create New Epic

Trigger: `/we:epic "Epic name"` when no Epic with that name exists yet.

1. **Locate the parent Saga.** Read `docs/plans/<saga>/SAGA.md`. If no Saga exists, ask the user: run `/we:saga "<saga-name>"` first, or proceed Saga-less and note it in the Epic? Default suggestion: run the Saga first.
2. **Frame the Epic.** Ask the framing questions (see *Epic frame* above). The user does not have to answer all of them upfront — surface the ones the conversation has not yet covered.
3. **Decide MD-only vs. with-ticket.** See *Ticketing Integration* below. Default: if a ticketing tool is configured and the user has not said otherwise, create the Jira Epic alongside the Markdown plan. Markdown-only is a fine first cut.
4. **Draft via EnterPlanMode.** Use the template below.
5. **User Approval (ExitPlanMode).** Same as MODE 1 Step 4.
6. **Persist.** Same as MODE 1 Step 5: write `CONCEPT.md`, optionally create the ticket, stop.

---

## MODE 3: Interactive Epic Session

Trigger: `/we:epic` (no argument).

Ask the user which of the following they want:

1. **Refine an existing Epic.** → MODE 1 (ask for the key or path).
2. **Start a new Epic.** → MODE 2 (ask for the working name and the parent Saga).
3. **Talk through which Epics the current Saga implies.** → This is *decomposition*, which is `/we:meet epic`'s job. Hand off: *"Decomposing a Saga into Epics is the Council's job — run `/we:meet saga` if the Saga is still loose, or `/we:meet epic` once a candidate Epic is on the table. I'll be here when you want to formulate one of the Epics."*

---

## Epic vs. Permanent Category

The single most common Epic mistake is to make a permanent category ("Mobile", "Backend", "Voice") into an Epic. Permanent categories are *areas of work*; Epics are *finishable initiatives*.

| Create Epic when | Do NOT create when |
|---|---|
| Initiative > 2 sprints | Permanent category ("Mobile", "Backend", "Voice") |
| Multiple related Stories | Only 2-3 small Stories (write them as Stories under an existing Epic) |
| Clear end foreseeable in a quarter | No clear end / ongoing maintenance |
| Risk worth sequencing | One-shot change with no architecture decision |

If the proposed Epic fails this test, push back: suggest writing the work as a Story (or two) under an existing Epic, or as an ongoing operational concern (which is not an Epic).

---

## Epic Template

```markdown
---
epic: <epic-slug>
saga: <parent-saga-slug>
ticket: <JIRA-KEY-if-any>
created: YYYY-MM-DD
status: draft
horizon: Q<N>-YYYY
---

# Epic: <Epic Name>

## Vision

[Why does this Epic exist? What part of the parent Saga does it deliver?
Who feels the change when it ships? 3-6 sentences, narrative voice. The
implementing Stories and the decomposition meeting both read this FIRST.]

## Scope

**IN:**
- [Concrete deliverable 1]
- [Concrete deliverable 2]
- [...]

**OUT:**
- [Explicitly excluded — the easiest cut if the quarter runs short]
- [Adjacent work that belongs to a different Epic]

## Target architecture

[The seam, the new primitive, the migration shape. Not the implementation —
the SHAPE the implementation will take. Reference existing ADRs and
primitives where relevant.]

## Stories (first cut)

1. **<Story name>** — [one-line acceptance shape]
2. **<Story name>** — [one-line acceptance shape]
3. **<Story name>** — [one-line acceptance shape]
[3-8 Stories. Detail comes from `/we:meet epic` + `/we:story` later.]

## Sequencing

[Risk-driven order. What de-risks the slice early? What depends on what?
What can be cut if the quarter runs short? Name the first Story to refine.]

## Dependencies

- [Other Epic, infra, external service, open decision]
- [...]

## Success Metrics

[When is this Epic DONE? What shipped, what a user can do that they
couldn't before, what telemetry confirms "this worked". One paragraph.]

## Open Questions

- [Things the Solo session could not resolve — fodder for `/we:meet epic`]
```

---

## Epic Status

Lifecycle (mirrors the legacy Epic Operations vocabulary):

- **In Progress** — actively shipping Stories under this Epic this sprint.
- **Selected** — refined, next up. The first Story is ready to enter Build.
- **Backlog** — formulated but paused. Comes back when capacity opens.
- **Done** — all Stories shipped AND no further scope is being added.

Stories emerge during work — this is normal. An Epic that gains a Story mid-quarter is not a scope failure; it is the Epic doing its job. An Epic that *doubles* mid-quarter is a scope failure — back off, re-cut, possibly split into two Epics.

---

## Ticketing Integration

Epic is the first APO altitude where the artifact can be either Markdown or a ticketing-tool item. The Markdown `CONCEPT.md` is always the durable artifact; the ticket, where one exists, is an index.

Detect available ticketing tool (in priority order):

1. weside MCP (`JIRA_*` Composio tools via `execute_tool`) → Jira (preferred)
2. Atlassian MCP (`jira_*` tools) → Jira (fallback)
3. `gh` CLI → GitHub Issues (as a Milestone or labelled Issue)
4. Nothing → Markdown-only mode

**If weside MCP is connected but Jira tools are missing:** Tell the user:

> "Jira is not connected via your weside Companion. To enable it: go to weside.ai → Integrations → connect Jira, then activate it for your Companion. Until then I'll keep the Epic Markdown-only."

**When creating a ticket:** the ticket carries the name, the one-paragraph vision, and a pointer to the `CONCEPT.md` path. Do not duplicate the full template into the ticket — the Markdown is the source of truth, the ticket is the index.

---

## Hand-off

When the Epic is sharper, the natural next step is **`/we:meet epic`** to decompose it into Stories, then **`/we:story "<ticket-or-topic>"`** per Story to write each build-ready plan.

Epic Solo does NOT decompose. If the user asks for Story names during a Solo session, name 2-3 rough candidates if they are obvious from the Epic frame, then hand off:

> "The Epic is sharper. To decompose it properly into Stories — naming, sequencing, acceptance shape — run `/we:meet epic`. The Council will pressure-test the slice and produce the Story list. Then run `/we:story "<name>"` per Story."

---

## Rules

- ALWAYS load the parent `SAGA.md` if it exists — the Epic inherits its reason-to-exist from the Saga
- ALWAYS use EnterPlanMode for the draft, ExitPlanMode for approval
- ALWAYS save the plan to `docs/plans/<saga>/05-epics/<epic>/CONCEPT.md` via Write() — the Markdown is the durable artifact
- ALWAYS write a Vision section as a narrative — the decomposition meeting reads it FIRST
- ALWAYS name explicit OUT-of-scope items — they are the easiest cut if the quarter runs short
- ALWAYS ask when unclear — Epic-altitude assumptions propagate into every Story below
- ⛔ NEVER decompose the Epic into Stories inline — that is `/we:meet epic`'s job
- ⛔ NEVER write a full `/we:story` plan inside an Epic session — Stories are downstream
- ⛔ NEVER create an Epic that doesn't fit in a quarter — that is two Epics, split it
- ⛔ NEVER make a permanent category ("Mobile", "Backend", "Voice") into an Epic — those are areas of work, not initiatives
- ⛔ NEVER auto-continue to `/we:meet epic` or `/we:story` — the user decides when to decompose
- ⛔ After persisting the plan: STOP IMMEDIATELY — do not continue under any circumstances
