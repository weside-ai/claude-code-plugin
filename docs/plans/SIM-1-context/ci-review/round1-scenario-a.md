# SIM-1 · `/we:ci-review` · Round 1 · Scenario A

Table-top simulation. Nothing was executed. Skill under test:
`<worktree>/we/skills/ci-review/SKILL.md` (335 lines).
Authoring contract: `<worktree>/.claude/rules/plugin-authoring.md`.

Scenario: PR #3721 on `feat/TICKET-000-ledger`, base `main`. `codex-review` — a **required**
check per the host repo's CI rules — is red after 1 min. It posted no comment. Its finding, if any, exists
only in run 9911's log, which ends in `remote: HTTP 429 too many requests` during
`actions/checkout`, then `VERDICT:ERROR`. Everything else is green; zero unresolved threads;
`claude[bot]` posted `<!-- VERDICT:PASS -->` with no SEV findings.

## Trace

**User:** "codex ist rot, mach mal /we:ci-review". No `--ci-only` typed, though line 335 says a flag
for exactly this complaint exists (see defect 4).

### Phase 1 — Collect

**Step 1 (skill lines 68-71).** "Resolve, and keep for the rest of this run: `$GH_AVAILABLE` … `$PR`
… `$BASE_REF` … and `$REPO` / `$OWNER` / `$REPO_NAME`". The skill names six variables and gives no
command for any of them. I would issue what it does not specify:

- `Bash: gh auth status` → authenticated ⇒ `$GH_AVAILABLE=true`
- `Bash: gh pr view --json number,baseRefName,headRepository,headRepositoryOwner` → `$PR=3721`,
  `$BASE_REF=main`, `$OWNER=the host repo-ai`, `$REPO_NAME=the host repo`, `$REPO=the app repo`

Recorded as defect 8: the bash blocks below are written as copy-executable and interpolate these
variables, so a literal follower runs `-F owner=` empty and takes a GraphQL error on the first real
call.

**Step 1a, source 1 (line 86).** `Bash: gh pr checks 3721`

```
CI Summary      pass  2m
Backend (Test)  pass  14m
Frontend (Lint) pass  3m
claude-review   pass  4m
codex-review    fail  1m  https://github.example/actions/runs/9911
```

The skill tells me nothing to *do* with this beyond 1b (are any `pending`? — no) and 1c (a table of
four CI error classes, none of which is "red check that posted nothing"). The run URL is handed to
me and no line of the skill consumes it (defect 2).

**Step 1a, source 2 (lines 90-96).** `Bash: gh api graphql -f query='…reviewThreads(first:100)…'
-F pr=3721 -F owner=the host repo-ai -F repo=the host repo --jq '…select(.isResolved==false)'`
→ **empty**. The one coderabbit thread is resolved. Per line 88 ("Each open thread is a finding"),
zero findings from the PRIMARY source.

**Step 1a, source 3 (lines 100-103).** `Bash: gh api repos/the app repo/pulls/3721/reviews
--jq 'group_by(.user.login)[] | last | select(.user.login | endswith("[bot]")) | …'`
→ `=== coderabbitai[bot] ===\nActionable comments posted: 0`. Zero findings.

**Step 1a, source 4 (lines 111-113).** `Bash: gh api repos/the app repo/issues/3721/comments
--paginate --jq '[…test("claude";"i") … test("## Code Review")] | sort_by(.created_at) | last | .body'`
→ the `## Code Review` body ending in `<!-- VERDICT:PASS -->`, containing **no** `<!-- SEV:* -->`
markers. Per line 158 I split it "into one row per `<!-- SEV:* -->` finding" — there are none. Zero
rows.

**Step 1b (lines 119-128).** Nothing is `pending`/`in_progress`. The push gate of this section is
therefore already satisfied — while a required check is red. See defect 3.

**Step 1c (lines 130-141).** "**Pre-existing CI failures that block your PR are YOUR problem.**"
Then a four-row table: ImportError, flaky test, coverage, lint/type error. `codex-review` failing
during `actions/checkout` with HTTP 429 matches none of them. Line 141: "Only skip a CI failure if
it's truly unfixable from this branch (e.g., infrastructure issue). Document why." This is the
closest the skill comes to my scenario — but I cannot yet *know* it is an infrastructure issue,
because nothing in Phase 1 has told me to open run 9911. The skill offers a disposition whose
precondition it never instructs me to establish.

**Step 1d (lines 143-161).** Build the findings table. Two readings diverge here, and the skill does
not adjudicate between them:

- **Reading A (minimal, literal).** Sources 2, 3 and 4 each produced zero rows. The table is empty.
- **Reading B (careful).** Line 149 lists "CI" as a legal **Source**, and the severity table line 21
  makes "CI failure" **BLOCKING / MUST fix**. So `codex-review` is one row:
  `| 1 | CI (codex-review) | — | BLOCKING | — | ??? | — | ??? |`. The Issue cell is unfillable: the
  skill has given me no step that obtains it, and Bot?/Severity are defined only as functions of
  `author.login` and body text, neither of which exists for a check that posted nothing.

Line 152 also uses `$REVIEW_ALLOWLIST` here, which is first defined 74 lines later at line 226
(defect 9).

### Phase 2 — Triage

Line 167: "**0 findings → 'All green, ready for merge' → STOP.**"

- **Reading A terminates here** and reports *All green, ready for merge* on a PR with a red required
  check. Catastrophic and silent — the user asked about exactly the check this sentence dismisses.
- **Reading B deadlocks here.** Line 169 says to triage "every finding per the **Severity policy**
  table above". My one finding is BLOCKING and MUST be fixed; line 21's only escape is "the reviewer
  is demonstrably factually wrong (cite evidence)". I hold no evidence and no reviewer text. Phase 3
  starts with "Read each finding, open file, make fix" (line 179) and I have no file. I stop, not
  because the skill said to, but because it ran out of instructions (defect 5).

I record Reading A as the outcome a fresh agent following the skill literally reaches, because the
skill's own terminal condition is phrased on finding-count, not on check colour.

### Phase 3 — Fix → Validate → Resolve → Push (traced for Reading B / the agent who did not stop)

- **3a (178-181).** No findings with a file. No-op.
- **3b (183-196).** "validate locally over the **changed surface only**". The diff is empty — the
  skill has no branch for "nothing changed", so a literal follower runs lint/tsc/pytest over an empty
  changed surface. Wasted minutes, no guard.
- **3c (198-206).** "ONE commit with all fixes" plus a literal `git commit -m "fix: address CI and
  review findings"`. With zero fixes staged this is an empty commit or a `nothing to commit` abort.
  Unguarded (defect 6).
- **3d (208-244).** `REVIEW_ALLOWLIST=$(jq -r … .weside/config.json …)`, then the thread query →
  `THREADS` empty → the `for` loop body never runs. Correct by accident.
- **3e (246-267).** Same query, `| length` → `UNRESOLVED=0` → prints "All bot threads resolved."
  **The hard gate passes.**
- **3e-bis (271-278).** Branch is `TICKET-000-ledger` — plausibly a migration branch; the skill
  gives no test for "adds an Alembic migration", so I would check `git diff --name-only
  origin/main...HEAD -- apps/backend/alembic/` myself. Out of scenario scope.
- **3f (280-289).** The push conditions: "(a) … `gh pr checks $PR` shows no `pending`/`in_progress`"
  — **true**; "(b) 3e confirms 0 unresolved bot threads" — **true**; (c) n/a. **Every stated push
  condition is satisfied while `codex-review` is red.** The skill then says `git push`. In this
  scenario the push is a no-op (nothing committed), but the *gate* has certified a red required check
  as pushable, which is the defect (defect 3). Frontmatter line 6 promises "pushes only when nothing
  blocking remains"; 3f never checks that.

### Phase 4 — Post-Push Check

Lines 293-298: opt-in. Line 296 lists "flaky/env-dependent check" as a qualifying reason — which is
what an HTTP 429 is, but I only learn that by reading a log the skill never opened. And line 300
frames the whole loop as "after pushing CI + reviews re-run": the loop's trigger is a push. With no
commit to push, there is **no path in this skill to re-run a check** (`gh run rerun 9911 --failed`
appears nowhere). Defect 7.

### Phase 5 — Report

Lines 315-320 want "CI status (pass/pending/fail)" alongside Phase 2's verdict. Reading A therefore
produces a report that says **All green, ready for merge** and **CI status: fail** in the same
output. The skill contradicts itself inside one deliverable.

## Conformance checklist

- [ ] **Phase 1 setup (68-71)** — names six variables, specifies zero commands to derive them; the
      blocks that consume them are presented as executable.
- [x] **Phase 1a sources 2/3/4 (83-117)** — unambiguous, runnable, correct results in this scenario.
- [ ] **Phase 1a source 1 / CI (86)** — collects `gh pr checks` and defines no step that turns a red
      check into a table row; drops the run URL it was handed.
- [x] **Phase 1b (119-128)** — unambiguous (nothing pending), though its rule is the wrong axis.
- [ ] **Phase 1c (130-141)** — its error taxonomy has no row for this failure, and its one escape
      ("infrastructure issue") has a precondition no step establishes.
- [ ] **Phase 1d (143-161)** — leaves it undecided whether a red check is a row; uses
      `$REVIEW_ALLOWLIST` before defining it.
- [ ] **Phase 2 (165-170)** — the 0-findings terminal state is reachable with a red required check,
      and the skill states it as an unconditional STOP.
- [ ] **Phase 3a-3c (174-206)** — no branch for "no findings / empty diff"; prescribes a commit
      regardless.
- [x] **Phase 3d/3e (208-269)** — unambiguous and correct; the gate does what it claims.
- [x] **Phase 3e-bis (271-278)** — clear, though it leaves the "is this a migration branch" test to me.
- [ ] **Phase 3f (280-289)** — its push conditions certify a red required check as pushable.
- [ ] **Phase 4 (293-309)** — entry is gated on a push having happened; no re-run mechanic exists.
- [ ] **Phase 5 (313-320)** — permits a self-contradicting report; no `- [ ]` completion criteria.
- [ ] **`--ci-only` (335)** — declared in eight words in the Rules block, defined nowhere.

## Skill defects

### 1. A red required check with no comment produces zero findings and the skill declares victory — BLOCKING

> `167:` **0 findings → "All green, ready for merge" → STOP.**

Phase 1's four collection sources are: `gh pr checks` (status only, never converted to a row),
unresolved review threads (0), bot review bodies (`Actionable comments posted: 0`), and the Claude
issue comment (`VERDICT:PASS`, no SEV markers). Every one returns nothing. The findings table is
empty, and line 167 terminates the run with *All green, ready for merge* — on a PR whose required
`codex-review` is red, in response to a user who literally said "codex ist rot". The skill converts
the user's stated problem into a green light.

The repo rule the skill should encode says the opposite:
the host repo's CI rules file → "**Red review gate with NO comment on the PR →
read the run log** (`gh run view <id> --log-failed`): the review may have failed to POST and its
finding lives only there." The string `gh run view` does not occur in the 335 lines of this skill.

Note the direction of the failure: line 167 is worse than a missing instruction. A the host repo agent
already holds the run-log rule in context via the host repo's CI rules; line 167 hands it a sanctioned
terminal state that **overrides** what it would otherwise do.

**Smallest fix:** in 1a, after `gh pr checks $PR`, add: *every non-`pass` check is a BLOCKING row.
If it posted no comment (absent from sources 2-4), fetch its finding with
`gh run view <run-id> --log-failed` — the URL is in the `gh pr checks` output.* And re-phrase line 167
to `0 findings AND no non-passing check → …`.

### 2. `gh pr checks` hands over the run URL and no step consumes it — MAJOR

> `85:` `# 1) CI status`
> `86:` `gh pr checks $PR`

The output contains `https://github.example/actions/runs/9911` — the exact pointer
to the only place this scenario's failure is observable. The skill collects it and drops it. The
information needed to avoid defect 1 was already in hand.

**Smallest fix:** the same added line as defect 1 — name the URL column as the input to
`gh run view`.

### 3. The push gate measures lateness, not outcome — MAJOR

> `126-127:` **But gate the PUSH on the long CI concluding.** Before you push (Phase 3f), wait until
> `gh pr checks $PR` shows no `pending`/`in_progress` left…
> `282-283:` Push only after: (a) the long CI has a conclusion — `gh pr checks $PR` shows no
> `pending`/`in_progress` (per 1b) … (b) 3e confirms 0 unresolved bot threads

Both encodings of the CI push condition test *has it finished*, never *did it pass*. In this scenario
both are satisfied with a red required check, so 3f authorises `git push`. This is the root cause
behind 1b and 3f alike, and it directly falsifies two of the skill's own promises:

> `6:` all bot threads, pushes only when nothing blocking remains.
> `15:` **Core principle: Fix everything. Push once. No leftovers.**

**Smallest fix:** change (a) to *no check is `pending`/`in_progress` **and** every required check is
`pass`, or a red one is documented per 1c*.

### 4. `--ci-only`, the flag aimed at exactly this complaint, is undefined — MAJOR

> `335:` - **`--ci-only` flag** — skip reviews, only check CI status.

The user's request was a pure CI complaint, so `--ci-only` is the intended mode here. Eight words in
a Rules block are its entire specification: no phase mentions it, nothing says what "only check CI
status" means for Phases 2-5, and it is absent from the frontmatter triggers (3-7). Worse, under
`--ci-only` sources 2/3/4 are skipped, so collection reduces to `gh pr checks` alone — the one source
that has no rule for producing a finding. The flag built for this scenario makes the dead end of
defect 1 strictly worse: a guaranteed empty table into line 167.

This also breaches the authoring contract twice —

> plugin-authoring `26-27:` **Rules blocks don't retell steps.** A `## Rules` section at the end of
> a skill contains ONLY invariants that are not already stated in the steps.

— a flag definition is neither an invariant nor a step restatement; it is spec with no home, which is
the single-owner failure inverted:

> plugin-authoring `13-14:` Every rule, procedure, schema, or template is defined in **exactly one
> file** — a skill step…

**Smallest fix:** move it to a `## Flags` line under Phase 1 stating which sources it skips and that
Phases 3d/3e are skipped with it, or delete the flag.

### 5. The exception taxonomy is closed and this failure falls outside it — MAJOR

> `21:` … **MUST fix.** Only exception: the reviewer is demonstrably factually wrong (cite evidence).
> `33-36:` **Skip criteria (strict) — a finding may be skipped ONLY when:** the reviewer is
> **factually incorrect** (cite evidence); the suggestion would **break existing behavior**; or it's
> a **pre-existing pattern** that was 1:1 moved…

All three exceptions presuppose a *reviewer with an opinion*. An HTTP 429 during `actions/checkout`
is not a reviewer, has no opinion, and is not wrong. Under Reading B I hold a BLOCKING finding for
which the skill's own policy provides **no legal disposition** — I may not fix it (no code is at
fault), may not skip it (no criterion matches), and Phase 3 has no branch for it. The one adjacent
sentence, line 141 ("Only skip a CI failure if it's truly unfixable from this branch (e.g.,
infrastructure issue). Document why."), lives in 1c and is not referenced by the severity table, so
the two policies disagree about whether an infra failure is skippable.

the host repo's CI rules states the missing rule: "**Red `codex-review` is not always a finding.**
`VERDICT:WARNING` is real; `VERDICT:ERROR` or no verdict at all (e.g. `actions/checkout` HTTP 429) is
the runner — re-run."

**Smallest fix:** add a fourth skip criterion at line 36 — *the check failed in its own runner
(`VERDICT:ERROR`, no verdict, checkout/network error): not a finding, re-run it* — and cross-link
line 141 to it so one owner holds the rule.

### 6. Phase 3 has no zero-findings / empty-diff branch — MAJOR

> `176:` ⛔ **This is ONE continuous flow. Execute every step in order. Do NOT jump to `git push`.**
> `199-206:` ONE commit with all fixes: `git add <specific changed files>` / `git commit -m "fix:
> address CI and review findings…"`

Reading B enters Phase 3 with a finding but no file to change. 3b then validates an empty changed
surface (lint + tsc + pytest for nothing), 3c commits nothing — an empty commit or a `nothing to
commit` abort that looks like a hook failure — and 3f pushes nothing while reporting success. Line
176 forbids skipping steps, so the literal follower cannot exit the flow.

**Smallest fix:** open 3a with *if no finding has a file to change, skip to Phase 5 and report the
unfixed BLOCKING rows*.

### 7. No re-run path, and Phase 4 is gated on a push — MAJOR

> `300:` When you do loop, after pushing CI + reviews re-run (~3-5 min). If new findings appear:
> `296:` (uncertain fix, flaky/env-dependent check, interdependent findings, or a high-stakes PR…)

Line 296 names "flaky/env-dependent check" as a qualifying reason to loop — the exact category of an
HTTP 429 — but the loop's entry is a push, and here there is nothing to push. `gh run rerun` appears
nowhere in the skill. The one correct action in this scenario (re-run run 9911, then confirm the gate
goes green) is unreachable through the skill's control flow.

**Smallest fix:** in Phase 4, allow entry without a push and add *for a runner-error failure:
`gh run rerun <id> --failed`, then re-check `gh pr checks $PR`* — counting toward the 2-cycle cap.

### 8. Six variables the bash blocks interpolate are never derived — MAJOR

> `68-71:` Resolve, and keep for the rest of this run: **`$GH_AVAILABLE`** … **`$PR`** …
> **`$BASE_REF`** … and **`$REPO` / `$OWNER` / `$REPO_NAME`** for the GraphQL calls below.

"Resolve" names no command. The blocks at 83-117, 222-244 and 248-267 are formatted as
copy-executable and interpolate all six. A literal follower's first real call is
`gh api graphql … -F pr= -F owner= -F repo=` and takes a GraphQL type error on an empty `Int!` — an
error that reads as a gh/API problem, not as a missing setup step, which is the expensive part.

**Smallest fix:** one line under 71:
`eval "$(gh pr view --json number,baseRefName,headRepositoryOwner,headRepository --jq '…')"` — or
simply state the two `gh pr view` calls.

### 9. `$REVIEW_ALLOWLIST` is used 74 lines before it is defined — MINOR

> `152:` … or is in the allowlist (`$REVIEW_ALLOWLIST` — union of `review.available`, default
> `greptile|coderabbit|claude`).
> `226:` `REVIEW_ALLOWLIST=$(jq -r '(.review.available // […]) | join("|")' .weside/config.json …)`

Phase 1d classifies Bot? against a variable Phase 3d sets. Line 249 ("Reuse `$REVIEW_ALLOWLIST`
exactly as set in 3d — do NOT redefine it with a different default") shows the author knew the
duplicate-default hazard and fixed it downstream only; line 152 still carries a third copy of the
literal default. Harmless in this scenario (zero threads), wrong in general.

**Smallest fix:** move the `REVIEW_ALLOWLIST=` assignment into the Phase 1 setup block at 68-71 and
cite it from 152, 226 and 249.

### 10. 3b restates the `test-runner` agent's rules instead of citing it — MAJOR (authoring)

> `189-192:` For each stack the diff touches: lint + format with auto-fix, then the type-checker,
> then the tests covering the diff (mapped paths for pytest, `--findRelatedTests` for Jest). **Two
> rules carry over from the `test-runner` agent**: **derive the base ref**, never assume `main`, and
> **fall back to the full suite** when the diff crosses test config or exceeds ~50 files.
>
> plugin-authoring `13-15:` Every rule, procedure, schema, or template is defined in **exactly one
> file** … Every other place cites it with one sentence + path (`see references/x.md`).

The skill *names the owner in the same sentence in which it copies the owner's rules* — and there are
two live owners it duplicates, the `we:static-analyzer` and `we:test-runner` agents (`/we:static`,
`/we:test`). Four lines of procedure now live in two places; only one will be updated. This is not
the sanctioned exception, which is limited to self-contained briefs (plugin-authoring 22-24) — this
skill runs in the main agent with full plugin context (line 13).

The same sentence also names the agent bare: `the test-runner agent`, where the real identifier is
`we:test-runner`.

> plugin-authoring `48:` `subagent_type` is always plugin-namespaced: `we:doc-architect`, never bare
> `doc-architect`.

This is a prose mention rather than a `subagent_type:` field, so the letter of line 48 is arguable —
but line 92 lists "dead `references/*.md` / `/we:*` / `subagent_type` mentions" among what
`validate-consistency.py` rejects, and a bare `test-runner` is precisely the string that check
cannot resolve.

**Smallest fix:** replace 189-192 with *run `/we:static` then `/we:test` over the changed surface*.
That removes the duplication and the un-namespaced reference in one edit.

### 11. The Rules block retells the steps — MAJOR (authoring)

> `324-334:` `## Rules` / The severity policy and Phases 1–5 above are the spec — reminders: /
> - **Fix everything, push once, no leftovers** … / - **Never auto-resolve a human-authored thread**
> … / - **Claude Code Review is a comment, not threads** … / - **One pass by default, max 2 cycles…**
>
> plugin-authoring `26-29:` **Rules blocks don't retell steps.** A `## Rules` section at the end of a
> skill contains ONLY invariants that are not already stated in the steps. A Rules block that
> paraphrases the steps is the start of drift: two places, one behavior, and only one gets updated.

Bullet 1 paraphrases 15 + 280-285; bullet 2 paraphrases 31 + 212-213 + 270; bullet 3 paraphrases
104-110 + 156-161 + 216-220 (its **fourth** statement); bullet 4 paraphrases 45-52 + 293-298. The
line "The severity policy and Phases 1–5 above are the spec — reminders:" is the author acknowledging
the violation rather than removing it. Only bullet 5 (`--ci-only`) is new — and that is defect 4.

**Smallest fix:** delete 324-334; relocate `--ci-only` per defect 4.

### 12. No phase ends in checkable completion criteria — MINOR (authoring)

> plugin-authoring `71-73:` **Completion criteria are checkable.** A phase ends with `- [ ]` items the
> agent can verify (can it tell done from not-done?), not with prose like "when everything works".

There is no `- [ ]` anywhere in the 335 lines. Phase 5 (313-320) comes closest — a bulleted report
shape — but "CI status (pass/pending/fail)" is a field to fill, not a condition to satisfy, which is
precisely why it can print `fail` under a Phase 2 verdict of "All green".

**Smallest fix:** end Phase 3 and Phase 5 with a short `- [ ]` list, one item being
*- [ ] every required check is `pass`, or each red one has a documented disposition*.

### 13. Unpaired negations — MINOR (authoring)

> `218-219:` Don't try to `resolveReviewThread` it (there's nothing to resolve) and don't treat its
> absence from the thread list as "missed".
>
> plugin-authoring `65-67:` **Pair every negation.** "Don't X" alone steers by prohibition and
> backfires; write the positive action next to it… A bare prohibition is allowed only when no
> positive form exists.

The positive form exists and is stated three lines later ("confirmed by the re-review"), but the two
prohibitions stand alone at the point of instruction. Most other negations in the skill *are* paired
correctly (121, 176→269, 50-51) — this is the outlier.

**Smallest fix:** "…— instead, confirm it via the post-push re-review verdict."

### 14. Frontmatter — PASS on size, MINOR on triggers

> `3-7:` description: > CI/Review checker and fixer — collects ALL findings from CI + every PR review
> source (reviewer-agnostic), fixes per severity policy, resolves all bot threads, pushes only when
> nothing blocking remains. Use when user says "/we:ci-review", "fix ci", "fix reviews", "ci failed".

~290 bytes, under the "≤ ~400 bytes" limit (plugin-authoring 53-55): **pass**. Two smaller misses:
the leading word is a noun phrase, not the action ("**Front-load the leading word.** The first word
or phrase names the action or artifact", 58-59); and "fix ci" / "ci failed" are synonyms reaching the
same branch, against "**One trigger per branch.** Each quoted phrase must reach a distinct branch of
the skill. Synonyms that rename a single branch are duplication — cut them." (60-62). If `--ci-only`
were properly defined, one of them could legitimately route there.

### 15. No-op lines that teach Opus what it already does — MINOR (authoring)

> `179:` 1. Read each finding, open file, make fix
> `13:` Iteratively collects findings from CI + reviews … Runs in the main agent (not a subagent) so
> the user can observe every step.
> `201-205:` `git add <specific changed files>` / `git commit -m "fix: address CI and review
> findings` / … / `{TICKET}"`
>
> plugin-authoring `68-70:` **No no-ops.** A line the model already obeys by default ("be thorough",
> "consider edge cases") pays context load to say nothing. Cut it — or, if it must steer, replace it
> with a stronger word that actually changes behavior.

Line 179 instructs the agent to read a finding and edit the named file; line 13's second clause
describes a harness fact the harness has already decided; 201-205 spells out `git add`/`git commit`.
None changes behaviour. The steering content sits entirely in their neighbours — line 180 ("Do NOT
commit between fixes — accumulate ALL changes") and line 199 ("ONE commit with all fixes") — both of
which survive the cut.

**Smallest fix:** delete 179, delete line 13's "Runs in the main agent…" clause, and reduce 199-206
to the prose sentence plus "message references `{TICKET}`".

## What I needed and did not find

Strictly: mechanics a fresh Opus agent would **not** supply unprompted.

1. **The convention that `VERDICT:ERROR` / no-verdict is the runner, not a finding — and that the
   response is a re-run, not a code change.** This is repo knowledge, not general competence. Without
   it, the honest agent classifies the red check as an unexplained BLOCKING and stalls; the careless
   one calls it green.
2. **A re-run mechanic and its budget.** Whether `gh run rerun 9911 --failed` is mine to fire or the
   user's call, and whether it counts against the 2-cycle cap. Nothing in the skill establishes
   either, and the answer is a project convention.
3. **A terminal state for "blocked, nothing to fix, nothing to push".** The skill has exactly two
   endings: all-green-STOP (167) and pushed-and-reported (Phase 5). This scenario is neither, and
   inventing the third ending is a policy choice I should not be making silently.
4. **`--ci-only`'s actual semantics.** The user's phrasing invokes it; I cannot infer whether it also
   suppresses 3d/3e and the push.

Deliberately excluded: deriving `$PR`/`$OWNER`/`$REPO_NAME` (I do that unprompted — it is defect 8
because the blocks are presented as executable, not because I would be lost); **opening the failing
job's log once told a check is red** (I would guess my way there — the problem is that line 167
licenses me not to, which is defect 1, not a gap); and skipping a commit when the diff is empty.

## What could be cut

- **`324-334` (Rules block)** — four bullets, each the third or fourth statement of its rule. Delete
  entirely; relocate the `--ci-only` line. ~11 lines.
- **`45-52` vs `293-298` vs `333-334`** — the single-pass-by-default policy stated three times, at
  ~8, ~6 and ~2 lines. Keep 293-298 (at the phase it governs), cut 45-52 to one sentence.
- **`28-36` vs `21-23`** — the severity table already carries "MUST fix / only exception"; 28-36
  re-states the exception as three prose criteria and 169-170 states it a third time ("the single
  spec" — while being the third copy). Keep the criteria list, cut 28-31 and 169-170.
- **`126-128` vs `282-285`** — "Start early, push late" written twice verbatim; keep the 3f copy.
- **`104-110` vs `156-161` vs `216-220` vs `331-332`** — "Claude review is a comment, not a thread,
  so it has nothing to resolve" appears **four** times, ~24 lines total. Once, in 1d, suffices.
- **`178-181`** — "1. Read each finding, open file, make fix / 2. Do NOT commit between fixes". Only
  the second half steers; the first is a no-op ("**No no-ops.** A line the model already obeys by
  default … pays context load to say nothing", plugin-authoring 68-70).
- **`199-206`** — the literal `git add` / `git commit -m` block. The instruction "ONE commit, message
  references the ticket" is the whole content; the code fence adds nothing an agent needs.
- **`25-26`** — the aside that `/we:doc-improve` uses a different scale. True, and irrelevant to
  anyone running this skill.
- **`13`** — "Runs in the main agent (not a subagent) so the user can observe every step" describes
  the harness, which already decided this.
- **`189-192`** — cut to a citation of `/we:static` + `/we:test` (defect 10); saves 4 lines and one
  drift surface.

Rough total: ~70 of 335 lines are duplication or no-op, and none of them buy the one paragraph this
scenario needed.

## Grade

**1/5** — a fresh Opus agent following this skill literally reports "All green, ready for merge" on
a PR whose required check is red and which the user explicitly asked about; the push gate certifies
that state as pushable, the severity policy has no legal disposition for a runner error, no re-run
path exists, and `--ci-only` — the flag for exactly this request — is eight undefined words in a
Rules block that should not contain it.
