---
name: story
description: >
  Story (Solo): one sprint-sized Story with a build-ready plan — ticket minimal, plan detailed.
  Triggers: "/we:story", "new story", "refine story", "acceptance criteria".
---

# /we:story — Story (Solo) at the Feature-slice altitude

You turn one sprint-sized change into an approved plan `docs/plans/{TICKET}-story.md` plus a minimal ticket.
Read the repo's instruction files and decision records before the first question; ask the user only what they cannot answer.
The interview runs in this session; a `we:dev-high` agent running `/we:refine` writes the plan.
Wanted stops: one interview question at a time, and the approval. Every other status note goes with the next tool call.
After the approval you run step 5 straight through, print the next verb and stop: no branch, no build.

Plan contract (frontmatter, sections, the refined scan): `${CLAUDE_PLUGIN_ROOT}/skills/story/references/plan-format.md`.
Epic work belongs to `/we:epic` or `/we:meet epic`. A contentious story goes through `/we:meet story`, which hands
off here. The approved plan feeds `/we:orchestrate {TICKET}`.

| Invocation | Mode |
|---|---|
| `/we:story {TICKET}` | Refine an existing story: steps 1–5. |
| `/we:story "description"` | Create: steps 1–5; the ticket is created in step 5. |
| `/we:story` | Ask what the user wants to build, then create. Several stories → one at a time, the parent epic first via `/we:epic`. |

## 1. Load — before the first question

- **Key.** `{TICKET}` is the Jira key, the bare GitHub issue number, or a kebab-case slug without ticketing; it
  never varies. Tool detection, reading and moving tickets: `${CLAUDE_PLUGIN_ROOT}/references/ticketing.md`.
  Print `/rename {TICKET}` once when the session title is not already the key.
- **Ticket with all comments.** Comments carry the later corrections. Note the newest comment's id for
  `comments_read_through`. `epic:` is the ticket's parent key; plan-only, the slug of the
  `docs/plans/*-epic.md` that lists the story.
- **Existing plan.** Read it in full; the refiner edits it in place and keeps its Design Decisions rows.
- **Decision records.** The instruction file chain (`AGENTS.md`, else `CLAUDE.md`), the repo rules for the paths
  the story touches, the ADR directory, the epic plan, `.weside/dor.md`, the vision (the PRD
  `docs/plans/*/PRD.md` that `/we:vision` writes; none → `.weside/vision.md`; neither → no vision check), and the
  glossary the instruction file names (else `CONTEXT.md`). The most frequent correction in past sessions was a
  wrong assumption about the environment or an earlier decision; these files hold both.
- **Code.** The seam the story names: the code graph where `.weside/config.json` → `tools.graphify` is true,
  else `rg` on the identifiers.

## 2. Understand — the interview

- The discipline of `/we:grill`: one question per turn, each with your recommended answer; what the repo
  answers is looked up, not asked.
- A decision already on record is stated with its source ("ADR-0065 settles this: …"), not asked again. Ask
  when two records disagree, or when the record predates the change the ticket describes.
- A vague "why": the first question is what success looks like. ACs come after the goal is clear.
- A tension with the vision (step 1) or the epic's `## Success Criteria` (older epics: `## Success Metrics`) is named.
- A resolved term becomes a glossary line (`${CLAUDE_PLUGIN_ROOT}/skills/grill/references/context-format.md`); collect
  the lines and write them in step 5's commit.
- **Too big — which kind?** Independent slices with separate user value and separate PRs are epic-sized: write
  the slice cut, the sequencing and the alternative the user rejected as one comment on the existing ticket,
  print `/we:epic {TICKET}` and stop. One coherent change with several phases (a refactor, a multi-layer fix,
  a migration) stays one story with a phased plan.
- The interview ends when every branch that shapes an AC has an answer or a recorded default.

## 3. Write the plan — `we:dev-high`

Open the scratch worktree `<scratch>/plan-{TICKET}` per `${CLAUDE_PLUGIN_ROOT}/references/plan-commit.md` steps 1–2 (repo fact first).

Dispatch `Agent(subagent_type: "we:dev-high", description: "refine {TICKET}", prompt: <brief>)`. Plan-writing
is a named `dev-high` case (Foxy 27.09.); the session's own `medium` default would otherwise write it. The brief:

- first line: `Read ${CLAUDE_PLUGIN_ROOT}/skills/refine/SKILL.md and follow it.` (the path as it resolves here);
- the absolute target path inside the scratch worktree, `{TICKET}`, `epic`, `depends_on`, `comments_read_through`;
- every decision from the interview with the alternative rejected and who decided, the user's answers verbatim,
  what the user cares about most;
- the records and files you read, with the one line each settled;
- create mode: "no ticket yet — work from this brief; step 5 replaces the slug with the new key".

A `blocked` report carries a fork: ask the user that one question with the refiner's recommendation, then
`SendMessage` the answer to the same agent; it keeps its context.

## 4. Approval

1. Run the refined scan (`${CLAUDE_PLUGIN_ROOT}/skills/story/references/plan-format.md` § The refined scan) with `rg` on
   the file, and check for `## Open Fork`.
   A failure goes back to the refiner via `SendMessage`, not to the user.
2. Present in one message: the absolute plan path, the refiner's digest (ACs one line each, phases with their
   risk, decisions the user did not state), and what step 5 will do (ticket created or updated, where the
   commit lands).
3. Feedback → `SendMessage` to the refiner, scan again, present again.

Plan mode is not used: the Agent tool gives a subagent the parent's permission mode, and plan mode would stop
the refiner from writing the file.

## 5. After approval — straight through

1. Set `status: approved`. Write the collected glossary lines.
2. **Ticket** (skip without ticketing):
   - Create mode: create exactly this one ticket. Rename the file to the new key and set `story:`.
   - Move it to the repo's plan-approved state (`.weside/orchestrate.md` § Ticket states; else the state meaning
     refined, not started; ask once when the names are ambiguous): `${CLAUDE_PLUGIN_ROOT}/references/ticketing.md`.
   - Description is the minimal body:

     ```markdown
     ## User Story
     As <role> I want <feature> so that <benefit>.

     ## Plan
     Implementation Plan: docs/plans/{TICKET}-story.md
     ```

   - One comment only when the plan overrides a statement in the ticket or its comments, naming each override;
     set `comments_read_through:` to that comment's id.
   - No other ticket. Side findings from the interview go into the output as a list (Foxy 25.09.).
3. Scan again, then commit, push and clean up per `${CLAUDE_PLUGIN_ROOT}/references/plan-commit.md` steps 4–6: files
   `docs/plans/{TICKET}-story.md` plus the glossary file if changed, subject
   `docs({TICKET}): story plan — <title>`.
4. Output, then stop:

   ```text
   Plan: docs/plans/{TICKET}-story.md (<sha> on <branch>). Ticket: <state>.
   Next: /we:orchestrate {TICKET}
   Not filed: <one line per side finding, only when there are any>
   ```
