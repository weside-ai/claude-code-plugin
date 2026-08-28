<!-- markdownlint-disable -->

# Round 1 — Scenario (d): story → orchestrate hand-off

Table-top only. No tool was executed; every call below is traced, not run.

## Act 1 trace

I am `/we:story PROJ-1207`. One argument that looks like a ticket key → **Refine Mode**.

**Prerequisites block (SKILL lines 24–34)**

1. `Read("${CLAUDE_PLUGIN_ROOT}/quality/dor.md")` → the full DoR checklist.
2. `Read("${CLAUDE_PLUGIN_ROOT}/references/verification.md")` → oracle ladder + receipt.
3. `Read("${CLAUDE_PLUGIN_ROOT}/references/long-running.md")` → `/loop` vs `/goal`.
4. `Bash("git rev-parse --show-toplevel")` → `/home/user/proj`.
5. `Read("/home/user/proj/.weside/dor.md")` → exists. One extra row beyond the plugin defaults:
   **"names the rollback step"**. Additive — both sets apply.
6. `Bash("ls /home/user/proj/.weside")` → `dor.md`, `verify.md`, `config.json`. `.weside/` exists →
   no `/we:setup` nag. Session model is Opus → no `/model opus` line.
   *(I did not read `.weside/verify.md` here — nothing in Prerequisites tells me to. I only reach
   it in Step 4 because `verification.md` says the commands live there. Noted for the gap list.)*

**Step 1 — Load Story**

7. `mcp__atlassian__jira_get_issue("PROJ-1207", fields="*all", comment_limit=50)` →
   summary, description, **one comment** from the tech lead:
   *"Retries must be idempotent and must not fan out: one in-flight attempt per delivery id.
   Dead-letter after 6 attempts, surfaced in the admin UI."*
   Newest statement wins → this comment is binding on scope.
8. `Bash("ls docs/plans/PROJ-1207-story.md docs/plans/PROJ-1207-plan.md")` → neither exists.
   Fresh plan.
9. `mcp__atlassian__jira_get_issue("PROJ-1200")` → parent epic *Webhook reliability*, so the
   `epic:` frontmatter field has a value.
10. `Bash("ls docs/plans/PROJ-1200*")` → no epic plan file on disk. (Only the Jira epic exists.)

**Step 2 — Understand Context (INTERACTIVE, grill-style, one question at a time)**

Requirements are not vague (description + a directive comment), so no brainstorming detour.
Four questions, each with my recommendation; I explore the repo instead of asking where I can.

11. `Bash("rg -n 'webhook' src/backend/app --type py -l")` → `app/services/webhook_dispatch.py`,
    `app/models/webhook_endpoint.py`, `app/api/admin/__init__.py`. Existing delivery path found —
    so I do not ask "does an outbound webhook sender exist".

    **Q1 — backoff shape.** *"Recommend `2**n` seconds base with full jitter, capped at 1 h;
    attempts 1..6 then dead-letter, per the lead's comment. OK?"*
    `[USER]` "Yes. Cap at 1 hour, jitter yes. 6 attempts total including the original."

    **Q2 — where the lock lives.** *"Recommend a Postgres advisory lock keyed on the delivery id
    inside the scheduler transaction — no new Redis dependency. Alternative: a `claimed_at`
    column with `SELECT … FOR UPDATE SKIP LOCKED`."*
    `[USER]` "Take `FOR UPDATE SKIP LOCKED` — we already use it in the jobs table, and it survives
    a Redis outage."

    **Q3 — dead-letter surface.** *"Recommend a read-only list in the existing admin screen stack
    plus a `GET /admin/webhooks/dead-letter` endpoint. Requeue-from-UI out of scope for this
    story?"*
    `[USER]` "Out of scope. Read-only list is enough for now, requeue is a separate ticket."

12. `Bash("cat /home/user/proj/.weside/verify.md")` → verbs `app seed --tenant <id>` and
    `app check webhooks`. So the assert side has a home but no dead-letter selector.

    **Q4 — the missing verb.** *"`app check webhooks` exists but reports live endpoint health only.
    The assert needs the dead-letter count. Recommend extending it with
    `app check webhooks --dead-letter --json` and shipping that in this story, per
    `verification.md` § *a missing verb is a bug in the CLI*."*
    `[USER]` "Yes, ship it here."

13. `Bash("ls /home/user/proj/CONTEXT.md")` → absent. No glossary pass, no `_Avoid_` terms.

Scope check (Step 2's "which kind of big"): four phases, one coherent change, one PR's worth of
value → **stays a single Story**, not an epic. The split instinct is the orchestrate signal.

**Step 3 — Update Ticket (MINIMAL)**

14. `mcp__atlassian__jira_update_issue("PROJ-1207", description=<the 5-line minimal template>)` —
    user story + plan link only, per `references/ticket-briefs.md`: no file paths, no line numbers.

**Step 4 — Create Plan (EnterPlanMode)**

15. `EnterPlanMode()`.
16. TurboVault: unavailable. I emit the mandated one-liner:
    > ⚠️ TurboVault unavailable — using grep fallback; architecture context may be incomplete. Check the MCP config.
17. `Grep(pattern="webhook|retry|backoff|idempot", include="*.md", path="docs/")` →
    `docs/architecture/outbound-integrations.md`, `docs/adr/ADR-0031-job-locking.md`.
18. `Glob(pattern="docs/architecture/**/*.md")` → 14 files; I read the two above plus
    `docs/architecture/admin-surfaces.md`.
19. `Bash("python3 scripts/graphify/check.py --build-if-missing")` → graph present (installed).
20. `Bash("python3 scripts/graphify/query.py 'WebhookDispatchService webhook_endpoint deliver_webhook' --top 10")`
    → entry points `WebhookDispatchService.deliver`, `app/crud/webhook_endpoint.py`,
    dependents `app/api/admin/webhooks.py`, `app/tasks/scheduler.py`. These become the
    per-phase `**Files:**` lists and the disjointness basis for `parallel_groups`.
21. Session-context distillation → `## Context` narrative + `## Design Decisions` rows for Q1–Q4.
22. `ExitPlanMode(plan=<the document below>)`.

**Step 5 — approval**

`[USER]` "Approved. Go."

**Step 6 — the six commands, no chatter between them**

23. `Read("~/.claude/plans/copper-heron.md")`; frontmatter → `status: approved`, `story: PROJ-1207`.
24. `Bash("git worktree list --porcelain | awk …")` → `MAIN_WORKTREE=/home/user/proj` (already cwd,
    already on `main`).
25. `Write("/home/user/proj/docs/plans/PROJ-1207-story.md", <content below>)`.
26. `mcp__atlassian__jira_update_issue("PROJ-1207")` → description carries the plan link.
27. `Bash("cd /home/user/proj && [ \"$(git branch --show-current)\" = main ] && git add docs/plans/PROJ-1207-story.md && git commit -m 'docs: add PROJ-1207 plan — Retry failed outbound webhooks with backoff' && git push")`.
28. `Bash("python3 ${CLAUDE_PLUGIN_ROOT}/scripts/orchestration.py story checkpoint PROJ-1207 refined")`.
    *(I ran no scan before writing this. The skill does not tell me to — see Gap 1.)*
29. TurboVault vault-links step: skipped silently (no MCP).
30. Output:
    ```
    Plan saved to docs/plans/PROJ-1207-story.md. /we:story DONE.

    Recommended next: /we:orchestrate PROJ-1207   ← 4 phases, phases 3+4 parallel after 1+2
    (or /we:orchestrate PROJ-1207 --solo if you'd rather run it inline.)

    Long-running:
      /loop Build PROJ-1207 phase by phase until `app check webhooks --dead-letter --json`
            reports a non-empty dead-letter list for a seeded exhausted delivery and the
            admin list renders it.
    ```
    No `/goal` line: no money, auth or tenant-isolation path. *(A migration is on
    `long-running.md`'s `/goal` bar — "a migration or a cutover with a hard finish line". I judged
    an additive table not to be a cutover. The skill gives me no tiebreaker; see Gap 12.)*
31. STOP. No branch, no code, no orchestrate.

---

## The plan file (Act 1 artifact)

```markdown
---
type: story-plan
story: PROJ-1207
epic: PROJ-1200
created: 2026-08-27
status: approved
parallel_groups: [[3,4]]
---

# Plan: Retry failed outbound webhooks with backoff

## Context

Integrators lose events today whenever their receiver has a brief outage: a delivery that
fails once is dropped and never retried, so a two-minute deploy on their side costs them
every event in that window. We are fixing it now because it is the top complaint on the
Webhook reliability epic (PROJ-1200) and because the admin team has no way to even see what
was lost. The tech lead set two hard constraints in the ticket that are not obvious from the
description: retries must be idempotent, and there must never be more than one in-flight
attempt per delivery id — a fan-out here would double-deliver to a customer, which is worse
than losing the event. Six attempts, then the delivery goes to a dead-letter state that the
admin UI lists. The user agreed we take `SELECT … FOR UPDATE SKIP LOCKED` for the lock rather
than a Postgres advisory lock or Redis, because the jobs table already uses that pattern and
it survives a Redis outage. Requeue-from-the-UI is explicitly out of scope for this story.

## Acceptance Criteria
1. **Given** an outbound webhook delivery whose receiver returns 503 **When** the retry
   scheduler runs **Then** a new row appears in `webhook_delivery_attempts` and the next
   attempt is scheduled at `min(2**n s + jitter, 1h)` after the failure.
2. **Given** a delivery with an attempt already in flight **When** a second scheduler tick
   selects candidates **Then** that delivery is skipped and exactly one attempt exists for it.
3. **Given** a delivery that has failed 6 times **When** the scheduler runs again **Then** the
   delivery is marked `dead_letter`, no further attempt is made, and it is returned by
   `GET /admin/webhooks/dead-letter`.
4. **Given** I am an admin on the Webhooks admin screen **When** I open the "Dead letter" tab
   **Then** I see one row per dead-lettered delivery with endpoint, last status and attempt count.
5. **Given** a seeded tenant with one dead-lettered delivery **When** I run
   `app check webhooks --dead-letter --json` **Then** it exits 0 and prints that delivery's id
   and attempt count.

## User Journey
1. An integrator's receiver goes down for two minutes; deliveries start failing.
2. The scheduler retries each failed delivery with growing backoff, one attempt at a time.
3. The receiver comes back; the next scheduled attempt succeeds and the delivery is done.
4. For a receiver still down after 6 attempts, the delivery is dead-lettered; the admin opens
   the Webhooks screen's "Dead letter" tab and sees exactly which events were lost, for whom.

## Testing Requirements
- Unit tests for the backoff function (attempt n → delay, cap at 1 h, jitter bounded).
- Unit tests for the dead-letter transition at exactly attempt 6, not 5, not 7.
- Integration tests (real Postgres) for the `FOR UPDATE SKIP LOCKED` claim: two concurrent
  scheduler ticks over the same delivery id produce exactly one attempt row.
- Integration test for the admin endpoint's tenant scoping.
- CLI test for `app check webhooks --dead-letter --json` output shape and exit code.
- Edge cases: receiver returns 2xx on the final attempt; clock skew on `next_attempt_at`;
  a delivery whose endpoint was deleted between attempts.

## Verification
> How this will be observed running — not inferred from green tests.

- **Oracle:** cli — the whole story is backend state plus one admin list; AC 1–3 and 5 are
  machine-readable. AC 4 is a UI reachability claim and gets a walkthrough on top (oracle 2).
- **Seed:** `app seed --tenant t-verify` then force six failures against a receiver stub:
  `app check webhooks --dead-letter --json` after the scheduler has ticked seven times.
- **Assert:** `app check webhooks --dead-letter --json` exits 0 and lists the seeded delivery
  with `attempts: 6`; `GET /admin/webhooks/dead-letter` returns that id; the admin screen's
  "Dead letter" tab renders a row carrying that id.
- **Not provable here:** that a real integrator's receiver behaves like the stub, and that the
  backoff cap is right for production traffic — that is owed by the first week of prod metrics.
- **Missing CLI verb:** `app check webhooks --dead-letter --json`. `app check webhooks` today
  reports live endpoint health only and cannot select dead-lettered deliveries. It ships with
  this story as Phase 4, not as a transcript snippet.

## Technical Approach
**Patterns:** existing `WebhookDispatchService` stays the single send path — the scheduler
calls it, never a second sender. Claim rows with `SELECT … FOR UPDATE SKIP LOCKED` exactly as
`app/crud/job.py` does (ADR-0031). Idempotency: the attempt row is inserted before the send and
carries the delivery id + attempt number as a unique constraint, so a replayed tick cannot
create a second attempt. Additive migration only — new table, plus two nullable columns on
`webhook_deliveries`; no backfill, no rewrite of an existing column.
**Rollback:** the migration is additive, so `alembic downgrade -1` drops
`webhook_delivery_attempts` and the two nullable columns with no data loss on the existing
table; the scheduler is off until its config key `WEBHOOK_RETRY_ENABLED` is set, so a bad
deploy is rolled back by clearing that key without a code revert.

## Implementation Phases

### Phase 1: Attempt table + migration
- **Goal:** `webhook_delivery_attempts` exists with the unique `(delivery_id, attempt_no)`
  constraint, plus `next_attempt_at` and `state` on `webhook_deliveries`; CRUD reads/writes it.
- **Files:** `src/backend/app/models/webhook_delivery_attempt.py`,
  `src/backend/app/models/webhook_delivery.py`,
  `src/backend/alembic/versions/8f21c4a0b3de_webhook_delivery_attempts.py`,
  `src/backend/app/crud/webhook_delivery.py`,
  `src/backend/tests/crud/test_webhook_delivery.py`
- **Approach:** additive Alembic revision off the current head; unique constraint in the
  migration, not only in the model. CRUD gets `claim_due_deliveries()` using
  `FOR UPDATE SKIP LOCKED` and `record_attempt()`.

### Phase 2: Retry scheduler with backoff and per-delivery lock
- **Goal:** a scheduler tick claims due deliveries one at a time per delivery id, re-sends via
  `WebhookDispatchService`, records the attempt, schedules the next one, and dead-letters at 6.
- **Files:** `src/backend/app/services/webhook_retry_scheduler.py`,
  `src/backend/app/services/webhook_dispatch.py`,
  `src/backend/app/tasks/scheduler.py`,
  `src/backend/app/core/config.py`,
  `src/backend/tests/services/test_webhook_retry_scheduler.py`
- **Approach:** `backoff(n) = min(2**n + full_jitter, 3600)`. The claim, the attempt insert and
  the send happen in one transaction boundary so a crash cannot leave a claimed-but-unrecorded
  attempt. Behind `WEBHOOK_RETRY_ENABLED`.

### Phase 3: Dead-letter list in the admin UI
- **Goal:** an admin can open the Webhooks screen's "Dead letter" tab and see every
  dead-lettered delivery for the tenant.
- **Files:** `src/backend/app/api/admin/webhooks.py`,
  `src/backend/app/schemas/webhook_admin.py`,
  `src/backend/tests/api/admin/test_webhooks_dead_letter.py`,
  `src/mobile/src/screens/admin/WebhookDeadLetterTab.tsx`,
  `src/mobile/src/api/webhooks.ts`,
  `src/mobile/src/screens/admin/__tests__/WebhookDeadLetterTab.test.tsx`
- **Approach:** `GET /admin/webhooks/dead-letter` paginated, tenant-scoped; the tab is a
  read-only list. No requeue action — out of scope.

### Phase 4: `app check webhooks --dead-letter` CLI verb
- **Goal:** the verification oracle exists as a real verb: a machine-readable dead-letter report.
- **Files:** `apps/cli/app/commands/check.py`,
  `apps/cli/tests/test_check_webhooks.py`,
  `.weside/verify.md`
- **Approach:** extend the existing `check webhooks` command with `--dead-letter` and `--json`;
  reads through `app/crud/webhook_delivery.py`, adds no query of its own.

> Phases 3 and 4 touch disjoint files and both depend only on 1 and 2 — declared as
> `parallel_groups: [[3,4]]`.

## Design Decisions

| Decision | Alternatives Considered | Why This |
|----------|------------------------|----------|
| `SELECT … FOR UPDATE SKIP LOCKED` for the per-delivery lock | Postgres advisory lock; a Redis `SET NX` lease | Already the repo's pattern in `crud/job.py` (ADR-0031); survives a Redis outage; no new dependency |
| `min(2**n + jitter, 1h)`, 6 attempts | fixed 5-minute retry; 10 attempts | Tech lead's comment fixed 6; full jitter avoids a thundering herd when a receiver recovers |
| Unique `(delivery_id, attempt_no)` for idempotency | dedup by a hash of the payload | The constraint is enforceable in the database; a payload hash is not stable across serialisation changes |
| Read-only dead-letter list | requeue button in the same story | User called requeue out of scope — separate ticket |
| Additive migration, feature flag | rewrite `webhook_deliveries.status` in place | Keeps rollback to a flag clear plus `downgrade -1`, no backfill window |

## Code Guidance
**DO:** route every send through `WebhookDispatchService`; insert the attempt row before the
send; keep the scheduler's selection in CRUD, not in the service.
**DON'T:** add a second sender; retry inside the request handler; widen the admin endpoint
beyond the caller's tenant; add a Redis dependency for locking.

## Security Review Required
No — no new authn/authz surface; the admin endpoint reuses the existing admin guard and is
tenant-scoped like its siblings. Payloads are not logged.

## Documentation Impact
- **Docstrings** — `webhook_retry_scheduler.py` (the backoff and the at-most-one-in-flight
  invariant), `crud/webhook_delivery.claim_due_deliveries` (why SKIP LOCKED).
- **Architecture doc** — `docs/architecture/outbound-integrations.md`: the delivery lifecycle
  gains a retry and dead-letter state; one diagram + one paragraph.
- **ADR** — no. The locking choice follows ADR-0031 rather than departing from it.
- **Generated** — `openapi.json` and the TS client for the new admin endpoint.
- **New doc** — none.
```

---

## Act 2 — field-by-field consumer audit

Fresh Lead, `/we:orchestrate PROJ-1207`, `bypassPermissions`, Agent Teams on.

Prerequisites first: `Read(".weside/orchestrate.md")` → **absent**. Per the skill I must derive
worktree bootstrap, generated artifacts, gate baselines, single-owner ports, risk-class file
lists and where plan/state commits land from `CLAUDE.md` and the always-loaded rules, say so in
the roll-up, and offer to write it. Everything marked *(derived, no `.weside/orchestrate.md`)*
below flows from that absence — it is the consumer's own gap, not the producer's, but it
compounds every producer gap under it.

| Field orchestrate reads | Carried by the plan? | What I guessed / asked / derived |
|---|---|---|
| **Step 0** — single Story? | **Partly — and the plan actively muddies it.** `docs/plans/PROJ-1207-story.md` exists and has `### Phase` blocks → Mode B. But Step 0's condition is "…and no Epic plan / **no other story shares it as `epic:`**", and the plan declares `epic: PROJ-1200`. | Derived: `ls docs/plans/PROJ-1200*` → no epic plan file; `rg -l 'epic: PROJ-1200' docs/plans/` → I must run this to find out whether a sibling story shares the epic. If one does, Step 0's own text says this is *not* a single Story even though the human typed one key. I resolved it as single Story because the human named one key — a judgement call the plan does not settle. |
| **Step 1/2** — `epic:` frontmatter for ready-set matching | **Yes.** `epic: PROJ-1200` | Nothing guessed. This is the producer's clearest win. |
| **Step 1** — state file path | **No line exists.** The plan never names `docs/plans/PROJ-1207-state.md`, and `/we:story`'s output block does not either. | Derived from orchestrate Step 1's own rule (`<primary-key>-state.md`), and **written by me before the first dispatch** — including a Board and Decisions-locked section I had to reconstruct from the plan's Design Decisions table. Where it may be committed: derived, no `.weside/orchestrate.md`. |
| **Step 1** — `## Success Criteria` lens for "done" | **No such section.** The plan has `## Acceptance Criteria`, not `## Success Criteria`; there is no epic plan on disk to supply the lens. | Synthesised the frame from the story's 5 ACs, exactly as Step 1's "no epic file → synthesise" fallback allows. Low cost here; for a real epic run this would be a fabricated lens. |
| **Step 2** — DoR scan (3 checks, by hand) | **Passes.** (1) GWT: `**Given** an outbound webhook delivery … **When** … **Then**` — present ✓. (2) Context > 50 chars: ~1 100 chars of narrative ✓. (3) `^### Phase \d+:` — four matches ✓. | Nothing guessed. But: a `refined` checkpoint **already exists** (`/we:story` Step 6.4 wrote it) and the producer never ran this scan. `integration-pipeline.md` says `refined` is "written by Lead, after verifying — **never the refiner**". So I inherited a checkpoint whose meaning the producer did not earn. I re-ran the scan by hand anyway; it happened to pass. |
| **Step 2** — repo `.weside/dor.md` row "names the rollback step" | **Yes, but in a place no consumer is told to look.** The plan carries `**Rollback:** the migration is additive … clearing that key without a code revert` — buried inside `## Technical Approach`. | I had to read the whole plan to find it. The template has **no slot** for repo-local DoR rows, so a different `/we:story` run could equally have put it in `## Code Guidance`, in the Context narrative, or nowhere at all. My approval read at the confirm gate is a full-text search for the word "rollback", not a section check. |
| **Step 3 signal 1** — open question in the ticket | No open question. Description + one directive comment. | `jira_get_issue(PROJ-1207, comments)` re-read at boot. Clean. |
| **Step 3 signal 2** — epic names it and nothing more | N/A — the plan is detailed. | — |
| **Step 3 signal 3** — mirror caveats (`TBD`, `blocked on`) | No epic plan → no mirror block to check. | Skipped, named as skipped in the roll-up. |
| **Step 3 signal 4** — freezes an interface others consume | **NO. The plan has no field for this at all.** Phase 1's unique constraint + `claim_due_deliveries()` signature and Phase 2's `state` enum are consumed by both Phase 3 (the admin endpoint) and Phase 4 (the CLI). Nothing in the plan says "this is frozen". | Derived by hand: `graphify affected "claim_due_deliveries" --relation calls --depth 2` plus `rg -n 'webhook_delivery' apps/cli src/mobile`. I concluded phases 1 and 2 are the seam, must be serial and first — which matches the plan's ordering, but I had to *re-derive* that rather than read it. `worker-dispatch.md` and Step 8 A both tell me to resolve merge conflicts "by the plan's **Constraints and Pins**" — **the producer template emits no Constraints and no Pins section**, so that instruction has no referent. |
| **Step 3 signal 5** — comments contradict the plan | **Cannot be answered from the plan.** The lead's comment (idempotent, one in-flight, 6 attempts, admin UI) *is* reflected in the ACs, but nothing in the plan records **which comments it was written against**. | I diffed the ticket's comment text against the plan by hand, clause by clause. If a second comment had landed after the plan was written I would have no way to tell it from the first except by date-vs-`created:` — and `created: 2026-08-27` is a *date*, not a comment watermark. This is exactly the signal that sends a `refined` story back to the refine lane, and the plan gives me no cheap way to fire it. |
| **Step 3/5** — `depends_on:` slot in frontmatter | **No slot.** Neither the producer template nor `docs/plan-format.md` lists `depends_on`. | Not fatal *here*: Step 3.4 says "in Mode B the wave map and the state file carry the order instead", so I wrote the order into the state file. But the producer cannot express a cross-story dependency at all, and PROJ-1207 plausibly has one (a sibling story in PROJ-1200 touching `webhook_dispatch.py`). |
| **Step 5.2** — risk class per chunk | **Partly derivable, never stated.** Phase 1's `**Files:**` contains `alembic/versions/…` → I classify it **migration** (a named risk class) from the path alone. Phase 2 touches `app/core/config.py` and a send path — ordinary. Phases 3–4 ordinary. | The risk class is my inference from a filename, not a producer declaration. `## Security Review Required` says "No", which is a *different axis* and, read carelessly, reads as "nothing critical here" over a migration chunk. Repo risk-class file lists live in `.weside/orchestrate.md` — absent, so I derived from `CLAUDE.md`. Consequence I had to invent: Phase 1 is **never fast-gates-only**, **never on a detached backend** ("a migration never on one at all"), and starts at `opus` or the Lead. |
| **Step 5.3** — per-phase `**Files:**` concrete enough to intersect? | **Yes for intersection, no for completeness.** P1 ∩ P2 = `{}` (P1 `models/webhook_delivery.py` vs P2 `services/webhook_dispatch.py` — disjoint). P3 ∩ P4 = `{}` ✓. So `[[3,4]]` survives the guard. | Two things the plan omits that I had to add before dispatch: (a) **generated artifacts** — P3 adds an admin endpoint, so `openapi.json` and the generated TS client change; the plan names them only in `## Documentation Impact` ("Generated — openapi.json and the TS client"), **not** in P3's `**Files:**`. Orchestrate's Executor-selection paragraph says the file list must be reconciled with the prose or a conscientious worker stops on the contradiction — "three of five phases once stopped on that contradiction alone". I moved them in by hand. (b) **`WORKER-REPORT.md`** — never a producer concern, added by me. |
| **Step 5.4** — `parallel_groups` semantics match? | **The declaration matches my intent by luck; the producer never states the semantics.** Plan says `[[3,4]]`; Step 5.4 reads that as "phases 1 and 2 run serially in plan order; the group [3,4] starts only after **phase 2 has merged**; inside it ≤ 2 concurrent". | The producer's own words (SKILL line 225) are only *"phases touch **disjoint files** and have **no ordering dependency**… can run concurrently"* — **no merge barrier, no ≤2 cap**. And `docs/plan-format.md` says the opposite of the cap: *"dispatched as concurrent sub-agents in a **single `Agent()` message**"* with no limit. Here `[[3,4]]` = 2 chunks, so the cap never bites and the barrier is what I wanted anyway. A plan with `parallel_groups: [[2,3,4]]` written under the producer's semantics would silently mean something else under the consumer's. |
| **Step 5.6/5.7** — worktree bootstrap, install rule | Not the plan's job. | Derived from `CLAUDE.md`, no `.weside/orchestrate.md`. |
| **Step 5.8** — verbs the verification needs | **Yes — the producer's best line.** `**Missing CLI verb:** app check webhooks --dead-letter --json. app check webhooks today reports live endpoint health only…` I would have caught it: I read `.weside/verify.md` (verbs `app seed --tenant <id>`, `app check webhooks`), and `--dead-letter` is not there. | **But the sequencing contradicts Step 5.8.** The plan makes the verb **Phase 4**, in the last parallel group, depending on 1 and 2. Step 5.8 says a missing verb is "cut in **wave 0** so its PR's merge window overlaps the build — not discovered at Step 8 B when every worker is gone". Same repo here, so no cross-repo PR wait — but the plan's own ordering puts the verification oracle last, and the producer never tells the story writer to sequence it first. I re-planned it into wave 0 alongside Phase 1? No — it reads through `crud/webhook_delivery.py`, which Phase 1 creates. So it genuinely cannot be wave 0, and the plan should have said so. I recorded the reasoning in the state file myself. |
| **Step 6** — `test_discipline` for the brief | **No.** Not a plan field. | `.weside/config.json` → invented as `tests-after` (the skill's stated default when absent). |
| **Step 6/5.2** — integration suite + database for the critical chunk | **No line exists.** `## Testing Requirements` says *"Integration tests (real Postgres)"* — a test *type*, not a runnable suite path or a database name. | Invented: `pytest src/backend/tests/crud -m integration` against `proj_test`, plus `alembic upgrade head` first. Both derived from `CLAUDE.md`, not from the plan. |
| **Step 8 A** — "Constraints and Pins" for conflict resolution | **No such section exists.** | Substituted `## Code Guidance` (DO/DON'T) + the Design Decisions table. Workable, but it is not what the reference names, and a foreign-engine brief that copies the `worker-dispatch.md` template will emit an empty `Pins:` line. |
| **Step 8 B / verification receipt** | **Section exists, labels drift.** The plan's block uses `**Assert:**` and `**Not provable here:**`; `verification.md`'s receipt uses `**Asserted:**` and `**Not proven:**`. | I write the receipt into the plan's `## Verification` at integration. I had to decide whether to overwrite the intent block or append under it — nothing says. I appended, keeping the intent above. |
| **Step 10** — Done check: every `### Phase`'s `**Files:**` actually changed | **Yes**, four phases with concrete file lists. | Nothing guessed — except that the two generated artifacts I added to P3 are now in *my* list and not in the plan's, so a literal Step-10 check reads the stale list. I rewrote P3's `**Files:**` in the close-out per Step 10's living-plan rule. |
| **long-running** — exit criterion for `/loop` | **No slot.** `long-running.md` says the exit criterion "lives in the plan and the state file"; the template has no `**Exit criterion:**` field anywhere. | `/we:story` printed one in its terminal output (`/loop Build PROJ-1207 … until app check webhooks --dead-letter --json reports …`) — **terminal output is not an artifact**. As a fresh Lead I never saw it. I reconstructed the criterion from AC 5 and wrote it into the state file. |

---

## The phase-1 Worker-Brief I would send

Phase 1 carries a migration → risk class **migration** (Step 5.2): `opus`, never fast-gates-only,
never a detached backend. So: an Agent teammate on `opus`, not the `sonnet` default in the
skill's dispatch snippet.

Fields marked **[INVENTED]** came from nowhere in the plan; **[DERIVED]** from the repo;
**[PLAN]** was actually carried.

```
You are worker-PROJ-1207-p1, a teammate spawned into this session's implicit team. The lead is "team-lead".

REPO: /home/user/proj.                                        [DERIVED — cwd]
Start every bash command with `cd /home/user/proj` and confirm `git rev-parse --show-toplevel`
before any git operation.
WORKTREE: `/home/user/proj-PROJ-1207-p1`, already on branch `feat/PROJ-1207-p1`
(off `feat/PROJ-1207-integration`) and bootstrapped.                [DERIVED — Step 5.7]
Bootstrap that was run: `uv sync && cp .env.example .env.local`.    [INVENTED — no .weside/orchestrate.md]
`cd` there; do not call EnterWorktree. Run: Skill(skill="develop") for PROJ-1207 --phases 1.

DEV-ONLY: implement phase 1 → gates → AC-check your diff → commit → push feat/PROJ-1207-p1 → STOP.
No gh pr create, no CI, no ticket transition, no doc pass.

CHUNK (verbatim from docs/plans/PROJ-1207-story.md § Phase 1):                          [PLAN]
  Goal: webhook_delivery_attempts exists with the unique (delivery_id, attempt_no) constraint,
  plus next_attempt_at and state on webhook_deliveries; CRUD reads/writes it.
  Files: src/backend/app/models/webhook_delivery_attempt.py
         src/backend/app/models/webhook_delivery.py
         src/backend/alembic/versions/8f21c4a0b3de_webhook_delivery_attempts.py
         src/backend/app/crud/webhook_delivery.py
         src/backend/tests/crud/test_webhook_delivery.py
         WORKER-REPORT.md (write-allowed, NOT committed)                           [INVENTED]
  Approach: additive Alembic revision off the current head; unique constraint in the migration,
  not only in the model. CRUD gets claim_due_deliveries() using FOR UPDATE SKIP LOCKED and
  record_attempt().

REVISION: branch off the current single head — run `alembic heads` first and refuse to invent a
down_revision. The filename in the plan pins a revision id that may already be taken;
if `alembic heads` disagrees, use the real head and say so in your report.       [INVENTED — the plan
                                              hard-codes a revision id it could not have known]

PINS: this chunk FREEZES an interface two later chunks consume — `claim_due_deliveries()`'s
signature and the `state` enum values (`pending|retrying|delivered|dead_letter`). Do not rename
them; if you must change one, stop and ask.        [INVENTED — enum values and the freeze itself;
                             the plan has no Constraints/Pins section and no freeze declaration]

CONSTRAINTS (from the plan's Code Guidance):                                            [PLAN]
  DO keep the scheduler's selection in CRUD, not in the service.
  DON'T add a second sender; DON'T widen beyond the caller's tenant; DON'T add Redis.

ROLLBACK (repo DoR row "names the rollback step"): the migration is additive; `alembic
downgrade -1` must drop the table and the two nullable columns cleanly. Write the downgrade,
do not `pass` it.                     [PLAN — but I had to dig it out of ## Technical Approach]

TESTS: tests-after — write tests in the same change, after the code. No implementation-coupled
tests, no tautological assertions, mock at system boundaries only.   [INVENTED — .weside/config.json
                                                                          has no test_discipline]

GATES: CRITICAL chunk (migration). Not fast-gates-only. Before reporting done run
  `alembic upgrade head && alembic downgrade -1 && alembic upgrade head` against proj_test,
  then `pytest src/backend/tests/crud -m integration`,
  and append the last 20 lines of each to WORKER-REPORT.md.
                                    [INVENTED — suite path, marker, and database name; the plan
                                     says only "Integration tests (real Postgres)"]
  (The Lead re-runs the real-database up→down→up itself at Step 8 B regardless.)

REPO CONSTRAINTS: no generated artifacts in this chunk; no gate-baseline file is touched.
                          [DERIVED — I had to prove this by reading the repo, since there is no
                           .weside/orchestrate.md listing generated artifacts or baselines]

REPORT FILE: write WORKER-REPORT.md in your worktree root before you stop. Do not `git add` it.
REPORTING IS NOT OPTIONAL: SendMessage(to="team-lead", summary="worker-PROJ-1207-p1 done|blocked",
  message="<branch | commits: N | gates: … | AC-check: … | skipped: … | blockers: …>")
NEVER report done without a pushed branch.
```

Tally: **7 invented blocks** in one brief for the *best-specified* phase in the plan. Three of
them (revision head, the enum/signature freeze, the integration suite + database) are the exact
class of thing a detached worker cannot ask about.

---

## Gaps — what the Lead needed and the plan did not carry

**G1 — `refined` checkpoint written without running the scan. Severity: HIGH.**
Producer line: `4. **Checkpoint:** python3 ${CLAUDE_PLUGIN_ROOT}/scripts/orchestration.py story checkpoint {TICKET} refined`.
`dor-scan.md` is not in `/we:story`'s Prerequisites and is never invoked anywhere in the skill,
yet the checkpoint it writes is *defined* as "the plan passes the DoR scan"
(`integration-pipeline.md`: "written by Lead, after verifying — **never the refiner**"). The
producer stamps the ready-set state unconditionally.
**Fix (producer):** insert one step before Step 6.4 — *"Run the 3-item scan in
`references/dor-scan.md` against the file you just wrote; a failure means fix the plan, not skip
the checkpoint."* Two lines.

**G2 — no `## Constraints and Pins` section, though two consumers resolve conflicts by it. Severity: HIGH.**
Producer line: **no line exists** — the template goes `## Technical Approach` → `## Implementation
Phases` → `## Design Decisions` → `## Code Guidance`.
Consumers: orchestrate Step 8 A *"Conflicts resolve by the plan's Constraints and Pins"*;
`worker-dispatch.md` worker contract step 2 *"respecting the plan's Constraints and Pins"*; the
foreign-engine brief template literally has `Constraints:` and `Pins:` lines to fill.
**Fix (producer):** add to the template, after `## Code Guidance`:
`## Constraints and Pins` — *"**Constraints:** conventions and primitives this change must
compose. **Pins:** existing behaviour that must not change, named precisely enough to conflict
against."* `## Code Guidance` can fold into it or stay.

**G3 — no per-phase risk class. Severity: HIGH.**
Producer line: the phase block is `- **Goal:** / - **Files:** / - **Approach:**` — no risk field.
`## Security Review Required` is the nearest thing and answers a different question; mine says
"No" over a chunk carrying a migration.
Consumer: Step 5.2 gates the model tier, the backend, and whether fast-gates-only is allowed on
this. I recovered it from a filename containing `alembic/versions/`.
**Fix (producer):** one line in the phase block —
`- **Risk:** ordinary | migration | money | auth | tenant-isolation — [why]`, with a note that a
non-ordinary phase is never dispatched fast-gates-only.

**G4 — the plan does not record which ticket comments it was written against. Severity: HIGH.**
Producer line: `Fetch from ticketing tool — **including the ticket's comments** … newest statement
wins on conflict`. It is read, absorbed, and then invisible.
Consumer: Step 3 **signal 5** — *"comments contradict the description or the plan (newest wins…
a refined story with this signal goes back to the refine lane, not to a worker)"*. Firing that
signal requires knowing the plan's comment watermark. `created:` is a date, not a watermark.
**Fix (producer):** one frontmatter field — `comments_read_through: <newest comment id or
timestamp>` — plus one clause in Step 1: *"record the newest comment you read in
`comments_read_through:` so a later Lead can fire signal 5 cheaply."*

**G5 — no slot for repo-local DoR rows. Severity: MEDIUM.**
Producer line: `treat its items as ADDITIVE to the plan DoR above — both sets of criteria apply`.
It says the criteria apply; the template has nowhere to satisfy them. My "names the rollback
step" landed inside `## Technical Approach` because I chose to put it there.
Consumer: Step 1 — *"`quality/dor.md` plus `<repo>/.weside/dor.md` are the Lead's approval read at
the confirm: a plan that fails a row there goes back to the refine lane **with the row named**"*.
Naming the row requires finding it.
**Fix (producer):** one line in Step 4 — *"Every repo-local DoR row gets its own labelled line in
the plan (`**<Row name>:** …`), so the Lead can check it by name."*

**G6 — no exit criterion in the plan, though `/loop` is printed against it. Severity: MEDIUM.**
Producer line: `/loop <the round's task, verbatim from the plan's exit criterion>` — and
`long-running.md`: *"write the exit criterion into the **plan and the state file**"*. The template
has no such field, so the criterion exists only in Step 6's terminal output, which no later
session reads.
**Fix (producer):** add `- **Exit criterion:** [what someone else could run to decide "done"]` to
the `## Verification` block. It is one line and it is where the oracle already lives.

**G7 — `parallel_groups` semantics not stated by the producer. Severity: MEDIUM.**
Producer line: `When phases touch **disjoint files** and have **no ordering dependency** (phase N's
output does not feed phase N+1), they can run concurrently.`
Consumer Step 5.4: *"phases absent from every group run serially in plan order; **a group runs
after every lower-numbered phase has merged**; inside a group **≤ 2 concurrent**."* Neither the
barrier nor the cap appears producer-side, so a writer packing four phases into one group is
declaring something they were never told the meaning of.
**Fix (producer):** append to the independence-check note — *"Orchestrate reads a group as: it
starts only after every lower-numbered phase has **merged**, and runs at most 2 chunks
concurrently inside it. Size groups accordingly."* One sentence.
(The contradicting sentence in `docs/plan-format.md` — *"dispatched as concurrent sub-agents in a
single `Agent()` message"*, no cap — is **FORK — outside producer**.)

**G8 — `**Files:**` lists exclude generated artifacts and the foreign tests a change pulls in. Severity: MEDIUM.**
Producer line: `The per-phase **Files:** lists also feed orchestrate's disjoint guard — fill them
concretely (use the graphify Blast-Radius query above), not vaguely.` graphify indexes the backend
AST; it cannot know about `openapi.json` or a generated TS client, and my `## Documentation Impact`
named both while Phase 3's `**Files:**` did not.
Consumer: the Executor-selection paragraph — *"reconcile the file list with the prose before
dispatch — generated artifacts, `WORKER-REPORT.md`, and the foreign test files a new required
field or a new collaborator inside an existing function pulls in"*, with the observed failure
*"Three of five phases once stopped on that contradiction alone."*
**Fix (producer):** one clause — *"A phase's `**Files:**` includes what the change *causes* to
change: generated artifacts (OpenAPI spec, generated clients, snapshots) and the existing test
files whose call sites the change breaks (`rg` the symbol under `tests/`)."*

**G9 — the missing-verb phase is sequenced last. Severity: MEDIUM.**
Producer line: `- **Missing CLI verb:** [name it if the seed needs a shell dance — it ships with
the story, not as a transcript snippet]`. It says *ships with*, never *ships first*.
Consumer Step 5.8: *"a seed or assert the repo's CLI cannot do yet is a Lead-owned chunk … **cut in
wave 0** so its PR's merge window overlaps the build — not discovered at Step 8 B when every
worker is gone."* My Phase 4 lands in the last wave; in a cross-repo case that is a wave-blocking
"waiting on your merge in `<repo>`".
**Fix (producer):** extend the bracket — *"…and say which phase ships it; put that phase as early
as its own dependencies allow, and if it cannot be first, say why."*

**G10 — no `depends_on:` slot in frontmatter. Severity: MEDIUM.**
Producer line: **no line exists**. Frontmatter is `type / story / epic / created / status /
parallel_groups`.
Consumer Step 3.4: *"write `depends_on: [KEY]` into the dependents' plan frontmatter so the CLI
holds them"*. The Lead is instructed to write a field into a file whose format never declared it.
**Fix (producer):** add `depends_on: []  # optional: story keys that must merge first` to the
template frontmatter with a one-clause note. (Its absence from `docs/plan-format.md` is
**FORK — outside producer**.)

**G11 — `epic:` collides with Step 0's single-Story test. Severity: LOW–MEDIUM. FORK — outside producer.**
Producer line: `epic: {EPIC-SLUG-OR-KEY} … **REQUIRED** when the story belongs to an Epic` — and the
Rules bullet: *"a missing `epic:` makes the story invisible to orchestration"*. Correct and
necessary. But Step 0 resolves **single Story** only when *"no Epic plan / **no other story shares
it as `epic:`**"*, so obeying the producer can flip a deliberately-single-key invocation into the
Epic path. Nothing the producer can fix without breaking the ready-set. Belongs in orchestrate
Step 0 (single key given → single Story, regardless of siblings).

**G12 — `/goal` bar is undecidable for a migration. Severity: LOW.**
Producer line: `Add a /goal line **only** when being wrong about "am I done" is expensive — money,
auth, tenant isolation, **a migration**, or unattended work`. `long-running.md` narrows it to *"a
migration or a **cutover with a hard finish line**"*. This story has an additive migration behind a
flag and no cutover. I judged no `/goal`; a different session reads the SKILL's flat list and
prints one.
**Fix (producer):** align the SKILL's enumeration with the reference — *"a migration with a cutover
or a backfill window"*.

**G13 — Verification field labels drift from the receipt they become. Severity: LOW.**
Producer line: `- **Assert:** …` / `- **Not provable here:** …`
Consumer (`verification.md` receipt, copied into the PR by `pr-creator`): `**Asserted:**` /
`**Not proven:**`. The integration step writes the receipt *into this same section*, so the plan
ends up with two vocabularies for one thing and no rule about which survives.
**Fix (producer):** rename the two bullets to `**Asserted:**` and `**Not proven:**` so the intent
block and the receipt are the same shape, and the receipt overwrites cleanly.

**G14 — no state-file path in the producer's output. Severity: LOW.**
Producer line: Step 6.6 prints `Recommended next: /we:orchestrate {TICKET}` and, for long-running
work, the `/loop` block. `programme-discipline.md` (which the SKILL's Rules link) says *"Every
session and every loop round **starts** by reading it"* — but the plan never names
`docs/plans/{TICKET}-state.md` and the producer never creates it.
**Fix (producer):** one line in Step 6.6's output block — `State file: docs/plans/{TICKET}-state.md
(the Lead creates it on the first run).` Cheap, and it makes the loop's memory discoverable.

**G15 — `## Verification` is in the SKILL template but not in `docs/plan-format.md`. Severity: LOW. FORK — outside producer.**
`plan-format.md` calls itself *"the **build contract** … Changes here are versioned and require
explicit consideration of both sides"*, yet its Full Template has no `## Verification`, no
`## Documentation Impact` cascade prose, no `type:` and no `epic:`. The producer is ahead of the
contract document. Fix belongs in `docs/plan-format.md`.

---

## Cuttable — producer lines I obeyed without needing to be told

`[UNPROMPTED]` — I would have produced identical output with these deleted.

1. The whole **"Writing Effective Acceptance Criteria"** section (SKILL lines 49–78): the formula,
   `Bad: "Dark mode works."`, the Given/When/Then example block, and the Red Flags table
   (`| "Feature exists" | No access path | Add "via [button/menu/route]" |`). The template already
   shows `1. **Given** [context] **When** [action] **Then** [result]`, and `plan-format.md` + the
   DoR both restate the GWT requirement. Three statements of one rule; the template alone carries it.
2. `**Ticket is MINIMAL. Plan contains ALL details.**` — stated in the Output table, again as the
   Step 3 heading `### Step 3: Update Ticket (MINIMAL)`, again in `Rules` bullet 1
   (`Ticket stays MINIMAL; the plan carries ALL detail`), and again in `dor.md`'s
   `**Details are in the Plan, NOT in the ticket.**` Keep one.
3. `Research codebase thoroughly, then create detailed plan.` (Step 4 opening line) — and
   `**Read the plan and the files it names in full.** A partially-read plan produces a partially-built
   story… Load more files than feel necessary`. In a plan-writing skill on Opus, "read the code
   before planning" is not a behaviour that needs instructing; the graphify + TurboVault blocks
   above it already operationalise it.
4. `**Execute these 6 commands IN ORDER. No explanations. No summaries between steps.**` — the
   numbered list is already ordered.
5. The triple stop: `⛔ **ExitPlanMode approval = "continue executing Step 6", NOT "stop and
   summarize"!**`, `⛔ **STOP after step 6. No implementation. No /we:orchestrate. No branch. No
   code.**`, and `Rules` bullet `⛔ NEVER implement, create branches, write code, or auto-continue`.
   One of the three is enough. (The *rule* is worth keeping — the repetition is not.)
6. `(~/.claude/plans/ is temporary — docs/plans/ is permanent!)` in Step 6.1 and again in `Rules`
   bullet 1 (`Save it to docs/plans/{TICKET}-story.md via Write() — ~/.claude/plans/ is NOT permanent`).
7. `Empty rows are fine if nothing was discussed.` (Design Decisions guidance) — never load-bearing;
   an empty table is self-evidently allowed.
8. The **phased-is-not-an-epic** rule stated three times: Step 2's bullet pair
   (`- **One coherent change with several phases** … → this stays a **single Story**`), the
   Execution Surface bullet (`**The split instinct is the signal.**`), and `Rules` bullet
   (`A single COHERENT change that is merely phased is NOT an epic`). Once, in Execution Surface.
9. **Vision Alignment (3 Levels)** + **Training on the Job** (~25 lines): no `.weside/vision.md`,
   no Companion → Level 1 fired, i.e. "skip". The one-time hint text is a nag with its own
   "never ask again" clause. Both are dead weight in the common path.
10. **Create Mode** and **Design Session Mode** (~20 lines) — both end in "continue as Refine Mode
    Steps 4–6". They are a routing table that could be three lines at the top.

The keepers, for contrast — lines I would **not** have produced unprompted: the `epic:` frontmatter
requirement and its rationale; the `parallel_groups` independence check; the `## Verification`
block, and specifically `**Missing CLI verb:**`, which is the single field in this plan that
saved the Lead a Step-8-B discovery; the `## Documentation Impact` cascade; the graphify
Blast-Radius query; and the Step 6.3 main-worktree resolution (`git worktree list --porcelain |
awk …`), which is a real trap.

---

## Grade

**3 / 5 for the hand-off.**

The plan gets the *mechanically* checked things right and one hard thing right: the DoR scan
passes on all three items, `epic:` is populated, the phase headers match the regex exactly, the
`**Files:**` lists are concrete enough that the disjointness intersection is a real computation
rather than a guess, and `**Missing CLI verb:**` caught the one gap that Step 5.8 exists to
prevent being discovered when every worker is gone. That is more than a template usually buys.
What it does not carry is everything the *judgement* half of orchestrate reads: no risk class, so
a migration chunk had to be classified off a filename; no Constraints-and-Pins section, so two
separate references instruct the Lead to resolve conflicts against a section the producer never
writes and a foreign-engine brief ships an empty `Pins:` line; no comment watermark, so Step 3's
signal 5 — the one signal aimed squarely at *refined* stories — costs a manual clause-by-clause
diff every wave; no exit criterion in the artifact, so the `/loop` line the producer printed to a
terminal is gone by the time a fresh Lead needs it; and `parallel_groups` declared under semantics
the producer never states, which happened to coincide with the consumer's here only because the
group had exactly two members. The seven invented blocks in the best-specified phase's brief are
the honest measure: the plan is a good *specification* and a thin *dispatch contract*, and
orchestrate needs both. G1–G4 are each a one-to-two-line producer edit, which is the encouraging
part — the shortening this skill is about can pay for all four out of the ten cuttable blocks
above and still come out shorter.
