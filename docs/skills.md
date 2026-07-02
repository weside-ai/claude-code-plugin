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

- **Status** (default) — read `SAGA.md`, mirror child Epics from the ticketing tool, render snapshot + drift detection + risk-driven next-move recommendation. Read-only.
- **Refine** (explicit intent: "refine" / "update" / "sharpen") — walks the four frame questions, drafts a tightened `SAGA.md` via plan-mode.
- **Create** (slug doesn't exist yet) — walks the frame from scratch.
- **Mirror-refresh** (intent: "refresh" / "sync" / "mirror") — lightweight write of just the mirror block + frontmatter date + Updates Log.

No flags to memorise. Target Saga is resolved from explicit argument → branch name → PWD → most-recent draft/active doc → ask one question.

**When to use:**
- "Where are we on this Saga?" — Status default; the 90%-case
- The Vision is set and you're choosing where to point energy next — Create
- A long-running Saga showing drift — Refine after a `/we:meet saga` Council
- Multiple Epics in flight that secretly belong to different themes — surface them by running Status across each candidate

**What it produces:**
- `docs/plans/<saga>/SAGA.md` — Markdown only; ticketing starts at Epic. The doc contains an auto-generated `## Sub-Epics` mirror block between `<!-- mirror:start --> … <!-- mirror:end -->` markers.

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

**Hand-off:** to `/we:build` (when you're ready to ship the plan) or `/we:meet story` (when the story is contentious enough to want two perspectives first).

---

## Build altitude skill

### `/we:build`

> *Run the full development pipeline autonomously.*

Build orchestrator — the autonomous half of the pipeline. Once you trigger it, it runs all nine steps + delivery hand-off without pausing unless something is genuinely blocking. No Solo/Meet split at this altitude — there is one mode, and it's autonomous.

> **Internal CLI back-compat:** the orchestration CLI keeps `story` as the table and command name. Interrupted builds always resume cleanly when re-invoked.

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

Runs inline as Step 8 of `/we:build`, but also standalone. Collects findings from CI failures plus whatever AI reviewers the repo configured in `review.available` on GitHub; triages them; fixes them in one batch; pushes once. Reviewer-agnostic — the bot-thread allowlist is built from `review.available`. On repos without a GitHub AI reviewer, local quality gates serve as the sole review signal.

**When to use standalone:**
- After CI failed on a PR not driven by `/we:build`
- After an AI-reviewer pass on a manually-opened PR
- To iterate review fixes without re-running the full pipeline

**What it produces:**
- A single commit with all fixes (per cycle)
- All bot review threads resolved (whichever reviewers are active on the repo)
- A push only after every blocker is addressed

**Limit:** 3 cycles max. After the third, stops and asks.

---

### `/we:orchestrate`

> *Spike — Epic-driven build orchestration; the Build-altitude sibling of `/we:council`.*

Boots from state like a colleague — reconstructs where an Epic stands from its plans, `epic:` frontmatter, the ticketing mirror, and the orchestration build-state — computes the ready set of buildable Stories, and on an explicit confirm dispatches one builder-teammate per ready Story (live Agent Team, same machinery as `/we:council`). Each builder runs the full unmodified `/we:build`; the Lead tracks them in the shared task-list + orchestration DB, reviews each finished PR, and never merges. weside MCP optional — the Lead reviews as your Companion when connected, with a generic role lens otherwise.

> **Spike status.** Hard cap of **≤2 concurrent builders**; the full orchestrator (parallel dispatch beyond 2, cross-Story circuit breakers, resume) is gated on this spike's go/no-go.

**Usage:**

```
/we:orchestrate <epic>              # boot + status + ready-set; dispatch only on confirm
/we:orchestrate <epic> --rehearsal  # run the pipeline against a fixture, no real PR/ticket
/we:orchestrate                     # boot from the most recently active epic, then status
```

**When to use:**
- An Epic has several refined Stories ready to build and you want them dispatched in parallel
- You want one persistent Lead that knows where the Epic stands instead of couriering between sessions
- `--rehearsal` — shake out skill friction against a fixture before a real run

**What it produces:**
- Up to 2 builder sessions, each running `/we:build` to a reviewable PR
- A live roll-up (in-flight / PR-ready / blocked / held-by-cap) + a Lead review per PR

**Differs from `/we:epic`:** `/we:epic` gives a read-only Status snapshot; `/we:orchestrate` is the dispatch sibling that actually spawns builders. **Won't do:** merge a PR, close a ticket, or exceed the ≤2 cap.

---

## CI / Quality gates (called by `/we:build`)

These also run standalone for one-off checks.

### `/we:review`

Diff-based code review, max 10 issues. Dispatched as a background agent (`code-reviewer`) alongside `/we:static` and `/we:test`. In `/we:build` Step 5 it runs only when Claude did not hand the review to `/codex:adversarial-review` (writer-aware single-reviewer rule), and AC + DoD were already gated in Step 3 — so inside the pipeline it reviews for bugs/security/design. Run directly via `/we:review` (no gate ahead of it), it does the full review including AC alignment and the DoD Quick Check.

### `/we:static`

Static analysis — lint, format, types. Auto-detects your stack (Python: ruff + mypy; Node: eslint + tsc; Rust: clippy; Go: golangci-lint). Runs as `static-analyzer` background agent.

### `/we:test`

Runs tests affected by the current changes. Auto-detects framework (pytest, jest, vitest, cargo test, go test). Coverage thresholds enforced if configured. Runs as `test-runner` background agent.

### `/we:pr`

Creates a PR with prerequisite validation. Won't open a PR until all three quality gates have passed checkpoints. Then it links the ticket and attaches the plan. The repo's configured GitHub AI reviewers (`review.available`) review after the PR opens; on other hosts or without a GitHub reviewer, the local quality gates are treated as authoritative.

### `/we:docs`

Documentation steward. Invokes the `doc-architect` agent, which reads the doc landscape fresh on every call, identifies what needs updating for the current diff, and proposes diffs. Never writes autonomously — every change is a proposal you approve.

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

### `/we:map`

> *Plan-tree dashboard — type one thing, see the whole landscape.*

A fast, read-only text overview of everything in flight: every Saga, its Epics, and the Stories under each, with status buckets (Done / Active / Refined / Backlog / Blocked). Scans `docs/plans/` by filename suffix (`*-saga.md`, `*-epic.md`, `*-story.md`), groups stories under epics via the `epic:` frontmatter and epics under sagas via the `saga:` prefix, joins build-pipeline phase from the orchestration DB (`orchestration.py story list`), and optionally live ticket status. No nested directories, no separate index — the filename suffix is the altitude marker; the saga-slug prefix is the grouping.

**When to use:**
- You want the bird's-eye view across ALL Sagas/Epics/Stories at once (`/we:map`)
- You want one Saga's full subtree expanded to story level (`/we:map presence`)
- You want to locate a ticket in the tree (`/we:map PROJ-1206`)

**Differs from `/we:saga` / `/we:epic`:** those render a *deep* Status dashboard for ONE artifact (drift, next-move). `/we:map` is the *wide, shallow* view across all artifacts — the bird's eye. It hands off to `/we:saga <slug>` or `/we:epic <slug-or-key>` for detail.

**Won't do:**
- Write any file — strictly read-only, no plan-mode
- Invoke another skill inline — prints the hand-off commands, the user picks
- Block on a missing ticketing tool or orchestration DB — degrades to frontmatter status

**Transition-tolerant:** also picks up legacy `*-plan.md` stories and `*/CONCEPT.md` nested epics during the suffix migration, flagging them with `~` so you see what still needs renaming.

---

### `/we:coach`

> *APO Coach — cross-altitude advisor and onboarding partner.*

A conversation partner for three situations, one skill:

- **ADVISOR mode** — you don't know what to do next. The Coach reads repo state, maps to the APO altitude you're at, and proposes the next `/we:*` command with a `[y/n]` confirmation gate before any command fires. If an open Saga or Epic is detected, ADVISOR also surfaces a one-line Plan-status — and delegates the detail to `/we:saga` or `/we:epic` (which both run a full Status dashboard as their default mode).
- **BEGINNER mode** — you're new to APO or the plugin. The Coach walks you through the four-altitude workflow, checks whether `.weside/config.json` exists, and proposes a sensible starting command. Triggered by "I'm new" / "what is this" / first-session markers.
- **Process-improvement front door (Scrum-Master)** — you want to *discuss or improve* how we work — a skill, the pipeline, the method — not report a specific breakage. The Coach engages a grounded discussion (from the `how-we-work.md` method it loaded at boot) and routes to `/we:retro` (a systematic pass) or `/we:story` (spec the change). Triggered by "how could we improve…", "let's rethink…", "discuss the workflow".

Intent is detected from the prompt shape — "where am I" / "what's next" / open-ended / "which Epics" / "status" → ADVISOR; "I'm new" / "help me start" → BEGINNER. Default ADVISOR when ambiguous. Companion-aware when weside MCP is connected (the Coach speaks as your Companion).

> **Renamed from `/we:sm`.** Scope expanded to full APO advisory, RETRO mode extracted to standalone `/we:retro`, Beginner mode added, and Plan-status detail delegated to `/we:saga` / `/we:epic` (Status-default modes) — Coach renders only the one-line snapshot.

**When to use:**
- You merged a Story / Epic and want to know the sensible next move (ADVISOR)
- A PRD exists but you're not sure whether to write Sagas Solo or convene `/we:meet vision` (ADVISOR)
- You're coming to the plugin for the first time or returning after a long gap (BEGINNER)
- You want a structured summary of which Sagas / Epics are in flight (ADVISOR — Coach surfaces the one-liner and points you to `/we:saga` or `/we:epic` for the full Status dashboard)

**Won't do:**
- Generic reports without a prompt
- Audit all skills in one invocation
- Re-plan an active initiative (that's `/we:meet` or the Solo Plan skill at the relevant altitude)
- Silent-fire any `/we:*` command. Every launch is `[y/n]`-gated. The Coach proposes; the user decides.
- Fire `/we:build` from a Coach session (even after `[y/n]`) — Build is a long autonomous run that deserves its own session; the Coach prints the command for the user to run fresh.
- Handle post-PR engineering-friction analysis — that's `/we:retro`

**Boot protocol:** reads rules + skill descriptions + DoR/DoD + (with weside) materializes the user's Companion + **self-grounds in the method via the [`how-we-work.md`](concepts/how-we-work.md) manifest** (APO altitudes, pipeline, skill catalog — the same manifest `/we:retro` loads) + reads repo state (Plan files, recent commits, open tickets, pipeline state) + surfaces active-initiative state. Then engages in dialog in the matched mode.

---

### `/we:retro`

> *Systematic continuous-improvement pass on the just-shipped cycle. Every error happens exactly once.*

`/we:retro` is the dedicated retrospective skill. It reads two complementary sources — the **session transcript** (what the agent *did*) and the **GitHub PR + CI history** via `gh api` (what failed *externally* — checks, review-bot threads, push-fix-push cycles) — and surfaces engineering frictions that cost time during the cycle. For each friction it drafts 1–2 concrete MD-file proposals with default placement (preferring user-repo `.claude/rules/<topic>.md`, then `CLAUDE.md`, then `docs/`; plugin MDs rare and explicitly flagged), an effort tag, and a diff preview. You approve per item via `[y / n / edit-path / skip-for-later]`. Approved items get applied via Edit/Write — default PR-workflow in the user repo, direct-commit when the repo is configured for it. A retro log (`docs/retros/YYYY-MM-DD-<topic>.md`) is always written, regardless of how many proposals applied — that's the corpus the optional `--scan N` flag reads later to surface recurring patterns across past retros.

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
- Push without PR review — rule + CLAUDE.md edits always go through a PR in repos without explicit direct-commit config

**Differs from `/we:coach`:** Coach ADVISOR reads repo state and proposes the next `/we:*` command. `/we:retro` proactively scans the full PR + CI cycle and proposes concrete engineering rule fixes — a different artifact with a different purpose.

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
- Push without PR review — default PR-workflow with branch `handoff/YYYY-MM-DD-<slug>` for repos without direct-commit config

**Differs from `/we:retro`:** Both write to `docs/<category>/YYYY-MM-DD-<slug>.md`. `/we:retro` captures *lessons* — frictions in the cycle that should become rules so they don't recur. `/we:handoff` captures *position* — where the work is, what was decided, what the next concrete step is. Different artifact, different purpose; both live in the user repo.

---

## Framework setup skills

### `/we:setup`

> *Project onboarding — detect stack + ticketing, write `.weside/config.json`, optionally compose crew.*

Run once per project. Interactive (4 core questions, ~5 minutes) — vision, ticketing, stack, and which code reviewers the repo uses (the ordered `review.available` list, free-text-extendable; put your preferred local reviewer first, and the order also seeds the CI-bot allowlist `/we:ci-review` reads).

**Idempotent:** re-running doesn't overwrite existing config; it reports current state and asks before changes.

**See also:** [getting-started.md](getting-started.md), [concepts/companion-framework.md](concepts/companion-framework.md).

---

### `/we:onboarding`

> *Build the repo's council from scratch + author `.weside/weside.md`.*

Invoked by `/we:setup` Step 5; standalone for rebuilding the crew. Works with zero Companions, no `.weside/`, and no weside account.

Guided council builder: for each role it offers three ways to fill the lens — **assign** an existing Companion (links it by id; the lens reaches it via the council brief, no identity edit), **create** a new Companion seeded with the role-lens + a neutral personality starter (via `create_companion`), or **generic** (the shipped `council-<role>` agent — the "Retorte" lens, free, no account, no plan-limit). A mixed council is normal. weside-backed members each cost a `plan.max_companions` slot; when the plan limit (Spark 1, Bond 3, Companion 5, Soulmate/Mascot unlimited) runs out, the remaining roles degrade gracefully to generic lenses plus an upgrade CTA — never stuck.

**Output:** writes the full `.weside/council.json` thin bridge (envelope + a `members` entry per role, gitignored) + updates `.weside/weside.md` (crew section) + `.weside/config.json` (roles_enabled, repo_flavor).

---

### `/we:sideload`

> *Load a sibling repo's full context into the current session. A stopgap — prefer a native session in the target repo when you can.*

Cross-repo work without leaving your current repo. A main agent rooted in the wrong repo never receives path-filtered rules from the harness, so sideload compensates by loading everything eagerly. Three layers:

1. **Shape** — `mcp__turbovault__explain_vault(<vault>)` overview
2. **Essentials** — CLAUDE.md + **every** rule under `.claude/rules/**/*.md` (all of them, eager, no filter)
3. **Crew** — reads the target's `.weside/weside.md` and prints the crew summary

**When to use:**
- Genuine cross-repo situations where switching to a native session in the target repo is not practical
- The eager rule load is expensive; if you can `cd` into the target repo and start a native session, do that instead

---

## Engineering discipline skills

### `/we:grill`

> *Relentless one-question-at-a-time interview on a plan or design.*

Walks every branch of the decision tree — one question per turn, each with a recommended answer, exploring the codebase instead of asking where possible. As decisions crystallise it updates the project glossary (repo-root `CONTEXT.md`) inline and offers a lean ADR when a decision passes the 3-gate: hard to reverse ∧ surprising without context ∧ a real trade-off.

**When to use:**
- Before committing to a contentious design
- When terminology is fuzzy or overloaded ("account" vs "customer" vs "user")
- To stress-test an epic/story scope outside the formal meeting flow

---

### `/we:diagnose`

> *Disciplined diagnosis loop for hard bugs and performance regressions.*

Phase 1 is the skill: build a fast, deterministic, agent-runnable feedback loop (failing test, curl script, replay harness, bisection — 10 escalating options). Then reproduce → 3-5 ranked falsifiable hypotheses → instrument one variable at a time → fix with a regression test at a correct seam → cleanup + post-mortem.

**When to use:**
- A bug survives the first obvious fix attempt
- Non-deterministic / flaky failures
- Performance regressions (measure first, fix second)

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

### `/we:audit`

> *Tool-driven security scan.*

Runs `semgrep / trivy / kubescape / gitleaks` (or your project's own `scripts/security-audit.sh`), parses JSON reports, summarizes findings by severity.

**When to use:**
- Pre-release security pass
- After integrating a new external dependency
- Compliance check-ins

---

## Dev Utilities

### `/we:audit-architecture`

> *Multi-phase backend architecture audit.*

Healthcheck → Hotspot map → Subsystem deep-read → Cross-cutting lenses → Findings. Configurable per-project via `docs/.audit-architecture.yml`.

**When to use:**
- Periodic architecture health-checks (suggest quarterly)
- After significant growth — when the codebase outgrew its old structure
- Before a major refactor — to know what the current shape *actually* is

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
