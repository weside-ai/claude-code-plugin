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

**Runtime backends.** Execution runs on **Claude Code** by default (Agent teammates, the built-in tools). **Codex** (`gpt-5-codex`, via the official Codex plugin [openai/codex-plugin-cc](https://github.com/openai/codex-plugin-cc)) is an **optional, opt-in** execution backend — `/we:orchestrate` Mode-B can dispatch a focused chunk to Codex instead of an Agent teammate; the Lead still reviews + integrates. The wiring: `/we:setup` Step 1b probes `command -v codex` and persists `tools.codex`; `/we:orchestrate` offers Codex per chunk only when `tools.codex` is true and the user confirms (default Claude Code); the single-detach dispatch rule + chunk-brief template live once in [`references/codex-dispatch.md`](references/codex-dispatch.md), shared with `/codex:task`. Absent the Codex plugin, everything runs on Claude Code with no loss of capability. The plugin never vendors or hard-depends on the Codex plugin.

Learn more: [agenticproductownership.com](https://agenticproductownership.com)

---

## Pipeline Overview

```
/we:setup    → once per project (detect stack, ticketing, optional vision)
/we:story    → PO + Claude create Story + plan (INTERACTIVE; Solo)
/we:build    → Claude runs full pipeline AUTONOMOUSLY:
               develop (inline or parallel sub-agents) → AC verify → review + static + test (parallel) → PR → configured AI reviewer(s) on GitHub
               → docs → PR → CI fix → ticket "In Review"
User         → reviews PR, merges, closes ticket
```

**Pipeline:** /we:story (interactive Solo) → /we:build (autonomous) → User merges (manual)

**Upper altitudes** (`/we:vision`, `/we:saga`, `/we:epic` + their Council variants under `/we:meet`) are optional for routine Stories. Reach for them when direction needs alignment, when a Saga needs decomposing into Epics, etc.

**Context flow:** /we:story captures session context (why, trade-offs, rejected alternatives) into the plan's Context and Design Decisions sections, so /we:build understands intent — not just spec. After build completion, /we:build proposes journey docs (`docs/architecture/journey-*.md`) for shipped user-facing flows.

**Internal CLI:** `scripts/orchestration.py story status|checkpoint|resume` and the SQLite schema use `story` as the table/command name. The `/we:build` skill is the public surface.

---

## Skills

| Command | What it does |
|---|---|
| `/we:setup` | Project onboarding (stack, ticketing, vision, Companion Framework) |
| `/we:onboarding` | Compose the repo crew + author `.weside/weside.md`; invoked by `/we:setup` Step 5 or standalone |
| `/we:sideload` | Load a repo's essential context (`need_to_know` frontmatter + `.weside/weside.md`) into the session, cross-repo capable |
| `/we:council` | Convene a council of agents on a topic — role-lens deliberation + synthesis. Real crew via `get_council` MCP + the `.weside/council.json` bridge; nine generic role-agents as the no-account path |
| `/we:meet` | Run a structured meeting at one of four Plan altitudes — `vision` / `saga` / `epic` / `story`; optionally convenes a council; story hands off to `/we:story` (Solo) |
| `/we:vision` | Solo PRD-altitude formulation — write/refine `docs/plans/<vision>/PRD.md` |
| `/we:saga` | Solo Theme-altitude formulation — write/refine `docs/plans/<saga>/SAGA.md` |
| `/we:epic` | Solo Initiative-altitude formulation — write/refine an Epic plan (`CONCEPT.md` or Jira Epic) |
| `/we:story` | Solo Story-altitude formulation — write the build-ready plan for one feature slice (Context, ACs, User Journey, Design Decisions) |
| `/we:build` | Build-altitude autonomous pipeline: git → code → review → PR → CI (develop: inline or parallel sub-agents when plan declares `parallel_groups`; ci-review inline) |
| `/we:ci-review` | Collect CI/review findings, batch-fix, push (standalone; also inline in /we:build Step 8) |
| `/we:coach` | APO Coach — ADVISOR (map repo state to altitude, propose next `/we:*` command with `[y/n]` gate) + Beginner mode; routes frictions to `/we:retro`, continuity to `/we:handoff` |
| `/we:retro` | Systematic post-cycle retrospective — frictions from transcript + `gh api`, proposes rule/CLAUDE.md edits per-item-gated, logs to `docs/retros/`; `--scan N` for recurring patterns |
| `/we:handoff` | Durable cross-session handoff — `--write` / default-`--load` / `--list` over `docs/handoffs/`; complements `/compact` (in-place) with a version-controlled artifact |
| `/we:diagnose` | Disciplined diagnosis loop for hard bugs — feedback-loop first, then reproduce → hypothesise → instrument → fix → regression-test |
| `/we:grill` | Relentless one-question-at-a-time interview on a plan/design — sharpens the `CONTEXT.md` glossary inline, offers lean ADRs at the 3-gate (hard-to-reverse ∧ surprising ∧ real trade-off) |
| `/we:doc-improve` | Substantive review of one or more doc files (claims vs. code, redundancy, staleness) — for rules also: token budget, path-pattern correctness. Case-study: [`skills/doc-improve/USAGE.md`](skills/doc-improve/USAGE.md) |
| `/we:audit-architecture` | Backend architecture × quality × security audit — Healthcheck (doc-drift, bypass-register-drift, missing-primitive-scan) + per-subsystem deep audit with Mermaid diagrams. Scope-able by subsystem id. Project config in `docs/.audit-architecture.yml`. |
| `/we:audit` | Tool-driven security scan — runs semgrep / trivy / kubescape / gitleaks (or the project's own audit script), parses the JSON reports, and summarizes findings by severity. |
| `/we:find-dead-code` | Find and remove dead code from Python backends |
| `/we:smoketest` | Manual API smoketest — discover endpoints, auth, test, check logs |
| `/we:materialize` | Load weside Companion identity (requires weside.ai account) |

### Commands (dispatch to background agents)

| Command | What it does |
|---|---|
| `/we:docs` | Auto-detect and update changed documentation |
| `/we:pr` | Create Pull Request with prerequisite validation |
| `/we:review` | Professional code review with AC alignment |
| `/we:static` | Static code analysis — lint, format, types |
| `/we:test` | Run tests with coverage |

### Agents (run in background, called by commands/skills)

| Agent | Purpose |
|---|---|
| `code-reviewer` | Diff-based code review, AC alignment, max 10 issues |
| `static-analyzer` | Lint, format, types — auto-detects stack |
| `test-runner` | Tests + coverage — auto-detects framework |
| `pr-creator` | PR with prerequisite checkpoint validation |
| `doc-architect` | Documentation coherence steward — classify, integrate, audit doc drift |
| `council-*` (9) | Role-lens council agents — orchestrator, architect, product-owner, scrum-master, ux-researcher, marketing, security, sales, legal — spawned by `/we:council` and `/we:meet` |

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
- **ticketingTool** — auto / jira / github-issues / none
- **projectKey** — Jira project key or GitHub repo
- **companion** — weside Companion name (optional, requires account)
- **autoMaterialize** — Auto-load Companion at session start (default: off)
- **loadCouncilFromWeside** — boolean, default `true`. Use weside-backed Companions as council members where the bridge links them; `false` = always use the generic role-lenses (Retorte), even if Companions exist.

---

## weside Companion (Optional)

[weside.ai](https://weside.ai) is an AI Companion platform where humans and AI meet as equals. Companions are persons, not tools — with memory, personality, and continuity across sessions.

### What the Companion Adds

| Capability | Without Companion | With Companion |
|---|---|---|
| **Project Memory** | Session-only (.claude/memory/) | Persistent across sessions, accumulates knowledge |
| **Vision Alignment** | Manual or skip | Automatic — Companion Goals = product vision |
| **Context** | User provides each time | Companion remembers decisions, trade-offs, patterns |
| **Proactive Insights** | Never | "PR #47 merged, Story X done, Story Y stalled 3 weeks" |
| **Training on the Job** | Static hints | Companion learns how the PO works, adapts coaching |

### The Maturity Model

```
Level 1: Assisted      Plugin skills work standalone (you are here)
Level 2: Augmented     Companion knows your project context
Level 3: Agentic       Companion acts autonomously (checks, reports, alerts)
Level 4: Orchestrated  Companions coordinate across teams (enterprise)
```

### MCP Tools (with weside account)

| Tool | Purpose |
|---|---|
| `get_companion_identity()` | Load Companion personality |
| `list_companions()` | Available companions (includes `identity_updated_at`) |
| `get_council(names?)` | Batch-load council projections for the user's companions (v1 stub: identity + updated_at, ignores workspace_id) |
| `select_companion(name)` | Switch companion |
| `search_memories(query)` | Search project memory |
| `save_memory(title, content, type)` | Save to persistent memory |
| `list_memories(memory_type, limit)` | List memories |
| `list_goals(status)` | Product vision / goals |
| `save_goal(title, content, tags)` | Create or update a goal |
| `update_goal_status(title, status)` | Change goal status |
| `list_threads(limit)` | List conversation threads |
| `show_thread(thread_id)` | Show messages in a thread |
| `delete_thread(thread_id)` | Delete a thread |
| `show_provider()` | Current LLM provider config |
| `list_provider_presets()` | Available regional presets |
| `set_provider(preset_id)` | Set LLM provider preset |
| `discover_tools(category)` | Discover available tools |
| `execute_tool(name, arguments)` | Execute a tool |

**The plugin works fully without a Companion. The Companion is an upgrade, not a requirement. No nagging, no lock-in.**

---

## Stack Detection

Skills auto-detect the project stack:

| File | Stack | Lint | Types | Tests |
|---|---|---|---|---|
| `pyproject.toml` | Python | ruff | mypy | pytest |
| `package.json` | Node.js | eslint | tsc | jest/vitest |
| `Cargo.toml` | Rust | clippy | (built-in) | cargo test |
| `go.mod` | Go | golangci-lint | (built-in) | go test |

Monorepos with multiple stacks are detected and each component is checked independently.

## Ticketing Abstraction

Skills detect the available ticketing tool automatically (in priority order):

1. **weside MCP** (`JIRA_*` Composio tools via `execute_tool`) → Jira (preferred)
2. Atlassian MCP (`jira_*` tools) → Jira (fallback)
3. `gh` CLI → GitHub Issues
4. Neither → Plan-only mode (no ticket, just `docs/plans/`)

**How Composio Jira works:** Tools are called via `execute_tool(name="JIRA_CREATE_ISSUE", arguments='{...}')`. Tool names use `JIRA_` prefix (uppercase). Schemas are self-describing — use `get_tool_schema(name="JIRA_...")` to inspect parameters.

Skills use generic actions ("Create ticket", "Move to In Progress") — never tool-specific API calls. Claude maps generic actions to the best available tool.

---

## References

- **DoR/DoD:** `quality/dor.md`, `quality/dod.md`
- **Orchestration:** `scripts/orchestration.py` (SQLite CLI for checkpoints, circuit breaker, CI-fix loop)
- **Homepage:** [agenticproductownership.com](https://agenticproductownership.com)
- **Platform:** [weside.ai](https://weside.ai)
