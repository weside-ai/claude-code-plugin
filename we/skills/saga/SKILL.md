---
name: saga
description: >
  Saga (Solo) — Product Owner skill at the Theme altitude. Default mode is
  Status: read the current SAGA.md, mirror the child Epics from the
  ticketing tool, render a status snapshot + drift detection + a
  risk-driven next-move recommendation. Refine mode (explicit) sharpens
  the SAGA.md itself via plan-mode. Create mode handles a new slug.
  Mirror-refresh is a lightweight write that touches only the mirror
  block + updates-log. Use when the user says "/we:saga", "saga",
  "theme", "where are we on", "what's the status of", "refine saga",
  "new saga". For decomposing a Saga into Epics, use `/we:meet saga`
  first (Council brainstorm), then return here to lock the SAGA doc.
---


# Saga (Solo) — Product Owner at the Theme altitude

You hold the Saga at the Theme altitude — a multi-bet inside the product Vision. This skill is the Solo half; the Council half is `/we:meet saga`. The two interleave: a Council to decompose or to re-cut, then Solo to sharpen the Saga doc itself.

> **APO altitude:** Saga (Solo). Upstream: `/we:meet vision` decomposes a PRD into Sagas that land here. Downstream: `/we:meet saga` decomposes a Saga into Epics; `/we:epic "<name>"` formulates each Epic. See [`docs/concepts/meetings.md`](../../../docs/concepts/meetings.md) for the four-altitude map.
>
> **Artifact:** `docs/plans/<saga>-saga.md`. The Saga itself is always Markdown — ticketing starts at Epic. The skill *mirrors* the child Epics from the ticketing tool into a clearly-marked block inside `SAGA.md`; that mirror is convenience, not state. The Markdown remains the source of truth.
>
> **Saga vs. Vision:** a Saga has a beginning and an end. If it doesn't — if the bet stretches indefinitely or has no nameable win — it's a Vision in disguise. The skill flags this as a soft warning during Refine, never as a hard block.

---

## Prerequisites

- `.weside/` configured (run `/we:setup` once per project if missing — does not block this skill).
- A ticketing tool is detected (priority: weside MCP → Atlassian MCP → `gh` CLI). The Saga doc itself never lives in the ticketing tool, but its child Epics do, and the Mirror block reads them. If none is detected, the skill falls back to scanning `docs/plans/<saga>-*-epic.md` for child status and tells the user.
- Parent PRD (`docs/plans/<vision>-prd.md`) is loaded if it exists. A Saga inherits its reason-to-exist from the Vision; without it, the Saga is flagged as an orphan in the doc.

---

## Smart-Mode resolution — pick a mode without asking the user for parameters

The skill decides what to do from the argument + the repo state. The user does not memorise flags.

### Step 1 — resolve the target Saga

Try in order, stop on first hit:

1. **Explicit argument** — a path, a slug, or a ticket key. Use it.
2. **Current branch name** contains a ticket key or a Saga slug. Use it.
3. **PWD is inside** `docs/plans/` and a `<saga>-saga.md` is referenced. Use that Saga.
4. **Most recent `status: active|draft`** `<saga>-saga.md` in `docs/plans/`. Use it.
5. **Nothing matched.** List the Sagas under `docs/plans/` with their status and ask: *"Which Saga? [1/2/3/…]"*. One question, not four.

### Step 2 — resolve the intent

Read the argument and the user's prompt around it for intent words:

| Signal | Mode |
|---|---|
| nothing, or just a target | **Status** (default) |
| "refine" / "update" / "sharpen" / "tighten" / "nochmal" | **Refine** |
| "new" / "neu" / "start" + a slug that does not exist yet | **Create** |
| "refresh" / "sync" / "mirror" | **Mirror-refresh** |
| "promote" / "re-cut" / "this Epic is actually a Saga" / a ticketing **Epic key** that has Story children | **Promote** |
| ambiguous between two of the above | ask one question |

Status is the default for a reason — it is the most common ask ("where are we?"), it is read-only, and it surfaces drift that the user often did not know to ask about. Refine is the heavier path; the user opts into it explicitly or accepts the Status-mode footer offer.

---

## MODE A — Status (default, read-only)

The 90%-case. The user wants to know where the Saga stands, what is in flight, what is drifting, and what to do next.

### Step A1 — load

- Read `docs/plans/<saga>-saga.md` completely.
- Read the parent PRD if present.
- Fetch the child Epics from the ticketing tool, filtered to this Saga's child set (typically via "Epic Link" / "Parent" / project label — the skill knows the conventions of the configured tool). Capture for each: key, title, status, last activity timestamp, blocker notes if any.
- If no ticketing tool: scan `docs/plans/<saga>-*-epic.md` frontmatter for status and `updated`.

### Step A2 — render the snapshot

Output template (adapt to the Companion's voice if one is materialised — strict structure in the middle, warmth in the wrapper):

```text
Saga: <Saga Name> (<status>, started <YYYY-MM-DD>)
docs/plans/<saga>-saga.md

Sub-Epics (<N> total):
  Done (<n>):     <KEY> <Title>, <KEY> <Title>, …
  Active (<n>):   <KEY> <Title>, …
  Backlog (<n>):  <KEY> <Title> (<short blocker note>), …
  Blocked (<n>):  <KEY> <Title> — <blocker>

Drift since last Mirror refresh (<YYYY-MM-DD>):
  + <N> sub-epic(s) in ticketing not in SAGA.md mirror
  - <N> mirror entries that no longer exist in ticketing
  ! <N> stale-status entries (mirror says X, ticketing says Y)
  • <free-form drift notes the skill noticed — e.g. a hypothesis in the doc text marked as falsified while the frontmatter still reads draft>

Risk-driven next move:
  <one Epic, one sentence why>. <one sentence what unblocks downstream / what the cost of not doing it is>.

What now?
  [r] refresh the Mirror block + updates-log (lightweight, no plan-mode)
  [f] full Refine of SAGA.md (plan-mode, prose changes welcome)
  [m] convene `/we:meet saga` to re-decompose (heavy — only if structural drift)
  [q] done
```

### Step A3 — act on the choice

- `r` → run **Mode D (Mirror-refresh)** inline.
- `f` → hand off to **Mode B (Refine)**.
- `m` → print *"To re-decompose this Saga into Epics, run `/we:meet saga`. I'll be here when you want to lock the SAGA doc afterwards."* and stop.
- `q` → stop.

Status never writes to the SAGA.md itself.

---

## MODE B — Refine (explicit)

Triggered by intent words or by accepting `[f]` from a Status snapshot.

### Step B1 — load + walk the four frame questions

Same load step as A1. Walk the four frame questions in conversation:

1. **The bet** — one sentence. Has it drifted from what was originally agreed?
2. **Success criteria** — externally verifiable. Has the list grown into "and also…"?
3. **Bounded scope** — what is IN, what is explicitly OUT. Missing OUTs are the silent scope-expanders.
4. **What success eliminates** — *"if this lands, we no longer need to argue about ___"*. If the user cannot finish the sentence, the Saga is not a bet yet.

Propose tightening with reasoning. Ask focused questions when an answer is unclear — do not present option menus. The user pushes back when wrong.

### Step B2 — draft (EnterPlanMode)

Inside plan mode, draft the revised `SAGA.md` using the template below. The Mirror block is auto-regenerated in the same step (fresh ticketing fetch), so a Refine always lands with a fresh mirror.

### Step B3 — approval (ExitPlanMode)

User reviews. On feedback → adjust. On approval → write.

### Step B4 — persist and stop

1. Write `docs/plans/<saga>-saga.md` in the project's main worktree.
2. Output: *"Saga sharpened at `docs/plans/<saga>-saga.md`. Mirror refreshed against ticketing. To decompose into Epics, run `/we:meet saga`. /we:saga DONE."*

⛔ STOP. No decomposition. No `/we:epic`. No `/we:meet saga`.

---

## MODE C — Create (new Saga)

Triggered when the resolved slug does not yet exist on disk.

1. If no parent PRD exists, tell the user: *"No Vision document found. You can run `/we:vision` first to anchor this Saga, or proceed without — this will be an orphan Saga and the doc will flag it."* Wait.
2. Walk the four frame questions in conversation. Do not draft until the bet, success criteria, scope, and what-success-eliminates are all named.
3. EnterPlanMode — draft using the template below. The Mirror block is empty on a brand-new Saga (no child Epics yet).
4. ExitPlanMode — approval.
5. Persist to `docs/plans/<saga>-saga.md`. Same stop rule as Mode B.

If during the conversation the scope balloons past what looks finishable — many parallel themes, no nameable end, multiple horizons — stop and tell the user: *"This is starting to read like a Vision. Want to step up to `/we:vision`, or trim the scope back to one bet?"* This is a soft warning, not a hard block.

---

## MODE D — Mirror-refresh (lightweight)

Triggered from Status `[r]`, or by explicit "refresh" / "sync" / "mirror" intent words.

This mode writes only the mirror block (between `<!-- mirror:start -->` and `<!-- mirror:end -->`), the `updated:` frontmatter date, and an entry in the Updates Log. It does NOT enter plan-mode and does NOT touch any prose section the user wrote.

1. Fetch child Epics from ticketing (same as Status Step A1).
2. Render the new mirror block (see *Mirror block format* below).
3. Replace the existing block between the markers in-place. If markers are missing, insert the block under `## Sub-Epics` (create the heading if missing).
4. Update the `updated:` frontmatter field to today.
5. Append a single-line entry to the Updates Log: `- YYYY-MM-DD — mirror refresh (<N> child epics; +<a> added, −<b> removed, !<c> status-changed)`.
6. Output: *"Mirror refreshed in `docs/plans/<saga>-saga.md`. <N> child epics, drift cleared. /we:saga DONE."*

⛔ STOP. No Refine continuation, no Council hand-off.

---

## MODE E — Promote (existing ticketing Epic → Saga)

Triggered when the target is a **ticketing Epic that has grown into a Saga** — many
Story children, no nameable end, themes that each deserve their own Epic. The
canonical signal: the user passes an Epic key (or says "this Epic is actually a
Saga" / "re-cut" / "promote"). This is the Brownfield path the greenfield Create
mode does not cover — the ticketing tool already holds an Epic and dozens of
Stories parented to it, and the four-altitude model has no Saga level in most
ticketing tools (Jira knows only Epic→Story). Promote bridges that gap.

### Step E1 — load + confirm the promotion is warranted

- Fetch the source Epic and **all** its child Stories from ticketing (key, title,
  status). Count them.
- Sanity-check the "Saga in disguise" signal: > ~8 children, active for months,
  multiple distinct themes, no single landing. If the signal is weak, say so and
  ask the user to confirm they still want to promote (maybe it's just a large Epic).

### Step E2 — propose the cut (conversation, not plan-mode yet)

- Cluster the child Stories into **3–6 candidate Epics** by theme/seam. Give each a
  short **epic-slug** and a one-line rationale. Name a saga-slug for the whole.
- Show the maturity gradient (which candidate Epics are Done / Active / Not-started)
  — a clean gradient is a good sign the cut follows real seams.
- Flag **orphans**: child Stories that don't fit any candidate Epic (they may belong
  to a *different* Saga, or get dropped). Never silently absorb them.
- The user corrects the cut. Iterate until they're happy. Do not draft until the
  saga-slug + the epic set + the orphan disposition are agreed.

### Step E3 — draft (EnterPlanMode)

Draft two things in plan-mode:

1. **`docs/plans/<saga>-saga.md`** using the Template below — distilled from the
   source Epic's existing doc if one exists (e.g. its CONCEPT). The big source doc
   stays in place as an architecture reference; the Saga doc is the lean frame.
2. **A Re-Parenting Plan** appended as a `## Promotion Plan` section (temporary —
   the user deletes it once executed). It specifies, as an explicit checklist:
   - the N new ticketing Epics to create, each titled with the **Jira-grouping
     convention** `[<saga-slug>] <Epic Title>` (so the flat Epic list shows saga
     membership — ticketing tools have no Saga level, the title prefix IS the group);
   - for each child Story: its current parent (the source Epic) → its new parent
     (one of the N new Epics), or "orphan → <disposition>";
   - what happens to the **source Epic ticket** after re-parenting: keep open as a
     historical anchor, or close — recommend, let the user decide;
   - the per-Epic markdown files to write next (`docs/plans/<saga>-<epic>-epic.md`),
     deferred to `/we:epic` per Epic (this skill does NOT write them).

### Step E4 — approval (ExitPlanMode), then persist + stop

1. Write `docs/plans/<saga>-saga.md` (incl. the `## Promotion Plan` checklist).
2. Do **not** auto-execute the ticketing re-parenting — it is bulk, partly
   irreversible work. Print the Promotion Plan as the next-actions checklist and let
   the user (or a follow-up turn) run it.
3. Output: *"Saga `<saga>` promoted from `<EPIC-KEY>` at `docs/plans/<saga>-saga.md`.
   Promotion Plan ready: create <N> Epics `[<saga>] …`, re-parent <M> Stories. Run
   `/we:epic "<first-epic>"` to formulate the first Epic doc. /we:saga DONE."*

⛔ STOP. No ticketing mutations, no `/we:epic`, no `/we:meet saga` fired inline.

---

## The Saga frame (reference)

A good Saga answers four questions, in order:

1. **The bet.** What is the multi-bet thing we are pointing energy at? Name it in one sentence.
2. **Success criteria.** What does landed-and-done look like? Externally verifiable.
3. **Bounded scope.** What is in the Saga and what is explicitly out? A Saga without an "out" list is a Vision.
4. **What success eliminates.** *"If this lands, we no longer need to argue about ___."* This is the honesty test — if nothing gets eliminated, the Saga isn't biting.

**Frame question:** *Where do we want to be in a meaningful while?* (The old "twelve months" wording was a sizing guess and a fragile one — implementation speed is decoupled from human planning intuition. Track the bet's seam, not the calendar.)

---

## Saga-vs-Vision boundary (soft warning, not a hard block)

If, during Refine or Create, you notice:

- the bet has no nameable end state, or
- success criteria keep escaping into "and also…" territory, or
- the user cannot finish *"if this lands, we no longer need to argue about ___"*, or
- the child-Epic set has grown past ~8 and the Saga has been active for many months without any landing,

tell the user *"This is reading more like a Vision than a Saga. Want to step up to `/we:vision`, or split into two Sagas?"* Soft warning. The user decides; the skill does not block.

(The previous "max 4 quarters" hard rule is removed. Sizing-by-time-window is unreliable when the implementer's speed is the unknown. Size by *bet shape* — does it have an end, does it eliminate an argument — not by stopwatch.)

---

## Children Mirror — block format

The mirror block lives inside the SAGA.md, surrounded by HTML comment markers so the skill can find and replace it without touching the user's prose:

```markdown
## Sub-Epics

<!-- mirror:start (auto-generated; do not edit by hand — run /we:saga to refresh) -->

_Mirror of child Epics in the ticketing tool, refreshed YYYY-MM-DD._

| Key | Title | Status | Last activity | Notes |
|---|---|---|---|---|
| <KEY> | <Title> | Done | YYYY-MM-DD | <free-form, e.g. "merged PR #N"> |
| <KEY> | <Title> | Active | YYYY-MM-DD | |
| <KEY> | <Title> | Backlog | YYYY-MM-DD | <blocker, e.g. "external dependency"> |
| <KEY> | <Title> | Blocked | YYYY-MM-DD | <blocker> |

<!-- mirror:end -->
```

Rules:
- The markers are mandatory. Everything between them is owned by the skill and overwritten on every refresh.
- Everything outside the markers is owned by the user and never touched.
- The skill normalises the ticketing tool's status vocabulary to the four buckets above (Done / Active / Backlog / Blocked) using the project's status mapping if configured, the shipped default otherwise.
- When no ticketing tool is configured, the table is populated from filesystem scan and a footnote says *"No ticketing tool configured — table reflects local `CONCEPT.md` frontmatter status."*

---

## Template

```markdown
---
saga: <saga-slug>
vision: <parent-vision-slug>  # optional; omit for orphan Sagas
created: YYYY-MM-DD
updated: YYYY-MM-DD
status: draft | active | landed | abandoned
---

# Saga: <Name>

## The Bet

[One sentence. The multi-bet thing we point energy at.]

## Why Now

[2-4 sentences. What in the Vision, in the market, or in the codebase makes this the right next bet. Anchor to the PRD if there is one.]

## Success Criteria

- [Concrete, externally verifiable.]
- [If the list is long, the Saga is probably two Sagas — soft-warn during Refine.]

## In Scope

- [What this Saga covers.]

## Out of Scope

- [What this Saga does NOT cover. If empty, the Saga isn't bounded — fix that before saving.]

## What Success Eliminates

[Plain prose. "If this lands, we no longer need to argue about X." If you cannot finish this sentence, the Saga isn't a bet yet.]

## Sub-Epics

<!-- mirror:start (auto-generated; do not edit by hand — run /we:saga to refresh) -->

_Mirror of child Epics in the ticketing tool, refreshed YYYY-MM-DD._

| Key | Title | Status | Last activity | Notes |
|---|---|---|---|---|

<!-- mirror:end -->

## Open Questions

- [Things genuinely unsettled. Will be resolved during `/we:meet saga` or as Epics start.]

## Updates Log

- YYYY-MM-DD — created
- YYYY-MM-DD — mirror refresh (N child epics; +a added, −b removed, !c status-changed)

## Notes

[Free-form: links to relevant ADRs, prior decisions, market context.]
```

---

## Hand-off

After Refine or Create:

1. **`/we:meet saga`** — convene the Council, validate the Saga against the Vision, decompose into Epics with rough sequencing.
2. **`/we:epic "<epic-name>"`** — per Epic that came out of the meeting, formulate the Epic doc.

Saga Solo never decomposes. Decomposition lives in `/we:meet saga` precisely because it benefits from multi-voice tension (PO + Architect + a rotating domain voice).

After Status:

- The footer offers `[r]` Mirror-refresh, `[f]` full Refine, `[m]` `/we:meet saga`, `[q]` done. The user picks; the skill never silent-continues.

---

## Companion voice (when a PO Companion is materialised)

When the session is running as a weside Companion in the PO role (via `/we:materialize` or auto-materialize), wrap the Status / Refine / Mirror outputs in the Companion's voice — warmth, brief acknowledgement, the kind of opener a real partner would use. Keep the structured tables and headers nüchtern; voice goes around the data, not into it. Without a Companion, output is plain and structured.

---

## Rules

- ALWAYS resolve the target Saga and the mode from argument + repo state before asking the user anything
- ALWAYS run Status as the default when no intent is signalled — read-only is the safe default
- ALWAYS regenerate the Mirror block when Refine runs (Refine implies fresh ticketing data)
- ALWAYS use EnterPlanMode + ExitPlanMode for Refine, Create, and Promote
- ALWAYS save Refine / Create / Promote output to `docs/plans/<saga>-saga.md` — never anywhere else
- ALWAYS use the Jira-grouping convention `[<saga-slug>] <Epic Title>` for the child Epics a Promote (or any decomposition) creates — ticketing tools have no Saga level, so the title prefix is what makes saga membership visible in the flat Epic list
- ⛔ NEVER auto-execute ticketing re-parenting during Promote — produce the Promotion Plan checklist and let the user run it (bulk, partly irreversible)
- ALWAYS name what is explicitly **out** of scope during Refine — a Saga without OUT is a Vision
- ALWAYS write in English — same convention as the rest of the plan tree
- ⛔ NEVER decompose the Saga into Epics inline — that is `/we:meet saga`
- ⛔ NEVER create a ticketing-tool item for the Saga itself — Sagas are Markdown-only; only the child Epics live in the ticketing tool
- ⛔ NEVER touch user-owned prose during Mirror-refresh — only the marker-enclosed block, `updated:`, and the Updates Log
- ⛔ NEVER auto-continue from Status to Refine to Decompose — each transition needs an explicit user choice
- ⛔ NEVER block on a sizing rule (quarters, story-counts, age) — soft-warn the user, let them decide
- ⛔ After persisting a write: STOP IMMEDIATELY — no further skill calls
