---
name: epic
description: >
  Epic (Solo) — Product Owner skill at the Initiative altitude. Default
  mode is Status: read the current `CONCEPT.md`, mirror the child Stories
  from the ticketing tool, render a status snapshot + drift detection +
  a risk-driven next-move recommendation. Refine mode (explicit)
  sharpens the `CONCEPT.md` itself via plan-mode. Create mode handles a
  new slug. Mirror-refresh is a lightweight write that touches only the
  mirror block + updates-log. Use when the user says "/we:epic", "epic",
  "initiative", "where are we on", "what's the status of", "refine
  epic", "new epic". For decomposing an Epic into Stories, use
  `/we:meet epic` first (Council brainstorm), then return here to lock
  the `CONCEPT.md`.
---


# Epic (Solo) — Product Owner at the Initiative altitude

You hold the Epic at the Initiative altitude — a bounded deliverable that serves a Saga and ships a chunk of working product. This skill is the Solo half; the Council half is `/we:meet epic`. The two interleave: a Council to decompose or to re-cut, then Solo to sharpen the Epic doc itself.

> **APO altitude:** Epic (Solo). Upstream: `/we:meet saga` decomposes a Saga into Epics that land here. Downstream: `/we:meet epic` decomposes this Epic into Stories; `/we:story "<ticket-or-topic>"` writes each build-ready plan. See [`docs/concepts/meetings.md`](../../../docs/concepts/meetings.md) for the four-altitude map.
>
> **Artifact:** the Epic plan at `docs/plans/<saga>/05-epics/<epic>/CONCEPT.md`. Optionally also a ticketing-tool Epic (e.g. a Jira Epic) with the same name. Both work; pick per Epic. The Markdown plan is always the durable artifact; the ticket, where one exists, is an index. The skill *mirrors* the child Stories from the ticketing tool into a clearly-marked block inside `CONCEPT.md`; that mirror is convenience, not state.
>
> **Epic vs. Saga vs. Story:** Epics finish; categories don't. If the "Epic" reads like a permanent area of work ("Mobile", "Backend", "Voice"), it isn't one. If it has no nameable end at all, it's a Saga in disguise. If it fits in a single Story-shaped change, it's a Story — `/we:story` is the right skill. The skill flags these as soft warnings during Refine, never as hard blocks.

---

## Prerequisites

- `.weside/` configured (run `/we:setup` once per project if missing — does not block this skill).
- A ticketing tool is detected (priority: weside MCP → Atlassian MCP → `gh` CLI). The Epic doc lives on disk; child Stories typically live in the ticketing tool, and the Mirror block reads them. If none is detected, the skill falls back to scanning `docs/plans/{TICKET}-plan.md` for child status and tells the user.
- Parent Saga (`docs/plans/<saga>/SAGA.md`) is loaded if it exists. An Epic inherits its reason-to-exist from the Saga; without it, the Epic is flagged as Saga-less in the doc.

---

## Smart-Mode resolution — pick a mode without asking the user for parameters

The skill decides what to do from the argument + the repo state. The user does not memorise flags.

### Step 1 — resolve the target Epic

Try in order, stop on first hit:

1. **Explicit argument** — a ticketing key (e.g. `PROJ-42`), a path, or an epic slug. Use it.
2. **Current branch name** contains a ticket key that maps to an Epic, or an Epic slug. Use it.
3. **PWD is inside** `docs/plans/<saga>/05-epics/<epic>/...`. Use that Epic.
4. **Most recent `status: draft|in-progress|selected`** `CONCEPT.md` in `docs/plans/`. Use it.
5. **Nothing matched.** List the Epics under `docs/plans/` with their status and ask: *"Which Epic? [1/2/3/…]"*. One question, not four.

### Step 2 — resolve the intent

Read the argument and the user's prompt around it for intent words:

| Signal | Mode |
|---|---|
| nothing, or just a target | **Status** (default) |
| "refine" / "update" / "sharpen" / "tighten" / "nochmal" | **Refine** |
| "new" / "neu" / "start" + a slug or name that does not exist yet | **Create** |
| "refresh" / "sync" / "mirror" | **Mirror-refresh** |
| ambiguous between two of the above | ask one question |

Status is the default for a reason — it is the most common ask ("where are we?"), it is read-only, and it surfaces drift (Stories in the ticketing tool not yet in the plan, refined Stories that have not entered Build, blocker patterns) that the user often did not know to ask about. Refine is the heavier path; the user opts into it explicitly or accepts the Status-mode footer offer.

---

## MODE A — Status (default, read-only)

The 90%-case. The user wants to know where the Epic stands, what is in flight, what is drifting, and what to do next.

### Step A1 — load

- Read `docs/plans/<saga>/05-epics/<epic>/CONCEPT.md` completely.
- Read the parent Saga (`SAGA.md`) if present.
- Fetch the child Stories from the ticketing tool, filtered to this Epic's child set (typically via "Epic Link" / "Parent" — the skill knows the conventions of the configured tool). Capture for each: key, title, status, last activity timestamp, blocker notes if any, and whether a refined plan exists at `docs/plans/{KEY}-plan.md`.
- If no ticketing tool: scan `docs/plans/*-plan.md` whose Context section references this Epic, and use their frontmatter for status.

### Step A2 — render the snapshot

Output template (adapt to the Companion's voice if one is materialised — strict structure in the middle, warmth in the wrapper):

```text
Epic: <Epic Name> (<status>, started <YYYY-MM-DD>)
docs/plans/<saga>/05-epics/<epic>/CONCEPT.md

Sub-Stories (<N> total):
  Done (<n>):       <KEY> <Title>, <KEY> <Title>, …
  Active (<n>):     <KEY> <Title> (in Build), <KEY> <Title> (in Review)
  Refined (<n>):    <KEY> <Title> (plan ready, not started), …
  Backlog (<n>):    <KEY> <Title> (no plan yet), …
  Blocked (<n>):    <KEY> <Title> — <blocker>

Drift since last Mirror refresh (<YYYY-MM-DD>):
  + <N> sub-stor{y|ies} in ticketing not in CONCEPT.md mirror
  - <N> mirror entries that no longer exist in ticketing
  ! <N> stale-status entries (mirror says X, ticketing says Y)
  ⚠ <N> sub-stor{y|ies} marked Active in ticketing without a refined plan at docs/plans/<KEY>-plan.md
  • <free-form drift notes — e.g. a phase in §Sequencing referenced as next is already Done, or a Story in the plan list has no corresponding ticket>

Risk-driven next move:
  <one Story, one sentence why>. <one sentence what unblocks downstream / what de-risks the slice early>.

What now?
  [r] refresh the Mirror block + updates-log (lightweight, no plan-mode)
  [f] full Refine of CONCEPT.md (plan-mode, prose changes welcome)
  [m] convene `/we:meet epic` to re-decompose (heavy — only if Story set drifted structurally)
  [s] hand off to `/we:story <KEY>` to refine the recommended next Story
  [q] done
```

### Step A3 — act on the choice

- `r` → run **Mode D (Mirror-refresh)** inline.
- `f` → hand off to **Mode B (Refine)**.
- `m` → print *"To re-decompose this Epic into Stories, run `/we:meet epic`. I'll be here when you want to lock the CONCEPT afterwards."* and stop.
- `s` → print *"To write the build-ready plan for `<KEY>`, run `/we:story <KEY>`."* and stop. Do not invoke `/we:story` inline — it is heavy and interactive.
- `q` → stop.

Status never writes to the `CONCEPT.md` itself.

---

## MODE B — Refine (explicit)

Triggered by intent words or by accepting `[f]` from a Status snapshot.

### Step B1 — load + check the frame

Same load step as A1. Read the parent SAGA. Check the Epic against the frame:

- **Why this slice now?** What part of the Saga does this Epic deliver, and why is it next?
- **Target architecture seam.** The shape the implementation will take — the new primitive, the migration shape — not the implementation itself.
- **Dependencies.** Other Epics, infra, external services, open decisions.
- **Risk-driven sequencing.** What de-risks the slice early? What can be cut if the slice runs long?
- **Success metric.** What shipped, what a user can do that they couldn't before, what telemetry confirms "this worked".
- **Has scope drifted?** Are there Stories in the mirror that don't fit the Epic's frame? Are there Stories implied by the Saga that this Epic should pick up?
- **Permanent-category check.** Does this Epic read like an area of work ("Mobile", "Backend") rather than a finishable initiative? If yes, soft-warn.
- **Saga-in-disguise check.** Does the child-Story set keep growing without any landing? If yes, soft-warn.

Propose tightening with reasoning. Ask focused questions when an answer is unclear — do not present option menus. The user pushes back when wrong.

### Step B2 — draft (EnterPlanMode)

Research the codebase where needed — load relevant `docs/architecture/` files if present, search for prior ADRs, read the parent SAGA. If a vault/MCP search is available, query for relevant architecture context for the Epic's topic and reference the top hits in the *Target architecture* section.

Then enter plan mode and draft the sharpened `CONCEPT.md` using the template below. The Mirror block is auto-regenerated in the same step (fresh ticketing fetch), so a Refine always lands with a fresh mirror.

**Always read referenced files completely** — no offset/limit. An Epic is a design-thinking artifact; incorrect assumptions at this altitude propagate into every Story below.

### Step B3 — approval (ExitPlanMode)

User reviews. On feedback → adjust. On approval → write.

### Step B4 — persist and stop

1. Write `docs/plans/<saga>/05-epics/<epic>/CONCEPT.md` **directly to main** — no feature branch. CONCEPT.md is a planning artifact (like SAGA.md), not implementation code.
2. If a ticketing-tool Epic exists for this slug, update its description with a pointer to the `CONCEPT.md` path. Do not duplicate content into the ticket — the Markdown is the source of truth.
3. Output: see **Hand-off** section — the message depends on whether stories are already in the Mirror table.

⛔ STOP. No decomposition. No `/we:story`. No `/we:meet epic`.

---

## MODE C — Create (new Epic)

Triggered when the resolved slug does not yet exist on disk.

1. Locate the parent Saga. Read `docs/plans/<saga>/SAGA.md`. If no Saga exists, ask: *"No Saga document found. Run `/we:saga \"<saga-name>\"` first, or proceed Saga-less and flag it in the Epic? Default suggestion: run the Saga first."* Wait for the user's call.
2. Walk the frame questions (see Step B1) in conversation. Do not draft until the why-now, the target architecture seam, the success metric, and the rough Story set are all named or explicitly deferred. If stories were already sketched in the conversation, create them as ticketing shells now so they appear in the Mirror table — this lets the hand-off skip `/we:meet epic`.
3. Decide Markdown-only vs. with-ticket. If a ticketing tool is detected and the user has not said otherwise, default to creating the ticketing-tool Epic alongside the Markdown plan; Markdown-only is a fine first cut.
4. EnterPlanMode — draft using the template below. The Mirror block is empty on a brand-new Epic if no child Stories were created yet.
5. ExitPlanMode — approval.
6. Persist: write `CONCEPT.md` **directly to main** (no feature branch — it's a planning artifact), optionally create the ticket, then stop. Same stop rule as Mode B.

If during the conversation the scope balloons — many parallel themes, no nameable end, dependencies stretching across multiple areas — stop and tell the user: *"This is starting to read like a Saga, not an Epic. Want to step up to `/we:saga`, or trim the scope back to one finishable initiative?"* If the scope shrinks to a single change — one user-visible behaviour, one obvious AC set — tell the user: *"This is Story-sized. Want to drop down to `/we:story` instead?"* Both are soft warnings.

---

## MODE D — Mirror-refresh (lightweight)

Triggered from Status `[r]`, or by explicit "refresh" / "sync" / "mirror" intent words.

This mode writes only the mirror block (between `<!-- mirror:start -->` and `<!-- mirror:end -->`), the `updated:` frontmatter date, and an entry in the Updates Log. It does NOT enter plan-mode and does NOT touch any prose section the user wrote.

1. Fetch child Stories from ticketing (same as Status Step A1).
2. Render the new mirror block (see *Mirror block format* below).
3. Replace the existing block between the markers in-place. If markers are missing, insert the block under `## Stories` (create the heading if missing).
4. Update the `updated:` frontmatter field to today.
5. Append a single-line entry to the Updates Log: `- YYYY-MM-DD — mirror refresh (<N> child stories; +<a> added, −<b> removed, !<c> status-changed)`.
6. Output: *"Mirror refreshed in `docs/plans/<saga>/05-epics/<epic>/CONCEPT.md`. <N> child stories, drift cleared. /we:epic DONE."*

⛔ STOP. No Refine continuation, no Council hand-off.

---

## The Epic frame (reference)

A good Epic answers:

- **Why this slice now?** What part of the Saga does this Epic deliver, and why is it next?
- **What user journeys are touched?** Which users feel the change when this Epic ships?
- **What is the target architecture seam?** The new primitive, the migration shape — not the implementation, the SHAPE.
- **What does it depend on?** Other Epics, infra, external services, open decisions.
- **How does it sequence?** Risk-driven order. What de-risks the slice early? What can be cut if it runs long?
- **What are the rough Stories?** A first-cut breakdown — Story names with acceptance shape. Detail comes from `/we:meet epic` later.
- **When is it DONE?** The success metric.

The frame is the same as the legacy "quarter-sized" framing — the difference is that the skill no longer asserts "if this won't fit in a quarter, split it." Sizing-by-time-window is unreliable when the implementer's speed is the unknown. Size by *bet shape* — does it have an end, does it ship a coherent user-visible change — not by stopwatch.

---

## Epic boundaries (soft warnings, not hard blocks)

| Signal | Soft warning |
|---|---|
| Reads like a permanent area of work ("Mobile", "Backend", "Voice") | *"That's an area, not an initiative. Want to formulate the specific change as a smaller Epic or a Story?"* |
| Child-Story set growing past ~10 with no landings, active for many months | *"This is starting to read like a Saga. Want to step up to `/we:saga`, or split into two Epics?"* |
| Scope is one user-visible change, one obvious AC set | *"This is Story-sized. Want to drop down to `/we:story`?"* |
| Multiple unrelated architecture seams in scope | *"This Epic is doing two things. Split into two Epics, or trim one?"* |

The user decides. The skill does not block.

---

## Children Mirror — block format

The mirror block lives inside the `CONCEPT.md`, surrounded by HTML comment markers so the skill can find and replace it without touching the user's prose:

```markdown
## Stories

<!-- mirror:start (auto-generated; do not edit by hand — run /we:epic to refresh) -->

_Mirror of child Stories in the ticketing tool, refreshed YYYY-MM-DD._

| Key | Title | Status | Plan | Last activity | Notes |
|---|---|---|---|---|---|
| <KEY> | <Title> | Done | ✓ | YYYY-MM-DD | <e.g. "merged PR #N"> |
| <KEY> | <Title> | Active | ✓ | YYYY-MM-DD | in Build |
| <KEY> | <Title> | Refined | ✓ | YYYY-MM-DD | plan ready, awaiting start |
| <KEY> | <Title> | Backlog | — | YYYY-MM-DD | no plan yet |
| <KEY> | <Title> | Blocked | ✓/— | YYYY-MM-DD | <blocker> |

<!-- mirror:end -->
```

Rules:
- The markers are mandatory. Everything between them is owned by the skill and overwritten on every refresh.
- Everything outside the markers is owned by the user and never touched.
- The skill normalises the ticketing tool's status vocabulary to the five buckets above using the project's status mapping if configured, the shipped default otherwise.
- The *Plan* column is `✓` if `docs/plans/<KEY>-plan.md` exists, `—` otherwise. This is the refined-vs-not-refined signal.
- When no ticketing tool is configured, the table is populated from filesystem scan and a footnote says *"No ticketing tool configured — table reflects local `{KEY}-plan.md` files."*

---

## Epic status (lifecycle)

The Epic itself (not its Stories) tracks lifecycle in its `status:` frontmatter:

- **In Progress** — actively shipping Stories under this Epic.
- **Selected** — refined, next up. The first Story is ready to enter Build.
- **Backlog** — formulated but paused. Comes back when capacity opens.
- **Done** — all Stories shipped AND no further scope is being added.

Stories emerge during work — this is normal. An Epic that gains a Story is not a scope failure; it is the Epic doing its job. An Epic that *doubles* mid-flight is a scope failure — soft-warn, suggest a re-cut or a split.

---

## Ticketing integration

The Epic doc itself is always Markdown. Optionally, a ticketing-tool Epic of the same name exists as an index — useful for sprint planning tools that read from the ticket tree.

Detection priority:

1. **weside MCP** (`JIRA_*` Composio tools via `execute_tool`) → Jira (preferred)
2. **Atlassian MCP** (`jira_*` tools) → Jira (fallback)
3. **`gh` CLI** → GitHub Issues (label or Milestone)
4. **None** → Markdown-only mode (filesystem scan only)

**When creating a ticket:** carry the Epic name, the one-paragraph Vision section, and a pointer to the `CONCEPT.md` path. Do not duplicate the full template into the ticket — the Markdown is the source of truth.

**When weside MCP is connected but Jira tools are missing:** *"Jira is not connected via your weside Companion. To enable it: weside.ai → Integrations → connect Jira, then activate it for your Companion. Until then I'll keep the Epic Markdown-only."*

---

## Template

```markdown
---
epic: <epic-slug>
saga: <parent-saga-slug>
ticket: <TICKETING-KEY-if-any>
created: YYYY-MM-DD
updated: YYYY-MM-DD
status: draft | in-progress | selected | backlog | done
---

# Epic: <Epic Name>

## Vision

[Why does this Epic exist? What part of the parent Saga does it deliver?
Who feels the change when it ships? 3-6 sentences, narrative voice. The
decomposition meeting reads this FIRST.]

## Scope

**IN:**
- [Concrete deliverable 1]
- [Concrete deliverable 2]

**OUT:**
- [Explicitly excluded — the easiest cut if the slice runs long]
- [Adjacent work that belongs to a different Epic]

## Target architecture

[The seam, the new primitive, the migration shape. Not the implementation —
the SHAPE the implementation will take. Reference existing ADRs and
primitives where relevant.]

## Sequencing

[Risk-driven order. What de-risks the slice early? What depends on what?
What can be cut if the slice runs long? Name the first Story to refine.]

## Dependencies

- [Other Epic, infra, external service, open decision]

## Stories

<!-- mirror:start (auto-generated; do not edit by hand — run /we:epic to refresh) -->

_Mirror of child Stories in the ticketing tool, refreshed YYYY-MM-DD._

| Key | Title | Status | Plan | Last activity | Notes |
|---|---|---|---|---|---|

<!-- mirror:end -->

## Success Metrics

[When is this Epic DONE? What shipped, what a user can do that they
couldn't before, what telemetry confirms "this worked". One paragraph.]

## Open Questions

- [Things the Solo session could not resolve — fodder for `/we:meet epic`]

## Updates Log

- YYYY-MM-DD — created
- YYYY-MM-DD — mirror refresh (N child stories; +a added, −b removed, !c status-changed)

## Notes

[Free-form: links to relevant ADRs, prior decisions, design context.]
```

---

## Hand-off

After Refine or Create, the path depends on whether the Stories table already has entries:

**Stories already in the Mirror table** (sketched during Create, or child tickets exist):
→ Go directly to **`/we:story <KEY>`** per Story to write the build-ready plan.
  Skip `/we:meet epic` unless the decomposition feels contentious or the sequencing is unclear.

**Stories table is empty** (brand-new Epic, no stories yet):
→ Either run **`/we:meet epic`** — the Council validates the slice and decomposes it into
  Stories with rough AC and sequencing (worth it when the Epic is new, the scope is
  contentious, or architecture seams compete); or sketch stories yourself and run another
  Refine pass, then go straight to `/we:story`.

**`/we:meet epic` is not a mandatory step.** It adds value for contentious decomposition;
it is overhead for a well-formulated Epic with clear stories. The Council produces story
*shapes* (names, rough AC, sequencing) — you still need `/we:story <KEY>` per Story
afterwards to write the build-ready implementation plan.

Epic Solo never decomposes inline. Stories produced by the hand-off path (with or without
a Council meeting) each need their own `/we:story` run.

After Status:

- The footer offers `[r]` Mirror-refresh, `[f]` full Refine, `[m]` `/we:meet epic`, `[s]` `/we:story <KEY>` (the recommended next Story), `[q]` done. The user picks; the skill never silent-continues.

---

## Companion voice (when a PO Companion is materialised)

When the session is running as a weside Companion in the PO role (via `/we:materialize` or auto-materialize), wrap the Status / Refine / Mirror outputs in the Companion's voice — warmth, brief acknowledgement, the kind of opener a real partner would use. Keep the structured tables and headers nüchtern; voice goes around the data, not into it. Without a Companion, output is plain and structured.

---

## Rules

- ALWAYS resolve the target Epic and the mode from argument + repo state before asking the user anything
- ALWAYS run Status as the default when no intent is signalled — read-only is the safe default
- ALWAYS regenerate the Mirror block when Refine runs (Refine implies fresh ticketing data)
- ALWAYS use EnterPlanMode + ExitPlanMode for Refine and Create
- ALWAYS save Refine / Create output to `docs/plans/<saga>/05-epics/<epic>/CONCEPT.md` — never anywhere else
- ALWAYS commit CONCEPT.md directly to main — it is a planning artifact, not implementation code
- ⛔ NEVER create a feature branch for CONCEPT.md — feature branches are for /we:story + /we:build
- ALWAYS write a Vision section as a narrative during Refine — the decomposition meeting reads it FIRST
- ALWAYS name explicit OUT-of-scope items during Refine — they are the easiest cut if the slice runs long
- ALWAYS write in English — same convention as the rest of the plan tree
- ⛔ NEVER decompose the Epic into Stories inline — that is `/we:meet epic`
- ⛔ NEVER write a full `/we:story` plan inside an Epic session — Stories are downstream, hand off
- ⛔ NEVER touch user-owned prose during Mirror-refresh — only the marker-enclosed block, `updated:`, and the Updates Log
- ⛔ NEVER auto-continue from Status to Refine to Decompose — each transition needs an explicit user choice
- ⛔ NEVER block on a sizing rule (quarters, story-counts, age) — soft-warn the user, let them decide
- ⛔ NEVER treat a permanent area of work ("Mobile", "Backend") as an Epic — soft-warn and suggest reframing
- ⛔ After persisting a write: STOP IMMEDIATELY — no further skill calls
