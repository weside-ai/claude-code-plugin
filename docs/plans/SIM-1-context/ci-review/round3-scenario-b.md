# SIM-1 · ci-review · Round 3 · Scenario B

Table-top run of the twice-revised `we/skills/ci-review/SKILL.md` (291 lines; round 2 read 285)
as the main agent, invoked as `/we:ci-review` in `the host repo` on `feat/TICKET-000-projection`
/ PR #3718. Nothing was executed. All line numbers below are the **291-line** file's.

---

## Trace

### The four demanded answers, up front

- **Does the run terminate? Yes — inside Phase 1a, after four tool calls, with zero blind
  waiting.** Earlier than round 2, and for a new reason (below).
- **The conflict:** L84-88 decides it for me. *"Waiting cannot fix it: **merge**
  `origin/$BASE_REF` (not rebase — a rebase of pushed commits needs a force-push, which is the
  user's call), apply 3f's one-head check if the branch carries migrations, push, then **start
  Phase 1 over**."* I merge `origin/main`, hand-resolve the conflicts, and do **not** rebase.
- **The second head:** the branch adds a migration, so 1a's imported one-head check runs
  **before** the unblocking push. `alembic heads` → two. 3f L243-245: *"If the second head came in
  from the base branch, the merge-heads migration belongs on the base branch, not as a per-branch
  patch — say so and ask rather than patching around it."* → **I stop and ask the user.** Nothing
  is pushed. This matches the host repo's CI rules file L75-76.
- **The human thread:** under a literal run **it is never seen**. Thread collection is 1b (L99-107)
  and the run stops in 1a. L154-155's *"Surface human-authored threads to the user NOW"* never
  fires. See New defect 1.
- **Re-collect after the merge:** yes, ordered explicitly — L88 *"then **start Phase 1 over** —
  the merge changes the diff every later finding is judged against."* It does not fire in this
  scenario, because the run stops before the push it follows.

### Phase 1a — Resolve the run's state (L64-88)

1. L66-70's fresh-shell warning is read first, so I know to re-derive the variables in every
   later block.
2. `Bash:` the L71-79 block verbatim → `GH_AVAILABLE=true`, `PR=3718`,
   `REPO=the app repo`, `OWNER=the host repo-ai`, `REPO_NAME=the host repo`, `BASE_REF=main`,
   `REVIEW_ALLOWLIST` from `.weside/config.json` (L77 — now defined **before** first use), and
   `{"mergeable":"CONFLICTING","mergeStateStatus":"DIRTY","autoMergeRequest":null,"state":"OPEN"}`.
3. L84 fires. `Bash: git fetch origin main` → `git merge origin/main` → **conflicts** (the PR is
   `CONFLICTING` by construction). The skill still gives no guidance for a conflicted *merge* —
   only for a conflicted rebase (L242-243) — so I hand-resolve, migration `down_revision` hunk
   included, unaided (round-2 defect 4, still open).
4. L87 *"apply 3f's one-head check if the branch carries migrations"* → the branch adds a
   migration → `Bash: cd src/backend && alembic heads` → **two heads**, the second from `main`.
5. 3f L243-245 → **stop and ask the user**; the merge-heads migration belongs on `main`.

**The run ends here.** Not reached: the unblocking push, 1b collection, 1c, the findings table,
Phase 2, all of Phase 3, Phase 4. Phase 5 (L288-292) then has an empty findings table, no push
status, no per-check gate status, and no terminal state (L271-279 has no matching row).

**Deliverable to the user:** one question — *"main has a second Alembic head; the merge-heads
migration belongs on main, not on this branch. Land it there and I'll re-run."* — plus a dirty
worktree carrying a hand-resolved merge, and **nothing else**. The `maintainer` question, the
`SEV:WARNING` and the CodeRabbit nitpick never surface.

### The ambiguity I had to resolve to produce that trace

L87 imports "3f's one-head check" without saying how much of 3f it imports. 3f is two sentences:
the *check* (L241-242, "confirm the migration heads resolve to exactly one") and its *failure
branch* (L243-245, "say so and ask"). Reading A imports both → the run stops at 1a, as traced.
Reading B imports only the check → I observe two heads, have no instruction, and push the base's
second head onto the branch anyway — round-2 MAJOR 1's exact outcome. I took **A**, because 3f's
failure branch is the only thing that makes the check actionable and because the host repo's CI rules
L75-76 forbids B's outcome. But the text does not settle it. See New defect 2.

### Counterfactual, one line

If the user lands the merge-heads migration on `main`: re-merge, push (L87), `start Phase 1 over`
(L88) — and on that continued path round-1 defect 6 (3d resolves threads before 3f can stop the
run) bites exactly as it did in round 2, because 3d L198 still precedes 3f L239 unqualified.

---

## Round 2 verdicts

| # | Round-2 defect | Verdict | Evidence (291-line numbers) |
|---|---|---|---|
| **New-1 (MAJOR)** | 1a orders a merge-and-push whose guardrails all live 150 lines downstream; main's second head gets pushed before 3f runs | **FIXED** (operative hazard) | L87 *"apply 3f's one-head check if the branch carries migrations, **push**"* — check *before* push, in that order. In this scenario it is what stops the run. Residue: L15's *"Push once. No leftovers"* still has no stated exemption for the 1a push, but L84-88 orders that push unconditionally by name, so there is no live fork — a wording tension, not a decision I have to make. |
| **New-2 (MAJOR)** | Nothing says to re-collect after the 1a unblocking push | **FIXED** | L88 *"then **start Phase 1 over** — the merge changes the diff every later finding is judged against."* Exactly the smallest fix round 2 proposed. |
| **New-3 (MINOR)** | Terminal states have no row for "stopped to ask the user" | **STILL OPEN — and now worse** | L271-279 still lists three: Green · Cap reached, still red · *"Blocked, nothing to fix"*. This run's actual end state fits none, and the stop moved from 3f (round 2) to 1a, so the run now also has no findings table, no push status and no gate status to report — Phase 5 (L288-292) is empty on every line. |
| **New-4 (MINOR)** | A conflicted MERGE has no guidance; the risky hunk is the migration chain | **STILL OPEN** | L242-243 still warns only about *"a conflicted rebase mid-flow"*. 1a L85 orders a merge on a PR that is `CONFLICTING` by definition, and step 3 above hand-resolves a `down_revision` conflict with no instruction to re-derive the chain from `alembic history`. |
| **New-5 (INFO)** | `--ci-only` reads as a contradiction (narrows "to CI", keeps review source 4) | **STILL OPEN** | L25-26 unchanged: *"narrows the run to CI: collect sources 1 and 4 only"*, no parenthetical explaining that the verdict comment IS the gate's payload. |
| **R1-4** | Assumes a rebase that cannot succeed; hides a force-push | **FIXED** | L86-87 *"**merge** `origin/$BASE_REF` (not rebase — a rebase of pushed commits needs a force-push, which is the user's call)"*. Round 2's bare *"merge or rebase"* at 1a is gone; both places now agree. |
| **R1-10** | `$REVIEW_ALLOWLIST` used before it is defined | **FIXED, with a stale pointer** | Definition moved into 1a's block at L77, 70 lines ahead of first use, plus L66-70's re-derivation rule. But L147 still says *"matches `$REVIEW_ALLOWLIST` (see 3d)"* — it now points *forward* to a re-derivation instead of *back* to the definition. New defect 5. |
| **R1-5** | Human thread has no severity, does not block, no wait/no-wait rule | **STILL OPEN** | L154-155 *"Surface … NOW, before fixing"* vs L229 *"Human threads do not block this gate"*. No line says whether to wait for the answer. Moot in this trace only because 1b is never reached. |
| **R1-6** | 3d resolves bot threads before 3f, a gate that can stop the run | **STILL OPEN** | 3d L198 (*"MANDATORY before push"*) still precedes 3f L239 with no caveat. Does not bite this run (stop is at 1a) — it bites the moment the user unblocks the head. |
| **R1-9 residue** | "A red check with no comment is still a finding", three owners | **STILL OPEN** | L22-23, L121-122 and L172 all state it. |
| **R1-13** | Green `claude-review` row vs `VERDICT:WARNING` marker — no tie-breaker | **STILL OPEN** | L22-23 still one-directional (*"the gate is the check's conclusion, not the comment"*); only L172's *"zero open SEV findings"* keeps the WARNING alive, by side effect. the host repo's CI rules L67-68 covers only the inverse case (red check + PASS comment). |
| **R1-14** | Confirmation of a MUST-fix `SEV:*` is default-disabled | **STILL OPEN** | L151-152 clears a SEV row *"by the re-review after the push"* = Phase 4; Phase 4's exception list (L56-58) still lacks "an unconfirmed SEV finding". |
| **R1-15** | The procedure has a second owner in `references/integration-pipeline.md` | **STILL OPEN — unchanged** | `integration-pipeline.md` L178 still *"**Wait for CI to conclude** (`gh pr checks {PR}` shows no `pending`/`in_progress`)"* — round-1 defect 1 verbatim, with no merge-state escape — while L170 forbids `Skill(skill="ci-review")`. Two rounds of fixes remain unreachable on the orchestrate path. `we/quality/dod.md` L124-128 is still a third severity scale. |
| **R1-16** | Phases end in prose, not checkable criteria | **STILL OPEN** | Only 3e L234-237 carries `- [ ]` items. |
| **R1-17** | Frontmatter triggers are synonyms of one branch | **STILL OPEN** | L7 unchanged; `--ci-only`, the only real branch, still has no trigger phrase. |

---

## New defects

### 1. The stop-and-ask now lands *before* the only collection step, so the run delivers nothing. **MAJOR**

> L87: *"apply 3f's one-head check if the branch carries migrations, push"* · L243-245: *"say so
> and ask rather than patching around it."*

The fix for round-2 MAJOR 1 moved the head check from 3f (post-collection) to 1a
(pre-collection). Safety improved; delivery regressed. In round 2 the same scenario ended with
the `maintainer` thread surfaced, the `SEV:WARNING` triaged and fixed, and a findings table. Here the
run ends before 1b, and the user gets a question with **no findings attached** — even though every
one of them was readable in three `gh` calls that need no merge, no push and no CI.

**Smallest fix (recovers both):** in 1a, after the one-head instruction — *"If the check stops the
run, still run 1b and report its findings alongside the question."*

### 2. "Apply 3f's one-head check" does not say how much of 3f it imports. **MAJOR**

3f is a check (L241-242) plus a failure branch (L243-245). Importing only the check leaves an
agent that observes two heads with no instruction at the one moment it matters — and the default
continuation is L87's next word, `push`, which ships the base's second head onto the branch:
round-2 MAJOR 1, reintroduced through the wording of its own fix. The two readings differ by
whether the run stops or pushes.

**Smallest fix:** *"apply 3f in full — the check **and** its stop-and-ask branch — if the branch
carries migrations."*

### 3. Nothing says what to do with the hand-resolved merge while the run is blocked. **MINOR**

The run stops holding a worktree that contains the base's second alembic head plus hand-resolved
conflicts — precisely the state 3f exists to keep off the remote. Keep it (and risk a later
absent-minded push), commit it locally, or `git merge --abort` and redo it after the user acts?
The skill is silent, and the choice is not obvious: aborting throws away real conflict-resolution
work, keeping it leaves a loaded gun in the worktree.

**Smallest fix:** in 1a — *"When the one-head check stops the run, commit the resolved merge
locally and push nothing; say in the report that the branch holds an unpushed merge."*

### 4. The `--required` read sits outside the collection that feeds the findings table. **MINOR**

the host repo's CI rules L8-9 names the required set as `CI Summary`, `claude-review`, `codex-review`, and
*"an absent check is not a passing check"*. Scenario B's five rows contain no `CI Summary`. L20 is
an imperative — *"read it with `gh pr checks $PR --required`, never from memory"* — so an agent
following it would see the absence. But L20 lives in the gate's *definition* section, not in 1b's
numbered source list (whose only check command, L97, is the bare `gh pr checks $PR`), and 1d's
table (L142) has no row type for "required check absent from the output". The read therefore
happens outside the collection that produces the table the gate is judged against, and the
absence has nowhere to land. (If the sim's check names are just naming drift, the structural gap
stands regardless.)

**Smallest fix:** move the `--required` read into 1b as source 0, and add to the gate — *"a
required check absent from the output is red."*

### 5. L147's allowlist pointer now points forward, past the definition. **INFO**

> L147: *"or matches `$REVIEW_ALLOWLIST` (see 3d)"*

The definition is L77 (1a); 3d only re-derives it. The pointer sends a reader 60 lines the wrong
way. **Smallest fix:** `(defined in 1a)`.

### 6. The merge-over-rebase caveat now has two owners. **INFO**

L86-87 (*"not rebase — a rebase of pushed commits needs a force-push, which is the user's call"*)
and L242-243 (*"**Prefer merge over rebase** — a rebase of pushed commits forces
`--force-with-lease`, which is a user decision"*) say the same thing twice. Single-owner
(`plugin-authoring.md` L12-20) wants one. **Smallest fix:** keep 3f's, cite it from 1a.

---

## What I needed and did not find

Strictly mechanics a fresh Opus 5 would **not** supply unprompted, because the text points
elsewhere or is silent:

1. **How much of 3f the phrase "3f's one-head check" imports** (New defect 2). Stop or push —
   the two readings produce opposite runs, and nothing in the text breaks the tie.
2. **What to do with the resolved merge while blocked** (New defect 3). Keep / commit / abort are
   all defensible; the wrong choice is only visible later.
3. **Whether to wait for the answer on a human thread** (L154-155 vs L229) — unresolved for the
   third round.
4. **Which Claude signal wins when the check row is green and the comment carries
   `VERDICT:WARNING`** — L22-23 still frames the check conclusion as authoritative, and the repo
   rule covers only the inverse case.
5. **Whether 1a's push is exempt from L15's "Push once"** — reduced to a wording tension by the
   unconditional order at L87, but still unstated.
6. **A precedence line for `.claude/rules/`** — the skill and the host repo's CI rules agree by luck
   again; the next divergence still has no tie-breaker.

Deliberately excluded, because I would do them without being told: resolving merge conflicts,
reading a file before editing it, one commit not five, `git log -1` after committing, not
resolving a human thread — **and collecting the findings anyway before honouring the 1a stop**.
That last one is a defect in the text (New defect 1), not something I needed told; a competent run
probably collects regardless, which is why the defect is MAJOR-on-text and mitigated in practice.

---

## What could still be cut

~20 lines, all previously flagged and all still present, plus two new duplications:

- **L13** — *"Collects findings from CI + reviews, fixes them, and pushes once everything is
  addressed."* Restates the frontmatter and L15. Cut. (Flagged in rounds 1 and 2.)
- **L22-23 / L121-122 / L172** — "a red check with no comment is still a finding", three times.
  Keep 1c's (L121-122); cite it from the other two. Making L22-23 bidirectional while you are
  there also closes R1-13.
- **L179** — *"⛔ **ONE continuous flow, in order. Do NOT jump to `git push`.**"* The steps are
  numbered and 3g states its own preconditions. A no-op under `plugin-authoring.md` L68-70;
  flagged twice, survived twice.
- **L55-58 vs L261-263** — "One pass by default" and Phase 4's preamble still restate each other
  clause for clause. Keep L55-58; reduce the Phase 4 preamble to *"Enter only under the
  single-pass exceptions above."*
- **L92-93** (*"Do not special-case a reviewer by name"*) and **L148-149** (*"never from the
  reviewer's name"*) — one statement suffices.
- **L190-191** — *"The full suite and the coverage gate run in CI."* Rationale, not behaviour.
- **NEW: L86-87 vs L242-243** — the merge-over-rebase caveat, now twice (New defect 6).
- **NEW: L20's `--required` sentence** — prose owning a command no numbered step runs. Either
  promote it into 1b (New defect 4) or cut it; as it stands it describes a gate the run never
  builds.

The reclaimed space covers New defects 1-3, which are one clause each.

---

## Grade

**3.5/5.**

Earned: two round-2 MAJORs are genuinely closed — the head check now runs *before* the unblocking
push (L87) and the re-collect after it is ordered explicitly (L88, verbatim the fix round 2 asked
for). The rebase ambiguity that survived round 1 is closed at both ends (L85-86 / L242-243), and
`$REVIEW_ALLOWLIST` is finally defined before it is used (L77). The run terminates in four tool
calls with zero blind waiting, honours the host repo's CI rules L75-76 exactly, and never force-pushes.

Withheld: the fix for round-2 MAJOR 1 introduced a new MAJOR by moving the stop ahead of the only
collection step, so scenario B's run now delivers a question with no findings — strictly less than
round 2 delivered. The import phrasing at L87 leaves the stop-or-push decision to the reader, and
terminal state 4 is still absent, so Phase 5 has no shape for the state this run actually ends in.
Correct and efficient; not yet free of guessing.
