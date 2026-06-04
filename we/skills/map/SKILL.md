---
name: map
description: >
  APO Map — a fast, read-only text dashboard of the whole plan tree.
  Scans docs/plans/ for sagas, epics, and stories (by filename suffix),
  joins build state from the orchestration DB, and renders a grouped
  Saga › Epics › Stories tree with status buckets. Optional argument
  filters to one saga slug. Use when the user says "/we:map", "map",
  "overview", "show the plan tree", "where do all the stories stand",
  "dashboard", "übersicht", "was läuft gerade". Never writes — pure view.
---

# /we:map — Plan-Tree Dashboard

A single textual overview of everything in flight: which Sagas exist, their
Epics, and the Stories under each — with status. Read-only. Boots fresh every
time (no cached tree). This is the "type one thing, see the whole landscape"
command.

> **Counterpart to the altitude skills.** `/we:saga` and `/we:epic` render a
> *deep* Status dashboard for ONE artifact (drift detection, next-move). `/we:map`
> is the *wide, shallow* view across ALL artifacts — the bird's eye. For detail on
> any one node, hand off to `/we:saga <slug>` or `/we:epic <slug-or-key>`.

---

## Argument

- **No argument** → render every Saga in the repo (the full landscape).
- **A saga slug** (e.g. `/we:map presence`) → render only that Saga's subtree.
- **A ticket key** (e.g. `/we:map WA-1206`) → locate that story, render its Epic
  subtree with the story highlighted.

---

## The naming convention this skill reads

The plan tree is **flat** under `docs/plans/`, distinguished by filename suffix —
no nested directories, no separate index. The filename suffix IS the altitude
marker; the saga-slug prefix on epics IS the grouping.

| Altitude | Filename | Frontmatter keys |
|---|---|---|
| Saga | `<saga>-saga.md` | `saga: <slug>` |
| Epic | `<saga>-<epic>-epic.md` | `saga: <slug>`, `epic: <slug>`, `ticket: WA-…` |
| Story | `<TICKET>-story.md` | `story: WA-…`, `epic: WA-…` |

**Transition tolerance (until migration completes):** also pick up legacy shapes —
`<TICKET>-plan.md` (old story suffix) and `<anything>/CONCEPT.md` (old nested epic).
Mark legacy-named files with a `~` flag in the render so the user sees what still
needs renaming.

---

## Boot Protocol (every invocation)

Read fresh — the tree moves between sessions.

1. **List the plan files:**
   ```bash
   ls docs/plans/*-saga.md docs/plans/*-epic.md docs/plans/*-story.md 2>/dev/null
   ls docs/plans/*-plan.md 2>/dev/null            # legacy stories
   ls docs/plans/*/CONCEPT.md 2>/dev/null          # legacy nested epics
   ```
2. **Parse frontmatter** of each (the `saga:`, `epic:`, `ticket:`, `story:`,
   `status:` keys). Group stories under epics via the story's `epic:` field;
   group epics under sagas via the epic's `saga:` field (or the filename prefix
   when frontmatter is missing).
3. **Build state (optional join):** run
   ```bash
   python3 ${CLAUDE_PLUGIN_ROOT}/scripts/orchestration.py story list --active
   ```
   to annotate stories that are mid-pipeline with their latest phase
   (`git_prepared` / `implementation_complete` / `pr_created` / `ci_passed` …).
   If the CLI or DB is absent, skip silently.
4. **Ticketing status (optional join):** if a ticketing tool is configured
   (`.weside/config.json`) and quick to query, fetch live status for the tickets
   referenced — Jira via MCP `jira_search` with `parent = <epic-key>`, or
   `gh issue list`. Normalise to the buckets below. If slow or unavailable, fall
   back to the `status:` frontmatter and note `(from frontmatter)`.

Status buckets (normalise every source into these five):
**Done · Active · Refined · Backlog · Blocked.**

---

## Render

Plain, scannable, monospace-friendly. One Saga block per Saga; epics indented;
a per-epic one-line story roll-up (not every story on its own line unless the
subtree is small or the user filtered to one saga).

```text
weside plan map — <N> sagas, <E> epics, <S> stories      (built <relative-time>)

▸ presence — Companion-in-all-spaces                      docs/plans/presence-saga.md
  status: active

  ✓ foundation    Channel Architecture Foundation          [9/9 done]
  ✓ awareness     Cross-Channel Awareness & Memory          [18 done · 1 backlog]
  ● teams         Teams Enterprise Surface                  [2 done · 2 review · 1 parked]   WA-718…
      ● WA-1206  Teams Production Hardening      In Review   (ci_passed)
      ● WA-1214  Owner-triggered tool gate       In Review
      ○ WA-1221  Multi-Tenant + AppSource        Backlog     parked
      ⊘ WA-1118  WhatsApp Outreach Templates      Blocked     Meta approval
  ○ coordination  Multi-Companion at Scale                  [0/2 — not started]
  ◐ circles       Trust Circles / Scoped Memory             [1 active · 2 refined]

  drift: ⚠ 1 story (WA-1202) has no epic: frontmatter — ungrouped
         ~ 3 stories still on legacy -plan.md suffix

Legend: ✓ done  ● active  ◐ partial  ○ not-started/backlog  ⊘ blocked  ~ legacy-name
For detail: /we:saga presence · /we:epic teams · /we:map WA-1206
```

Rules for the render:
- **Full-landscape mode** (no arg): show each Saga with its epics as one line each
  (the `[n done · n active …]` roll-up). Expand stories only for Sagas with ≤ 1 epic,
  else keep it to epic-level to stay scannable.
- **Filtered mode** (`/we:map <saga>`): expand every epic to show its stories.
- Always surface a short **drift** line per saga: ungrouped stories (no `epic:`),
  legacy-named files (`~`), epics whose ticket status disagrees with frontmatter,
  and epics with > ~10 stories (the "this epic is becoming a saga" smell —
  echoes the `/we:epic` size-warning).
- Stories with no parent saga/epic at all → a final `⟂ unfiled` block listing them,
  so nothing is silently dropped.

---

## Hand-off footer

End every render with the three most useful next moves, derived from what the map
showed — e.g. the saga with the most active work, an epic with drift, or a story
mid-pipeline:

```text
Next: /we:epic teams (most active) · fix 1 ungrouped story · /we:build WA-1221 when unparked
```

---

## Rules

- ALWAYS boot fresh — never render from a cached tree
- ALWAYS scan both new-suffix files AND legacy (`-plan.md`, `*/CONCEPT.md`) so the
  view is complete during migration; flag legacy with `~`
- ALWAYS normalise every status source into the five buckets
- ALWAYS surface ungrouped/unfiled stories — never silently drop a node
- ALWAYS keep full-landscape mode scannable (epic-level roll-up); expand to story
  level only when filtered to one saga or the subtree is tiny
- ⛔ NEVER write any file — `/we:map` is strictly read-only (no plan-mode, no edits)
- ⛔ NEVER invoke another skill inline — print the hand-off commands, let the user pick
- ⛔ NEVER block on a missing ticketing tool or orchestration DB — degrade to
  frontmatter and note the degradation
