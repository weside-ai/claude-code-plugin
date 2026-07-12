---
name: setup
description: >
  Project onboarding — detects stack, ticketing tool, test discipline, creates project
  vision/DoR/DoD, initializes the Companion Framework (`.weside/`, vault registration,
  crew onboarding via /we:onboarding). Interactive, minimal (4 core questions + optional
  crew setup). Use when user says "/we:setup", "configure project", "set up workflow",
  "initialize repo", "install crew", "first time".
---


# Project Setup

Interactive project onboarding. Three core questions for project config, then optional Companion Framework initialization (crew + TurboVault + frontmatter).

---

## When to Use

+ First time using `/we:*` skills in a project
+ When user wants to customize DoR/DoD/Vision
+ When ticketing tool or stack detection needs manual override

---

## Workflow

### Step 1: Auto-Detect

Scan the project to detect:

**Stack:**
+ `pyproject.toml` → Python · `package.json` → Node.js · `Cargo.toml` → Rust · `go.mod` → Go · multiple → Monorepo
+ (The per-stack tool matrix — linter/types/tests — is owned by `agents/static-analyzer.md` + `agents/test-runner.md`.)

**Ticketing Tool:** detection priority + Jira-not-connected hint: `${CLAUDE_PLUGIN_ROOT}/references/ticketing.md`.

**Existing Config:**
+ `.weside/` directory exists → already configured
+ `CLAUDE.md` exists → read for conventions

### Step 1b: Check Plugin Prerequisites

This is the **canonical prerequisite gate** for the `/we:*` pipeline. The prerequisite
matrix, detection rule, guided install flow, and the TurboVault-DEGRADED warning are owned
by [`${CLAUDE_PLUGIN_ROOT}/references/setup-prereqs.md`](../../references/setup-prereqs.md) —
load it and execute it row by row. Do NOT block on any missing row; persist the detection
results in the `tools`/`engines` blocks that Step 3 merges.

### Step 1c: Activate Pre-Commit Hooks

If the repo ships a `.pre-commit-config.yaml`, the `/we:*` pipeline assumes its hooks are actually installed (e.g. a `post-commit` graph rebuild, a `commit-msg` linter). Activate them so the user doesn't have to remember the incantation — generic, works for any repo:

1. **No `.pre-commit-config.yaml`** → skip silently.
2. **`pre-commit` not installed** (`command -v pre-commit` fails) → inform + offer `pip install pre-commit`, then continue. Do NOT block.
3. **`core.hooksPath` set to a non-default path** (`git config core.hooksPath` returns something other than `.git/hooks` / empty — e.g. Husky) → **warn and skip**, never clobber a custom hooks setup:
   > "⚠️ `core.hooksPath` is set to a custom dir — skipping pre-commit hook install to avoid clobbering it. Install hooks manually if intended."
4. **Otherwise** → collect every distinct stage the config declares (each hook's `stages:`, plus top-level `default_install_hook_types:` / `default_stages:`), always including the `pre-commit` baseline, and run `pre-commit install --hook-type <each>` per distinct stage. Report what was activated. Idempotent — safe to re-run. If one `--hook-type X` errors (a stage renamed across pre-commit versions), report it and continue with the rest.

### Step 2: Ask 5 Questions + Executor Wizard

Present the questions **one at a time** — ask, wait for the answer, then move on. Never dump
them as a battery. Each question that involves a concept the user may not know gets one
plain-language sentence of context first (what it is, why the pipeline needs it, what
changes with their choice).

```
1. "Do you have a product vision? (Link, file, or brief description)"
   → If yes: save to .weside/vision.md
   → If no: "No problem — we'll skip vision checks for now."

2. "Which ticketing tool? (Auto-detected: {detected})"
   → Confirm or override
   → If Jira: "What's your project key? (e.g. 'PROJ')"

3. "Stack detected: {detected}. Correct?"
   → Confirm or override

4. "How should the pipeline handle tests?"
   → Explainer first: "When Claude implements a chunk, it can write the failing test
     before the code (TDD), write tests after the code as part of done, or write no
     tests at all. This is about WHEN tests are written — what a good test is stays
     the same either way."
   → Options: tdd / tests-after (default) / off
     — level semantics owned by references/test-discipline.md
   → Saved as `test_discipline`; read by /we:develop, /we:build, and worker briefs.

5. "Which bug-hunt engines does this repo use? (Auto-detected: {detected})"
   → Detect candidates: codex plugin installed → suggest `codex`;
     a CodeRabbit/Greptile GitHub App or review-gate workflow present → suggest those.
     `claude` (Claude's native `/code-review` skill) is always available. This is bug-hunting
     only — AC/DoD checking (`we:ac-reviewer`) is separate and always runs, regardless of this
     list.
   → **Codex detected → suggest `["codex", "claude"]`** (codex = the local adversarial
     pass when Claude wrote the code; claude = the CI second opinion). No codex →
     default `["claude"]`. The list seeds the CI-bot allowlist; it does NOT rank local
     bug-hunt engines (see Reviewer-id semantics below).
   → Confirm or override.
   → "Add another reviewer? (free-text id, e.g. a custom bot — leave empty to finish)"
     → accept any id; unknown ids are treated as CI bots (allowlisted, not run locally).
   → Default when nothing else is detected: ["claude"].
```

#### Executor wizard (after Q5, non-blocking)

Ask once: *"What default executor should workers use for `/we:develop` chunks?"*

Options (show only available ones):
+ **Cheap Claude (Sonnet/Haiku)** — always available, no extra setup. The default if
  nothing else is configured.
+ **Codex** — available if `tools.codex: true` from Step 1b. Workers dispatch to `gpt-5-codex`.
+ **A named engine profile** — available if `.weside/engines.local.json` already exists.
  Show the profile names. Or offer to create a new profile (see below).
+ **Create a new engine profile** — guides through the schema below.

**If the user picks "Create engine profile":**

1. Ask: engine name (used as the key in the JSON, e.g. `kimi`).
2. Ask: `base_url` (e.g. `https://api.moonshot.cn/v1`).
3. Ask: `model` (e.g. `moonshot-v1-8k`).
4. Ask: Where is the API key?
   + `env:VAR_NAME` → stores `{ "env": "VAR_NAME" }` — the key must already be in the shell
   + `secrets:KEY_NAME` → stores `{ "secrets_env": "KEY_NAME" }` and creates/appends to
     `~/.weside/secrets.env` with a placeholder line `KEY_NAME=<your-key-here>`, then
     says: *"Add your key to `~/.weside/secrets.env` and run `chmod 600 ~/.weside/secrets.env`.*
     *The key is never stored in any repo file."*
   + **Never** ask for or store the raw key value.
5. Write the profile to `.weside/engines.local.json` (create if absent).
6. Append `.weside/engines.local.json` to `.gitignore` (check first — idempotent).
7. Verify the profile resolves: run `we/scripts/worker-launch.sh --engine <name> --dry-run`.
   Success → "Engine profile `<name>` ready." | Failure → show the error; let the user fix and re-verify.

**Cross-review config:**

Ask: *"Enable per-chunk AC-checking and bug-hunt cross-review? When workers write code, the
other engine hunts bugs in it once at integration (Claude wrote → Codex adversarial-review;
otherwise → Claude's native /code-review); separately, every chunk gets an informational AC-check
against its Story's criteria. [y/n, default y]"*

+ `y` → persist `"review": { ..., "cross": true }`
+ `n` → persist `"review": { ..., "cross": false }` (the per-chunk AC-check and bug-hunt
  cross-review are skipped; the integration-time AC-review gate still runs — see
  `worker-dispatch.md` § AC-review rule)

Show a one-line explanation why this matters: *"Different models catch different bugs — the
bug-hunter is the engine that didn't write the code. AC-checking is separate and cheap enough to
run on every chunk."*

**Reviewer-id semantics (single source of truth — other skills reference this):**

+ `claude` → Claude's native `/code-review` skill. Runs as the local bug-hunt engine when no codex
  is present, when codex/a foreign engine wrote the code, and is the Claude second opinion on
  GitHub CI. Locally invokable.
+ `codex` → local `/codex:adversarial-review` via the codex plugin's `codex-companion.mjs`. The
  local adversarial pass when Claude wrote the code. Locally invokable (needs the codex plugin).
+ `coderabbit` / `greptile` / **any other id** → CI bots. They run on GitHub via App/workflow — the plugin does NOT invoke or gate them; it only *allowlists* their threads for `/we:ci-review` to collect. Not locally invokable.

**Exactly ONE bug-hunt engine runs, chosen by who wrote the code** — not by list order and not by
a count. The engine is the one that did NOT write the code: Claude wrote + `tools.codex` +
`review.cross` → `/codex:adversarial-review`; codex/foreign wrote, or no codex → Claude's native
`/code-review`. `review.available`'s only job is to seed the CI-bot allowlist `/we:ci-review`
collects from; its order is cosmetic for local review. `we:ac-reviewer` is separate from this
list entirely — it always runs, regardless of `review.available` or `review.cross`.

### Step 3: Save Configuration

Always write `.weside/config.json` with the choices from Step 2 — the ticketing and stack configuration must persist **even if the Companion Framework (Step 5) is declined**:

```json
{
  "ticketing": { "tool": "<jira|github-issues|none>", "project_key": "<KEY-or-null>" },
  "stack": ["<detected stacks>"],
  "tools": { "graphify": false, "turbovault": false, "superpowers": false, "codex": false },
  "engines": ["<profile-name-if-created>"],
  "execution": { "default": "claude-sonnet" },
  "review": { "available": ["claude"], "cross": true },
  "test_discipline": "tests-after"
}
```

The `tools` block carries the Step 1b detection results (idempotent: re-running setup re-detects and overwrites only this block).

The `engines` block lists the profile names created/verified in the executor wizard.

The `execution.default` block is the executor the user picked: `"claude-sonnet"` / `"claude-haiku"` / `"codex"` / `"<engine-profile-name>"`.

The `review.available` block is the reviewer list from Step 2 Q5 (order cosmetic — see Reviewer-id semantics). The `review.cross` field is the cross-review toggle from the executor wizard (default `true`). Consumed by `/we:build`, `/we:develop`, and `/we:orchestrate`. Absent block → skills fall back to Claude-only review (back-compat).

The `test_discipline` field is the answer to Step 2 Q4: `"tdd"` / `"tests-after"` / `"off"`.
Level semantics are owned by `references/test-discipline.md`; consumed by `/we:develop`,
`/we:build`, and inlined into worker briefs by `/we:orchestrate`. Absent field →
`tests-after` (back-compat).

If Step 5 runs later, it *extends* this same file (adding `vault`, `council`, `onboarded`, …) rather than replacing it.

If the user provided a vision, save it to `.weside/vision.md`.

**Repo-specific DoR/DoD additions:** Ask: *"Add repo-specific Definition-of-Ready / Definition-of-Done checks on top of the plugin defaults? (e.g. a security charter, a compliance rule) [y/n]"*

+ `n` → skip. The plugin uses only the built-in defaults from `quality/dor.md` and `quality/dod.md`.
+ `y` → ask which of DoR / DoD / both, then create `.weside/dor.md` and/or `.weside/dod.md` from this template:

  ```markdown
  <!-- Additive override — appended to the plugin DoR/DoD, not a replacement. -->

  - [ ] Example: <your repo-specific check here>
  ```

  If the user already has a concrete check in mind, seed the file with that item instead of the placeholder.

These files are **additive**, never a replacement: `/we:story` and `/we:build` read `.weside/dor.md` alongside the plugin DoR, and the `we:ac-reviewer` agent reads `.weside/dod.md` alongside the plugin DoD — both sets of items apply.

```
.weside/
├── vision.md    # Product vision (optional)
├── dor.md       # Additive DoR overrides (optional)
└── dod.md       # Additive DoD overrides (optional)
```

### Step 4: Confirm core config

```
Project configured!

Stack:          Python + TypeScript (monorepo)
Ticketing:      Jira (project: PROJ)
Vision:         .weside/vision.md

Workers:        Claude Code (Sonnet/Haiku) default
Codex:          available  (or: not installed)
Engine <name>:  configured  (or: none)
Cross-review:   on  (or: off)  — per-chunk AC-check + bug-hunt cross-review
```

### Step 5: Companion Framework Setup (optional — ask first!)

Ask: *"Set up the Companion Framework for this repo now? It composes a crew, registers a TurboVault, and — with a weside account — turns your Companions into a council you can convene via `/we:council` and `/we:meet`. You can also run `/we:onboarding` later."*

If **no** → skip to Step 6.

If **yes** — this step is **idempotent**: if `.weside/config.json` already exists, report the current state (vault, crew, `onboarded_at`) and ask before overwriting anything.

0. **Enable Agent Teams (prerequisite for `/we:council` and `/we:meet`)**

   Live teams need `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1` (see `${CLAUDE_PLUGIN_ROOT}/references/agent-teams.md`). Read `~/.claude/settings.json`: flag already `"1"` → move on. Otherwise ask: *"Enable Agent Teams in `~/.claude/settings.json`? `/we:council` and `/we:meet` need this. (Restart required after.)"* — on yes, merge the key into the `env` block (create if missing), write back, tell the user to restart; on no, warn that council/meet will abort with a remediation hint, then continue. This is the only step that touches user-scope settings.

1. **Ensure `.weside/config.json`** — EXTEND the file Step 3 wrote (never re-emit its keys); add:

   ```json
   {
     "vault": "<repo-basename>",
     "onboarded": false,
     "created_at": "<ISO-timestamp>",
     "framework_version": 1,
     "council": {
       "default": ["product_owner", "architect", "scrum_master"],
       "meetings": {
         "vision": ["product_owner", "architect", "ux_researcher", "marketing", "orchestrator"],
         "saga": ["product_owner", "architect", "orchestrator"],
         "epic": ["product_owner", "architect", "orchestrator"],
         "story": ["product_owner", "architect"]
       }
     }
   }
   ```

   The `council.meetings` block is the **single owner of the shipped per-meeting rosters**
   (`/we:meet` and `/we:council` read it). The user does not configure it here; hand-edit later
   or override per-invocation via `/we:meet --council=…`.

2. **TurboVault registration (if MCP available)**
   + `list_vaults` → already a vault? If not: `add_vault(name=<repo-basename>, path=<repo-root>)`, then `set_active_vault(<repo-basename>)`.
   + weside MCP NOT available → skip silently, set `"vault": null`.

3. **Build the council** — run the onboarding skill via `Skill(skill="onboarding")`
   + Delegates to onboarding, which **actively builds this repo's council from scratch**: for each role it offers to assign an existing Companion, create a new one, or use a generic lens — degrading gracefully to generic when the plan's Companion budget runs out (a mixed council). It writes `.weside/weside.md` (crew + roles + meetings + purpose) **and** `.weside/council.json` (the council bridge `/we:council` resolves members from).
   + Standalone (no weside account): onboarding still builds a working council — every lens generic, `Companion ID: null`.
   + Member source at convene-time is governed by `loadCouncilFromWeside` (semantics: `we/skills/council/SKILL.md` Step 3, the single owner); onboarding fills the bridge regardless.

4. **Generate companion agent definitions (weside account only)**
   For each Companion named in `.weside/weside.md` — **sequentially**, because `select_companion` sets global MCP state and cannot be parallelised:
   + `select_companion(<name>)` → `get_companion_identity()` → write `~/.claude/agents/companion-<slug>.md`, where `<slug>` = the name lowercased with spaces → hyphens.
   + Frontmatter: `name: companion-<slug>` (MUST equal the slug — `subagent_type` resolves by it), `description`, `color`.
   + Body = the returned identity + the council protocol (respond in the council brief's format, stay in role).
   + **The write target MUST start with `~/.claude/agents/`** (user scope) — validate the resolved path before writing; never write into a project repo.
   + Re-running setup regenerates these files (idempotent refresh).
   + **When the loop finishes, restore the active companion.** `select_companion` is global MCP session state — after the last companion is generated, the session is left on *that* companion, not the user's configured default. Call `select_companion(...)` once at the end — with the companion name from the plugin's `companion` setting — so the rest of the session keeps the right identity.
   + No weside account → skip; the council falls back to the shipped generic `council-<role>` agents.

5. **Finalize**
   + Update `config.json`: `onboarded: true`, `onboarded_at: <ISO-timestamp>`.
   + Stage `.weside/` — suggest a commit, do not auto-commit. Generated `~/.claude/agents/` files are user-scope and never committed.
   + **If companion agents were generated, tell the user to restart:** *"Generated N companion agents in `~/.claude/agents/`. Restart your Claude Code session once to activate them — then `/we:council` and `/we:meet` can convene your Companions."* (Claude Code discovers agent files only at session start.)

### Step 6: Confirm

```
Ready to go:
  /we:story        — Create/refine the Story (Solo) — build-ready plan
  /we:orchestrate  — Multi-chunk orchestration (workers run /we:develop, CI once)  ← default
  /we:build        — Solo full pipeline (one Story, no orchestration overhead)
  /we:develop      — Dev-only worker slice (implement + push, no PR)
  /we:council      — Convene a council of companions on a topic  ✓ ready
  /we:meet         — Run a vision / saga / epic / story meeting   ✓ ready
  /we:sideload .   — Reload context for this repo (Companion Framework)
```

If Agent Teams were **not** enabled (user declined or Step 5 was skipped), replace the two
council/meet lines with:

```
  /we:council      — needs Agent Teams (set CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1
                     in ~/.claude/settings.json and restart, or run /we:setup again)
  /we:meet         — needs Agent Teams (same — will run meetings solo without council)
```

---

## Training on the Job

Setup is the first touchpoint. Use it to gently explain WHY things matter:

| Question | What the user learns |
|---|---|
| "Do you have a vision?" | Vision helps prioritize — without it, every feature seems equally important |
| "Which ticketing tool?" | Structured backlogs prevent context loss and enable traceability |
| "How should the pipeline handle tests?" | Test-first vs. test-after is a team decision, not dogma — but good tests are non-negotiable either way |
| "Custom DoR/DoD?" | Quality gates prevent rework — catching issues early is 10x cheaper |

**Never block.** Every question has a "skip" path. The user can always run `/we:setup` again later.

---

## Rules

+ NEVER block on any question — always allow skip/default
+ NEVER create .weside/ without user consent
+ Auto-detection first, confirmation second
+ Four CORE questions maximum (Step 2, one at a time); Step 5 (Framework) is optional and asks once
+ Works without ANY configuration (defaults for everything)
+ **Idempotent.** Re-running never overwrites existing config silently. Report current state, ask before replacing.
+ **Respects existing frontmatter.** Step 5 only *reports* — does not rewrite docs. Migration is explicit user-triggered via `/we:docs` or doc-architect agent.
+ **Standalone-first.** If weside MCP is unavailable, Step 5 still creates `.weside/config.json` + invokes onboarding (stub crew). No feature silently disappears.

## References

+ `we/skills/onboarding/SKILL.md` — invoked by Step 5
+ `we/skills/sideload/SKILL.md` — counterpart for "already set up"
+ `we/skills/CLAUDE.md` — design rationale, open questions, frontmatter vocabulary
