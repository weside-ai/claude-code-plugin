---
name: epic-plan
description: The epic plan file — frontmatter links, mirror block, target and mode, drafting and writer contract. Shared by /we:epic, /we:standup, /we:merged.
---

# Epic plan

## Contents

Links · Mirror block · Target and mode · Drafting an epic · Writer contract.

Above an epic stands only the goal file (L0 §Units): an epic carries `serves: <metric>`, a chain is
the epics serving one metric, and an epic too big for one outcome becomes linked epics. `/we:epic`
improves one epic and never decomposes it; it hands off by printing the next verb.

## Links

- Slugs are kebab-case.
- Epic frontmatter: `type: epic-plan`, `epic` (the file stem), `serves` (the goal file's metric or
  `null`), `ticket` (key or `null`), `created`, `updated`,
  `status: draft | selected | in-progress | backlog | done`.
- A Story's `epic:` is the Epic's ticket key, or the Epic file stem without ticketing. Readers match
  a Story to an Epic on either value (file stem, `epic:` or `ticket:` of the Epic plan).
- Frontmatter lines are bare `key: value`: the v6 parser keeps a trailing `# comment` in the value.
- A Story named only in an Epic's `## Sequencing` has no key: `/we:master <epic>` rosters it only
  after it has a ticket or a plan.
- Readers below the Epic (`/we:plan-story`, `/we:master`) read the Epic's success section and
  `## Scope`. The success section is `## Success Criteria`, or `## Success Metrics` in Epics written
  before v7 (measured in 12 Epics, 27.09.2026): readers accept both, writers write
  `## Success Criteria`.
- A ticket description carries the one-line purpose and the plan path, never the plan's content.

## Mirror block

`/we:epic` owns a block of child Stories between markers; `/we:merged` updates one row after a
merge. Everything outside the markers is user prose and never touched.

```markdown
<!-- mirror:start (auto-generated; do not edit by hand — run /we:epic to refresh) -->

_Mirror of child Stories in the ticketing tool, refreshed YYYY-MM-DD._

| Key | Title | Status | Plan | Last activity | Notes |
|---|---|---|---|---|---|

<!-- mirror:end -->
```

- The block sits under `## Stories`.
- `Plan` is `✓` when `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/ready_gate.py story
  docs/plans/<KEY>-story.md` exits 0 (`${CLAUDE_PLUGIN_ROOT}/references/story-plan.md` § Readiness), else `—`.
- Status buckets: Done · Active · Refined (plan passes the gate, not started) · Backlog · Blocked.
  Map the tool's status names through `.weside/orchestrate.md` § Ticket states.
- Children come from the ticketing tool (`${CLAUDE_PLUGIN_ROOT}/references/ticketing.md`) by parent or
  Epic link. Without ticketing: the frontmatter of the child plan files, with a footnote saying so.
- A refresh rewrites only the block, sets `updated:` and appends one line to `## Updates Log`:
  `- YYYY-MM-DD — mirror refresh (<N> children; +<a> added, −<b> removed, !<c> status-changed)`.
  Missing markers: insert the block under its heading, creating the heading.

## Target and mode

1. Target, first hit wins: the argument (key, path or slug); the branch name; the newest epic plan in
   `docs/plans/` with an active status; else list the candidates and ask one question.
2. Mode from the words around the target: none → **Status** (read-only, the default); "refine",
   "update", "sharpen" → **Refine**; "new" or a slug with no file → **Create**; "refresh", "sync",
   "mirror" → **Mirror-refresh**. Ambiguous → one question. A ticket key that is a Story, or matches
   no `*-epic.md` and no ticketing Epic, is **Create** from that ticket's newest comment (a slice cut
   written there before `/we:epic {TICKET}` was printed).
3. Status loads the plan, the goal file's metric it serves and the children, and renders: header
   line with status and path, the children per bucket, drift against the mirror (`+` missing, `-`
   gone, `!` stale status), one risk-driven next move, and the offers `[r]` refresh · `[f]` Refine ·
   `[q]` done. Status never writes.
4. Mirror-refresh is mechanical: the session writes the block itself and commits it per `${CLAUDE_PLUGIN_ROOT}/references/plan-commit.md`. No writer.
5. Each transition (Status → Refine) needs the user's choice.

## Drafting an epic (Refine and Create)

1. Interview in the session with the `/we:grill` discipline: one question per turn with your
   recommendation, a decision on record cited instead of asked, the epic's frame questions in
   order. Read first: the plan, the goal file, the instruction files, ADRs, `docs/plans/out-of-scope/`
   when present, and the glossary the instruction files name.
2. Worktree and commit path: `${CLAUDE_PLUGIN_ROOT}/references/plan-commit.md` (repo fact first, else a detached scratch
   worktree off the default branch).
3. Dispatch `Agent(subagent_type: "we:dev-high", description: "draft epic <slug>", prompt: <brief>)`.
   Plan-writing is a named `dev-high` case (owner 27.09.2026); the session's `medium` would write it
   otherwise. A subagent writes a plan file here, never code. Brief: first line `Read <abs>/skills/epic/references/template.md and <abs>/references/epic-plan.md, then follow § Writer contract.`
   (paths as they resolve here); the absolute target path in the scratch worktree; the goal file's
   metric; every interview decision with the rejected alternative and who decided; the user's words
   verbatim where they matter; the records read with the one line each settled; freshly fetched
   mirror rows.
4. Approval: present the path, the writer's digest and what step 5 will do: the ticket created or
   updated with its title (or re-parented or closed), and where the commit lands. The approval covers
   only what this message names. Feedback goes to the same writer via `SendMessage`. Plan mode is not
   used: it would stop the writer from writing.
5. After approval, straight through: set `status`, run the verb's ticket step, commit and push per
   step 2, remove the scratch worktree, print the output line and the next verb, stop.

## Writer contract

- Write only the target file. No ticket, no commit, no other file, no downstream verb.
- Follow the template's sections in order. On Refine, edit in place: keep the user's prose where the
  interview did not change it, and leave the mirror block to the rows the brief carries.
- Read the goal file and the records the brief names before writing; a contradiction between them
  and the brief is reported, never resolved silently.
- Name a size signal you notice (more than one outcome, more stories than the epic limit) in the
  report instead of re-cutting the epic.
- Final message, one of:

  ```text
  done: <absolute path> | digest: <one line per section written or changed> | warnings: <size signals or none> | decisions not in the brief: <…>
  blocked: <fork in one line> | A: <option + cost> | B: <option + cost> | recommend <X> because <why>
  ```
