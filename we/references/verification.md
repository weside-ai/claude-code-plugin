---
description: What makes a story verified — the oracle ladder (CLI/API, UI walkthrough, substitute), the receipt that gates the PR, DEV-before-staging, and why green tests are not evidence. Loaded by /we:orchestrate and /we:story.
---

# Verification

Consumers: `/we:orchestrate` (once at integration, before the PR), `/we:story` (emits the
plan's verification section), `we:ac-reviewer` (checks the receipt exists and matches),
`we:pr-creator` (copies the receipt into the PR body; the hook gates on it).

## Why this exists

Green tests prove that the units behave the way they were written. They cannot
prove the app **navigates, renders, persists and survives a reload** — and, more
sharply: **a test written by whoever wrote the code shares that code's blind
spots by construction.** Believe the screen is named `rooms` and you write the
assertion against `rooms`; both are equally wrong and both are green.

A run against a live instance is the only step whose oracle is not the author's
own mental model. That is the whole argument. Everything below is mechanism.

## The oracle ladder — cheapest first

| Oracle | Use when | Costs |
|---|---|---|
| **1 · CLI / API** | Default. There is an endpoint, a job, a command. Drive it against a running instance and assert on machine-readable output. | Scriptable, headless, loop-safe |
| **2 · UI walkthrough** | An AC says the user can *see*, *tap*, *reach* or *navigate to* something. **Reachability is not provable from an endpoint** — an endpoint that nothing calls answers 200 all day. | Expensive, irreplaceable |
| **3 · Substitute** | Neither is possible: native geometry, push, store builds, a surface with no local backend. Name the substitute AND what stays owed. | — |
| **4 · Not applicable** | The change has no runtime behaviour — docs, a rule, a comment, a rename with no reachable surface. **Say it; never let it be assumed.** | — |

Climb only as far as the ACs demand. A backend-only story stops at 1. A story
whose AC says "the button opens the sheet" does not.

## The receipt

Verification is a claim, and a claim needs evidence attached where the next
person will look: **the PR body, under `## Verification`.** Minimum:

```markdown
## Verification

**Oracle:** cli | ui | substitute | not-applicable
**Seed:** <copy-pasteable command that puts the system in the asserted state>
**Asserted:** <what was observed — endpoint + status + field, or route + label + ref>
**Not proven:** <what this oracle cannot show, and who owes it>
```

**The four labels are read literally, by a hook, at `gh pr create`.** Write them exactly as
above — `**Seed:**`, not `**Seed (the one that discriminates):**` — and pass the body as
`--body-file`, or the gate refuses the PR and says the receipt is still a template.
Decorating a label costs a round trip (measured 2026-09-19).

Rules that make the receipt worth having:

- **A screenshot is evidence for a human, not for you.** Assert on structure —
  status codes, JSON fields, accessibility-tree labels and refs — and attach the
  screenshot alongside.
- **State what failed, if something did.** A receipt that only ever says "works"
  is decoration. The four defects that motivated this contract were all found by
  a walkthrough that expected success.
- **Run the control arm, and believe it when it comes back green.** A probe whose
  timing depends on something you do not control measures that thing, not your
  change: WA-2302 SIGTERMed a backend mid-turn and the fixed tree looked perfect,
  until the same probe on the UNFIXED tree also passed — the two turns had taken
  14.7 s and 6.0 s. Fix the one variable that decides the outcome, keep everything
  else real, and put both arms' output in the receipt. A green control arm is not
  a nuisance to explain away; it is the probe telling you it proves nothing.
- **`not-applicable` is a legitimate answer and must carry its reason.** What is
  forbidden is silence.

## Where it runs

**DEV first, always.** Staging is shared and visible to others, so deploying
there is a **question to the user, not a step** — even mid-`/loop`. Ask, then
cut the RC.

If DEV cannot be brought up, that is a finding about the environment, not a
licence to skip. Say so and fall to oracle 3.

**The dev ports are a singleton, deliberately, and you release yours when the round ends.**
Verification serialises across sessions, and that is the cheaper trade — decided 2026-09-22
after a night where two sessions wanted DEV:

- **The browser driver is single-owner too.** One daemon, one profile; a second `close --all`
  kills the first. Per-session backends would therefore parallelise oracle 1 only and leave
  oracle 2 — the expensive half — serialised anyway.
- **The isolation that protects correctness already exists** at the database, per worktree. What
  per-session ports would add is configuration surface: the app pointing at the right backend,
  the CORS and auth origins, the CLI's `--api-url`. Every one of those is a fresh way to produce
  a receipt against the wrong tree, and a receipt against the wrong tree is worse than none,
  because it looks like one.
- **Serialisation was not what cost the time** in the measured case. What cost it was an
  ownership question the documented lookup could not answer. Fix the lookup, not the topology.

Revisit when three or more sessions routinely need DEV at once — then the queue, not the config
surface, is the larger cost. Until then: check the port before you start, ask its owner rather
than clearing it, and stop your own server as soon as the round ends.

## The standing consequence: a missing verb is a bug in the CLI

If verifying needs a multi-step shell dance the project's own CLI cannot do,
**that verb is missing and ships in the same wave.** Not a snippet in a
transcript — transcripts rot, verbs compound. This is also what makes an
unattended `/loop` round honest: a loop can only verify what is scriptable.

Same for a fixture, a seed command, a reset. Recurring setup belongs in tooling.

## Repo recipes

The contract above is runtime-agnostic. The concrete commands live in the repo:

- `<repo>/.weside/verify.md` — how DEV comes up here, the CLI verbs, the browser
  driver, which journeys exist, how staging is cut.
- `<repo>/.weside/config.json` → `verification.required: true` arms the PR gate
  (`hooks/verification_gate.py`). Absent or false → advisory only.

Missing recipe file → do not silently skip. Say once that the repo has no recipe,
verify with what the stack offers (its own CLI, `curl`, its test client), and
propose adding `.weside/verify.md` in the same PR.
