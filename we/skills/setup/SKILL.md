---
name: setup
description: >
  Project setup: detects stack, ticketing and tools, asks up to seven skippable questions,
  writes .weside/config.json, optionally rosters and crew. Triggers: "/we:setup", "configure
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
  - graphify: `python3 -c "import graphify"` (code graph for `/we:plan-story` and the build workers);
  - weside MCP: `mcp__plugin_we_weside-mcp__get_companion_identity` is listed (materialize,
    Companion-backed council).
  A missing tool is reported with its install command and never blocks.
- `.pre-commit-config.yaml` present → activate the hooks: `pre-commit` missing → offer
  `pip install pre-commit`; `git config core.hooksPath` set to a custom directory (Husky) → warn and
  skip; otherwise `pre-commit install --hook-type <stage>` once per stage the config declares
  (`stages:`, `default_install_hook_types:`, plus `pre-commit`), reporting a stage that errors and
  continuing with the rest.

## 2. Questions

1. **Goals**: the goal file above the epics (L0 §Units: goals with metrics, no epics; an epic
   carries `serves: <metric>`): its path, or a link or short text → `.weside/goals.md`. The Ready
   gate reads it only through the crew: step 4a.3 binds `files.goals` to this path. Without a crew,
   the goal check needs a crew binding and stays off; skip → no goal file, no goal check.
2. **Ticketing** tool confirmed; for Jira, the project key.
3. **Stack** confirmed or corrected.
4. **Tests**: when does a worker write them? `tdd` (failing test first) · `tests-after` (default,
   same change) · `off`. It decides when tests are written, not what a good test is.
5. **Verification**: must every PR declare how the change was observed, or why not? `yes`
   (recommended) · `advisory`. Green tests share the author's blind spots; with `yes` the plugin's
   PreToolUse hook refuses `gh pr create` without a `## Verification` block whose `**Oracle:**` line
   says how the change was observed, or `not-observed — <reason>`. On `yes`, offer to scaffold
   `.weside/verify.md` from what step 1 found: the repo's CLI, its dev bring-up command, whether a
   browser driver exists.
6. **Worker cap**: how many sessions may work at once on this machine, and above which share of
   the 5h window an account counts as full (no new worker starts while every account in rotation is)? Defaults `8` and `80` (skip keeps them). Process
   workers share one machine and one login; `we-worker` refuses a start over either
   (`${CLAUDE_PLUGIN_ROOT}/scripts/worker_launch.py` `capacity`). The first is the machine's, for
   every repo: write it to `~/.claude/we-state/workers/pool.json` as `{"max_busy_sessions": N}`.
7. **Plan landing**, asked only when the default branch has a ruleset
   (`gh api repos/{owner}/{repo}/rules/branches/<default>` returns a rule): do plans reach it by a
   docs PR or by direct push? `pr` (default) · `push` (only when this session's account may bypass the
   ruleset). `push` lands plan commits through `plan_push.py`
   (`${CLAUDE_PLUGIN_ROOT}/references/plan-commit.md` step 5), and only once `.weside/config.json`
   is committed on the default branch: both read that copy.

Review gates are detected, not asked: a Claude or Codex review workflow in `.github/workflows/`, a
CodeRabbit or Greptile app. The ids go to `review.available`; `/we:ci-review` collects threads from
exactly these. Default `["claude"]`. A Codex job named other than `Codex Review` goes to
`review.codex_check`; the merge waits for it only where the base branch requires that check.

Offer once: additive repo checks on top of the plugin's → `.weside/dor.md`, seeded with the user's
concrete check; `/we:plan-story` reads it. Additive, never a replacement. A `.weside/dod.md` says
only when a story is Done and who sets it.

## 3. `.weside/config.json`

Written always, also when step 4 is declined. Only keys a verb reads:

```json
{
  "ticketing": { "tool": "jira|github-issues|none", "project_key": "<KEY or null>",
                 "plugin": "<plugin or MCP server serving the tool, or null>" },
  "stack": ["python", "node"],
  "tools": { "graphify": false },
  "test_discipline": "tests-after",
  "verification": { "required": true,
                    "pre_merge_receipt": "<command with {KEY}: prints report:/skip:/not-run:, exit 0 green, 1 red>" },
  "review": { "available": ["claude"] },
  "agents": { "visible_teammates": false, "worker_launch": "subagent",
              "accounts_command": "<command printing the chosen account as JSON, or null>" },
  "build": { "pr_owner": "master|worker" },
  "workers": { "max_active_5h_percent": 80,
               "blocked_notify_minutes": 15, "idle_stop_minutes": 30,
               "tree": "caller|own",
               "add_worktree": "<command with {path} {branch}, or null>",
               "remove_worktree": "<command with {path}, or null>",
               "context": { "auto_memory": "off", "disable_plugins": [], "deny_mcp_servers": [],
                            "auto_compact_window": null } },
  "plans": { "land": "pr", "push_paths": ["docs/plans/**"], "secret_scan": null },
  "acceptance": { "receipts_workflow": "<workflow path whose RC run uploads accept.json, or null>",
                  "rc_tag_glob": "<RC tag glob, e.g. v*-rc.*>" }
}
```

The Done-row sample sits beside them but in the crew file's `acceptance` block (step 4a), which
`board.py` reads: `acceptance.done_sample` (default 5, `null` = off) samples every n-th Done by
receipt for the acceptance keeper; `lenses.acceptance.sample` stays the lens sampler's
(`${CLAUDE_PLUGIN_ROOT}/docs/board.md` § Acceptance).

`/we:merged` moves a landed story to In Review, never to Done (L0 §Lifecycle;
`${CLAUDE_PLUGIN_ROOT}/skills/merged/SKILL.md` § 5).

`workers.tree`, `add_worktree`, `remove_worktree` and `context` shape a `we-worker` start: whether
a start from the main checkout gets its own tree (`own`; default `caller`, it stays there), the repo's
worktree commands and the worker's lean settings (`${CLAUDE_PLUGIN_ROOT}/references/worker-dispatch.md`
§ Tree, context and end). Write them only when the repo has a worktree command of its own, the
user wants every worker started from the main checkout in a tree of its own (`tree: own`), or the
user names plugins or MCP servers a worker never needs; absent, the plugin's defaults hold.
`ticketing.plugin`: write the plugin or MCP server whose tools reached the ticket in step 2, when
it is not the default `worker_launch.py` maps from `ticketing.tool` (`TICKETING_DEFAULTS`). After
writing `workers.context.disable_plugins` or `deny_mcp_servers`, run
`python3 ${CLAUDE_PLUGIN_ROOT}/scripts/worker_launch.py needs --all --repo .` and show every line it
prints as a warning: a worker started for that skill is refused.

`build.pr_owner` (default `master`: the master pushes, opens, arms and watches every build PR) set to
`worker` makes a story's build worker carry its own PR to one end line
(`${CLAUDE_PLUGIN_ROOT}/references/worker-dispatch.md` § PR-carrying worker); it opens that worker's PR
rights once on the default branch. Write it only when the user asks for it. The rights hang on the
switch, not on the brief: every process worker on a branch carrying its key holds them, a refiner
or a multi-chunk build too. A repo that sets `worker` carries a `.weside/risk-paths`: without it the
one-way check before a worker's merge has no rules.

`plans.secret_scan` stays `null` (gitleaks) unless the user names a scanner: a command with `{range}`
and an optional `{report}`, or `"none"` (`${CLAUDE_PLUGIN_ROOT}/scripts/plan_push.py`).
`plans.push_paths` takes the repo's dated records only when the user names them (`${CLAUDE_PLUGIN_ROOT}/references/plan-commit.md` step 5).
`plans.short_max_files` (default 3) caps the files of a short-form plan (`${CLAUDE_PLUGIN_ROOT}/references/story-plan.md`
§ Short form); write it only when the user names another limit.

`flow.construction_checks` (a list, default empty) names required checks that are red by construction until a release
commit (a version check); `${CLAUDE_PLUGIN_ROOT}/scripts/flow_report.py` shows them on a row of
their own, outside the red-head totals. Write it only when the repo has such a check. The crew's
`flow` block (log, sampler) is another file's (`${CLAUDE_PLUGIN_ROOT}/scripts/crew.py`).

`agents.worker_launch` is a command template that starts each dev worker as a session of its own
(`${CLAUDE_PLUGIN_ROOT}/references/worker-dispatch.md` § Worker launch backend), for a repo without a
crew; `"subagent"` (shown above) is its default. A repo with a crew gets one in the crew's
`launch.worker` instead, written in step 4a (L0 §Sessions: build only in workers).

`agents.accounts_command` lets the project's own tool choose the account of a `we-worker --account`
start (`${CLAUDE_PLUGIN_ROOT}/references/worker-dispatch.md` § Worker rights). Write it only when the
user names such a command; absent, workers start on the login they always did.

A re-run re-detects `tools` and overwrites only that block. Print what was configured in a short
block (stack, ticketing, goals, test discipline, verification, review gates, worker cap, plan landing, missing tools).

## 4. Council (optional, ask once)

"Set up this repo's council now? `/we:council` convenes it; without a weside account
every lens is generic and still works." On yes:

Extend `config.json` (never re-emit its keys) with the roster `/we:council` reads:
`"council": {"default": ["product_owner","architect","scrum_master"]}`.

## 4a. Crew (optional, ask once)

"Does a crew work in this repo (Product Owner, Orchestrator, HR, Tester, component owners)?" Rules:
the crew process L0 (`${CLAUDE_PLUGIN_ROOT}/process/L0.md`) and `${CLAUDE_PLUGIN_ROOT}/references/companion-session.md` § Crew; schema: `${CLAUDE_PLUGIN_ROOT}/scripts/crew.py`. On yes:

1. Another repo holds the crew → only `.weside/config.json` → `"crew": "<relative path>"`, checked
   with `crew.py validate --strict --from <target>`; go to 4a.4 (its humans stay that repo's).
2. Propose: with the weside MCP, `list_companions` plus the handbook's role notes
   (`references/companion-session.md` § Role owners) as one block the user corrects; without it, ask
   who holds each role key (`crew.py` `ROLE_KEYS`; skippable, `OPTIONAL_ROLE_KEYS` such as
   `security` may stay unbound), then one line per member (name, title, components, workplace, on
   call, `specialist` for a member woken on demand that holds no role key). Ask the
   skill prefix once (default: the team's or repo's name).
3. Write `.weside/crew.json` v2 (tracked; no identity text, no companion ids): `"version": 2`,
   `roles` (role key → member slug), `members`, and only the keys whose value differs from
   `crew.py`'s `DEFAULTS`; `weside_account: true` only when the MCP was connected. A goal file from
   question 1 → bind `files.goals` to its path, or the Ready gate's goal check stays off. The humans
   (one `human`, or `humans` with their board signals, labels and `in_test`, and how each human
   starts): follow `references/humans.md` beside this skill. Check it with
   `crew.py validate --strict` (it names every key it refuses, an unknown one too). Propose
   `launch.worker` with `{agent}`, so the worker's effort applies: `we-worker {name} --bg --agent {agent}
   {brief}` (§ 5 installs `we-worker` next to `wclaude`; a user who declines it there gets this line
   rewritten to `claude --bg -n {name} --agent {agent} {brief}`); the user corrects it (§ Worker launch backend of
   `references/worker-dispatch.md` lists the placeholders). Ask once: "Should every start offer
   bypass mode (Shift+Tab), while the start mode stays your `permissions.defaultMode`?" yes →
   `launch.allow_bypass: true`. Ask once: "Should a background worker start in bypass mode, since
   nobody answers its prompts?" yes → `launch.worker_mode: bypass` (else `default`: its start mode stays
   `permissions.defaultMode`). A workflow in `.github/workflows/` that turns on auto-merge for ready PRs →
   `merge.armer: workflow`, and the labels it skips → `merge.hold_labels` (detected, not asked).
   A re-run shows the diff and asks before replacing.
4. `crew.py stubs` lists members without a role skill in their workplace; on yes `--write`
   creates them from `templates/companion-skill/SKILL.md` (a member with a `.weside/roles/<slug>.md`
   addendum gets the pointer skill `pointer.md`), never overwriting.
5. A crew without `weside_account: true` → merge `"deniedMcpServers": [{"serverName":
   "plugin:we:weside-mcp"}]` into the tracked `.claude/settings.json` (other keys kept): the only
   per-repo switch that keeps the plugin's weside MCP from connecting (a `permissions.deny` blocks
   its tools only). The SessionStart hook warns while it is missing.
6. Copy `${CLAUDE_PLUGIN_ROOT}/templates/orchestrate.md` to `.weside/orchestrate.md` and
   `${CLAUDE_PLUGIN_ROOT}/templates/risk-paths` to `.weside/risk-paths`, each only when absent, and fill
   the `TODO` lines you detected (bootstrap, ticket states); name the rest to the user. A crew
   without risk rules on its default branch gets no class until one lands there.
   A team that wants no one-way class deletes the sections and keeps the file.

## 5. Rule bridge and statusline

- **Rule bridge**, when the repo has `.claude/rules/`: Claude Code loads the rules itself, every other
  agent (Codex, Gemini) does not. `.agents/skills/claude-rules/SKILL.md` exists → skip. Otherwise copy
  `${CLAUDE_PLUGIN_ROOT}/templates/agents-skill/SKILL.md` there unchanged and name the instruction-file
  line that points at it. The template resolves `scripts/load-rules.py` at run time from the install Claude Code
  uses in the repo (`installed_plugins.json`, project scope first), so the repo carries no copy of the loader.
- **Statusline** (model · branch · PR · context · cost; follows `/we:master`'s
  `~/.claude/we-focus/<session>.json`): run `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/install_statusline.py --status`.
  `offer to install` → ask once, on yes `--apply`. `already active` with a `NOTE` that the copy differs → `--apply`
  refreshes `~/.claude/we-statusline.js`. `keep theirs` → keep the user's statusline and
  mention `--apply --force` (backed up, `--revert` restores it).
- **Companion launcher** `wclaude` (menu over the crew, then
  `WESIDE_COMPANION=<Name> claude`; `${CLAUDE_PLUGIN_ROOT}/references/companion-session.md`): run
  `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/install_launcher.py --status`. `offer the launcher` → ask once,
  on yes `--apply` into `~/.local/bin/wclaude`. `launcher installed` with a `NOTE` that the copy differs →
  `--apply` refreshes it. `foreign wclaude` → keep the user's file and mention `--apply --force` (backed up,
  `--revert` restores it). Relay a `NOTE` that `~/.local/bin` is not on PATH. The same script installs the
  worker launcher `we-worker`: a `NOTE` naming it (missing, differing or someone else's) → ask once, on yes
  `--apply` (`--apply --force` for someone else's); declined while the crew's `launch.worker` starts with
  `we-worker` → rewrite it to `claude --bg -n {name} --agent {agent} {brief}` (step 4a.3).
- The statusline and the two launchers (`wclaude`, `we-worker`) are the only user-scope files setup touches.

## 6. Instruction loop (optional, ask once)

"Keep this repo's rules, skills and AGENTS.md fit for the current model?" Store and keys:
`${CLAUDE_PLUGIN_ROOT}/references/optimization-store.md`. On yes, offer each item on its own:

1. **Store skeleton**: `.weside/optimization/` with `CHARTER.md` (frontmatter `last_optimize:`
   empty; sections Goal, Decisions, Findings, Next steps), `LEDGER.md` (the ledger table header),
   and `inbox/.gitkeep`. A re-run removes an
   `.weside/optimization/inbox/*.md merge=union` line from `.gitattributes` and says so (why:
   `optimization-store.md` § Inbox entry).
2. **Authoring rule**: copy `${CLAUDE_PLUGIN_ROOT}/references/instruction-authoring.md` to
   `.claude/rules/instruction-authoring.md`, body unchanged, with `paths:` derived from what the
   repo holds. Candidates: `.claude/rules/**`, `.claude/skills/**/SKILL.md`, `.claude/agents/*.md`,
   `**/AGENTS.md`, `**/CLAUDE.md`, and `<dir>/skills/**/SKILL.md` plus `<dir>/agents/*.md` for each
   plugin directory (one holding `.claude-plugin/`). List each candidate's matches with
   `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/load-rules.py --files-matching '<glob>'`. Keep a candidate
   that matches a file outside `optimization.exclude`; drop one that matches none. A candidate that
   also matches files under `exclude` is replaced by narrower globs over the kept files' directories,
   because `paths:` has no negation. A re-run refreshes the body after asking and keeps the `paths:`.
3. **Gate as pre-commit hook**, when `.pre-commit-config.yaml` exists: add the local hook of
   `${CLAUDE_PLUGIN_ROOT}/references/optimization-store.md` § Gate hook, run it once
   (`pre-commit run instruction-budget --all-files`) and report the count; a red first run is the
   repo's backlog for `/we:optimize`, not a setup failure.
4. **Config keys**: `optimization.target_model` and `target_effort` (default: this session's model at
   `medium`), `exclude` for trees that hold content rather than instructions, and `workspace`: the
   sibling git repos of this one, one per remote URL, each the main checkout
   (`git rev-parse --git-dir` equals `--git-common-dir`). Ask which siblings to include.

## 7. Next

`/we:epic` (one epic plan) → `/we:master <epic>` (refiner worker per story without a plan
(`/we:plan-story`), one PR per story; auto-merge unless the computed class is one-way) → `/we:merged`.
