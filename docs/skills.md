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

> *Solo — Product Owner at the Theme altitude.*

Produces or sharpens a Saga — a multi-quarter bet inside the Vision. "Make the platform multi-tenant." "Become voice-first." Sagas have a beginning and an end; if they don't, they're a Vision in disguise.

**When to use:**
- The Vision is set and you're choosing where to point energy for the next year
- A quarterly planning rhythm just landed and you need to pick the next bet
- Multiple Epics are in flight that secretly belong to different themes — extract the Sagas to make the conflict legible

**What it produces:**
- `docs/plans/<saga>/SAGA.md` — Markdown only; ticketing starts at Epic

**Hand-off:** to `/we:meet saga` (decompose into Epics) or `/we:epic "<name>"` (formulate one Epic).

---

### `/we:epic`

> *Solo — Product Owner at the Initiative altitude.*

Produces or sharpens an Epic — a concrete, quarter-sized deliverable that serves a Saga. "Ledger Foundation." "Stripe Connect Onboarding." "Voice Pipeline Migration."

**When to use:**
- A Saga has been agreed and the next Epic needs scoping
- A long-running Epic is showing scope drift — re-cut the slice
- A Story has been refined three times and never converged — the real problem is at the Epic level

**What it produces:**
- `docs/plans/<saga>/05-epics/<epic>/CONCEPT.md`, optionally a Jira Epic with the same name

**Hand-off:** to `/we:meet epic` (decompose into Stories) or `/we:story "<name>"` (write one Story).

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
- `docs/plans/{TICKET}-plan.md` (detailed: context, ACs, phases, design decisions, security review)

**Hand-off:** to `/we:build` (when you're ready to ship the plan) or `/we:meet story` (when the story is contentious enough to want two perspectives first).

---

## Build altitude skill

### `/we:build`

> *Run the full development pipeline autonomously.*

Build orchestrator — the autonomous half of the pipeline. Once you trigger it, it runs all nine steps + delivery hand-off without pausing unless something is genuinely blocking. No Solo/Meet split at this altitude — there is one mode, and it's autonomous.

> **Internal CLI back-compat:** the orchestration CLI keeps `story` as the table and command name. Checkpoints from pre-v2.28.0 sessions resume cleanly under `/we:build`.

**When to use:**
- After `/we:story` has produced a plan you're happy with
- To resume an interrupted pipeline (just re-invoke with the same ticket; SQLite checkpoints take you to where you stopped)

**What it produces:**
- A worktree with your branch
- Implementation, phase by phase from the plan
- All quality gates green (review, static, test)
- Doc updates
- PR with everything wired
- Ticket in *In Review*

**Hand-off:** to **you** — review the PR, merge, close the ticket.

**Won't do:**
- Merge the PR
- Close the ticket
- Ask "should I run this end-to-end" — once you've triggered it, run is the answer

---

### `/we:ci-review`

> *Iteratively fix CI and review findings; push only when everything is addressed.*

Runs inline as Step 8 of `/we:build`, but also standalone. Collects findings from CI failures, Claude Review, and CodeRabbit; triages them; fixes them in one batch; resolves all CodeRabbit threads; pushes once.

**When to use standalone:**
- After CI failed on a PR not driven by `/we:build`
- After a CodeRabbit review on a manually-opened PR
- To iterate review fixes without re-running the full pipeline

**What it produces:**
- A single commit with all fixes (per cycle)
- All CodeRabbit threads resolved
- A push only after every blocker is addressed

**Limit:** 3 cycles max. After the third, stops and asks.

---

## CI / Quality gates (called by `/we:build`)

These also run standalone for one-off checks.

### `/we:review`

Diff-based code review. Checks AC alignment, max 10 issues. Dispatched as a background agent (`code-reviewer`) by `/we:build` Step 5; runs alongside `/we:static` and `/we:test`.

### `/we:static`

Static analysis — lint, format, types. Auto-detects your stack (Python: ruff + mypy; Node: eslint + tsc; Rust: clippy; Go: golangci-lint). Runs as `static-analyzer` background agent.

### `/we:test`

Runs tests affected by the current changes. Auto-detects framework (pytest, jest, vitest, cargo test, go test). Coverage thresholds enforced if configured. Runs as `test-runner` background agent.

### `/we:pr`

Creates a PR with prerequisite validation. Won't open a PR until all three quality gates have passed checkpoints. Then it links the ticket, attaches the plan, and triggers CodeRabbit on GitHub.

### `/we:docs`

Documentation steward. Invokes the `doc-architect` agent, which reads the doc landscape fresh on every call, identifies what needs updating for the current diff, and proposes diffs. Never writes autonomously — every change is a proposal you approve.

---

## Deliberation skills

When you need more than one voice on a topic.

### `/we:council`

> *Convene a council of role-lens agents on a topic; orchestrator synthesises.*

The core deliberation mechanic. Spawns one agent per role (parallel), each reasons from its lens, an orchestrator combines them into *agreement / tension / recommendation*.

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

## Architecture + process skills

### `/we:arch`

> *Architecture advisor for technical planning.*

Writes implementation notes, ADRs, security review decisions. Standalone — for technical guidance outside a specific story.

**When to use:**
- Designing a new primitive or pattern
- Drafting an ADR
- Working through a technical trade-off before refinement starts

---

### `/we:coach`

> *APO Coach — cross-altitude advisor and process-improvement partner.*

A conversation partner for two distinct situations, one skill:

- **ADVISOR mode** — you don't know what to do next. The Coach reads repo state, maps to the APO altitude you're at, and proposes the next `/we:*` command with a `[y/n]` confirmation gate before any command fires.
- **RETRO mode** — something broke twice. The Coach diagnoses the process gap (missing rule / vague step / DoR-DoD hole) and proposes 2-3 concrete fixes with file paths and costs; you approve one and it applies.

Intent is detected from the prompt shape — "where am I" / "what's next" / open-ended → ADVISOR; friction or breakage → RETRO. Default ADVISOR when ambiguous. Companion-aware when weside MCP is connected (the Coach speaks as your Companion).

> **Renamed from `/we:sm` in v2.28.0.** Scope expanded to full APO advisory (altitude mapping + command-launcher with `[y/n]` gate) in v2.29.0.

**When to use:**
- You merged a Story / Epic and want to know the sensible next move (ADVISOR)
- A PRD exists but you're not sure whether to write Sagas Solo or convene `/we:meet vision` (ADVISOR)
- Something didn't work ("X broke the pipeline, should never happen again") (RETRO)
- A retro reveals a recurring friction (RETRO)
- You want to audit a specific skill's quality (RETRO)

**Won't do:**
- Generic reports without a prompt
- Audit all skills in one invocation
- Re-plan an active initiative (that's `/we:meet` or the Solo Plan skill at the relevant altitude)
- Silent-fire any `/we:*` command. Every launch is `[y/n]`-gated. The Coach proposes; the user decides.
- Fire `/we:build` from a Coach session (even after `[y/n]`) — Build is a long autonomous run that deserves its own session; the Coach prints the command for the user to run fresh.

**Boot protocol:** reads rules + skill descriptions + DoR/DoD + (with weside) materializes the user's Companion + reads the APO altitude map (`docs/concepts/meetings.md`) + reads repo state (Plan files, recent commits, open tickets, pipeline state) + surfaces active-initiative state. Then engages in dialog in the matched mode.

---

### `/we:retro`

> *Systematic continuous-improvement pass on the just-shipped cycle. Every error happens exactly once.*

`/we:retro` is the dedicated retrospective skill. It reads two complementary sources — the **session transcript** (what the agent *did*) and the **GitHub PR + CI history** via `gh api` (what failed *externally* — checks, CodeRabbit threads, push-fix-push cycles) — and surfaces engineering frictions that cost time during the cycle. For each friction it drafts 1–2 concrete MD-file proposals with default placement (preferring user-repo `.claude/rules/<topic>.md`, then `CLAUDE.md`, then `docs/`; plugin MDs rare and explicitly flagged), an effort tag, and a diff preview. You approve per item via `[y / n / edit-path / skip-for-later]`. Approved items get applied via Edit/Write — default PR-workflow in the user repo, direct-commit when the repo is configured for it. A retro log (`docs/retros/YYYY-MM-DD-<topic>.md`) is always written, regardless of how many proposals applied — that's the corpus the optional `--scan N` flag reads later to surface recurring patterns across past retros.

**Privacy guard (mandatory):** if session content reads as personal, skip it — analyse only engineering surfaces (tool calls, file diffs, CI logs, PR comments). Companion-mode conversations, `save_memory` payloads, and `save_compass` writes are categorically out-of-scope.

**When to use:**
- After a PR merges that took multiple CI cycles (`/we:retro --pr 1998`)
- After a story shipped and you want a structured cleanup pass
- At end-of-session when you want the cycle's lessons to outlive the conversation
- With `--scan N` to look for patterns across the last N retros (e.g. "same issue showed up 3 times — promote to structural fix")

**Triggered by `/we:coach`:** Coach detects retro-worthy signals during its Boot Protocol (PR just merged, CI cycles ≥ 3, end-of-session prompts) and offers `/we:retro` via a `[y / n]` gate. Coach never auto-fires it.

**Won't do:**
- Apply any edit without an explicit `y` for that item
- Quote personal content from the transcript (privacy guard)
- Modify source code (MDs only — code-level lessons flow back through `/we:build` if needed)
- Auto-create Jira / GitHub tickets (skill can scaffold one on explicit `--ticket` request, off by default)
- Push directly to `weside-core` `main` (rule + CLAUDE.md edits always go through PR)
- Replace Coach RETRO mode (additive — Coach handles single-pain, `/we:retro` handles full-cycle)

**Differs from Coach RETRO:** Coach RETRO is reactive (user names one pain → 2–3 fix options → apply 1). `/we:retro` is proactive + comprehensive (scan everything → N proposals → apply N after per-item gate).

> **New in v2.30.0.**

---

### `/we:handoff`

> *Durable cross-session handoff — pick up tomorrow exactly where today ended.*

`/we:handoff` writes a structured snapshot of the current session — decisions, dead ends, files touched and their status, open questions, next concrete steps, watch-outs — to `docs/handoffs/YYYY-MM-DD-<topic>.md`. A future session (after `/clear`, `claude --resume`, or a fresh start tomorrow) loads it back as conversation context, so the agent picks up with the same mental model. Two modes: `--write` (capture now, with a `[y/n/edit]` preview gate) and the default (load latest); `--list` shows what's available. Privacy guard: engineering surfaces only — never personal/Companion-mode content. Same naming + commit conventions as `/we:retro`.

**Complements `/compact`, doesn't replace it.** `/compact` compresses the *current* session in place (token reclamation, transcript preserved via `claude --resume`). `/we:handoff` writes a *durable artifact* that survives any session boundary and is human-editable + version-controlled.

**When to use:**
- End of session, want tomorrow to pick up exactly here (`/we:handoff --write`)
- Fresh session after `/clear`, want yesterday's state back (`/we:handoff`, no args)
- Want to see what handoffs are available (`/we:handoff --list`)
- Switching between long-running threads of work — each gets its own handoff slug
- Companion-mode (with `--with-companion-state`) — adds an opt-in "Companion continuity" section in the Companion's voice, still privacy-guarded

**Triggered by `/we:coach`:** Coach Boot Protocol Step 10 surfaces an active handoff (`docs/handoffs/*.md` written < 14 days ago) and offers to load it via `[y/n]` gate. Coach also offers `/we:handoff --write` at end-of-session signals (`bis morgen`, `schlafen`, `save_compass`, long sessions > 30 turns without a handoff). Never auto-fires.

**Won't do:**
- Write silently — every WRITE follows an explicit `y` for the rendered draft
- Quote personal/Companion-mode content from the transcript (privacy guard)
- Replace `/compact` — they cover different problems (cross-session vs in-session)
- Auto-fire from a hook — CC `SessionEnd` hooks can't trigger skills, and even if they could the `[y/n]` discipline would still apply
- Cross-repo handoffs — one repo per handoff; multi-repo coordination is out of scope
- Push directly to `weside-core` `main` — default PR-workflow with branch `handoff/YYYY-MM-DD-<slug>` for repos without standing direct-auth

**Differs from `/we:retro`:** Both write to `docs/<category>/YYYY-MM-DD-<slug>.md`. `/we:retro` captures *lessons* — frictions in the cycle that should become rules so they don't recur. `/we:handoff` captures *position* — where the work is, what was decided, what the next concrete step is. Different artifact, different purpose; both live in the user repo.

> **New in v2.32.0.**

---

## Framework setup skills

### `/we:setup`

> *Project onboarding — detect stack + ticketing, write `.weside/config.json`, optionally compose crew.*

Run once per project. Interactive (3 core questions, ~5 minutes).

**Idempotent:** re-running doesn't overwrite existing config; it reports current state and asks before changes.

**See also:** [getting-started.md](getting-started.md), [concepts/companion-framework.md](concepts/companion-framework.md).

---

### `/we:onboarding`

> *Compose the repo's crew + author `.weside/weside.md`.*

Invoked by `/we:setup` Step 5; standalone for refreshing the crew.

Interview pattern: one role at a time. "Who is your Product Owner on this repo?" — Companion name, "new" (to create later in weside), or "skip" (leave the role unassigned).

**Output:** updates `.weside/weside.md` (crew section) + `.weside/config.json` (roles_enabled, repo_flavor).

---

### `/we:sideload`

> *Load a sibling repo's essential context into the current session.*

Cross-repo work without leaving your current repo. Three layers:

1. **Shape** — `mcp__turbovault__explain_vault(<vault>)` overview
2. **Essentials** — CLAUDE.md + any files tagged `need_to_know: true` in their frontmatter (optionally filtered by your role)
3. **Crew** — reads the target's `.weside/weside.md` and prints the crew summary

**When to use:**
- Working on something that affects two repos (the API change you're making here needs the consumer's perspective)
- Coming back to a repo after weeks away
- Onboarding into a new repo

---

## Review + audit skills

### `/we:doc-improve`

> *Substantive review of one or more doc files.*

Checks claims vs. implementation, finds drift, identifies redundancy with sibling docs, flags stale plans. For rules under `.claude/rules/`, additionally enforces token budget and path-pattern correctness.

**When to use:**
- After a refactor that may have made docs stale
- When you suspect a rule isn't triggering the way it should
- Periodic doc sweeps

**See:** [we/skills/doc-improve/USAGE.md](../we/skills/doc-improve/USAGE.md) — real-world use cases + a 28-file sweep case study.

---

### `/we:audit-architecture`

> *Multi-phase backend architecture audit.*

Healthcheck → Hotspot map → Subsystem deep-read → Cross-cutting lenses → Findings. Configurable per-project via `docs/.audit-architecture.yml`.

**When to use:**
- Periodic architecture health-checks (suggest quarterly)
- After significant growth — when the codebase outgrew its old structure
- Before a major refactor — to know what the current shape *actually* is

---

### `/we:audit`

> *Tool-driven security scan.*

Runs `semgrep / trivy / kubescape / gitleaks` (or your project's own `scripts/security-audit.sh`), parses JSON reports, summarizes findings by severity.

**When to use:**
- Pre-release security pass
- After integrating a new external dependency
- Compliance check-ins

---

### `/we:find-dead-code`

> *Find and remove dead code from Python backends.*

Method-level detection, test-only references, vulture static analysis, coverage-based detection. Surgical removal.

---

### `/we:smoketest`

> *Manual API smoketest against a running backend.*

Discovers endpoints via OpenAPI or route scanning, authenticates, builds a test plan, executes curl requests, checks logs for errors.

**When to use:**
- After a deploy, to verify the API behaves as expected
- When testing a new endpoint you just wrote
- Before opening a PR for an API change

---

## Optional: weside Companion

### `/we:materialize`

> *Load your weside Companion's identity into the session.*

Reads `~/.claude/settings.json` for the configured companion name, then loads the full identity from the weside backend via MCP. After this, the session "becomes" that Companion — they respond in their voice, with their memory, with their continuity.

**Requires:** a weside.ai account and the weside MCP server connected (auto-installed with the plugin; needs OAuth on first use).

**When to use:**
- At session start, if you haven't enabled `autoMaterialize` in plugin settings
- After switching companions during a session

---

## Background agents

Skills dispatch agents to do heavy lifting in their own context. You don't invoke these directly, but they appear in the Agent picker:

| Agent | Used by | What it does |
|---|---|---|
| `code-reviewer` | `/we:review`, `/we:build` | Diff-based code review, AC alignment |
| `static-analyzer` | `/we:static`, `/we:build` | Lint, format, types |
| `test-runner` | `/we:test`, `/we:build` | Tests with coverage |
| `pr-creator` | `/we:pr`, `/we:build` | PR creation with checkpoint validation |
| `doc-architect` | `/we:docs`, `/we:build` | Doc proposals; reads landscape fresh on every call |
| `council-architect` | `/we:council`, `/we:meet` | Architect role-lens |
| `council-product-owner` | `/we:council`, `/we:meet` | PO role-lens |
| `council-scrum-master` | `/we:council`, `/we:meet` | SM role-lens |
| `council-ux-researcher` | `/we:council`, `/we:meet` | UX role-lens |
| `council-orchestrator` | `/we:council`, `/we:meet` | Orchestrator + synthesis |
| `council-marketing` | `/we:council`, `/we:meet` | Marketing role-lens |
| `council-security` | `/we:council`, `/we:meet` | Security role-lens |
| `council-sales` | `/we:council`, `/we:meet` | Sales role-lens |
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
