---
type: story-plan
story: "31"
created: 2026-06-26
updated: 2026-06-27
status: approved
parallel_groups: [[2, 3], [9, 10]]
review_intensity: standard
---

# Plan: Lightweight runtime-agnostic execution — lead orchestrates, cheap/foreign workers implement, engines cross-review

## Context

The `we` plugin's execution model assumes Claude Code on whatever model the session runs (in practice
Opus — expensive) does *everything*: plan, implement, review, ship. Two real sessions exposed the cost:
running an integration with N workers, each on a full `/we:build`, paid N CI cycles plus the integration
CI, all on the most expensive model. The user's direction turns this inside out.

**The new stance: the expensive plan (Claude Max) is for planning, orchestration, and review only.** The
actual implementation is pushed down to a cheaper or foreign engine — by preference Codex on its own
subscription, otherwise a cheaper Anthropic tier or any Anthropic-compatible LLM. Because the plugin is
open-source, *every* part of this is the user's choice and degrades gracefully to today's all-Claude-Code
behaviour when nothing is configured.

Four threads land here:

1. **A dedicated worker slice (`/we:develop`).** Implementation is split from integration. A worker does
   the **development slice only** — implement the chunk, run the **local** quality gates, commit, push its
   branch, and **stop**. No PR, no per-worker CI/review loop. `/we:orchestrate` dispatches workers that run
   `/we:develop`; the Lead integrates onto one branch and runs the full CI + review **once**. `/we:build`
   stays untouched as the fast, clean **solo** path for a single Story that doesn't warrant orchestration.

2. **Any-engine workers via an engine launcher.** Workers run on (a) a cheaper Anthropic tier by default
   (the Agent `model` param — Sonnet/Haiku — Lead stays on the session model), or (b) **Codex** (own
   subscription), or (c) a **foreign Anthropic-compatible LLM** (GLM, Kimi, MiniMax, Qwen, Bedrock, a
   LiteLLM/ccr proxy). The foreign path is a headless `claude -p` with `ANTHROPIC_BASE_URL` /
   `ANTHROPIC_AUTH_TOKEN` / `ANTHROPIC_MODEL` set per an **engine profile**. The user's personal `clauded`
   script is the *template* for this — it is **not shippable** (hard-coded secrets, personal). The plugin
   ships its **own** launcher (`we/scripts/worker-launch.sh`) that reads a profile from config and execs
   `claude -p --cwd <chunk worktree>`. Research (musistudio `claude-code-router`/"ccr", LiteLLM proxy,
   Alibaba Model Studio, MiniMax, Kimi, Bedrock) confirms env-var routing is the de-facto standard and that
   neither router is *required* — a direct Anthropic-compatible endpoint works.

3. **Engines cross-review each other.** Whoever wrote the code, the **other** engine reviews it. Claude
   wrote → Codex `/codex:adversarial-review`. Codex wrote → the local Claude `code-reviewer`. The pieces
   already exist (the official Codex plugin ships `adversarial-review`; the plugin ships `code-reviewer`).
   `review.cross: true` is the default, switchable per-repo in `.weside/config.json`, and applies to
   `/we:build`, `/we:develop`, and `/we:orchestrate`. A repo without a Codex/foreign engine sets it false
   and runs Claude-only — no degradation.

4. **Lead latitude over a rigid path.** Orchestrate today prescribes one path (full `/we:build` per chunk,
   fixed ≤2 cap, fixed step order, spike status). The user wants those to be **defaults with explicit
   override** — the Lead holds the context and is trusted to pick executor, model, chunk granularity, and
   integration shape. Safety rails stay (cap as default, human merge gate, verify-before-trusting-done);
   the spike framing graduates.

Non-obvious constraints carried from the original #31 (still true): (a) the official Codex plugin is
`openai/codex-plugin-cc` (third-party, OpenAI's) — declare it *optional/recommended*, never vendor or
hard-depend; (b) `/codex:task` now ships from the plugin (`we/commands/codex/task.md`); the repo-local
`weside-core/.claude/commands/codex/task.md` deletion is sequenced with the version bump so the slash
command never has a dead window; (c) the Agent tool already exposes a `model` param
(`sonnet`/`haiku`/`opus`), so model-tiered Claude-Code workers need no new runtime — only a skill
convention; (d) a foreign-engine worker cannot use the in-session Agent tool (it inherits the session's
provider/auth) — it must be a separately-spawned headless `claude -p` with its own env, which is what the
launcher does; (e) the official Codex plugin (v1.0.4) ships `review`, `adversarial-review`, `rescue`,
`result`, `status`, `cancel`, `setup` + a `codex-rescue` agent — **no `task`** — so the plugin's
`/codex:task` does not collide.

## Acceptance Criteria

### Worker slice + single CI

1. **Given** a chunk to implement **When** a worker (Agent teammate, Codex, or foreign-engine) runs it via
   `/we:develop` **Then** it does only the **development slice** — implements the chunk, runs the **local**
   quality gates (lint/type/test for the touched stack), commits, and pushes its branch — and does **NOT**
   open a PR or run a per-worker CI/review-fix loop. "Stop after local-green + pushed" is the contract,
   stated explicitly in the brief.
2. **Given** `/we:develop` is invoked directly (no orchestration) **Then** it runs the same dev-only slice
   for one Story/chunk and stops at local-green + pushed — a usable standalone skill, not only a worker
   brief.
3. **Given** multiple workers have pushed chunk branches **When** the Lead integrates **Then** it merges
   them onto **one** integration branch and runs the full CI + review-fix loop **exactly once** on the
   integration→main PR — not once per worker. The skill documents the integration-branch pattern as the
   default for ≥2 chunks/stories with the CI-cost math.
4. **Given** `/we:build` is invoked for a single Story **Then** it still runs the full unchanged solo
   pipeline to a reviewable PR — it is the documented fast path for work not worth orchestrating; the docs
   frame `/we:orchestrate` as the default for multi-chunk/integration work and `/we:build` as the solo
   exception.

### Any-engine workers + launcher

1. **Given** a Claude-Code worker is dispatched for a dev-only chunk **Then** it runs on a **cheaper
   Anthropic tier by default** (Agent `model` — Sonnet for normal chunks, Haiku for mechanical) while the
   **Lead stays on the session model**. The skill makes cheap-worker/expensive-Lead the documented default
   and names when to override upward (a hard chunk worth Opus — a worker may be Opus when justified).
2. **Given** an engine profile is configured in `.weside/engines.local.json` **When** the Lead dispatches a
   foreign/cheaper engine worker **Then** `we/scripts/worker-launch.sh` launches a headless `claude -p`
   with the profile's `ANTHROPIC_BASE_URL` / `ANTHROPIC_AUTH_TOKEN` (resolved from a key-reference) /
   `ANTHROPIC_MODEL`, scoped to the chunk worktree (`--cwd`), and the Lead reviews + integrates its diff
   like any other worker. **Given** no engine profile **Then** workers fall back to the cheap Anthropic
   tier (any-engine AC 1) with no degradation.
3. **Given** an engine profile **Then** it stores only `base_url`, `model`, and a **key-reference** (an
   env-var name or a pointer into `~/.weside/secrets.env`, chmod 600) — never a raw key in any repo file
   (the file is gitignored regardless). The launcher passes the key by env and **never logs its value**.
4. **Given** Codex is configured (`tools.codex = true`) and the user opts in **When** `/we:orchestrate`
   dispatches a chunk **Then** the Lead may dispatch it to Codex (single-detach pattern,
   `references/codex-dispatch.md`) and still reviews + integrates; exactly one backgrounding mechanism is
   used and the Lead verifies the worktree actually changed before trusting "done". **Given** Codex
   absent/false **Then** chunks run on Claude Code with no degradation.

### Cross-review

1. **Given** `review.cross = true` (default) **When** code is produced by an engine **Then** the **other**
   engine reviews it: Claude-written code → Codex `/codex:adversarial-review`; Codex-written code → the
   local `code-reviewer` agent. Applies in `/we:build`, `/we:develop`, and `/we:orchestrate` integration.
   **Given** `review.cross = false` or no second engine available **Then** review runs Claude-only with no
   degradation.

### Setup + config

1. **Given** a fresh project **When** the user runs `/we:setup` **Then** it (a) probes for `codex` and any
   configured engine profile (non-blocking), (b) asks the user's **default executor** (cheap Claude tier /
   Codex / a named engine profile), (c) helps create `.weside/engines.local.json` + gitignore it + guides
   secret placement without storing a raw key, and (d) sets `review.cross` — all persisted to `.weside`,
   never blocking when anything is absent.

### Lead latitude

1. **Given** orchestrate's defaults (dev-only chunk per worker, ≤2 concurrent cap, integration-branch
   shape) **When** the Lead judges the task needs a different shape **Then** the skill prose grants
   **explicit latitude** to adapt executor, model, chunk granularity, and integration shape — defaults
   remain, stated as defaults-with-override, not a forced path. The ≤2 cap stays the safety default; the
   skill names when the Lead may raise it. The spike status is removed.

### Docs + release

1. **Given** the README, `we/CLAUDE.md`, and the tour (`tour/`) **Then** they describe the model
   accurately — Claude Code solo `/we:build` as the fast path, `/we:orchestrate` + `/we:develop` as the
   lightweight default for multi-chunk work, cheap-tier workers default, Codex + foreign engines optional,
   engines cross-review — **no over-claim beyond what is wired**.
2. **Given** the release **Then** the plugin version is bumped (minor — new capability) and the changelog
   notes the worker-slice / any-engine / cross-review capabilities. The weside-core `/codex:task` deletion
   is sequenced here.

## User Journey

1. User installs the we-plugin (and optionally the official Codex plugin and/or configures an engine
   profile for a cheaper/foreign LLM).
2. Runs `/we:setup` — picks a default executor, sets up an engine profile (Codex or foreign) with the
   secret guidance, confirms cross-review. Sees the roster: "Workers: Claude Code (Sonnet/Haiku) default ·
   Codex: available/absent · Engine `<name>`: configured/absent · Cross-review: on".
3. For a quick single Story → `/we:build KEY` (solo, fast, Claude reviews + Codex adversarial-reviews if
   cross is on).
4. For multi-chunk / integration work → `/we:orchestrate <ticket-or-epic>`. At each chunk the Lead picks an
   executor (cheap Claude tier by default; Codex or a foreign engine when configured + confirmed) and
   briefs it **dev-only** via `/we:develop` — implement, local gates, push, stop. The other engine
   cross-reviews each chunk.
5. Workers push chunk branches; the Lead integrates onto one branch, reviews neutrally, runs CI +
   review-fix **once**, opens one integration→main PR; the human merges.
6. User reads the tour and understands: expensive plan plans + orchestrates + reviews, cheap/foreign
   engines implement, and the two engines keep each other honest.

## Testing Requirements

- The plugin is markdown-skills + `orchestration.py` + the new launcher script; "tests" are mostly
  **doc/skill consistency checks** + manual dry-runs.
- Unit: `we/scripts/worker-launch.sh` gets a runnable self-check (a `--dry-run`/`demo` that asserts it
  builds the right env from a fixture profile and **never echoes the key**). If any `orchestration.py`
  helper gains executor/engine/config-read logic, add a pytest (`scripts/test_*`).
- Manual: `/we:setup` on repos with/without `codex` and with/without an engine profile → correct config
  persistence, gitignore entry, no raw key in any repo file, non-blocking.
- Manual: `/we:develop KEY` standalone → produces a pushed branch, local-green, NO PR, NO per-worker CI.
- Manual: `/we:orchestrate` dry-run dispatching one chunk to a cheap Claude worker, one to Codex
  (single-detach), one to a foreign engine (launcher) — all **dev-only**, all integrated by the Lead onto
  one branch with a **single** CI run, each cross-reviewed by the other engine.
- Manual: flip `review.cross` false → confirm no second-engine review fires.
- Lint: `markdownlint-cli2` + the plugin's frontmatter validator on every touched `.md`;
  `shellcheck` on `worker-launch.sh`.

## Technical Approach

**Patterns:** Claude Code plugin command/skill authoring (markdown + frontmatter). Optional-capability
detection mirrors the existing `/we:setup` Step 1b empirical-probe (`command -v codex`, persist to
`.weside/config.json` `tools.*`, never block). Executor + model selection in `/we:orchestrate` is
**skill-prose the Lead reads + acts on** (no runtime code) plus shared references. The genuinely new code
is one small launcher: `we/scripts/worker-launch.sh` reads an engine profile from
`.weside/engines.local.json`, resolves the key by reference (env-var name, or sources `~/.weside/secrets.env`),
and execs `claude -p "<chunk brief>"` with `ANTHROPIC_BASE_URL`/`ANTHROPIC_AUTH_TOKEN`/`ANTHROPIC_MODEL`,
`--cwd <chunk worktree>` — never logging the key. The Lead dispatches it over Bash with the same
single-detach + verify-worktree-changed discipline as Codex. Cross-review is wiring of existing pieces
(`/codex:adversarial-review` and the `code-reviewer` agent), gated on `review.cross` + which engine wrote
the code.

**Engine profile schema** (`.weside/engines.local.json`, gitignored):
```json
{
  "<engine-name>": {
    "base_url": "https://api.z.ai/api/anthropic",
    "model": "glm-5",
    "key_ref": { "env": "ZAI_TOKEN" }
  }
}
```
`key_ref` is one of `{ "env": "<VAR_NAME>" }` or `{ "secrets_env": "<KEY_NAME>" }` (looked up in
`~/.weside/secrets.env`). No raw token in the repo, ever.

## Implementation Phases

### Phase 1: (done — foundation) /codex:task in the plugin + Codex optional dep + setup probe

- **Status:** Already landed in this worktree (commits `29ab4b3`, `e45a4ac`, `f3d295d`, `4a27da9`). Keep.
- Covers: `/codex:task` ships from the plugin, `references/codex-dispatch.md`, Codex declared
  optional/recommended, `/we:setup` Step 1b `tools.codex` probe, Mode-B Codex executor selection in
  `/we:orchestrate`. The weside-core deletion is still pending → sequenced into Phase 11.

### Phase 2: Engine config — schema, gitignore, secret handling

- **Goal:** A documented `.weside/engines.local.json` profile schema + secret-by-reference convention.
- **Files:** `we/references/dependencies.md` (engine-profile schema + key handling), a short
  `we/references/engines.md` if dependencies.md gets too long.
- **Approach:** Define the profile shape, the `key_ref` forms, the gitignore requirement, and the
  `~/.weside/secrets.env` (chmod 600) convention. No raw key in any repo file. Document the
  no-router-required stance (direct Anthropic-compatible endpoint) + that a router (ccr/LiteLLM) is an
  optional front for the `base_url`.

### Phase 3: worker-launch.sh — the engine launcher (the one code piece)

- **Goal:** A worker can run as a headless `claude -p` on a configured cheaper/foreign engine.
- **Files:** `we/scripts/worker-launch.sh` (NEW), `we/references/worker-dispatch.md` (invocation +
  verify-worktree-changed discipline).
- **Approach:** Reads the named profile, resolves the key by reference (env or `secrets.env`), execs
  `claude -p "<brief>"` under the profile env, `--cwd <chunk worktree>`. Single-detach when backgrounded.
  Ships a `--dry-run` self-check that prints the resolved env **with the key value redacted** and asserts
  the key is never echoed. `shellcheck`-clean. Graceful: no profile → never invoked, AC5 cheap-tier Agent
  worker is the fallback.

### Phase 4: /we:develop — the dev-only worker slice (NEW skill)

- **Goal:** A skill that does implement + local gates + commit + push + stop, runnable standalone and as a
  worker brief.
- **Files:** `we/skills/develop/SKILL.md` (NEW), `we/references/worker-dispatch.md` (the dev-only contract
  lives here, linked from the skill).
- **Approach:** Reuse `/we:build` Step 1–5 logic (DoR-lite, worktree, implement per plan phase, local
  lint/type/test) but **stop after local-green + push** — explicitly NO `/we:pr`, NO Step 8 CI loop. On its
  own diff, run the cross-review (other engine) when `review.cross` is on. Reports a short structured
  result (branch, local-gate status, cross-review verdict) for the Lead. Honours `parallel_groups` when run
  standalone over a multi-phase plan.

### Phase 5: /we:orchestrate — workers run /we:develop; generalized executor selection

- **Goal:** Mode B is the default front door; workers run `/we:develop`; the Lead picks executor per chunk
  (cheap Claude default | Codex | foreign engine).
- **Files:** `we/skills/orchestrate/SKILL.md` (rewrite the Builder/Chunk brief to dispatch `/we:develop`,
  not the full `/we:build`; generalize the executor subsection to three backends reading
  `tools.codex` + the engine profiles; integration-branch + single-CI as the default for ≥2 chunks with the
  CI-cost math), `we/references/worker-dispatch.md`, `we/references/codex-dispatch.md` (exists).
- **Approach:** Executor + model selection is prose the Lead acts on; gate Codex/foreign behind their
  config + an explicit per-chunk confirm; reuse the review/integration path; the Lead runs the single CI on
  the integration PR.

### Phase 6: Lightweight worker contract + cross-review at integration

- **Goal:** The dev-only contract and the cross-review pairing are documented once and linked.
- **Files:** `we/references/worker-dispatch.md` (dev-only contract, model-tier defaults, engine launcher
  invocation, cross-review pairing by who-wrote-it, integration-branch/single-CI), `we/skills/orchestrate/SKILL.md`.
- **Approach:** Replace the "run the COMPLETE /we:build incl. Step 8" brief with the dev-only brief + the
  cross-review step. Document why (the N-CI-cycle waste). (Phases 5 + 6 both edit the orchestrate skill
  heavily — sequence them, do NOT parallelise.)

### Phase 7: Lead-latitude pass — defaults-with-override; drop the spike

- **Goal:** De-rigidify the skill: defaults stay, the Lead is explicitly trusted to adapt; remove the spike
  framing.
- **Files:** `we/skills/orchestrate/SKILL.md`.
- **Approach:** Reword the prescriptive sections (chunk-per-worker, ≤2 cap, fixed order) as defaults with
  named override conditions; keep safety rails (cap default, human merge gate, verify-before-done). Remove
  the "Spike status" block; frame orchestrate as the graduated default for multi-chunk work.

### Phase 8: /we:setup wizard — default executor, engine profile, cross-review

- **Goal:** Setup helps the user configure the whole model and persists it to `.weside`.
- **Files:** `we/skills/setup/SKILL.md`, `we/references/dependencies.md`.
- **Approach:** Extend Step 1b (probe engine profiles alongside `codex`) and Step 2 (ask default executor;
  offer to create `.weside/engines.local.json` + add it to `.gitignore` + guide secret placement into
  `~/.weside/secrets.env` without the plugin touching the raw key; ask `review.cross`). Persist
  `execution.default`, the engine list, and `review.cross`. Non-blocking throughout.

### Phase 9: /we:build — cross-review + demote to solo fast path

- **Goal:** `/we:build` stays the fast solo path; gains cross-review; docs frame it as the exception.
- **Files:** `we/skills/build/SKILL.md` (Step 5/8: when `review.cross` + a second engine, run the other
  engine's review on Claude's output), README/we:CLAUDE positioning.
- **Approach:** Minimal — add the cross-review hook reading `review.cross`; do not otherwise change the
  pipeline. (Phases 9 + 10 are disjoint docs/skill edits once 4–8 are real.)

### Phase 10: Docs + tour

- **Goal:** README, `we/CLAUDE.md`, `tour/` describe the wired model.
- **Files:** `README.md`, `we/CLAUDE.md`, `tour/`.
- **Approach:** Update claims to match wired reality; no over-claim. Tour: expensive plan plans +
  orchestrates + reviews; cheap/foreign engines implement; engines cross-review.

### Phase 11: Version bump + changelog + sequence the weside-core deletion

- **Goal:** Ship it.
- **Files:** `we/.claude-plugin/plugin.json` (bump from 2.60.x), changelog,
  `weside-core/.claude/commands/codex/task.md` (DELETE — cross-repo, only once the bumped plugin is the
  resolving source).
- **Approach:** Minor bump (new capability). Sequence the weside-core `/codex:task` deletion here so
  slash-command resolution never has a dead window.

> **parallel_groups [[2,3],[9,10]]:** Phase 1 is done (foundation). Phases 2+3 are disjoint (config schema
> vs launcher code) — parallel. Phase 4 (`/we:develop`) depends on 3's launcher + 2's schema. Phases 5+6+7
> all edit the orchestrate skill heavily — **serial, same file**. Phase 8 (setup) depends on the config
> contract from 2. Phases 9+10 are disjoint docs/skill edits once 4–8 land — parallel. Phase 11 last
> (sequences the deletion). The orchestrate-skill phases (5,6,7) are the critical path — the actual
> "lightweight rebuild".

## Design Decisions

| Decision | Alternatives Considered | Why This |
|----------|------------------------|----------|
| `/we:develop` as a separate dev-only skill | Worker runs full `/we:build`; or merge build into develop | A worker running full `/we:build` opens its own PR + CI = N CI cycles (the waste). A clean dev-only slice the Lead integrates is the fix. Keeping `/we:build` separate preserves the fast solo path; a separate `/we:develop` is clearer than a `--dev-only` flag on build. |
| `/we:build` stays standalone, unchanged pipeline | Demote it into a develop+orchestrate combo | Single Stories not worth orchestration overhead deserve a fast clean path. Build earns its keep; orchestrate is the default only for multi-chunk/integration work. |
| Plugin ships its own launcher; `clauded` is template-only | Ship a copy of `clauded`; ask users to point at their own script | `clauded` has hard-coded secrets and is personal — not shippable. A plugin-owned launcher reading a config profile is reproducible and safe; setup helps the user fill the profile. |
| Engine profiles per-repo, gitignored; keys by reference | User-global profiles; inline keys at 600 | User chose per-repo (repo is the config unit). Keys stay out of every repo file (referenced from `~/.weside/secrets.env` or an env var) so "one subscription, many repos" still works and no token is ever committed. |
| Cross-review = the other engine, `review.cross` default-on, per-repo switchable | Always-on everywhere; opt-in only | "Whoever wrote it, the other reviews" catches what one engine misses (different training/bias). Default-on honours the user's "immer"; the per-repo switch respects repos without a second engine and the cost of every Codex run. |
| Cheap-tier workers, Opus Lead, by default; a worker may be Opus | All-Opus (today) / all-cheap | Real implementation is the expensive part — push it to Sonnet/Haiku/Codex/foreign; keep the expensive plan for the Lead's context-holding + review. Override upward for genuinely hard chunks. |
| Foreign engine via headless `claude -p` + launcher | In-session Agent tool with a foreign model | The Agent tool inherits the session provider/auth — it cannot point at a foreign base-URL. A separate headless process with its own env is the only way; the launcher keeps it a one-liner for the Lead. |
| Defaults-with-override (Lead latitude); drop the spike | Keep the rigid prescribed path + spike status | The Lead holds the context; boxing it into one path made orchestrate feel heavy. Trust the Lead, keep safety rails as defaults. The capability is graduating from spike. |
| Single coherent Story, phased | Epic of N stories | One coherent capability (lightweight runtime-agnostic execution), phased — not many independent slices. Large (11 phases, one done) but coherent. |

## Code Guidance

**DO:** mirror the `/we:setup` Step 1b empirical-probe + `tools.*` persistence for `tools.codex` and the
engine profiles; keep the single-detach rule in ONE shared reference (`codex-dispatch.md`) and link it; put
the dev-only worker contract + cross-review pairing + integration-branch/single-CI + model-tier defaults in
`references/worker-dispatch.md` and link from both `/we:develop` and `/we:orchestrate`; keep every backend
strictly opt-in with the cheap-Claude-Code-worker default; the launcher resolves keys by reference and
**never logs the key value** — store only the env-var name / secrets-file key name in any repo file; verify
the worktree changed before trusting any worker's "done"; English for all plugin-shipped text;
`shellcheck`-clean the launcher with a redacting `--dry-run` self-check.

**DON'T:** hard-depend on or vendor the Codex plugin; ship or hard-code `clauded`; brief a worker to run a
full `/we:build` with its own PR + CI loop (that is the overhead this story removes); run N per-worker CI
cycles when one integration CI suffices; point the in-session Agent tool at a foreign LLM (use the headless
launcher); write a raw API key into any repo file (even gitignored) or log it; over-claim in README/tour
beyond what is wired; re-introduce the double-detach; delete the weside-core `/codex:task` before the
bumped plugin is the resolving source.

## Security Review Required

No — no money/tenant/auth path in the plugin itself. Cautions: the launcher reads a key by reference and
must **never** log or commit the value — the engine profile stores only the env-var/secrets-file key
*name*; `.weside/engines.local.json` is gitignored; `~/.weside/secrets.env` is chmod 600; don't hard-couple
the third-party Codex plugin.

## Documentation Impact

- [x] **README/Setup** — README recommended-plugins + Requirements; `/we:setup` wizard (default executor +
      engine profile + cross-review).
- [x] **Architecture docs** — `we/CLAUDE.md` runtime/cost-backends note; `references/codex-dispatch.md`
      (exists), `references/worker-dispatch.md` (NEW), `references/dependencies.md` (engine schema).
- [x] **User-facing docs** — the interactive tour (`tour/`).
- [ ] **API docs** — n/a.
