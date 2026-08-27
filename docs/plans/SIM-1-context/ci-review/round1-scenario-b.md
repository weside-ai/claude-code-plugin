# SIM-1 · ci-review · Round 1 · Scenario B

Table-top run of `we/skills/ci-review/SKILL.md` (335 lines) as the main agent, invoked as
`/we:ci-review` in `the host repo` on `feat/TICKET-000-projection` / PR #3718.
Nothing was executed. Every tool call below is what the skill's text makes me issue.

**Outcome in one line: the run deadlocks in Phase 3f and never pushes.** The two `pending`
rows are pending because the PR is `CONFLICTING`, the skill's push gate is "wait until no
`pending`", the skill never once looks at mergeability, and it gives no timeout, no poll
interval and no escape hatch. Along the way 3e-bis would have told me to do the exact thing
`the host repo`'s own CI rule forbids.

---

## Trace

### Phase 1 — Collect

**Step 0 (skill L68-71):** "Resolve, and keep for the rest of this run: **`$GH_AVAILABLE`** …
**`$PR`** … **`$BASE_REF`** … and **`$REPO` / `$OWNER` / `$REPO_NAME`**".
No commands are given for any of the six, in a skill that otherwise spells out four-line
GraphQL queries verbatim. I improvise:

1. `Bash: gh auth status` → authenticated. `$GH_AVAILABLE=true`.
2. `Bash: gh pr view --json number,baseRefName,headRefName,url`
   → `$PR=3718`, `$BASE_REF=main`, branch `feat/TICKET-000-projection`.
3. `Bash: gh repo view --json nameWithOwner,owner,name`
   → `$REPO=the app repo`, `$OWNER=the host repo-ai`, `$REPO_NAME=the host repo`.

Note what I did **not** do: `gh pr view 3718 --json mergeable,mergeStateStatus`. The skill
never mentions `mergeable` or `mergeStateStatus` anywhere in 335 lines, and step 0 is an
explicit, closed list of what to resolve. A fresh agent has no reason to add a field the
skill's own enumeration omits. This omission is the whole scenario.

### 1a — Start with what's ready (skill L83-117)

1. `Bash: gh pr checks 3718`
```
core-required         pending   —
Backend (Test)        pending   —
claude-review         pass      5m
codex-review          pass      6m
CodeRabbit            pass      2m
```
No `fail` rows — but `claude-review` is **green against a `<!-- VERDICT:WARNING -->`**
(collected at step 7 below). The check row and the review comment disagree, and the skill
never tells me to reconcile them; `the host repo`'s the host repo's CI rules says `claude-review` blocks
on a WARNING verdict, so this green row is stale. See defect 13.
**1c's table (L134-139) has no row for the pending state either** — its
four rows are ImportError / flaky / coverage / lint, all *failures*. Skill decision: none;
1c does not apply. Fall through to 1b.

(Aside: `gh pr checks` exits non-zero while checks are pending. Inside the skill's `if …; fi`
block that is harmless, but no line says so.)

1. `Bash: gh api graphql … reviewThreads … select(.isResolved==false)` (skill L90-96)
   → two nodes:
   - `PRRT_kwAAA_coderabbit` · `coderabbitai[bot]` · "consider extracting this dict literal"
     · `src/backend/app/rooms/projection.py:88`
   - `PRRT_kwAAA_human` · `maintainer` · "warum projizierst du hier zweimal?"
     · `src/backend/app/rooms/projection.py:141`

2. `Bash: gh api repos/the app repo/pulls/3718/reviews --jq '…endswith("[bot]")…'`
   (skill L100-103) → CodeRabbit summary body, no new findings beyond the thread.

3. `Bash: gh api repos/the app repo/issues/3718/comments --paginate --jq '…'`
   (skill L111-113) → the `claude[bot]` "## Code Review" comment:
   one `<!-- SEV:WARNING -->` — "the new migration has no down_revision test" —
   and `<!-- VERDICT:WARNING -->`.

### 1b — "start now, but hold the push" (skill L119-128)

L121-123: *"**don't wait to START** — collect and fix findings from the reviews that are
already available … Begin triaging and fixing those immediately."* → proceed to Phase 2.

L126-128 is recorded and carried forward as the push gate:
> "**But gate the PUSH on the long CI concluding.** Before you push (Phase 3f), wait until
> `gh pr checks $PR` shows no `pending`/`in_progress` left"

At this point the skill has made a factual assumption it never checks: that the pending rows
*will* conclude. They have been pending 40 minutes and no job ever started.

### 1d — Findings table (skill L145-161)

| # | Source | Bot? | Severity | File:Line | Issue | Thread ID | Action |
|---|---|---|---|---|---|---|---|
| 1 | Claude | — (comment) | **WARNING** (`SEV:WARNING`) | `alembic/versions/20260826_add_projection.py` | migration has no down_revision test | — | must fix (L22) |
| 2 | CodeRabbit | yes | NITPICK | `…/projection.py:88` | extract dict literal | `PRRT_…coderabbit` | may skip w/ reason (L23) |
| 3 | maintainer | **no** | **unmarked** | `…/projection.py:141` | "warum projizierst du hier zweimal?" | `PRRT_…maintainer` | ??? |

Finding 3 is where the skill runs out of spec. L152-153 says only *"Human threads → mark
'needs user confirm', never auto-close."* L155-157 says severity is read *"from the
thread/body **text**"* — a German question carries no `Critical/Major/Minor/🔴/SEV:` marker,
so it maps to **no row of the severity table**. And L270 says human threads *"do not block
this gate"*. Net skill instruction: label it, don't resolve it, don't let it stop the push.
On a projection PR, "why do you project twice here?" is plausibly the bug report of the
PR — and the skill routes it to a footnote in Phase 5.

### Phase 2 — Triage (skill L165-170)

Not "0 findings", so no early STOP. Triage per L19-23:
finding 1 = WARNING = **MUST fix**; finding 2 = NITPICK = fix anyway (cheap, on-seam, and
L38-43 "Finish-first" pushes toward fixing); finding 3 = unclassifiable, carried to the report.

### Phase 3a — Batch fix (skill L178-181)

1. `Read: src/backend/alembic/versions/20260826_add_projection.py`
2. `Read: src/backend/tests/…/test_migrations.py` (locate the existing pattern)
3. `Edit`: add a `down_revision` chain assertion for the new revision.
4. `Edit: src/backend/app/rooms/projection.py` — extract the dict literal (finding 2).
No commit between fixes (L181).

### Phase 3b — Local validation (skill L183-196)

1. `Bash: ruff format … && ruff check --fix …` on the two touched files
2. `Bash: mypy` / repo type gate on the diff
3. `Bash: a test src/backend/tests/…/test_migrations.py` — the diff-covering suite (L191)
4. `Bash: ls scripts/check-*.sh` then run the matching gates (L195)

### Phase 3c — Commit (skill L198-206)

1. `Bash: git add src/backend/alembic/versions/20260826_add_projection.py src/backend/tests/.../test_migrations.py src/backend/app/rooms/projection.py`
2. `Bash: git commit -m "fix: address CI and review findings\n\n{TICKET}"`

**`{TICKET}` is never defined in the skill.** No line resolves it, no line says "derive it
from the branch name". Literal execution commits the string `{TICKET}`. I substitute
`TICKET-000` from the branch — competence, not instruction.

### Phase 3d — Resolve bot threads (skill L208-243)

1. `Bash: REVIEW_ALLOWLIST=$(jq -r '(.review.available // […]) | join("|")' .weside/config.json …)` (L226)
2. `Bash: gh api graphql … reviewThreads … | select(bot) | .id` → one id, the CodeRabbit thread.
3. `Bash: gh api graphql -f query="mutation…resolveReviewThread…" -f id="PRRT_…coderabbit"` → `isResolved: true`.

The human thread is correctly left alone (L212-213).

**This is irreversible-ish and it happens before the gate that can never clear.** The skill
resolves the reviewer's thread at 3d, and then hangs at 3f without ever pushing the fix. The
PR now reads "CodeRabbit thread resolved" with none of the fix on the remote.

### Phase 3e — Hard gate (skill L246-270)

1. `Bash: gh api graphql … | length` → `UNRESOLVED=0` → "All bot threads resolved."
Gate passes. Human thread listed for the report, per L270.

### Phase 3e-bis — Migration rebase (skill L272-278)

The branch adds `20260826_add_projection.py`, so this fires:
> L274-275: "rebase onto `origin/${BASE_REF}` BEFORE the final push and confirm
> `alembic heads` resolves to exactly **one** head."

1. `Bash: git fetch origin main`
2. `Bash: git rebase origin/main` → **CONFLICT**. The PR is `mergeable: CONFLICTING`.
    The skill says nothing about a conflicted rebase: no `--abort`, no conflict-resolution
    guidance, no acknowledgement that a rebase can fail at all. It is written as if the
    rebase always succeeds. Dead end #1 — I am mid-rebase with a dirty index and a skill
    whose next sentence is about `alembic heads`.

Suppose I hand-resolve (the skill did not tell me to; I would):
1. `Bash: cd src/backend && alembic heads` → **two heads** (main gained a second).
    The skill's fix, L277-278:
    > "If a second head appears, merge it (a `down_revision = (head_a, head_b)` merge
    > migration) and re-run the check until `alembic heads` == 1."

    `the host repo`'s own the host repo's CI rules (in context, no `paths:` filter, so always loaded)
    says the opposite: *"Main can hold multiple Alembic heads while every PR is green. The fix
    is one merge-heads migration on main, **never a per-branch patch**."* The skill orders the
    per-branch patch by name. Dead end #2 — the skill and the repo rule contradict, and the
    skill never states a precedence.

2. Even if I write the merge migration, the rebase has rewritten published history:
    `git push` (L288) is rejected non-fast-forward, and `--force-with-lease` needs explicit
    user instruction per `git-workflow.md` (*"Require explicit user instruction before: …
    force-pushing"*). The skill's Phase 3f contains one bare `git push` and no word about
    force. Dead end #3.

### Phase 3f — Push (skill L280-289)

> L282-283: "Push only after: (a) the long CI has a conclusion — `gh pr checks $PR` shows no
> `pending`/`in_progress` (per 1b)"

1. `Bash: gh pr checks 3718` → still two `pending`.
2. `Bash: gh pr checks 3718` → still two `pending`.
3. `Bash: gh pr checks 3718` → still two `pending`.
… and so on.

**How long I would have waited, and on whose instruction.** The skill supplies:
no poll interval, no maximum wait, no staleness heuristic, no "if a check has not started
within N minutes, investigate", and no alternative exit from condition (a). Its only number,
*"max 2 total cycles"* (L302, L307), governs the **post-push** loop and cannot fire before a
push exists. Followed literally, condition (a) is unsatisfiable and the loop is unbounded —
the run does not terminate. And **the skill gives me nothing to do while waiting**: L121-123's
"start fixing early" work is finished at 3e, 3e-bis is done, so I idle on a poll the skill
never bounds. In practice I would break out after ~3-5 polls / 10-15 minutes on my own
judgement, run `gh pr view 3718 --json mergeable,mergeStateStatus`, get
`CONFLICTING/DIRTY`, and recognise the the host repo's CI rules known state. **That diagnosis is
mine, not the skill's** — the skill's text at that moment is still ordering me to wait.

### Phase 4 / Phase 5

Phase 4 (L293-309) is unreachable: it is entered "after pushing". Worth noting that its own
opt-in list (L49) names *"migration"* as a high-stakes reason to loop — so for exactly the PR
class 3e-bis exists for, L45's "Default to a single pass" is already overridden.

Phase 5 (L313-320) asks for "Push status" and "CI status (pass/pending/fail)" — the only two
lines in the whole skill that would surface the truth ("not pushed", "pending 40 min"), and
they arrive after the run has already failed to terminate. Note also that "CI status
(pass/pending/fail)" is asked for as the **check rows**, which in this scenario report
`claude-review pass` while the verdict marker says WARNING — Phase 5 would report a
green-looking CI state that the repo's gate rule contradicts (defect 13).

---

## Conformance checklist

- [x] **Phase 1 step 0 (L68-71)** — names the six variables; unambiguous *what*, silent on
      *how*. Opus resolves them anyway. Pass, barely.
- [ ] **1a (L76-117)** — four copy-pasteable collection calls, the clearest part of the skill,
      but it collects the `claude-review` check row and the `VERDICT:` marker without ever
      comparing them; here they disagree and the skill has no tie-breaker (defect 13).
- [ ] **1b (L119-128)** — tells me to hold the push on "no pending". Gives no interval, no
      cap, no failure mode for a check that never starts. Deadlock. **Unambiguous and wrong.**
- [ ] **1c (L130-141)** — the failure table has no row for "pending forever / job never
      started", the single most common non-failure CI blocker in this repo.
- [ ] **1d (L143-161)** — human thread has no severity path, no fix/skip verdict, and
      references `$REVIEW_ALLOWLIST` 74 lines before L226 defines it.
- [x] **Phase 2 (L165-170)** — clear.
- [x] **3a (L178-181)** — clear (and content-free; see cuts).
- [x] **3b (L183-196)** — clear.
- [ ] **3c (L198-206)** — `{TICKET}` is an undefined placeholder in an executable snippet.
- [x] **3d (L208-243)** — clear and correct; the one genuinely load-bearing mechanic.
- [x] **3e (L246-270)** — clear, checkable, hard.
- [ ] **3e-bis (L272-278)** — assumes the rebase succeeds, contradicts the repo's alembic
      rule, and ignores that a rebase forces a force-push.
- [ ] **3f (L280-289)** — condition (a) is unsatisfiable in this scenario; `git push` is
      wrong after 3e-bis.
- [ ] **Phase 4 (L293-309)** — unreachable here, and default-off while 1d delegates all
      Claude `SEV:*` confirmation to it (defect 14).
- [ ] **Phase 5 (L313-320)** — clear list, not a checklist (defect 16), and its "CI status
      (pass/pending/fail)" line reports the stale green row (defect 13).
- [ ] **Cross-file** — the entire procedure has a second owner in
      `references/integration-pipeline.md` L168-190, carrying the same deadlock (defect 15).

---

## Skill defects

### 1. The push gate has no liveness condition — the run does not terminate. **BLOCKING**

> L126-128: "**But gate the PUSH on the long CI concluding.** Before you push (Phase 3f),
> wait until `gh pr checks $PR` shows no `pending`/`in_progress` left…"
> L282-283: "Push only after: (a) the long CI has a conclusion — `gh pr checks $PR` shows no
> `pending`/`in_progress` (per 1b)"

Concretely here: `core-required` and `Backend (Test)` are pending because the PR is
`CONFLICTING` — no merge commit, so no CI Core run was ever created. They will stay pending
until someone merges the base. The skill's exit condition is "not pending", which is never
reached, and the skill supplies no interval, no cap, and no branch for "a check that has not
started". Everything already done (fixes committed, CodeRabbit thread resolved) sits unpushed.

**Smallest fix:** two sentences in 1b —
"Bound the wait: poll at most 3 times over ~10 minutes. If a check is still `pending` with no
run, it usually never started — run `gh pr view $PR --json mergeable,mergeStateStatus`;
`CONFLICTING`/`DIRTY` means merge the base first, then re-collect. Report and stop rather than
polling indefinitely."

### 2. Mergeability is never read, anywhere. **BLOCKING**

`mergeable` / `mergeStateStatus` appear zero times in 335 lines. Every diagnosis in this
scenario hangs off one call the skill never makes. Worse, the shortcut at L166 —

> L166: "**0 findings → 'All green, ready for merge' → STOP.**"

— would, on a variant of this PR with no review findings, declare a `CONFLICTING`,
never-buildable PR "ready for merge".

**Smallest fix:** add `gh pr view $PR --json mergeable,mergeStateStatus` to the step-0
resolution list at L68-71 as `$MERGE_STATE`, and gate L166 on it.

### 3. 3e-bis orders the per-branch alembic patch the repo rule forbids. **BLOCKING**

> L277-278: "If a second head appears, merge it (a `down_revision = (head_a, head_b)` merge
> migration) and re-run the check until `alembic heads` == 1."

the host repo's CI rules file: *"Main can hold multiple Alembic heads
while every PR is green. The fix is one merge-heads migration on main, never a per-branch
patch."* Main has a second head right now, so following the skill produces exactly the
forbidden artifact — a merge migration on a feature branch that will collide with the next
branch that does the same. The skill also never states that repo rules outrank it.

**Smallest fix:** replace the parenthetical with "…a second head that comes from **main** is
fixed by one merge-heads migration **on main**, not on this branch — stop and tell the user.
Only a head your own branch created is yours to merge." Plus one line at the top of the skill:
"Repo rules in `.claude/rules/` outrank this skill where they conflict."

### 4. 3e-bis assumes a rebase that cannot succeed, and hides a force-push. **BLOCKING**

> L274: "rebase onto `origin/${BASE_REF}` BEFORE the final push"
> L288: "```bash\ngit push\n```"

The branch is `CONFLICTING`: `git rebase origin/main` stops with conflicts. The skill has no
`--abort`, no conflict path, no acknowledgement that step 23 can fail — it goes straight to
`alembic heads`. And a successful rebase rewrites pushed history, so L288's bare `git push` is
rejected non-fast-forward; the required `--force-with-lease` needs explicit user instruction
under `git-workflow.md`, which the skill never mentions.

**Smallest fix:** in 3e-bis — "If the rebase conflicts, `git rebase --abort` and report: the
PR needs a base merge before this skill can finish. A completed rebase requires
`git push --force-with-lease`, which needs the user's explicit go — ask before pushing."

### 5. A human review thread has no severity, no verdict, and does not block. **MAJOR**

> L152-153: "Human threads → mark 'needs user confirm', never auto-close."
> L155-157: "**Severity** = read from the thread/body **text** (markers like Critical/Major/
> Minor/Nitpick or 🔴/🟡/🟢 / `VERDICT:`/`SEV:`)"
> L270: "Human-authored threads do not block this gate — list them in the report instead."

`maintainer`'s "warum projizierst du hier zweimal?" carries no marker, so it maps to no row of the
L19-23 policy table. The skill tells me to label it and push past it. On a
rooms-**projection** PR, a human asking why you project twice is the highest-value finding on
the board and the only one the skill has no policy for.

**Smallest fix:** one row in the policy table — "**Human thread, unmarked**: treat as
BLOCKING for the push until answered — fix it, or reply in the thread and get the user's go.
Never auto-resolve." (The no-auto-resolve rule stays; only the *gating* changes.)

### 6. 3d resolves threads before a push gate that can fail. **MAJOR**

3d (L208-243, ordered before 3e-bis and 3f) resolves the CodeRabbit thread. In this scenario
the run then never pushes. The PR is left with a reviewer thread marked resolved and no fix on
the remote — a state that reads, to the reviewer and to the next agent, as "handled".

**Smallest fix:** move 3d after the push, or add to 3d: "Resolve only when the push is
expected to happen in this run; if a later gate (3e-bis, 3f) blocks, say so in the report so
the resolved-but-unpushed state is visible."

### 7. Rules block retells the steps — plugin-authoring violation. **MAJOR**

plugin-authoring L26-29: *"**Rules blocks don't retell steps.** A `## Rules` section at the
end of a skill contains ONLY invariants that are not already stated in the steps. A Rules
block that paraphrases the steps is the start of drift: two places, one behavior, and only one
gets updated."*

L324-335 is five bullets, four of which are verbatim paraphrase:
- L328-329 "Fix everything, push once…" = L15 + L282-284
- L330 "Never auto-resolve a human-authored thread" = L31 + L212-213 + L270
- L331-332 "Claude Code Review is a comment, not threads" = L105-110 + L158-161 + L216-220
  (this fact is now stated **four** times)
- L333-334 "One pass by default, max 2 cycles" = L45-52 + L293-298 + L307

**Smallest fix:** delete L326-334; keep only L335 (`--ci-only`).

### 8. `--ci-only` exists only in the Rules block and is never handled. **MAJOR**

> L335: "**`--ci-only` flag** — skip reviews, only check CI status."

No phase mentions it. Phase 1a has no branch for it, Phase 3d/3e (the thread gates) have no
opt-out, Phase 5 has no reduced report. Also a single-owner violation: the flag's only
definition lives in the section plugin-authoring says must contain *no* new procedure.

**Smallest fix:** move it to a `## Flags` line right under Phase 1's intro and add the one
branch it implies — "`--ci-only`: run 1a step 1 only, skip 1a steps 2-4, skip 3d/3e."

### 9. Duplicated ownership of the severity policy and the Claude-comment fact. **MAJOR**

plugin-authoring L13-15: *"Every rule, procedure, schema, or template is defined in **exactly
one file**… Every other place cites it with one sentence + path."*

Within this one file, the severity policy is stated at L19-23 (table), restated as prose at
L28-31, again as skip-criteria at L33-36, again at L169-170, again at L326-334. The
"Claude review is a comment, nothing to resolve" fact appears at L105-110, L158-161, L216-220
and L331-332. The `REVIEW_ALLOWLIST` default `greptile|coderabbit|claude` is hard-coded twice
(L152 and L226) — L249 even has to warn *"do NOT redefine it with a different default"*, which
is the drift the rule predicts, already visible in the file.

**Smallest fix:** keep the L19-23 table; cut L28-31 and L169-170 to one citation each; state
the Claude-comment fact once (in 1d) and cite it elsewhere; define the allowlist once, in 1d,
and have 3d/3e reuse it.

### 10. `$REVIEW_ALLOWLIST` is used at L152 and defined at L226. **MINOR**

Phase 1d's Bot? column depends on a variable Phase 3d sets 74 lines later. A literal reading
of 1d has an empty allowlist; only the `[bot]` suffix saves this scenario (CodeRabbit carries
it). A bot without the suffix would be misfiled as human in the findings table and then
correctly resolved at 3d — the table and the action disagree.

**Smallest fix:** move the `REVIEW_ALLOWLIST=$(jq …)` line from L226 into the 1a bash block.

### 11. `{TICKET}` is an undefined placeholder in an executable snippet. **MINOR**

> L203-205: `git commit -m "fix: address CI and review findings\n\n{TICKET}"`

Nothing in the skill resolves it. Literal execution commits the braces.

**Smallest fix:** `{TICKET}` → "the ticket key from the branch name (`feat/TICKET-000-…` →
`TICKET-000`); omit the line if the branch carries none."

### 12. 1c's failure table has no row for the repo's most common CI blocker. **MINOR**

L134-139 covers ImportError, flaky, coverage, lint. It has no row for "check pending, job
never started" and none for "multiple alembic heads on main" — both documented known states in
the host repo's CI rules file, and the first one is this entire scenario.

**Smallest fix:** two rows.

### 13. The skill's only proof for Claude-comment findings is falsified before the run starts. **MAJOR**

> L218-220: "after you push the fixes, the Claude review re-runs and posts a delta with
> `✅ Fixed` and `VERDICT:PASS`; **the CI gate fails on `VERDICT:BLOCKING`/`VERDICT:WARNING`,
> so a green gate after push is the proof.**"
> L159-161: it "is **not** subject to the 3e thread gate — it is confirmed by the re-review
> after push"

Concretely here: `gh pr checks 3718` shows `claude-review  pass  5m` while that same run's
comment carries `<!-- VERDICT:WARNING -->`. The skill's stated invariant — WARNING verdict ⇒
red gate — is **already false in the collected data**, and the skill's Phase 1 never compares
the two. So the check row cannot serve as proof for finding #1 either before or after the
push, and the skill offers no other verification for its own highest-severity finding.
`the host repo`'s the host repo's CI rules is explicit that `claude-review` blocks on a "BLOCKING /
WARNING verdict in its summary comment" and that a mismatched row is "the gate, not the
review" — the skill never says the marker outranks the row.

**Smallest fix:** one sentence in 1d — "Read the verdict from the `<!-- VERDICT:* -->` marker
in the comment, never from the `claude-review` check row. If they disagree, the marker wins
and the row is stale; say so in the report."

### 14. The confirmation path for MUST-fix Claude findings is default-disabled. **MAJOR**

> L159-161: Claude findings are "confirmed by the re-review after push (3d note / **Phase 4**)"
> L293-295: "**By default, stop after the first push and report (Phase 5).** Enter this loop
> **only** when one of the single-pass exceptions applies"

1d delegates verification of every `SEV:*` finding to Phase 4; Phase 4 is opt-in and off by
default. So in the default path a Claude `SEV:WARNING` — which L22 says **MUST** be fixed — is
verified by nothing at all. This contradiction is internal to the skill and independent of the
scenario; here it lands on finding #1, the migration's missing `down_revision` test.

**Smallest fix:** add "an unconfirmed Claude `SEV:BLOCKING`/`SEV:WARNING` finding" to Phase 4's
opt-in list at L48-50.

### 15. The whole procedure has a second owner in `references/integration-pipeline.md`. **MAJOR**

plugin-authoring L13-15: *"Every rule, procedure, schema, or template is defined in **exactly
one file** … Every other place cites it with one sentence + path (`see references/x.md`)."*

`we/references/integration-pipeline.md` L168-190 re-implements this skill as eight numbered
steps — collect early, triage BLOCKING/WARNING/SUGGESTION, wait for CI, one commit, resolve
bot threads, verify zero, push once, one pass then stop — and L170-171 instructs the Lead
**"Never `Skill(skill=\"ci-review\")`"**, so on the orchestrate path this skill is by design
never the executed artifact. Two owners, one behaviour. The exception at plugin-authoring
L22-24 (self-contained briefs sent verbatim to a context-less process) does not apply: this
block is read by the Lead inside plugin context.

The drift is already load-bearing for this scenario: integration-pipeline L172-173 —
*"**Wait for CI to conclude** (`gh pr checks {PR}` shows no `pending`/`in_progress`)"* —
carries **defect 1's unbounded deadlock verbatim**. Fixing 1b alone leaves the Lead path
hanging on the identical conflict.

`we/quality/dod.md` L124-128 is a third statement of the severity scale
(`BLOCKING`/`WARNING`/`INFO/NITPICK` → action), against the SKILL's L19-23 table.

**Smallest fix:** cut integration-pipeline L172-190 to "run the ci-review procedure inline —
`we/skills/ci-review/SKILL.md` Phases 1-3; do not `Skill()`-load it"; have dod.md cite the
SKILL table instead of restating it.

### 16. Phases end in prose, not checkable completion criteria. **MINOR**

plugin-authoring L71-73: *"**Completion criteria are checkable.** A phase ends with `- [ ]`
items the agent can verify (can it tell done from not-done?), not with prose."*

Only 3e (L246-267) has a real pass/fail gate. Phases 1, 2, 3a, 3b, 4 and 5 end in prose;
Phase 5 (L315-320) is a list of report *contents*, not `- [ ]` items.

### 17. Frontmatter triggers are synonyms of one branch. **MINOR**

plugin-authoring L60-61: *"**One trigger per branch.** Each quoted phrase must reach a
distinct branch of the skill. Synonyms that rename a single branch are duplication — cut
them."*

L7: `"/we:ci-review", "fix ci", "fix reviews", "ci failed"`. "fix ci" and "ci failed" reach
the same branch (there are no branches — `--ci-only` is unimplemented, defect 8).
Size itself is fine: the description block is 301 bytes, under the ≤400 budget (L54-56).

**Smallest fix:** cut `"ci failed"`.

---

## What I needed and did not find

Strict list — things a fresh Opus following this skill would **not** do on its own, because
the skill's own text points the other way:

1. **`gh pr view $PR --json mergeable,mergeStateStatus`.** Step 0 (L68-71) is a closed
   enumeration of state to resolve, and 1b frames the pending rows as "the long CI" that is
   merely slow. Nothing in the skill suggests the checks might not be *running at all*. This
   is the single missing call.
2. **A bound on the pre-push wait.** No interval, no cap, no "if still pending after N,
   investigate". The skill's only number governs the post-push loop.
3. **What a conflicted rebase means in 3e-bis** — abort, or resolve, or stop and report.
4. **The force-push consequence of 3e-bis**, and permission for it. 3f's bare `git push` is
   actively misleading after a rebase.
5. **Whether a second alembic head belongs to main or to my branch**, and which one I am
   allowed to merge. The skill says "merge it" unconditionally; the repo rule says the
   opposite for the main case.
6. **A verdict route for an unmarked human finding** — fix / answer / block / defer.
7. **`{TICKET}` resolution** and **`--ci-only` semantics** — both referenced, neither defined.
8. **Which of the two Claude signals wins.** The skill collects the `claude-review` check row
   (1a step 1) and the `VERDICT:` marker (1a step 4) and never says they can disagree, while
   asserting at L218-220 that a WARNING verdict implies a red gate. With that assertion in
   front of me I have no prompt to distrust a `pass` row.

Deliberately excluded (I would do these unprompted, so they are not gaps): reading files
before editing; running lint/types/affected tests; one commit not five; not resolving a human
thread; checking `git log -1` after commit.

---

## What could be cut

- **L324-334** — the Rules block minus `--ci-only`. Eleven lines of pure step paraphrase, and
  a direct plugin-authoring violation (defect 7).
- **L293-298** — Phase 4's opt-in preamble restates L45-52 nearly sentence for sentence. Keep
  L45-52, replace L293-298 with "Enter only under the single-pass exceptions above."
- **L216-220** — the blockquote repeats L105-110 and L158-161. Third statement of one fact.
- **L269-270** — "⛔ If UNRESOLVED > 0: STOP. Go back to 3d." The bash at L261-264 already
  echoes `⛔ BLOCKED` and `exit 1`. The prose adds nothing the exit code does not.
- **L28-31 and L169-170** — prose restatements of the L19-23 table.
- **L180 "Read each finding, open file, make fix"** — a no-op under plugin-authoring L68-70
  ("A line the model already obeys by default … pays context load to say nothing").
- **L176** — "⛔ This is ONE continuous flow. Execute every step in order. Do NOT jump to
  `git push`." Phase headings are already numbered 3a-3f.
- **L13** second clause, "so the user can observe every step" — rationale, not behaviour.

Roughly 35 of 335 lines are removable without losing a single instruction — and the space
would more than cover the seven missing mechanics above.

---

## Grade

**2/5.** The collection queries (1a) and the thread-resolution gate (3d/3e) are genuinely good
— reviewer-agnostic, copy-pasteable, and they close the failure mode they were written for —
but this scenario walks straight into a push gate with no liveness condition, a migration step
that contradicts the repo's own alembic rule and silently requires a force-push, a green
`claude-review` row the skill's own L218-220 invariant says cannot exist, and no policy at all
for the one human finding on the PR; a fresh agent following the text terminates only by
disobeying it.
