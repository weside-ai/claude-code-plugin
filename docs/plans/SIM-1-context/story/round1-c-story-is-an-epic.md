<!-- markdownlint-disable -->

# Round 1 — Scenario (c): epic-sized story vs. coherent phased story

## Trace

### Boot

1. `Read("${CLAUDE_PLUGIN_ROOT}/quality/dor.md")` — per Prerequisites.
2. `Read("${CLAUDE_PLUGIN_ROOT}/references/verification.md")` — per Prerequisites.
3. `Read("${CLAUDE_PLUGIN_ROOT}/references/long-running.md")` — per Prerequisites.
4. `Bash("git rev-parse --show-toplevel")` → repo root.
5. `Bash("ls -a <root>/.weside/")` → `verify.md`, `config.json`. No `dor.md` → per the
   "Repo-local DoR additions" paragraph I silently proceed with plugin defaults. Nothing to say
   to the user. ✔ executed as written.
6. Model check: session is Opus → the "Run this on Opus" paragraph produces no output. I do
   **not** read `references/worker-dispatch.md` (it is only cited as the rule's home, and the
   rule's outcome is already decided). **[UNPROMPTED skip]**
7. `.weside/` exists → no `/we:setup` suggestion.

**Where I was left guessing (1):** the skill has three modes (Refine / Create / Design Session)
and **no mode-resolution step**. `/we:story PROJ-940` is a bare ticket key; "Create Mode" is
documented as `/we:story "Feature description"` and "Refine Mode" as "Refine Existing Story"
without saying what the argument looks like. `references/po-altitude.md` — which this skill does
*not* load — has exactly the Smart-Mode resolution table that is missing here. I inferred Refine
Mode from the key shape. **[UNPROMPTED]**

### PROJ-940 — load and scope-check

8. Ticketing detection per `references/ticketing.md` priority order. weside MCP is connected, so
   priority 1 applies before Atlassian:
   `mcp__plugin_we_weside-mcp__discover_tools(query="JIRA")`
   → assume it answers with `JIRA_GET_ISSUE` present.
9. `mcp__plugin_we_weside-mcp__get_tool_schema(name="JIRA_GET_ISSUE")` — ticketing.md explicitly
   tells me to inspect the schema to find the comment field/expand.
10. `mcp__plugin_we_weside-mcp__execute_tool(name="JIRA_GET_ISSUE", arguments='{"issue_key":"PROJ-940","expand":"renderedFields,comment"}')`
    → Summary "Multi-language support"; the six-deliverable description; Status Backlog; **no
    comments**, so the "newest wins" conflict rule is inert this round.
11. `Bash("ls docs/plans/PROJ-940-story.md docs/plans/PROJ-940-plan.md 2>/dev/null")` → neither
    exists. (Step 1 says "Check if plan already exists" without naming the legacy fallback; I
    checked both because `plan-format.md` documents the `-plan.md` back-compat. **[UNPROMPTED]**)
12. `Bash("ls <root>/CONTEXT.md <root>/.weside/vision.md 2>/dev/null")` → I invent: neither
    exists. So Vision Alignment = Level 1 (skip), and the "Training on the Job" one-time hint is
    due. **Guessing (2):** the Vision Alignment and Training sections sit *below* Step 6 in the
    file and no step references them, so nothing tells me *when* they run. I fired the hint at
    the top of Step 2 because that is the only place it is not disruptive.

13. **Step 2, the scope check.** I read the description against the two-shape test in Step 2:
    six deliverables — UI string extraction/translation, a settings language picker, locale
    date/number formatting, push notification translation, transactional email translation, and
    a translator hand-off workflow for the content team. Test applied literally:
    - *separate user value?* Yes for at least four of six — a user gets value from a language
      picker with German strings before any email is translated.
    - *separate PRs?* Yes — push and email are different subsystems with different deploy trains.
    - *does phase N feed phase N+1?* Only string-extraction → everything else; the rest are
      mutually independent.
    - one item ("translator hand-off workflow") is not code at all; it is a process the content
      team runs.
    → **many independent slices → `/we:epic`.** The skill routed me correctly, and it did so on
    the *first* read of Step 2, before any research. Good sequencing: the escalation happens
    before I spend the user's tokens on a plan.

14. Grill-style, one question, with my recommendation attached (as Step 2 demands):

    > **Me:** This is six shippable things, not one. The language picker + German strings is a
    > story someone can use next week; translated transactional emails is a separate system with
    > its own deploy. My recommendation: make PROJ-940 an Epic and cut the first story as
    > "German UI strings + settings language picker". Shall I hand this to `/we:epic`?

    **[USER]** *"can't we just do it as one story?"*

15. Second, reasoned answer (the skill gives me the argument, so this is on-script):

    > **Me:** We could, and it would break in a specific way. The test isn't size, it's shape.
    > A refactor or a migration is one coherent change with phases — every phase serves one AC
    > set and nothing ships until the last one lands; that stays a story and `/we:orchestrate`
    > runs the phases. This isn't that. Translated push notifications and a translator hand-off
    > workflow share nothing but the word "language": different subsystems, different reviewers,
    > different risk, and each has its own user-visible value. As one story it produces one
    > PR nobody can review, one AC list of ~20 items, and a DoD that can't be met incrementally
    > — and the moment we cut French to ship German, we'd be renegotiating scope inside the
    > build, which the DoR explicitly forbids. As an epic we get six tickets that can be
    > sequenced, dropped or parallelised, and story one ships in a week.

    **[USER]** *"ok, epic it is."*

16. **Step 2 ends here and the skill stops helping.** It says "hand off to `/we:epic`" and
    nothing else — see § *The epic hand-off* and Defect D1.
    Tool call I would make: **none the skill names.** What I actually did:
    `mcp__plugin_we_weside-mcp__execute_tool(name="JIRA_ADD_COMMENT", arguments='{"issue_key":"PROJ-940","body":"<the six-slice cut + the coherence argument + the recommended first story>"}')`
    — improvised, so the reasoning survives to the `/we:epic` session. **[UNPROMPTED]**
17. Printed hand-off line (improvised wording, the skill supplies none):
    `Next: /we:epic PROJ-940 — six independent slices; my cut and the reasoning are in the
    ticket's newest comment.`
18. I did **not** run TurboVault or graphify for PROJ-940 — those live in Step 4, which the
    escalation never reaches. Nothing researched is lost, because nothing was researched. What
    *is* lost is step 13–15: the slice cut and the argument the user paid a pushback round for.

### PROJ-941 — raised mid-session

19. **Guessing (3):** the skill has no mechanic for "the user raises a second ticket mid-run".
    Design Session Mode's "If multiple Stories emerge, work them one at a time" is the nearest
    line and it is in the wrong mode. I improvised: closed 940 cleanly, then restarted Refine
    Mode at Step 1 for PROJ-941.
20. `execute_tool(name="JIRA_GET_ISSUE", arguments='{"issue_key":"PROJ-941","expand":"renderedFields,comment"}')`
    → "Rework the credit ledger to double-entry"; touches DB schema, ledger service,
    reconciliation job, admin UI. No comments.
21. `Bash("ls docs/plans/PROJ-941-*.md 2>/dev/null")` → none.
22. **Step 2 scope check, second shape.** User's instinct is "that's four stories". Test:
    - *separate user value per slice?* No. A double-entry schema nobody posts to is worth
      nothing; a service writing balanced entries with a reconciliation job that still reads the
      old model is a half-migration sitting in main.
    - *does phase N feed phase N+1?* Yes, 1→2 and 2→{3,4}.
    → **one coherent change, phased. Stays a Story.** Exactly the second bullet of Step 2, and
    the "if you catch yourself wanting to split into phases, that is the orchestrate signal" line
    is the sentence I quoted back to the user. The skill earned its keep here.
23. Grill round, ~5 questions, each with a recommendation. Condensed, decisions recorded:
    - Backfill strategy → **[USER]** dual-write window rejected; one-shot backfill inside the
      migration, ledger read-only for the window.
    - Does the old single-entry table stay? → **[USER]** no. (Matches the repo's own
      "no legacy fallbacks" stance; and `development-principles.md`'s "moving a field is not done
      while its old home still type-checks" — dropped in the same PR.)
    - Money precision → **[USER]** integer minor units, no floats, unchanged.
    - Admin UI scope → **[USER]** read-only entry browser; no manual journal posting.
    - Offer to record "posting", "journal entry", "leg" in `CONTEXT.md` → **[USER]** no
      CONTEXT.md yet, skip. (Step 2 tells me to offer; it does not tell me to create the file.)

24. **Step 4 — Create Plan (EnterPlanMode).**
    `EnterPlanMode()`
25. `Bash("ls <root>/CONTEXT.md")` → absent → glossary paragraph no-ops.
26. `mcp__turbovault__semantic_search(query="credit ledger double-entry accounting reconciliation")`
    → 2 ADRs (`ADR-0031 money is integer minor units`, `ADR-0047 ledger is append-only`).
27. `mcp__turbovault__advanced_search(query="ledger", frontmatter_filters=[{"key":"domain","value":"billing"}])`
    → the same 2 ADRs + a billing overview.
28. `Read(<each of the 3>)` — "read the top 3-5 results".
29. `Bash("python3 scripts/graphify/check.py --build-if-missing")` — **this is where the skill
    breaks**, see Defect D2. `scripts/graphify/` is a weside-core path shipped in a
    stack-agnostic plugin. In this repo it does not exist; `python3` exits 2 with
    `can't open file`. The skill promised "silently no-ops when graphify is not installed".
    I improvised: `Bash("command -v graphify && graphify explain CreditLedger --relation calls")`.
30. `Bash("python3 scripts/graphify/query.py 'CreditLedger LedgerEntry ReconciliationJob' --top 10")`
    — same failure, same improvisation. I derived the `Files:` lists from `rg` instead:
    `Grep(pattern="class (CreditLedger|LedgerEntry)", output_mode="files_with_matches")`.
31. `Read("<root>/.weside/verify.md")` → documents `app seed --demo-tenant` and
    `app check tokens`. **Guessing (4):** no step in the skill tells me to read this file. The
    plan template's `## Verification` block mentions it in a blockquote aside
    ("commands live in `<repo>/.weside/verify.md`") and `references/verification.md` names it
    under *Repo recipes*, but the Prerequisites `Read()` block does not list it and Step 4 never
    mentions it. I read it because I had already read `verification.md`. A session that skipped
    that reference writes a `## Verification` section out of thin air. **[UNPROMPTED]**
32. Assessed the two verbs against the ACs: `app seed --demo-tenant` is a usable **Seed**.
    `app check tokens` is **not** a ledger assertion — it checks auth tokens. So the repo has a
    seed and no assert. Per `verification.md` § *a missing verb is a bug in the CLI*, the verb
    ships **in this wave** → it becomes Phase 3 of the plan, deliberately placed *before* the
    two phases it has to verify.
33. Wrote the plan (below). `parallel_groups` decided by the independence check, not by feel:
    phases 4 and 5 both consume phase 2's read API, touch disjoint files, and neither feeds the
    other → `[[4, 5]]`.
34. `ExitPlanMode(plan=<the plan below>)` → **[USER]** approved.

### Step 6 — the six commands

35. `Read("~/.claude/plans/{codename}.md")` — **cannot be executed as written**, see Defect D3.
    I never learn `{codename}`. I improvised `Bash("ls -t ~/.claude/plans/ | head -3")` and, on
    ambiguity, wrote from the plan already in my context.
36. `Bash("git worktree list --porcelain | awk '/^worktree /{p=$2} /^branch refs\\/heads\\/main$/{print p; exit}'")`
    → `MAIN_WORKTREE`.
37. `Write(file_path="<MAIN_WORKTREE>/docs/plans/PROJ-941-story.md", content=<plan, status: approved>)`
38. `execute_tool(name="JIRA_UPDATE_ISSUE", arguments='{"issue_key":"PROJ-941","fields":{"description":"<minimal template>"}}')`
    — note this is the *second* time the skill has told me to update this ticket (Step 3 already
    did), see Defect D4. I ran it once, here, because Step 3's version would have linked a file
    that did not yet exist.
39. `Bash('cd "$MAIN_WORKTREE" && [ "$(git branch --show-current)" = "main" ] && git add docs/plans/PROJ-941-story.md && git commit -m "docs: add PROJ-941 plan — Double-entry credit ledger" && git push || echo "WARN: ..."')`
    — I would **stop and ask** before running this, see Defect D5 (unconditional push to a
    protected `main`). **[deviation, flagged to user]**
40. `Bash("python3 ${CLAUDE_PLUGIN_ROOT}/scripts/orchestration.py story checkpoint PROJ-941 refined")`
    — I write `refined` without ever having run the DoR scan the checkpoint is supposed to
    attest, see Defect D6.
41. `mcp__turbovault__suggest_links(path="docs/plans/PROJ-941-story.md")` → offered 3 links
    `[y/n]` each. **[USER]** y, y, n.
42. Final output, Execution Surface heuristic applied (5 phases, non-empty `parallel_groups`,
    coherent multi-layer migration → dispatch, and the *split instinct* bullet says explicitly
    not to escalate this one to an epic):

    ```
    Plan saved to docs/plans/PROJ-941-story.md. /we:story DONE.

    Recommended next: /we:orchestrate PROJ-941   ← 5 phases, wave [4,5] parallel; coherent
    money-path migration — dispatch keeps this session's context clean and the review neutral.
    (or /we:orchestrate PROJ-941 --solo if you'd rather run it inline.)

    Long-running:
      /loop Run the next unbuilt phase of docs/plans/PROJ-941-story.md, verify with
            `app ledger verify --tenant demo`, update docs/plans/PROJ-941-state.md.
      /goal `app ledger verify --tenant demo` exits 0 on a demo tenant AND every legacy
            single-entry row has a matching balanced journal entry     ← money path;
            wrong-about-done here is a silent balance error
    ```

    The `/goal` line is justified against `long-running.md`'s bar: money path **and** a migration
    with a hard finish line. The oracle is scriptable **only after Phase 3** — I said so in one
    line, per Step 6's "if the oracle is not scriptable yet, say so".
43. **STOP.** No branch, no code, no `/we:orchestrate`.

---

## The PROJ-941 plan I would have written

```markdown
---
type: story-plan
story: PROJ-941
created: 2026-08-27
status: approved
parallel_groups: [[4, 5]]
---

# Plan: Rework the credit ledger to double-entry

## Context

The credit ledger records each movement as a single row with a signed amount, so there is no
structural guarantee that money leaving one place arrives anywhere. Three balance discrepancies
this quarter were only found because a customer complained, and reconciliation today compares a
number against itself. We are moving to double-entry: every posting writes two or more balanced
legs and the sum of a journal entry is zero by construction, so a discrepancy becomes impossible
to write rather than hard to find. The user's instinct was to cut this into four stories — DB,
service, job, admin UI — but none of those four is shippable alone: a schema nobody posts to is
worth nothing, and a service writing balanced entries beside a reconciliation job still reading
the old model is a half-migration living in main. It stays one story with five phases and one PR.
Two constraints are not visible in the code: money stays integer minor units (ADR-0031, no
floats anywhere on this path), and the old single-entry table is **deleted in this PR**, not left
behind — a second owner of the same fact is how the discrepancies started. There is no dual-write
window; the ledger goes read-only for the backfill.

## Acceptance Criteria

1. **Given** a demo tenant seeded with credit movements **When** an operator runs
   `app ledger verify --tenant demo` **Then** it exits 0 and reports every journal entry
   summing to zero across its legs.
2. **Given** a credit purchase **When** the ledger service posts it **Then** two balanced legs
   are written in one transaction, and a posting whose legs do not sum to zero is rejected before
   commit with a `LedgerImbalance` error.
3. **Given** the pre-migration single-entry rows **When** the migration runs **Then** every
   historical movement has a matching balanced journal entry and the per-tenant closing balance
   is byte-identical to the pre-migration balance.
4. **Given** the reconciliation job runs on a tenant with a deliberately corrupted leg
   **When** it completes **Then** it reports that tenant as unbalanced and exits non-zero,
   rather than reporting success.
5. **Given** a support operator on the admin UI **When** they open a tenant's page and click
   **Ledger** **Then** they see that tenant's journal entries with their legs and a running
   balance, newest first, and the page states the balance is derived from the legs.
6. **Given** any surface still importing the old single-entry model **When** the PR's type check
   runs **Then** it fails — the old model no longer exists.

## User Journey

1. A support operator opens a tenant whose balance a customer disputes, in the admin UI.
2. They click **Ledger** in the tenant's sidebar.
3. They see each journal entry expanded into its legs, with a running balance beside it, and can
   point at the exact entry where the balance moved.
4. They copy the entry id into the ticket and close the page; no shell access was needed.

## Testing Requirements

- Unit: the posting API's imbalance rejection (legs summing to non-zero, single-leg posting,
  zero-amount leg); integer-minor-unit arithmetic at the rounding boundaries.
- Integration (real Postgres, `alembic upgrade head` on the test DB first): the backfill
  migration on a fixture with every historical movement type, asserting per-tenant closing
  balances match pre-migration; the `ON CONFLICT` behaviour of the posting insert under
  concurrent postings to one tenant.
- Integration: the reconciliation job against both a clean and a deliberately corrupted tenant —
  the corrupted arm is the one that matters; a job that only ever passes proves nothing.
- E2E / UI: the admin ledger route renders legs and a running balance for a seeded tenant.
- Edge cases: a tenant with zero movements; a refund reversing a posting; a movement recorded
  during the read-only backfill window (must be rejected, not queued).

## Verification

> How this will be observed running — not inferred from green tests.

- **Oracle:** cli (ACs 1–4, 6) + ui (AC 5) — the ledger is machine-readable so the CLI carries
  most of it, but AC 5 says the operator can *see* and *reach* the page, and reachability is not
  provable from an endpoint.
- **Seed:** `app seed --demo-tenant` (from `.weside/verify.md`), then
  `app ledger verify --tenant demo` — the second verb **does not exist yet and ships in Phase 3**.
- **Assert:**
  - `app ledger verify --tenant demo` → exit 0; JSON output `{"entries": N, "imbalanced": 0}`.
  - Corrupted arm: hand-corrupt one leg, re-run → exit non-zero, `imbalanced: 1`. A verify that
    cannot fail is decoration.
  - Backfill: capture per-tenant balances before the migration, diff after → empty diff.
  - UI: route `/admin/tenants/<id>/ledger` renders, accessibility tree carries the label
    `Ledger` on the sidebar link and one row per journal entry with its legs.
- **Not provable here:** production data volume — the backfill is verified on demo-tenant scale
  only, and its runtime against the production row count is owed by the deploying human before
  the migration window is chosen. Nothing here proves the read-only window is short enough.
- **Missing CLI verb:** `app ledger verify --tenant <slug> [--json]`. `.weside/verify.md`
  documents `app seed --demo-tenant` and `app check tokens`; the latter checks auth tokens and is
  useless here. Phase 3 ships the verb and adds it to `.weside/verify.md` — it is what makes the
  `/loop` above honest.

## Technical Approach

**Patterns:** append-only journal (ADR-0047) — entries and legs are never updated, a correction
is a reversing entry. Money as integer minor units end to end (ADR-0031); no float ever touches
this path. The balance invariant is enforced in **two** places on purpose: a service-level check
before commit (for the readable error) and a deferred DB constraint on the entry's leg sum (for
the guarantee), because a service-only check is one raw insert away from being bypassed.
Postings go through the existing session primitive; the backfill runs inside the Alembic
revision, not as a separate script, so a failed backfill rolls the schema back with it.

## Implementation Phases

### Phase 1: Journal schema + backfill migration
- **Goal:** `journal_entries` and `journal_legs` exist, every historical single-entry row has a
  balanced counterpart, and per-tenant closing balances are unchanged.
- **Files:** `migrations/versions/<rev>_double_entry_ledger.py`, `app/models/ledger.py`,
  `tests/migrations/test_double_entry_backfill.py`
- **Approach:** new tables with a deferred CHECK on the per-entry leg sum; backfill inside the
  same revision, mapping each legacy movement type to its two-leg shape; downgrade drops the new
  tables only (the legacy table is dropped in Phase 2, so a Phase-1-only rollback is clean).

### Phase 2: Balanced posting API + delete the single-entry model
- **Goal:** all credit movement goes through a posting API that cannot write an imbalanced entry,
  and the old model is gone rather than deprecated.
- **Files:** `app/services/ledger_service.py`, `app/crud/ledger.py`, `app/models/ledger.py`,
  every caller `rg` finds for the old model, `tests/services/test_ledger_service.py`
- **Approach:** `post(tenant, legs)` validates sum-zero and non-empty, writes entry + legs in one
  transaction, raises `LedgerImbalance` otherwise. Then delete the legacy model and adapt every
  call site in this phase — no compatibility shim, no `if new_ledger:` branch.

### Phase 3: `app ledger verify` CLI verb (the oracle)
- **Goal:** the verification of phases 4 and 5 is scriptable before those phases are built.
- **Files:** `app/cli/ledger.py`, `tests/cli/test_ledger_verify.py`, `.weside/verify.md`
- **Approach:** `app ledger verify --tenant <slug> [--json]` walks every journal entry for the
  tenant, sums its legs, exits non-zero listing imbalanced entry ids. Machine-readable output;
  no prose parsing. Documented in `.weside/verify.md` in the same phase — a verb nobody can find
  is a transcript, not a tool.

### Phase 4: Reconciliation job on the journal
- **Goal:** the scheduled job proves balance from the legs and fails loudly when it cannot.
- **Files:** `app/jobs/ledger_reconciliation.py`, `tests/jobs/test_ledger_reconciliation.py`
- **Approach:** reuse the Phase-3 verification query, run per tenant, emit one structured record
  per tenant, fail the job on any imbalance. The corrupted-tenant test arm is mandatory.

### Phase 5: Admin ledger view
- **Goal:** a support operator can reach a tenant's journal from the tenant page.
- **Files:** `app/api/admin/ledger.py`, `admin-ui/src/pages/TenantLedger.tsx`,
  `admin-ui/src/routes.tsx`, `tests/api/admin/test_ledger.py`
- **Approach:** read-only endpoint returning entries with nested legs, newest first, paginated;
  a sidebar link from the tenant page (the link is the AC, not the endpoint). No manual posting
  from the UI — a journal entry created by clicking is an unaudited posting.

> **Independence check:** phases 1→2 are strictly ordered (schema feeds service) and 2→3 is
> ordered (the verb reads the new model). Phases 4 and 5 both consume phase 2's read API, touch
> **disjoint** files (`app/jobs/` + its test vs. `app/api/admin/` + `admin-ui/` + its test), and
> neither's output feeds the other → `parallel_groups: [[4, 5]]`. Phase 3 is deliberately *not*
> in that group even though its files are disjoint: phases 4 and 5 are verified with its verb, so
> it has an ordering dependency the file lists do not show.

## Design Decisions

| Decision | Alternatives Considered | Why This |
|---|---|---|
| One story, five phases | Four stories under an epic (the user's instinct) | No slice has independent user value; a schema nobody posts to and a job reading the old model are half-migrations. One coherent change → `/we:orchestrate` Mode B, not `/we:epic`. |
| One-shot backfill inside the migration, ledger read-only | Dual-write window with a cutover flag | Dual-write means two owners of the same fact for the length of the window — the exact condition that produced the discrepancies. Read-only for minutes beats correct-ish for a week. |
| Delete the single-entry model in the same PR | Keep it, deprecated, drop next quarter | A schema default left behind is a second owner and one path silently serves it while every file still looks correct. AC 6 makes the deletion type-checked. |
| Balance enforced in service **and** DB constraint | Service check only | A service check is one raw insert away from being bypassed; the constraint is the guarantee, the service check is the readable error. |
| Admin UI read-only | Allow manual journal entries for support | A posting created by clicking is unaudited money movement. Out of scope, and named as out of scope so nobody adds it. |
| Ship `app ledger verify` in this wave | Verify with a psql snippet in the PR body | `verification.md`: a missing verb is a bug in the CLI. Transcripts rot; the `/loop` needs it to be honest. |

## Code Guidance

**DO:** post through `LedgerService.post()`; integer minor units everywhere; corrections as
reversing entries; the backfill inside the Alembic revision; the reconciliation test's corrupted
arm.
**DON'T:** write `journal_legs` directly from feature code; `float`/`Decimal`-to-float anywhere
on this path; UPDATE or DELETE a journal row; a `if double_entry_enabled:` branch; leave the
legacy model importable.

## Security Review Required

Yes — money path. Tenant isolation on the new tables and on the admin read endpoint must be
proven, not assumed: the admin ledger endpoint is the classic place a `where tenant_id =` goes
missing, and the reconciliation job iterates tenants with elevated scope by construction.

## Documentation Impact

- **Docstrings** — `LedgerService.post()` carries the balance invariant and names the test that
  pins it; `app/models/ledger.py` carries the entry/leg relationship.
- **Architecture doc** — the billing overview's ledger section: single-entry → double-entry, the
  reconciliation contract.
- **ADR** — no new ADR. ADR-0047 (append-only) is being *upheld*, not revisited, and ADR-0031
  is unchanged. A new ADR here would restate two existing ones.
- **Generated** — OpenAPI + the admin TS client (Phase 5's endpoint).
- **New doc** — none.
```

---

## The epic hand-off for PROJ-940

**What the skill tells me to hand over:** nothing. Both statements of the rule end at the verb —
Step 2 says *"→ genuinely Epic-sized → hand off to `/we:epic`"*, Create Mode says
*"many independent slices → hand off to `/we:epic`"*. No payload, no format, no destination
file, no invocation string.

**What I improvised passing:**

1. The invocation `/we:epic PROJ-940`, printed, not invoked.
2. A Jira comment on PROJ-940 carrying: the six-slice cut with the independence verdict per
   slice, the sequencing constraint (string extraction gates the other five), the note that the
   translator hand-off is a process not code, the recommended first story, and the user's
   pushback + the argument that resolved it.

**What is lost even so:**

- **The user's decision.** The user rejected "one story" and accepted "epic" *for a reason*. In a
  fresh `/we:epic` session that reason is gone; the first thing an Epic Refine does is walk its
  frame questions, and "why is this an epic and not a story?" is exactly the question that gets
  re-litigated. `programme-discipline.md` § 1 has a name for this — *decisions locked, do not
  re-litigate* — and a home for it (the state file), and `/we:story` writes neither.
- **The slice cut.** My six-slice decomposition is the single most valuable artifact of the
  round, and `/we:epic` Mode C step 2 will walk the frame and re-derive it from scratch. My
  Jira comment is a workaround, not a mechanic: `references/ticket-briefs.md` governs ticket
  *bodies*, and nothing tells `/we:epic` to read comments-as-input from a story escalation.
- **Nothing else, because nothing else existed.** The escalation fires in Step 2, before Step 4's
  TurboVault and graphify research — so the three i18n docs TurboVault would have returned were
  never fetched. That ordering is correct and worth keeping.

**And the hand-off lands somewhere it cannot stand:** `/we:epic` resolves PROJ-940 → no doc on
disk → **Mode C (Create)**, whose step 1 is *"Locate the parent doc. If it is missing, tell the
user..."*. There is no Saga. Worse, the epic doc path is `docs/plans/<saga>-<epic>-epic.md` and
the Jira-grouping convention prefixes the epic title with a saga slug — neither has a defined
value for an epic that arrived from a story escalation with no saga above it. `/we:story` routes
me to a door that opens onto a missing parent.

---

## Conformance checklist

| Skill instruction | Followed? | Note |
|---|---|---|
| Prerequisites: read dor.md / verification.md / long-running.md | ✅ | 3 reads |
| Repo-local `.weside/dor.md` additive check | ✅ | Absent → silent, as specified |
| "Run this on Opus" | ✅ (no-op) | Already Opus |
| `.weside/` exists → no `/we:setup` nudge | ✅ | |
| Mode resolution | ⚠️ improvised | No resolution step exists (D7) |
| Step 1: fetch ticket **with comments** | ✅ | Both tickets; none had comments |
| Step 1: check plan exists | ✅ | Also checked legacy `-plan.md` **[UNPROMPTED]** |
| Step 2: grill-style, one question at a time, recommendation attached | ✅ | 1 round on 940, 5 on 941 |
| Step 2: brainstorming-first if vague | ➖ | Neither ticket was vague on intent |
| Step 2: offer CONTEXT.md glossary entry | ✅ | Offered, declined |
| Step 2: **which kind of big** scope test | ✅ ✅ | Routed 940→epic, 941→story. **The core test passes.** |
| Step 3: update ticket MINIMAL | ⚠️ deferred | Ran once at Step 6.2 instead (D4) |
| Step 4: CONTEXT.md glossary | ✅ (absent) | |
| Step 4: TurboVault semantic_search + advanced_search | ✅ | 2 ADRs + overview |
| Step 4: graphify blast radius | ❌ **not executable** | Path does not exist (D2); improvised `rg` |
| Step 4: "read the plan and the files it names in full" | ❌ n/a | There is no plan to read at Step 4 (D8) |
| Step 4: Session Context → plan Context + Design Decisions | ✅ | 6-row table |
| Step 4: plan template incl. `## Verification` | ✅ | Filled from `.weside/verify.md` |
| Step 4: `parallel_groups` independence check | ✅ | `[[4,5]]`, reasoned in-plan |
| Step 4: per-phase concrete `**Files:**` | ✅ | Derived by `rg`, not graphify |
| Step 5: ExitPlanMode | ✅ | |
| Step 6.1: read `~/.claude/plans/{codename}.md` | ❌ **not executable** | `{codename}` unresolvable (D3) |
| Step 6.1: write to main worktree | ✅ | Resolved via `git worktree list` |
| Step 6.2: update ticket | ✅ | |
| Step 6.3: commit + **push** to main | ⚠️ gated on user | Unconditional push to protected main (D5) |
| Step 6.4: checkpoint `refined` | ✅ mechanically | Attests a scan never run (D6) |
| Step 6.5: `suggest_links` | ✅ | 3 offered |
| Step 6.6: execution-surface recommendation | ✅ | dispatch, phases named, wave named |
| Step 6.6: long-running block | ✅ | `/loop` + a justified `/goal` |
| Step 6.6: oracle scriptable before printing | ✅ | Said so: scriptable only after Phase 3 |
| ⛔ STOP after Step 6 | ✅ | |
| Rules: `epic:` frontmatter | ✅ omitted | PROJ-941 is standalone |
| Rules: `-story.md` suffix | ✅ | |
| Rules: user-visible surface owes a proof block | ✅ | AC 5 + ui oracle |
| Vision Alignment (3 levels) | ⚠️ improvised timing | Section is unreachable from the step sequence (D9) |
| Training on the Job one-time hint | ⚠️ | Fired once; no mechanic to remember a "no" (D10) |

---

## Defects

### D1 — "hand off to `/we:epic`" has no payload, and lands on a missing parent — **blocking**

> `we/skills/story/SKILL.md`:
> "- **Many independent slices** (separate features, separate user value, separate PRs) → genuinely Epic-sized → hand off to `/we:epic`."
> "2. Scope check: many independent slices → hand off to `/we:epic`; …"

Both statements end at the verb. The round's entire output — the slice cut, the sequencing
constraint, the user's rejected alternative and the reasoning that convinced them — has nowhere
to go, and `/we:epic` Mode C (`we/references/po-altitude.md`) opens with *"Locate the parent doc.
If it is missing, tell the user…"* plus a doc path (`docs/plans/<saga>-<epic>-epic.md`) and a
title convention that both require a saga slug PROJ-940 does not have. The escalation is a
dead-end door.

**Smallest fix:** replace the bare verb in Refine Step 2 with a two-line hand-off:

```markdown
→ Epic-sized. Do not research further. Write the slice cut, the sequencing constraint and
the decision (incl. the alternative the user rejected and why) as a comment on the ticket,
then print — never invoke — `/we:epic {TICKET}` and STOP. If no Saga exists, say so in the
same line: `/we:epic` will ask for one.
```

### D2 — the graphify block cannot run outside weside-core, and its escape hatch is wrong — **blocking**

> `we/skills/story/SKILL.md`:
> "```bash
> python3 scripts/graphify/check.py --build-if-missing
> python3 scripts/graphify/query.py "<story key identifiers>" --top 10
> ```"
> "`check.py --build-if-missing` builds the graph if absent (~30 s, silently no-ops when graphify is not installed)."

`scripts/graphify/` is a repo-relative path from one specific project, hard-coded into a
stack-agnostic plugin. The world state says "graphify is installed" — the *tool*; nothing says
this repo carries those wrapper scripts, and most repos will not. `python3` on a missing file
exits 2 with `can't open file`, which is not "silently no-ops"; the promised graceful degradation
is a claim about a script that isn't there. The block then feeds the two things the plan depends
on most (`**Files:**` lists and `parallel_groups`).

**Smallest fix:** gate it and name the fallback in the same breath:

```bash
# only if the repo ships them (weside-core: scripts/graphify/); else use `rg` on the
# identifiers and say in the plan that Files: lists are grep-derived
[ -f scripts/graphify/query.py ] && python3 scripts/graphify/query.py "<identifiers>" --top 10
```

### D3 — Step 6.1 reads a file whose name the skill never resolves — **blocking**

> `we/skills/story/SKILL.md`:
> "1. **Save plan:** Read approved plan from `~/.claude/plans/{codename}.md`."

`{codename}` is never defined, never emitted by any earlier step, and never passed back by
`ExitPlanMode`. The step cannot be executed as written. It also contradicts the Rules block —

> "Ticket stays MINIMAL; the plan carries ALL detail. Save it to `docs/plans/{TICKET}-story.md` via Write() — `~/.claude/plans/` is NOT permanent."

— which correctly describes a `Write()` of the plan already in context. The Read is a
superstition about plan-mode internals.

**Smallest fix:** delete the Read. `"1. **Save plan:** Write the approved plan to
docs/plans/{TICKET}-story.md in the project's main worktree, frontmatter status: approved."`

### D4 — the ticket is updated twice, and the first update links a file that does not exist — **friction**

> `we/skills/story/SKILL.md`:
> "### Step 3: Update Ticket (MINIMAL)
> ```markdown
> ## Plan
> Implementation Plan: docs/plans/{TICKET}-story.md
> ```"

and later

> "2. **Update ticket:** If ticket exists → update description with plan link."

Step 3 runs before Step 4 writes the plan, so its "Implementation Plan:" line points at nothing
for the whole duration of the plan-mode session — and if the user abandons at ExitPlanMode, the
ticket is left permanently pointing at a file that will never exist. Step 6.2 then does the same
write again.

**Smallest fix:** cut Step 3 to the user-story sentence only and move the plan link entirely to
Step 6.2, or delete Step 3 and renumber. I would delete it: Step 6.2 already covers both the
"ticket exists" and "no ticket" cases.

### D5 — Step 6.3 pushes to `main` unconditionally — **blocking**

> `we/skills/story/SKILL.md`:
> "   cd "$MAIN_WORKTREE" && \
>    [ "$(git branch --show-current)" = "main" ] && \
>    git add … && git commit … && \
>    git push || echo "WARN: main worktree not on main branch — plan saved but not committed. Commit manually.""

Two problems in four lines. (a) The guard only checks *which branch* — it does not check whether
pushing to main is allowed, and in this very workspace `main` is protected and the standing rule
is "require explicit user instruction before pushing to `main`". The skill's own
`po-altitude.md` sibling makes the same call deliberately ("ALWAYS commit the doc directly to
main"), so this is a considered convention, but it is asserted without a consent gate. (b) The
`&&`/`||` chain attaches one error message to five different failures: if `git push` fails
(protection, no upstream, network) the user is told *"main worktree not on main branch — plan
saved but not committed"*, which is false on both clauses. A wrong diagnosis costs more than no
diagnosis.

**Smallest fix:** split the chain and tell the truth per failure —

```bash
cd "$MAIN_WORKTREE" || exit
[ "$(git branch --show-current)" = "main" ] || { echo "WARN: main worktree not on main — plan saved, not committed."; exit; }
git add docs/plans/{TICKET}-story.md && git commit -m "docs: add {TICKET} plan — {Title}" || { echo "WARN: commit failed — plan saved, commit by hand."; exit; }
git push || echo "WARN: committed locally, push failed (branch protection?) — push or open a PR by hand."
```

### D6 — the `refined` checkpoint attests a scan `/we:story` never runs — **friction**

> `we/skills/story/SKILL.md`:
> "4. **Checkpoint:** `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/orchestration.py story checkpoint {TICKET} refined`"

`we/skills/orchestrate/SKILL.md` defines what that value means downstream:

> "The `refined` checkpoint means the plan passes `references/dor-scan.md` — the same three checks the CLI computes; write it now, whoever wrote the plan."

`/we:story` writes `refined` after ExitPlanMode without ever running the three-check scan
(GWT ACs · Context > 50 chars · at least one `### Phase` header). A plan whose ACs came out as
prose bullets gets stamped `refined` and enters orchestrate's DEVELOP lane. `dor-scan.md` exists
in `we/references/` and is never read by this skill.

**Smallest fix:** one line before the checkpoint — `"Run the 3-check scan in
references/dor-scan.md against the file you just wrote; fix and rewrite before checkpointing."`

### D7 — no mode-resolution step — **friction**

> `we/skills/story/SKILL.md`:
> "## Refine Mode: Refine Existing Story" / "Trigger: `/we:story "Feature description"`" / "Trigger: `/we:story` (no argument)"

Only two of three modes state a trigger, and neither states what a bare ticket key means. The
sibling PO skills load `references/po-altitude.md`, which has a two-step Smart-Mode resolution
table for exactly this; `/we:story` neither loads it nor duplicates it. I guessed. A different
session could reasonably read `/we:story PROJ-940` as Create Mode with a terse description.

**Smallest fix:** add a trigger line to Refine Mode: `"Trigger: `/we:story {TICKET-KEY}` — an
argument that resolves to an existing ticket, a branch key, or an existing plan file."`

### D8 — Step 4 tells the plan's *author* to read the plan — **no-op / misplaced**

> `we/skills/story/SKILL.md`:
> "**Read the plan and the files it names in full.** A partially-read plan produces a partially-built story, and the sections you skip are the ones carrying the constraint."

Step 4 is where the plan is *written*. There is no plan to read and no `Files:` list to read
from — those are outputs of this step. The paragraph is a consumer-side instruction (it belongs
in `/we:orchestrate` and `/we:develop`, where both already say it) that migrated into the
producer. In a *re*-refine of an existing plan it would be right, but Step 1 already covers that
case with "Check if plan already exists".

**Smallest fix:** delete it here, or move it into Step 1 conditioned on the plan existing.

### D9 — Vision Alignment and Training on the Job are unreachable from the step sequence — **friction**

> `we/skills/story/SKILL.md`:
> "## Vision Alignment (3 Levels)" … "## Training on the Job" … "On first `/we:story` without vision:"

Both sections sit below Step 6 and below Create/Design-Session Mode. No numbered step references
either. A session executing Steps 1–6 in order never runs the vision check at all — and the
DoR's own checklist has a "Vision Alignment (optional)" row, so the check is expected to have
happened. I fired it at Step 2 by judgement.

**Smallest fix:** one line in Refine Step 2: `"Vision check: if `.weside/vision.md` or a
Companion is connected, check the story against it here (see § Vision Alignment)."`

### D10 — the one-time hint has no memory — **no-op**

> `we/skills/story/SKILL.md`:
> "One-time hint. If user says no → never ask again."

Nothing is named as the place the "no" is recorded — not `.weside/config.json`, not a memory
file. Across sessions the skill has no way to honour this, so it either asks every time (breaking
its own promise) or the line is decoration.

**Smallest fix:** name the store — `"record the answer as `vision_hint_declined: true` in
`.weside/config.json`"` — or cut the sentence.

### D11 — `plan-format.md` and the skill template disagree on the plan's shape — **friction**

`docs/plan-format.md`'s frontmatter table and Full Template omit `epic:`, omit `type:
story-plan`, and omit the entire **`## Verification`** section. The skill's template has all
three, and the Rules block calls `epic:` load-bearing:

> `we/skills/story/SKILL.md`: "ALWAYS set the `epic:` frontmatter field when the story belongs to an Epic — `/we:orchestrate`'s ready-set filters stories by it; a missing `epic:` makes the story invisible to orchestration."

`docs/plan-format.md` announces itself as *"the exact format both sides depend on. Changes here
are versioned"* — so the authoritative contract is the one missing the field that makes a story
visible to the consumer, and missing the section the verification gate reads. `quality/dor.md`'s
"In Plan" checklist is a third voice with no Verification row either.

**Smallest fix:** add `epic:`, `type:`, and `## Verification` to `plan-format.md`'s frontmatter
table and Full Template, and a Verification row to `dor.md`'s In-Plan checklist. One template,
three files pointing at it.

### D12 — "Execute these 6 commands" is not 6 commands — **no-op**

> `we/skills/story/SKILL.md`: "**Execute these 6 commands IN ORDER. No explanations. No summaries between steps.**"

Item 5 is explicitly optional ("Skip silently without TurboVault") and item 6 is an output block
containing a judgement call (the Execution-Surface heuristic) plus a conditional long-running
block — the opposite of a command. The "no explanations" imperative also directly contradicts
item 6, which is nothing but explanation. Harmless, but it trains a reader to discount the
emphatic formatting elsewhere in the file.

**Smallest fix:** "Execute steps 1–4 in order without narrating them, then emit the Step-6
output block."

---

## The three-places question

It is four places, not three. The rule is stated in Refine Step 2, in the Execution Surface
heuristic, in the Rules block, **and** in Create Mode step 2.

1. **Refine Step 2** — the only one that gives me a *test* rather than a verdict. It names both
   shapes, gives the discriminators (separate user value, separate PRs / phase N feeds N+1), and
   supplies the argument I needed when the user pushed back ("splitting a coherent change into N
   stories multiplies QS overhead the work doesn't need"). It also sits at the decision point:
   the moment the work first feels too big, before any research is spent.
2. **Execution Surface bullet 3** — its first half is genuinely its own point (*the split
   instinct is the signal → recommend orchestrate*), which belongs in a section about choosing
   a surface. Its second half ("do NOT escalate to `/we:epic` for a *single coherent* change —
   epics are for many independent slices") is a compressed restatement of Step 2, and it is the
   half most likely to drift, because it is the version that omits the test.
3. **Rules block** — a bare restatement that ends by pointing at the other two: *"(Refine Mode
   Step 2 + Execution Surface are the spec)"*. It disclaims its own authority. It is the
   textbook no-op: it cannot be followed on its own, it changes no behaviour, and it exists
   only to be seen.
4. **Create Mode step 2** — a one-line restatement, also with a see-also pointer.

**If only one survives: Refine Step 2.** It is the only statement that is *executable* —
it can be applied by someone who has not read the other three, because it carries the
discriminating test and not just the conclusion. Both of the others are recognisable as
paraphrases *of it*, which is the drift risk: the day someone sharpens the test (say, adds "does
each slice have its own deploy train?"), three copies quietly keep asserting the old one.

This is redundancy, not reinforcement, and the tell is what all four copies leave out: not one
of them says what to *hand over* to `/we:epic` (D1). Four statements of the decision, zero
statements of the mechanic. The reinforcement is spent on the half I would have got right
unaided.

Concretely I would: keep Refine Step 2 in full (and add the hand-off payload to it); in Execution
Surface, cut the second half of bullet 3 to `"— that is the orchestrate signal (Refine Step 2)"`;
delete the Rules bullet outright; cut Create Mode step 2 to `"2. Scope check — Refine Mode Step 2."`

---

## What I needed and did not find

- **The hand-off payload for `/we:epic`.** The single largest gap. Covered in D1.
- **What to do when the escalated ticket has no Saga.** `/we:epic`'s Create mode wants a parent
  doc and the epic path needs a saga slug. `/we:story` sends me there with neither.
- **When to read `.weside/verify.md`.** The `## Verification` section is mandatory in the
  template and its content is repo-specific, but no step says to read the repo recipe. I only
  got there because `verification.md` was in Prerequisites. A missing-recipe path is specified
  in `verification.md`; the *present*-recipe path is not.
- **Whether an existing verb is good enough.** `.weside/verify.md` gave me a seed and an assert
  verb that was irrelevant (`app check tokens`). Deciding "this repo has a seed but no oracle,
  so the story must ship a verb" was the sharpest judgement of the round and nothing in the skill
  prompts it — `verification.md` says a missing verb ships in the same wave, but nothing tells me
  to *audit the listed verbs against my ACs* before concluding one is missing.
- **What "one at a time" means for a second ticket raised mid-session.** Only Design Session Mode
  mentions it, in the wrong mode.
- **Mode resolution for a bare ticket key.** D7.
- **Whether Step 6.3's push is permitted here.** No consent gate, no reference to the repo's
  branch protection. D5.

---

## Cuttable — lines I obeyed without needing to be told

> "Research codebase thoroughly, then create detailed plan."

Contentless. The next 60 lines specify the research; this sentence adds an adverb.

> "explore the codebase instead of asking whenever the answer is discoverable there"

I would not ask a human a question I can answer with `rg`. This is the definition of the job.

> "Read the top 3-5 results to understand existing patterns, primitives, and ADRs that apply."

Having run the search, reading the results is not a decision. (The *second* half — "Reference
them in the plan's Technical Approach section" — is worth keeping; that one is a placement
instruction.)

> "**Read the plan and the files it names in full.** … Load more files than feel necessary — a wrong assumption costs more than a wide read."

Cuttable *and* wrong here — see D8. There is no plan at Step 4.

> "**Ticket is MINIMAL. Plan contains ALL details.**"

Stated four times: the Your-Output table's caption, this bold line, Step 3's heading, the first
Rules bullet — plus twice more in `quality/dor.md`. Once is enough; the table already says it.

> "⛔ **STOP after step 6. No implementation. No /we:orchestrate. No branch. No code.**"

and

> "⛔ NEVER implement, create branches, write code, or auto-continue to `/we:orchestrate` — after Step 6, STOP IMMEDIATELY. Story + Plan is the whole job; the user invokes the next surface."

The same prohibition twice, ~90 lines apart, in the same emphatic register. Keep the Step-6 one
(it is at the point of temptation), cut the Rules one.

> "| "Feature exists" | No access path | Add "via [button/menu/route]" |
> | "Shows X" | How to open? | Add entry point |
> | "Implemented" | Too vague | Specify user action |"

The Red Flags table is three restatements of the formula three lines above it ("User Action +
Entry Point + Outcome"). The formula and the Dark-Mode good/bad pair carry it; the table is
padding.

> "No explanations. No summaries between steps."

Contradicted by step 6 of the six, which is entirely explanation (D12).

> "**Blocked (<n>):** …" — n/a here, but the same class:
> "Anything beyond this template follows `${CLAUDE_PLUGIN_ROOT}/references/ticket-briefs.md`"

If the ticket is MINIMAL and the template is two headings, "anything beyond this template" is by
construction almost nothing — the pointer is real but it is aimed at a case the same paragraph
forbids.

---

## Grade

**3/5.** The scenario's central test — does the skill route an epic-shaped "story" out and keep a
coherent phased one in? — the skill passes, and passes well: Refine Step 2's two-shape question
is genuinely good writing, it fires at the right moment (before Step 4 spends research on work
that is about to be handed away), and it handed me the exact argument I needed when the user
pushed back on "epic" the first time. PROJ-941 stayed one story with five phases, a reasoned
`parallel_groups: [[4,5]]`, and a `## Verification` block that caught the real thing — that the
repo's two documented verbs contain a usable seed and no usable oracle, so the story owes a CLI
verb it now ships in Phase 3. That is the skill working.

What costs it two points is that the routing decision is stated four times and the *mechanic* it
implies is stated zero times: "hand off to `/we:epic`" with no payload, into a Create mode that
opens by asking for a parent that does not exist, dropping the slice cut and the user's own
pushback-and-acceptance on the floor. Around that sit three lines that cannot be executed as
written (`{codename}`, the two hard-coded `scripts/graphify/` paths), one that pushes to a
protected `main` behind a guard that then reports the wrong failure, one that stamps a `refined`
checkpoint attesting a DoR scan this skill never runs, a ticket updated twice with the first
update linking a file that does not exist yet, and a plan template whose own cross-skill contract
document is missing the `epic:` field and the entire Verification section. The judgement in this
skill is better than its mechanics; shortening it should cut the fourfold rule and the Red Flags
table, and spend the space on the hand-off it never specifies.
