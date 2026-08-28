<!-- markdownlint-disable -->

# Round 2 — Scenario (d): story → orchestrate hand-off

Table-top. Nothing was executed; every tool call below is traced, not run. The plan in
§2 exists only inside this report — Step 5.1 was **not** performed on disk.

## Act 1 trace

I am `/we:story PROJ-1207`.

**Prerequisites**

1. `Read("${CLAUDE_PLUGIN_ROOT}/quality/dor.md")` → the checklist. Note the In-Plan rows I
   owe: Context, GWT ACs, User Journey, Design Decisions, Testing Requirements, Technical
   Approach, Glossary vocabulary, Security Review, Code Guidance, Documentation Impact.
2. `Read("${CLAUDE_PLUGIN_ROOT}/references/verification.md")` → oracle ladder, receipt shape.
3. `Read("${CLAUDE_PLUGIN_ROOT}/references/long-running.md")` → the `/loop` trigger is
   structural: **4+ phases**, or non-empty `depends_on:`, or the user says they will be away.
4. `Bash: git rev-parse --show-toplevel` → `/home/user/proj`.
5. `Read("/home/user/proj/.weside/dor.md")` → the plugin rows **plus one repo row**:
   *"names the rollback step"*. Per Prerequisites this row owes "its own labelled line in the
   plan (`**<Row name>:** …`)".
6. `Read("/home/user/proj/CONTEXT.md")` → **does not exist**. Glossary offer is live for Step 2.
7. `Read("/home/user/proj/.weside/config.json")` → `{"tools": {"graphify": true}}`. No
   `test_discipline`, no `execution.default`, no `review.cross`, no `verification.required`.
8. `Read("/home/user/proj/.weside/verify.md")` → verbs `app seed --tenant <id>`,
   `app check webhooks`.

**Step 1 — Load**

9. `mcp__atlassian__jira_get_issue("PROJ-1207")` (with comments) → summary, description,
   parent `PROJ-1200`, one comment id **10442** from the tech lead, 2 days old. Newest
   comment id → `comments_read_through: 10442`.
10. `Glob("docs/plans/PROJ-1207*.md")` → no hit. New plan, not a refine.
11. `Glob("docs/plans/PROJ-1200*")` → no epic plan file on disk. (I note this; I do not
    create one — Epic altitude is `/we:epic`.)

Token picked once: **`PROJ-1207`** — plan file, frontmatter `story:`, checkpoint, branch.

**Step 2 — Understand (INTERACTIVE, grill-style, one question at a time)**

12. `Read("/home/user/proj/.weside/vision.md")` → absent → skip silently (no tension line).
13. `Grep(pattern="webhook", include="*.py", path="api/app")` → `api/app/services/webhook_dispatcher.py`,
    `api/app/models/webhook.py` (`WebhookDelivery`, statuses `pending|sent|failed`),
    `api/app/api/admin/webhooks.py`.
14. `Read("api/app/services/webhook_dispatcher.py")` → single-shot POST, marks `failed`, no retry.
15. `Read("api/app/models/webhook.py")` → `WebhookDelivery` has `id`, `endpoint_id`, `payload`,
    `status`, `created_at`. No attempt history anywhere.
16. `Grep(pattern="check webhooks|def check", path="cli")` → `cli/app/commands/check.py` has a
    `webhooks` subcommand that today only pings endpoint reachability.

> **Q1** — Backoff schedule? Recommendation: 1m · 5m · 25m · 2h · 10h · 24h, dead-letter on
> the 6th failed attempt (matches the lead's "dead-letter after 6").
> **[USER]** "Yes. Six attempts total including the first."
>
> **Q2** — What enforces "one in-flight attempt per delivery id"? Recommendation: a Postgres
> row lock (`SELECT … FOR UPDATE SKIP LOCKED` on the delivery row) rather than a Redis lock —
> the scheduler already has the session, and one fewer dependency in the fan-out path.
> **[USER]** "Postgres. We have Redis but I don't want the retry path depending on it."
>
> **Q3** — Dead-letter UI: read-only list, or list + manual requeue? Recommendation: read-only
> list this story; requeue is its own decision (does it reset the counter?).
> **[USER]** "Read-only list. Requeue later."
>
> **Q4** — Parked, recorded as such in the ticket comment: does a future manual requeue reset
> the attempt counter or continue it?
>
> **Q5** (repo DoR row *names the rollback step*) — Recommendation: the migration is additive
> (new table only, no column change on `webhook_deliveries`), and the scheduler ships behind
> `WEBHOOK_RETRY_ENABLED`, default **off**; rollback = flip the flag, and the migration's
> `downgrade()` drops the table.
> **[USER]** "Flag it, default off. Ship the downgrade."
>
> **Glossary offer** — `CONTEXT.md` does not exist; may I create it with *delivery attempt*
> (one POST try, a row) vs *delivery* (the event, may have N attempts), and *dead-letter*
> (a delivery that exhausted its attempts; `_Avoid_`: "failed queue")?
> **[USER]** "Yes, create it."

Size call: this is **one coherent change with several phases**, not many independent slices →
stays a single Story with a phased plan. The urge to split is the orchestrate signal.

**Step 3 — Create Plan (EnterPlanMode)**

17. `EnterPlanMode()`.
18. TurboVault: unavailable. I print **once**: "⚠️ TurboVault unavailable — using grep
    fallback; architecture context may be incomplete. Check the MCP config."
19. `Grep(pattern="webhook|retry|backoff", include="*.md")` → `docs/architecture/outbound-events.md`.
20. `Glob("docs/architecture/**/*.md")` → three files; I read `outbound-events.md`.
21. Blast radius — `tools.graphify: true`, so identifier-style:
    `Bash: graphify affected "WebhookDelivery" --relation calls --depth 2`
    → `webhook_dispatcher.py`, `api/app/api/admin/webhooks.py`, `api/tests/unit/test_webhook_dispatcher.py`,
    `api/tests/api/test_admin_webhooks.py`.
22. `Bash: graphify affected "webhook_dispatcher.deliver" --relation calls --depth 2`
    → the events publisher `api/app/services/events.py` (read-only for us).
23. `Bash: rg -l "admin/webhooks" mobile/src` → `mobile/src/api/generated/client.ts`,
    `mobile/src/screens/admin/AdminHome.tsx`.
24. Write the plan into plan mode (the artifact in §2 below).
25. `ExitPlanMode(plan=<the file>)`.

**Step 4 — Approval**

> **[USER]** "Approved. Go."

**Step 5 — Post-approval (traced, not run)**

26. `Bash: MAIN_WORKTREE=$(git worktree list --porcelain | awk '/^worktree /{p=$2} /^branch refs\/heads\/main$/{print p; exit}')`
    → `/home/user/proj`.
27. `Write("/home/user/proj/docs/plans/PROJ-1207-story.md")` with `status: approved`.
28. `Write("/home/user/proj/CONTEXT.md")` — the three glossary terms.
29. Step 5.2 — the 3-item scan of `references/dor-scan.md` against the file I just wrote:
    (1) `Given`/`When`/`Then` present — ✓ (5 ACs); (2) Context > 50 chars — ✓ (~7 sentences);
    (3) `^### Phase [0-9]+:` — ✓ (4 headers). Pass.
30. `mcp__atlassian__jira_get_transitions("PROJ-1207")` → ready state is **"Selected for
    Development"**.
31. `mcp__atlassian__jira_transition_issue("PROJ-1207", "Selected for Development")`, then
    verify with `jira_get_issue`.
32. `mcp__atlassian__jira_update_issue("PROJ-1207", description=<minimal body>)`.
33. `mcp__atlassian__jira_add_comment("PROJ-1207", …)` — one comment: contradictions resolved
    (none — comment 10442 sharpened the description rather than contradicting it), decisions
    taken (Postgres row lock over Redis; read-only dead-letter list; flag default off),
    questions parked (requeue semantics, Q4).
34. `Bash: cd /home/user/proj && git add docs/plans/PROJ-1207-story.md CONTEXT.md && git commit -m "docs: add PROJ-1207 plan — Retry failed outbound webhooks with backoff" && git log --oneline -1`
35. `Bash: git push`
36. `Bash: python3 ${CLAUDE_PLUGIN_ROOT}/scripts/orchestration.py story checkpoint PROJ-1207 refined`
37. Vault links — TurboVault unavailable → skip silently.
38. Step 5.7 output. Execution surface: 4 real phases and a non-empty `parallel_groups` →
    **dispatched**, not `--solo`. `long-running.md` trigger fires (4 phases ≥ 4) and the
    plan's `## Verification` names a scriptable oracle *once phase 4 lands*, so I print the
    `/loop` line with that caveat:

```
Plan saved to docs/plans/PROJ-1207-story.md. /we:story DONE.
State file: docs/plans/PROJ-1207-state.md (the Lead creates it on the first run).

Recommended next: /we:orchestrate PROJ-1207   ← 4 phases; 3 and 4 parallelise after 1+2 merge
(or /we:orchestrate PROJ-1207 --solo if you'd rather run it inline.)

Long-running:
  /loop Build the next unfinished phase of PROJ-1207, then run
        `app check webhooks --json` against DEV and stop when it reports
        6 attempts recorded, one in-flight per delivery id, and the exhausted
        delivery listed as dead-lettered.

  Note: the oracle is not scriptable until phase 4 extends `app check webhooks`.
  Until then a round can only verify by SQL against the DEV database.
```

39. **STOP.** No branch, no implementation, no auto-continue.

---

## The plan file (Act 1 artifact)

Written to the SKILL.md template slot-for-slot, no improvements.

```markdown
---
type: story-plan
story: PROJ-1207
epic: PROJ-1200
depends_on: []
comments_read_through: 10442
created: 2026-08-27
status: approved
parallel_groups: [[3, 4]]
---

# Plan: Retry failed outbound webhooks with backoff

## Context

Outbound webhook deliveries are single-shot today: `webhook_dispatcher` POSTs once, marks the
row `failed`, and the event is gone. Integrators lose events over a two-minute restart on their
side, which is the support ticket we keep answering, and it is why this is now rather than
later. The tech lead pinned three things in comment 10442 that the description does not say:
retries must be idempotent, exactly one attempt may be in flight per delivery id, and a delivery
that exhausts six attempts must be dead-lettered and visible to a human in the admin UI. We
chose a Postgres row lock over a Redis lock in refinement because the retry path should not gain
a second infrastructure dependency, and because the scheduler already holds a session. The
delivery record keeps no attempt history at all, so the attempt table is the foundation
everything else reads. The whole change ships behind `WEBHOOK_RETRY_ENABLED`, default off, so
the rollback is a flag flip rather than a revert. Manual requeue from the dead-letter list is
explicitly out — we did not settle whether it resets the counter.

## Acceptance Criteria
1. **Given** an outbound delivery whose endpoint returns 500 **When** the retry scheduler runs
   **Then** a `webhook_delivery_attempts` row is written with the attempt number, the response
   status and the next scheduled time, and the delivery stays `pending`.
2. **Given** a delivery whose last attempt failed **When** the scheduler picks work **Then** the
   next attempt fires no earlier than the backoff step for that attempt number (1m, 5m, 25m, 2h,
   10h, 24h).
3. **Given** two scheduler workers running concurrently **When** both select the same delivery id
   **Then** exactly one attempt is made and the other worker skips the row.
4. **Given** a delivery that has failed six attempts **When** the scheduler evaluates it **Then**
   it is marked `dead_letter`, no further attempt is scheduled, and it appears in the admin
   dead-letter list with its endpoint, last status and attempt count.
5. **Given** a DEV instance with a seeded failing endpoint **When** an operator runs
   `app check webhooks` **Then** the output reports attempts per delivery, in-flight count and
   dead-lettered deliveries in machine-readable form.

## User Journey
> **This story is only DONE when the user can experience the journey end-to-end.**

1. An integrator's endpoint goes down for ten minutes and our events keep firing.
2. The scheduler retries each failed delivery on the backoff ladder without duplicating it.
3. The endpoint comes back and the pending deliveries succeed on their next attempt.
4. Anything that never came back lands in the admin dead-letter list, where an operator opens
   **Admin → Webhooks → Dead letter** and sees the endpoint, attempt count and last error.

## Testing Requirements
- Unit tests for the backoff schedule (attempt N → delay), the dead-letter threshold at 6, and
  the attempt-row writer.
- Integration tests for the concurrency invariant and the migration — runnable suite
  `pytest api/tests/integration/test_webhook_retry.py` against a **real Postgres**
  (`proj_test`, `alembic upgrade head` first). The SKIP LOCKED behaviour does not exist on a
  mocked session, so this suite is the only place AC 3 can be proven.
- Component test for the dead-letter list rendering an empty state and a populated state
  (`mobile/__tests__/screens/admin/DeadLetterScreen.test.tsx`).
- Unit test for the CLI verb's JSON shape.

## Verification
> How this will be observed running — not inferred from green tests. The build turns this into
> the PR's `## Verification` receipt. See `references/verification.md`; commands live in
> `<repo>/.weside/verify.md`.

- **Oracle:** cli — plus one ui pass. AC 1–3 and 5 are machine-observable against a running
  DEV instance; AC 4 says an operator *sees* the dead-letter list, and reachability is not
  provable from an endpoint, so the admin screen gets a walkthrough.
- **Seed:** `app seed --tenant dev-1` then point one seeded endpoint at a sink that returns 500,
  and run the scheduler with `WEBHOOK_RETRY_ENABLED=1`.
- **Asserted:** `app check webhooks --json` reports `attempts` per delivery ascending on the
  backoff ladder, `in_flight <= 1` per delivery id, and the exhausted delivery under
  `dead_lettered`; the admin route **Admin → Webhooks → Dead letter** renders that same delivery
  id with its endpoint and attempt count.
- **Not proven:** real-world clock drift over the 24h step (only the first three steps are
  observed inside a session), and behaviour under a partitioned database — owed by whoever runs
  the first production wave.
- **Exit criterion:** `app check webhooks --json` on DEV, after the seed above, reports six
  attempts on the failing delivery, never more than one in flight per delivery id, and that
  delivery listed as dead-lettered — and the admin dead-letter route shows it.
- **Missing CLI verb:** `app check webhooks` exists but reports endpoint reachability only; it
  must be extended to emit attempts, in-flight count and dead-letters as JSON. **Phase 4 ships
  it.** It cannot be first: the verb reads the `webhook_delivery_attempts` table (phase 1) and
  the scheduler's in-flight marker (phase 2), so there is nothing for it to report before those
  merge. Phase 4 is in the first wave that can hold it, `[[3, 4]]`.

## Technical Approach
**Patterns:** the scheduler composes the existing `webhook_dispatcher.deliver()` rather than
re-implementing the POST — retry is a scheduling concern, not a transport one. Attempt rows are
append-only; the delivery row keeps a denormalised `attempt_count` and `next_attempt_at` so the
scheduler's claim query stays a single indexed `SELECT … FOR UPDATE SKIP LOCKED`. Idempotency
comes from the claim: an attempt is written inside the same transaction that claims the row, so a
crashed worker's row is re-claimable but never doubled. Admin exposure follows the existing
`api/app/api/admin/webhooks.py` router and the generated client, not a new surface.
Architecture ref: `docs/architecture/outbound-events.md` (the at-least-once contract this makes
true for the first time). `Files:` lists are graph-derived (`graphify affected`) for the backend;
the mobile list is `rg`-derived.

## Implementation Phases

### Phase 1: Attempt table and migration
- **Goal:** `webhook_delivery_attempts` exists with its indexes, and `webhook_deliveries` carries
  `attempt_count`, `next_attempt_at` and the `dead_letter` status; up and down both run clean.
- **Files:** `api/app/models/webhook.py`, `api/migrations/versions/{rev}_webhook_delivery_attempts.py`,
  `api/tests/unit/test_webhook_models.py`, `api/tests/integration/test_webhook_retry.py` (new
  file, migration round-trip case). No generated artifact — the model is not on the API surface yet.
- **Risk:** migration — a new table plus two additive columns and one new status value on an
  existing table; not a money, auth or tenant-scoped table.
- **Approach:** additive-only. New table with `(delivery_id, attempt_no)` unique, index on
  `(status, next_attempt_at)` for the claim query. `downgrade()` drops the table and the two
  columns. No backfill: existing `failed` rows stay `failed`.

### Phase 2: Retry scheduler with backoff and the per-delivery lock
- **Goal:** a scheduler pass claims due deliveries one at a time per delivery id, retries via the
  existing dispatcher, writes the attempt row, and dead-letters at six.
- **Files:** `api/app/workers/webhook_retry.py` (new), `api/app/services/webhook_dispatcher.py`,
  `api/app/config.py` (`WEBHOOK_RETRY_ENABLED`, default false),
  `api/tests/unit/test_webhook_dispatcher.py` (existing call sites change),
  `api/tests/unit/test_webhook_backoff.py` (new),
  `api/tests/integration/test_webhook_retry.py` (concurrency case).
- **Risk:** ordinary — no money, auth or tenant-isolation path; the correctness risk is
  concurrency, which the integration suite covers.
- **Approach:** `SELECT … FROM webhook_deliveries WHERE status='pending' AND next_attempt_at <= now()
  FOR UPDATE SKIP LOCKED LIMIT n`. Attempt row and `next_attempt_at` update commit in the claim
  transaction. Backoff table is a module constant, not config.

### Phase 3: Dead-letter list in the admin UI
- **Goal:** an operator can open the dead-letter list and see every exhausted delivery.
- **Files:** `api/app/api/admin/webhooks.py`, `api/app/schemas/webhook.py`,
  `api/tests/api/test_admin_webhooks.py`, **`api/openapi.json` (regenerated)**,
  **`mobile/src/api/generated/client.ts` (regenerated from the spec)**,
  `mobile/src/screens/admin/DeadLetterScreen.tsx` (new),
  `mobile/src/screens/admin/AdminHome.tsx` (route entry),
  `mobile/__tests__/screens/admin/DeadLetterScreen.test.tsx` (new).
- **Risk:** ordinary — an admin-only read endpoint; no write, no money, no tenant widening
  (the existing admin tenant scope is reused unchanged).
- **Approach:** `GET /admin/webhooks/dead-letter` paginated, reusing the router's existing admin
  dependency. The screen is a list with an empty state; no requeue action.

### Phase 4: Extend `app check webhooks`
- **Goal:** the verification oracle exists — `app check webhooks --json` reports attempts,
  in-flight count and dead-letters.
- **Files:** `cli/app/commands/check.py`, `cli/tests/test_check_webhooks.py`,
  `.weside/verify.md` (the verb's new output documented where the next run reads it).
- **Risk:** ordinary — read-only diagnostics.
- **Approach:** one query per section against the same session the CLI already opens; `--json`
  emits a stable object (`attempts`, `in_flight`, `dead_lettered`) that a `/loop` round can
  assert on. Human-readable output stays the default.

## Constraints and Pins
**Constraints:** compose `webhook_dispatcher.deliver()` — do not re-implement the POST or its
signing. The claim query is the only concurrency primitive; no Redis, no advisory-lock helper.
Config flags go through `api/app/config.py`, not `os.environ` at the call site. The admin router's
existing auth dependency is reused as-is.
**Pins:** a delivery that succeeds on its first attempt writes exactly one attempt row and its
observable status stays `sent` — existing consumers of `WebhookDelivery.status` see no new value
until a retry actually happens. `webhook_dispatcher.deliver()`'s signature and its signing header
do not change. With `WEBHOOK_RETRY_ENABLED` off, behaviour is byte-identical to today: one POST,
`failed`, no attempt rows, no `dead_letter`.
**Names the rollback step:** revert is a flag flip — set `WEBHOOK_RETRY_ENABLED=false` and the
scheduler stops claiming; the migration's `downgrade()` drops `webhook_delivery_attempts` and the
two added columns, and is exercised up→down→up against `proj_test` before the PR.

## Design Decisions

| Decision | Alternatives Considered | Why This |
|----------|------------------------|----------|
| Postgres `FOR UPDATE SKIP LOCKED` on the delivery row | Redis `SET NX` lock keyed by delivery id; an advisory lock | The retry path gains no second infrastructure dependency, and the claim and the attempt row commit in one transaction — a Redis lock can outlive or predecease the transaction |
| Append-only attempt table + denormalised counter | attempt JSON column on the delivery row | The counter query stays indexed; the history survives a schema change and is what the dead-letter view reads |
| Dead-letter list is read-only | list + manual requeue | Requeue needs a decision we have not made (does it reset the counter?); shipping the visibility is the lead's stated need |
| Six attempts, 1m/5m/25m/2h/10h/24h | five attempts; linear backoff | Comment 10442 fixes six; the ladder covers a ~36h outage, which is the support pattern |
| Whole change behind `WEBHOOK_RETRY_ENABLED`, default off | ship on | Rollback is a flag flip rather than a revert of a migration |

## Code Guidance
**DO:** write the attempt row inside the claim transaction; keep the backoff ladder a single
module constant with the unit test reading it; reuse the admin router's auth dependency;
regenerate `openapi.json` and the mobile client in the same commit as the endpoint.
**DON'T:** don't add a Redis dependency; don't mutate `webhook_dispatcher.deliver()`'s signature;
don't backfill existing `failed` rows into the new table; don't add a requeue action; don't let
the scheduler run when the flag is off.

## Security Review Required
No — no new authentication surface, no new tenant scope, no user-supplied payload path. The new
admin endpoint reuses the existing admin dependency and returns data the operator can already see
per delivery.

## Documentation Impact
- **Docstrings** — `api/app/workers/webhook_retry.py` module docstring carries the claim/idempotency
  reasoning and the ladder; `webhook_delivery_attempts`' model docstring says why it is append-only.
- **Architecture doc** — `docs/architecture/outbound-events.md`: the at-least-once claim becomes
  true and gains a dead-letter terminal state; that section is rewritten, not appended to.
- **ADR** — no. Reversible (flag) and unsurprising.
- **Generated** — `api/openapi.json` and `mobile/src/api/generated/client.ts` regenerate in phase 3.
- **New doc** — none. `.weside/verify.md` gains the extended verb's output shape in phase 4.
```

---

## Act 2 — field-by-field consumer audit

I am a fresh Lead running `/we:orchestrate PROJ-1207`. Prerequisites:
`Read(verification.md)`, `Read(long-running.md)`, `Read(".weside/orchestrate.md")` → **absent**,
so I derive dispatch facts from `CLAUDE.md` and say so in the roll-up, and offer to write it.
Agent Teams on, session on bypass — both fine.

| Field orchestrate reads | Carried? | What I guessed / asked / derived |
|---|---|---|
| **Step 0** — target resolution (Single Story vs Epic) | **Ambiguous.** Plan carries `story: PROJ-1207` and `epic: PROJ-1200`. Step 0 wants Single Story only when "no Epic plan / **no other story shares it as `epic:`**". | Derived by hand: `ls docs/plans/PROJ-1200*` → nothing, `grep -l "epic: PROJ-1200" docs/plans/*-story.md` → only this file. So Mode B. But the plan itself asserts membership in an epic while the epic is invisible on disk, and the producer's own frontmatter comment says the field exists so "`/we:orchestrate`'s ready-set filters on it". Two readings of one field; I resolved it with a glob the plan did not ask for. |
| **Step 1/2** — `epic:` present | ✅ `epic: PROJ-1200` | Nothing guessed for the field itself. |
| **Step 1** — state-file path | **Not in the plan.** It was printed to Act-1's terminal (`State file: docs/plans/PROJ-1207-state.md`) and that scrollback is gone. | Derived from orchestrate's own rule: "`docs/plans/<primary-key>-state.md` for a single Story" → `docs/plans/PROJ-1207-state.md`. Correct by convention, not by contract. File does not exist → I write it before the first dispatch. Where it may be committed is a `.weside/orchestrate.md` fact — **absent, guessed** (same commit as the plan, on the integration branch). |
| **Step 1** — the done lens (`## Success Criteria` of the epic plan) | **No.** No epic file exists. | `epic: PROJ-1200` gave me a key, so I fetch `jira_get_issue("PROJ-1200")` and use "Webhook reliability" plus this story's 5 ACs as the frame — orchestrate's "no epic file → synthesise from the stories" path. Better than round-1's nothing, but the lens is my synthesis. |
| **Step 2** — DoR scan by hand (single-Story path, no CLI roster) | ✅ passes | `Given`/`When`/`Then` all present (5 ACs); Context 7 sentences ≫ 50 chars; four `^### Phase \d+:` headers. `story status PROJ-1207` → `refined` checkpoint already written by `/we:story`. Orchestrate says the scan is the Lead's regardless of who wrote it — I re-ran it, agreed. Git ladder: `git branch --list 'feat/PROJ-1207-*'` empty, `git worktree list` clean, no origin branch → nothing in flight. |
| **Step 2** — repo `.weside/dor.md` row ("names the rollback step") | ✅ **carried, but in a slot the template does not define.** The line reads `**Names the rollback step:** revert is a flag flip — …` | I found it by grepping the plan for the row name after reading `.weside/dor.md`. The producer's Prerequisites promise a labelled line; the template has **no section that owns it**, so the writer parked it at the end of `## Constraints and Pins`. Any other writer could equally park it under Technical Approach or Documentation Impact, and my grep would still find it — but only because I grepped the whole file rather than a named section. Approval-read passes. |
| **Step 3 signal 4** — freezes an interface others consume | **Derived.** The plan does not label anything "signal 4". | `## Constraints and Pins` names the frozen seams explicitly enough for me to decide: `webhook_dispatcher.deliver()`'s signature and signing header are pinned, and `WebhookDelivery.status` gains `dead_letter`. The new status value **is** a consumed interface — I ran `graphify affected "WebhookDelivery.status" --relation calls --depth 2` myself to find the dependents. Signal 4 fires *inside* the story (phase 1 freezes for 2–4), which the phase order and `parallel_groups` already serialize, so no `depends_on:` is owed to another story. Decision: no Decision-Queue item, but I derived that, the plan did not. |
| **Step 3 signal 5** — comments have overtaken the plan | ✅ **carried, and it worked.** `comments_read_through: 10442` | `jira_get_issue("PROJ-1207")` with comments → newest is still `10442`. Equal → the plan already answered the comments → signal 5 does not fire, `refined` stands, story goes to develop. This is the one field that turned a judgement call into a comparison. Nothing guessed. |
| **`depends_on:`** | ✅ `depends_on: []` | Empty and correct — the story depends on no other story. Note it is *story*-scoped: the real ordering here is phase 1+2 → 3+4, which lives in `parallel_groups`, not here. I did not have to guess, but I did have to know that. |
| **Step 5.2** — risk class per chunk | ✅ per phase, ❌ for the classification the step actually needs | Every phase carries `**Risk:**`. Phase 1 says `migration`, phases 2–4 say `ordinary`. Step 5.2 defines critical as "money, auth, tenant isolation, **a migration on such a table**" — so `migration` alone does not tell me the class. The plan's *why* clause saved me: "not a money, auth or tenant-scoped table". **Without that clause I would have had to open the model.** Consequence I derived: phase 1 is not critical → may run on `sonnet`; but Step 5.2 also says a migration never goes to a **detached** backend at all, so my executor pick is Agent-sonnet, not Codex. Repo risk-class file lists live in `.weside/orchestrate.md` — **absent, so nothing to check the plan's self-classification against.** |
| **Step 5.3** — per-phase `**Files:**` incl. generated artifacts | ✅ **carried well.** Phase 3 lists `api/openapi.json (regenerated)` and `mobile/src/api/generated/client.ts (regenerated from the spec)`; phase 2 lists the *existing* `test_webhook_dispatcher.py` whose call sites change. | Union/intersect for disjointness: {1} ∩ {2} = `api/tests/integration/test_webhook_retry.py` (both write cases into it) and `api/app/models/webhook.py` vs `webhook_dispatcher.py` (disjoint). {3} ∩ {4} = **∅** ✓. {3,4} ∩ {1,2} = ∅ ✓. So `[[3,4]]` holds. **One thing I had to invent:** the phase-1/phase-2 overlap on the integration test file is real and the plan does not flag it — they are serial anyway, so it costs nothing, but the plan let me discover it rather than telling me. `WORKER-REPORT.md` is not listed in any phase; for a Codex/foreign chunk I must add it as write-allowed-and-not-committed myself. |
| **Step 5.4** — `parallel_groups` semantics (barrier + ≤2 cap) | ✅ `parallel_groups: [[3, 4]]` and the producer's independence-check prose states the same barrier/cap I apply | Nothing guessed at the field. But the *contract doc* (`docs/plan-format.md` § parallel_groups) still describes a different semantics — "dispatched as concurrent sub-agents in a single `Agent()` message", no barrier, no cap. Group size is 2 so both readings dispatch identically here; a `[[3,4,5]]` would not. **FORK** — that file is outside the producer's file list. |
| **Step 5.8** — verbs the verification needs, and when they ship | ✅ **carried, and it answers the follow-up question too** | `**Missing CLI verb:**` names the extension, says phase 4 ships it, and says why it cannot be wave 0 (it reads phase-1 and phase-2 state). Step 5.8 wants such a chunk "cut in wave 0 so its PR's merge window overlaps the build" — that is impossible here and the plan told me so *before* Step 8 B, which is the whole point of the slot. What I still derived: **which repo owns the CLI.** The Files list says `cli/app/commands/check.py`, which is inside this monorepo, so there is no second PR and no "waiting on your merge in `<repo>`" state. The plan never says "same repo"; I read it off a path. |
| **Step 8 A** — "Constraints and Pins" as the conflict-resolution authority | ✅ present, and usable | Both halves are concrete enough to arbitrate a merge: the flag-off byte-identical pin and the `deliver()` signature pin are the two conflicts phases 2 and 3 could plausibly produce. Nothing guessed. |
| **Exit criterion for a `/loop` round** | ✅ **in the plan**, under `## Verification` → `**Exit criterion:**` | Someone else could run it: seed, `app check webhooks --json`, three named conditions plus the admin route. `long-running.md` demands exactly that it live in the plan and not in terminal output — it does. **But the `/loop` invocation itself, and the "not scriptable until phase 4" caveat, were printed to Act-1's terminal only.** I reconstructed the caveat from the Missing-CLI-verb line. |
| **Integration suite + database for the critical chunk** | ✅ **named** — `pytest api/tests/integration/test_webhook_retry.py` against real Postgres `proj_test`, `alembic upgrade head` first | Carried at **story level**, in `## Testing Requirements`, not per phase. The Worker-Brief's CRITICAL clause wants `{integration suite}` + `{database}` per chunk, so I mapped it myself: phase 1 (migration round-trip) and phase 2 (concurrency) both need it; phases 3 and 4 do not. The plan's per-phase Files lists happen to name the same file, which is what let me map it — a plan that named the suite only in Testing Requirements and not in a Files list would have left me guessing. |

**Confirm gate assembled from the above** — the stand, wave map (wave 0: phase 1 serial; wave 1:
phase 2 serial; wave 2: phases 3+4 concurrent, cap 2), disjointness result (∅ inside the group),
risk classes (1 migration/not-critical, 2–4 ordinary), executors (sonnet Agents throughout;
phase 1 never on a detached backend), verbs (phase 4, same repo, no second PR), Decision Queue
(two items, both mine to raise: **(a)** `.weside/orchestrate.md` is missing — may I write it?
**(b)** the parked Q4 requeue semantics is recorded in the ticket as open; it does not block).

---

## The phase-1 Worker-Brief I would send

Fields I had to **invent** are marked ⟨INVENTED⟩; fields **derived** from something the plan
does carry are marked ⟨DERIVED⟩.

```
You are worker-PROJ-1207-p1, a teammate spawned into this session's implicit team. The lead is "team-lead".

REPO: /home/user/proj. Start every bash command with `cd /home/user/proj` and confirm
`git rev-parse --show-toplevel` before any git operation.
WORKTREE: `/home/user/proj-PROJ-1207-p1`, already on branch `feat/PROJ-1207-p1`
(off `feat/PROJ-1207-integration`) and bootstrapped. `cd` there; do not call EnterWorktree.
Run: Skill(skill="develop") for PROJ-1207 --phases 1.

DEV-ONLY: implement phase 1 → fast local gates → AC-check your diff → commit → push
feat/PROJ-1207-p1 → STOP. No `gh pr create`, no CI, no ticket transition, no doc pass — the Lead
merges every branch onto feat/PROJ-1207-integration and runs ONE CI on ONE PR.

FINISH FIRST: a small finding (≤ ~30 min) on the seam you touch gets FIXED in your branch —
"pre-existing" is no deferral reason. Product decisions, money-path changes and foreign-subsystem
redesigns go back to the Lead as QUESTIONS in your report; workers never create tickets. Surface a
design fork BEFORE you pin behaviour around it.

TESTS: tests-after — write tests in the same change, after the code.        ⟨INVENTED: .weside/config.json
  has no `test_discipline`; the brief's own fallback rule chose this, the plan says nothing.⟩
No implementation-coupled tests, no tautological assertions, mock at system boundaries only.

FAST GATES: unit + fast smoke only. A test that needs a running database, queue or network
service belongs to the Lead's integration run — skip it and say so in your report. No
yarn/npm install, jest, tsc in a fresh worktree; report the skipped frontend validation.

  This chunk is a MIGRATION but NOT a critical chunk (the table is not money/auth/tenant-scoped
  — the plan's Risk line says so).                                          ⟨DERIVED from `**Risk:** migration
  — … not a money, auth or tenant-scoped table`⟩
  Even so, do NOT report done on unit tests alone: run
    `alembic upgrade head && pytest api/tests/integration/test_webhook_retry.py`
  against `proj_test`, and append the run's last 20 lines to WORKER-REPORT.md.
                                                                            ⟨DERIVED: suite + DB come from
  `## Testing Requirements` at story level; I mapped them to this phase myself. The up→down→up
  round-trip stays MINE — Step 8 B says a migration chunk gets it from the Lead.⟩

SCOPE — touch only:
  api/app/models/webhook.py
  api/migrations/versions/{rev}_webhook_delivery_attempts.py
  api/tests/unit/test_webhook_models.py
  api/tests/integration/test_webhook_retry.py   (create; phase 2 will add cases — keep your
                                                 case in its own class)     ⟨INVENTED: the plan does not
                                                 flag that phases 1 and 2 share this file.⟩
Do not touch api/app/services/webhook_dispatcher.py — that is phase 2.

CONSTRAINTS (verbatim from the plan's Constraints and Pins):
  Config flags go through api/app/config.py, not os.environ at the call site.
  Additive-only migration: new table + two columns + one new status value. No backfill.
  downgrade() drops the table AND the two columns.
PINS:
  With WEBHOOK_RETRY_ENABLED off, behaviour is byte-identical to today.
  A delivery that succeeds first time writes exactly one attempt row; observable status stays `sent`.

REPO CONSTRAINTS: none recorded — this repo has no .weside/orchestrate.md. No generated
artifact is produced by this phase (the plan's Files list says so explicitly). Gate baselines:
unknown; if a gate prints a pinned total, stop and ask rather than editing the baseline.
                                                                            ⟨INVENTED wholesale: the
  absent .weside/orchestrate.md is orchestrate's own dependency, not the plan's.⟩

REPORT FILE: write WORKER-REPORT.md in your worktree root before you stop — what you built,
skipped, could not settle. It is not part of the change: do not `git add` it.

REPORTING IS NOT OPTIONAL: your plain-text output is INVISIBLE to the lead. Send EXACTLY ONE message:
  SendMessage(to="team-lead", summary="worker-PROJ-1207-p1 done|blocked",
              message="<branch | commits: N | gates: … | AC-check: … | skipped: … | blockers: …>")
NEVER report done without a pushed branch.
```

Score for the brief: **4 invented fields** (test discipline, the shared-test-file warning, the
repo-constraints block, gate baselines), **2 derived** (risk-criticality, suite→phase mapping).
Round 1's brief had, by my count of what a plan can supply, materially more.

---

## Round-1 verdict table

Producer file list for this judgement: `we/skills/story/SKILL.md`,
`we/references/long-running.md`, `we/references/ticket-briefs.md`. Anything needing a change in
`docs/plan-format.md`, `we/quality/dor.md`, other `we/references/*`, or orchestrate itself is a
**FORK**, not a producer failure.

| # | Round-1 gap | Verdict | Evidence from this run |
|---|---|---|---|
| **G1** | `refined` checkpoint written without running the scan | **FIXED** | Step 5.2 now exists — *"Scan what you wrote: run the 3-item check in `${CLAUDE_PLUGIN_ROOT}/references/dor-scan.md` against the file. A failure means fix the plan — never skip ahead to the checkpoint."* I ran it as Act-1 call 29 (all three items) **before** the checkpoint at call 36. The definitional conflict with `integration-pipeline.md` ("never the refiner") is also gone: orchestrate Step 1 now reads *"write it now, whoever wrote the plan"*. As the Act-2 Lead I re-ran the scan anyway and it agreed. |
| **G2** | No `## Constraints and Pins` section | **FIXED** | The template carries it verbatim, and it is the section I used at Step 8 A to name the two conflicts phases 2 and 3 could produce. My phase-1 brief's `CONSTRAINTS:`/`PINS:` lines are quoted straight out of it — round 1 shipped that brief with an empty `Pins:`. |
| **G3** | No per-phase risk class | **FIXED** (residual is a new gap, N1) | Every phase block carries `- **Risk:** …`. I read `**Risk:** migration` off phase 1 instead of inferring it from a filename containing `alembic/versions/`. Round 1's suggested *addendum* — "a non-ordinary phase is never dispatched fast-gates-only" — did **not** ship; see N2. |
| **G4** | No comment watermark | **FIXED — and it is the sharpest fix in the revision** | `comments_read_through: 10442` in frontmatter, plus the Step-1 clause. Act 2's signal-5 check became a single comparison: newest Jira comment `10442` == watermark → signal does not fire → `refined` stands. Round 1 paid a clause-by-clause diff of the comment against the plan every wave. |
| **G5** | No slot for repo-local DoR rows | **PARTIALLY FIXED** | The *instruction* shipped exactly as round 1 asked — Prerequisites now say each repo-local row *"gets its own labelled line in the plan (`**<Row name>:** …`), because `/we:orchestrate` gates on it and names the failing row"*. So `**Names the rollback step:**` exists and I found it by grepping the row name. But the **template still owns no section for it**; my writer parked it at the tail of `## Constraints and Pins` by choice, and a different writer would put it under Technical Approach or Documentation Impact. The Lead's approval read works only because it greps the whole file. |
| **G6** | No exit criterion in the plan | **FIXED** | `- **Exit criterion:**` is in the `## Verification` block and mine is runnable by someone else (seed → `app check webhooks --json` → three named conditions + the admin route). `long-running.md`'s demand that it live in the plan rather than terminal output is satisfied. |
| **G7** | `parallel_groups` semantics not stated producer-side | **FIXED** | The independence-check note now reads *"a group starts only after every lower-numbered phase has **merged**, and at most 2 chunks run concurrently inside it. Size groups accordingly"* — the same two facts as Step 5.4, so I declared `[[3, 4]]` knowing what I was declaring. The `docs/plan-format.md` contradiction is untouched, which round 1 had already scoped as FORK. |
| **G8** | `**Files:**` excluded generated artifacts and foreign tests | **FIXED** | The Files bullet now names *"generated artifacts (OpenAPI spec, generated clients, snapshots) and the existing test files whose call sites it breaks (`rg` the symbol under the test trees)"*. My phase 3 lists `api/openapi.json (regenerated)` **and** `mobile/src/api/generated/client.ts (regenerated from the spec)`; my phase 2 lists the pre-existing `api/tests/unit/test_webhook_dispatcher.py`. Round 1's failure mode — *"Three of five phases once stopped on that contradiction alone"* — is closed for these. `WORKER-REPORT.md` is still not a plan concern (correctly: it is the brief's). |
| **G9** | Missing-verb phase sequenced last with no rationale | **FIXED** | The bracket now reads *"…and say which phase ships it, as early as that phase's own dependencies allow; if it cannot be first, say why."* My plan uses the escape hatch honestly: phase 4 reads phase-1 and phase-2 state, so wave 0 is impossible, and it says so. At Step 5.8 I got the answer **and** the reason without opening the CLI. |
| **G10** | No `depends_on:` slot | **FIXED** (producer half) | `depends_on: []  # optional: story keys that must merge first` is in the template frontmatter. Step 3.4's instruction to a Lead — "write `depends_on: [KEY]` into the dependents' plan frontmatter" — now writes into a declared field. Its continued absence from `docs/plan-format.md` remains FORK, as round 1 scoped it. |
| **G11** | `epic:` collides with Step 0's single-Story test | **FORK — and I hit it live** | Round 1 already scoped this to orchestrate Step 0. It is unchanged and it cost me a call: with `epic: PROJ-1200` in the frontmatter, Step 0's *"no Epic plan / no other story shares it as `epic:`"* is not answerable from the plan, so I ran `ls docs/plans/PROJ-1200*` and `grep -l "epic: PROJ-1200" docs/plans/*-story.md` to prove Mode B. The producer did the right thing; the consumer's test is the wrong shape. Fix belongs in orchestrate Step 0 (*a single key given → single Story, regardless of siblings*). |
| **G12** | `/goal` bar undecidable for a migration | **FIXED — by deletion** | The SKILL no longer enumerates the `/goal` bar at all. Step 5.7 now says only *"Print the `/loop` (or, at its bar, `/goal`) invocation when `references/long-running.md`'s trigger fires"*, delegating to the reference's narrower *"a migration or a cutover with a hard finish line"*. My story — additive migration behind a flag, no cutover — reads as `/loop`-only under one rule instead of two conflicting ones. Cleaner than the alignment round 1 proposed. |
| **G13** | Verification labels drift from the receipt | **FIXED** | Template bullets are now `- **Asserted:**` and `- **Not proven:**`, matching `verification.md`'s receipt exactly, so `pr-creator`'s copy and the integration step's overwrite land on the same shape. My plan writes the intent block in receipt vocabulary. |
| **G14** | No state-file path in the producer's output | **PARTIALLY FIXED** | The line shipped verbatim as round 1 specified — Step 5.7's block prints `State file: docs/plans/{TICKET}-state.md (the Lead creates it on the first run).` But it prints to **terminal output**, and round 1's own G6 argument applies to it unchanged: *"exists only in Step 6's terminal output, which no later session reads."* Act-2 me never saw it; I derived the path from orchestrate's own Step-1 rule instead. The fix is correct and lands in the wrong medium. |
| **G15** | `## Verification` in the SKILL template but not in `docs/plan-format.md` | **FORK — still open, and wider than round 1 found** | `docs/plan-format.md`'s Full Template still lacks `## Verification`, `## Constraints and Pins`, the per-phase `**Risk:**` line, `type:`, `epic:`, `depends_on:` **and** `comments_read_through:` — the revision moved the producer four more fields ahead of the document that calls itself *"the **build contract** … Changes here are versioned and require explicit consideration of both sides."* Every G2/G3/G4/G10 fix widened this. Outside the producer file list; it is now the largest single hand-off debt in the repo. |

**Score:** 10 FIXED · 2 PARTIALLY FIXED (G5, G14) · 0 STILL OPEN · 3 FORK (G11, G15, and the
`plan-format.md` half of G7/G10).

---

## New gaps introduced by the revision

**N1 — the `**Risk:**` enum flattens the one distinction Step 5.2 makes. Severity: MEDIUM.**
Producer line: `- **Risk:** ordinary | migration | money | auth | tenant-isolation — [why]`.
Consumer: Step 5.2 defines critical as *"Money, auth, tenant isolation, **a migration on such a
table**"* — so `migration` is **not** a peer of the other three; it is critical only when it
lands on one of them. My phase 1 is a migration on a plain table and is therefore **not**
critical, but `**Risk:** migration` alone does not say that. I only got the answer because the
writer volunteered it in the free-text `— [why]`: *"not a money, auth or tenant-scoped table"*.
A writer who fills the why with "adds a table" leaves the Lead to open the model and decide the
model tier, the backend and the gate list — exactly what G3 was meant to stop.
**Fix (producer, one clause):** `- **Risk:** … — [why; for a migration, name the table class it
touches — a migration on a money/auth/tenant table is a critical chunk]`.

**N2 — nothing tells the writer what the Risk line decides. Severity: LOW–MEDIUM.**
Round 1's proposed G3 fix carried a second half — *"with a note that a non-ordinary phase is
never dispatched fast-gates-only"* — which did not ship. The template presents `**Risk:**` as
descriptive metadata; the writer has no reason to know that `ordinary` vs. not selects the model
tier, forbids a detached backend, and switches on the Worker-Brief's CRITICAL clause. The
cheapest labelling is the default one.
**Fix:** half a clause after the enum — *"a non-ordinary phase is never dispatched
fast-gates-only or to a cheap tier."*

**N3 — the integration suite and database are story-level; the brief needs them per chunk. Severity: MEDIUM.**
The revision added to `## Testing Requirements`: *"Integration tests for [Y] — name the runnable
suite and the database, not just the type."* Good, and I named
`pytest api/tests/integration/test_webhook_retry.py` against `proj_test`. But the Worker-Brief's
CRITICAL clause interpolates `{integration suite}` and `{database}` **per chunk**, and the phase
blocks have no slot for either. I mapped suite→phase by hand (phases 1 and 2 yes, 3 and 4 no),
and it only worked because those phases happened to list the suite file in `**Files:**`. A plan
that named the suite only in Testing Requirements would leave the mapping a guess.
**Fix:** either say in the phase-block comment that a non-ordinary phase names its own suite +
database, or say in Testing Requirements *"and which phases must run it before reporting done"*.

**N4 — the repo-local DoR line still has no home. Severity: LOW.** (residual of G5)
The instruction exists, the slot does not. One line in the template — a
`## Repo DoR` heading, or a sentence under `## Constraints and Pins` saying repo-local rows land
here — makes the Lead's "name the failing row" a section read instead of a whole-file grep.

**N5 — the `/loop` block and its scriptability caveat are terminal-only. Severity: MEDIUM.**
`long-running.md`'s trigger fires structurally on this plan (4 phases ≥ 4), and Step 5.7 says to
print the invocation *"only once the plan's `## Verification` names a scriptable oracle. If the
oracle is not scriptable yet, say so and make the first round's job to make it so."* That is a
real judgement — here the oracle is **not** scriptable until phase 4 — and it is made once, into
scrollback. The plan carries the exit criterion (G6, fixed) but nothing saying *this story is
loop-shaped and its oracle does not exist until phase 4*. Act-2 me had to re-derive both: the
4-phase trigger by counting headers, the caveat from the `**Missing CLI verb:**` line. Same
medium error as G14.
**Fix:** one line in the `## Verification` block — `- **Oracle available from:** [phase N — before
that, a round can only verify by <fallback>]` — or lift the whole Step-5.7 long-running block
into the plan.

**N6 — the G8 fix can manufacture an intra-plan file overlap it does not warn about. Severity: LOW.**
Because `**Files:**` must now name the test files a change touches, my phases 1 and 2 both name
`api/tests/integration/test_webhook_retry.py` — phase 1 creates it with the migration round-trip
case, phase 2 adds the concurrency case. That is correct and intended, but Step 5.3's disjointness
guard is a set intersection: it sees an overlap. Here it costs nothing (the phases are serial),
but the same pattern between two phases a writer wanted in one `parallel_groups` entry would be
silently wrong. Nothing in the template says *"when two phases legitimately share a file, say so
and never group them."*

**N7 — `depends_on:` is story-scoped and the intra-story ordering has only one carrier. Severity: LOW.**
Phases 3 and 4 depend on 1 and 2; the only place that fact lives is `parallel_groups: [[3,4]]`'s
barrier semantics. That works because they are two. Had phase 3 not existed, the ordering of a
lone phase 4 would need `[[4]]` — a one-member group neither the SKILL nor Step 5.4 defines — or
prose, which the SKILL itself warns is *"invisible to the consumer"*.

---

## Still cuttable

Round 1 listed ten blocks; most are gone — the "Writing Effective Acceptance Criteria" section,
the Red Flags table, Vision Alignment (3 Levels), Training on the Job, the Create/Design-Session
mode prose and the `~/.claude/plans/` duplication have all been cut or folded into the three-row
Modes table. What still restates itself:

1. **The triple stop.** Step 4's *"On approval → Step 5 immediately"*, Step 5's
   *"⛔ ExitPlanMode approval means 'run Step 5', not 'stop and summarize'"*, and
   *"⛔ **STOP after Step 5.** … no auto-continue to `/we:orchestrate`"*. Three statements of two
   rules. The two ⛔ lines are enough; Step 4's clause is the third telling.
2. **`**Ticket is MINIMAL. Plan contains ALL details.**`** (line 55) — already the Output table's
   Detail-Level column, already Step 5.3's heading and body, already `dor.md`'s
   *"Details are in the Plan, NOT in the ticket."* Keep the table.
3. **`The urge to split into phases is the orchestrate signal, not the epic signal.`** (line 107)
   — the two-bullet fork immediately above it already says exactly this, one bullet each.
4. **The Execution Surface table** (four rows × two columns) versus the two `**Recommend**`
   sentences that follow it. The sentences are the decision procedure and Step 5.7 only needs
   them; the table is a rationale a plan-writing Opus does not need served.
5. **`Load more files than feel necessary; a wrong assumption costs more than a wide read.`** —
   the graphify + TurboVault blocks directly above it already operationalise the behaviour.
6. **Rules bullet *"User-visible surfaces owe a proof block"*** — the `## Verification` block's
   own blockquote header states the same contract at the point of use.

Kept, for contrast — lines I would not have produced unprompted and that earned their tokens in
this run: `comments_read_through:`, the per-phase `**Risk:**` line, the Files bullet's
"what the change *causes* to change", `**Missing CLI verb:**` with its "if it cannot be first,
say why", `**Exit criterion:**`, the barrier + ≤2 sentence in the independence check,
`## Constraints and Pins`, and Step 5.0's main-worktree `awk`.

---

## Grade

**4 / 5 for the hand-off.** (Round 1 was 3/5.)

The revision closed the whole judgement half of round 1's list, and it closed it where a plan can
actually carry it. Three fields changed my Act-2 run measurably rather than cosmetically:
`comments_read_through: 10442` turned Step 3's signal 5 from a clause-by-clause re-read of the
tech lead's comment into one equality check; `## Constraints and Pins` gave the phase-1 brief real
`CONSTRAINTS:`/`PINS:` content where round 1 shipped an empty line and told the worker to respect a
section that did not exist; and the Files bullet's "what the change *causes* to change" put
`openapi.json` and the generated mobile client into phase 3's list, which is the single class of
omission the executor-selection paragraph names as having stopped three of five phases dead. Add
the `**Missing CLI verb:**` line answering *when* and *why not earlier*, and the Step-5.8 discovery
that round 1 also avoided is now avoided **with its reason attached**. Four invented fields in my
phase-1 brief against round 1's seven, and three of my four (test discipline, repo constraints,
gate baselines) are the absent `.weside/orchestrate.md` and a thin `config.json` — orchestrate's
own dependencies, not the plan's. It is a dispatch contract now, not just a specification.

It is not 5/5 for two reasons and one that is not the producer's. First, the fields that decide
*how a chunk is dispatched* still leak: `**Risk:** migration` does not answer Step 5.2's actual
question (migration **on what class of table**), and only a volunteered why-clause saved my
executor pick (N1/N2); the integration suite and database exist at story level while the
Worker-Brief interpolates them per critical chunk, so I mapped them by hand (N3). Second, two of
round 1's fixes landed in the wrong medium — the state-file path (G14) and the `/loop` block with
its "oracle not scriptable until phase 4" caveat (N5) are printed to a terminal that the fresh
Lead, by definition, never saw; G6's own argument condemns both, and both are one line in the
plan away from being fixed. The third, not the producer's fault: `docs/plan-format.md` still calls
itself the versioned build contract while the producer has now moved seven fields ahead of it,
and orchestrate Step 0 still can't resolve a single-key invocation against the `epic:` field the
producer is required to write. Those are the FORKs, and they are now the biggest thing standing
between this hand-off and a 5.
