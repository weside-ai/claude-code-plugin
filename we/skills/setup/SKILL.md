---
name: setup
description: >
  Project onboarding — detects stack, ticketing tool, creates project vision/DoR/DoD,
  initializes the Companion Framework (`.weside/`, vault registration, crew onboarding
  via /we:onboarding). Interactive, minimal (3 core questions + optional crew setup).
  Use when user says "/we:setup", "configure project", "set up workflow", "initialize repo",
  "install crew", "first time".
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

This is the **canonical prerequisite gate** for the `/we:*` pipeline. Verify each prerequisite empirically — never derive availability from plugin filesystem paths alone, since plugins can ship agents, skills, or commands under different names than expected.

**Detection rule:** for each row, run the listed *Detection check*. The check is the source of truth. If it succeeds → prerequisite is met. If it errors with "not found" → mark as missing and inform the user (do NOT block).

| Prerequisite | Detection check | Provided by | Used by |
|---|---|---|---|
| `gh` CLI authenticated | `gh auth status` exits 0 | GitHub CLI install + `gh auth login` | `/we:pr`, `/we:ci-review`, `/we:build` PR creation, CI status, review-thread resolution |
| Jira access (one of) | weside MCP Composio `JIRA_*` via `execute_tool` (preferred) / `mcp__atlassian__jira_*` (fallback) / `gh issue` for GitHub-Issues mode | weside MCP + Composio Jira, or Atlassian MCP, or GitHub CLI | `/we:story`, `/we:build` ticket fetch and transitions |
| `simplify` skill | `Skill(skill="simplify")` available in the skill list | `code-simplifier@claude-plugins-official` (ships an agent that the harness exposes as the `simplify` skill) | `/we:build` Step 4: Simplify |
| security guidance hooks | `security-guidance` plugin in `~/.claude/plugins/installed_plugins.json` | `security-guidance@claude-plugins-official` | `/we:build` Step 2 security checks |
| TurboVault MCP | **Liveness, not just presence:** actually call `mcp__turbovault__list_vaults` and confirm it responds. Tool name present but the call errors/hangs → **DEGRADED** (registered but not responding). Tool name absent → **not registered**. | TurboVault MCP server | `/we:story` (semantic search), `/we:build` (architecture context), `/we:docs`, `/we:doc-improve` (skills have fallbacks if missing) |
| weside MCP | `mcp__plugin_we_weside-mcp__get_companion_identity` available | weside MCP (requires weside.ai account) | `/we:materialize`, optional companion memory in `/we:story` and `/we:build` |
| superpowers plugin | `superpowers` in `~/.claude/plugins/installed_plugins.json` (or `Skill(skill="superpowers:brainstorming")` listed) | `superpowers@anthropics` (Anthropic) | TDD/debugging/brainstorming discipline skills used throughout `/we:build` |
| graphify CLI | `python3 -c "import graphify"` exits 0 AND `graphifyy>=0.8.38` (`python3 -c "from importlib.metadata import version; print(version('graphifyy'))"`) | `pip install -U 'graphifyy>=0.8.38'` (user-level) | `/we:story` blast-radius block, `/we:audit-architecture` graph-drift check, code-graph nav rule |
| turbovault binary | `command -v turbovault` (only when the MCP row above is missing) | TurboVault binary install + MCP registration | distinguishes "binary missing" from "MCP not registered" for the guided fix |
| Codex backend (optional) | `command -v codex` exits 0 (the official Codex plugin's CLI) | [openai/codex-plugin-cc](https://github.com/openai/codex-plugin-cc) | `/we:orchestrate` and `/we:develop` optional executor; cross-review via `/codex:adversarial-review`. Absent → workers run on Claude Code with no degradation |
| Engine profiles (optional) | `.weside/engines.local.json` exists and has ≥1 profile with a resolvable `key_ref` | User-created via this wizard | `/we:orchestrate` foreign-engine executor via `worker-launch.sh`; any Anthropic-compatible endpoint |

**Guided install flow** — for each MISSING row, offer the fix interactively instead of only hinting. Full per-dependency commands and re-check instructions: [`${CLAUDE_PLUGIN_ROOT}/references/dependencies.md`](../../references/dependencies.md). Shape per item:

> "Missing: **{name}** — provides {what}. Install now with `{command}`? [y/n]"

+ `y` → print the exact command (or run it for safe, user-scoped installs like `pip install graphifyy` after confirmation), then RE-RUN the row's detection check and report the result.
+ `n` → continue; the pipeline works without it, the dependent feature is skipped.

**Persist the result** in `.weside/config.json` (Step 3 merges it):

```json
"tools": { "graphify": true, "turbovault": true, "superpowers": false, "codex": false },
"engines": []
```

`engines` is a list of profile names from `.weside/engines.local.json` that were successfully probed — starts empty, filled by Step 2's executor wizard.

Downstream skills read `tools.*` from config to decide whether to offer graph/vault features — they still verify empirically before each actual call (config can go stale) and only skip when the real call says "not found".

**TurboVault DEGRADED is the silent-killer case — call it out loudly.** A registered-but-dead MCP passes a name-only check and then every doc search silently falls back to grep for weeks. If the liveness probe fails, persist `"turbovault": false` AND warn explicitly:

> "⚠️ TurboVault MCP is registered but NOT responding — `list_vaults` failed. Doc search (`/we:docs`, `/search`, `/we:story`) is running on grep fallback, which is much weaker. Restart the session or check the MCP config (`~/.claude.json` / `~/.claude/settings.json`)."

**Do NOT block.** This is informational — the pipeline works without these plugins. Downstream skills (e.g. `/we:build` Step 4) MUST trust this gate: they invoke the prerequisite directly and only skip when the actual tool call returns "not found", never on assumption.

### Step 1c: Activate Pre-Commit Hooks

If the repo ships a `.pre-commit-config.yaml`, the `/we:*` pipeline assumes its hooks are actually installed (e.g. a `post-commit` graph rebuild, a `commit-msg` linter). Activate them so the user doesn't have to remember the incantation — generic, works for any repo:

1. **No `.pre-commit-config.yaml`** → skip silently.
2. **`pre-commit` not installed** (`command -v pre-commit` fails) → inform + offer `pip install pre-commit`, then continue. Do NOT block.
3. **`core.hooksPath` set to a non-default path** (`git config core.hooksPath` returns something other than `.git/hooks` / empty — e.g. Husky) → **warn and skip**, never clobber a custom hooks setup:
   > "⚠️ `core.hooksPath` is set to a custom dir — skipping pre-commit hook install to avoid clobbering it. Install hooks manually if intended."
4. **Otherwise** → collect every distinct stage the config declares (each hook's `stages:`, plus top-level `default_install_hook_types:` / `default_stages:`), always including the `pre-commit` baseline, and run `pre-commit install --hook-type <each>` per distinct stage. Report what was activated. Idempotent — safe to re-run. If one `--hook-type X` errors (a stage renamed across pre-commit versions), report it and continue with the rest.

### Step 2: Ask 4 Questions + Executor Wizard

```
1. "Do you have a product vision? (Link, file, or brief description)"
   → If yes: save to .weside/vision.md
   → If no: "No problem — we'll skip vision checks for now."

2. "Which ticketing tool? (Auto-detected: {detected})"
   → Confirm or override
   → If Jira: "What's your project key? (e.g. 'PROJ')"

3. "Stack detected: {detected}. Correct?"
   → Confirm or override

4. "Which code reviewers does this repo use? (Auto-detected: {detected})"
   → Detect candidates: codex plugin installed → suggest `codex`;
     a CodeRabbit/Greptile GitHub App or review-gate workflow present → suggest those.
     `claude` (the local code-reviewer agent) is always available.
   → **Codex detected → suggest `["codex", "claude"]`** (codex = the local adversarial
     pass when Claude wrote the code; claude = the CI second opinion). No codex →
     default `["claude"]`. The list seeds the CI-bot allowlist; it does NOT rank local
     reviewers (see Reviewer-id semantics below).
   → Confirm or override.
   → "Add another reviewer? (free-text id, e.g. a custom bot — leave empty to finish)"
     → accept any id; unknown ids are treated as CI bots (allowlisted, not run locally).
   → Default when nothing else is detected: ["claude"].
```

#### Executor wizard (after Q4, non-blocking)

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

Ask: *"Enable cross-review? When workers write code, the other engine reviews it
(Claude wrote → Codex adversarial-review; other engine wrote → Claude code-reviewer).
[y/n, default y]"*

+ `y` → persist `"review": { ..., "cross": true }`
+ `n` → persist `"review": { ..., "cross": false }`

Show a one-line explanation why cross-review matters: *"Different models catch different
things — the reviewer is the engine that didn't write the code."*

**Reviewer-id semantics (single source of truth — other skills reference this):**

+ `claude` → the local `code-reviewer` agent. Runs as the local reviewer when no codex is present, when codex/a foreign engine wrote the code, and is the Claude second opinion on GitHub CI. Locally invokable.
+ `codex` → local `/codex:adversarial-review` via the codex plugin's `codex-companion.mjs`. The local adversarial pass when Claude wrote the code. Locally invokable (needs the codex plugin).
+ `coderabbit` / `greptile` / **any other id** → CI bots. They run on GitHub via App/workflow — the plugin does NOT invoke or gate them; it only *allowlists* their threads for `/we:ci-review` to collect. Not locally invokable.

**Exactly ONE local reviewer runs, chosen by who wrote the code** — not by list order and not by a count. The reviewer is the engine that did NOT write the code: Claude wrote + `tools.codex` + `review.cross` → `/codex:adversarial-review` (and the `code-reviewer` agent does NOT also run); codex/foreign wrote, or no codex → `code-reviewer`. `review.available`'s only job is to seed the CI-bot allowlist `/we:ci-review` collects from; its order is cosmetic for local review.

### Step 3: Save Configuration

Always write `.weside/config.json` with the choices from Step 2 — the ticketing and stack configuration must persist **even if the Companion Framework (Step 5) is declined**:

```json
{
  "ticketing": { "tool": "<jira|github-issues|none>", "project_key": "<KEY-or-null>" },
  "stack": ["<detected stacks>"],
  "tools": { "graphify": false, "turbovault": false, "superpowers": false, "codex": false },
  "engines": ["<profile-name-if-created>"],
  "execution": { "default": "claude-sonnet" },
  "review": { "available": ["claude"], "cross": true }
}
```

The `tools` block carries the Step 1b detection results (idempotent: re-running setup re-detects and overwrites only this block).

The `engines` block lists the profile names created/verified in the executor wizard.

The `execution.default` block is the executor the user picked: `"claude-sonnet"` / `"claude-haiku"` / `"codex"` / `"<engine-profile-name>"`.

The `review.available` block is the reviewer list from Step 2 Q4 (order cosmetic — see Reviewer-id semantics). The `review.cross` field is the cross-review toggle from the executor wizard (default `true`). Consumed by `/we:build`, `/we:develop`, and `/we:orchestrate`. Absent block → skills fall back to Claude-only review (back-compat).

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

These files are **additive**, never a replacement: `/we:story` and `/we:build` read `.weside/dor.md` alongside the plugin DoR, and the `code-reviewer` agent reads `.weside/dod.md` alongside the plugin DoD — both sets of items apply.

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
Cross-review:   on  (or: off)
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
| "Custom DoR/DoD?" | Quality gates prevent rework — catching issues early is 10x cheaper |

**Never block.** Every question has a "skip" path. The user can always run `/we:setup` again later.

---

## Rules

+ NEVER block on any question — always allow skip/default
+ NEVER create .weside/ without user consent
+ Auto-detection first, confirmation second
+ Three CORE questions maximum (Step 2); Step 5 (Framework) is optional and asks once
+ Works without ANY configuration (defaults for everything)
+ **Idempotent.** Re-running never overwrites existing config silently. Report current state, ask before replacing.
+ **Respects existing frontmatter.** Step 5 only *reports* — does not rewrite docs. Migration is explicit user-triggered via `/we:docs` or doc-architect agent.
+ **Standalone-first.** If weside MCP is unavailable, Step 5 still creates `.weside/config.json` + invokes onboarding (stub crew). No feature silently disappears.

## References

+ `we/skills/onboarding/SKILL.md` — invoked by Step 5
+ `we/skills/sideload/SKILL.md` — counterpart for "already set up"
+ `we/skills/CLAUDE.md` — design rationale, open questions, frontmatter vocabulary
