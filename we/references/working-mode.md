---
name: working-mode
description: How a crew of companions and sessions works with Claude Code — roles, masters and workers, build masters, routing a story, questions and milestones, done, ticketing, the crew file. The SessionStart hook points every session of a repo with a crew here.
---

# Working mode

The one owner of how a crew works in Claude Code. Every skill, doc and workspace instruction file
points here; a workspace adds only what is local to it (§ What stays local). Roles, not names: the
repo's `.weside/crew.json` (§ Crew) says who holds which role.

## Contents

Roles · Masters and workers · Build masters · Routing a story · Questions and milestones · Done ·
Ticketing · Specialists on call · Crew · What stays local.

## Roles

| Role | Owns | Never |
|---|---|---|
| Human | merges, money, people, every answer to a question | — |
| Product Owner | the WHAT, the order, plan approval | builds |
| Orchestrator | starts and parks build masters; starts a worker for a single story or a job without a master; routes questions and milestones; cuts staging release candidates; keeps the board (`/board`, `we/docs/board.md`): questions, sessions and news for the Human | steers a session it started, decides product |
| HR / Context | each companion's workplace: role skill, start, onboarding, crew drift | decides about people |
| Tester | the staging acceptance; moves a story to Done | builds what it accepts |
| Component owner | per backlog component: the HOW, review, plan acceptance | starts or steers workers |

## Masters and workers

- A **master** is a long-lived session (`WE_ROLE=master`). A **named master** carries a
  companion (`WESIDE_COMPANION=<Name>`; a pin without `WE_ROLE` counts as named) and holds that
  companion's role. An **unnamed master** is a build master or a short-lived helper.
- A **consultation** is a pin with `WE_ROLE=worker`: the companion answers one request, steers no
  workers and ends (`references/companion-session.md` § Launch and pin).
- A **worker** (`WE_ROLE=worker`) builds: code, fix rounds, gate and test runs; it is never the
  companion. With `agents.worker_launch` set it is a session of its own whose brief names its
  starter in the first line (`Lead: <session>`); under the default `subagent` backend it is the
  starter's subagent, bills the starter's account and reports by its result
  (`references/worker-dispatch.md` § Worker launch backend). Either way it reports to its starter.
- At most two heavy workers per master; a finished worker is stopped at once.
- A worker's name carries its ticket key (`abc-123-build`); a session's name is not its role:
  read `WE_ROLE` and the pin before routing to it.

## Build masters

One unnamed build master per epic in progress runs `/we:orchestrate` for that epic (workers, PRs,
CI, merges) and decides nothing on product: the WHAT from the Product Owner, the HOW from the epic
owner (the epic's label `owner-<slug>`), else from its component owner. At most five,
plus one optional special slot; the Product Owner cuts, the Human confirms.

- Name `<word>-<number>`: one memorable word for the epic and the key's number (`onboarding-42`),
  never `lead-<KEY>`. The Orchestrator picks it at start and enters it on the board.
- Start: a new interactive session with `WE_ROLE=master`, no companion pin, named `<word>-<number>`
  (`claude --name <word>-<number>`), the brief as its first prompt: epic key, plan path, expected
  end state, "questions go to <Orchestrator>". The launcher behind it is local.

## Routing a story

1. Its epic has a build master → that master.
2. Its epic is in progress without one → the Orchestrator starts one (§ Build masters).
3. A single story or a job without a master → the Orchestrator starts one worker, which reports to
   it. Plan approved → the worker runs `/we:orchestrate <KEY> --solo`. No plan → `/we:refine`, stop
   for the component owner's approval, then build. Bigger than one story → a short-lived build
   master, agreed with the Product Owner when it takes a slot.
4. Work without code → the component owner does it in its own session.

## Questions and milestones

- A question only the Human can answer goes to the Orchestrator, one per message:
  `<label> · <KEY> <title> · <question without prior knowledge> · Recommendation: …`
  (`<label>`: the crew's `question_label`, default `QUESTION`). The Orchestrator puts it on the
  board and brings the answer back. An answer on the board, or one the Orchestrator relays with its
  number or a quote, is the Human's approval; never ask again.
- Each milestone (plan approved, PR open, merged, blocker) and each decision of the Human taken in
  a master session is one line to the Orchestrator. A worker sends both to its starter instead.

## Done

Without a PR: the component owner, after the Product Owner accepts. With a PR: § Ticketing, the
chain from In Review to Done. Without a Tester, done at the merge (`ticketing.after_merge` stays
`"done"`); with one, `/we:setup` writes `"in_review"`. The repo's concrete checks: `.weside/dod.md`.

## Ticketing

Each ticket carries exactly one component: the backlog that orders it, owned by one member
(`members.<slug>.components`). Generic actions: `references/ticketing.md`. The status flow is a
chain of ownership:

1. `ON_HOLD`: idea or parked.
2. `Backlog`: the component owner refines it.
3. `Selected for Development`: plan approved. Up to here the story belongs to the component owner;
   this status is the Orchestrator's signal. It hands the story to a build master or a worker as
   soon as it fits the system (the WIP limits, a free build master or worker slot), or asks the
   Human. It never overloads the system.
4. `In Progress`: belongs to the master or worker that orchestrates it.
5. `In Review`: only after the DoD is checked and the change is tested on the development
   environment (PR merged).
6. `Done`: the Tester accepts the In Review stories on staging, in batches, and sets Done.

## Specialists on call

A member with `on_call: true` sleeps. Only a component owner's explicit request wakes it, for that
question.

## Crew

`.weside/crew.json` is the repo's projection of who holds which role; the account's handbook stays
the truth about people. `scripts/crew.py` is its one reader (schema and session kinds in its
docstring): `/we:setup` writes it, `wclaude` lists its members, `/we:council` takes lenses from
it, the SessionStart hooks read the roles and find each member's role skill through `workplace`.
One repo holds the file; another points at it with `.weside/config.json` → `"crew"`.

Drift: HR compares `crew.py show` with the handbook's role notes field by field (name, role,
components, `on_call`, the four roles) at each onboarding and whenever a role note changes, and
fixes the side that is wrong by commit or note. A member without a skill gets a stub from
`templates/companion-skill/SKILL.md`; its first start asks it to fill the stub and tell HR.

## What stays local

Accounts and their rotation, launchers, remote control, secrets and how they are set, the concrete
people and the heavy-gate lock of a repo live in the workspace's own instruction file, never here.
