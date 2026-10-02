---
name: instruction-authoring
description: How to write rules, skills, subagent definitions and AGENTS.md/CLAUDE.md for the current model — the limits the budget gate enforces, model-fit patterns, progressive disclosure, provenance. /we:setup installs it as a path-scoped rule.
paths:
  - ".claude/rules/**"
  - "**/SKILL.md"
  - "**/agents/*.md"
  - "**/AGENTS.md"
  - "**/CLAUDE.md"
---

# Writing instruction files

Applies to `.claude/rules/**`, every `SKILL.md` and its reference files, subagent definitions and
`AGENTS.md` / `CLAUDE.md`. The gate `check-instruction-budget.py` (shipped with the `we` plugin)
enforces the limits below; the patterns after them are what an audit flags.

## Contents

Limits · Where a line goes · What earns a line · Model-fit patterns · Progressive disclosure ·
Provenance · Frontmatter.

## Limits

| File | Limit | Source |
|---|---|---|
| Rule without `paths:` | ≤ 200 lines each; all of them together ≤ the repo budget (default 600) | memory.md |
| `AGENTS.md` / `CLAUDE.md` | ≤ 200 lines | memory.md |
| `SKILL.md` | ≤ 500 lines | skills.md, Agent Skills best practices |
| Skill `description` + `when_to_use` | ≤ 1,536 characters | skills.md |
| All subagent `description`s together | ≤ 15,000 tokens | sub-agents.md |
| Reference file or pointed-at rule over 100 lines | opens with `## Contents` | Agent Skills best practices |
| Rule `paths:` | matches at least one file | a rule whose globs match nothing never loads |

A repo overrides a limit in `.weside/config.json` → `optimization.budget`.

## Where a line goes

- `AGENTS.md`: what every session in the repo needs, for every agent.
- A rule without `paths:`: the same, for Claude Code only. Prefer `AGENTS.md` unless the line is Claude-specific.
- A rule with `paths:`: what matters only while those files are open.
- A skill: a procedure run on demand; its body loads only when invoked.
- A subagent definition: the brief and tool scope of one delegated role.
- `docs/`: explanation a reader looks up, not an instruction.

## What earns a line

A line stays when a session would act worse without it: a fact the model cannot derive from the
repo, a decision someone made, a measured trap stated as fact and fix, or a pointer to the gate
or script that enforces it. Generic engineering advice and restated Claude Code behaviour go.

## Model-fit patterns

Current models follow instructions closely and literally. Text written to push an older model now
over-steers. The audit taxonomy (`claude-api` skill, `shared/prompt-audit.md`) names them:

- **Pressure language (G1a):** capitals, "NEVER EVER", ⛔, "CRITICAL". Say it once at normal
  volume. A skill `description` may keep calibrated urgency: it routes, it does not steer behaviour.
- **Prohibition lists (G1c, G1e):** describe the goal; keep a prohibition only where the failure
  reproduces on the current model, and pair it with the positive action.
- **Fossils (G1d):** workarounds for a named older model. Remove them and re-test.
- **Output choreography (G1f):** fixed update cadences and word counts. State the audience and outcome instead.
- **Recency trap (G2):** one session's stumble written as a permanent rule. Keep it only if it
  would have helped most recent sessions.
- **Volatile specifics (G2):** versions, counts, file trees that the code outgrows. Point at the
  file that holds the fact.
- **Contradictions (G2):** two files with opposite rules on one point. One owner per fact; the other file points at it.
- **Trigger enumeration (G2):** a description that grows one synonym per missed trigger. One trigger per branch.

## Progressive disclosure

`SKILL.md` is the overview; detail lives in reference files it links **directly**. A reference
reached only through another reference is two levels deep, and a partial read misses it. A
reference over 100 lines opens with `## Contents`, so a preview shows its scope.

## Provenance

A decision may carry who and when, and a ticket that anchors a contract still in force. History
that explains how the rule came about goes to the commit message or the ticket.

| Good | Bad |
|---|---|
| "Docs go straight to main (Alex, 2026-09-26)." | "Docs no longer need a PR (changed 2026-09-26)." |
| "The export keeps the v2 shape; PROJ-412 pins it." | "Previously the export used v1; after the outage in PROJ-398 we moved to v2." |
| "`sync` retries three times, then raises." | "Last week `sync` hung for an hour, so it now retries three times." |

## Frontmatter

- A rule reads only `paths:`: a YAML list or a comma-separated string; `globs:` is ignored. Globs
  follow gitignore semantics after brace expansion: without a `/` a pattern matches at any depth
  (`*.md` loads for `docs/a.md`), with one it is anchored at the root, and `!` excludes nothing.
  Quote every glob: Claude Code repairs an unquoted `key: value` line, but frontmatter that still
  fails to parse (an unquoted `- **/*.py` item) makes the rule load for every file. The measured
  semantics and the importable matcher live in `scripts/rule_loading.py` of the `we` plugin; call
  it instead of writing another matcher.
- A skill `description` names what it does first, then the trigger phrases. Claude Code parses
  skill frontmatter leniently, so an unquoted `Triggers: "…"` still loads; the gate only warns.
