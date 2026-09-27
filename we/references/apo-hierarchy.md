---
name: apo-hierarchy
description: The Agentic Product Ownership hierarchy — altitudes, artifact paths, frontmatter links, mirror block, drafting and writer contract, council rosters and synthesis headings. Shared by /we:vision, /we:saga, /we:epic, /we:meet, /we:council.
---

# APO hierarchy

Solo (`/we:<altitude>`) improves one item at its own altitude and never decomposes it. Meet
(`/we:meet <altitude>`) convenes a Council that validates the item and decomposes it into items one
altitude down. Every verb hands off by printing the next verb; none invokes another one inline.
Source of the product: `leading-companions/02-weside/2-produkt/AGENTIC_PO/` (Foxy 26.09.2026: APO
stays in v7, even where Vision and Saga are rarely used).

## Altitudes

| Altitude | Solo | Meet decomposes into | Artifact | Ticket |
|---|---|---|---|---|
| Vision (PRD) | `/we:vision` | Sagas | `docs/plans/<vision>/PRD.md` | never |
| Saga (Theme) | `/we:saga` | Epics | `docs/plans/<saga>-saga.md` | never |
| Epic (Initiative) | `/we:epic` | Stories | `docs/plans/<epic>-epic.md` | optional, the index |
| Story (Feature slice) | `/we:story` | a build-ready plan | `docs/plans/{TICKET}-story.md` | optional, the index |
| Build | `/we:orchestrate` | — | branch + one PR | moved by the Lead |
| Deliver | — (human merge; `/we:merged` closes out after it) | — | merge | closed after merge |

- The APO documents name a `/we:build` verb and a nine-step pipeline. Neither exists in v7:
  `/we:orchestrate` is the Build altitude and takes an approved story or an epic.
- The APO documents also name `SAGA.md`, `05-epics/<epic>/CONCEPT.md` and `stories/<TICKET>-plan.md`.
  The flat names in the table replace them; the core repo and every v7 reader use the flat names.
- Sizing is by bet shape, never by calendar: a Saga has a nameable end and eliminates an argument,
  an Epic ships one coherent user-visible change, a Story is one sprint-sized change.
- A boundary signal (an Epic reads like a permanent area, a Saga has no end, an Epic fits one
  Story) is a soft warning with the neighbour verb named. The user decides; no verb blocks on size.

## Links between altitudes

- Slugs are kebab-case. An Epic under a Saga starts its slug with the Saga slug
  (`ambient-presence-body` under `ambient-presence`).
- Saga frontmatter: `type: saga-plan`, `saga`, `vision` (slug or `null`), `created`, `updated`,
  `status: draft | active | landed | abandoned`.
- Epic frontmatter: `type: epic-plan`, `epic` (the file stem), `saga` (slug or `null`), `ticket` (key or
  `null`), `created`, `updated`, `status: draft | selected | in-progress | backlog | done`.
- A Story's `epic:` is the Epic's ticket key, or the Epic file stem without ticketing. Readers match
  a Story to an Epic on either value (file stem, `epic:` or `ticket:` of the Epic plan).
- Frontmatter lines are bare `key: value`: the v6 parser keeps a trailing `# comment` in the value.
- A Story named only in an Epic's `## Sequencing` has no key: `/we:orchestrate <epic>` rosters it only
  after `/we:story "<name>"` gave it a ticket or a plan.
- Readers below the Epic (`/we:story`, `/we:refine`, `/we:orchestrate`) read the Epic's
  success section and `## Scope`. The success section is `## Success Criteria`, or
  `## Success Metrics` in Epics written before v7 (12 in weside-core, 27.09.2026): readers accept
  both, writers write `## Success Criteria`.
- Ticketing has no Saga level. A ticketing Epic under a Saga is titled `[<saga-slug>] <Epic Title>`
  (JQL `summary ~ "[<saga-slug>]"`). A ticket description carries the one-line purpose and the plan
  path, never the plan's content.

## Mirror block

`/we:saga` (child Epics) and `/we:epic` (child Stories) own a block between markers; `/we:merged`
updates one Epic row after a merge. Everything outside the markers is user prose and never touched.

```markdown
<!-- mirror:start (auto-generated; do not edit by hand — run /we:epic to refresh) -->

_Mirror of child Stories in the ticketing tool, refreshed YYYY-MM-DD._

| Key | Title | Status | Plan | Last activity | Notes |
|---|---|---|---|---|---|

<!-- mirror:end -->
```

- The Saga block sits under `## Sub-Epics`, has no `Plan` column and says `/we:saga`. The Epic block
  sits under `## Stories`.
- `Plan` is `✓` when `docs/plans/<KEY>-story.md` passes
  `${CLAUDE_PLUGIN_ROOT}/skills/story/references/plan-format.md` § The refined scan, else `—`.
- Status buckets: Done · Active · Refined (Epic only: plan passes the scan, not started) · Backlog ·
  Blocked. Map the tool's status names through `.weside/orchestrate.md` § Ticket states.
- Children come from the ticketing tool (`${CLAUDE_PLUGIN_ROOT}/references/ticketing.md`) by parent or
  Epic link. Without ticketing: the frontmatter of the child plan files, with a footnote saying so.
- A refresh rewrites only the block, sets `updated:` and appends one line to `## Updates Log`:
  `- YYYY-MM-DD — mirror refresh (<N> children; +<a> added, −<b> removed, !<c> status-changed)`.
  Missing markers: insert the block under its heading, creating the heading.

## Target and mode (Saga and Epic)

1. Target, first hit wins: the argument (key, path or slug); the branch name; the newest doc in
   `docs/plans/` with an active status; else list the candidates and ask one question.
2. Mode from the words around the target: none → **Status** (read-only, the default); "refine",
   "update", "sharpen" → **Refine**; "new" or a slug with no file → **Create**; "refresh", "sync",
   "mirror" → **Mirror-refresh**. Ambiguous → one question. For `/we:epic`: a ticket key that is a
   Story, or matches no `*-epic.md` and no ticketing Epic, is **Create** from that ticket's newest
   comment (the slice cut `/we:story` writes before it prints `/we:epic {TICKET}`).
3. Status loads the doc, its parent and the children, and renders: header line with status and path,
   the children per bucket, drift against the mirror (`+` missing, `-` gone, `!` stale status), one
   risk-driven next move, and the offers `[r]` refresh · `[f]` Refine · `[m]` print the Meet verb ·
   `[q]` done. Status never writes.
4. Mirror-refresh is mechanical: the session writes the block itself and commits it per `${CLAUDE_PLUGIN_ROOT}/references/plan-commit.md`. No writer.
5. Each transition (Status → Refine → Meet) needs the user's choice.

## Drafting a doc (Refine and Create, every upper altitude)

1. Interview in the session with the `/we:grill` discipline: one question per turn with your
   recommendation, a decision on record cited instead of asked, the altitude's frame questions in
   order. Read first: the doc, its parent, the instruction files, ADRs, `docs/plans/out-of-scope/`
   when present, and the glossary the instruction files name.
2. Worktree and commit path: `${CLAUDE_PLUGIN_ROOT}/references/plan-commit.md` (repo fact first, else a detached scratch
   worktree off the default branch).
3. Dispatch `Agent(subagent_type: "we:dev-high", description: "draft <altitude> <slug>", prompt: <brief>)`.
   Plan-writing is a named `dev-high` case (Foxy 27.09.2026); the session's `medium` would write it
   otherwise. Brief: first line `Read <abs>/skills/<verb>/references/template.md and <abs>/references/apo-hierarchy.md, then follow § Writer contract.`
   (paths as they resolve here); the absolute target path in the scratch worktree; the parent doc
   path; every interview decision with the rejected alternative and who decided; the user's words
   verbatim where they matter; the records read with the one line each settled; freshly fetched
   mirror rows.
4. Approval: present the path, the writer's digest (a Vision: the whole PRD) and what step 5 will do:
   the ticket created or updated with its title (or re-parented or closed), and where the commit lands.
   The approval covers only what this message names. Feedback goes to the same writer via
   `SendMessage`. Plan mode is not used: it would stop the writer from writing.
5. After approval, straight through: set `status`, run the verb's ticket step, commit and push per
   step 2, remove the scratch worktree, print the output line and the next verb, stop.

## Writer contract

- Write only the target file. No ticket, no commit, no other file, no downstream verb.
- Follow the template's sections in order. On Refine, edit in place: keep the user's prose where the
  interview did not change it, and leave the mirror block to the rows the brief carries.
- Read the parent doc and the records the brief names before writing; a contradiction between them
  and the brief is reported, never resolved silently.
- Name a boundary signal you notice (see § Altitudes) in the report instead of re-cutting the item.
- Final message, one of:

  ```text
  done: <absolute path> | digest: <one line per section written or changed> | warnings: <boundary signals or none> | decisions not in the brief: <…>
  blocked: <fork in one line> | A: <option + cost> | B: <option + cost> | recommend <X> because <why>
  ```

## Council rosters and synthesis

Rosters come from `.weside/config.json` → `council.meetings.<type>` and `council.default`. Shipped
defaults, used when the repo has none:

| Key | Roles |
|---|---|
| `default` | `product_owner`, `architect`, `scrum_master` |
| `vision` | `product_owner`, `architect`, `ux_researcher`, `marketing`, `orchestrator` |
| `saga` | `product_owner`, `architect`, `marketing` or `ux_researcher` (the Saga's domain), `orchestrator` |
| `epic` | `product_owner`, `architect`, `orchestrator` |
| `story` | `product_owner`, `architect` |

Shipped role shells: `product_owner`, `architect`, `scrum_master`, `ux_researcher`, `marketing`,
`security`, `sales`, `legal`, `orchestrator` (agent `we:council-<role with hyphens>`).

The synthesis has exactly these four headings; `/we:meet` parses them:

```text
## Council Perspectives
## Agreement
## Tension
## Recommendation
```
