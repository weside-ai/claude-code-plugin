---
name: setup-dependencies-reference
description: Per-dependency install commands, detection checks, and re-check instructions for the /we:setup Step 1b guided install flow. Loaded on demand by the setup skill.
---

# Dependency Install Guide (Step 1b Concierge)

One section per prerequisite. Each follows the same shape: what it provides,
how to detect, how to install, how to re-check. The setup skill walks MISSING
items one at a time with a `[y/n]` gate — never silently installs anything
that touches user scope, and never blocks the pipeline on a `n`.

## gh CLI

- **Provides:** PR creation, CI status, review-thread resolution (`/we:pr`, `/we:ci-review`, `/we:build`).
- **Detect:** `gh auth status` exits 0.
- **Install:** platform package manager (`apt install gh`, `brew install gh`), then `gh auth login` (interactive — suggest the user runs it themselves, e.g. via `! gh auth login`).
- **Re-check:** `gh auth status`.

## Jira access

- **Provides:** ticket fetch + transitions (`/we:story`, `/we:build`).
- **Detect (in priority order):** weside MCP Composio `JIRA_*` via `execute_tool` → `mcp__atlassian__jira_*` tools → `gh issue` (GitHub-Issues mode).
- **Install:** weside.ai → Integrations → connect Jira (preferred), or register the Atlassian MCP server in `~/.claude.json`.
- **Re-check:** call the detected tool with a read-only query.

## simplify skill

- **Provides:** `/we:build` Step 4 simplification pass.
- **Detect:** `simplify` appears in the session skill list.
- **Install:** `/install code-simplifier@claude-plugins-official`.
- **Re-check:** skill list after restart.

## security-guidance plugin

- **Provides:** `/we:build` Step 2 security checks.
- **Detect:** `security-guidance` in `~/.claude/plugins/installed_plugins.json`.
- **Install:** `/install security-guidance@claude-plugins-official`.
- **Re-check:** re-read `installed_plugins.json`.

## superpowers plugin (Anthropic)

- **Provides:** discipline skills (`brainstorming`, `test-driven-development`, `systematic-debugging`, `verification-before-completion`) that `/we:build` and general agent work lean on.
- **Detect:** `superpowers` in `~/.claude/plugins/installed_plugins.json`, or any `superpowers:*` skill in the session skill list.
- **Install:** `/install superpowers@anthropics`.
- **Re-check:** skill list after restart.

## TurboVault (MCP + binary)

- **Provides:** semantic search over `docs/` (`/we:story`, `/we:docs`, `/we:doc-improve`, doc-architect).
- **Detect (liveness, not just presence):** actually call `mcp__turbovault__list_vaults` and confirm it responds. A name-only check ("are `mcp__turbovault__*` tools listed") passes for a registered-but-dead MCP, which then silently degrades every doc search to grep for weeks unnoticed. Three outcomes: responds → **OK**; tool present but call errors/hangs → **DEGRADED** (warn loudly, persist `turbovault: false`); tool absent → **not registered** (then `command -v turbovault` distinguishes binary-missing from MCP-not-registered).
- **Install (binary missing):** download/build the TurboVault binary, place it on PATH.
- **Install (MCP not registered):** add to `~/.claude.json` `mcpServers`:

  ```json
  "turbovault": { "command": "<path-to-binary>", "args": ["--vault", "<repo>/docs", "--init"] }
  ```

  Restart the session afterwards (MCP servers load at session start).
- **Re-check:** `mcp__turbovault__list_vaults` responds. Vault registration for the repo happens in Step 5.2 (`add_vault` + `set_active_vault`).

## graphify CLI

- **Provides:** code knowledge graph — `/we:story` blast-radius block, `/we:audit-architecture` graph-drift check, per-repo code-graph nav rules.
- **Detect:** `python3 -c "import graphify"` exits 0 AND version `>= 0.8.38` (`python3 -c "from importlib.metadata import version; print(version('graphifyy'))"`). Older versions break the repo hooks (the `to_json(..., force=True)` write that prevents stale graphs needs `>=0.8`).
- **Install:** `pip install -U 'graphifyy>=0.8.38'` (PyPI name has the double y; user-level install is fine). Safe to run directly after `[y]` — it touches only the user's Python environment. Must land in the same interpreter the repo hooks call (`python3`) — install via `python3 -m pip`, not pipx (pipx isolation breaks `import graphify`).
- **Re-check:** `python3 -c "import graphify"` again; optionally `graphify --help`.
- **Post-install (per repo):** pre-commit hook activation is handled generically by `/we:setup` Step 1c — no graphify-specific reminder needed.

## weside MCP

- **Provides:** Companion identity, memories, councils (`/we:materialize`, memory-aware `/we:story`/`/we:build`).
- **Detect:** `mcp__plugin_we_weside-mcp__get_companion_identity` available.
- **Install:** requires a weside.ai account; the `we` plugin ships the MCP — check plugin config (`pluginConfigs["we@weside-ai"]`).
- **Re-check:** call `get_companion_identity`.
