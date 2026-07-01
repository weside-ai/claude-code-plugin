# `--refine-ahead` P3 — the autonomous refiner-teammate lane

**OFF by default.** Enable only after a `--rehearsal` go/no-go proves it (see `rehearsal.md`). Until then, all refinement runs the P2 path (Lead refines interactively with the user).

P2 has the Lead refine interactively. P3 adds a **second refine lane**: for a `refinable` story whose
context the Lead can fully front-load (no human design input needed), dispatch **one** refiner-teammate
(`refiner-{TICKET}`) so refinement *also* parallelizes — the Lead discusses story N+1 with the user
while a refiner drafts N+2 and builders build N. **Cap: ≤1 refiner** (a symmetric runaway guard to the
≤2 build cap).

## Strict duty split (this is what makes it safe)

The refiner-teammate **produces the plan file and nothing else** — it needs only the **Write** tool. The **Lead** is the single writer + verifier:

- **Refiner:** draft → `Write` `docs/plans/{TICKET}-story.md` → one `SendMessage` with the path. No
  git, no `orchestration.py`, no `story ready`, no checkpoint.
- **Lead, on refiner-done:** run `story ready` (the real DoR gate on the actual body) → if the story
  left `refinable` (passed), run `story checkpoint refined` + commit the plan to the main worktree → if
  it failed, **retry once** (re-dispatch with the specific missing-token feedback, e.g. "no `### Phase`
  header") → still failing, hand it to the P2 Lead-interactive lane and mark it held `refine failed —
  needs human`.

Why the split: (a) under default/auto permission mode every teammate **Bash** call is denied (the same
reason builders need `acceptEdits`) — a Write-only refiner sidesteps that. (b) It keeps the Lead the
sole writer of `docs/plans/` + `orchestration.db` on main (no two-writer git/DB race; the Mode B
"Lead never lets a teammate commit to main" invariant). (c) DoR-verify becomes a **Lead** act —
state-as-truth: never trust the refiner's "done", run the scan yourself.

## Refiner-Brief

Write-only; a *direct template*, NOT a `/we:story` invocation — `/we:story` is interactive by construction and would stall a teammate at its ExitPlanMode approval gate:

```text
You are refiner-{TICKET}, a teammate spawned into this session's implicit team. The lead is "team-lead".

Your ONLY job: write a build-ready story plan to docs/plans/{TICKET}-story.md, then report its path.
You have NO user to ask — all the context you need is below. Do NOT use EnterPlanMode/ExitPlanMode.
Do NOT run git, gh, or any orchestration command. Use the Write tool for the file. Nothing else.

CONTEXT (front-loaded — this replaces the interactive clarification a human would give):
  Epic frame:        {epic success-criteria + scope, 3-5 lines}
  This story:        {ticket title + the one-paragraph intent}
  Scope boundaries:  {what is IN / explicitly OUT}
  Known constraints: {seams, deps, prior decisions, the files it will touch}
  Architecture refs: {the 1-3 docs/ files most relevant — read them before drafting}

Write docs/plans/{TICKET}-story.md with frontmatter (story, epic, created, status: draft) and these
sections — they are the readiness gate, all are required:
  ## Context              — a real narrative brief (NOT one line): why, the seam, what done means (>50 words)
  ## Acceptance Criteria  — numbered, each in GWT form: "**Given** … **When** … **Then** …"
  ## Technical Approach    — the patterns/files; reuse over rebuild
  ## Implementation Phases — "### Phase 1", "### Phase 2", … (these exact headers are gate-checked)
  ## Design Decisions      — a table of the real forks + why this option (so the builder doesn't relitigate)
  ## Testing Requirements  — unit/integration/security per AC
Also: ## User Journey, ## Code Guidance, ## Security Review Required, ## Documentation Impact.
If you hit a genuine design fork you cannot resolve from the context above, do NOT guess — SendMessage
the fork to team-lead and wait, so the Lead's call shapes the plan instead of forcing a rework.

REPORTING IS NOT OPTIONAL: your plain-text output is INVISIBLE to the lead. When the file is written,
send EXACTLY ONE message:
  SendMessage(to="team-lead", summary="refiner-{TICKET} done|blocked",
              message="wrote docs/plans/{TICKET}-story.md | blocked: <fork/reason>")
Do not run `story ready` or claim it passed — the Lead verifies. Just write + report.
```
