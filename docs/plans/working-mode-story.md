---
status: approved
---

# The working mode ships in the plugin

Goal: a team that installs `we` and runs `/we:setup` gets the working mode (roles, masters and
workers, routing, questions, done, ticketing) without copying another workspace's instruction
file. Before this change the mode lived in a workspace instruction file, two companions' role
skills, an untracked `council.json` and two plugin references; now the plugin owns it and a
workspace keeps only what is local to it.

## Decisions

### A. `we/references/working-mode.md` is the one owner

Generic, roles not names: Human, Product Owner, Orchestrator, HR/Context, Tester,
component owners, specialists on call. The Orchestrator keeps questions, sessions and news for the
Human on the board (`we/docs/board.md`).

- Build-master name `<word>-<number>` (`onboarding-42`), never `lead-<KEY>`; only build masters. A
  worker's name carries its key; its brief names its starter in the first line
  (`worker_launch.py` now writes `Lead:` first).
- Question line `<label> · <KEY> <title> · <question> · Recommendation: …`; the label is
  `crew.json` → `question_label` (default `QUESTION`), so a team keeps its board prefix.
- Epic owner: the owner of the epic's component; an override is the label `owner-<slug>` on the
  epic. Not in `crew.json`: epic state is volatile and lives in ticketing.
- Stays local: accounts and rotation, remote control, secrets, the concrete people, a repo's
  heavy-gate lock.

### B. A tracked `.weside/crew.json` replaces `council.json` (no fallback)

`council.json` was gitignored by convention, copied per repo and drifting; "council" names one
consumer, not the crew. Schema in `we/scripts/crew.py` (the one reader): `roles` (product_owner,
orchestrator, hr, tester → member slug), `members.<slug>` with `name`, `role`, `title`, `lens`,
`components`, `workplace`, `on_call`, plus `skill_prefix` and `question_label`. One repo holds the
file; another points at it with `.weside/config.json` → `"crew": "<relative path>"`. Readers moved:
`wclaude`, `council_lens.py` (`/we:council`), both SessionStart hooks, `/we:setup`. The rollout
script `scripts/bootstrap-weside-repo.py`, a second writer of `council.json`, is removed.

Setup proposes the crew from the account's handbook with the weside MCP, else asks. The handbook
stays the truth; HR checks drift with `crew.py show` against the handbook's role notes.

### C. SessionStart core: `hooks/working_mode_on_start.py`

Only with a crew; every source; role from `WE_ROLE` + `WESIDE_COMPANION` (worker · named master,
also a pin without `WE_ROLE` · unnamed master). Names the PO, the Orchestrator, where questions go,
and the reference path. Budget ≤ 10 lines / 1,200 characters, asserted per kind in the test.

### D. Role-skill stubs, no links

`we/templates/companion-skill/SKILL.md` (the skeleton, marker `<!-- we:stub`); `crew.py stubs
--write` creates one per member without a skill in its `workplace`. `materialize_on_start.py`
finds the skill through `crew.py skill-path`: loadable → invoke; only in the workplace → read by
path (no link into `~/.claude/skills/` needed); a stub → fill it and tell HR.

### Without a weside account

A team gets `working-mode.md`, the crew from setup's questions, the `wclaude` menu, the start
core, stubs and the fill note, council lenses with titles. Missing: materialize, the handbook
proposal and drift check, the MCP pin header, wake.

### Review round (simulation of the draft)

- One resolver `crew.session_kind` for both hooks, with a fourth kind `consult` (pin +
  `WE_ROLE=worker`): the companion answers one request and ends.
- The Orchestrator starts sessions and steers none: build masters, and a worker for a single story
  or a job without a master, which reports to it (plan approved → `--solo`; else `/we:refine`, the
  component owner's acceptance, then build). Start recipe for a build master in § Build masters.
- The core carries one line per `roles.*` holder with its duties; a worker sends questions and its
  report to its starter; the last line is the imperative to read the reference.
- Status flow as a chain of ownership in § Ticketing (component owner → Orchestrator → the
  orchestrating session → Tester).
- Done: `/we:setup` writes `after_merge: "in_review"` when the crew has a Tester, who moves a story
  to Done; without a Tester, done at the merge.
- Without `weside_account: true` a pinned session gets its title and role-skill line, no
  `/we:materialize`. `find` stops at the repo root; setup asks the skill prefix.
- The gate hook YAML moved from setup to `optimization-store.md` § Gate hook (setup back to 168
  lines); the indiscretion check also catches a ticket key glued into a name.

## Budgets

`working-mode.md` 111 lines with `## Contents`; `setup/SKILL.md` 168 lines; hook core ≤ 10 lines / 1,200 characters (test; about 930 for a seven-member crew);
skill listing ≤ 6,000 characters (validator); `check-instruction-budget.py` 0 errors.

## Verification

- **Oracle:** `pytest -q we scripts` (crew resolver and pointer, hook core per role and its
  length, pin without `WE_ROLE`, workplace read note, stub note, `wclaude` menu and
  `council_lens.py` from the crew, `Lead:` first in a worker brief), then a live start of the hooks
  against a real crew.
