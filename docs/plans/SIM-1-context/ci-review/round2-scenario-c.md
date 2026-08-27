# SIM-1 · ci-review · Round 2 · Scenario C

**Table-top simulation. Nothing was executed.** Role: main agent in `the host repo`, user typed
`/we:ci-review`, branch `feat/TICKET-000-escalation`, PR #3725, base
`feat/TICKET-000-integration` (not main), 9 files (Python + TypeScript), five unresolved threads,
one factually-wrong BLOCKING finding in the newest claude review comment.

Skill under test: `we/skills/ci-review/SKILL.md` (285 lines, was 335). All line numbers below are
the **new** file's.

**Headline:** the scenario's central round-1 failure is fixed. The dispute now has a destination
on the PR (L44–47), a format (L40–42), and a named terminal state (L273). The run ends
deterministically in *Blocked — needs a human*, and the report says so. What remains is
**mechanics**, not judgment: the thread reply the skill now mandates cannot be posted from the
data the skill collects, and 3e's "do not redefine `$REVIEW_ALLOWLIST`" is a latent deadlock.

---

## Trace

### Step 0 — invocation, no flag

`--ci-only` is now documented in the body (L24–25) rather than a trailing Rules block. There is
still no `## Invocation` line stating that a bare `/we:ci-review` means the full path; I infer it
from "`--ci-only` narrows the run" (L24). One inference, harmless.

### Step 1 — 1a resolves the run state (L76–84)

The revision **gives the commands** round 1 was missing, and states the hazard first:

> L76: `Each Bash call is a **fresh shell** — derive these in the same block that uses them, or re-derive:`

Tool call 1, verbatim from L79–83:

```bash
gh auth status >/dev/null 2>&1 && GH_AVAILABLE=true || GH_AVAILABLE=false
PR=$(gh pr view --json number --jq .number 2>/dev/null)
REPO=$(gh repo view --json nameWithOwner --jq .nameWithOwner); OWNER=${REPO%%/*}; REPO_NAME=${REPO#*/}
BASE_REF=$(gh pr view $PR --json baseRefName --jq .baseRefName)
gh pr view $PR --json mergeable,mergeStateStatus,autoMergeRequest
```

→ `GH_AVAILABLE=true`, `PR=3725`, `REPO=the app repo`, `BASE_REF=feat/TICKET-000-integration`,
`mergeable: MERGEABLE`, `mergeStateStatus: BLOCKED` (a required check is red), `autoMergeRequest: null`.

L89–91's CONFLICTING/DIRTY branch does not fire. **Round-1 defect 1's silent self-confirming skip
is gone** — the `if [ "$GH_AVAILABLE" = true ]` guard that swallowed the whole collection no longer
wraps 1b. Residual: the 1b and 3d blocks still reference `$PR`/`$OWNER`/`$REPO_NAME` without
re-deriving them, so I substitute literals on L76's authority. See defect verdicts.

### Step 2 — 1b source 1: CI status

```bash
gh pr checks 3725
```
→ everything `pass`, `claude-review` = `fail`. Per L20–22 ("The gate is satisfied when every
required check has concluded non-red") and L122 ("Every non-pass check is a BLOCKING row"), this
is a finding.

1c sends me to the log:

```bash
gh run view <claude-review-run-id> --log-failed
```
→ the run succeeded at posting; the failure is the verdict itself. 1c's classification bullets
(L134–140) offer "a review verdict that never posted → BLOCKING row" and "the runner, not the
code → re-run". Neither is *this* case: the verdict posted, and it is the content of source 4.
**The skill still never states the check↔comment identity** (round-1 defect 5). I decide unaided
that `claude-review: fail` is not an independent row and that its content is the three `SEV:` rows;
I do **not** call `gh run rerun`.

### Step 3 — 1b source 2: unresolved threads (PRIMARY)

```bash
gh api graphql -f query='query($pr:Int!,$owner:String!,$repo:String!){
  repository(owner:$owner,name:$repo){pullRequest(number:$pr){reviewThreads(first:100){nodes{
    id isResolved isOutdated comments(first:1){nodes{author{login} body path line}}
  }}}}}' -F pr=3725 -F owner=the host repo-ai -F repo=the host repo \
  --jq '.data.repository.pullRequest.reviewThreads.nodes[] | select(.isResolved==false)'
```

| # | login | bot? | path:line | text |
|---|---|---|---|---|
| T1 | `coderabbitai[bot]` | yes | `service.py:88` | 🛠️ Refactor suggestion |
| T2 | `coderabbitai[bot]` | yes | `useThing.ts:41` | ⚠️ Potential issue: missing dep |
| T3 | `coderabbitai[bot]` | yes | `test_service.py:12` | 🧹 Nitpick: unused import |
| T4 | `github-actions[bot]` | yes | `service.py:120` | claude inline thread |
| T5 | `maintainer` | **no** | `service.py:60` | "das war Absicht, siehe ADR" |

The query selects `id … author{login} body path line` — **not the comment's `databaseId`**. That
matters at 3d; see new defect N2.

### Step 4 — 1b sources 3 and 4

Source 3 (L110–112) → the CodeRabbit walkthrough body, context only.

Source 4 (L117–119) is the round-1 fix landing:

```bash
gh api repos/the app repo/issues/3725/comments --paginate \
  --jq '[.[] | select(.user.type=="Bot" or (.user.login|endswith("[bot]")))
       | select(.body|test("VERDICT:|SEV:|Code Review"))] | group_by(.user.login)[] | last | .body'
```

Filtering by **shape, not name** (L114–116) means this returns the newest claude review whether it
posted as `claude[bot]` or `github-actions[bot]` — the exact dual-login trap round 1 flagged, and
the trap the host repo's CI rules file documents. `group_by | last` picks the
newest of the three. Three `SEV:` rows + `VERDICT:BLOCKING` land in the table.

### Step 5 — 1d table, and the human thread surfaced **before** fixing

> L157–158: `**Surface human-authored threads to the user NOW**, before fixing — one may say the
> code is intentional and make a bot finding moot. Never auto-resolve them.`

So T5 goes to the user here, not in Phase 5. I quote it verbatim and note it sits on
`service.py:60`, the same file as the disputed BLOCKING. Round-1 defect 4 is fixed at the
level that mattered (timing). The skill does not say whether to **wait** for the answer, and 3e
only checkboxes "surfaced" — so nothing stops me pushing on an unanswered human objection.

| # | Source | Bot? | Sev | File:Line | Issue | Thread | Action |
|---|---|---|---|---|---|---|---|
| 1 | claude | — | **BLOCKING** | service.py (~118) | `target_ref` written without tenant filter | — | **dispute** |
| 2 | claude | — | **WARNING** | service.py | new preset row has no escalation target | — | fix |
| 3 | claude | — | SUGGESTION | service.py | rename `p` → `preset` | — | fix (cheap) |
| 4 | claude (inline) | yes | ? | service.py:120 | T4 body | `PRRT_4` | ? twin of 1 |
| 5 | CodeRabbit | yes | SUGGESTION | service.py:88 | extract retry loop | `PRRT_1` | skip + reason |
| 6 | CodeRabbit | yes | **WARNING** | useThing.ts:41 | missing useEffect dep | `PRRT_2` | fix |
| 7 | CodeRabbit | yes | NITPICK | test_service.py:12 | unused import | `PRRT_3` | fix (trivial) |
| 8 | human | no | — | service.py:60 | "das war Absicht, siehe ADR" | `PRRT_5` | user |

Row 4 vs row 1: **still no dedupe rule** (round-1 defect 6). I carry both.

### Step 6 — the dispute. This is where round 2 differs

I read `apps/backend/app/services/service.py` and confirm `await apply_tenant_scope(db, uid)`
runs three lines above the write. The finding is wrong. The skill now tells me exactly what that
buys me and what it costs:

> L40–41 (good): `*"BLOCKING 'no tenant filter' — false: the call site applies`apply_tenant_scope`
> three lines up (`service.py:85`), so the query is already scoped."*`
> L42 (bad): `*"BLOCKING 'no tenant filter' — RLS handles this."* (asserts, cites nothing).`

The pair answers round 1's open question — a **file:line citation suffices; no test name is owed**.

> L44–47: `**A skipped BLOCKING needs a destination on the PR.** Your terminal report is not one:
> the reviewer re-runs on the next push, re-posts the same verdict, and the gate stays red forever.
> Post the evidence as a PR comment (`gh pr comment $PR --body …`) … and say in the report that the
> gate needs a human override.`

**Where the dispute is recorded** — two places, both instructed:

```bash
gh pr comment 3725 --body "Disputed BLOCKING (claude-review, newest review comment): \
'target_ref written without tenant filter'. False — the call site applies \
apply_tenant_scope(db, uid) at apps/backend/app/services/service.py:115, three lines above \
the write, so the transaction is already tenant-scoped. Not changing the code. \
claude-review will stay red on the re-run; this PR needs a human gate override."
```

and, because row 4 is a thread restating the same claim, a reply in T4 before resolving it
(L46: *"for a thread finding, reply in the thread before resolving it"*).

### Step 7 — 3a/3b/3c fix, validate, commit

Fix rows 2, 3, 6, 7. Validate over the changed surface (L188–193): 9 files < 50, no test-config
change → affected-only, base ref `feat/TICKET-000-integration`; `/we:static`, `/we:test`, plus any
`scripts/check-*.sh` that exist. One commit (L195–198), subject `fix: address CI and review
findings`, body carries `TICKET-000` — **derived from the branch name per L197's "the ticket key in
the body when the branch carries one"**, no `{TICKET}` placeholder to guess at any more. Verify
HEAD moved.

### Step 8 — 3d resolve bot threads, and the first real friction

```bash
REVIEW_ALLOWLIST=$(jq -r '(.review.available // ["greptile","coderabbit","claude"]) | join("|")' .weside/config.json 2>/dev/null || echo "greptile|coderabbit|claude")
```
No `.weside/config.json` in the host repo → fallback fires → `greptile|coderabbit|claude`. T1–T4
selected (all `[bot]`), T5 correctly excluded.

L200–204 now requires *"Reply with the reason before resolving a skipped one"*. T1 (refactor
suggestion, consciously skipped) and T4 (the dispute) both need a reply. **The code block at
L218–220 is still a bare `resolveReviewThread` loop with no reply call**, and the 1b query never
collected a comment id — so I have to invent the mechanics *and* re-query GitHub for the id:

```bash
# not in the skill — I derive it
gh api graphql -f query='…reviewThreads(first:100){nodes{id comments(first:1){nodes{databaseId}}}}…'
gh api repos/the app repo/pulls/comments/<databaseId>/replies -f body="Skipped: …"
```

Then the four resolve mutations.

### Step 9 — 3e hard gate, and the latent deadlock

> L225–226: `Re-run the same query with`| length` (**reusing `$REVIEW_ALLOWLIST` — do not
> redefine it**) and `exit 1`while the count is > 0.`

Followed **literally**, this is a fresh shell: `$REVIEW_ALLOWLIST` is empty, so
`test("";"i")` matches **every** login — including `maintainer`. T5 is counted, the length is 1, the
gate `exit 1`s, and no push can ever happen. The instruction contradicts the skill's own L76.
I notice and re-derive the allowlist inline; a literal follower deadlocks here. **New defect N1.**

With the allowlist correct: 0 unresolved bot threads. Checklist (L232–235):

- [x] every BLOCKING/WARNING row Fixed or Skipped-with-evidence
- [x] every skipped BLOCKING has a reply or PR comment carrying the evidence (Step 6)
- [x] 0 unresolved bot threads
- [x] human threads surfaced (T5, at Step 5)

### Step 10 — 3f / 3g push

No Alembic migration → 3f does not fire. (Its round-1 self-contradiction is gone: L240–241 now
*prefers merge over rebase* precisely because a rebase would force `--force-with-lease`, "which is
a user decision".)

3g's condition (a) — *"every check has concluded and **its failures are folded into the fix
commit**"* — is not literally true: `claude-review`'s failure is disputed, not folded in. I push
on the strength of 3e's checklist and L45's own premise that the reviewer re-runs on the next push.
Minor wording conflict, **new defect N3**.

```bash
git push
```

### Step 11 — termination

Default is one pass (L54–58). Phase 4 is opt-in, and the terminal-state list names my exact case:

> L272–273: `3. **Blocked, nothing to fix** — infrastructure red after a re-run, or **a BLOCKING
> you skipped as factually wrong: the PR needs a human.** Report it as blocked, do not keep
> pushing.`

So I do **not** enter the re-check loop, do **not** wait for `claude-review` to re-run and re-fail,
and do **not** claim the gate will go green.

**Answer to the scenario's question:** the gate does **not** go green, and round 2 *knows* it. The
dispute is written to the PR as a comment and as a reply in T4 — both readable by the human who
must override the gate. The run terminates in **terminal state 3, Blocked**, reported as such.
Round 1 ended in a silent unmergeable PR with the dispute stranded in chat; round 2 ends in a
labelled, actionable stop. That is the whole difference, and it is the right one.

### Step 12 — Phase 5 report

Findings table with Actions, four one-line fix summaries, push status, per-check gate status
(`claude-review` = fail, expected, disputed), terminal state 3, 0 unresolved bot threads, T5
verbatim (second surfacing).

---

## Round 1 verdicts

| # | Round-1 defect | Verdict | Evidence (new line numbers) |
|---|---|---|---|
| 1 | Run-scoped vars never derived; every block a fresh shell | **PARTIALLY FIXED** | L76–83 now give all five derivations and state "Each Bash call is a **fresh shell** — derive these in the same block that uses them, or re-derive"; but the 1b (L98–120), 3d (L209–221) and 3e (L225) blocks still consume `$PR`/`$OWNER`/`$REPO_NAME`/`$REVIEW_ALLOWLIST` without re-deriving, and 3d's guard still has no `else` branch. |
| 2 | Claude-comment filter greps one login | **FIXED** | L117–118 filters `select(.user.type=="Bot" or (.user.login\|endswith("[bot]")))` plus a body-shape test, with L114–116 explaining "a review action posts under its own app login OR under github-actions[bot], so filter by SHAPE, not by name". |
| 3 | Disputed BLOCKING has no destination and no terminal state | **FIXED** | L44–47 "A skipped BLOCKING needs a destination on the PR. Your terminal report is not one… Post the evidence as a PR comment (`gh pr comment $PR --body …`)"; L272–273 gives it terminal state 3 "the PR needs a human… do not keep pushing". |
| 4 | Human threads surfaced only in Phase 5, after the push | **FIXED** | L157–158 "**Surface human-authored threads to the user NOW**, before fixing — one may say the code is intentional and make a bot finding moot", now inside 1d, with a checklist item at L235. Residual: no rule to *wait* for the answer. |
| 5 | `claude-review: fail` fits neither 1c nor a stated identity with source 4 | **PARTIALLY FIXED** | 1c's useless ImportError/flaky/coverage table is gone and L134–139 classify from the log with a re-run branch; but no line anywhere says a red review gate is not a second finding — L155–156's "cleared by the re-review… or by the PR comment you left" only implies it. |
| 6 | No dedupe rule between an inline thread and the summary comment | **STILL OPEN** | 1d (L146–158) adds Source/Bot?/Severity derivation and the "—" thread-id rule but no collapse rule; T4 and SEV row 1 stay two rows. Impact is reduced, because L46's reply-before-resolve now writes the dispute into T4 anyway. |
| 7 | Bot threads resolved with no reply recording fix or skip | **PARTIALLY FIXED** | L203 "Reply with the reason before resolving a skipped one" is prose only — the loop at L218–220 is still a bare `resolveReviewThread` mutation, and *fixed* threads still get no "Fixed in \<sha\>" trace. |
| 8 | 3e-bis rebase vs 3f bare `git push` | **FIXED** | L240–241 "**Prefer merge over rebase** — a rebase of pushed commits forces `--force-with-lease`, which is a user decision, and a conflicted rebase mid-flow loses the fix commit." |
| 9 | `{TICKET}` undefined placeholder | **FIXED** | L197 "ONE commit with all fixes, subject `fix: address CI and review findings`, and the ticket key in the body when the branch carries one." |
| 10 | `--ci-only` defined only in the Rules block | **FIXED** | L24–25 defines it in the body above the workflow: "`--ci-only` narrows the run to CI: collect sources 1 and 4 only, skip thread collection and the 3d/3e thread steps, still fix and push." No `## Invocation` heading, but the behaviour is now in the steps. |
| 11 | Rules block paraphrases the steps | **FIXED** | The `## Rules` block is deleted; the file ends at Phase 5 (L280–285). |
| 12 | Single-owner violations inside and across files | **PARTIALLY FIXED** | Severity policy is now one owner (L27–47) and Phase 2 is a citation — L170 "Triage every row per the Severity policy above". Still multi-owned: human threads at L157–158, L204, L227, L235, L285; and L49–52's finish-first paragraph still restates the host repo's `.claude/rules/workflows/finish-first.md` instead of citing it. |
| 13 | No phase ends in checkable completion criteria | **PARTIALLY FIXED** | One `- [ ]` list now exists, at L232–235 (3e). Phases 1, 2, 4 and 5 still end in prose; "Phase 1 is done" has no test. |
| 14 | The one decision needing a good/bad pair does not get one | **FIXED** | L40–42 give exactly the pair, and it resolves the "do I owe a test name?" ambiguity in favour of a file:line citation. |
| 15 | Unpaired negations | **FIXED** | L95–96 "Do not special-case a reviewer by name — the repo's `review.available` list seeds the allowlist, nothing else does"; L137–138 "**re-run it**… do not change code to appease it". (New unpaired negation at L226 — see N1.) |

Score: 8 FIXED, 5 PARTIALLY, 1 STILL OPEN.

---

## New defects

### N1. 3e's "reusing `$REVIEW_ALLOWLIST` — do not redefine it" deadlocks the hard gate — **BLOCKING** (in this scenario)

> L225–226: `Re-run the same query with`| length` (reusing `$REVIEW_ALLOWLIST` — do not redefine
> it) and `exit 1`while the count is > 0.`

This instruction contradicts the skill's own L76 and is impossible to obey: 3e is a new Bash call,
so `$REVIEW_ALLOWLIST` is empty. The 3d selector is
`select(… | (endswith("[bot]")) or test("'"$REVIEW_ALLOWLIST"'";"i"))` — with an empty pattern,
`test("";"i")` is **true for every login**. T5 (`maintainer`) is therefore counted as an unresolved
"bot" thread, the count is 1, the gate `exit 1`s, and the push is unreachable for the rest of the
run. Scenario C has a human thread, so this fires here.

Smallest fix — L225–226 → *"Re-run the same query with `| length`, in one block that re-derives
`$REVIEW_ALLOWLIST` and the PR variables (L76), and `exit 1` while the count is > 0."*

### N2. The mandated thread reply has no mechanism and no collected comment id — **MAJOR**

> L203: `Reply with the reason before resolving a skipped one`
> L46: `for a thread finding, reply in the thread before resolving it`
> L103–105: `reviewThreads(first:100){nodes{ id isResolved isOutdated comments(first:1){nodes{author{login} body path line}} }}`
> L218–220: the loop — `resolveReviewThread` only.

The revision made replying a *requirement* and a 3e checklist item (L233) without shipping either
the API call or the identifier it needs. `POST /repos/{owner}/{repo}/pulls/comments/{comment_id}/replies`
needs `comment_id`, which the 1b query does not select. Every agent re-derives this differently,
which is precisely the predictability plugin-authoring L8–10 exists to protect.

Smallest fix — add `databaseId` to L105's comment selection, and one line in the L218 loop:
`gh api repos/$REPO/pulls/comments/$cid/replies -f body="Fixed in $(git rev-parse --short HEAD)"`
or `-f body="Skipped: <reason>"`.

### N3. 3g condition (a) contradicts the skip path — **MINOR**

> L247: `Push only when: (a) every check has concluded and **its failures are folded into the fix
> commit**;`

A BLOCKING skipped as factually wrong is by definition *not* folded into the fix commit, yet L45
and terminal state 3 both assume the push happens. Read literally, (a) blocks the push in exactly
the case the skill was revised to handle.

Smallest fix — (a) *"…folded into the fix commit, or skipped with evidence posted per the severity
policy."*

### N4. Terminal states are run-global but nested inside an opt-in phase — **MINOR**

> L54: `**One pass by default.**` / L256: `## Phase 4: Post-push check (opt-in, or user-budgeted)`
> L266: `**Terminal states** — every run ends in exactly one, and each is reported:`

In scenario C I never enter Phase 4, so the one paragraph that tells me how this run ends sits in a
section the default path skips. I found it only because I read the whole file first.

Smallest fix — move L266–276 out of Phase 4 into Phase 5, or into a top-level `## Terminal states`.

### N5. The good/bad skip pair is scenario C's own answer — **LOW (observation)**

L40–41's exemplar is verbatim this scenario's finding, file, and rebuttal (`apply_tenant_scope`,
`service.py:85`). It is the file's strongest teaching device and I credit it as such — but a
hardcoded repo-specific example in a deliberately reviewer-agnostic skill invites pattern-matching
over verification, and it makes any simulation using this scenario flattering. Consider a
domain-neutral example, or one sentence: *"the shape, not the subject, is what transfers."*

---

## What I needed and did not find

Strictly mechanics Opus 5 would **not** produce unprompted:

1. **How to post a thread reply, and the id it needs** (N2). The skill made the reply mandatory and
   gate-checked; it is the one step where "invent it yourself" costs a re-query and diverges per run.
2. **Whether `claude-review: fail` is a second BLOCKING row or is the same finding as source 4.**
   Left alone I collapse them, but a literal reader of L122 ("Every non-pass check is a BLOCKING
   row") opens a row with no fix and no `Action`, and 1c's re-run branch could tempt an unnecessary
   `gh run rerun`.
3. **Whether resolving T4 is legitimate while disputing its twin** — the dedupe rule (round-1
   defect 6, still open). Resolving a thread whose claim I am rejecting is a protocol choice, not a
   default.
4. **Whether an unanswered human thread blocks the push.** 3e checkboxes "surfaced", never
   "answered"; L227 states only that human threads do not block the *bot* count. With T5 sitting on
   the same file as the disputed finding, this is a real fork and the skill does not close it.

Everything else in the trace — substituting literals for shell variables, reading the code before
believing a reviewer, affected-only validation, one commit, choosing not to enter Phase 4 — I do
unprompted and do not list here.

---

## What could still be cut

285 lines. The revision cut the right 50: the Rules block, the ImportError/flaky fix table, Phase
2's restatement of the severity table, and the "green gate is the proof" blockquote that was
defect 3's root. What remains is **~25–30 lines** of duplication and no-op — noticeably less than
round 1's 45–50, and none of it now contradicts a step:

- **L60–68** (9 lines) — the ASCII workflow block restates the five phase headings verbatim, plus
  the L182 "ONE continuous flow" rule. Cut entirely or reduce to one line.
- **L54–58 vs L256–260** (~5 duplicated lines) — the one-pass default, the exception list and the
  user-budget override are stated in full twice. Keep the Phase 4 copy, cite it from L54.
- **L49–52** (4 lines) — finish-first is owned by the host repo's `.claude/rules/workflows/finish-first.md`,
  an always-loaded rule already in context when this skill runs. One citation line.
- **L15** — `**Core principle: Fix everything. Push once. No leftovers.**` restates L54 and the
  workflow block; a no-op under plugin-authoring L68–70.
- **L225–227 vs L232–235** — the prose gate and the checkbox list assert the same two conditions.
  Keep the checklist, reduce the prose to the `exit 1` mechanic.
- **L172–176** — Phase 2's "All green → STOP" restates L20–22's gate definition; two sentences, one
  owner.
- **L184–186** — 3a is a heading plus one real rule ("do not commit between fixes"); fold into 3b's
  heading.

Against that, N1–N3 need roughly **4 lines added**, and the two open ambiguities (dedupe, the
check↔comment identity) one line each. Net the file can lose ~20 lines and get *more* determinate.

---

## Grade

**4/5** — a fresh Opus agent now handles scenario C correctly: it collects the review under either
bot login, surfaces the human thread before touching code, disputes the wrong BLOCKING with a
cited file:line, writes that dispute where the PR and the human gate-approver can read it, and
stops in a named *Blocked — needs a human override* state instead of pretending a green gate is
coming. The missing point is mechanics, not judgment: 3e's "do not redefine `$REVIEW_ALLOWLIST`"
can deadlock the hard gate on this PR's human thread, and the thread reply the skill now demands
ships without an API call or the comment id to make it.
