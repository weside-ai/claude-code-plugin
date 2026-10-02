---
name: optimization-store
description: Format of a repo's `.weside/optimization/` store — charter, ledger, inbox entries, frozen audits, source lock, measurement adapter — and the config keys the instruction loop reads. Shared by /we:retro, /we:instruction-audit, /we:optimize, /we:setup.
---

# Optimization store

The instruction loop (`/we:retro` → inbox → `/we:optimize` → `/we:instruction-audit`) keeps its
state in `.weside/optimization/` of the repo where the session runs. The plugin's own checkout never
holds a store: it is public, and entries come from transcripts and carry internal names.

## Contents

Layout · Inbox entry · Ledger row · Source lock · Measurement adapter · Config keys · Plugin
checkout and workspace.

## Layout

| Path | Holds | Written by |
|---|---|---|
| `CHARTER.md` | goal, decisions, current findings, next steps; frontmatter `last_optimize: YYYY-MM-DD` | `/we:optimize` |
| `LEDGER.md` | one row per decided candidate | `/we:optimize` |
| `inbox/<YYYY-MM-DD>-<key>.md` | one open finding per file | `/we:retro`, `/we:instruction-audit` |
| `audits/<YYYY-MM-DD>-<repo>.md` | frozen audit report: gate output plus the `/doctor prompt-audit` report | `/we:instruction-audit` |
| `sources.md` | optional repo-specific source URLs, one Markdown list item each | the user |
| `sources.lock` | hashes of the fetched sources and the last audit's context | `/we:instruction-audit` |
| `measure/README.md` | the repo's measurement adapter | the user |

A store exists only where a human created it (`/we:setup` asks). A verb that finds no
`.weside/optimization/` writes nothing there and says so in one line.

**Where store commits land.** `references/plan-commit.md` step 1 decides from the repo's own
instruction files. When they say nothing, its default (a push to the default branch) does not apply
here: a manual verb asks once, `--auto` stages.

**Staging.** An automatic retro cannot ask and cannot open a PR. Where the repo's instruction files
grant no direct docs commit, it writes its entries to `~/.claude/we-inbox/<repo>/` instead, in the
inbox format below; `/we:optimize` moves them into `inbox/`. `<repo>` is the `origin` URL's
`<owner>-<name>` (`org-app` for `github.com/org/app.git`), so every worktree copy stages to one place.

## Inbox entry

One finding per file, so parallel sessions never edit the same file. `<key>` is
`<pattern>--<target-slug>`: the pattern id in lower case, and the target path with every
character outside `[a-z0-9]` replaced by `-` (`g2-volatile--claude-rules-git-workflow-md`). The
date is the day the key was first seen.

```markdown
---
key: g2-volatile--agents-md
pattern: G2-volatile        # see Pattern ids below
target: AGENTS.md           # repo-relative path; `plugin:<path>` for a plugin file
target_repo: this           # this · plugin
action: rewrite             # remove · rewrite · move · replace-with-API-feature · add · flag
confidence: High            # High · Medium · Low
source: audit               # audit · gate · retro · guideline
---

The quoted line, why it no longer fits, and the proposed replacement text.

## Evidence

- 2026-10-02 audit `audits/2026-10-02-core.md` #4: "toolchain 1.26.x" vs `go.mod` 1.27.1
```

- **A repeat** of a key appends one `- <date> <source> <pointer>: <fact>` line under `## Evidence`
  of the existing file (`ls inbox/*-<key>.md`); it never creates a second file. The repeat count is
  the number of evidence lines across every file carrying the key; it is the entry's weight.
- **Pattern ids** reuse the prompt-audit taxonomy that ships with Claude Code (`claude-api` skill,
  `shared/prompt-audit.md`): `G1a`–`G1f`, the Group 2 rows as `G2-verbose`, `G2-freedom`,
  `G2-recency`, `G2-volatile`, `G2-conflict`, `G2-time`, `G2-history`, `G2-triggers`, then `G3`,
  `G4`. Three ids sit outside it: `gate:<check>` for a gate violation, `guideline-changed` for a
  changed source, `gap` for a missing instruction (action `add`).
- `.gitattributes` line `.weside/optimization/inbox/*.md merge=union` lets two branches that
  appended evidence to one entry merge without a conflict.
- **Lifecycle:** `/we:optimize` decides an entry, writes its ledger row and deletes the inbox file
  in the same commit. A deferred entry stays and gains an evidence line `- <date> deferred: <reason>`.

## Ledger row

`LEDGER.md` is one table, newest row first:

`| date | key | target | decision | evidence | before → after | change |`

- `decision`: `applied` · `rejected` · `deferred` · `upstream` (reported to the plugin's
  maintainers).
- `before → after`: the adapter's numbers, or `unmeasured` when the repo has no adapter.
- `change`: the commit SHA or PR that carries it.

## Source lock

`sources.lock` is JSON:

```json
{
  "audit": {"date": "2026-10-02", "model": "claude-opus-5-5", "effort": "medium", "claude_code": "2.1.287"},
  "sources": [{"url": "https://code.claude.com/docs/en/memory.md", "sha256": "…", "fetched": "2026-10-02"}]
}
```

The raw copies live outside the repo in `~/.cache/we/sources/<sha256>.md`, so a later audit can
diff a changed source against the copy it last hashed.

## Measurement adapter

`measure/README.md` names the commands that put a number on a candidate before and after a change
(a KPI script, a bench arm, a transcript query) and what each number means. Without it every
decision is recorded as `unmeasured`. A plugin skill is measured with `claude plugin eval` (or
the `skill-creator` plugin's evals) instead; an unused skill shows up in `/skill-doctor`.

## Config keys

`.weside/config.json`, all optional:

```json
{
  "optimization": {
    "target_model": "claude-opus-5-5",
    "target_effort": "medium",
    "reminder": true,
    "reminder_days": 14,
    "budget": {"rules_total_lines": 600},
    "exclude": ["vendor"]
  },
  "workspace": [{"path": "../other-repo", "remote": "https://github.com/org/other-repo"}]
}
```

- `target_model` / `target_effort`: the model the audit runs as; absent → the session's model.
- `reminder`: `false` silences the SessionStart reminder (open inbox count, days since
  `last_optimize`); `reminder_days` is the age that triggers it.
- `budget`, `exclude`: overrides for `scripts/check-instruction-budget.py` (keys in its
  `DEFAULT_BUDGET`); `exclude` takes directory names or repo-relative prefixes.
- `workspace`: sibling repos the loop may offer to work on, one entry per remote URL.

## Plugin checkout and workspace

- **Plugin checkout:** a repo in `workspace` (or the current one) whose `origin` URL matches
  `repository` in `${CLAUDE_PLUGIN_ROOT}/.claude-plugin/plugin.json`, compared after dropping a
  trailing `.git` and mapping `git@github.com:` to `https://github.com/`.
- **Worktree copies** of one repo share a remote. Keep the copy whose `git rev-parse --git-dir`
  equals `git rev-parse --git-common-dir` (the main checkout), drop the others.
- A finding whose target is a plugin file goes to the inbox of the repo where the session ran,
  with `target_repo: plugin`.
