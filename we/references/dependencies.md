---
name: setup-dependencies-reference
description: Per-dependency install commands, detection checks, and re-check instructions for the /we:setup Step 1b guided install flow. Loaded on demand by the setup skill.
---

# Dependency Install Guide (Step 1b Concierge)

The **detection matrix** — what each prerequisite provides, how to probe it, who consumes it — is
owned by [`setup-prereqs.md`](setup-prereqs.md). This file carries only what that matrix cannot:
the install command and the trap that comes with it. The setup skill walks MISSING items one at a
time behind a `[y/n]` gate, never silently installs into user scope, and never blocks on a `n`.

| Prerequisite | Install | The trap |
|---|---|---|
| **gh CLI** | platform package manager, then `gh auth login` | `gh auth login` is interactive — suggest the user runs it themselves (`! gh auth login`) rather than trying to drive it |
| **Jira access** | weside.ai → Integrations → connect Jira (preferred), or register the Atlassian MCP in `~/.claude.json` | — |
| **simplify skill** | `/install code-simplifier@claude-plugins-official` | Skill list only refreshes after a restart |
| **security-guidance** | `/install security-guidance@claude-plugins-official` | — |
| **superpowers** (Anthropic) | `/install superpowers@anthropics` | — |
| **TurboVault binary** | place the binary on PATH | — |
| **TurboVault MCP** | add to `~/.claude.json` → `mcpServers`: `{"turbovault": {"command": "<binary>", "args": ["--vault", "<repo>/docs", "--init"]}}` | MCP servers load at session start — the registration only takes effect after a restart |
| **graphify CLI** | `pip install -U 'graphifyy>=0.8.38'` | The PyPI name has the double *y*. Install into the **same interpreter the repo hooks call** — `python3 -m pip`, never pipx: pipx's isolation breaks `import graphify`. Safe to run directly after a `[y]` (user scope only) |
| **weside MCP** | needs a weside.ai account; the plugin ships the server — check `pluginConfigs["we@weside-ai"]` | — |
| **Codex backend** (optional) | the official [openai/codex-plugin-cc](https://github.com/openai/codex-plugin-cc) plugin | Third-party and strictly opt-in — the `we` plugin never vendors or hard-depends on it. Absent → workers run on the configured Claude tier with no loss of capability. Dispatch mechanics: [`codex-dispatch.md`](codex-dispatch.md) |

Re-check after every install by re-running that row's detection check from `setup-prereqs.md` —
the probe is the source of truth, not the install's exit code.

## Foreign engine profiles (optional)

Engine profiles route workers to Anthropic-compatible third-party APIs (e.g. Alibaba/Qwen, GLM-5/z.ai, Kimi/moonshot, MiniMax, Bedrock). All use the same three env-var pattern — `ANTHROPIC_BASE_URL`, `ANTHROPIC_AUTH_TOKEN`, `ANTHROPIC_MODEL` — so no router proxy (ccr, LiteLLM) is needed; the provider must speak the Anthropic Messages API format.

### File: `.weside/engines.local.json`

Per-repo, **gitignored** (setup wizard appends to `.gitignore` automatically). Never committed; never shared.

```json
{
  "glm5": {
    "base_url": "https://api.z.ai/api/anthropic",
    "model": "glm-5",
    "key_ref": { "env": "ZAI_TOKEN" }
  },
  "kimi": {
    "base_url": "https://api.moonshot.cn/v1",
    "model": "moonshot-v1-8k",
    "key_ref": { "secrets_env": "KIMI_API_KEY" }
  }
}
```

### `key_ref` forms

Raw API keys are **never stored in any repo file** — committed or gitignored. Two reference forms only:

| Form | Where the key lives | Example |
|---|---|---|
| `{ "env": "VAR_NAME" }` | Already set in the shell environment | `{ "env": "ZAI_TOKEN" }` |
| `{ "secrets_env": "KEY_NAME" }` | `~/.weside/secrets.env` (chmod 600, never committed) | `{ "secrets_env": "KIMI_API_KEY" }` |

`worker-launch.sh` resolves the key at runtime and **never logs its value**.

### `~/.weside/secrets.env` (global key store)

Plain `KEY=value` format, one per line, `chmod 600`. Managed by the user; never touched by the plugin automatically.

```bash
KIMI_API_KEY=sk-…
MINIMAX_KEY=…
```

- **Detect:** file exists at `~/.weside/secrets.env`.
- **Setup wizard:** suggests creating the file and adding the key there; reminds the user to `chmod 600`.
- **Launcher:** reads with `grep "^KEY=" ~/.weside/secrets.env | cut -d= -f2-` — no shell sourcing, no variable pollution.

### Launcher

`we/scripts/worker-launch.sh` implements the dispatch: reads the profile, resolves the key, execs `claude -p "<brief>"` with the env vars set. See [`worker-dispatch.md`](worker-dispatch.md) for the full invocation contract.

- **Detect:** `command -v claude` exits 0 (always true if Claude Code is installed).
- **No extra install** needed beyond the profile file and the key reference.
- **`--dry-run`:** prints profile + engine selection with the key redacted; exits without executing.
