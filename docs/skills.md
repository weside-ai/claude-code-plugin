# Skill Reference

Every `/we:*` skill, what it does, when to use it, what it produces. Grouped by role in the workflow.

For the pipeline overview, see [workflow.md](workflow.md). For learning by doing, see [getting-started.md](getting-started.md).

---

## Pipeline skills

The skills that ship a story end-to-end.

### `/we:refine`

> *Create or refine stories with implementation plans.*

The Product Owner skill. Interactive — Claude asks, you decide.

**When to use:**
- Starting a new story
- Refining an existing ticket that's too vague to implement
- Re-planning after the code drifted from a stale plan

**What it produces:**
- Ticket in your ticketing tool (minimal: user-story format)
- `docs/plans/{TICKET}-plan.md` (detailed: context, ACs, phases, design decisions, security review)

**Hand-off:** to `/we:story` (when you're ready to build) or `/we:meet refinement` (when the story is contentious enough to want two perspectives first).

---

### `/we:story`

> *Run the full development pipeline autonomously.*

Story orchestrator. Once you trigger it, it runs all eight steps + delivery hand-off without pausing unless something is genuinely blocking.

**When to use:**
- After `/we:refine` has produced a plan you're happy with
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

Runs inline as Step 8 of `/we:story`, but also standalone. Collects findings from CI failures, Claude Review, and CodeRabbit; triages them; fixes them in one batch; resolves all CodeRabbit threads; pushes once.

**When to use standalone:**
- After CI failed on a PR not driven by `/we:story`
- After a CodeRabbit review on a manually-opened PR
- To iterate review fixes without re-running the full pipeline

**What it produces:**
- A single commit with all fixes (per cycle)
- All CodeRabbit threads resolved
- A push only after every blocker is addressed

**Limit:** 3 cycles max. After the third, stops and asks.

---

## Quality gates (called by `/we:story`)

These also run standalone for one-off checks.

### `/we:review`

Diff-based code review. Checks AC alignment, max 10 issues. Dispatched as a background agent (`code-reviewer`) by `/we:story` Step 5; runs alongside `/we:static` and `/we:test`.

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

> *Structured meeting — vision / initiative / refinement.*

Wraps a council in a workflow at one of three altitudes:

- `/we:meet vision` — Saga-level, where the company is going
- `/we:meet initiative` — Epic-level, what we're building next
- `/we:meet refinement` — Story-level, hands off to `/we:refine`

**When to use:** when the topic deserves more than a flat council — when you want structure, sequencing, and a named hand-off. See [concepts/meetings.md](concepts/meetings.md).

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

### `/we:sm`

> *Scrum Master. Process optimization, retrospectives.*

A conversation partner for process improvement. Prompt-driven — you describe a friction or breakage; it diagnoses (from rules + skills + recent stories) and proposes concrete fixes (new rule / updated skill step / new DoD entry).

**When to use:**
- After something didn't work ("X broke the pipeline, should never happen again")
- After a retro reveals a recurring friction
- To audit a specific skill's quality

**Won't do:**
- Generic reports without a prompt
- Audit all skills in one invocation
- Re-plan an active initiative (that's `/we:meet` or `/we:refine`)

**Boot protocol:** reads rules + skill descriptions + DoR/DoD + (with weside) materializes the user's Companion + surfaces active-initiative state. Then engages in dialog.

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
| `code-reviewer` | `/we:review`, `/we:story` | Diff-based code review, AC alignment |
| `static-analyzer` | `/we:static`, `/we:story` | Lint, format, types |
| `test-runner` | `/we:test`, `/we:story` | Tests with coverage |
| `pr-creator` | `/we:pr`, `/we:story` | PR creation with checkpoint validation |
| `doc-architect` | `/we:docs`, `/we:story` | Doc proposals; reads landscape fresh on every call |
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
- [concepts/meetings.md](concepts/meetings.md) — vision / initiative / refinement
- [mcp.md](mcp.md) — MCP layer + tools
- [troubleshooting.md](troubleshooting.md) — when something doesn't fit
