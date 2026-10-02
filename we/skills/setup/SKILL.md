---
name: setup
description: >
  Project setup: detects stack, ticketing and tools, asks up to five skippable questions,
  writes .weside/config.json, optionally the council rosters. Triggers: "/we:setup", "configure
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

1. **Vision**: a PRD at `docs/plans/*/PRD.md` is used as is; else a link, file or short text →
   `.weside/vision.md`, or `/we:vision` later writes the PRD. Skip → no vision check.
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

"Set up this repo's council now? `/we:council` and `/we:meet` convene it; without a weside account
every lens is generic and still works." On yes:

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
3. `.weside/weside.md` and `.weside/council.json` are written by no verb. `/we:council` reads
   `council.json` (members per role: `members.<slug>.name`, `.role`, optional `lens`), which the user
   edits by hand; without it every lens is generic.

## 5. Rule bridge and statusline

- **Rule bridge**, when the repo has `.claude/rules/`: Claude Code loads the rules itself, every other
  agent (Codex, Gemini) does not. `.agents/skills/claude-rules/SKILL.md` exists → skip. Otherwise copy
  `${CLAUDE_PLUGIN_ROOT}/templates/agents-skill/SKILL.md` there unchanged and name the instruction-file
  line that points at it. The template resolves `scripts/load-rules.py` from the plugin cache
  (`~/.claude/plugins/cache/weside-ai/we/*/`) at run time, so the repo carries no copy of the loader.
- **Statusline** (model · branch · PR · context · cost; follows `/we:orchestrate`'s
  `~/.claude/we-focus/<session>.json`): run `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/install_statusline.py --status`.
  `offer to install` → ask once, on yes `--apply`. `already active` with a `NOTE` that the copy differs → `--apply`
  refreshes `~/.claude/we-statusline.js`. `keep theirs` → keep the user's statusline and
  mention `--apply --force` (backed up, `--revert` restores it). This and the council agents are the only
  user-scope files setup touches.

## 6. Instruction loop (optional, ask once)

"Keep this repo's rules, skills and AGENTS.md fit for the current model?" Store and keys:
`${CLAUDE_PLUGIN_ROOT}/references/optimization-store.md`. On yes, offer each item on its own:

1. **Store skeleton**: `.weside/optimization/` with `CHARTER.md` (frontmatter `last_optimize:`
   empty; sections Goal, Decisions, Findings, Next steps), `LEDGER.md` (the ledger table header),
   and `inbox/.gitkeep`. Never in the plugin's own checkout.
2. **Authoring rule**: copy `${CLAUDE_PLUGIN_ROOT}/references/instruction-authoring.md` to
   `.claude/rules/instruction-authoring.md`, body unchanged, with `paths:` derived from what the
   repo holds. Candidates: `.claude/rules/**`, `.claude/skills/**/SKILL.md`, `.claude/agents/*.md`,
   `**/AGENTS.md`, `**/CLAUDE.md`, and `<dir>/skills/**/SKILL.md` plus `<dir>/agents/*.md` for each
   plugin directory (one holding `.claude-plugin/`). List each candidate's matches with
   `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/load-rules.py --files-matching '<glob>'`. Keep a candidate
   that matches a file outside `optimization.exclude`; drop one that matches none. A candidate that
   also matches files under `exclude` is replaced by narrower globs over the kept files' directories,
   because `paths:` has no negation. A re-run refreshes the body after asking and keeps the `paths:`.
3. **Gate as pre-commit hook**, when `.pre-commit-config.yaml` exists: add this local hook. It resolves
   the gate from the plugin cache and passes with a notice where the plugin is absent (CI).

   ```yaml
   - repo: local
     hooks:
       - id: instruction-budget
         name: Instruction budget (we plugin)
         entry: bash -c 'g=$(ls -d ~/.claude/plugins/cache/weside-ai/we/*/scripts/check-instruction-budget.py 2>/dev/null | sort -V | tail -1); if [ -z "$g" ]; then echo "we plugin absent - instruction budget not checked"; exit 0; fi; python3 "$g"'
         language: system
         pass_filenames: false
         files: '(^|/)(\.claude/rules/.*|SKILL\.md|agents/[^/]*\.md|AGENTS\.md|CLAUDE\.md|references/.*\.md|\.weside/config\.json)$'
   ```

   Run it once (`pre-commit run instruction-budget --all-files`) and report the count; a red first
   run is the repo's backlog for `/we:optimize`, not a setup failure.
4. **Config keys**: `optimization.target_model` and `target_effort` (default: this session's model at
   `medium`), `exclude` for trees that hold content rather than instructions, and `workspace`: the
   sibling git repos of this one, one per remote URL, each the main checkout
   (`git rev-parse --git-dir` equals `--git-common-dir`). Ask which siblings to include.

## 7. Next

`/we:story <KEY>` (plan) → `/we:orchestrate <KEY>` (build to a green PR; auto-merge unless a stop
applies) → `/we:merged`.
