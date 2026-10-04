---
name: instruction-audit
description: >
  Audits rules, skills and AGENTS.md against fresh Anthropic docs and a budget gate; findings go
  to the optimization inbox. Triggers: "/we:instruction-audit".
---

# /we:instruction-audit

1. The output is inbox entries, a frozen audit report and an updated `sources.lock` — never an edit
   to a rule, skill or instruction file. `/we:optimize` decides what changes.
2. Store format, config keys and plugin-checkout detection: `${CLAUDE_PLUGIN_ROOT}/references/optimization-store.md`.
3. In the plugin's own checkout the audit reports and writes nothing there; a store lives only in a
   repo a human set up.
4. Sources are fetched raw with `curl -sL` per `${CLAUDE_PLUGIN_ROOT}/references/instruction-sources.md`.

Invocation: `/we:instruction-audit` (this repo) · `--no-doctor` (sources and gate only).

## 1 · Resolve

- **Repo and store.** The git root of the current directory. No `.weside/optimization/` → ask once
  whether to create the store skeleton (`/we:setup` § Instruction loop); declined → run, print the
  report, write nothing. The plugin checkout → report only.
- **Target.** `.weside/config.json` → `optimization.target_model` and `target_effort`; absent → the
  session's model at `medium`.
- **Siblings.** `workspace` lists other repos: offer them after this one finishes. Each runs in its
  own session via `/we:sideload` (editing mode) with the brief "Use the Skill tool with skill
  `we:instruction-audit`", so that repo's own rules apply.

## 2 · Sources

1. The list: the table in `instruction-sources.md` plus the items of `.weside/optimization/sources.md`.
2. Fetch each, check status 200 and `text/markdown`, hash it, keep the copy in the cache.
3. Compare with `sources.lock`. A changed hash becomes one inbox entry, pattern `guideline-changed`,
   target the URL, with a summary of what changed for instruction authors (diff against the cached
   copy of the old hash; no copy → summarise the sections the gate's limits and the authoring guide
   cite). A failed fetch keeps its old lock entry and is named in the report.

## 3 · Gate

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/check-instruction-budget.py --root <repo> --json
```

Each error becomes an entry with pattern `gate:<check>`, source `gate`, confidence `High`, action
`rewrite` (`move` for a line or budget overflow). Warnings go into the report only: a lenient-YAML
skill or one dead glob among live ones is no candidate on its own.

Usage: when `~/.claude/we-timing/*.jsonl` spans 30 days, a `.claude/rules/**` file of this repo with
no `InstructionsLoaded` line and a skill with no `PreToolUse` `skill` or `UserPromptExpansion`
`command_name` line in that window becomes a `sunset` entry, action `flag`, confidence `Medium`.
`AGENTS.md` read as project instructions fires no `InstructionsLoaded`; never flag it.

## 4 · Built-in prompt audit

Run Claude Code's own audit headless from the repo root, as a background command (it takes minutes):

```bash
claude -p "/doctor prompt-audit" --model <target_model> --effort <target_effort> --permission-mode plan
```

For the plugin checkout pass its path (`/doctor prompt-audit <path>`): without one the audit
reads the installed cache copy. The run prints the path of its report under `~/.claude/plans/`.
Copy that report, with the gate output above it, to `.weside/optimization/audits/<YYYY-MM-DD>-<repo>.md`.
A run that prints no report path is a failure: name it, keep the gate and source results.

Each row of its findings table becomes an entry: its pattern id (`G1a` … `G4`, Group 2 rows as in
the store reference), its confidence and action, the quoted line and its proposed replacement.
Rows on ancestor instruction files outside this repo get `target: ~/<path>` and their real action
(store reference § Inbox entry); other rows outside it get `action: flag`; rows on plugin files get `target_repo: plugin`.

## 5 · Inbox and lock

1. Write the entries per the store reference: an existing key gains an evidence line, a new key a
   new file.
2. Diff against the newest earlier file in `audits/`: findings **new**, **persisting** (same key)
   and **resolved** (in the old report, gone now).
3. Write `sources.lock`: every source's hash and fetch date, and the `audit` block (date, target
   model and effort, `claude --version`).
4. Commit the store files per `${CLAUDE_PLUGIN_ROOT}/references/optimization-store.md` § Layout (where store commits land).

## 6 · Report

Five lines at most: gate errors and warnings · audit findings per group and confidence · new /
persisting / resolved against the last audit · changed sources · inbox entries created and
repeated, with the store path. Close with `/we:optimize` as the next step when the inbox holds a
High finding.
