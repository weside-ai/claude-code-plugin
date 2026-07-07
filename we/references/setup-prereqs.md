# Plugin Prerequisites — Detection & Guided Install

The canonical prerequisite matrix for the `/we:*` pipeline. Owned here; `/we:setup` Step 1b
executes it. Verify each prerequisite empirically — never derive availability from plugin
filesystem paths alone, since plugins can ship agents, skills, or commands under different
names than expected.

**Detection rule:** for each row, run the listed *Detection check*. The check is the source
of truth. If it succeeds → prerequisite is met. If it errors with "not found" → mark as
missing and inform the user (do NOT block).

| Prerequisite | Detection check | Provided by | Used by |
|---|---|---|---|
| `gh` CLI authenticated | `gh auth status` exits 0 | GitHub CLI install + `gh auth login` | `/we:pr`, `/we:ci-review`, `/we:build` PR creation, CI status, review-thread resolution |
| Jira access (one of) | weside MCP Composio `JIRA_*` via `execute_tool` (preferred) / `mcp__atlassian__jira_*` (fallback) / `gh issue` for GitHub-Issues mode | weside MCP + Composio Jira, or Atlassian MCP, or GitHub CLI | `/we:story`, `/we:build` ticket fetch and transitions |
| `simplify` skill | `Skill(skill="simplify")` available in the skill list | `code-simplifier@claude-plugins-official` (ships an agent that the harness exposes as the `simplify` skill) | `/we:build` Step 4: Simplify |
| security guidance hooks | `security-guidance` plugin in `~/.claude/plugins/installed_plugins.json` | `security-guidance@claude-plugins-official` | `/we:build` Step 2 security checks |
| TurboVault MCP | **Liveness, not just presence:** actually call `mcp__turbovault__list_vaults` and confirm it responds. Tool name present but the call errors/hangs → **DEGRADED** (registered but not responding). Tool name absent → **not registered**. | TurboVault MCP server | `/we:story` (semantic search), `/we:build` (architecture context), `/we:docs`, `/we:doc-improve` (skills have fallbacks if missing) |
| weside MCP | `mcp__plugin_we_weside-mcp__get_companion_identity` available | weside MCP (requires weside.ai account) | `/we:materialize`, optional companion memory in `/we:story` and `/we:build` |
| superpowers plugin | `superpowers` in `~/.claude/plugins/installed_plugins.json` (or `Skill(skill="superpowers:brainstorming")` listed) | `superpowers@anthropics` (Anthropic) | brainstorming/debugging discipline skills used throughout `/we:build` |
| graphify CLI | `python3 -c "import graphify"` exits 0 AND `graphifyy>=0.8.38` (`python3 -c "from importlib.metadata import version; print(version('graphifyy'))"`) | `pip install -U 'graphifyy>=0.8.38'` (user-level) | `/we:story` blast-radius block, `/we:audit-architecture` graph-drift check, code-graph nav rule |
| turbovault binary | `command -v turbovault` (only when the MCP row above is missing) | TurboVault binary install + MCP registration | distinguishes "binary missing" from "MCP not registered" for the guided fix |
| Codex backend (optional) | `command -v codex` exits 0 (the official Codex plugin's CLI) | [openai/codex-plugin-cc](https://github.com/openai/codex-plugin-cc) | `/we:orchestrate` and `/we:develop` optional executor; cross-review via `/codex:adversarial-review`. Absent → workers run on Claude Code with no degradation |
| Engine profiles (optional) | `.weside/engines.local.json` exists and has ≥1 profile with a resolvable `key_ref` | User-created via the setup wizard | `/we:orchestrate` foreign-engine executor via `worker-launch.sh`; any Anthropic-compatible endpoint |

## Guided install flow

For each MISSING row, offer the fix interactively instead of only hinting. Full
per-dependency commands and re-check instructions: `references/dependencies.md`. Shape per
item:

> "Missing: **{name}** — provides {what}. Install now with `{command}`? [y/n]"

- `y` → print the exact command (or run it for safe, user-scoped installs like
  `pip install graphifyy` after confirmation), then RE-RUN the row's detection check and
  report the result.
- `n` → continue; the pipeline works without it, the dependent feature is skipped.

## Persisting the result

Persist in `.weside/config.json` (setup Step 3 merges it):

```json
"tools": { "graphify": true, "turbovault": true, "superpowers": false, "codex": false },
"engines": []
```

`engines` is a list of profile names from `.weside/engines.local.json` that were
successfully probed — starts empty, filled by the executor wizard.

Downstream skills read `tools.*` from config to decide whether to offer graph/vault
features — they still verify empirically before each actual call (config can go stale) and
only skip when the real call says "not found".

## TurboVault DEGRADED — the silent-killer case, call it out loudly

A registered-but-dead MCP passes a name-only check and then every doc search silently falls
back to grep for weeks. If the liveness probe fails, persist `"turbovault": false` AND warn
explicitly:

> "⚠️ TurboVault MCP is registered but NOT responding — `list_vaults` failed. Doc search
> (`/we:docs`, `/search`, `/we:story`) is running on grep fallback, which is much weaker.
> Restart the session or check the MCP config (`~/.claude.json` /
> `~/.claude/settings.json`)."

**Do NOT block.** This is informational — the pipeline works without these plugins.
Downstream skills (e.g. `/we:build` Step 4) MUST trust this gate: they invoke the
prerequisite directly and only skip when the actual tool call returns "not found", never on
assumption.
