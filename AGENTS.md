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
  skills/<verb>/SKILL.md          one directory per /we:<verb>
  agents/                         dev-medium, dev-high, council-<role> lenses
  references/                     shared contracts (apo-hierarchy, plan-commit, worker-dispatch, ticketing, privacy-guard,
                                  optimization-store, instruction-sources, instruction-authoring, companion-session)
  types/index.d.ts                the hooks module's $.state contract (plugin.json `types`)
  docs/board.md                   the /board pane and its board.json schema (ships with the plugin)
  hooks/                          hooks.json + register.ts (the one function-hooks module) with flow/ (the /flow pane,
                                  phase.ts logic), board/ (the /board pane, board.ts logic, work.ts trees, probe.py,
                                  answer.py) and plans/ (plan files and PRs both panes read), *.test.ts
                                  + SessionStart materialize and optimization reminder, UserPromptSubmit
                                  wake counter (news_on_prompt), Stop store-conversation, conflict gate
                                  (own DIRTY PRs), reply-language gate and question gate
                                  (AskUserQuestion while background work runs),
                                  tmux attention (window title white while the session waits),
                                  PreToolUse verification gate, auto-merge gate (Codex verdict
                                  on the head first), draft-reason gate and teammate gate
                                  (no worker panes by default), SubagentStart/Stop timing,
                                  SubagentStop report gate (dev workers), InstructionsLoaded + skill-run telemetry
  scripts/                        rule_loading.py (Claude Code's rule-loading semantics, importable; fixtures/
                                  from probe-rule-loading.py), load-rules.py, check-instruction-budget.py,
                                  identity cache, wake_poller.py (companion wake), statusline,
                                  wclaude + install_launcher.py (companion launcher),
                                  watch-pr-checks.sh (CI watch bound to the PR head, to the merge),
                                  watch-pr-conflicts.sh, watch-worker.sh (Lead watchdog), retro_claim.sh,
                                  pr-body-receipt.py (splices the plan's Verification block),
                                  check-plan-identifiers.py (plan names exist on the base),
                                  test-delta.py (the PR body's test line)
  templates/agents-skill/         rule bridge /we:setup installs for non-Claude agents
docs/                             user docs (index: docs/README.md)
tour/index.html                   one-page tour, served at plugin.weside.ai/tour/
scripts/                          repo validators (frontmatter, structure, consistency), claude_review_gate.py
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
python3 -m pytest -q we scripts
python3 we/scripts/check-instruction-budget.py
claude plugin validate we && claude plugin test we   # the /flow and /board hooks module
```

`claude plugin test` runs the `*.test.ts` files under `we/hooks/` against Claude Code's own
engine; CI does not run it, so a change to the hooks module runs it locally before the push.
The module's types come from Claude Code: `claude plugin validate` prints what it hooks and calls.
The engine takes one `session.start` hook per module (`register.ts` starts both panes), follows
`$` past an import only into `function` declarations, and a pane's button that runs the plugin's
own command calls its function (`openFlow`, `openBoard`): `$.command.run` does not reach the
plugin's own hook.

Python floor 3.9 (macOS `/usr/bin/python3`): CI runs the tests on 3.9 and on the latest release.
Re-record `we/scripts/fixtures/rule-loading.json` with `probe-rule-loading.py` after a Claude Code
release that touches rule loading; a fixture the matcher disagrees with means the matcher is wrong.

## Versioning

`/plugin update` compares `version` in `we/.claude-plugin/plugin.json`; a push to `main` without a
bump stays invisible to users. Patch for fixes and docs, minor for new or changed behaviour, major
for removed or renamed verbs. After a pushed bump: `claude plugins update we@weside-ai`.

## Plugin and weside backend

The plugin reaches the weside backend only through the `weside-mcp` server. A change to an MCP tool
signature needs both the backend implementation and the skills that call the tool updated.
