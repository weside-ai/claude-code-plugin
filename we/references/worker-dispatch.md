---
name: worker-dispatch-reference
description: Worker contract, engine backends, the AC-review rule, the bug-hunt dispatch matrix, integration-branch pattern, and verify-before-integrate discipline. Referenced by /we:orchestrate and /we:develop. Loaded on demand.
---

# Worker Dispatch Reference

This document defines the three worker backends, the dev-only worker contract,
the AC-review rule, the bug-hunt dispatch matrix, and the integration-branch /
single-CI pattern. For Codex-specific dispatch mechanics (the single-detach
rule), see [`codex-dispatch.md`](codex-dispatch.md).

**Two separate checks, two separate rhythms.** AC-review (`we:ac-reviewer`) asks
"does this satisfy the Story's acceptance criteria and our DoD?" — it's cheap, so it
runs after every chunk, informationally, plus once more, gating, at integration.
Bug-hunt (Codex adversarial-review or Claude's native `/code-review`) asks "does this
diff actually work?" — it's the expensive pass, so it runs exactly once, at
integration, against the full merged diff. Never run the bug-hunt per chunk; never
skip the AC-review at either point.

---

## Three worker backends

| Backend | How dispatched | When to use |
|---|---|---|
| **Cheap Claude** (Sonnet / Haiku) | `Agent(model: "sonnet", prompt: "…")` inline | Default — always available, no extra config |
| **Codex** | `codex-companion.mjs task --write --cwd <worktree> "…"` | When `tools.codex` is `true` and user confirms; see [`codex-dispatch.md`](codex-dispatch.md) |
| **Foreign engine** | `we/scripts/worker-launch.sh --engine <name> --cwd <worktree> -- <brief>` | When `.weside/engines.local.json` has a profile for that engine; requires Anthropic-compatible endpoint |

The **default executor** is persisted in `.weside/config.json` as `execution.default`
(`claude-sonnet` / `claude-haiku` / `codex` / `<engine-name>`). `/we:setup` wizard writes this
(default: `claude-sonnet`). `/we:orchestrate` reads it; the user can override per-chunk at
execution time.

**Model-tier rule (single owner):** default `sonnet`; `haiku` only for mechanical/boilerplate
chunks; `opus` only when the Lead explicitly requests it for a hard chunk.

---

## Dev-only worker contract

Workers run one chunk of a Story. They stop at commit + push — no PR, no CI, no
ticket work. That is the Lead's responsibility after integrating.

**What every worker does (regardless of backend):**

1. **Locate plan** — read `docs/plans/<story>/` (or chunk brief if dispatched headlessly)
2. **Implement** — the assigned phases/files, respecting the plan's Constraints and Pins,
   and the test discipline the brief states (the Lead reads `test_discipline` from
   `.weside/config.json` and spells the level out in every brief — workers can't load
   references; level semantics: `test-discipline.md`)
3. **Local gates** — lint, type-check, affected tests; fix gate failures before committing
4. **AC-check own diff** (when `review.cross: true`) — see below
5. **Commit** — atomic commit with a clear message referencing the Story/chunk
6. **Push** branch
7. **Report** — structured summary: what changed, gate results, any fork decisions, blockers

Workers **must not**: open PRs, run CI, transition tickets, merge branches, or modify
files outside their assigned chunk scope.

---

## AC-review rule

`we:ac-reviewer` checks a diff against the Story's acceptance criteria and the DoD —
never bugs. It runs at two points, same agent both times:

- **Per chunk** — against the worker's own diff, before committing. Informational, not
  a gate: the worker reads the findings and decides whether to fix before committing;
  findings go into the report either way so the Lead sees them at integration.
- **At integration** — against the full merged diff, once, gating. See
  [`orchestrate/SKILL.md`](../skills/orchestrate/SKILL.md) Step 8.

To disable the per-chunk pass (integration still gates): `review.cross: false` in
`.weside/config.json`. `review.cross` is the one flag that governs both the per-chunk
AC-check and the bug-hunt dispatch below — turning it off skips the early, informational
checks, not the final gate.

## Bug-hunt dispatch

Whoever wrote the code, the **other** engine hunts bugs in it — runs exactly **once**,
at integration, against the full merged diff. Never per chunk; it's the expensive pass.

| Writer | Bug-hunt engine |
|---|---|
| Claude, `tools.codex: true`, script resolves | `/codex:adversarial-review` |
| Anything else — Claude without Codex, Codex, or a foreign engine | Claude's native `/code-review` |

See [`orchestrate/SKILL.md`](../skills/orchestrate/SKILL.md) Step 8 B1b for the
integration-time dispatch, including the mixed-authorship case.

When dispatching Claude's native `/code-review`, point it at
[`test-discipline.md`](test-discipline.md)'s anti-patterns (implementation-coupled,
tautological, horizontal-slicing) as part of what to look for — that check moved here from the
old `code-reviewer` agent and belongs with the other bug-hunt findings, not with `we:ac-reviewer`.

---

## Integration-branch pattern (Lead's responsibility)

`/we:orchestrate` coordinates N workers on N chunk branches. After all workers report:

1. **Verify each worktree actually changed** before integrating — `git -C <worktree> status` / `git log`.
   A worker that reports success without commits or a dirty tree signals a lost dispatch.
   Re-dispatch before integrating; never integrate an empty worktree.

2. **Merge onto one integration branch** — `feat/<story>-integration` (created from the Story branch).
   Resolve conflicts with the plan's Constraints and Pins as the source of truth.

3. **Run CI once** on the integration branch — one PR, not N. The Lead reviews the
   aggregated diff before creating the PR; workers never open PRs.

4. **CI-fix loop** — if CI fails, the Lead fixes inline (or re-dispatches the owning
   worker's chunk); no new PRs per fix.

---

## Foreign-engine brief format

When dispatching to a foreign engine via `worker-launch.sh`, the brief is a
self-contained task description (the foreign model has no plugin context):

```
Story: <ticket or plan path>
Chunk: <phase number(s) / coherent slice> — what "done" means
Files: <the files this chunk owns; do NOT touch anything outside>
Constraints: <conventions, primitives to compose, anti-patterns to avoid>
Pins: <existing behaviour to preserve exactly>
Tests: <the test_discipline level, spelled out — e.g. "write the failing test before the
  code at each seam" (tdd) / "write tests after the code, same change" (tests-after) /
  "no new tests unless stated in Chunk" (off). Always add: no implementation-coupled
  tests, no tautological assertions, mock at system boundaries only.>
Local gates: run lint + type-check + affected tests; fix failures before committing
Done = <concrete checkable outcome — tests green / file:line exists / command exits 0>
Report: diff summary + any fork decisions + gate results; do NOT open a PR.
```

This is the same shape as the Codex chunk brief in [`codex-dispatch.md`](codex-dispatch.md),
adapted for the direct `claude -p` invocation path.
