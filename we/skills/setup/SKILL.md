---
name: setup
description: >
  Project onboarding: detects stack, ticketing and tools, asks up to five skippable questions,
  writes .weside/config.json, optionally builds the council. Triggers: "/we:setup", "configure
  project", "initialize repo", "first time".
---

# /we:setup

Every question has a skip path and a default; setup never blocks. Ask one question at a time, each
with one sentence on why the pipeline needs it. Idempotent: on a re-run, show the current value
and ask before replacing it. Create `.weside/` only with the user's consent. Suggest a commit;
never commit yourself.

## 1. Detect

- Stack from marker files: `pyproject.toml`, `package.json`, `Cargo.toml`, `go.mod`; several →
  monorepo, one entry per component.
- Ticketing per `${CLAUDE_PLUGIN_ROOT}/references/ticketing.md`.
- Tools, each by a check that actually runs, never by a path on disk:
  - `gh auth status` exits 0 (PRs, CI, review threads);
  - graphify: `python3 -c "import graphify"` (code graph for story and refine);
  - TurboVault: call `mcp__turbovault__list_vaults`; absent = not registered, error or hang =
    degraded (semantic doc search);
  - weside MCP: `mcp__plugin_we_weside-mcp__get_companion_identity` is listed (materialize,
    Companion-backed council).
  A missing tool is reported with its install command and never blocks.
- `.pre-commit-config.yaml` present → activate the hooks: `pre-commit` missing → offer
  `pip install pre-commit`; `git config core.hooksPath` set to a custom directory (Husky) → warn and
  skip; otherwise `pre-commit install --hook-type <stage>` once per stage the config declares
  (`stages:`, `default_install_hook_types:`, plus `pre-commit`), reporting a stage that errors and
  continuing with the rest.

## 2. Questions

1. **Vision** (link, file or short text) → `.weside/vision.md`. Skip → no vision check.
2. **Ticketing** tool confirmed; for Jira, the project key.
3. **Stack** confirmed or corrected.
4. **Tests**: when does a worker write them? `tdd` (failing test first) · `tests-after` (default,
   same change) · `off`. It decides when tests are written, not what a good test is.
5. **Verification**: must a story be observed running before its PR opens? `yes` (recommended) ·
   `advisory`. Green tests share the author's blind spots; with `yes` the plugin's PreToolUse hook
   refuses `gh pr create` without a filled `## Verification` block (oracle, seed, asserted, not
   proven). On `yes`, offer to scaffold `.weside/verify.md` from what step 1 found: the repo's CLI,
   its dev bring-up command, whether a browser driver exists.

Review gates are detected, not asked: a Claude or Codex review workflow in `.github/workflows/`, a
CodeRabbit or Greptile app. The ids go to `review.available`; `/we:ci-review` collects threads from
exactly these. Default `["claude"]`.

Offer once: additive repo checks on top of the plugin's → `.weside/dor.md` and/or `.weside/dod.md`,
seeded with the user's concrete check. `/we:story` reads the DoR file, `/we:orchestrate` the DoD
rows. Additive, never a replacement.

## 3. `.weside/config.json`

Written always, also when step 4 is declined. Only keys a verb reads:

```json
{
  "ticketing": { "tool": "jira|github-issues|none", "project_key": "<KEY or null>" },
  "stack": ["python", "node"],
  "tools": { "graphify": false, "turbovault": false },
  "test_discipline": "tests-after",
  "verification": { "required": true, "recipe": ".weside/verify.md", "staging_needs_ask": true },
  "review": { "available": ["claude"] }
}
```

A re-run re-detects `tools` and overwrites only that block. Print what was configured in a short
block (stack, ticketing, vision, test discipline, verification, review gates, missing tools).

## 4. Council (optional, ask once)

"Build this repo's council now? `/we:council` and `/we:meet` convene it; without a weside account
every lens is generic and still works. `/we:onboarding` can do it later." On yes:

1. Extend `config.json` (never re-emit its keys) with `vault`, `framework_version: 1`, and the
   meeting rosters `/we:meet` and `/we:council` read:
   `"council": {"default": ["product_owner","architect","scrum_master"], "meetings": {"vision":
   ["product_owner","architect","ux_researcher","marketing","orchestrator"], "saga":
   ["product_owner","architect","orchestrator"], "epic": ["product_owner","architect","orchestrator"],
   "story": ["product_owner","architect"]}}`.
2. TurboVault: check whether this repo's vault is in `list_vaults` by name (another repo's vault
   passing a loose "any vault" check leaves every later search answering from the wrong tree).
   Missing → `add_vault(name=<basename>, path=<root>)` and `set_active_vault`; write `vault` only
   after both succeeded. A small repo may want no vault: `vault: null` is valid.
3. Run `/we:onboarding` through the Skill tool.
4. With a weside account, for each Companion in `.weside/weside.md`, one after another
   (`select_companion` is global state): `select_companion` → `get_companion_identity` → write
   `~/.claude/agents/companion-<slug>.md` (frontmatter `name: companion-<slug>`, `description`,
   `color`; body = identity plus "answer in the council brief's format, stay in role"). The path must
   start with `~/.claude/agents/`, never a repo. Afterwards `select_companion(<configured companion>)`
   restores the session's identity. Tell the user to restart once so the agents load.
5. Set `onboarded: true`, `onboarded_at`. Prerequisites for live council deliberation are named in
   `/we:council`.

## 5. Next

`/we:story <KEY>` (plan) → `/we:orchestrate <KEY>` (build to a green PR) → the human merges →
`/we:merged`.
