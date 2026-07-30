---
description: What makes a story verified — the oracle ladder (CLI/API, UI walkthrough, substitute), the receipt that gates the PR, DEV-before-staging, and why green tests are not evidence. Loaded by /we:orchestrate and /we:story.
---

# Verification

Consumers: `/we:orchestrate` (once at
integration, before the PR), `/we:story` (emits the plan's verification section),
`we:ac-reviewer` (checks the receipt exists and matches).

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

Rules that make the receipt worth having:

- **A screenshot is evidence for a human, not for you.** Assert on structure —
  status codes, JSON fields, accessibility-tree labels and refs — and attach the
  screenshot alongside.
- **State what failed, if something did.** A receipt that only ever says "works"
  is decoration. The four defects that motivated this contract were all found by
  a walkthrough that expected success.
- **`not-applicable` is a legitimate answer and must carry its reason.** What is
  forbidden is silence.

## Where it runs

**DEV first, always.** Staging is shared and visible to others, so deploying
there is a **question to the user, not a step** — even mid-`/loop`. Ask, then
cut the RC.

If DEV cannot be brought up, that is a finding about the environment, not a
licence to skip. Say so and fall to oracle 3.

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
