---
name: doc-improve-claude-md-reference
description: Type-specific addendum for reviewing CLAUDE.md files — hierarchy awareness, Quick-Reference discipline, currency across the chain, no internal contradictions, section order. Loaded on demand by the doc-improve skill.
---

# Reference: Reviewing CLAUDE.md files

This is the type-specific addendum for `CLAUDE.md` files at any level. Apply
**after** the four universal pillars from `SKILL.md`. CLAUDE.md is special
because it's loaded **always** (every session, every agent), and there's
typically a hierarchy of them (`~/CLAUDE.md` → `~/weside/CLAUDE.md` →
`~/weside/<repo>/CLAUDE.md`) where the lower levels inherit context from the
upper levels.

---

## Pillar 5a — Hierarchy Awareness

### What loads when

When the agent starts in a working directory, **all** CLAUDE.md files on the
path from the user's home down to the cwd are concatenated into the system
prompt. Concretely for this project:

```
~/CLAUDE.md                                 (user-global)
~/weside/CLAUDE.md                          (workspace)
~/weside/<repo>/CLAUDE.md                   (repo)
~/weside/<repo>/.claude/rules/**/*.md       (rule layer, conditional)
```

The repo CLAUDE.md inherits everything in the parent CLAUDE.md files — so
restating that content in the repo file is pure duplication.

### Method

```bash
# Read the chain
for f in ~/CLAUDE.md ~/weside/CLAUDE.md ~/weside/<repo>/CLAUDE.md; do
  echo "=== $f ==="; cat "$f"
done

# Or quickly compare facts
diff <(grep -oE "[A-Z][A-Za-z][^.]+\." ~/weside/CLAUDE.md) \
     <(grep -oE "[A-Z][A-Za-z][^.]+\." ~/weside/<repo>/CLAUDE.md)
```

### Findings to look for

- **Repo CLAUDE.md restates the workspace overview** — drop it. Workspace
  CLAUDE.md already loads.
- **Repo CLAUDE.md restates the user-global identity** — same fix.
- **Rule content shadowed in CLAUDE.md** — if the same workflow lives in
  CLAUDE.md and in a `.claude/rules/workflows/*.md`, drop from CLAUDE.md.
  CLAUDE.md is for orientation; the rule is for the mechanism.

---

## Pillar 5b — Quick-Reference Discipline

CLAUDE.md is the agent's first context. Its job is **orientation**:

- Vision (1-2 sentences).
- Essential commands (the 5-10 things the agent will do most often).
- Project structure (one tree).
- Tech stack table.
- Pointers into the rules tree for detail.

It is **not** the right home for:

- Step-by-step workflows (those are in rules or skills).
- Long explanations of why decisions were made (those are ADRs).
- Architecture deep-dives (those are `docs/architecture/`).
- Long debugging recipes (those are guides or rules).

### Findings to look for

- **CLAUDE.md > 200 lines for a repo** — likely contains content that should
  move into `.claude/rules/`. Propose specific extractions.
- **Workflow with > 5 steps in CLAUDE.md** — should be a skill or a rule.
  CLAUDE.md keeps the one-line pointer.
- **Explanation paragraphs in CLAUDE.md** — convert to "X works like Y; full
  details: <rule path>". One line in, one link out.
- **Code blocks > 10 lines in CLAUDE.md** — usually a sign that detail leaked
  in. Reduce to the bare command and link out.

---

## Pillar 5c — Currency Across the Hierarchy

### What gets stale fast

CLAUDE.md is touched often (it's the entry point everyone updates). That
means it's also where the most *recent-looking-but-now-wrong* content
accumulates. Common drifts:

- Commands that got renamed (`a release patch` → `a release prod patch`).
- Test user emails / credentials that rotated.
- Version pin numbers in tables.
- Pointers to `.claude/rules/<old-path>.md` after a rule was moved.
- "Last Updated: 2026-01-12" line that's been stale for three months.

### Method

```bash
git log --oneline --since="3 months ago" -- CLAUDE.md
git log -1 --format="%ai" CLAUDE.md      # vs claimed "Last Updated"
```

For each command in the Essential Commands block: confirm it actually exists
in the CLI (`a --help`, `weside --help`, `sup --help`).

For each path mentioned: confirm the path exists.

### Findings to look for

- **Stale command syntax** — `a release patch` (old) vs `a release prod patch`
  (current). **MAJOR.**
- **Stale path** — link to a rule file that was moved or renamed. **MAJOR.**
- **"Last Updated" line drift** — if the doc claims a date but `git log`
  shows older or newer activity, propose updating to the actual date or
  removing the line entirely (it rots).
- **Missing recent additions** — a command shipped two months ago that
  belongs in Essential Commands but isn't there.

---

## Pillar 5d — No Internal Contradictions

CLAUDE.md often picks up multiple contributors over time. Sections written
months apart can disagree.

### Method

Walk the doc front-to-back. Note any time the same concept appears twice. If
the second mention contradicts or evolves the first, that's a finding.

### Findings to look for

- **Two different versions of the dev-server command** — one in Essentials,
  one in Project Structure section. Reconcile.
- **Vision statement repeated in different words** in two places — pick one,
  drop the other.
- **Two different recommendations for the same task** — e.g. "use `a test`"
  in one section, "run `pytest -v` directly" in another. Pick.

---

## Pillar 5e — Section Order

CLAUDE.md gets read top-to-bottom by the agent at session start. The first
~20 lines have the most leverage.

### Findings to look for

- **Vision buried** — the user/agent statement of purpose should be near the
  top, not in section 8.
- **Essential Commands buried** — these are what the agent reaches for most
  often. Top of doc, after vision.
- **Architecture diagram first, commands later** — invert. Commands win
  for daily use; architecture for occasional reference.
- **"Last Updated" / version footer at the top** — irrelevant to the agent;
  belongs at the bottom or removed.

---

## Output additions for CLAUDE.md

The verdict line for CLAUDE.md includes:

```
**CLAUDE.md meta:** <line count> lines · level: <user-global | workspace | repo>
**Inheritance:** <what loads above this file>
**Token note:** <e.g. "150→95 lines projected after F2+F4 (drop duplicates with workspace)">
```

This makes the always-loaded cost visible — same logic as for rules, since
CLAUDE.md and `core/` rules share the always-loaded budget.
