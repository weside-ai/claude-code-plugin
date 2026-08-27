<!-- markdownlint-disable -->

# Round 2 — Scenario (c)

Table-top replay of `/we:story PROJ-940` (Opus, `acceptEdits`) against the revised
`we/skills/story/SKILL.md`. Every tool call is the one I *would* have made; nothing was
executed. `[USER]` marks invented human replies. `[UNPROMPTED]` marks a line I followed that I
would have done without the skill telling me.

---

## Trace

### Boot — Prerequisites

1. `Read("${CLAUDE_PLUGIN_ROOT}/quality/dor.md")` → the DoR checklist.
2. `Read("${CLAUDE_PLUGIN_ROOT}/references/verification.md")` → oracle ladder, receipt, "a missing verb is a bug in the CLI".
3. `Read("${CLAUDE_PLUGIN_ROOT}/references/long-running.md")` → `/loop` default, `/goal` exception, the 4+ phases trigger.
4. `Bash: git rev-parse --show-toplevel` → repo root.
5. `Read("<root>/.weside/dor.md")` → **not found**. Plugin DoR alone applies. No repo-local rows to label in the plan.
6. `Read("<root>/CONTEXT.md")` → not found. I note that a glossary entry may be offered later (Step 2).
7. `Read("<root>/.weside/config.json")` → `tools.graphify: true`. Blast radius will be graph-grounded.
8. `Read("<root>/.weside/verify.md")` → **exists**, documents exactly two verbs: `app seed --demo-tenant`, `app check tokens`. Filed for the `## Verification` block.
9. `Read("<root>/.weside/vision.md")` → not found → skip silently (skill says so; I would have skipped anyway) `[UNPROMPTED]`.

**Friction (small).** The Prerequisites block names three reads. The repo-local DoR, `CONTEXT.md`,
`config.json`, `verify.md` and `vision.md` are each introduced later, in prose, in four different
sections. Calls 5–9 are a boot sequence I assembled myself by reading the whole skill first. A
first-time reader who executes top-down issues them scattered through the session, and `verify.md`
in particular arrives only when Step 3's template is already being filled.

### Step 1 — Load

10. `ToolSearch("select:mcp__plugin_we_weside-mcp__discover_tools")` then `discover_tools(query="JIRA")` — `references/ticketing.md` puts weside MCP *ahead* of Atlassian MCP, so I must probe before I may use the connector the scenario actually gave me. → no `JIRA_*` tools.
11. `ToolSearch("select:mcp__atlassian__jira_get_issue")`.
12. `mcp__atlassian__jira_get_issue(issue_key="PROJ-940", comment_limit=50, expand="renderedFields")`

    → Summary: *Multi-language support*. Status: Backlog. Parent epic: **none**. Comments: **none**.
    Description lists six deliverables: UI string translation, language picker in settings,
    locale-aware date/number formatting, translated push notifications, translated transactional
    emails, translator hand-off workflow for the content team.

    `comments_read_through: none` `[UNPROMPTED]` — I read comments on any ticket regardless.
13. `Bash: ls docs/plans/PROJ-940-*.md` → nothing. New plan, if any.

### Step 2 — Understand (INTERACTIVE)

I do **not** open plan-mode yet. The description reads as six deliverables, not one; the first
question is the scope question, not an AC question.

14. `mcp__turbovault__semantic_search("internationalisation locale translation")` → three i18n docs
    (a locale-resolution note, a string-catalogue convention, a push-payload doc).

    **This call was premature under the skill's own rule.** Step 2's epic branch says *"Do not
    research further"* once the shape is Epic — but the branch fires *after* I have understood the
    scope, and the research instruction sits in Step 3, which I have not reached. In the replay I
    ran it because Step 2 says "read the codebase for anything discoverable there". Cheap here;
    on a heavier ticket that is a wasted deep read on work that is about to leave this skill.

15. **Question 1 to the user** (grill-style, one at a time, with my recommendation):

    > These six deliverables ship independently and each has its own user value: a language picker
    > is useful before push notifications are translated; translated transactional emails touch the
    > mail templating stack and nothing else; the translator hand-off is a workflow for the content
    > team, not for the end user at all. My recommendation: this is Epic-sized — six slices, not one
    > story. Do you agree?

    `[USER]` — *"No. It's one feature. 'The app is available in German, French and Spanish' is a
    single thing a user experiences. I don't want the overhead of an epic for one feature."*

16. **Question 2 — the reasoned second answer:**

    > The user-facing sentence is one; the delivery is not. Three tests:
    > **Separate PRs?** The string catalogue + picker land in the app bundle; the transactional
    > emails land in the mail service; the hand-off workflow lands in the content tooling. Three
    > deploy surfaces, no shared file.
    > **Separate value?** Shipping the picker + UI strings alone already makes the app German. The
    > other four are each independently releasable increments on top.
    > **Separate audience?** The translator hand-off has no end-user surface at all — its user is
    > the content team.
    > A single story with six phases would have one PR, one CI pass, one AC set spanning three
    > stacks — and the first slice could not ship until the sixth was written. That is the cost I
    > am trying to avoid, not the ceremony. Epic, with the picker + strings as story 1?

    `[USER]` — *"Alright, that's fair. Make it an epic."*

    The skill's design here works: **the branch is a question about *which kind* of big**, and the
    two-shape framing ("many independent slices" vs "one coherent change with several phases") is
    exactly the vocabulary I needed to defend the recommendation on the second pass.

17. `mcp__atlassian__jira_add_comment(issue_key="PROJ-940", body=<slice cut>)` — the branch's
    required comment:

    ```
    h3. Scope decision — Epic, not Story

    Six independently shippable slices:
    # UI string catalogue + extraction (de/fr/es)
    # Language picker in settings (depends on 1)
    # Locale-aware date/number formatting
    # Translated push notifications
    # Translated transactional emails
    # Translator hand-off workflow for the content team

    h3. Sequencing constraint
    1 before 2 (the picker needs a catalogue to switch between) and before 4-5
    (both reuse the catalogue). 3, 6 independent of all others.

    h3. Alternative rejected
    One Story with six phases. Rejected because the slices land in three deploy
    surfaces (app bundle, mail service, content tooling) with no shared file, and
    slice 1 could not ship until slice 6 was written. Overhead avoided is release
    latency, not ceremony.

    h3. No parent Saga
    Nothing under docs/plans/*-saga.md. /we:epic will ask for one.
    ```

    Wiki-markup, not Markdown — `references/ticketing.md` does not say this, and neither does the
    story skill. I know it from elsewhere; a reader of these files alone would post Markdown that
    Jira mangles.

18. Print, never invoke:

    ```
    PROJ-940 is Epic-sized — six independent slices, sequencing 1 → {2,4,5}, 3 and 6 free.
    The slice cut, the sequencing and the rejected alternative are on the ticket as a comment.
    No parent Saga exists in docs/plans/ — /we:epic will ask you for one.

    Next: /we:epic PROJ-940
    ```

19. **STOP.** No plan file, no checkpoint, no transition, no Step 5. PROJ-940 stays `Backlog`.

    The skill is silent on the ticket's *status* on this branch. Leaving it in Backlog is right —
    it is not refined — but it is my judgement, not the skill's instruction, and a reader who
    carried Step 5.3's "transition to the repo's ready state" habit across would mark an
    un-refined epic Ready.

### Mid-session pivot — PROJ-941

`[USER]` — *"Different one. I want to rework the credit ledger to double-entry — the DB schema, the
ledger service, the reconciliation job and the admin UI. Feels like four stories to me."*

The skill has just told me `⛔ STOP`, and its Modes table describes one invocation = one story.
It gives no rule for a second ticket raised in the same session. I treat the user's message as a
fresh `/we:story PROJ-941` and re-enter at Step 1 — obvious, but self-authored.

20. `mcp__atlassian__jira_get_issue(issue_key="PROJ-941", comment_limit=50)` → Summary "Rework the credit ledger to double-entry"; no comments; Backlog. `comments_read_through: none`.
21. `Bash: ls docs/plans/PROJ-941-*.md` → nothing. New plan.
22. `mcp__turbovault__semantic_search("credit ledger double-entry reconciliation")` → **two ledger ADRs**: one on the current single-column balance model and its known drift, one on the reconciliation job's tolerance window.
23. `mcp__turbovault__advanced_search(query="ledger", frontmatter_filters=[{key:"domain", value:"billing"}])` → same two, plus the admin-UI surface note.

24. **Question 1 to the user** — the same branch, other outcome:

    > This is the second shape, not the first. Four layers of *one* change: the schema, the service
    > that writes it, the job that reads it, the surface that shows it. They cannot ship
    > independently — a double-entry schema with a single-entry writer is a broken ledger, and the
    > reconciliation job reading the old balance column while the writer emits journal lines is
    > worse than either. Split into four stories and you get four PRs that are individually
    > unreleasable, four CI passes, and a window where main carries a half-migrated money path.
    > My recommendation: **one Story, phased**, dispatched with `/we:orchestrate PROJ-941`, which
    > runs each phase as its own work-chunk on one integration branch and one PR. You get the
    > per-phase separation you wanted without the release hazard. Agreed?

    `[USER]` — *"Yes, that's what I actually wanted."*

    **This is the revision's clearest win.** The two bullets in Step 2 gave me both answers from one
    rule, and the closing line — *"The urge to split into phases is the orchestrate signal, not the
    epic signal"* — is the sentence that made the recommendation say itself.

25. **Question 2:** does the backfill of historical rows have to be reversible? `[USER]` — *"Additive only. Never drop the balance column in this story."* → becomes a **Pin**.
26. **Question 3:** does the admin UI need editing, or read-only? `[USER]` — *"Read-only. Nobody hand-edits a ledger."* → narrows Phase 6, keeps the story out of an auth/mutation risk class.
27. **Question 4 (glossary):** *journal entry* vs *ledger entry* vs *posting* are used interchangeably in the two ADRs. I offer to create `CONTEXT.md` with `journal entry` canonical, `_Avoid_: ledger entry`. `[USER]` — *"Yes."* → written in Step 5.1.

### Step 3 — Blast radius, then EnterPlanMode

28. `Bash: graphify affected "LedgerService" --relation calls --depth 2` → the credit grant path, the reconciliation job, two admin API handlers, and (surprise) a webhook retry handler that also posts credits.
29. `Bash: graphify affected "reconcile_balances" --relation calls --depth 2` → the nightly job entrypoint and one admin trigger.
30. `Bash: graphify explain "CreditBalance"` → the model + every read site, which is how the admin UI files below are grounded rather than guessed.
31. `EnterPlanMode` with the plan in the next section.

### Step 4 / Step 5 (would follow on approval)

32. `ExitPlanMode` → `[USER]` approves.
33. `Bash: MAIN_WORKTREE=$(git worktree list --porcelain | awk '/^worktree /{p=$2} /^branch refs\/heads\/main$/{print p; exit}')`
34. `Write("$MAIN_WORKTREE/docs/plans/PROJ-941-story.md")` with `status: approved`; `Write("$MAIN_WORKTREE/CONTEXT.md")` with the glossary entry.
35. `Read("${CLAUDE_PLUGIN_ROOT}/references/dor-scan.md")` + run the 3-item check: GWT tokens present, Context > 50 chars, `^### Phase (\d+): ` matches six times. Pass.
36. `mcp__atlassian__jira_get_transitions(issue_key="PROJ-941")` → find the ready state.
37. `mcp__atlassian__jira_update_issue(PROJ-941, description=<minimal body>)`.
38. `mcp__atlassian__jira_transition_issue(PROJ-941, <ready>)` — **bare, no comment field** (`ticketing.md`).
39. `mcp__atlassian__jira_get_issue(PROJ-941)` → verify the status actually moved.
40. `mcp__atlassian__jira_add_comment(PROJ-941, "Refined. Resolved: 'four stories' → one phased Story (release hazard of a half-migrated money path). Parked: whether the balance column is dropped in a follow-up. Glossary: 'journal entry' canonical.")`
41. `Bash: cd "$MAIN_WORKTREE" && git add docs/plans/PROJ-941-story.md CONTEXT.md && git commit -m "docs: add PROJ-941 plan — double-entry credit ledger" && git push`

    **Defect (carried, small):** Step 5.4's snippet `git add`s only the plan file. Step 5.1 tells me
    to write `CONTEXT.md` "in Step 5.1's commit" (Step 2's wording) — but the only commit command
    in the skill does not stage it. Following the snippet literally leaves the glossary uncommitted.

42. `Bash: python3 ${CLAUDE_PLUGIN_ROOT}/scripts/orchestration.py story checkpoint PROJ-941 refined`
43. `mcp__turbovault__suggest_links(<plan path>)` → offer each `[y/n]`.
44. Final output:

    ```
    Plan saved to docs/plans/PROJ-941-story.md. /we:story DONE.
    State file: docs/plans/PROJ-941-state.md (the Lead creates it on the first run).

    Recommended next: /we:orchestrate PROJ-941   ← six phases, two parallel waves ({2,3} and {5,6}),
    coherent money-path migration — dispatch keeps this session's context clean and gives you a
    neutral review of a ledger rewrite.

    Long-running:
      /loop Run the next unmerged phase of docs/plans/PROJ-941-story.md to green, then stop.
      /goal `app check ledger --strict` exits 0 on the demo tenant and the backfilled fixture
            ← money path; wrong-about-done is expensive
      NOTE: the /goal condition is not scriptable yet — `app check ledger` does not exist. Phase 2
      ships it, and that is the first round's job.
    ```

45. **STOP.**

---

## The PROJ-941 plan I would have written

```markdown
---
type: story-plan
story: PROJ-941
epic:                     # standalone — no parent Epic
depends_on: []
comments_read_through: none
created: 2026-08-27
status: approved
parallel_groups: [[2, 3], [5, 6]]
---

# Plan: Double-entry credit ledger

## Context

The credit ledger today is a single `credit_balances.amount` column that every writer mutates in
place, and the nightly reconciliation job compares it against a replay of the purchase table with a
tolerance window — a design ADR-0031 already records as drift-prone. Drift is now visible to
support: a tenant's balance and their purchase history disagree and nothing in the system can say
which one is wrong, because no journal exists. This story replaces the model with double-entry: every
credit movement becomes a balanced pair of journal lines, the reconciliation job derives balances
from the journal instead of comparing against it, and the admin UI shows the journal read-only. The
user pushed back on splitting this into four stories; the reason it stays one is that a double-entry
schema with a single-entry writer, or a job reading the balance column while the writer emits
journal lines, is a *broken money path on main* — the layers have no independently releasable state.
The balance column is not dropped here: it stays as a shadow value the check verb compares against,
which is what makes the cutover reversible.

## Acceptance Criteria
1. **Given** a tenant with an existing balance **When** a credit is granted, spent or refunded
   **Then** the ledger writes a balanced pair of journal lines whose signed amounts sum to zero, and
   the shadow `credit_balances.amount` still agrees with the journal-derived balance.
2. **Given** any tenant's journal **When** `app check ledger` runs **Then** it exits 0 and reports
   zero unbalanced entries and zero journal-vs-shadow divergences; on an injected imbalance it exits
   non-zero and names the offending entry id.
3. **Given** historical single-entry rows written before this change **When** the backfill runs
   **Then** every historical balance equals its journal-derived balance, and the backfill is
   idempotent — a second run writes no rows.
4. **Given** the nightly reconciliation job **When** it runs on a tenant **Then** it reports
   discrepancies computed from the journal, not from the balance column, and its tolerance window is
   removed rather than widened.
5. **Given** a support admin **When** they open a tenant's ledger page in the admin UI **Then** they
   see journal entries with debit, credit and a running balance, in reverse chronological order, and
   no control that mutates a row.

## User Journey

> **This story is only DONE when the user can experience the journey end-to-end.**

1. A support admin gets a "my balance is wrong" report. 2. They open the tenant in admin UI and
click **Ledger**. 3. They see every movement as a balanced journal pair with a running balance, and
can point at the entry where the running balance and the shadow balance diverge. 4. They close the
report with the entry id, instead of escalating "the numbers disagree".

## Testing Requirements
- Unit tests for the posting engine: grant, spend, refund, partial refund, zero-amount, and the
  balanced-pair invariant as a property test.
- Unit tests for the backfill's idempotency (run twice, assert row count unchanged).
- Integration tests for the schema + posting + reconciliation path against **real Postgres**, suite
  `tests/integration/billing/test_ledger_double_entry.py` on the `app_test` database after
  `alembic upgrade head` — mocked sessions cannot see the `ON CONFLICT` arbiter on the journal's
  uniqueness constraint, which is the whole point of the idempotency AC.
- E2E: the admin UI ledger page renders and is reachable from the tenant page.

## Verification

- **Oracle:** **cli for AC1–AC4, ui for AC5.** The money invariants are machine-readable and belong
  on rung 1; AC5 is a reachability claim ("they open the ledger page") and `verification.md` is
  explicit that reachability is not provable from an endpoint. *(The template offers one Oracle
  slot; two ACs classes genuinely need two rungs — see New defects, N1.)*
- **Seed:** `app seed --demo-tenant` (fresh tenant with purchases and spends — covers AC1, AC2, AC5)
  **plus a verb that does not exist:** nothing in `.weside/verify.md` seeds *pre-migration
  single-entry* rows, which is the only state AC3 can be tested from. See Missing CLI verb.
- **Asserted:** `app check ledger --tenant <id>` exits 0, prints `unbalanced=0 divergences=0`;
  injected-imbalance run exits 2 naming the entry id. For AC5: admin UI route `/admin/tenants/:id/ledger`
  renders an a11y node labelled `Ledger` with ≥1 row carrying debit, credit and running-balance
  cells, and **no** button/input inside the table (read-only pin).
- **Not proven:** the CLI cannot show that the *nightly cron* actually fires the job (only that the
  job is correct when invoked) — owed by an ops check after deploy. The UI walkthrough cannot show
  behaviour on a 100k-entry tenant — owed by a pagination check in a follow-up.
- **Exit criterion:** `app check ledger --strict` exits 0 on both the demo tenant and the backfilled
  legacy fixture, and the admin ledger page renders for a tenant with ≥1 refund.
- **Missing CLI verb:** two.
  1. **`app check ledger [--tenant|--strict]`** — the assert verb. `.weside/verify.md` documents
     `app check tokens`, which asserts nothing about ledger balance; using it here would be a green
     receipt that cannot fail. **Ships in Phase 2** — as early as its own dependency (the Phase 1
     schema) allows, and deliberately *before* the posting engine so the engine's first commit is
     already observable.
  2. **`app seed --demo-tenant --legacy-ledger`** — seeds pre-migration single-entry rows so AC3's
     backfill has a Given. Ships in Phase 4 with the backfill it verifies; it cannot be earlier,
     because the shape it seeds is defined by the backfill's own input contract.

### Verb audit against `.weside/verify.md`

| Documented verb | Covers | Verdict |
|---|---|---|
| `app seed --demo-tenant` | Given for AC1, AC2, AC5 | Sufficient as a seed for the post-migration state; blind to AC3's legacy state |
| `app check tokens` | — | **Covers nothing in this story.** It pattern-matches the assert slot and proves nothing about ledger balance. Naming it under **Asserted:** would produce a receipt that is green by construction. |

## Technical Approach

**Patterns:** append-only `journal_entries` + `journal_lines` (entry header, N signed lines,
DB-level constraint `sum(amount) = 0` per entry); the posting engine is the only writer and every
existing caller of `LedgerService.adjust_balance` routes through it. `graphify affected
"LedgerService" --relation calls --depth 2` surfaced a **webhook retry handler** that also posts
credits — not mentioned in either ADR and not in the user's four-layer mental model; it is in
Phase 3's `Files:` because of that call, and it is the reason Phase 3 is money-class rather than
ordinary. `Files:` lists are graph-derived. Architecture refs: ADR-0031 (single-column balance
model and its drift), ADR-0042 (reconciliation tolerance window — this story removes the window).

## Implementation Phases

### Phase 1: Journal schema + additive migration
- **Goal:** `journal_entries` and `journal_lines` exist with the balanced-entry constraint; nothing
  writes to them yet; `credit_balances.amount` untouched.
- **Files:** `migrations/versions/<rev>_journal_schema.py`, `app/models/ledger.py`,
  `app/crud/ledger.py` (read helpers only), `tests/unit/models/test_ledger_models.py`
- **Risk:** migration — [additive DDL on a money table; no data movement, but it lands on the
  rolling-update window and must be forward-compatible with pods still running the old model]
- **Approach:** additive migration only, no backfill, no drop. The balanced-entry constraint is a
  deferrable CHECK over a per-entry sum so a multi-statement post inside one transaction is legal.

### Phase 2: `app check ledger` verify verb
- **Goal:** the assert half of this story's oracle exists before the behaviour it asserts.
- **Files:** `cli/commands/check.py`, `app/services/ledger_audit.py`,
  `tests/unit/cli/test_check_ledger.py`, `.weside/verify.md` (document the new verb)
- **Risk:** ordinary — [read-only; no write path, no money mutation]
- **Approach:** asserts **schema-level** invariants only — per-entry sum-to-zero, orphan lines,
  journal-derived balance vs the shadow column. It deliberately does **not** assert posting
  semantics (which credit event maps to which account pair); that is what keeps it disjoint from
  Phase 3 and safe to run concurrently with it. On an empty journal it exits 0 with `entries=0`.

### Phase 3: Posting engine — every credit movement writes a balanced pair
- **Goal:** grant, spend, refund and the webhook retry path all post journal lines, alongside the
  existing shadow write.
- **Files:** `app/services/ledger_service.py`, `app/services/posting.py` (new),
  `app/api/webhooks/credit_retry.py`, `app/services/credit_service.py`,
  `tests/unit/services/test_ledger_service.py`, `tests/unit/services/test_posting.py`,
  `tests/integration/billing/test_ledger_double_entry.py`,
  `tests/unit/api/test_credit_retry_webhook.py` (existing — its call sites break)
- **Risk:** money — [the credit write path; a wrong account pair silently mis-states every
  subsequent balance. Not for a cheap-tier worker; real-Postgres integration suite named above.]
- **Approach:** shadow write stays (Pin). The posting engine is the only caller allowed to insert
  journal rows; `adjust_balance` becomes a thin wrapper over it so no call site is left on the old
  path.

### Phase 4: Backfill historical rows + legacy seed verb
- **Goal:** every pre-existing balance has a journal history that reproduces it; AC3's Given is
  seedable.
- **Files:** `migrations/versions/<rev>_journal_backfill.py`, `app/jobs/backfill_journal.py`,
  `cli/commands/seed.py`, `tests/integration/billing/test_journal_backfill.py`,
  `.weside/verify.md`
- **Risk:** money — [rewrites history for every existing tenant; idempotency is the only thing
  between a re-run and doubled balances]
- **Approach:** batched, idempotent via a unique key on `(source_table, source_id)`, resumable.
  Verified by Phase 2's verb, which is why the verb comes first.

### Phase 5: Reconciliation job reads the journal
- **Goal:** the nightly job derives balances from the journal and the tolerance window is deleted.
- **Files:** `app/jobs/reconcile_balances.py`, `app/services/reconciliation.py`,
  `tests/unit/jobs/test_reconcile_balances.py`,
  `tests/integration/billing/test_reconciliation_journal.py`
- **Risk:** money — [the job that decides whether the books are right]
- **Approach:** replace the replay-vs-column comparison with journal-derived vs shadow-column, and
  delete `TOLERANCE_CENTS` rather than widening it (ADR-0042 is superseded — noted under
  Documentation Impact).

### Phase 6: Admin UI ledger view (read-only)
- **Goal:** a support admin can reach a tenant's journal from the tenant page.
- **Files:** `web/admin/routes/tenants/[id]/ledger.tsx`, `web/admin/components/LedgerTable.tsx`,
  `app/api/admin/ledger.py` (read endpoint), `openapi.json`, `packages/api-client/**` (generated),
  `web/admin/__tests__/LedgerTable.test.tsx`, `tests/unit/api/test_admin_ledger.py`
- **Risk:** ordinary — [read-only surface; SUPERADMIN-gated endpoint reusing the existing admin
  auth dependency, no new authorisation decision]
- **Approach:** paginated read endpoint over `journal_entries`, table with debit / credit / running
  balance. No mutating control anywhere in the table (Pin).

**Note for the Lead on `parallel_groups: [[2, 3], [5, 6]]`:** group `[2,3]` is disjoint by files
*and* by assertion scope — Phase 2 asserts schema invariants, Phase 3 defines posting semantics, and
they do not feed each other (see Phase 2's Approach). Group `[5,6]` is disjoint by files but
**mixes risk classes**: Phase 5 is money, Phase 6 is ordinary. `/we:orchestrate` Step 5.2 forbids a
cheap tier for a money chunk, so the two members of this group need different executors. The group
declaration cannot say that; this line does.

## Constraints and Pins

**Constraints:** the posting engine is the only writer of `journal_lines`; every credit path goes
through it (no second money path). Idempotency key on every backfilled and webhook-sourced entry.
Real-Postgres integration suite for anything touching `ON CONFLICT`.
**Pins:** `credit_balances.amount` is **not** dropped, and every existing reader of it keeps working
unchanged for the whole story — it is the shadow value the check verb compares against. The admin
ledger table has no mutating control. The reconciliation job's public report shape
(`{tenant_id, delta, entries}`) is unchanged so the existing alerting keeps parsing it.

## Design Decisions

| Decision | Alternatives Considered | Why This |
|---|---|---|
| One Story, six phases, one PR | Four Stories (the user's instinct) — schema / service / job / UI | Four PRs that are individually unreleasable; a window where main carries a double-entry schema with a single-entry writer. The phases give the separation; `/we:orchestrate` gives the dispatch. |
| Keep `credit_balances.amount` as a shadow column | Drop it in the same story | The shadow is the check verb's second opinion; dropping it removes the only independent oracle at exactly the moment we need one. Dropping is a follow-up, parked with the user. |
| Ship `app check ledger` in Phase 2, before the posting engine | Ship it last, with the UI | The verb is the assert half of the oracle; shipping it after the money path means Phases 3–5 land unobservable. `.weside/verify.md`'s `app check tokens` cannot substitute — it asserts nothing about balance. |
| Delete the reconciliation tolerance window | Widen it, or keep it during cutover | A tolerance window on a double-entry journal is a bug mask — the journal is either balanced or it is not. ADR-0042 is superseded, not amended. |
| Backfill as a job invoked by a migration, not inside the migration | Backfill inline in the Alembic revision | A batched, resumable, idempotent backfill cannot run inside a single migration transaction on a large tenant table without holding locks for the whole rolling update. |
| Admin UI read-only | Allow a manual correcting entry | A correcting entry is a money mutation with its own authorisation and audit story. Out of scope; the user was explicit. |

## Code Guidance

**DO:** post through `PostingEngine.post(event)` — one entry, N signed lines, sum zero, asserted in
the engine before flush. Carry the idempotency key on every entry from a retryable source. Name
things `journal entry` (see `CONTEXT.md`).
**DON'T:** write `journal_lines` from any call site other than the posting engine; add a
`if double_entry_enabled: … else: legacy…` branch (no legacy fallbacks — adapt every call site now);
widen the reconciliation tolerance to make a test pass; call the thing a "ledger entry".

## Security Review Required

**Yes** — money path plus a new admin-facing read endpoint. Two specific reads: the ledger endpoint
is tenant-scoped in its query (not only in its route), and the backfill job cannot cross tenants.

## Documentation Impact

- **Docstrings** — `PostingEngine` (the balanced-pair invariant and why the shadow column stays),
  `app/services/ledger_audit.py` (what `app check ledger` does and does not assert).
- **Architecture doc** — yes: the billing architecture doc's ledger section, because the write path
  changes shape for every credit source including the webhook retry handler.
- **ADR** — **supersede ADR-0042** (reconciliation tolerance window): removing it is hard to reverse
  and was a real trade-off. No new ADR for double-entry itself — ADR-0031 already framed the
  problem; this is its resolution and gets a superseded-by note.
- **Generated** — `openapi.json` and the TS API client (Phase 6).
- **New doc** — none. `.weside/verify.md` gains two verb rows, which is an edit, not a new doc.
```

---

## The epic hand-off for PROJ-940

**What actually crosses the boundary:**

| Artifact | Where it lands | Does `/we:epic` read it? |
|---|---|---|
| The six-slice cut | Jira comment on PROJ-940 | **No** |
| The sequencing constraint (1 → {2,4,5}) | same comment | **No** |
| The rejected alternative + reasoning | same comment | **No** |
| "No parent Saga exists" | printed to the user *and* in the comment | Only because the user reads it |
| `/we:epic PROJ-940` | printed to the user | n/a — the user retypes it |
| The three i18n docs I already found (call 14) | nowhere | **No** |

**The hand-off is lossy, and the loss is total for the reasoning.** `po-altitude.md` A1 and B1 both
say: *read the doc, read the parent doc, "fetch the **children** from the ticketing tool"*. Nothing
in either mode reads the epic ticket's **own comments**. Every sentence Step 2 required me to write
— the slice cut, the sequencing, the alternative the user rejected and why — lands in a place
`/we:epic` structurally does not look. It will re-derive the decomposition from the description
alone and can re-propose the alternative the user just rejected, because the record of that
rejection is invisible to it.

Two separable halves:

- **Read side** — `/we:epic` (via `po-altitude.md`) must fetch the target's own comments the way
  `ticketing.md` already mandates for every skill that loads a ticket. → **FORK** (`po-altitude.md`,
  not in my file list).
- **Write side** — `we/skills/story/SKILL.md` sends the reasoning to exactly one destination and
  prints only the command. It could require the slice cut to be *printed to the user in the same
  breath*, so the human carries what the tool loses. That mitigation is inside my file list. →
  **defect in this file** (N3 below).

The 6-line print I wrote in call 18 is my own repair, not the skill's instruction — the skill says
"print … `/we:epic {TICKET}`", one command.

---

## Round-1 verdict table

| # | Round-1 defect | Verdict | Evidence from this run |
|---|---|---|---|
| **D1** | "hand off to `/we:epic`" has no payload, lands on a missing parent | **FIXED** | Step 2's Epic bullet made me produce a payload I did not have to invent: at call 17 I wrote the slice cut, the sequencing constraint *and* the rejected alternative with its reasoning as a ticket comment, and at call 18 I printed the command instead of invoking it. The missing-Saga half fired too — the branch's own sentence made me say "no parent Saga exists; `/we:epic` will ask for one" in the same line, which in round 1 I had to notice myself. Where the payload then *goes* is a separate, newly-visible defect — N3. |
| **D2** | graphify block hard-codes `scripts/graphify/`; its "silently no-ops" escape hatch was false | **FIXED** | Calls 28–30 ran `graphify affected` / `graphify explain` — the installed binary, not a repo-relative wrapper — because the block is now gated on `.weside/config.json` → `tools.graphify`, which I read at call 7. The false degradation claim is gone and replaced by an *honest* fallback: `rg` plus a required sentence in the plan ("`Files:` lists are grep-derived"). I exercised the true branch and wrote the graph-derived counterpart into Technical Approach. |
| **D3** | Step 6.1 reads `~/.claude/plans/{codename}.md` — an undefined token | **FIXED** | Call 34 is a `Write` of the plan already in my context to `$MAIN_WORKTREE/docs/plans/PROJ-941-story.md`. No undefined token, no Read of a plan-mode internal. Step 5.0's `MAIN_WORKTREE` resolution is now the thing that supplies the path, and it *is* defined (call 33). |
| **D4** | ticket updated twice; the first update links a file that does not exist | **FIXED** | There is exactly one ticket touch now, and it is after the plan is on disk: calls 37–40 (description → transition → verify → comment) all happen in Step 5.3, i.e. after Step 5.1's write. Nothing in my run pointed the ticket at a nonexistent file, and an abandon at ExitPlanMode would have left PROJ-941 untouched. |
| **D5** | Step 6.3 pushes to `main` unconditionally, behind a guard that reports the wrong failure | **PARTIALLY FIXED** | The wrong-diagnosis half is fixed: Step 5.4's chain is now split so each failure carries its own message ("no worktree on main" / "commit failed (hook rewrite?)" / "committed locally, push failed (branch protection?)"), and the header says one failure mode per message. At call 41 I could have told the user the truth about any of the three. The **consent half is untouched** — I would still have pushed a commit to `main` without asking, in a workspace whose standing rule is "ask before any branch push". The skill never names branch protection or a consent gate. |
| **D6** | the `refined` checkpoint attests a DoR scan `/we:story` never runs | **FIXED** | Call 35 is now a step, not my initiative: Step 5.2 sends me to `references/dor-scan.md` and runs the three checks against the file I just wrote, *before* the checkpoint at call 42. I checked GWT tokens, Context length and six `^### Phase (\d+): ` matches. Had my ACs come out as prose bullets, the sequence would have stopped me. |
| **D7** | no mode-resolution step; a bare ticket key is unspecified | **FIXED** | I resolved `/we:story PROJ-940` at boot with no guess — the Modes table's first row now reads `/we:story {TICKET}` → refine an existing Story. In round 1 this was an inference from the key's shape; here it was a lookup. |
| **D8** | Step 4 tells the plan's *author* to read the plan | **FIXED** | No such instruction fired in my run. The consumer-side sentence is gone from the writing step; what survives in Step 3 is "Load more files than feel necessary", which is a calibration for research and correct where it stands. The re-refine case it was half-right about is now handled where it belongs — Step 1: "If `docs/plans/{TICKET}-story.md` exists, read it in full and refine **in place**". |
| **D9** | Vision Alignment unreachable from the step sequence | **FIXED** | Call 9 happened inside Step 2, because Step 2 now carries the check inline ("If `.weside/vision.md` exists, or a Companion is connected… No vision configured → skip silently"). In round 1 I fired it by judgement from a section no step referenced. |
| **D10** | the one-time vision hint has no memory store | **FIXED (by deletion)** | The hint no longer exists to be broken. In my run the absent `.weside/vision.md` produced a silent skip and no offer, so there was no "no" to remember. |
| **D11** | `docs/plan-format.md` and the skill template disagree on the plan's shape | **FORK** — and **still open** | Exercised directly: the frontmatter I wrote carries `type: story-plan`, `epic:`, `depends_on:` and `comments_read_through:`; `plan-format.md`'s frontmatter table and Full Template list none of them, and its Full Template still has no `## Verification` section at all — the section this scenario's whole verb audit lives in. `quality/dor.md`'s In-Plan checklist likewise has no Verification row. The skill's own template is now *better* than the document that calls itself "the exact format both sides depend on". Fix belongs in `docs/plan-format.md` + `we/quality/dor.md`, neither in this worker's file list. |
| **D12** | "Execute these 6 commands" is not 6 commands; "No explanations" contradicts item 6 | **FIXED** | The count claim and the "No explanations. No summaries between steps." line are both gone; the header now reads "Run these in order" over items 0–7, and item 7 is openly an output-plus-judgement block. Nothing in my run required me to discount the emphatic formatting. |

**Score:** 9 FIXED, 1 FIXED-by-deletion, 1 PARTIALLY FIXED, 1 FORK. Nothing round 1 filed is
untouched-and-owned.

---

## New defects introduced by the revision

### N1 — the `## Verification` block admits exactly one Oracle; a story's ACs can demand two — **blocking for any story with a UI surface**

> `- **Oracle:** cli | ui | substitute | not-applicable — *why this one*`

The italic *"why this one"* forecloses the plural. PROJ-941's AC1–AC4 are machine-readable money
invariants (rung 1); AC5 is *"the admin opens the ledger page and sees…"*, and
`verification.md` is explicit that **"reachability is not provable from an endpoint — an endpoint
that nothing calls answers 200 all day."** So the ACs demand two rungs, and neither file says what
to write. `verification.md`'s own steer — *"climb only as far as the ACs demand"* — reads as
picking one rung, not a set.

I resolved it by writing `**Oracle:** cli for AC1–AC4, ui for AC5` and flagging it in-line. That is
me repairing the template mid-plan. The failure mode for a reader who does not is the *bad* one:
pick `cli` because four of five ACs fit, and the reachability AC silently ships with no oracle —
which is the exact defect class `verification.md` exists to prevent.

**Smallest fix** (in `we/skills/story/SKILL.md`, so not a FORK): make the line per-AC-group —
`- **Oracle:** cli | ui | substitute | not-applicable — *which ACs, and why this rung for them*.
ACs on different rungs get one line each.`

### N2 — the block prompts for an *absent* verb and never for a *useless* one — **blocking, and it is this scenario's trap**

> `- **Missing CLI verb:** [name it if the seed needs a shell dance — and say which phase ships it…]`

The revision sharpened the scheduling half well (it made me put `app check ledger` in Phase 2,
ahead of the money path it observes, and made me *justify* why the legacy-seed verb cannot be
earlier). But the prompt only fires on **absence**. `.weside/verify.md` hands me `app check tokens`
— a verb that pattern-matches the assert slot, is documented as this repo's check verb, and proves
exactly nothing about a ledger balance. Nothing in the template asks *"does the verb you are about
to name under **Asserted:** actually falsify this AC?"*. A reader who fills `**Asserted:** app check
tokens` produces a receipt that is **green by construction** and passes the whole downstream chain:
`we:ac-reviewer` checks the receipt exists and matches, and a matching receipt for a vacuous assert
matches fine.

Round 1 named this under "What I needed and did not find"; the revision touched this exact block and
did not close it. I wrote a *Verb audit* sub-table into the plan to close it by hand.

**Smallest fix:** one clause on the `Seed:`/`Asserted:` lines — *"name the verbs from
`<repo>/.weside/verify.md` you are using and, for each AC, the verb that would go RED if the AC
broke; an AC with no such verb owes one under Missing CLI verb."*

### N3 — the epic hand-off writes its reasoning to exactly one destination, and it is the one `/we:epic` does not read — **blocking**

Detailed in *The epic hand-off* above. The read side is a FORK (`po-altitude.md` fetches children,
never the target ticket's own comments). The write side is in this file: Step 2 says *"write … as a
ticket comment, print — never invoke — `/we:epic {TICKET}`, and STOP"*. One destination, and the
human — the only party who will actually carry the decision into `/we:epic` — gets a bare command.

**Smallest fix:** *"…and print the slice cut and the sequencing constraint to the user above the
`/we:epic {TICKET}` line, not only to the ticket."* Six lines of output, and the reasoning survives
a connector that does not read comments.

### N4 — Step 5.4's `git add` cannot stage the glossary Step 5.1 tells me to write — **friction**

Step 2 says the accepted `CONTEXT.md` entry is written "in Step 5.1's commit"; Step 5.1 repeats
"Write the accepted `CONTEXT.md` glossary entry, if any, now." Step 5.4's snippet then runs
`git add docs/plans/{TICKET}-story.md` — only. Executed literally (call 41), my agreed glossary entry
stays uncommitted and un-pushed, and the next session's `CONTEXT.md` read finds nothing. I staged it
anyway; the snippet did not.

**Smallest fix:** `git add docs/plans/{TICKET}-story.md CONTEXT.md 2>/dev/null || git add docs/plans/{TICKET}-story.md`, or simply name both files.

### N5 — *(withdrawn after checking the consumer)* mixed risk classes inside a `parallel_groups` group

I drafted this as a finding — group `[5, 6]` passes both of the independence check's tests (disjoint
files, no ordering dependency) while mixing a `money` phase with an `ordinary` one, and I wrote a
prose note to the Lead about it in the plan. Re-reading `/we:orchestrate` Step 5.2 kills it: risk
class and executor are assigned **per chunk** ("Risk class per chunk… A critical chunk is never on a
cheap model tier"), and a group is a concurrency declaration, not an executor declaration. A Lead
reading `[[5,6]]` correctly puts Phase 5 on Opus/Codex/itself and Phase 6 wherever, and dispatches
both in one message. **No defect.** My in-plan note to the Lead is harmless but redundant — the
consumer already does the right thing without it.

### N6 — Prerequisites names three reads; the boot actually needs eight — **friction**

Prerequisites lists `dor.md`, `verification.md`, `long-running.md`. The run also required
`<repo>/.weside/dor.md` (a paragraph below Prerequisites), `CONTEXT.md` (the next paragraph),
`.weside/config.json` (Step 3, mid-prose), `.weside/vision.md` (Step 2) and — the sharp one —
**`<repo>/.weside/verify.md`, which is named only inside a blockquote *inside the plan template***.
By the time a top-down reader reaches it they are already filling the section it feeds. I assembled
calls 5–9 as a boot block only because I read the whole file first. Round 1 filed "when to read
`.weside/verify.md`" under *What I needed and did not find*; the revision moved it into the template
blockquote, which is later, not earlier.

**Smallest fix:** add the four repo files to the Prerequisites block as conditional reads.

### N7 — Step 2's Epic branch says "do not research further" one step *before* the research instruction — **minor**

Step 2 tells me to "read the codebase for anything discoverable there"; the Epic bullet then says
"Do not research further"; the actual architecture research lives in Step 3. At call 14 I had
already spent a TurboVault semantic search on PROJ-940 before the branch fired, and those three i18n
docs went nowhere. Cheap here, not cheap on a ticket that needs a deep read to size.

**Smallest fix:** make it forward-looking — *"→ Epic-sized. Skip Step 3 entirely."*

### N8 — the Epic branch leaves the ticket's status unspecified — **minor**

The Story path ends by transitioning to the repo's ready state (Step 5.3). The Epic path stops at
Step 2 and says nothing about status, so PROJ-940 stayed `Backlog` on my judgement. That is the
right answer — an un-decomposed epic is not ready — but `workflows/orchestration.md`'s rule that
"a status is a claim about the work" makes it worth one clause rather than an inference.

---

## Still cuttable

**The epic-vs-phased rule is now stated the right number of times — this is the revision's best
structural change.** Round 1 counted **four** statements (Refine Step 2, Execution Surface bullet 3,
the Rules block, Create Mode step 2) and recommended keeping only the one carrying the *test*. The
revision kept exactly that one. What remains is: the full two-shape test in Step 2; a one-line
epigram closing it (*"The urge to split into phases is the orchestrate signal, not the epic
signal"*); and, in Execution Surface, `"it is a coherent multi-layer/refactor/migration change"` as
one of four **recommend-orchestrate** criteria — which is a surface criterion, not a restatement of
the routing rule, and earns its place. The Rules-block copy and the Create-Mode copy are gone. In
the replay this showed up as the epigram doing real work at call 24: it is the sentence I reached
for, and it is one line, not a paraphrase that can drift out of sync with the test above it. Leave
it alone.

Still cuttable:

- **"Ticket is MINIMAL. Plan contains ALL details."** — still twice inside this file (the Your
  Output table's "Ticket (minimal)" cell, then the bold line under it), plus twice in `dor.md` and
  once in `ticket-briefs.md`. The table cell says it structurally; cut the bold line.
- **"Anything beyond this template follows `references/ticket-briefs.md` for *wording*"** — round 1
  flagged it and it survived. The template it qualifies is two headings and a link; "anything beyond
  it" is a case the same paragraph forbids. `ticket-briefs.md` is a real reference for
  `/we:triage` and worker briefs; this pointer aims it at nothing. Cut.
- **"Load more files than feel necessary; a wrong assumption costs more than a wide read."** —
  borderline. It changed no behaviour of mine (I would read wide regardless), but it is a
  calibration instruction rather than a restatement, and it is one clause. Keep.
- **`references/ticketing.md`'s weside-MCP-first probe** — call 10 was a `discover_tools` round trip
  that could only ever fail in a session where Atlassian MCP is the connected connector. Not this
  file's to fix (FORK), but it is a real tax on every `/we:story` boot.

---

## Grade

**4/5.** (Round 1 was 3/5.) Every defect round 1 could fix inside this file list is fixed, and the
fixes are the *behaviour-changing* kind rather than the wording kind: the epic hand-off now has a
payload I was made to write rather than one I had to invent; the graphify block ran the installed
tool and made me stamp "graph-derived" on the `Files:` lists; the DoR scan fired before the
checkpoint that attests it; the ticket was touched once, after the plan existed; and the four-way
restatement of the routing rule collapsed to one test plus one epigram that earned its line at the
exact moment the user pushed back. The scenario's central question is answered cleanly and twice
over — PROJ-940 left for `/we:epic` with its reasoning written down, PROJ-941 stayed one Story with
six phases, `parallel_groups: [[2,3],[5,6]]`, per-phase risk classes and a verification block that
scheduled its own missing verb into Phase 2 ahead of the money path it observes.

The missing fifth point is that the sharpest judgement of the round is still unaided, and it is the
same one as last time. `.weside/verify.md` handed me a seed that works and `app check tokens`, a
verb that looks exactly like an assert and falsifies nothing about a ledger; the revision rewrote
the very block where that decision is made and still prompts only for the verb that is *absent*, not
for whether the verb that is *present* could ever go red (N2). Next to it sits an Oracle field that
structurally cannot express a story with both money invariants and a UI reachability AC (N1), and an
epic hand-off whose reasoning is written to the one place the receiving skill does not read (N3,
read side FORK). Those three are the difference between a skill that produces a correct plan when a
careful reader runs it and one that produces a correct plan regardless — which is what the fifth
point is for.
