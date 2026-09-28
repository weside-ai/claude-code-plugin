---
name: vision
description: >
  Vision (Solo) at the PRD altitude: creates or sharpens the product's PRD (audience, problem,
  intended change, non-bets) at docs/plans/<vision>/PRD.md. Triggers: "/we:vision", "PRD",
  "write a vision", "refine vision".
---

# /we:vision — Vision (Solo) at the PRD altitude

You sharpen or create one PRD at `docs/plans/<vision>/PRD.md`: who the product is for, what is broken
for them, what changes when it works, what we will not build. One PRD per product, always Markdown, never a ticket.
Vision Solo never decomposes: Sagas come from `/we:meet vision`, each Saga is formulated by `/we:saga`.
Wanted stops: one interview question at a time, and the approval. After the approval you commit, print the next verb and stop.

Shared contract (altitudes, drafting, writer, commit path): `${CLAUDE_PLUGIN_ROOT}/references/apo-hierarchy.md`.
Template: `${CLAUDE_PLUGIN_ROOT}/skills/vision/references/template.md`.

| Invocation | Mode |
|---|---|
| `/we:vision` with a PRD present | Refine |
| `/we:vision "<product>"` with no PRD | Create |
| `/we:vision` and nothing obvious | Ask once: refine, create, or talk it through (talk-through writes no file and ends with the offer to draft) |

## Frame — the four questions

| Question | Sharp looks like |
|---|---|
| Who is this for? | One named audience in a concrete role or situation, never "users". |
| What is broken for them today? | The problem in their words, no solution, no technology. |
| What changes when this works? | The visible difference: what they can do that they could not before. |
| What are we explicitly not building? | The adjacent bets we turn down, with the reason. The question most often skipped. |

Then the bets and assumptions the answers rest on, each falsifiable. A PRD that changes every quarter
is a Saga in disguise: say so. Feature ideas that surface belong to a Saga or Epic; note them for
`/we:meet vision` and return to the frame.

## Steps

1. **Load.** The PRD and its folder (`docs/plans/<vision>/`), `docs/plans/out-of-scope/` if present
   (already-decided non-bets: cite them, do not re-open them), the instruction files, and the existing
   Sagas (`docs/plans/*-saga.md` with `vision: <vision>`). With a materialised Companion, read its goals
   (`list_goals`) and name a tension between them and the PRD; never resolve it silently.
2. **Interview** per `apo-hierarchy.md` § Drafting step 1, walking the four questions. On Refine, read
   back each current answer in your words and ask what has shifted; hedge words ("mostly", "kind of")
   mark the fuzzy edge.
3. **Draft** with a `we:dev-high` writer per § Drafting step 3. The writer rewrites the whole PRD; it is
   short enough.
4. **Approval** per § Drafting step 4, showing the PRD in full.
5. **After approval:** set `updated:` to today, commit per § Drafting step 2, then output and stop:

   ```text
   PRD: docs/plans/<vision>/PRD.md (<sha> on <branch>).
   Next: /we:meet vision — validate the PRD and derive the Sagas.
   ```
