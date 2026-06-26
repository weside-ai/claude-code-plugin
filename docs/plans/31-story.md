---
type: story-plan
story: "31"
created: 2026-06-26
status: approved
parallel_groups: [[2, 3]]
review_intensity: standard
---

# Plan: Runtime-agnostic execution — Codex as a first-class optional backend

## Context

The `we` plugin's execution model has always assumed Claude Code (Agent teammates, built-in
tools). This session proved Codex (`gpt-5-codex`) is a viable second execution backend — a real
`/we:orchestrate` Mode-B build (WA-1446 Flux migration) was implemented by dispatching chunks to
Codex while the Lead reviewed + integrated. The user's direction: the plugin should run with
**Claude Code AND Codex**, with Codex as an **opt-in, gracefully-degrading** backend (never a hard
requirement — Claude-Code-only users must not be forced to install Codex).

2.59.0 already shipped the *honest bounded* groundwork: README + `we/CLAUDE.md` document Codex as an
optional Mode-B executor, `/we:orchestrate` carries the executor-pluggability note, `/we:setup` has
a Codex detection row, and the **single-detach dispatch rule** is baked into the orchestrate skill
(the bug that triggered all this: `/codex:task --background` + Bash `run_in_background` double-detaches
and orphans the job). This story turns that documentation into a **wired** feature.

Non-obvious constraints: (a) the official Codex plugin is `openai/codex-plugin-cc` (third-party,
OpenAI's) — we can declare it as an *optional/recommended* dependency but must not vendor or hard-depend
on it; (b) `/codex:task` currently lives in `weside-core/.claude/commands/codex/task.md` (repo-local) —
it is generic (no weside coupling) and belongs in the plugin so every plugin user gets it; moving it is
**cross-repo** (create in plugin, delete in weside-core); (c) the installed plugin cache lags the source
repo, so the moved command resolves from the plugin only after the next plugin update — until then the
weside-core copy is what answers `/codex:task`, so the deletion must be sequenced with a version bump +
re-publish, not done blind.

## Acceptance Criteria

1. **Given** the we-plugin is installed **When** a user runs `/codex:task <prompt>` **Then** the command
   resolves from the plugin (`we/commands/codex/task.md`), and the repo-local
   `weside-core/.claude/commands/codex/task.md` no longer exists.
2. **Given** a fresh project **When** the user runs `/we:setup` **Then** it probes for the `codex` CLI,
   reports it as an optional backend (present/absent), and persists `tools.codex` in `.weside/config.json`
   — never blocking when absent.
3. **Given** `tools.codex = true` and an explicit user opt-in **When** `/we:orchestrate` dispatches a
   Mode-B chunk **Then** the Lead may dispatch it to Codex (using the single-detach pattern) instead of an
   Agent teammate, and still reviews + integrates the result. **Given** `tools.codex` is false/absent
   **Then** Mode-B runs on Claude Code Agent teammates with no degradation.
4. **Given** the Codex backend is dispatched **When** the chunk runs **Then** exactly one backgrounding
   mechanism is used (companion `--background` + Bash foreground, OR companion foreground + Bash
   background) — never both — and the Lead verifies the worktree actually changed before trusting "done".
5. **Given** the README, `we/CLAUDE.md`, and the interactive tour (`tour/`) **Then** they describe the
   runtime-agnostic model (Claude Code default, Codex optional) accurately — no over-claim beyond what is
   wired.
6. **Given** the release **Then** the plugin version is bumped and the new capability is noted.

## User Journey

1. User installs the we-plugin (and, optionally, the official Codex plugin).
2. Runs `/we:setup` — sees "Codex backend: available (optional)" or "absent — Mode-B runs on Claude Code".
3. Runs `/we:orchestrate <ticket>`; at a Mode-B chunk dispatch the Lead offers the Codex backend when
   available; the user confirms (or stays on Claude Code).
4. The chunk is implemented by the chosen backend; the Lead reviews + integrates; one PR.
5. User reads the tour and understands the plugin runs on either runtime.

## Testing Requirements

- The plugin is markdown-skills + `orchestration.py`; "tests" here are mostly **doc/skill consistency
  checks** + a manual dry-run.
- Unit: if any `orchestration.py` helper gains executor-selection logic, add a pytest for it
  (`scripts/test_*`). Otherwise none.
- Manual: `/we:setup` on a repo with and without `codex` CLI → correct `tools.codex` + non-blocking.
- Manual: a `/we:orchestrate` Mode-B dry-run dispatching one chunk to Codex (single-detach) and one to an
  Agent teammate, both reviewed by the Lead.
- Lint: `markdownlint-cli2` + the plugin's frontmatter validator on every touched `.md`.

## Technical Approach

**Patterns:** Claude Code plugin command/skill authoring (markdown + frontmatter). Optional-dependency
detection mirrors the existing `/we:setup` Step 1b empirical-probe pattern (`command -v codex`, persist to
`.weside/config.json` `tools.*`, never block). Executor selection in `/we:orchestrate` is **skill-prose**
the Lead reads + acts on (no runtime code) + a shared `references/codex-dispatch.md` carrying the
single-detach rule once, referenced from both the orchestrate skill and the `/codex:task` command.

## Implementation Phases

### Phase 1: Move /codex:task into the plugin (cross-repo)

- **Goal:** `/codex:task` ships from the plugin; the repo-local copy is gone.
- **Files:** `claude-code-plugin/we/commands/codex/task.md` (NEW — fixed single-detach content, English
  toast for distribution), `weside-core/.claude/commands/codex/task.md` (DELETE — cross-repo).
- **Approach:** Copy the already-fixed `task.md` into the plugin under `we/commands/codex/`. English-ize
  the user-facing toast. Sequence the weside-core deletion with the plugin version bump (Phase 6) so the
  slash command never has a dead window — delete only once the bumped plugin is the resolving source.

### Phase 2: Declare the Codex plugin as an optional dependency

- **Goal:** The official Codex plugin is a documented *optional/recommended* dependency, never hard.
- **Files:** `we/.claude-plugin/plugin.json` (if the manifest supports an optional-deps/recommended
  field — verify; else document-only), `we/references/dependencies.md`, `README.md` (recommended-plugins
  row already added in 2.59.0 — reconcile).
- **Approach:** Add the `codex` row to the per-dependency reference with install command
  (`openai/codex-plugin-cc`) + the "absent → Claude Code default" degradation note.

### Phase 3: /we:setup Codex capability check + config

- **Goal:** `/we:setup` detects `codex`, persists `tools.codex`, offers a guided install, never blocks.
- **Files:** `we/skills/setup/SKILL.md` (the Step 1b row exists — wire the guided-install flow + the
  `tools.codex` persistence already in the example), `we/references/dependencies.md`.
- **Approach:** Follow the existing empirical-probe pattern; `command -v codex`; on missing offer the
  install hint; write `tools.codex` into the config `tools` block.

### Phase 4: /we:orchestrate Mode-B executor selection

- **Goal:** The Lead can choose Codex vs Agent teammate per Mode-B chunk, defaulting to Claude Code.
- **Files:** `we/skills/orchestrate/SKILL.md` (extend the executor subsection added in 2.59.0 from
  *documented* to *operative*: read `tools.codex`, offer Codex at the rolling confirm, dispatch via the
  shared reference), `we/references/codex-dispatch.md` (NEW — the single-detach rule + brief template in
  one place, referenced by both orchestrate and `/codex:task`).
- **Approach:** Executor selection is prose the Lead acts on; gate Codex behind `tools.codex` + explicit
  per-chunk confirm; reuse the Mode-B review/integration path unchanged.

### Phase 5: Docs + interactive tour runtime-agnostic

- **Goal:** README, `we/CLAUDE.md`, and the `tour/` stations describe the runtime-agnostic model.
- **Files:** `README.md`, `we/CLAUDE.md` (refine the bounded notes from 2.59.0 once the feature is wired),
  `tour/` (the interactive tour stations — add/adjust a station or copy for the Codex backend).
- **Approach:** Update claims to match the now-wired reality (no over-claim). Tour: a short note that
  orchestrate can run on Claude Code or Codex.

### Phase 6: Version bump + changelog

- **Goal:** Ship it.
- **Files:** `we/.claude-plugin/plugin.json` (bump from 2.59.0), changelog/release notes if present.
- **Approach:** Minor bump (new capability). Sequence the Phase-1 weside-core deletion here so the
  slash-command resolution never has a dead window.

> **parallel_groups [[2,3]]:** Phase 2 (dependency declaration, `references/dependencies.md` + manifest)
> and Phase 3 (`/we:setup` skill) touch mostly disjoint files and both only depend on the decision made
> here. Phase 1 is foundational (the command must exist in the plugin first); Phase 4 depends on the
> config contract from Phase 3; Phase 5 depends on 1-4 being real; Phase 6 last (sequences the deletion).

## Design Decisions

| Decision | Alternatives Considered | Why This |
|----------|------------------------|----------|
| Codex = optional/recommended dependency | Hard dependency | Claude-Code-only users must not be forced to install Codex; "runs with both" implies opt-in + graceful degradation. |
| Move `/codex:task` into the plugin | Keep it repo-local in weside-core | It is generic (no weside coupling) and the plugin should own Codex dispatch so every plugin user gets it. |
| Keep command name `/codex:task` | Rename to `/we:codex` | The official Codex plugin ships no `task` command, so no namespace collision; users already know `/codex:task`. |
| Executor selection as skill-prose | Code in orchestration.py | Mode-B dispatch is already Lead-driven prose; no runtime code needed, keeps it simple. |
| Sequence weside-core deletion with the version bump | Delete immediately | The installed plugin cache lags the source; deleting before re-publish leaves a dead `/codex:task` window. |
| Single coherent Story + orchestrate | Epic of N stories | One coherent capability, just phased — not many independent slices. |

## Code Guidance

**DO:** mirror the existing `/we:setup` Step 1b empirical-probe + `tools.*` persistence; put the
single-detach dispatch rule in ONE shared reference and link it; keep Codex strictly opt-in with
Claude-Code default; English for all plugin-shipped text.

**DON'T:** hard-depend on or vendor the Codex plugin; over-claim in README/tour beyond what is wired;
re-introduce the double-detach (companion `--background` + Bash `run_in_background`); delete the
weside-core `/codex:task` before the bumped plugin is the resolving source.

## Security Review Required

No — no money/tenant/auth path. Codex is a developer-facing execution backend; the only caution is not
hard-coupling a third-party plugin.

## Documentation Impact

- [x] **README/Setup** — README recommended-plugins + Requirements, `/we:setup` Step 1b.
- [x] **Architecture docs** — `we/CLAUDE.md` runtime-backends note; `references/codex-dispatch.md` (NEW),
      `references/dependencies.md`.
- [x] **User-facing docs** — the interactive tour (`tour/`).
- [ ] **API docs** — n/a.
