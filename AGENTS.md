# claude-code-plugin — developer guide

Repository of the Claude Code plugin `we` (Agentic Product Ownership plus build pipeline) by
[weside.ai](https://weside.ai). User-facing overview: [README.md](README.md).

This is a public repository. Never commit internal weside architecture, API keys, internal URLs,
customer data or proprietary business logic.

## Binding contract

Every file under `we/` follows [we/AUTHORING.md](we/AUTHORING.md): what earns a line, the shape of a
skill, built-ins first, the measured facts a skill must respect.

## Layout

```text
.claude-plugin/marketplace.json   publisher weside-ai
we/                               plugin root
  .claude-plugin/plugin.json      name, version, userConfig
  .mcp.json                       weside-mcp (OAuth, optional)
  AUTHORING.md                    authoring contract
  process/                        the crew process: L0.md, L0-worker.md (rendered by scripts/render_process.py)
  roles/<role>.md                 role cards (L1), rendered by scripts/render_process.py
  skills/<verb>/SKILL.md          one directory per /we:<verb>
  agents/                         dev-medium, dev-high, explore-medium, council-member (every council lens),
                                  lens-product, lens-architecture, lens-acceptance (the lens panel)
  references/                     shared contracts, one owner per fact (.claude/rules/plugin-authoring.md § Single owner)
  types/index.d.ts                the hooks module's $.state contract (plugin.json `types`)
  docs/board.md                   the /board pane, board.json schema, moves, answers, freeze, self-merge, staging
  templates/                      agents-skill/ (rule bridge for non-Claude agents), companion-skill/ (role-skill stub
                                  and pointer), orchestrate.md and risk-paths (copied by /we:setup), cold-reader.md
  hooks/
    hooks.json, register.ts       the hook table and the one function-hooks module (both panes)
    flow/, board/, plans/         the /flow pane (phase.ts), the /board pane (board.ts, work.ts, deliver.ts, probe.py,
                                  answer.py, deliveries.py), plan files and PRs both panes read
    SessionStart                  materialize_on_start, process_on_start (L0), role_on_start (role card),
                                  optimization_reminder, compact_on_start (matcher compact)
    UserPromptSubmit              news_on_prompt (wake counter), sampler_on_prompt (dead sampler, blocked worker)
    PreToolUse                    automerge_gate (every merge form: worker refusal, freeze, risk class, T2 panel,
                                  security card PASS, Codex verdict on the head, receipt red), verification_gate,
                                  draft_reason_gate, teammate_gate
    Stop                          store_conversation_hook, conflict_gate (own DIRTY PRs), reply_language_gate,
                                  question_gate, worker_report_gate (process workers)
    PreCompact                    epic_age_precompact (stale Updates Log)
    SubagentStop                  the dev-worker report gate (a hook on `we:dev-*`, no script)
    timing and telemetry          subagent_timing (SubagentStart/Stop, InstructionsLoaded, UserPromptExpansion, Skill)
    attention                     tmux_attention (window title white while the session waits, grey at rest)
  scripts/
    crew                          crew.py (the one reader of .weside/crew.json), render_process.py, start.py,
                                  state_move.py, council_lens.py
    board                         board.py, board_freeze.py, board_self_merge.py, board_staging.py, cold_reader.py,
                                  accept.py, ticket_adapter.py, epic_state.py
    gates                         ready_gate.py, plan_tier.py, risk_paths.py, risk_runner.py, lens_verdict.py,
                                  check-plan-identifiers.py, check-instruction-budget.py
    rules                         rule_loading.py, load-rules.py, probe-rule-loading.py, probe-hook-cap.py (fixtures/)
    launch                        wclaude, we-worker, install_launcher.py, worker_launch.py, pin.sh, identity_cache.py,
                                  wake_poller.py, gh_anchor.sh
    watch                         watch-pr-checks.sh (CI to the merge), watch-pr-conflicts.sh, watch-worker.sh
    flow                          flow_log.py (the flow log's one owner), sampler_age.py
    PR and plan                   pr-body-receipt.py, test-delta.py, session_tokens.py, retro_claim.sh
    statusline                    statusline.js, install_statusline.py
    hook state                    state_prune.py (ages out per-session hook files), claude_home.py (Claude Code's config dir)
    test support                  node_test_procs.py (the node binary and process reaping for statusline tests)
docs/                             user docs (index: docs/README.md)
tour/index.html                   one-page tour, served at plugin.weside.ai/tour/
scripts/                          repo checks: validate-frontmatter.py, validate-plugin-structure.sh,
                                  validate-consistency.py (also checks this layout names every file), full_test_run.py,
                                  version_bump.py, check_compat_line.py, claude_review_gate.py
```

## Conventions

- Every verb works without a weside account; Companion features are additive.
- Skills name ticketing actions generically ("move to In Review"), per `we/references/ticketing.md`.
- Tool commands are detected from the project's marker files, never hard-coded.
- No weside application paths, internal ticket keys or internal URLs in `we/`.
- A shared fact lives in one file under `we/references/`; skills point at it.

## Checks before a commit

```bash
pre-commit run --all-files
python3 scripts/validate-frontmatter.py we/skills/*/SKILL.md we/agents/*.md
bash scripts/validate-plugin-structure.sh
python3 scripts/validate-consistency.py
python3 scripts/full_test_run.py   # pytest we scripts under the host's test slot, prints its peak
python3 we/scripts/check-instruction-budget.py
claude plugin validate we && claude plugin test we   # the /flow and /board hooks module
```

A full local test run goes through `scripts/full_test_run.py`: on a host shared by several sessions it
waits for the test slot (`$WESIDE_TESTS_LOCK`, default `/tmp/weside-tests.lock`) and ends with its
peak process count and RSS; a single suite runs with plain `pytest <file>`.

`claude plugin test` runs the `*.test.ts` files under `we/hooks/` against Claude Code's own
engine; CI runs it (job Hooks Module, a pinned CLI), and a change to the hooks module runs it
locally before the push too.
The module's types come from Claude Code: `claude plugin validate` prints what it hooks and calls.
The engine takes one `session.start` hook per module (`register.ts` starts both panes), follows
`$` past an import only into `function` declarations, and a pane's button that runs the plugin's
own command calls its function (`openFlow`, `openBoard`): `$.command.run` does not reach the
plugin's own hook.

Python floor 3.9 (macOS `/usr/bin/python3`): CI runs the tests on 3.9 and on the latest release.
Re-record `we/scripts/fixtures/rule-loading.json` with `probe-rule-loading.py` after a Claude Code
release that touches rule loading; a fixture the matcher disagrees with means the matcher is wrong.

## Versioning

`/plugin update` compares `version` in `we/.claude-plugin/plugin.json`. No PR sets it: after every
merge to `main`, `.github/workflows/version-bump.yml` opens or updates the rolling PR
`chore: bump we to X` and arms its auto-merge (`scripts/version_bump.py`: the Conventional Commits
since the last bump decide, `!`/`BREAKING CHANGE` major, `feat` minor, anything else patch). The
required `Version Bump Check` refuses a PR that moves the version and is no bump PR (its diff is the
version line alone, its head commit's author `github-actions[bot]`). After the bump PR merged:
`claude plugins update we@weside-ai`.

## Plugin and weside backend

The plugin reaches the weside backend only through the `weside-mcp` server. A change to an MCP tool
signature needs both the backend implementation and the skills that call the tool updated.
