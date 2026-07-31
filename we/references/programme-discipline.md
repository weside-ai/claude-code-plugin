---
name: programme-discipline
description: How to run a multi-wave programme (an Epic that spans sessions, context windows and compacts) without losing the thread — the state file, living plans, self-verification, and the /loop shape. Loaded by /we:orchestrate and /we:story when the work is bigger than one sitting.
---

# Programme discipline — work that outlives a context window

A Story fits in a session. An Epic with several waves does not: it crosses
compacts, model switches, days off and parallel agents. The failure mode is never
"the code was wrong" — it is **nobody could say where we were**, so the same
decision got re-litigated, a finished piece got rebuilt, or a half-migration sat
in main for a week.

Four habits fix that. They cost minutes per story and they are what makes an
unattended `/loop` legitimate rather than reckless.

## 1. One state file, updated in the same PR as the work

Every programme gets `docs/plans/<epic>-state.md` — small enough to read in
thirty seconds, current enough to trust:

- **Right now** — phase, current wave, what blocks, last verified state, the
  single next action.
- **Decisions locked** — with a "do not re-litigate" heading, because that is
  exactly what a fresh context will do.
- **Open decisions** — who owes them, and whether they block.
- **Board** — one row per story with status and whether a refined plan exists.
- **Progress bars** — parity items ticked, journeys covered, gates live.
- **Verification log** — one row per wave: what was walked, on what, by whom.
- **Update protocol** — restated inside the file, so it survives the author.

The rule that makes it work: **it is updated in the same PR as the change it
describes**, never afterwards, never "when things calm down". A state file that
lags is worse than none, because it is trusted.

Every session and every loop round **starts** by reading it and **ends** by
updating it. If nothing moved, log that — silence and forgetting look identical
from the outside.

## 2. Plans are living documents, not intentions

- A Story's plan is rewritten to match what was actually built **before its PR
  merges** — a Definition-of-Done line, not an afterthought. The next agent reads
  the plan, not the diff.
- The Epic's mirror block is refreshed per wave.
- Checklists (parity, journeys, gates) are ticked in the PR that earns them, so
  they become progress bars instead of aspirations.

A plan that describes an older intention is a trap laid for your successor —
which, after a compact, is you.

## 3. Verify the running thing, don't admire the diff

For anything user-visible: bring the app up, drive it, assert, and say what you
could not prove. Ship a **proof block** with the PR — what was walked, how the
state was seeded, what was asserted, what still owes a manual round. "Tests are
green" is a claim about units; "the app works" is a different claim and needs
different evidence.

Two supporting rules that pay for themselves quickly:

- **Deterministic setup beats clever setup.** Seed state through the project's
  own CLI/API with machine-readable output, not by clicking.
- **Recurring work belongs in the tooling.** The same multi-step dance done twice
  is a missing subcommand. Add it to the project's CLI in the same wave —
  transcripts rot, tools compound.

## 4. `/loop` is the shape of long-running work

"Keep going until X" is a loop of **build → verify → write the state file → pick
the next step**. It only works when:

- the **state file** carries memory between rounds (the loop has no context),
- **verification is scripted** and unattended (else every round pays setup),
- the **exit criterion is written down** and checkable, not felt,
- and each round leaves main releasable, so stopping mid-programme is safe.

If those four are not true yet, the first loop round's job is to make them true.

## 5. Two failure modes to name out loud

- **Scope drift.** A story changes only what its ACs name; anything else found
  becomes a ticket. This is the difference between five waves and fifteen.
- **Decision latency.** Many stories × open questions ÷ one human = the real
  bottleneck. Batch decisions at wave boundaries and surface each story's
  decisions *before* building, not mid-build.
- **The idle wait.** A pipeline stage that runs without you (CI, a review round,
  a worker mid-build) is refine time for the next wave, not a pause. The Lead
  that reports "waiting" without a parallel work item has stopped; the programme
  has not. (The behavioural rule lives in `/we:orchestrate` § Forward momentum.)

## 6. Rollback beats hotfix

Without feature flags, main must stay releasable. A wave that fails verification
is reverted **whole** — it is one integration branch — and re-cut. Cheap by
construction, and it removes the pressure to patch forward at 2am.
