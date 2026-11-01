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
| Owner | the human: merges, money, people, every answer to a question | — |
| Product Owner | the WHAT, the order, plan approval | builds |
| Orchestrator | starts and parks masters, routes questions and milestones, cuts staging release candidates, keeps the board (`/board`, `we/docs/board.md`): questions, sessions and news for the Owner | steers a worker, decides product |
| HR / Context | each companion's workplace and context: role skill, start, onboarding, crew drift | decides about people |
| Tester | the staging acceptance that makes a story done | builds what it accepts |
| Component owner | per backlog component: the HOW, review, plan acceptance | steers workers |

## Masters and workers

- A **master** is a long-lived session (`WE_ROLE=master`). A **named master** carries a
  companion (`WESIDE_COMPANION=<Name>`; a pin without `WE_ROLE` counts as named) and holds that
  companion's role. An **unnamed master** is a build master or a short-lived helper.
- A **worker** (`WE_ROLE=worker`) builds: code, fix rounds, gate and test runs. It is a session of
  its own (`agents.worker_launch`, `references/worker-dispatch.md` § Worker launch backend), never
  the companion. An `Agent` subagent bills the account of the session that calls it.
- At most two heavy workers per master; a finished worker is stopped at once.
- A worker's name carries its ticket key (`wa2796-build`, `2796-fix`); its brief names its starter
  in the first line (`Lead: <session>`), so every worker maps to the session that started it.
- A session's name is not its role: read `WE_ROLE` and the pin before routing to it.

## Build masters

One unnamed build master per epic in progress runs `/we:orchestrate` for that epic (workers, PRs,
CI, merges) and decides nothing on product: the WHAT from the Product Owner, the HOW from the
epic's owner. At most five, plus one optional special slot; the Product Owner cuts, the Owner
confirms. The name is `<word>-<number>`: one memorable word for the epic and the key's number
(`gum-2662`, `onboarding-2201`), never `lead-<KEY>`. The Orchestrator picks it at start and enters
it on the board. The epic's owner is the owner of its component, unless the epic carries the label
`owner-<slug>`.

## Routing a story

1. Its epic has a build master → that master.
2. Its epic is in progress without one → the Orchestrator starts one.
3. A single story or a repair → one worker that runs `/we:refine`, stops for the owner's approval,
   then runs `/we:orchestrate <KEY> --solo`. Bigger than one story → a short-lived build master,
   agreed with the Product Owner when it takes a slot.
4. Work without code → the component owner does it in its own session.

## Questions and milestones

- A question only the Owner can answer goes to the Orchestrator, one per message:
  `<label> · <KEY> <title> · <question without prior knowledge> · Recommendation: …`
  (`<label>`: the crew's `question_label`, default `QUESTION`). The Orchestrator puts it on the
  board and brings the answer back. An answer on the board, or one the Orchestrator relays with its
  number or a quote, is the Owner's approval; never ask again.
- Each milestone (plan approved, PR open, merged, blocker) and each decision of the Owner taken in
  a session is one line to the Orchestrator.

## Done

With a PR: merged → In Review; done after the Tester's staging acceptance. Without a PR: the
component owner, after the Product Owner accepts. The repo's concrete checks: `.weside/dod.md`.

## Ticketing

Each ticket carries exactly one component: the backlog that orders it, owned by one member
(`members.<slug>.components`). Status: `ON_HOLD` = idea or parked, `Backlog` = refine now,
`Selected for Development` = plan approved. Generic actions: `references/ticketing.md`.

## Specialists on call

A member with `on_call: true` sleeps. Only an owner's explicit request wakes it, for that question.

## Crew

`.weside/crew.json` is the repo's projection of who holds which role; the account's handbook stays
the truth about people. `scripts/crew.py` is its one reader (schema in its docstring): `/we:setup`
writes it, `wclaude` lists its members, `/we:council` takes lenses from it, the SessionStart hooks
read the roles and find each member's role skill through `workplace`. One repo holds the file;
another points at it with `.weside/config.json` → `"crew": "<relative path>"`.

Drift: HR compares `crew.py show` with the handbook's role notes field by field (name, role,
components, `on_call`, the four roles) at each onboarding and whenever a role note changes, and
fixes the side that is wrong by commit or note. A member without a skill gets a stub from
`templates/companion-skill/SKILL.md`; its first start asks it to fill the stub and tell HR.

## What stays local

Accounts and their rotation, remote control, secrets and how they are set, the concrete people
and the heavy-gate lock of a repo live in the workspace's own instruction file, never here.
