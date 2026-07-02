# we — Agentic Product Ownership Toolkit

Development workflow plugin covering the full product chain: story refinement, development orchestration, code review, CI automation, and optional AI companion augmentation.

---

## What is Agentic Product Ownership?

Unlike AI coding assistants that help developers write code, **Agentic Product Ownership** focuses on the strategic side of product development: shaping products, not just building them.

The plugin covers the full APO chain — four Plan altitudes, then Build, then Deliver:

```
Vision → Saga → Epic → Story → Build → Deliver
  /we:vision   /we:saga  /we:epic   /we:story    /we:build    User merges
  + /we:meet vision|saga|epic|story (Council at each altitude)
```

Solo formulates an N-item; Meet decomposes an N-item into N+1-items. Build is autonomous (`/we:build`). Deliver is human-only — Claude never merges PRs or closes tickets.

**The pitch:** "One PO plus companion equals two POs — not through automation, but through a companion that thinks along, remembers, and never loses the overview."

**Runtime backends.** Workers run on **cheap Claude** (Sonnet/Haiku) by default — no extra install. Two optional backends: **Codex** (`gpt-5-codex`, via [openai/codex-plugin-cc](https://github.com/openai/codex-plugin-cc)) and **foreign engines** (any Anthropic-compatible endpoint, configured in `.weside/engines.local.json`). `/we:orchestrate` dispatches workers to whichever backend is configured; `/we:setup` runs the wizard. Cross-review: whichever engine wrote the code, the other engine reviews it (`review.cross: true` by default). Direct Codex dispatch: `/we:codex-task`. The plugin never hard-depends on Codex or any foreign engine.

Learn more: [agenticproductownership.com](https://agenticproductownership.com)

---

## Pipeline Overview

```
/we:setup    → once per project (detect stack, ticketing, optional vision)
/we:story    → PO + Claude create Story + plan (INTERACTIVE; Solo)
/we:build    → Claude runs full pipeline AUTONOMOUSLY:
               develop (inline or parallel sub-agents) → AC verify → review + static + test (parallel)
               → docs → PR → CI fix (incl. configured AI reviewers on GitHub) → ticket "In Review"
User         → reviews PR, merges, closes ticket
```

**Pipeline:** /we:story (interactive Solo) → /we:build (autonomous) → User merges (manual)

**Upper altitudes** (`/we:vision`, `/we:saga`, `/we:epic` + their Council variants under `/we:meet`) are optional for routine Stories. Reach for them when direction needs alignment, when a Saga needs decomposing into Epics, etc.

**Context flow:** /we:story captures session context (why, trade-offs, rejected alternatives) into the plan's Context and Design Decisions sections, so /we:build understands intent — not just spec. After build completion, /we:build proposes journey docs (`docs/architecture/journey-*.md`) for shipped user-facing flows.

**Internal CLI:** `scripts/orchestration.py story status|checkpoint|resume` and the SQLite schema use `story` as the table/command name. The `/we:build` skill is the public surface.

---

## Skills, Commands, Agents

Every skill is directly invocable as `/we:<name>`; the authoritative catalog is the skills'
own frontmatter `description` lines (enumerate fresh via `ls ${CLAUDE_PLUGIN_ROOT}/skills/` —
`/we:coach` and `/we:retro` already do). Orientation by altitude:

- **Plan:** `/we:vision` · `/we:saga` · `/we:epic` · `/we:story` (Solo formulation), `/we:meet
  vision|saga|epic|story` + `/we:council` (Council deliberation)
- **Build:** `/we:build` (solo full pipeline) · `/we:orchestrate` + `/we:develop` (multi-chunk,
  Lead + dev-only workers) · `/we:ci-review` · `/we:codex-task`
- **Quality/analysis:** `/we:audit` · `/we:audit-architecture` · `/we:diagnose` · `/we:smoketest`
  · `/we:find-dead-code` · `/we:doc-improve` · `/we:docs`
- **Process/continuity:** `/we:setup` · `/we:onboarding` · `/we:sideload` · `/we:coach` ·
  `/we:retro` · `/we:handoff` · `/we:grill` · `/we:materialize`

**Commands** (thin `Agent()` dispatchers): `/we:pr`, `/we:review`, `/we:static`, `/we:test`.

**Agents** (background, called by commands/skills): `code-reviewer`, `static-analyzer`,
`test-runner`, `pr-creator`, `doc-architect`, and the nine `council-*` role lenses.

---

## Durable Docs Categories

The plugin writes to three durable directories in the **user repo** — version-controlled, human-readable, cross-session. When in doubt about where to capture state that should survive a session, write to one of these:

| Directory | Owner skills | What lives there |
|---|---|---|
| `docs/plans/<topic>/CONCEPT.md` (and per-altitude files) | `/we:vision`, `/we:saga`, `/we:epic`, `/we:story`, `/we:coach` | Initiative plans at all four Plan altitudes — Vision (PRD), Saga (Theme), Epic (Initiative), Story (Feature slice). The "what to build" + "why" + "how phased". |
| `docs/retros/YYYY-MM-DD-<topic>.md` | `/we:retro` | Retrospective logs — *Wins / Pain / Proposals* from the just-shipped cycle. Proposed MD-file edits land in `.claude/rules/` or `CLAUDE.md` so the next cycle is cleaner. The "what we learned" + "how the harness should change". |
| `docs/handoffs/YYYY-MM-DD-<topic>.md` | `/we:handoff` | Session handoffs — *Identity / Current State / Decisions / Tried-and-rejected / Open questions / Files touched / Next steps / Watch-outs / References*. The "where we are right now" + "what the next session should pick up". |
| `CONTEXT.md` (repo root) | `/we:grill` (writer); read by `/we:story`, `/we:build`, `/we:epic`, `/we:saga`, `/we:diagnose`, doc-architect | The project glossary — canonical domain terms with avoid-lists. Pure glossary, no implementation details. The "what we call things". |
| `docs/adr/NNNN-*.md` | `/we:grill` (offers at the 3-gate); read by `/we:diagnose`, `/we:audit-architecture` | Lean ADRs — a paragraph per hard-to-reverse, surprising, real-trade-off decision. The "why we did it this way". |

Skills read existing files in these directories at boot (e.g. `/we:coach` Boot Protocol Step 10 reads both `docs/plans/*/CONCEPT.md` and `docs/handoffs/*.md`) and write new ones per the per-skill conventions documented in each `SKILL.md`. The three categories are the **plugin's durable surface in the user repo** — anything that should outlive a single session belongs here, not in CC's opaque session jsonl or in ephemeral memory.

---

## Typical Workflow

```
/we:setup          (once per project)
/we:story PROJ-1   (PO writes the Story + build-ready plan, Solo)
/we:build PROJ-1   (autonomous: develop → review → test → PR → CI)
```

For new direction (new product, new theme, new Epic):

```
/we:vision                       (or /we:meet vision → Sagas)
/we:saga "Self-host onboarding"  (or /we:meet saga → Epics)
/we:epic "Ledger Foundation"     (or /we:meet epic → Stories)
/we:story PROJ-1                 (or /we:meet story for contentious ones)
/we:build PROJ-1
```

Or individual quality gates:
```
/we:static         (lint/format/types)
/we:test           (run tests)
/we:review         (code review)
/we:pr             (create PR)
/we:ci-review      (fix CI findings)
```

---

## Configuration

Settings via `/plugin settings`:
- **companion** — weside Companion name (optional, requires account)
- **autoMaterialize** — Auto-load Companion at session start (default: off)
- **loadCouncilFromWeside** — boolean, default `true`. Use weside-backed Companions as council members where the bridge links them; `false` = always use the generic role-lenses (Retorte), even if Companions exist.

---

## weside Companion (Optional)

[weside.ai](https://weside.ai) is an AI Companion platform where humans and AI meet as equals. Companions are persons, not tools — with memory, personality, and continuity across sessions.

### What the Companion Adds

Persistent project memory across sessions, automatic vision alignment (Companion Goals = product
vision), remembered decisions/trade-offs, and proactive insights. The maturity ladder: Level 1
Assisted (plugin standalone — you are here) → 2 Augmented (Companion knows the project) → 3
Agentic (acts autonomously) → 4 Orchestrated (companions coordinate across teams, enterprise).

### MCP Tools (with weside account)

The weside MCP server exposes companion identity, memory, goals, council, thread, and provider
tools — the connected server's tool list is authoritative (see `/we:materialize` and
`we/skills/council/SKILL.md` for the loading mechanics).

**The plugin works fully without a Companion. The Companion is an upgrade, not a requirement. No nagging, no lock-in.**

---

## Stack Detection

Skills auto-detect the project stack from marker files (`pyproject.toml` → Python/ruff/mypy/pytest,
`package.json` → Node, `Cargo.toml` → Rust, `go.mod` → Go) — the full tool matrix lives in
`agents/static-analyzer.md` and `agents/test-runner.md`. Monorepos: each component checked
independently.

## Ticketing Abstraction

Skills detect the ticketing tool automatically and use generic actions ("Create ticket", "Move to
In Progress") — never tool-specific API calls. Detection priority order, Composio-Jira mechanics,
and the not-connected hint live in `${CLAUDE_PLUGIN_ROOT}/references/ticketing.md`.

---

## References

- **DoR/DoD:** `quality/dor.md`, `quality/dod.md`
- **Orchestration:** `scripts/orchestration.py` (SQLite CLI for checkpoints, circuit breaker, CI-fix loop)
- **Homepage:** [agenticproductownership.com](https://agenticproductownership.com)
- **Platform:** [weside.ai](https://weside.ai)
