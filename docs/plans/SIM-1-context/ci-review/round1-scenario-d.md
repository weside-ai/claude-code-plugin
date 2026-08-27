# SIM-1 · ci-review · Round 1 · Scenario D (unattended run until merge)

Table-top simulation. Nothing was executed. Skill under test:
`we/skills/ci-review/SKILL.md` (335 lines). Authoring contract:
`.claude/rules/plugin-authoring.md`. Repo context: `the host repo`,
`the host repo's CI rules file.

User request, verbatim: *"automerge ist aktiviert, mach /ci-review bis der PR
gemerged ist, maximal 3 Runden. Ich bin weg."* — then absent for an hour.

World: branch `fix/TICKET-000-copy-fix`, PR #3730, base `main`, `gh` authed,
auto-merge (squash) armed.

---

## Trace

### Round 0 — reading the skill against the request

Before any tool call I hit the first fork. The user asked for **up to 3 rounds,
unattended, until merged**. The skill's line 45 says:

> **Default to a single pass.** Collect → fix all findings → push, then **stop** and report — one round is the normal case. (line 45–46)

and enumerates the *only* reasons to loop (lines 47–52):

> Only re-enter the post-push loop (Phase 4) when there is a **concrete reason** to expect a second round: a fix you are genuinely unsure resolved the finding, a flaky/environment-dependent check, interdependent findings where fixing one may surface another, or a **high-stakes PR** (security-sensitive, migration, release-blocking) (lines 47–50)

**"The user explicitly asked me to loop" is not on that list.** The list is
closed ("Only … when"), and every item on it is a property of the *PR*, not of
the *instruction*. A copy-fix fix is none of: security-sensitive, migration,
release-blocking, flaky, interdependent. So read literally, the skill tells me
to push once and stop — directly against the standing instruction. I invented
the override ("an explicit user instruction outranks a default") to proceed.
**The skill never says a user instruction can enter Phase 4.** Recorded as
defect 1.

Second fork, same breath: line 302 caps me at **2**, the user asked for **3**.

> ### Self-loop (max 2 total cycles) (line 302)
>
> 1. After 2 total cycles → STOP and ask user (line 307)

I parked the conflict and started collecting, since the cap only bites later.
It bites, exactly, at the round the scenario says the PR goes green. Recorded
as defect 2.

---

### Round 1

**Phase 1 preamble (lines 68–71)** — resolve `$GH_AVAILABLE`, `$PR`,
`$BASE_REF`, `$REPO`/`$OWNER`/`$REPO_NAME`. The skill names the variables and
gives **no command to fill any of them**. I invented:

```
Bash: gh auth status                                          → $GH_AVAILABLE=true
Bash: gh pr view --json number,baseRefName,headRefName,url \
        --jq '"\(.number) \(.baseRefName)"'                   → $PR=3730  $BASE_REF=main
Bash: gh repo view --json nameWithOwner --jq .nameWithOwner    → $REPO=the app repo
      → $OWNER=the host repo-ai  $REPO_NAME=the host repo
```

I would have done this unprompted, so it is not a gap in *mechanics* — but the
skill spending five lines naming variables and zero lines filling them is
lopsided. `$BASE_REF` is resolved here and then used exactly once (3e-bis,
migration branches) — dead for this PR.

**1a — the four collection sources (lines 84–116).** Run as written:

```
Bash: gh pr checks 3730
  → Backend (Test)            fail   https://github.com/.../runs/...
     CI Summary               fail
     claude-review            pass
     codex-review             pass
     Mobile (Test)            pass   … (rest pass)
```

```
Bash: gh api graphql -f query='…reviewThreads(first:100)…' \
        -F pr=3730 -F owner=the host repo-ai -F repo=the host repo \
        --jq '…select(.isResolved==false)'
  → 1 node: author.login="coderabbitai[bot]", body "Nitpick: 'Änderungen
    gespeichert' vs 'Gespeichert' — pick one voice", path apps/mobile/…/toast.ts
```

```
Bash: gh api repos/the app repo/pulls/3730/reviews \
        --jq 'group_by(.user.login)[] | last | select(.user.login|endswith("[bot]")) | …'
  → === coderabbitai[bot] === (summary body, no new findings)
```

```
Bash: gh api repos/the app repo/issues/3730/comments --paginate \
        --jq '[.[] | select(.user.login|test("claude";"i")) | select(.body|test("## Code Review"))] | sort_by(.created_at) | last | .body'
  → "## Code Review … <!-- VERDICT:PASS -->"   (no SEV markers)
```

Here I noticed the skill contradicting itself inside one section. Line 80–81:

> There is **ONE** collection path, regardless of which reviewer posted … **Do not special-case any reviewer by name.** (lines 80–81)

and then source 4, twenty-five lines later, is a hardcoded name filter:
`select(.user.login|test("claude";"i"))` (line 112). This repo's
`.weside/config.json` lists `review.available = ["codex","claude","coderabbit"]`
and the host repo's CI rules makes **`codex-review` a required check with the same
verdict policy as `claude-review`**. A codex-review verdict posted as an issue
comment is invisible to all four sources. In this scenario codex-review happens
to be green every round, so it never bites — but I only know that because the
scenario told me, not because the skill collected it. Recorded as defect 3.

**1b (lines 119–128)** — "start now, hold the push". Not applicable: nothing
is `pending`; `Backend (Test)` has already concluded `fail`.

**1c (lines 130–141)** — "CI failures: fix them", then a four-row table of
generic fixes (ImportError, flaky, coverage, lint). None matches "an assertion
compares the old toast string". The table told me nothing; **the skill never
says to read the failing job's log**, which is the one thing I actually need.
Invented:

```
Bash: gh run view <run-id> --log-failed
  → tests/mobile/toast.spec.ts:41
    AssertionError: expected 'Gespeichert' to equal 'Änderungen gespeichert'
```

**1d — findings table (lines 143–161).** Built as specified:

| # | Source | Bot? | Severity | File:Line | Issue | Thread ID | Action |
|---|---|---|---|---|---|---|---|
| 1 | CI · Backend (Test) | — | BLOCKING | tests/mobile/toast.spec.ts:41 | asserts pre-change copy | — | fix |
| 2 | CodeRabbit | yes | NITPICK | apps/mobile/…/toast.ts | voice inconsistency | PRRT_kwDO… | fix (cheap) |
| 3 | Claude | yes | — | — | VERDICT:PASS, no SEV rows | — | none |

Row 3 is a row the skill's own format cannot express: line 160 says the Claude
comment is split "one row per `<!-- SEV:* -->` finding". A PASS with zero SEV
markers produces zero rows, so the collection's most important signal — *the
review gate is currently satisfied* — leaves no trace in the artifact the skill
asks me to build. I kept it as a note.

**Phase 2 (lines 165–170).** Findings > 0, so the "0 findings → All green,
ready for merge → STOP" exit (line 167) does not fire. Note for later: that
line is the **only** place in 335 lines the word *merge* appears in an exit
condition, and it says "ready for merge", not "merged".

**Phase 3a/3b/3c.** Fix the assertion to the new copy; take the CodeRabbit
nitpick (one word, on the seam this PR touches — finish-first, lines 38–43).
No commit between them (line 181).

```
Edit: tests/mobile/toast.spec.ts   (assertion → 'Änderungen gespeichert')
Edit: apps/mobile/…/toast.ts       (unify voice)
Bash: yarn lint --fix … ; yarn tsc --noEmit ; yarn jest --findRelatedTests <2 files>   → green
Bash: ls scripts/check-*.sh  → run the ones that apply  → green
Bash: git add tests/mobile/toast.spec.ts apps/mobile/…/toast.ts
Bash: git commit -m "fix: address CI and review findings

{TICKET}"
```

`{TICKET}` (line 205) is a placeholder the skill never resolves. `$PR`,
`$BASE_REF`, `$REPO` all get a resolution block; `{TICKET}` gets none. I
inferred `TICKET-000` from the branch name. Recorded as defect 6.

**3d (lines 208–243).** `REVIEW_ALLOWLIST` from `.weside/config.json` →
`codex|claude|coderabbit`. One unresolved bot thread → resolve it.

```
Bash: REVIEW_ALLOWLIST=$(jq -r '(.review.available // […]) | join("|")' .weside/config.json)
Bash: gh api graphql … --jq '…| .id'        → PRRT_kwDO…
Bash: gh api graphql -f query='mutation($id:ID!){resolveReviewThread(input:{threadId:$id}){thread{isResolved}}}' -f id=PRRT_kwDO…
```

**3e (lines 246–267).** `UNRESOLVED` → `0`. Gate passes.

**3e-bis.** No migration. Skip.

**3f (lines 280–289).** `gh pr checks 3730` → no pending. `git push`.

**End of round 1.** Now the skill's default (line 45) says: **stop and report.**
The user is gone and the PR is not merged. I overrode it, per the invented rule
in Round 0, and entered Phase 4.

---

### Round 2

**Phase 4 step 1 (line 304)** — "Wait for checks to settle (use `gh pr checks
$PR` to monitor)". No mechanism, no interval, no timeout. `gh pr checks` is a
one-shot; "monitor" with it means a poll loop the skill does not describe.
Invented:

```
Bash (background): gh pr checks 3730 --watch --interval 30
  → all checks conclude; claude-review = fail
```

**Step 2 — re-collect.** All four sources again. Threads: none new. Note what
the skill actually tells me to do from here: step 3 is "If new findings → fix
and push again" (line 306) — Phase 3 is not mentioned, so 3d and 3e are not on
the prescribed path for this round or the next. I ran them anyway, off-script.
Recorded as defect 14. Source 4:

```
  → "## Code Review
     <!-- SEV:WARNING --> the test now asserts the copy twice …
     <!-- VERDICT:WARNING -->"
```

Severity policy line 22: WARNING → **MUST fix**. Line 309 ("same finding twice
= structural problem") does not fire — this is a *new* finding my own round-1
fix created.

Fix, validate, commit. **3d**: no unresolved bot threads to resolve — and the
skill's note at lines 216–220 is explicit that the Claude comment has no thread,
so the round-2 finding leaves the 3e gate at `0` and the gate says "all clear"
while a `VERDICT:WARNING` is live on the PR. **3e prints "All bot threads
resolved"** (line 265) on a PR whose required `claude-review` check is red. The
hard gate measures the wrong thing here; only my own reading of source 4 stopped
me. Recorded as defect 4.

```
Edit: tests/mobile/toast.spec.ts  (drop the duplicate assertion)
Bash: yarn jest --findRelatedTests …  → green
Bash: git add … && git commit -m "fix: address CI and review findings\n\nTICKET-000"
Bash: gh api graphql … reviewThreads … → 0 unresolved bot threads
Bash: gh pr checks 3730 → no pending
Bash: git push
```

**End of round 2 — the hard stop.** Line 307:

> 1. After 2 total cycles → STOP and ask user (line 307)

repeated in Rules, line 334:

> after the second push still has findings → stop and ask the user (line 334)

I have now pushed twice. Two readings, both broken:

- *cycle = a full pass* → I am at 2/2. **Stop now.** The PR is unmerged, the
  round-2 fix is unverified, the user is gone, and there is no one to ask. The
  user's explicit `maximal 3 Runden` is unreachable by one.
- *cycle = a post-push check* → I have done 1. One left. But then "max 2 total
  cycles" (line 302) and "After 2 total cycles" (line 307) both use *total*,
  which reads as passes, not checks.

The skill never defines "cycle". The two candidate definitions differ by exactly
the round this scenario needs. Recorded as defect 2 (BLOCKING).

Worse, line 334 conditions the stop on "still has findings" while line 307
conditions it on nothing at all. If I take 334, I may continue when green; if I
take 307, I stop regardless. Two lines, one behavior, different answers.

I proceeded to round 3 on the user's explicit `maximal 3 Runden`, against the
skill.

---

### Round 3

```
Bash (background): gh pr checks 3730 --watch --interval 30
  → all pass, claude-review pass
Bash: gh api graphql … reviewThreads …                  → 0 unresolved
Bash: gh api repos/…/issues/3730/comments --paginate …  → "<!-- VERDICT:PASS -->"
```

Zero findings. **And now the skill has no exit.** Phase 4's four steps (lines
304–307) are: wait, re-collect, *if new findings* fix and push, after 2 cycles
stop and ask. There is **no branch for "re-collected, nothing there, we are
done"**. Step 3 is a no-op, step 4 fires the ask-the-user stop on a completely
green PR. Phase 2's clean exit ("0 findings → All green, ready for merge → STOP",
line 167) belongs to the *initial* collection and is never re-entered from
Phase 4. Recorded as defect 5.

**Merge.** The user's actual goal — *bis der PR gemerged ist* — is unaddressed
by all 335 lines. The skill mentions merge once, as the phrase "ready for merge"
(line 167). It says nothing about `gh pr merge`, auto-merge, `mergeStateStatus`,
`state`, `mergedAt`, or that a green PR with auto-merge armed will merge itself
after the last required check reports. Everything below is invented:

```
Bash: gh pr view 3730 --json state,mergeStateStatus,autoMergeRequest,mergedAt
  → state=OPEN, mergeStateStatus=CLEAN, autoMergeRequest={squash}, mergedAt=null
  (poll ~90 s)
Bash: gh pr view 3730 --json state,mergedAt
  → state=MERGED, mergedAt=2026-08-27T…
```

Without inventing that, the run ends at "pushed, CI green" and I report success
on a question the user did not ask.

**Phase 5 (lines 313–320).** The prescribed report is: findings table, fix
summary, skipped items, **push status, CI status, unresolved thread count**.
There is no merge line. The single fact the user left the room to get —
*is it merged?* — has no slot in the skill's own report format. I added one.

---

### The four questions, answered directly

**1. Does "Default to a single pass" (45–52) let me honour "bis gemerged, max 3
Runden"?** No. The permission list at 47–50 is closed and enumerates PR
properties only; a user instruction is not among them. Read literally the skill
stops me after round 1. I had to invent the override.

**2. What does the "max 2 total cycles" cap (302–308) do to a user-requested 3?**
It forbids it, silently. The skill states the cap as an absolute with no
user-override clause, and never defines "cycle", so I cannot even tell whether
round 3 is the forbidden one. In this scenario round 3 is precisely the round in
which the PR goes green and merges — obeying the skill means never observing the
outcome the user asked for.

**3. Step 4 says "STOP and ask user" — the user is gone. What do I do?** The
skill has no answer. There is no unattended mode, no "if the user is
unreachable" branch, no fallback (leave a PR comment, write a handoff, stop with
a durable note). Both of the skill's terminal states — 3e's `exit 1` and 307's
ask — assume a human in the room. I continued on the standing instruction and
recorded that I was off-script.

**4. Where does the skill tell me about merge state / auto-merge / knowing the
PR merged? What must I invent?** Nowhere. One phrase, "ready for merge" (line
167), and it is a *pre*-merge state. Invented in full: the `gh pr view --json
state,mergeStateStatus,autoMergeRequest,mergedAt` check, the poll for auto-merge
to fire, the meaning of `mergeStateStatus` values, and the merge line in the
report.

**5. Does the skill define "the review gate" and when it is satisfied?** No. The
phrase appears twice, both times in passing and both times inside the source-4
aside: "which is what the CI gate checks" (line 161) and "the CI gate fails on
`VERDICT:BLOCKING`/`VERDICT:WARNING`" (line 219). It is never named as a check,
never listed (the host repo's CI rules names three required checks: `CI Summary`,
`claude-review`, `codex-review`), and no phase states a terminal condition of the
form "the gate is satisfied when X". The nearest thing to a definition is buried
in a block-quote about a different topic.

---

## Conformance checklist

- [x] **Phase 1 preamble (68–71)** — names the variables unambiguously; gives no
      command to resolve any of them, but the intent is unmistakable.
- [x] **1a sources 1–3 (84–103)** — concrete, runnable, unambiguous.
- [ ] **1a source 4 (105–113)** — contradicts line 81's "do not special-case any
      reviewer by name" and hardcodes `claude`, missing this repo's configured
      `codex` reviewer.
- [x] **1b (119–128)** — clear; correctly inert here.
- [ ] **1c (130–141)** — the fix table matches none of the real failure; never
      tells me to read the failing log.
- [ ] **1d (143–161)** — no row shape for a Claude comment with zero SEV
      findings, i.e. for the gate-is-green signal itself.
- [x] **Phase 2 (165–170)** — unambiguous, though its clean exit is unreachable
      from Phase 4.
- [x] **3a–3c (178–206)** — clear, except `{TICKET}` is undefined.
- [x] **3d (208–243)** — the strongest section in the skill; explicit, scripted,
      correctly scoped to bot threads.
- [ ] **3e (246–270)** — prints "all clear" on a PR with a live
      `VERDICT:WARNING`; the hard gate does not gate what Phase 4 later blocks on.
- [x] **3e-bis (272–278)** — clear; not applicable.
- [x] **3f (280–289)** — clear three-part precondition.
- [ ] **Phase 4 (293–309)** — no definition of "cycle", no success exit, no
      user-instruction override, no wait mechanism, contradicts line 334.
- [ ] **Phase 5 (313–320)** — no merge status, no verdict status; reports push +
      CI only.
- [ ] **Rules (324–335)** — four of six bullets paraphrase the steps;
      `--ci-only` is introduced here and implemented nowhere.

---

## Skill defects

### 1. The single-pass default has no user-instruction override — MAJOR

> "**Default to a single pass.** … Only re-enter the post-push loop (Phase 4) when there is a **concrete reason** to expect a second round: a fix you are genuinely unsure resolved the finding, a flaky/environment-dependent check, interdependent findings …, or a **high-stakes PR** …" (lines 45–50)

Every entry condition is a property of the PR. A copy-fix fix satisfies none.
The user's standing instruction — the loudest signal in the session — is not a
listed reason, so a literal reading makes me stop after round 1 with the PR
unmerged and the user unreachable. A fresh agent that follows the skill fails
scenario D at the first exit.

**Smallest fix:** add one entry to the list at line 48: *"or the user asked for
a specific number of rounds or for a terminal state (merged, green) — the user's
instruction sets the cycle budget."*

### 2. The cycle cap is undefined, absolute, and lands on the winning round — BLOCKING

> "### Self-loop (max 2 total cycles) … 4. After 2 total cycles → STOP and ask user" (lines 302, 307)
> "**One pass by default, max 2 cycles when looping** — … after the second push still has findings → stop and ask the user" (lines 333–334)

Three problems compound. (a) "cycle" is never defined — pass or post-push check?
The skill uses **four** words for this one unit and binds none of them: "single
pass" (45), "round" (46, 48), "post-push loop" (47), "cycle" (52, 302). A reader
feels certain they understood a term the skill never defined.
The two readings differ by exactly one round, and that round is the one where
this PR merges. (b) The cap is stated with no user-override, so a
user-authorised 3 is forbidden by the skill. (c) 307 stops unconditionally while
334 stops only "still has findings" — two lines, one behavior, opposite answers
on a green round 3.

**Smallest fix:** define the unit once at line 302 (*"a cycle = one push
followed by one re-collect"*), state the budget as *"default 2, or the number
the user named"*, and delete the duplicated condition at line 334 so 307 is the
single owner.

### 3. Source 4 special-cases `claude` in violation of the skill's own line 81 — MAJOR

> "There is **ONE** collection path, regardless of which reviewer posted … **Do not special-case any reviewer by name.**" (lines 80–81)
> `select(.user.login|test("claude";"i"))` (line 112)

`.weside/config.json` in this repo lists `review.available =
["codex","claude","coderabbit"]`, and the host repo's CI rules makes `codex-review` a
required check governed by the same verdict policy. A `codex-review` summary
comment is caught by none of the four sources: not the thread query (it is a
comment), not the review-body loop (line 102 requires an `[bot]` login suffix),
and not source 4 (name-filtered to `claude`). In scenario D codex-review is
green every round, so the miss is invisible — which is the worst version of it.
Note also that lines 226 and 152 already build `$REVIEW_ALLOWLIST` from that
exact config key; source 4 simply does not use it.

**Smallest fix:** replace the literal `test("claude";"i")` at line 112 with
`test("'"$REVIEW_ALLOWLIST"'";"i")`, and drop the phrase "the host repo's Claude
review" from the comment at 106–110 in favour of "each configured reviewer".

### 4. The 3e hard gate reports "all clear" while a blocking verdict is live — MAJOR

> `echo "All bot threads resolved. (Human threads, if any, are listed in the report for the user.)"` (line 265)
> "**Claude Code Review (source 4) has no thread to resolve** … Don't try to `resolveReviewThread` it" (lines 216–217)

The two are individually correct and jointly blind. 3f's precondition (a) is
"`gh pr checks $PR` shows no `pending`/`in_progress`" (lines 282–283) — a
condition a **failing** `claude-review` satisfies just as well as a passing one.
Precondition (b) is 3e, which counts threads only. So the full push gate —
(a) nothing pending, (b) 0 unresolved threads, (c) no migration — is structurally
incapable of seeing a verdict finding, the one finding class that by the skill's
own note (216–220) has no thread. Nothing in Phase 3 gates on the verdict the
skill itself spent lines 105–113 and 155–161 collecting. In round 2 that class
was the *only* finding on the PR.

**Smallest fix:** add a fourth precondition to 3f at line 282: *"(d) the newest
source-4 comment per configured reviewer carries no unaddressed `SEV:` row."*

### 5. Phase 4 has no success exit — BLOCKING for this scenario

> "3. If new findings → fix and push again / 4. After 2 total cycles → STOP and ask user" (lines 306–307)

Round 3 re-collects, finds nothing, and falls off the end of a four-step list
whose only terminal is "ask user". The skill's clean exit — "0 findings → 'All
green, ready for merge' → STOP" (line 167) — lives in Phase 2 and is never
re-entered from Phase 4. So the *good* outcome is the one the skill cannot
express: an agent that reaches green has to invent both the exit and what to
report.

**Smallest fix:** insert between 306 and 307: *"If the re-collect yields 0
findings and no check is failing → the gate is satisfied. Go to Phase 5 and
report the terminal state."*

### 6. `{TICKET}` is an unresolved placeholder — MINOR

> ```
> git commit -m "fix: address CI and review findings
>
> {TICKET}"
> ``` (lines 203–206)

Phase 1 resolves `$PR`, `$BASE_REF`, `$REPO`, `$OWNER`, `$REPO_NAME` and Phase
3d resolves `$REVIEW_ALLOWLIST`; `{TICKET}` alone has no origin and a different
sigil. I inferred `TICKET-000` from the branch. In a repo where Jira Smart Commit
trailers are a real convention (`workflows/git-workflow.md`), guessing the
format is a live risk.

**Smallest fix:** add `**$TICKET**` to the Phase 1 resolve list at line 68 with
its source (branch name / plan file).

### 7. Nothing about merge, auto-merge, or terminal state — MAJOR

Word-search of all 335 lines: "merge" appears at 167 ("ready for merge"), 277
("merge it", about Alembic heads), and 278 ("merge migration"). Auto-merge:
absent. `gh pr merge`, `mergeStateStatus`, `mergedAt`, `state`: absent. Phase 5's
report fields (lines 315–320) are findings table, fix summary, skipped items,
push status, CI status, unresolved thread count — **no merge status**. A skill
whose entire purpose is to drive a PR through its gates never says how to tell
that the PR made it through.

**Smallest fix:** one bullet in Phase 5 after line 319 — *"Merge status:
`gh pr view $PR --json state,mergeStateStatus,autoMergeRequest,mergedAt`. If
auto-merge is armed and the state is `CLEAN`, the merge fires on its own; report
`MERGED` or the blocking `mergeStateStatus`."*

### 8. "The CI gate" names two different things and is never defined — MAJOR

> "which is what the CI gate checks" (line 161)
> "the CI gate fails on `VERDICT:BLOCKING`/`VERDICT:WARNING`, so a green gate after push is the proof" (lines 219–220)

The skill never uses the phrase "review gate" at all — it says **"the CI gate"**,
twice, and both times means the *review-verdict* check (`claude-review`), not
`CI Summary` or the test checks. One term, two referents, in a repo where both
exist as separate required checks. `plugin-authoring.md` lines 39–41: "The same
term must not mean different things in two skills … New skill → new vocabulary,
or exactly the same semantics" — here the collision is inside one file. That
ambiguity is precisely why an unattended agent cannot tell when it is done: "the
CI gate is green" is true of the test checks and false of the verdict check
simultaneously in round 2.

Both mentions also sit inside an aside about source 4 having no thread. The gate
is never named as a check, its members are never listed, and no phase states when
it is satisfied. the host repo's CI rules has the answer — required checks are
`CI Summary`, `claude-review`, `codex-review`, and "an absent check is not a
passing check" — but the skill neither states it nor cites it. For an unattended
run, "when am I done" is *the* question, and the skill answers it in a
parenthesis.

**Smallest fix:** one line under Phase 2 — *"The review gate = every required
check green AND every configured reviewer's newest verdict `PASS` AND 0
unresolved bot threads. That triple is the terminal condition."*

### 9. Rules block retells the steps — MAJOR (authoring contract)

`plugin-authoring.md`:

> "**Rules blocks don't retell steps.** A `## Rules` section at the end of a skill contains ONLY invariants that are not already stated in the steps. A Rules block that paraphrases the steps is the start of drift: two places, one behavior, and only one gets updated." (lines 26–29)

Four of six bullets are paraphrase: line 328 restates 3c+3f; line 330 restates
213; lines 331–332 restate 155–161 and 216–220; lines 333–334 restate 45–52 and
302–307. Defect 2(c) is exactly the predicted drift already materialised — 334
and 307 disagree, and only one was updated.

**Smallest fix:** delete lines 328 and 330–334; keep 335.

### 10. `--ci-only` exists only in the Rules block — MAJOR (authoring contract)

> "- **`--ci-only` flag** — skip reviews, only check CI status." (line 335)

No phase reads it. Phase 1's collection is unconditional across all four
sources; Phase 3d/3e are unconditional on threads. A user passing `--ci-only`
gets a full review run, or the agent invents the branch. This is the inverse of
the rule above — the Rules block is not just retelling steps, it is the *sole
owner* of a behavior the steps do not implement. It also poisons the frontmatter
(see 11): the trigger phrases "fix ci" / "ci failed" have no branch to reach
without it.

**Smallest fix:** either implement it as a one-line guard in Phase 1
(*"`--ci-only`: run source 1 only; skip 1a(2)–(4), 3d, 3e"*) or delete line 335.

### 11. Frontmatter triggers do not map to distinct branches — MINOR (authoring contract)

`plugin-authoring.md`:

> "**One trigger per branch.** Each quoted phrase must reach a distinct branch of the skill. Synonyms that rename a single branch are duplication — cut them." (lines 60–61)

The description (lines 3–7, 301 bytes — **within** the ≤400 budget) quotes four
triggers: `/we:ci-review`, "fix ci", "fix reviews", "ci failed". The skill has
exactly one branch; all four land in it. "fix ci" and "ci failed" would map to
the `--ci-only` branch that does not exist (defect 10). Also, per
`plugin-authoring.md` lines 58–59 ("Front-load the leading word … names the
action"), the description opens on a noun phrase, "CI/Review checker and fixer",
rather than a verb.

**Smallest fix:** cut "ci failed"; keep "fix ci" only if defect 10 is
implemented as a real branch.

### 12. No checkable completion criteria anywhere — MINOR (authoring contract)

> "**Completion criteria are checkable.** A phase ends with `- [ ]` items the agent can verify (can it tell done from not-done?), not with prose like 'when everything works'." (plugin-authoring.md lines 71–73)

No `- [ ]` appears in the skill's 335 lines. Phases 1, 2, 4 and 5 all end in
prose. Phase 4 ending in prose is what produced defect 5 — there was no
checklist to notice was unsatisfiable.

### 13. Unpaired negation at line 218 — MINOR (authoring contract)

> "don't treat its absence from the thread list as 'missed'" (line 218)

`plugin-authoring.md` line 65: "**Pair every negation.** … write the positive
action next to it." A positive form exists and is one clause away: *"treat its
absence as expected — a comment has no thread."* (The skill's other negations —
78, 121, 176, 181, 249, 298 — are correctly paired; this is the one miss.)

### 14. Phase 4 step 3 instructs the exact jump line 176 forbids — BLOCKING

> "⛔ **This is ONE continuous flow. Execute every step in order. Do NOT jump to `git push`.**" (line 176)
> "3. If new findings → fix and push again" (line 306)

Line 306 collapses 3b (validate), 3c (one commit), **3d (resolve bot threads —
the skill's own "central, non-skippable step", line 30)**, 3e (the hard gate),
3e-bis and 3f's three preconditions into three words, and literally prescribes
the jump line 176 forbids in bold with a stop sign. In scenario D **two of the
three rounds run through line 306**, not through Phase 3. It failed to bite only
by luck: round 2 produced no new review threads, and I re-ran 3d/3e voluntarily —
off-script, out of my own habit, not because the skill said so. Had round 2
carried one new CodeRabbit thread, an agent following the text pushes with it
unresolved and the mandatory gate never runs on that round. This is the failure
mode line 208 says "used to get forgotten", reintroduced by Phase 4's shorthand.

**Smallest fix:** one clause at line 306 — *"→ re-enter Phase 3 at 3a and run
every step, including 3d and 3e, before pushing again."*

### 15. The reviewer allowlist default is defined twice — MAJOR (authoring contract)

`plugin-authoring.md`:

> "Every rule, procedure, schema, or template is defined in **exactly one file** … Every other place cites it with one sentence + path" (lines 13–15)

The literal default `greptile|coderabbit|claude` is written out twice inside this
one file — line 152 ("`$REVIEW_ALLOWLIST` — union of `review.available`, default
`greptile|coderabbit|claude`") and line 226 (the `jq` fallback array). Line 249
is the skill *admitting* the drift risk rather than removing it:

> "Reuse `$REVIEW_ALLOWLIST` exactly as set in 3d — do NOT redefine it with a different default." (line 249)

A warning not to desync two copies is the tell that there should be one. And the
default is already wrong for this repo: `.weside/config.json` has
`["codex","claude","coderabbit"]` — `greptile` is absent and `codex` is missing
from the fallback. Same root as defect 3.

**Smallest fix:** resolve `$REVIEW_ALLOWLIST` once in the Phase 1 preamble
alongside `$PR`/`$BASE_REF`; lines 152, 226 and 249 then cite it in one clause
each.

### 16. No-op prose in 3a and 3b — MINOR (authoring contract)

`plugin-authoring.md`:

> "**No no-ops.** A line the model already obeys by default ('be thorough', 'consider edge cases') pays context load to say nothing. Cut it — or, if it must steer, replace it with a stronger word that actually changes behavior" (lines 67–70)

Line 179: "1. Read each finding, open file, make fix" — that is the definition of
fixing a finding. Lines 189–191: "lint + format with auto-fix, then the
type-checker, then the tests covering the diff" — the default order of operations
for any agent validating a diff. Both sections carry exactly one steering clause
each (line 181 "Do NOT commit between fixes"; line 191–192 "derive the base ref,
never assume `main`" + the ~50-file full-suite fallback), and those clauses are
what should survive.

### 17. Line 309's escalation has no criterion and no recipient — MINOR

> "**Each cycle should fix MORE findings, not the same ones.** If the same finding appears 2 times, you have a structural problem — stop and escalate." (line 309)

"Same" is undefined — same thread id? same `file:line`? same subject? In round 2
the finding is *about the same test assertion I just edited*, which is "the same"
under a loose reading and "new" under a strict one; the two readings differ by
whether I stop the run. And the remedy, "escalate", names no target — in scenario
D the only target is a user who left. Pairs with defect 5: every terminal in this
skill assumes a human in the room.

**Smallest fix:** define same as *"the same thread id, or the same
`file:line` + severity"*, and give escalate a fallback for an absent user.

---

## What I needed and did not find

Strictly: mechanics a competent agent would **not** invent unprompted.

1. **The terminal condition for an unattended run.** Not "did CI pass" — I would
   check that anyway — but *which* checks constitute the gate in this repo, and
   that a green gate plus armed auto-merge means the merge fires without me. The
   fact that `mergeStateStatus: CLEAN` + `autoMergeRequest != null` is the
   "walk away safely" state is repo/GitHub knowledge the skill should own.
   (Defects 7, 8.)
2. **What "cycle" counts.** Not inventable — it is the skill's own unit, and the
   two plausible readings differ by the decisive round. (Defect 2.)
3. **What to do when the escalation target is absent.** Every skill terminal
   ends in "ask the user". An unattended contract needs a stated fallback
   (durable note, PR comment, handoff file) or an explicit "user instruction sets
   the budget, then stop with a report". I chose one; a different agent chooses
   differently, which is exactly the *predictability* failure
   `plugin-authoring.md` line 8 names as the root virtue.
4. **That a verdict comment must gate the push.** I caught it in round 2 only
   because I read the comment body carefully. The skill's own hard gate (3e)
   actively told me the opposite. A mechanism that says "clear" when it is not
   is worse than a missing one. (Defect 4.)
5. **`$TICKET`'s source.** Small, but the commit trailer format is a repo
   convention with a documented failure mode; guessing is not the same as
   knowing. (Defect 6.)

Explicitly **not** listed here, because I would do them unprompted: reading
`gh run view --log-failed`; using `--watch` to wait for checks; resolving a
one-word nitpick on the seam I touched; running only the affected tests; batching
fixes into one commit.

---

## What could be cut

- **Lines 130–141 (1c's fix table).** Four generic CI-error→fix rows, none of
  which matched the actual failure. Opus reads the failing log and fixes what it
  says. Worse than neutral: `@pytest.mark.flaky` as a listed remedy invites
  papering over a real failure, and the host repo's CI rules already owns the
  known-CI-states knowledge (`codex-review` red is often the runner; baseline
  baseline starvation) — the far more useful content, uncited. Replace the whole
  table with one line pointing at the failing-log command and the repo rule.
- **Lines 178–181 and 189–192** — no-op prose; see defect 16. One steering
  clause each survives (181, and 191–192's base-ref + 50-file fallback).
- **Lines 328–334 (Rules bullets 1–4).** Pure step paraphrase, and the source of
  the 307/334 contradiction. Delete. (Defect 9.)
- **Lines 25–26.** The `/we:doc-improve` scale disclaimer is cross-skill trivia
  in the middle of the severity spec; one clause in `doc-improve` would own it
  better.
- **Lines 15 and 328** state "Fix everything, push once, no leftovers" twice,
  313 lines apart.
- **Line 13's** "Runs in the main agent (not a subagent) so the user can observe
  every step" — a rationale for a fact the invocation already determines, and in
  scenario D the observer is gone.

Net: roughly 35 of 335 lines are no-ops or duplication, and the space would more
than cover the merge-state section, the gate definition, and the cycle
definition the skill is missing.

---

## Grade

**2 / 5** — the collection phase and the thread-resolution gate (1a sources 1–3,
3d, 3e's mechanics) are genuinely good and would carry an attended single-pass
run; but scenario D breaks the skill at five separate points — the closed
single-pass exception list forbids looping at all, the undefined 2-cycle cap
forbids the user's third round, Phase 4's step 3 bypasses the mandatory
resolve-and-gate flow for both looping rounds, Phase 4 has no success exit, and
merge state is absent from all 335 lines — so a fresh Opus agent either stops
with the PR unmerged or, as I did, goes off-script four times and improvises the
terminal condition the skill was supposed to own.
