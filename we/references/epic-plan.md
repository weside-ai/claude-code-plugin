---
name: epic-plan
description: The epic plan file — frontmatter links, finish line, upkeep after a merge, target and mode, drafting and writer contract. Shared by /we:epic, /we:standup, /we:merged.
---

# Epic plan

## Contents

Links · Finish line · Upkeep after a merge · Target and mode · Drafting an epic · Writer contract.

Above an epic stands only the goal file (L0 §Units): an epic carries `serves: <metric>`, a chain is
the epics serving one metric, and an epic too big for one outcome becomes linked epics. `/we:epic`
improves one epic and never decomposes it; it hands off by printing the next verb.

## Links

- Slugs are kebab-case.
- Epic frontmatter: `type: epic-plan`, `epic` (the file stem), `serves` (the goal file's metric or
  `null`), `ticket` (key or `null`), `created`, `updated`,
  `status: draft | approved | selected | in-progress | backlog | done` (`board.py move <KEY> backlog --epic` needs a status starting `approved`),
  optional `select: owner` (the epic's owner reads every story before Selected, § Finish line).
- A Story's `epic:` is the Epic's ticket key, or the Epic file stem without ticketing. Readers match
  a Story to an Epic on either value (file stem, `epic:` or `ticket:` of the Epic plan).
- Frontmatter lines are bare `key: value`: the parsers (`ready_gate.py`, `epic_state.py`) keep a trailing `# comment` in the value.
- A Story named only in an Epic's `## Sequencing` has no key: `/we:master <epic>` rosters it only
  after it has a ticket or a plan.
- Readers below the Epic (`/we:plan-story`, `/we:master`) read the Epic's success section and
  `## Scope`. The success section is `## Success Criteria` or `## Success Metrics`: readers accept
  both, writers write `## Success Criteria`.
- A ticket description carries the one-line purpose and the plan path, never the plan's content.

## Finish line

The human approves an epic together with its finish line (L0 §Units); the line is where the epic ends.

- **Frontmatter:** `line: [KEY, KEY, …]`, the story keys the epic delivers (at most the crew's
  `limits.epic_stories` upper bound, ~8), and `line_goal: <one measurable goal>`, the number the
  line moves. `ready_gate.py epic` refuses an `approved` epic without both, a key named twice or an
  empty line, and warns above the limit.
- **Who selects:** a refiner selects its own story (`board.py select <KEY> --refiner`) only when the
  epic is approved and the key stands on its `line:`; an epic without a line, a key off it, a story
  without an epic, or an epic with `select: owner` leave Selected to the product role. `select: owner`
  is the owner's switch for an independent counter-read before Selected: a green Ready panel never
  replaces it. A crew that sets `select.refiner: false` (`scripts/crew.py` § Schema) leaves every
  story to the product role, whatever its epic says: the crew-wide form of `select: owner`.
- **Free inside the line:** a sharper AC, a fix of a defect against an existing AC, small work at the
  place the story already touches. None of it needs a new key.
- **Beyond the line:** a new story, new visible behaviour or a new place (one more instance of what a
  story corrects) is not built. It becomes one entry under `## Extensions`:

  ```markdown
  ## Extensions

  - [ ] <KEY or short name> <what, one line> (found by <session>, YYYY-MM-DD)
  - [x] <entry> → line | follow-up epic <KEY> | dropped (<human>, YYYY-MM-DD)
  ```

  The product owner pre-sorts the open (`- [ ]`) entries; the human decides each one in the decision
  bundle. "Line" adds the key to `line:` (the master writes it with an Updates Log line); "follow-up
  epic" goes to a new epic plan; "dropped" stays as a checked line. `board.py move <KEY> backlog
  --epic <E>` refuses a key not on `line:` and names this list.
- **Progress:** `epic_state.py line <epic plan>` prints `n/m line done · k extensions open · age`
  against the board's last state per key (Done); the /board work pane shows `n/m line · k ext · age`
  per epic, counting merged line stories, so it runs ahead of the script between merge and acceptance.
- **Finish line reached:** when the last line key is Done (`/we:accept` § 4 tells the epic's master,
  the coordinator's sweep is the backstop), the master posts "good as is?" on the board itself (`board.py ask`) and tells the coordinator "finish line reached": **good** → close the epic;
  **X is missing** → a small new line on this epic; **an extension** → a follow-up epic. No story of
  the epic is built until the answer.
- **Running epics** approved before the finish line have no `line:`: `board.py move … backlog` warns
  and moves until their master draws the line (a proposal the human approves like a new epic).

## Upkeep after a merge

The epic plan holds no story table: `/flow` and the `/board` work pane derive it from the story plans
whose `epic:` names the epic and from their PRs (`hooks/plans/plans.ts`). After a story's merge the
epic gets exactly one line in `## Updates Log`, committed per `${CLAUDE_PLUGIN_ROOT}/references/plan-commit.md`, and
`updated:` set; `we-worker close <KEY>` (`scripts/worker_close.py`) writes it on the story's move to
In Review, naming every merged PR of the story:

```text
- YYYY-MM-DD — <KEY> merged (PR #<n>); <epic_state.py line summary, with a line:>; <a learning the next plan needs | none>
```

A learning longer than that line goes into the next story's plan, never into the epic. An older epic
plan may still carry a block between `<!-- mirror:start` and `<!-- mirror:end -->`: nothing reads
it; the next commit to the epic deletes it.

## Target and mode

1. Target, first hit wins: the argument (key, path or slug); the branch name; the newest epic plan in
   `docs/plans/` with an active status; else list the candidates and ask one question.
2. Mode from the words around the target: none → **Status** (read-only, the default); "refine",
   "update", "sharpen" → **Refine**; "new" or a slug with no file → **Create**. Ambiguous → one question. A ticket key that is a Story, or matches
   no `*-epic.md` and no ticketing Epic, is **Create** from that ticket's newest comment (a slice cut
   written there before `/we:epic {TICKET}` was printed).
3. Status loads the plan, the goal file's metric it serves and the children (ticketing children of
   the epic ticket, else the story plans whose `epic:` matches; status buckets Done · Active · Refined
   (plan passes the Ready gate, not started) · Backlog · Blocked, mapped through
   `.weside/orchestrate.md` § Ticket states), and renders: header line with status and path, the
   children per bucket, one risk-driven next move, and the offers `[f]` Refine · `[q]` done. Status
   never writes.
4. Each transition (Status → Refine) needs the user's choice.

## Drafting an epic (Refine and Create)

1. Interview in the session with the `/we:grill` discipline: one question per turn with your
   recommendation, a decision on record cited instead of asked, the epic's frame questions in
   order. Read first: the plan, the goal file, the instruction files, ADRs, `docs/plans/out-of-scope/`
   when present, and the glossary the instruction files name.
2. Worktree and commit path: `${CLAUDE_PLUGIN_ROOT}/references/plan-commit.md` (repo fact first, else a detached scratch
   worktree off the default branch, landed by push or docs PR per `plans.land`).
3. Dispatch `Agent(subagent_type: "we:dev-high", description: "draft epic <slug>", prompt: <brief>)`.
   Plan-writing is a named `dev-high` case (`references/worker-dispatch.md` § Choosing the worker); the session's `medium` would write it
   otherwise. A subagent writes a plan file here, never code. Brief: first line `Read <abs>/skills/epic/references/template.md and <abs>/references/epic-plan.md, then follow § Writer contract.`
   (paths as they resolve here); the absolute target path in the scratch worktree; the goal file's
   metric; every interview decision with the rejected alternative and who decided; the user's words
   verbatim where they matter; the records read with the one line each settled.
4. Approval: present the path, the writer's digest and what step 5 will do: the ticket created or
   updated with its title (or re-parented or closed), and where the commit lands. The approval covers
   only what this message names. Feedback goes to the same writer via `SendMessage`. Plan mode is not
   used: it would stop the writer from writing.
5. After approval, straight through: set `status`, run the verb's ticket step, commit and push per
   step 2, remove the scratch worktree, print the output line and the next verb, stop.

## Writer contract

- Write only the target file. No ticket, no commit, no other file, no downstream verb.
- Follow the template's sections in order. On Refine, edit in place: keep the user's prose where the
  interview did not change it.
- Read the goal file and the records the brief names before writing; a contradiction between them
  and the brief is reported, never resolved silently.
- Name a size signal you notice (more than one outcome, more stories than the epic limit) in the
  report instead of re-cutting the epic.
- Final message, one of:

  ```text
  done: <absolute path> | digest: <one line per section written or changed> | warnings: <size signals or none> | decisions not in the brief: <…>
  blocked: <fork in one line> | A: <option + cost> | B: <option + cost> | recommend <X> because <why>
  ```
