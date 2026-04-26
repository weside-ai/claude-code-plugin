---
name: doc-improve-rules-reference
description: Type-specific addendum for reviewing files in .claude/rules/ — token budget, paths: pattern correctness, cross-rule trigger-overlap, always-loaded vs path-filtered fit, CLAUDE.md de-duplication. Loaded on demand by the doc-improve skill.
---

# Reference: Reviewing Claude Code Rules (`.claude/rules/**/*.md`)

This is the type-specific addendum for files in `.claude/rules/`. Apply
**after** the four universal pillars from `SKILL.md`. The unique concern for
rules is that they are loaded into **every** matching agent session — so
content quality has a token cost that scales linearly with how often the rule
matches. A wrong sentence in a rule misleads every future session; a redundant
sentence inflates every future session's prompt.

---

## Pillar 5a — Token Budget

### Why it matters

| Folder | Loads | Token impact |
|---|---|---|
| `core/` | Every session (always-loaded) | Maximum — every byte appears in every conversation |
| `workflows/` | Every session (always-loaded) | Maximum |
| `stacks/` | When matching files are touched | High — loads many sessions per day |
| `quality/` | When matching files are touched | High |

The size guideline from `doc-standards.md`:

| Type | Lines | Split if |
|---|---|---|
| Rules (always-loaded) | 50-300 | >300 |
| Rules (path-filtered) | 50-500 | >500 |

These are not arbitrary. Always-loaded rules compete for the always-loaded
budget (CLAUDE.md + every `core/*.md` + every `workflows/*.md` + the user's
auto-memory index, all stacked). Cross the 300-line ceiling and you're
crowding out other always-loaded content.

### Method

```bash
# Line count + always-loaded vs path-filtered classification
wc -l <rule-file>
head -10 <rule-file>          # see if it has paths:

# What's in the always-loaded set today?
wc -l .claude/rules/core/*.md .claude/rules/workflows/*.md
```

### Findings to look for

- **Over-budget always-loaded rule** — `core/foo.md` at 320 lines. Either
  tighten or split (e.g. peel "Worktree Branch Guard" detail out into a
  path-filtered companion). Cite the size guideline rule.
- **Under-budget = under-information**, possibly. A `core/` rule at 30 lines
  may just be efficient — only flag if the rule is *too thin* to be useful.
  The minimum is "the rule's job done well", not "more bytes".
- **Paragraphs where a table would do** — prose carries warmth but takes 3x
  the tokens. Rules optimise for compression. Tables, bullet lists, code
  blocks > flowing paragraphs. Convert without losing nuance.
- **Repeated examples** — three near-identical bash blocks teaching the same
  lesson. One canonical example wins. Drop the others.
- **Boilerplate framing** — "This document describes..." / "In this rule we
  will..." → cut. The rule's content is the rule.

---

## Pillar 5b — `paths:` Frontmatter Correctness

### What the contract says

```yaml
---
description: One-line summary
paths:
  - "apps/backend/app/companion/**/*.py"
  - "apps/backend/alembic/**"
---
```

Three frontmatter rules from `weside-core/CLAUDE.md`:

1. The field is `paths:`, **NOT** `globs:`. (`globs:` is a silent typo — the
   rule loads as if always-loaded, blowing the budget.)
2. **No brace-expansion**. `*.{ts,tsx}` does not expand. Write two entries:
   ```yaml
   paths:
     - "apps/mobile/**/*.ts"
     - "apps/mobile/**/*.tsx"
   ```
3. Rules without `paths:` load **always**. This is correct for `core/` and
   `workflows/`. Anywhere else it's a bug.

### Method

```bash
# Inspect frontmatter
head -10 <rule-file>

# Confirm paths actually match files
ls $(echo "<glob from paths:>")        # quick sanity
git ls-files | grep -E "<regex form>"  # exhaustive

# Detect typo (globs: instead of paths:)
grep -l "^globs:" .claude/rules/**/*.md
```

### Findings to look for

- **`globs:` typo** — loads as always-loaded by accident. **BLOCKER.**
- **Brace expansion in a path** — only the literal-brace files match (none).
  **BLOCKER for the rule's intended scope.**
- **Glob too broad** — `paths: ["**"]` or `paths: ["apps/**"]` on a
  rule that only applies to backend Python. Loads on every frontend edit too.
  **MAJOR — token waste.** Tighten the glob.
- **Glob too narrow** — describes a pattern that applies repo-wide but only
  matches one folder. The rule won't fire when the agent edits the symptom
  elsewhere. **MAJOR — coverage gap.**
- **Glob points at a non-existent path** — `apps/backend/app/companion/adapters/**`
  when the directory was renamed. **MAJOR — rule never fires.**
- **No `paths:` on a stack-specific rule** — should be path-filtered, isn't.
  **MAJOR — always-loaded budget waste.**

---

## Pillar 5c — Cross-Rule Trigger Overlap

### What it is

Two rules whose `paths:` overlap will both load when an agent edits a matching
file. The overlap is fine **iff** their content doesn't duplicate. When the
content overlaps too — same workflow described twice, same primitive
explained twice, same caveat repeated — the agent reads the same thing
twice and the always-loaded budget gets eaten.

### Method

```bash
# Find rules that match the same files
for r in .claude/rules/**/*.md; do
  echo "=== $r ==="
  awk '/^paths:/,/^[^ ]/' "$r"
done

# Or: ask the question directly via TurboVault if available
mcp__turbovault__find_similar_notes(<rule-path>)
```

For each rule under review: read the frontmatter `paths:` of every other rule
in the tree, identify overlaps. Then check if the overlapping rules duplicate
content.

### Findings to look for

- **Same-paths different rules with overlapping content** — propose a merge
  (one rule), or a split-by-audience (different angles, no shared content).
  Real example: `content-seeding.md` and `migration-safety.md` both trigger
  on `apps/backend/alembic/**` and shared ~30% of the workflow.
- **Reference-instead-of-duplicate** — when sibling rule X already covers
  invariant Y, this rule should reference X with one line, not restate Y.
- **Path-overlap with a `core/` always-loaded rule** — your path-filtered
  rule explains something the agent already loaded from `core/`. Redundant.

---

## Pillar 5d — Always-Loaded vs Path-Filtered Fit

A rule sits in `core/` because it's load-bearing in *every* agent context.
The question to ask of every always-loaded rule: *does the agent really need
this when it's editing a frontend test?*

### Method

Walk through the rule mentally with three different agent contexts:

1. Agent editing `apps/backend/app/companion/being.py`.
2. Agent editing `apps/mobile/components/ChatScreen.tsx`.
3. Agent editing `docs/architecture/MEMORY.md`.

Does the rule's content help in **all three** contexts? If yes — `core/` is
correct. If no — the rule should move to a path-filtered location.

### Findings to look for

- **Always-loaded rule with backend-only content** — move to `stacks/` with
  `paths: apps/backend/**`. **MAJOR — token waste.**
- **Always-loaded rule with infrastructure-only content** — same fix.
- **`core/` rule that's a placement decision tree** — usually fine, that
  *is* always-loaded territory. Don't over-correct.

---

## Pillar 5e — Don't Duplicate CLAUDE.md

CLAUDE.md is also always-loaded. If the rule restates content from
CLAUDE.md word-for-word, drop it from one or the other. The rule wins for
detail; CLAUDE.md wins for orientation. They should not overlap on facts.

### Method

```bash
# Rough overlap check
diff <(grep -oE "[A-Z][^.]+" CLAUDE.md | sort -u) \
     <(grep -oE "[A-Z][^.]+" <rule> | sort -u)
```

Or read both side by side. The rule is the right home for the actual
mechanism (commands, file paths, invariants). CLAUDE.md is the right home
for the one-line pointer.

### Findings to look for

- Rule restates a section that's verbatim in CLAUDE.md → propose dropping
  one side.
- Rule contradicts CLAUDE.md (different version of the same workflow) →
  reconcile against the code.

---

## Frontmatter for description

Per `superpowers:writing-skills` discovery rules (and the same logic applies
to rule frontmatter): the `description:` field is what the agent sees first.
Make it scannable.

- Lead with the topic.
- One line, no narrative.
- Don't explain the workflow inside the description — keep that for the body.

```yaml
# Good
description: Git workflow — branch protection, conventional commits, push policy

# Bad (narrative, repeats body)
description: This rule explains how we use git, including branch protection rules and conventional commits, and what to do before pushing
```

---

## Output additions for rules

In addition to the universal report format, every rule review's verdict line
includes:

```
**Rule meta:** <line count> lines · <always-loaded | path-filtered> · paths: [list]
**Token note:** <e.g. "120→85 lines projected after F1+F3", or "in budget, no change">
```

This tells the user the token impact of the proposed changes at a glance.
