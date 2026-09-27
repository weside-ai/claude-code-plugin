# Skill Reference

Every `/we:*` skill, what it does, when to use it, what it produces. Grouped by role in the workflow.

For the pipeline overview, see [workflow.md](workflow.md). For learning by doing, see [getting-started.md](getting-started.md).

---

## Plan altitude skills

Four altitudes — Vision, Saga, Epic, Story. Each has a **Solo** half (formulate / refine the item) and a **Meet** half (Council that decomposes the item into the next altitude down). The Solo skills are listed first; the Meet variants are all dispatched via the single `/we:meet` skill (see *Deliberation skills* below).

### `/we:vision`

> *Solo — Product Owner at the PRD altitude.*

Produces or sharpens a Product Requirements Document — the multi-year reason a product exists, the audience it serves, the change it intends, the bets it will not make.

**When to use:**
- Starting a new product or sub-product
- After a strategic pivot — the old PRD no longer fits
- When the team can name 50 features but cannot finish the sentence "we exist to ___"

**What it produces:**
- `docs/plans/<vision>/PRD.md` — one PRD per product

**Hand-off:** to `/we:meet vision` (decompose the PRD into Sagas) or `/we:saga "<name>"` (formulate one Saga the PRD implies).

---

### `/we:saga`

> *Solo — Product Owner at the Theme altitude. Status-default; smart-mode resolution.*

Holds a Saga — a multi-bet inside the Vision. "Make the platform multi-tenant." "Become voice-first." Sagas have a beginning and an end; if they don't, they're a Vision in disguise.

**Four modes, picked automatically from argument + repo state:**

- **Status** (default) — read `docs/plans/<saga>-saga.md`, mirror child Epics from the ticketing tool, render snapshot + drift detection + risk-driven next-move recommendation. Read-only.
- **Refine** (explicit intent: "refine" / "update" / "sharpen") — walks the four frame questions, drafts a tightened saga plan via plan-mode.
- **Create** (slug doesn't exist yet) — walks the frame from scratch.
- **Mirror-refresh** (intent: "refresh" / "sync" / "mirror") — lightweight write of just the mirror block + frontmatter date + Updates Log.

No flags to memorise. Target Saga is resolved from explicit argument → branch name → PWD → most-recent draft/active doc → ask one question.

**When to use:**
- "Where are we on this Saga?" — Status default; the 90%-case
- The Vision is set and you're choosing where to point energy next — Create
- A long-running Saga showing drift — Refine after a `/we:meet saga` Council
- Multiple Epics in flight that secretly belong to different themes — surface them by running Status across each candidate

**What it produces:**
- `docs/plans/<saga>-saga.md` — Markdown only; ticketing starts at Epic. The doc contains an auto-generated `## Sub-Epics` mirror block between `<!-- mirror:start --> … <!-- mirror:end -->` markers.

**Hand-off:** Status footer offers `[r]` refresh, `[f]` Refine, `[m]` `/we:meet saga`, `[q]` done. After Refine, hand off to `/we:meet saga` (decompose) or `/we:epic "<name>"` (formulate one Epic).

---

### `/we:epic`

> *Solo — Product Owner at the Initiative altitude. Status-default; smart-mode resolution.*

Holds an Epic — a concrete, bounded deliverable that serves a Saga. "Ledger Foundation." "Stripe Connect Onboarding." "Voice Pipeline Migration." Epics finish; permanent areas of work ("Mobile", "Backend") don't.

**Four modes, picked automatically from argument + repo state:**

- **Status** (default) — read the epic doc, mirror child Stories from the ticketing tool, render snapshot + drift detection + risk-driven next-move. The mirror table flags refined-vs-not-refined per Story (does `docs/plans/{KEY}-story.md` exist?). Read-only.
- **Refine** (explicit intent) — checks the frame (why-now, target architecture seam, sequencing, success metric), drafts via plan-mode.
- **Create** (new slug) — walks the frame from scratch; optionally creates the ticketing-tool Epic alongside.
- **Mirror-refresh** — lightweight write of just the mirror block + frontmatter date + Updates Log.

No flags to memorise. Same resolution chain as `/we:saga`.

**When to use:**
- "Where are we on this Epic?" — Status default
- A Saga has been decomposed and the next Epic needs scoping — Create
- A long-running Epic is showing scope drift — Refine after `/we:meet epic`
- A Story has been refined three times and never converged — the real problem is at Epic level, run Status to confirm

**What it produces:**
- `docs/plans/<saga>-<epic>-epic.md`, optionally a ticketing-tool Epic with the same name. The doc contains an auto-generated `## Stories` mirror block.

**Hand-off:** Status footer offers `[r]` refresh, `[f]` Refine, `[m]` `/we:meet epic`, `[s]` `/we:story <KEY>` (recommended next Story), `[q]` done.

**Sizing posture:** no quarter-hard-block. Soft warnings for permanent-category Epics, Saga-in-disguise (child set growing past ~10 with no landings), Story-in-disguise (one obvious AC set), or multi-seam Epics. The user decides; the skill never blocks.

---

### `/we:story`

> *Solo — Product Owner at the Story altitude.*

Produces or sharpens a Story — one sprint-sized feature slice with a build-ready plan. Ticket MINIMAL, plan DETAILED. Interactive — Claude asks, you decide.

**When to use:**
- Starting a new story (most common pipeline entry point)
- Refining an existing ticket that's too vague to implement
- Re-planning after the code drifted from a stale plan

**What it produces:**
- Ticket in your ticketing tool (minimal: user-story format)
- `docs/plans/{TICKET}-story.md` (detailed: context, ACs, phases, design decisions, security review)

**Hand-off:** to `/we:orchestrate` (when you're ready to ship the plan) or `/we:meet story` (when the story is contentious enough to want two perspectives first).

---

## Build altitude skills

### `/we:refine`

> *Write a build-ready plan from front-loaded context, with no user in the room.*

The non-interactive counterpart to `/we:story`: same output file, no Q&A. It writes
`docs/plans/{TICKET}-story.md` and reports the path — no git, no ticket transition, no
self-verification. That shape is deliberate: a refiner runs without Bash, so it works under a
permission mode that denies teammate shell calls, and the Lead stays the only writer of
`docs/plans/` and the only one who runs the DoR scan.

**When to use:**
- Dispatched by `/we:orchestrate` for a story whose context is settled (the common case)
- Standalone when the scope is already decided and you just want the plan written

**Reach for `/we:story` instead** when the scope is genuinely open — that path asks the
questions, sharpens the glossary, and stops at a plan-mode gate.

**Won't do:** ask you anything, guess a design fork (it writes the plan as far as the fork allows, adds an `## Open Fork` section, and stops — `/we:develop` refuses to build past it, `/we:orchestrate` queues it), or claim its own
output passed the gate.

---

### `/we:develop`

> *Dev-only worker slice — implement, gate, commit, push, stop.*

Implements one chunk (a Story, or a `--phases N,M` subset), runs fast local gates (lint/type/affected tests for the touched stack), commits, pushes its branch, and **stops** — no PR, no CI loop, no ticket transition. It's the worker `/we:orchestrate` dispatches, and it works standalone for manual dev work when you want the implementation without the full solo pipeline. Runs an informational AC-check (`we:ac-reviewer`) against its own diff when `review.cross` is on; the bug-hunt runs once, at Lead integration, not per chunk. Branch shape: `feat/{TICKET}-work`.

**When to use:**
- Dispatched by `/we:orchestrate` per chunk (the common case)
- Standalone when you want "just implement and push" without a PR or CI

**Won't do:** open a PR, run CI, transition the ticket — the Lead (`/we:orchestrate`) integrates and runs CI once.

---

### `/we:codex-task`

> *Send a focused task straight to Codex (`gpt-5-codex`).*

Dispatches a single self-contained task to the official Codex plugin runtime (foreground by default; `--background` detaches it). The Lead reviews and integrates the returned diff. Requires the `openai/codex-plugin-cc` plugin; absent it, the plugin is unaffected and workers run on Claude.

---

### `/we:ci-review`

> *Iteratively fix CI and review findings; push only when everything is addressed.*

Runs inline as the last step of the build pipeline, but also standalone. Collects findings from CI failures plus whatever AI reviewers the repo configured in `review.available` on GitHub; triages them; fixes them in one batch; pushes once. Reviewer-agnostic — the bot-thread allowlist is built from `review.available`. On repos without a GitHub AI reviewer, local quality gates serve as the sole review signal.

**When to use standalone:**
- After CI failed on a PR the pipeline didn't open
- After an AI-reviewer pass on a manually-opened PR
- To iterate review fixes without re-running the full pipeline

**What it produces:**
- A single commit with all fixes (per cycle)
- All bot review threads resolved (whichever reviewers are active on the repo)
- A push only after every blocker is addressed

**Limit:** one pass by default; an explicit user budget ("bis merged, max 3 Runden") sets the cycle cap; without one it stops after the first pass and asks — except on a concrete reason (an unsure fix, a flaky check, interdependent findings, a high-stakes PR), where it loops at most twice.

---

### `/we:orchestrate`

> *Multi-chunk build orchestration; the Build-altitude sibling of `/we:council`.*

Boots from state like a colleague — reads each story's state from **git first** (a merged branch outranks a checkpoint nobody wrote), then plans, tickets and the mirror — and on an explicit confirm dispatches **`/we:refine` workers for what has no plan and `/we:develop` workers for what does, in the same wave** (live Agent Team, same machinery as `/we:council`). Workers implement, run fast local gates, commit, and push their branch — no PR, no CI. The **Lead** merges every worker branch onto **one integration branch**, opens **one PR**, and runs **CI once** on the combined diff. It tracks workers in the shared task-list + orchestration DB, reviews the integrated diff, and never merges. Workers run on cheap-tier Claude (Sonnet/Haiku) by default; Codex or a foreign engine are opt-in per chunk. weside MCP optional — the Lead reviews as your Companion when connected, generic role lens otherwise.

**Three dispatch shapes, one pipeline.** Every run ends in the same integration half — simplify, AC+DoD gate, verification, parallel gates, docs, one PR, one CI pass. Only *who implements* differs:

- **Mode A (epic target)** — computes the ready set of buildable Stories and dispatches one worker per ready Story.
- **Mode B (single-Story target)** — runs that one Story's `### Phase` blocks as lead-integrated work-chunks (one worker per phase / parallel wave).
- **`--solo`** — nothing dispatched: the Lead implements the story here, then integrates. For work too small to be worth a worker.

**Six states, one action each.** `shipped` · `integrated` · `built` → INTEGRATE · `refined` →
DEVELOP · `draft`/`idea` → REFINE. First match wins, evidence decides — which is what lets one
epic with mixed maturity move in a single pass instead of needing a flag. Stories that need a
human decision (an open question in the ticket, a frozen interface, contradicting comments) go
to a **Decision Queue** presented as one batch at the wave boundary, not as interruptions.

**Usage:**

```
/we:orchestrate <epic>              # epic target: boot + ready-set; dispatch on confirm (Mode A)
/we:orchestrate <story-key>         # single-Story target: run its phases as work-chunks (Mode B)
/we:orchestrate <story-key> --solo  # single Story, no workers: implement here, then integrate
/we:orchestrate                     # boot from the most recently active epic, then status
```

**When to use:**
- An Epic has several refined Stories ready to build and you want them dispatched together
- One coherent change is split into phases and you'd rather keep your own context clean
- You want one persistent Lead that knows where the Epic stands instead of couriering between sessions

**What it produces:**
- Worker branches merged onto one integration branch → **one PR**, CI run **once**
- A live roll-up (in-flight / PR-ready / blocked) + a Lead review of the integrated diff

**Differs from `/we:epic`:** `/we:epic` gives a read-only Status snapshot; `/we:orchestrate` is the dispatch sibling that actually spawns workers. **Won't do:** merge a PR, close a ticket, or ask whether to run end-to-end — once you've triggered it, run is the answer.

---

## CI / Quality gates (called by the pipeline)

These also run standalone for one-off checks.

### `/we:ac-review`

AC-alignment and DoD check with verdict — dispatched as a background agent (`ac-reviewer`). Never
hunts bugs. It runs per chunk in `/we:develop` (informational) and once at integration (gating). Bug-hunting is separate: Codex adversarial-review when
Claude wrote the code, Claude's native `/code-review` otherwise — runs once, at integration, never
per chunk. See `references/worker-dispatch.md`.

### `/we:pr`

Creates a PR with prerequisite validation. Won't open a PR until all three quality gates have passed checkpoints. Then it links the ticket and attaches the plan. The repo's configured GitHub AI reviewers (`review.available`) review after the PR opens; on other hosts or without a GitHub reviewer, the local quality gates are treated as authoritative.

---

## Deliberation skills

When you need more than one voice on a topic.

### `/we:council`

> *Convene a council of role-lens agents on a topic; orchestrator synthesises.*

The core deliberation mechanic. Opens a live Claude Code Agent Team (one agent per role); members deliberate through `SendMessage` turns in real time; quiescence detection closes the debate; the lead synthesises *agreement / tension / recommendation*. Agents address each other directly rather than writing parallel memos.

Each role-lens is filled by either a generic `council-<role>` agent or a weside-backed Companion (mixed is normal) — `/we:onboarding` decides the mapping, written into `.weside/council.json`. At convene time the `loadCouncilFromWeside` plugin option (default `true`) governs which actually load: `true` resolves to the weside-backed Companions where the bridge links them; `false` convenes every role as a generic lens even if Companions exist.

**Usage:**

```
/we:council "<topic>"                                # default roster from config.json
/we:council "<topic>" --council=architect,product_owner   # explicit roles
/we:council "<topic>" --meeting=vision                 # use a meeting's roster
```

**When to use:**
- A decision affecting multiple domains
- You're stuck between two paths and want lensed perspectives
- A question that benefits from disagreement

**See also:** [concepts/roles.md](concepts/roles.md) (the nine role-lenses), [concepts/companion-framework.md](concepts/companion-framework.md) (how identity is loaded).

---

### `/we:meet`

> *Structured meeting at one of four APO altitudes — vision / saga / epic / story.*

Wraps a council in a workflow tuned to the altitude. Each meeting validates the current artifact and decomposes it into the next altitude's items:

- `/we:meet vision` — PRD altitude, decomposes Vision → Sagas. Hand-off: `/we:vision` to lock the PRD, then `/we:saga` per Saga.
- `/we:meet saga` — Theme altitude, decomposes Saga → Epics. Hand-off: `/we:saga` to lock the SAGA, then `/we:epic` per Epic.
- `/we:meet epic` — Initiative altitude, decomposes Epic → Stories. Hand-off: `/we:epic` to lock the CONCEPT, then `/we:story` per Story.
- `/we:meet story` — Story altitude, sharpens scope and hands off to `/we:story` (Solo) to write the build-ready plan.

**When to use:** when the topic deserves more than a flat council — when you want structure, sequencing, and a named hand-off. The roster defaults are tuned per altitude (widest at Vision, tightest at Story); override per repo in `.weside/config.json` or per call with `--council=role,role,…`. See [concepts/meetings.md](concepts/meetings.md).

---

## Process skills

## Background agents

Skills dispatch agents to do heavy lifting in their own context. You don't invoke these directly, but they appear in the Agent picker:

| Agent | Used by | What it does |
|---|---|---|
| `council-architect` | `/we:council`, `/we:meet` | Architect role-lens |
| `council-product-owner` | `/we:council`, `/we:meet` | PO role-lens |
| `council-scrum-master` | `/we:council`, `/we:meet` | SM role-lens |
| `council-ux-researcher` | `/we:council`, `/we:meet` | UX role-lens |
| `council-orchestrator` | `/we:council`, `/we:meet` | Orchestrator + synthesis |
| `council-marketing` | `/we:council`, `/we:meet` | Marketing role-lens |
| `council-security` | `/we:council`, `/we:meet` | Security role-lens |
| `council-legal` | `/we:council`, `/we:meet` | Legal role-lens |

For the council lenses, see [concepts/roles.md](concepts/roles.md).

---

## References

- [workflow.md](workflow.md) — pipeline overview
- [getting-started.md](getting-started.md) — first-project walkthrough
- [concepts/companion-framework.md](concepts/companion-framework.md) — what `.weside/` adds
- [concepts/meetings.md](concepts/meetings.md) — vision / saga / epic / story meetings
- [mcp.md](mcp.md) — MCP layer + tools
- [troubleshooting.md](troubleshooting.md) — when something doesn't fit
