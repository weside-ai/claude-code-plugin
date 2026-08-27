<!-- markdownlint-disable -->

# Round 3 — Scenario (a)

Simulated table-top run of `/we:story PROJ-812`, scenario (a) (contradicting comments),
against the round-3 revision of `we/skills/story/SKILL.md`. Session model Sonnet,
Agent Teams OFF, mode `acceptEdits`, cwd = main worktree `/home/user/proj` on `main`.

Nothing was executed. `[USER]` marks invented user answers. `[UNPROMPTED]` marks lines I
obeyed that I would have done anyway without the skill saying so.

---

## Trace

### Prerequisites

1. `Read("${CLAUDE_PLUGIN_ROOT}/quality/dor.md")` → the plugin DoR. Note the Required /
   In-Plan / Recommended split and the pointer to `references/dor-scan.md`.
2. `Read("${CLAUDE_PLUGIN_ROOT}/references/verification.md")` → oracle ladder, receipt shape,
   "missing verb is a bug in the CLI", `.weside/verify.md` recipe file.
3. `Read("${CLAUDE_PLUGIN_ROOT}/references/long-running.md")` → `/loop` default, `/goal`
   exception (money/auth/tenant-isolation), trigger = 4+ phases OR non-empty `depends_on:`
   OR user away.
4. `Bash("git rev-parse --show-toplevel")` → `/home/user/proj`.
5. `Read("/home/user/proj/.weside/dor.md")` → exists, one additive row:
   *"Every story names the rollback step."*
   → per the skill this owes "its own labelled line in the plan (`**<Row name>:** …`)".
   **First guessing point:** the plan template in Step 3 has no slot for it, and the skill
   does not say which section it belongs in. Parked; resolved by improvisation in Step 3.
6. `Read("/home/user/proj/CONTEXT.md")` → glossary exists; **"workspace" is `_Avoid_`, use
   "tenant"**. Binding for "the ticket and the plan".

Not read, because the skill does not ask for it at this point and nothing referenced it:
`.weside/config.json` (deferred to Step 3), `.weside/council.json`, `.weside/weside.md`.

### Step 1 — Load

7. `mcp__atlassian__jira_get_issue(issue_key="PROJ-812", comment_limit=50)`
   → Summary "Workspace admins can revoke a member's API token";
     Description "As an admin I want to revoke a member's API token so that a leaked token
     stops working. Should revoke instantly.";
     Status **Backlog**; parent **PROJ-800** ("Tenant access control");
     comments 10401 (14d, PO), 10437 (3d, tech lead), 10453 (yesterday, PO).
   Derived: `epic: PROJ-800`, `comments_read_through: 10453`.
   `{TICKET}` fixed here as `PROJ-812` and never varied.
8. `Bash("ls docs/plans/PROJ-812-story.md")` → not found. New plan, not a refine-in-place.
9. `Read("/home/user/proj/docs/plans/PROJ-800-epic.md")` — **[UNPROMPTED]**. Step 1 only tells
   me to take `epic:` from the parent key; reading the epic plan for the Success Criteria
   frame is my own habit. (It paid: the epic frames access control as tenant-scoped, which
   is what makes the authz AC in Phase 4 tenant-isolation-classed.)

**Conflicts found, unprompted-in-shape but prompted-in-principle** (ticketing.md: newest
wins, name the conflict to the user):

- 10401 (PO, 14d): "accept a 60s window" — **superseded**.
- 10437 (tech lead, 3d): "no 60s window, cache must be invalidated on revoke" + a *new*
  requirement not in the description: **"revocation must be auditable, one row per revoke."**
- 10453 (PO, yesterday): agrees on cache invalidation; **opens** "do we also need self-revoke
  for the member themselves? Open."

So the ticket arrives with one resolved contradiction, one silently-added requirement, and
one live open question. The skill handles the first well and the third not at all (see
*New defects*).

### Step 2 — Understand (INTERACTIVE, grill-style, one question at a time)

10. `Bash("ls /home/user/proj/.weside/vision.md")` → absent → skip silently, as instructed.
11. weside MCP Companion check — **guessing point.** The skill's vision clause says "or a
    Companion is connected via weside MCP", and `.weside/council.json` exists, but the skill
    gives no detection call and no branch for "council configured, vision absent". I did not
    call `mcp__plugin_we_weside-mcp__get_council`; I read "No vision configured → skip
    silently" as covering it. Improvised.

Not vague — the summary and the "why" are both clear — so no brainstorming detour.

**Q1 (contradiction).** "Comments 10401 and 10437 disagree about a 60-second window. Newest
wins, so I'd build zero-window: `verify_token` consults revocation state, and the revoke path
invalidates the cache entry synchronously. Confirm?"
`[USER]` *"Yes, kill the window. The tech lead is right — a 60s window on a leaked token is
the bug, not the mitigation."*

**Q2 (the added requirement).** "10437 also adds an audit requirement that is nowhere in the
description: one row per revoke. I'd model it as an append-only `token_revocations` table
with actor, target member, token id, timestamp, reason — never updated, never deleted.
Reason optional?"
`[USER]` *"Yes. Reason optional, free text, max 200 chars."*

**Q3 (the open question).** "10453 asks whether members can self-revoke. I recommend NO for
this story: it changes the authz shape from admin-over-member to actor-over-own and needs its
own UI surface. I'd park it as a follow-up and record the parking in my ticket comment."
`[USER]` *"Agreed, out of scope. Park it, don't file a ticket yet."*

**Q4 (glossary).** "`CONTEXT.md` marks *workspace* as `_Avoid_` in favour of *tenant*, but the
ticket summary says 'Workspace admins'. I'll write plan and ticket in *tenant* vocabulary.
Separately, *revoke* is doing two jobs here — deleting the token row vs. making it stop
authenticating. I'd record in `CONTEXT.md`: **Revocation** — a token is revoked when
`verify_token` rejects it, not when its row is deleted; `_Avoid_`: 'disable', 'expire',
'deactivate'. Record it?"
`[USER]` *"Yes, add it."* (the scenario's stipulated acceptance)

**Q5 (the cache, read from the codebase — the skill says read the codebase for anything
discoverable there).**
12. `Grep(pattern="verify_token|TokenCache|token_cache", include="*.py")`
    → `src/auth/tokens.py`, `src/auth/token_cache.py`, `src/api/deps.py`.
13. `Grep(pattern="revoke|revocation", include="*.py")` → nothing but a docstring.
14. `Grep(pattern="token", path="web/src", include="*.ts*")`
    → `web/src/api/tokens.ts`, `web/src/pages/MemberDetail.tsx`.
15. `Bash("ls migrations/versions | tail -5")` → alembic-style chain, head known.
    "So there is one entry point, `verify_token`, and a Redis-backed cache with TTL 60.
    Invalidation is a single `DEL` on revoke plus a negative marker so a racing read cannot
    repopulate. Right?"
    `[USER]` *"Right. Redis, TTL 60, one entry point. The negative marker is a good catch."*

**Q6 (repo-local DoR row).** "Your `.weside/dor.md` requires a named rollback step. I'd say:
revert the deploy; the `token_revocations` table is additive and stays — dropping it would
destroy audit rows. So rollback is deploy-only, migration is forward-only. OK?"
`[USER]` *"Yes. Never drop that table."*

**Size check.** Skill Step 2's fork: many independent slices vs. one coherent change with
several phases. This is the second — one change through migration → service → API → UI, plus
the verification verbs. Stays a Story with a phased plan. No `/we:epic` print, no STOP.

### Step 3 — Create Plan

16. `EnterPlanMode`.
17. TurboVault absent → printed once, verbatim:
    "⚠️ TurboVault unavailable — using grep fallback; architecture context may be incomplete.
    Check the MCP config."
18. `Grep(pattern="token|auth|revoke", include="*.md")` → `docs/architecture/auth.md`,
    `docs/architecture/tenancy.md`.
19. `Glob(pattern="docs/architecture/**/*.md")` → 6 files; read `auth.md` and `tenancy.md`.
20. `Read("/home/user/proj/.weside/config.json")` → `tools.graphify: false`.
    → the config is present and false, so the "absent-and-`graphify --version`-answers"
    branch does not apply. **Neither holds** → derive `Files:` with `rg`, and write
    "`Files:` lists are grep-derived — no code graph" into Technical Approach. I did **not**
    run `graphify --version` — the config settles it. This branch is written clearly enough
    that it needed no improvisation.
21. `Bash("rg -n --files-with-matches 'verify_token' -g '*.py'")` → the Phase 3 file list.
22. `Bash("rg -n --files-with-matches 'tokens' web/src -g '*.ts*'")` → the Phase 5 file list.
23. `Bash("ls /home/user/proj/.weside/verify.md")` → **absent**. Per verification.md: say once
    that the repo has no recipe, verify with what the stack offers, propose adding it in the
    same PR → it goes under Documentation Impact, as Step 3's Verification block instructs.
    Because the file is absent there are no existing verbs to audit against the ACs, so the
    "a verb that cannot go red is as absent as one that does not exist" paragraph collapses
    to "everything is missing" — correct outcome, but the paragraph is written for the
    file-present case only.

**Missing CLI verb.** The ACs need: mint a token for a member, then assert it stops
authenticating. The repo's CLI (`proj-cli`) has neither. Named: `proj-cli token issue
--member <id>` and `proj-cli token check <token>` (exit 0 authenticates / exit 1 rejected).
Earliest phase its own dependencies allow: **Phase 1** — `token check` only needs the
existing `verify_token`, `token issue` only needs the existing token model. So it is first,
and the plan says so.

**Repo-local DoR row — improvised.** The template has no slot. I put a labelled line
`**Rollback step:**` inside *Constraints and Pins*, because that is the section about "what
must not change". This is a guess; another run would as reasonably put it under Technical
Approach or invent a `## Rollback` section, and `/we:orchestrate` gates on the row by name.

24. `ExitPlanMode(plan=<the plan below>)`.

### Step 4 — Approval

`[USER]` *"Approved. One thing: put the UI last, I want the API usable before anyone sees a
button."* → already the case (Phase 5). Re-presented once, approved.

### Step 5 — see the item-by-item table below.

---

## Step 5, item by item

| # | Executable as written here? | Actual effect |
|---|---|---|
| **0 — resolve main worktree** | **Yes.** `git worktree list --porcelain \| awk '/^worktree /{p=$2} /^branch refs\/heads\/main$/{print p; exit}'` runs and prints `/home/user/proj`. Non-empty, so no skip-step-4 branch. The instruction "print the path and use it literally" is unambiguous and correct. | Printed `/home/user/proj`. I now hold the path as text, not as shell state — which is exactly what item 4 then fails to honour. |
| **1 — save plan** | **Yes, with one silent substitution.** Write to `/home/user/proj/docs/plans/PROJ-812-story.md` with `status: approved`, `story: PROJ-812`. The `CONTEXT.md` clause ("write the accepted glossary entry now") is clear and I executed it: `Edit("/home/user/proj/CONTEXT.md")` adding the **Revocation** row. | Plan written, 118 lines, `comments_read_through: 10453`. `CONTEXT.md` gained one row. **Not** covered: the ticket *summary* still says "Workspace admins" — the `_Avoid_` term sits in the one field Step 5.3 never touches (see New defects). |
| **2 — dor-scan** | **Yes.** Ran the 3 checks against the file I just wrote: (1) `Given`+`When`+`Then` present — 5 ACs; (2) Context section 640 chars > 50; (3) `^### Phase 1:` present, 5 phase headers. | PASS. **But it scanned a file that is about to change:** item 3 rewrites `comments_read_through`, and nothing re-scans. Here the rewrite is one frontmatter value so the scan verdict survives; the ordering is still wrong in principle. |
| **3 — ticket, one pass** | **Partly — the ready-state clause forced a question the skill anticipated, the rest is under-specified.** `.weside/orchestrate.md` is absent, so I need "the one meaning *refined, not yet started*". `mcp__atlassian__jira_get_transitions("PROJ-812")` → `Selected for Development`, `In Progress`, `Done`. Two could plausibly mean it, so per the skill I **asked once**: `[USER]` *"Selected for Development."* Then `jira_transition_issue` bare (no comment field — ticketing.md's ADF trap), then `jira_get_issue` to verify → status is `Selected for Development`. ✔ Then `jira_update_issue(description=<minimal body>)`. Then `jira_add_comment(...)` → new id **10461**. | Ticket moved and verified; description replaced with the 5-line minimal body; one comment posted naming the resolved contradiction (60s window dead), the added audit requirement, and the parked self-revoke question. **Then the instruction "set the plan's `comments_read_through:` to **its** id" — which requires an edit to a file items 1 and 2 already finalised, and item 4 is about to commit. The skill never says to re-open the file.** I improvised a 4th call: `Edit(plan, "comments_read_through: 10453" → "comments_read_through: 10461")`. Also improvised: `jira_update_issue(summary="Tenant admins can revoke a member's API token")` to kill the `_Avoid_` term — **not instructed**. |
| **4 — commit the plan** | **NO — the snippet as written cannot work in this world.** It opens `[ -n "$MAIN_WORKTREE" ] \|\| { echo "WARN: no worktree on main — plan saved, not committed."; exit; }`. `$MAIN_WORKTREE` is **never assigned anywhere in the skill**, and item 0 explicitly says shell state does not survive between tool calls — it says to use the *printed path literally*, which is the opposite of a variable. Run literally, the guard sees the empty string. | **The literal run prints "WARN: no worktree on main — plan saved, not committed." and exits — while standing in the main worktree, with `main` checked out.** The plan is never committed, never pushed, and the WARN text actively lies about why. I improvised: substituted `/home/user/proj` for `$MAIN_WORKTREE` in all three lines and ran `cd /home/user/proj && git add docs/plans/PROJ-812-story.md CONTEXT.md && git commit -m "docs: add PROJ-812 plan — Tenant admins can revoke a member's API token"` → committed; `git push` → succeeded (main not protected in this repo). Note the `git add` list is hardcoded to `CONTEXT.md`; had the user *declined* the glossary offer, `git add CONTEXT.md` would fail on a path with no changes — harmless with `git add` but it would still be a wrong path in the list. |
| **5 — checkpoint** | **Yes.** `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/orchestration.py story checkpoint PROJ-812 refined`. The script exists in the plugin tree (`we/scripts/orchestration.py`), so this is a real invocation, not a reference to something absent. | Checkpoint row written, phase `refined`. Matches what orchestrate Step 2 reads to classify PROJ-812 as `refined` → DEVELOP lane. |
| **6 — vault links** | **Yes, trivially.** TurboVault MCP is not available → "Skip silently without TurboVault." | No output, no call. Correct and unambiguous. |
| **7 — output + execution-surface** | **NO, not as written — the literal block contradicts the heuristic it points at.** Agent Teams is OFF. The *Execution Surface* section says: recommend `--solo` "whenever Agent Teams is disabled: dispatch aborts on orchestrate's own prerequisites there, so `--solo` is the only shape that runs. Say so, and say that enabling Agent Teams unlocks the other one." But the fenced output block hardcodes `Recommended next: /we:orchestrate {TICKET}` with `--solo` demoted to the parenthetical. A literal-minded run emits the recommendation that cannot execute. | I obeyed the **prose**, not the block, and inverted it (full text below). Second gap: **nothing in the skill tells me how to detect Agent Teams state** — no flag file, no tool, no "ask". I only knew it was off because the scenario told me. A real session would emit the block's default and be wrong. The `/loop` clause worked well: 5 phases ≥ 4 fires the trigger; the oracle is *not* scriptable until Phase 1 ships the verbs, and the skill has the exact sentence for that case, so I said it. `/goal` also fires — auth path — per long-running.md's critical bar. |

**Score of item-by-item executability:** 0 ✔, 1 ✔, 2 ✔(ordering wrong), 3 ✔ with one
improvised call and one uncovered field, 4 ✘ (fails closed and lies), 5 ✔, 6 ✔, 7 ✘
(self-contradictory + undetectable precondition).

---

## The plan I would have written

`/home/user/proj/docs/plans/PROJ-812-story.md`

```markdown
---
type: story-plan
story: PROJ-812
epic: PROJ-800
depends_on: []
comments_read_through: 10461
created: 2026-08-27
status: approved
parallel_groups: [[1, 2]]
---

# Plan: Tenant admins can revoke a member's API token

## Context

A leaked API token is currently only as dead as the cache lets it be: `verify_token` reads a
Redis entry with a 60-second TTL, so a token stays live for up to a minute after anyone
decides it should not be. The PO originally accepted that window (comment 10401); the tech
lead overruled it three days ago (10437) and the PO agreed (10453), so the window is out of
scope as a mitigation and in scope as the bug — revocation must take effect on the next
request, not the next minute. 10437 also added a requirement the description never carried:
every revocation leaves exactly one audit row, because "who killed this token and when" is
the question a leak post-mortem actually asks. Whether a member can revoke their *own* token
is open (10453) and deliberately parked: it changes the authorisation shape from
admin-over-member to actor-over-own and earns its own story. The repo has no way to mint or
check a token from the command line today, which is why the first phase is tooling and not
the feature. Vocabulary: this repo says **tenant**, never *workspace* (`CONTEXT.md`), even
though the Jira summary did.

## Acceptance Criteria

1. **Given** a tenant admin and a member of that tenant holding a live API token,
   **When** the admin revokes that token,
   **Then** the very next authenticated request with it is rejected with 401 — with no
   dependency on cache expiry.
2. **Given** a revocation has just happened,
   **When** the `token_revocations` table is read,
   **Then** it holds exactly one new row naming the acting admin, the target member, the
   token id and a UTC timestamp, and no prior row was modified.
3. **Given** an admin of tenant A,
   **When** they attempt to revoke a token belonging to a member of tenant B,
   **Then** the request is rejected with 404 (not 403 — existence is not disclosed) and no
   audit row is written.
4. **Given** a member without the admin role,
   **When** they call the revoke endpoint for any token including their own,
   **Then** the request is rejected with 403 and no audit row is written.
5. **Given** a tenant admin on the member detail screen,
   **When** they choose to revoke a listed API token and confirm,
   **Then** the token disappears from the list without a reload and a confirmation is shown.

## User Journey

1. An admin learns a member's token has leaked and opens that member's detail screen.
2. They see the member's API tokens, each with a **Revoke** control.
3. They revoke the leaked one and confirm the destructive-action dialog.
4. The token leaves the list, a confirmation appears, and the leaked token stops
   authenticating on its next use.

## Testing Requirements

- Unit tests for the revocation service: cache entry deleted, negative marker written,
  audit row built exactly once (Phase 3).
- Unit tests for the migration's table shape and its append-only constraint (Phase 2).
- Integration tests against a real Postgres — suite `tests/integration/test_revocation.py`,
  database `proj_test` (`alembic upgrade head` first) — covering AC1 (issue → verify OK →
  revoke → verify 401 with no sleep), AC2, AC3 and AC4 (Phases 3 and 4). Mocked sessions
  cannot see the cross-tenant filter or the ON CONFLICT arbiter, so these do not run against
  a fake.
- Component test for the revoke control's confirm dialog and optimistic removal (Phase 5).
- Edge cases: revoking an already-revoked token is idempotent and writes no second row;
  a racing `verify_token` between DEL and marker write must not repopulate the cache.

## Verification

- **Oracle:** `ui + cli`. `cli` because AC1–AC4 are endpoint-and-database claims with
  machine-readable answers. `ui` on top because AC5 says the admin can *see* and *reach* the
  Revoke control, and an endpoint nothing calls answers 200 all day — reachability is not
  provable from the API.
- **Seed:** `proj-cli token issue --member m_42 --tenant t_1` (Phase 1 verb), then
  `curl -X DELETE $API/tenants/t_1/members/m_42/tokens/$TOKEN_ID -H "Authorization: Bearer $ADMIN"`.
- **Asserted:** `proj-cli token check $TOKEN` exits 1 immediately after the revoke (no sleep);
  `GET /me` with that token returns 401; `SELECT count(*) FROM token_revocations WHERE
  token_id=$TOKEN_ID` = 1; the cross-tenant call returns 404 and leaves that count at 0;
  in the browser, the member-detail route shows a **Revoke** control by accessible name and
  the row is gone from the a11y tree after confirming.
- **Not proven:** that no *other* code path caches an authentication decision outside
  `verify_token` — this oracle only exercises the one entry point; a follow-up audit of
  auth read paths owes that, and it is named as such in the PR.
- **Exit criterion:** `proj-cli token issue` → `proj-cli token check` exits 0 → revoke via
  API → `proj-cli token check` exits 1 with no sleep, and `token_revocations` gained exactly
  one row. Someone else can run those four commands and decide "done".
- **Missing CLI verb:** `proj-cli token issue --member <id> --tenant <id>` and
  `proj-cli token check <token>` (exit 0 = authenticates, exit 1 = rejected). Neither exists.
  Both ship in **Phase 1** — `check` only needs the existing `verify_token` and `issue` only
  needs the existing token model, so nothing holds them back and everything downstream needs
  them. The repo has no `.weside/verify.md`, so there were no existing verbs to audit
  against the ACs; adding that file is proposed under Documentation Impact.

## Technical Approach

**Patterns:** revocation state is authoritative at `verify_token`, the single auth entry
point — no second check anywhere. The cache invalidation is DEL + short-lived negative
marker, so a read racing the delete cannot repopulate a live entry. The audit table is
append-only and additive: nothing updates or deletes a row, and no code path drops it.
Authorisation for the endpoint is tenant-scoped first, role-checked second, so a
cross-tenant target is indistinguishable from a missing one (404, per AC3). Architecture
refs: `docs/architecture/auth.md` (token lifecycle), `docs/architecture/tenancy.md`
(tenant scoping on admin routes).

`Files:` lists are grep-derived — no code graph. (`.weside/config.json` sets
`tools.graphify: false`.)

⚠️ TurboVault unavailable — architecture context above comes from a grep over `docs/`, so
it may be incomplete.

## Implementation Phases

### Phase 1: Verification verbs
- **Goal:** a token can be minted and checked from the command line, so every later phase
  has a red/green oracle that is not a test the author also wrote.
- **Files:** `cli/commands/token.py`, `cli/main.py`, `tests/cli/test_token_cmds.py`,
  `docs/cli-reference.md` (generated).
- **Risk:** ordinary — read-only against auth, no schema, no money path. The `issue` verb
  mints real credentials, so it refuses to run against a non-dev API base.
- **Approach:** thin wrappers over the existing token model and `verify_token`; `check`
  exits 1 on rejection so a loop can branch on it.

### Phase 2: Audit table
- **Goal:** `token_revocations` exists, append-only, with the columns AC2 names.
- **Files:** `migrations/versions/<new>_token_revocations.py`, `src/models/revocation.py`,
  `src/models/__init__.py`, `tests/unit/test_revocation_model.py`.
- **Risk:** **migration** — on a new table only; nothing existing is rewritten and no
  backfill runs, which is what makes it forward-only-safe.
- **Approach:** additive DDL, no data migration; a DB-level rule or trigger rejects UPDATE
  and DELETE so "append-only" is a constraint and not a convention.

### Phase 3: Revocation service + cache invalidation
- **Goal:** revoking makes `verify_token` reject on the next call, and writes exactly one
  audit row.
- **Files:** `src/auth/revocation_service.py` (new), `src/auth/token_cache.py`,
  `src/auth/tokens.py`, `tests/unit/test_revocation_service.py`,
  `tests/integration/test_revocation.py`, `tests/unit/test_token_cache.py` (existing —
  its TTL-window assertions pin the old behaviour and flip here).
- **Risk:** **auth** — this is the authentication decision path itself; a fail-open here
  makes a revoked token live forever rather than for 60 seconds.
- **Approach:** revoke writes the audit row and invalidates in one transaction boundary;
  `verify_token` consults the negative marker before the positive cache. Idempotent on a
  second revoke of the same token — no second row.

### Phase 4: Admin API endpoint
- **Goal:** `DELETE /tenants/{tenant}/members/{member}/tokens/{token}` exists, admin-only,
  tenant-scoped.
- **Files:** `src/api/routes/tokens.py`, `src/api/deps.py`, `openapi.json` (generated),
  `web/src/api/generated/` (generated client), `tests/integration/test_revocation.py`,
  `tests/api/test_token_routes.py`.
- **Risk:** **tenant-isolation** (and auth) — on the admin route's scoping: the tenant
  filter, not the role check, is what stops an admin of A reaching a token of B.
- **Approach:** tenant scope resolved from the path and intersected with the caller's
  tenant before the row is ever loaded; a miss is a 404, never a 403.

### Phase 5: Member-detail revoke control
- **Goal:** an admin can reach the revocation from the UI.
- **Files:** `web/src/pages/MemberDetail.tsx`, `web/src/api/tokens.ts`,
  `web/src/components/ConfirmDialog.tsx`, `web/src/pages/__tests__/MemberDetail.test.tsx`.
- **Risk:** ordinary.
- **Approach:** destructive-action confirm dialog, optimistic removal with rollback on
  error, the native error surfaced in the toast.

## Constraints and Pins

**Constraints:** `verify_token` stays the single authentication entry point — no second
revocation check elsewhere. The audit table is written only through the revocation service,
with the acting admin's id, never a service principal. Admin routes are tenant-scoped before
the role check.

**Pins:** unrevoked tokens keep their existing cache behaviour and TTL — this story removes
the *window on revocation*, not the cache. The 401 body shape for a rejected token is
unchanged. No existing token row is deleted by a revoke; the token remains listed as revoked
in the data model.

**Rollback step:** revert the deploy. The `token_revocations` migration is **forward-only**
and is not reverted — the table is additive, nothing reads it on the old code path, and
dropping it would destroy audit rows. (This line answers `.weside/dor.md`'s row *"Every story
names the rollback step."*)

## Design Decisions

| Decision | Alternatives Considered | Why This |
|---|---|---|
| Zero-window revocation via cache invalidation | Accept a 60s window (PO, comment 10401); shorten the TTL to 5s | Newest statement wins (10437, agreed in 10453). A window is the bug a leaked token exploits; a shorter TTL is a smaller bug, not a fix, and costs cache hit rate. |
| DEL + negative marker | DEL alone | A read racing the delete would repopulate a live entry from the database and the token survives the revoke. |
| Append-only audit table with a DB-level UPDATE/DELETE rule | A `revoked_at` column on the token row; application-level convention | One row per revoke is the requirement (10437); a column holds only the last state, and a convention is not a constraint. |
| Cross-tenant target returns 404, not 403 | 403 | A 403 discloses that a token id exists in another tenant. |
| CLI verbs first, in Phase 1 | Verify with curl snippets in the PR body | verification.md: a missing verb is a bug in the CLI, and transcripts rot. It is also what makes the `/loop` round honest. |
| Self-revoke deferred | Build it now behind the same endpoint | Different authorisation shape (actor-over-own) and its own UI surface; PO left it open in 10453 and confirmed the parking. |
| Forward-only migration | Reversible downgrade | A downgrade drops audit rows, which is the one thing this story exists to keep. |

## Code Guidance

**DO:** consult revocation state inside `verify_token`; write the audit row and invalidate
the cache within one transaction boundary; scope by tenant before loading the row; make a
repeat revoke idempotent.

**DON'T:** add a second revocation check outside `verify_token`; update or delete an audit
row; return 403 for a cross-tenant target; rely on TTL expiry for any part of AC1; widen the
endpoint to non-admin callers "since self-revoke is coming".

## Security Review Required

**Yes** — the change sits on the authentication decision path and on an admin route's
tenant boundary. Two failure modes to review explicitly: a fail-open in `verify_token` when
the cache or marker read errors, and a tenant filter applied after the row is loaded.

## Documentation Impact

- **Docstrings** — `revocation_service.revoke()` carries the window/marker reasoning and why
  a repeat revoke writes no second row; `token_cache` carries the negative-marker contract.
- **Architecture doc** — `docs/architecture/auth.md`: the token lifecycle gains a revoked
  state and the cache section loses "worst case 60s".
- **ADR** — none. Hard to reverse (forward-only migration) but neither surprising nor a real
  trade-off once 10437 settled it; the Design Decisions table carries it.
- **Generated** — `openapi.json`, the generated web client, `docs/cli-reference.md`.
- **New doc** — `.weside/verify.md`. The repo has none, so every future story re-derives how
  DEV comes up and which verbs exist; that cannot live in a docstring because it is about the
  repo's operation, not about one module. Proposed in this PR alongside the Phase 1 verbs.
```

### The output block I emitted at Step 5.7

```
Plan saved to docs/plans/PROJ-812-story.md. /we:story DONE.
State file: docs/plans/PROJ-812-state.md (the Lead creates it on the first run).

Recommended next: /we:orchestrate PROJ-812 --solo   ← Agent Teams is disabled, so phase
dispatch aborts on orchestrate's own prerequisites; --solo is the only shape that runs.
Enabling Agent Teams unlocks the dispatched shape, which is what this plan actually wants:
5 phases, parallel wave {1,2}, and an auth-classed chunk that benefits from neutral review.

Long-running:
  /loop Ship the next unmerged phase of PROJ-812, then run the exit criterion: proj-cli
        token issue → token check exits 0 → revoke via API → token check exits 1 with no
        sleep, and token_revocations gained exactly one row.
  /goal token_revocations has exactly one row per revoke and a revoked token fails
        proj-cli token check with no sleep     ← auth path; wrong-about-done is expensive

⚠️ The oracle is not scriptable yet — `proj-cli token issue` and `token check` do not exist.
The first round's job is Phase 1, which ships them; do not start an unattended loop before it
merges.
```

---

## Round-2 verdict table

Round 2 asserted that all eight live in `we/skills/story/SKILL.md` and none is a FORK. I agree
with that scoping for all eight — every fix I would need is inside my file list.

| # | Round-2 defect | Verdict | Evidence from this run |
|---|---|---|---|
| **N1** | Step 5.0 is a bare assignment that prints nothing, so `$MAIN_WORKTREE` is empty in 5.1 and 5.4; 5.4 announces "no worktree on main" on a repo standing on main · *blocking* | **PARTIALLY FIXED** | The 5.0 half closed cleanly and the 5.1 half with it. Step 5.0 is now a bare command that **prints** the path, carries the sentence "Shell state does not survive between tool calls, so **print the path and use it literally**", and 5.1 takes a `<main-worktree>` placeholder instead of a `$VAR` — trace 5.0/5.1: I got `/home/user/proj` in the tool result and wrote a literal path, no `$MAIN_WORKTREE` directory created. **The 5.4 half did not close, and the edit made it structurally worse:** removing the assignment from 5.0 left 5.4's two references (`[ -n "$MAIN_WORKTREE" ]` and `cd "$MAIN_WORKTREE"`) pointing at a variable that is now assigned **nowhere in the skill at all**. Run literally, as I traced it in Step-5 item 4, the guard sees the empty string, prints *"WARN: no worktree on main — plan saved, not committed."*, and exits — in the main worktree, on `main`. The plan is neither committed nor pushed, and the WARN text lies about the reason. This is the third consecutive round in which Step 5 contains a command that cannot run. |
| **N2** | The accepted `CONTEXT.md` glossary entry is written by 5.1 but 5.4 stages only the plan file · *blocking (silently)* | **FIXED** | Step 5.4 now reads `git add docs/plans/{TICKET}-story.md CONTEXT.md`. The user accepted my glossary offer at Q4, I wrote the **Revocation** row in 5.1, and the staging line covers it. Exactly the smallest fix round 2 proposed, and the "user declined" case needs no branch because `git add` on an unmodified path is a no-op. One caveat that is N1's fault and not this line's: in a literal run the commit never fires at all, so the *effect* of this fix is invisible until 5.4's guard is repaired. |
| **N3** | `comments_read_through` is stale the moment 5.3 posts its own comment · *friction* | **PARTIALLY FIXED** | The semantics closed: 5.3 now says "Your comment is now the newest, so set the plan's `comments_read_through:` to **its** id — the marker means 'everything through my answer'." That is the right rule and I applied it (10453 → 10461). **The mechanics did not close.** 5.1 already wrote the file and 5.2 already scanned it; 5.3 is not a file-writing step and never says to re-open the plan. I improvised a 4th Jira-step call, an `Edit` on the plan, that the numbered procedure does not contain — and the artifact 5.2 validated is therefore not the artifact 5.4 commits. Nothing says whether 5.2 should re-run. The fix moved the defect from "the field is wrong" to "the field is right and the write is unlocated". |
| **N4** | "the repo's ready state" is undefined for `/we:story`; `.weside/orchestrate.md` is never read here · *friction* | **FIXED** | 5.3 now reads "the state named in `.weside/orchestrate.md` if that file exists, otherwise the one meaning *refined, not yet started*; ask once when the board's names are ambiguous". This world exercises the hard branch — no `.weside/orchestrate.md` — and the instruction resolved it without guessing: `jira_get_transitions` returned `Selected for Development` / `In Progress` / `Done`, two of which could be read as "refined, not yet started", so the "ask once" clause fired and the user named it. Round 2's proposed wording, adopted almost verbatim, and it worked on the branch that has no config file to lean on. |
| **N5** | The Execution Surface heuristic steers to `/we:orchestrate` with Agent Teams off, and the last printed line dead-ends · *blocking* | **PARTIALLY FIXED** | The prose closed, and closed well: "**Recommend `--solo`** … **and whenever Agent Teams is disabled**: dispatch aborts on orchestrate's own prerequisites there, so `--solo` is the only shape that runs. Say so, and say that enabling Agent Teams unlocks the other one." I obeyed that and led with `--solo`. **But Step 5.7's fenced output block, which is the thing a procedural reader actually copies, still hardcodes `Recommended next: /we:orchestrate {TICKET}` with `--solo` demoted to a parenthetical.** A literal follower emits the dead-ending line even after reading the corrected prose two screens later — the two halves of the fix disagree. And a second half of N5 was never addressed at all: **nothing in the skill tells me how to detect whether Agent Teams is enabled.** No flag, no file, no tool call, no "ask". I only knew because the scenario briefed me; a real session cannot execute the new clause. |
| **N6** | `Oracle:` is single-valued but the ladder is not · *friction* | **FIXED** | The template now reads "**Oracle:** the highest rung the ACs demand, plus every lower rung you also assert (`ui + cli`, `cli`, `substitute`, `not-applicable`) — *why each*". This story needs exactly that shape: AC5 is a reachability claim only a walkthrough proves, AC1–AC4 are machine-readable, and the CLI rung is what makes the `/loop` honest. I wrote `ui + cli` with a reason per rung and had nothing to hedge or hope a downstream reviewer would parse from prose. Round 2's suggested wording, adopted. |
| **N7** | 5.3's parenthetical says transition-first, the sentence it introduces lists transition last · *friction* | **FIXED** | 5.3 now reads "transition it to the repo's ready state … verify the move, then set the description to the minimal body below and add ONE comment". Prose order and `ticketing.md`'s ADF rule now agree, and I executed transition → verify → description → comment with no re-reading. |
| **N8** | Nothing tells the reader how to derive `epic:`, the one frontmatter field the skill calls load-bearing · *friction (carried)* | **FIXED** | Step 1 now ends "Take `epic:` from the ticket's parent key — with no ticketing tool, from the slug of the `-epic.md` plan that lists this story." I read `PROJ-800` off the parent and wrote it without deliberation, where round 2 had to reason it out. One residue the fix does not reach: the frontmatter placeholder is still `{EPIC-SLUG-OR-KEY}` and nothing says which of the two `/we:orchestrate`'s ready-set matches on. It was invisible here only because the epic plan is `PROJ-800-epic.md`, so slug and key coincide. In a repo where the epic plan is `tenant-access-control-epic.md` under ticket `PROJ-800`, the new sentence and the placeholder point at different strings. |

**Tally:** 5 FIXED, 3 PARTIALLY FIXED, 0 STILL OPEN, 0 FORK. Blocking count 3 → 1 clear
(5.4's dead variable) plus 1 half (5.7's block contradicting its own heuristic).

---

## New defects introduced by this revision

### R1 — `$MAIN_WORKTREE` now has zero assignments and two uses · **blocking**

Not a carried defect but a fresh one, because the referent changed. Round 2's 5.0 at least
*assigned* the variable; this revision replaced that assignment with a printing command and a
sentence explaining that shell state does not survive — then left 5.4's block untouched. The
skill now instructs, in the same numbered procedure, both "shell variables do not carry" and
`[ -n "$MAIN_WORKTREE" ] || { echo "WARN: no worktree on main…"; exit; }`. The two are
directly incompatible, and the incompatible half is the one inside a fenced code block, which
is what a procedural reader runs. Outcome traced in Step-5 item 4: false WARN, no commit, no
push, in a repo that satisfies every precondition.

**Smallest fix:** substitute the placeholder in 5.4 as 5.0 already instructs —
`cd <main-worktree> || exit` and drop the `[ -n … ]` guard entirely, since 5.0 already says
what to do on empty output ("say so, skip step 4, and keep going").

### R2 — 5.3's marker rewrite has no home in the numbered order · **friction, silently corrupting**

Covered under N3 as the unclosed half, but it is a *new* line's defect: the "set
`comments_read_through:` to **its** id" sentence did not exist in round 2. It asks for a plan
edit from inside a ticketing step, after the write step and after the scan step, with no
instruction to re-open the file and no statement about whether 5.2 re-runs. Every run of this
skill now either improvises an unlisted `Edit` (what I did) or commits a plan whose marker
contradicts the comment it just posted.

**Smallest fix:** move the sentence to a 5.3b — "re-open the plan and set
`comments_read_through:` to your comment's id; the scan in 5.2 still holds, this is a
frontmatter value" — or reorder so the ticket pass precedes the plan write.

### R3 — the `_Avoid_` term sits in the ticket field Step 5 never writes · **friction**

Prerequisites promise: "use its canonical vocabulary in the **ticket and the plan** (never its
`_Avoid_` terms)". PROJ-812's summary is *"**Workspace** admins can revoke a member's API
token"* — the `_Avoid_` term is in the summary, and 5.3 sets only the **description**. Following
the steps literally leaves the banned word as the ticket's headline, in the one field every
board, every search and every orchestrate roll-up displays. I improvised a
`jira_update_issue(summary=…)` that no step asks for. Round 2 did not surface this; my run hit
it because the summary is the only place the scenario put the term.

**Smallest fix:** 5.3 — "set the summary and description; rewrite the summary into the
glossary's canonical vocabulary if it uses an `_Avoid_` term, and say in your comment that you
did."

### R4 — the repo-local DoR row still has a format but no slot · **friction (carried through two revisions now)**

Prerequisites: "Each repo-local row gets its own labelled line in the plan (`**<Row name>:** …`),
because `/we:orchestrate` gates on it and names the failing row." The Step-3 template has no
section for it. I put `**Rollback step:**` under *Constraints and Pins*; round 2 put it in the
same place by coincidence; round 1 invented a `## Rollback` heading. `/we:orchestrate` Step 1
reads `<repo>/.weside/dor.md` at the confirm and bounces a plan that fails a row — against a
plan whose answer is in a section the gate has no reason to look in. Two rounds have named the
format half; the location half is untouched.

**Smallest fix:** one line in the template — a `## Repo DoR` section under Design Decisions,
or "append repo-local rows as labelled lines at the end of *Constraints and Pins*".

### R5 — 5.7's `/loop` clause tells me both to print and not to print · **friction**

"Print the `/loop` … invocation when `references/long-running.md`'s trigger fires — printed,
never invoked, **and only once the plan's `## Verification` names a scriptable oracle**. If the
oracle is not scriptable yet, say so and make the first round's job to make it so." My case is
exactly the second sentence: 5 phases fires the trigger, and the oracle is not scriptable until
Phase 1 ships the verbs. Do I print the `/loop` line with a caveat, or withhold it and print
only the caveat? I printed it with a warning attached, which felt more useful, but that is a
coin flip on the last line the user reads.

**Smallest fix:** "…if the oracle is not scriptable yet, print the invocation anyway with the
blocker named above it" (or the reverse) — pick one.

### R6 — nothing closes the loop on a parked open question · **friction**

The scenario's third comment (10453) leaves *self-revoke* explicitly open. `/we:story` tells me
to name parked questions in the 5.3 comment, which I did, and that is the right thing. But
`/we:orchestrate` Step 3 signal 1 fires on "an open question in the ticket (summary,
description, **or an unanswered comment**)" and signal 5 on "comments contradict the description
or the plan" — and my 5.3 comment, being the newest, both answers 10453 *and* is itself the
thing the Lead reads. Whether a parked question counts as answered by a comment saying "parked,
out of scope" is not stated in either file, so a refined plan may bounce straight back to the
refine lane. The `comments_read_through:` marker helps and is clearly aimed at this, but the
fix lands in orchestrate's Step 3 wording — **FORK**, noted here only because `/we:story` is
where the parking decision is made.

---

## Still cuttable

The revision cut hard again and cut correctly. Every line round 2 listed is gone except one:
the "Ticket is MINIMAL / Plan contains ALL details" restatement, the "Load more files than feel
necessary" exhortation, Step 4's `ExitPlanMode` description, the "user-visible surfaces owe a
proof block" third copy, and the "Lead with the recommended shape" prose under the output block
have all been removed, and I did not want any of them back. What remains:

> "Legacy `-plan.md` files are still read for back-compat; new plans are always `-story.md`."
> *(Rules, first bullet)*

Unchanged from round 2's list. Every `{TICKET}-story.md` literal in Steps 1, 5.1, 5.7 and the
Output table already says it, and it changed nothing I did.

> "The urge to split into phases is the orchestrate signal, not the epic signal." *(Step 2)*

A one-line restatement of the two-bullet fork immediately above it, which already says the same
thing twice as precisely ("this stays a **single Story** with a phased plan"). `[UNPROMPTED]` —
I classified PROJ-812 from the bullets, not from this line.

> Execution Surface table rows **"Caller's context"** and **"Review stance"**

The paragraph below the table already carries both arguments in its recommendation clause
("the caller benefits from context-hygiene plus neutral review"). Four table lines to say what
one clause says, in a section whose actual decision here was made by the Agent-Teams sentence.

> "(the CLI keeps the `story` table name for back-compat)" *(5.5)*

Trivia about the script's internals, in a step whose whole content is one copy-pasteable
command. It cannot change what I run.

> "Anything beyond this template follows `${CLAUDE_PLUGIN_ROOT}/references/ticket-briefs.md` for
> *wording* …" *(5.3, after the minimal-ticket template)*

`ticket-briefs.md` itself opens by scoping its `/we:story` consumer to "ticket *wording* only —
its ticket stays minimal and the ACs live in the plan". The pointer is fine; the "behavioural,
durable, no file paths or line numbers" summary appended to it is the reference's own first
principle, restated at the call site.

Rough count: ~12 lines, against round 2's ~15 and round 1's ~90. The file is lean; nothing left
is padding worth a round of its own.

---

## Grade

**3/5** — the top of that band, and it stays there for one reason. This revision is the most
disciplined of the three: it took eight named defects and closed five of them cleanly, mostly in
round 2's own proposed wording, and the five it closed are the ones that shape the artifact.
`Oracle: ui + cli` let me state a two-rung claim without hedging; `epic:` came off the parent key
without deliberation; the ready-state clause survived contact with the branch that has no
`.weside/orchestrate.md` and asked exactly one question instead of guessing; the transition/
comment ordering matched `ticketing.md` for the first time; `git add … CONTEXT.md` closed a
silent data-loss path. The plan I produced is genuinely build-ready — five phases with real
`Files:` lists, `parallel_groups: [[1,2]]`, a named missing CLI verb landing in the phase its own
dependencies allow, a forward-only migration with the rollback step written down, and a `/goal`
line that fired on the auth path exactly as `long-running.md` intends. What holds it at 3 is that
Step 5 — the numbered, "run these in order", ⛔-marked procedure that round 1 flagged and round 2
flagged again for containing a command that cannot run — **contains one for the third round in a
row**, and this time the revision touched the lines on either side of it. Fixing 5.0 to print
instead of assign, and 5.1 to take a placeholder, left 5.4 referencing a variable that the skill
no longer assigns anywhere; a literal run announces "no worktree on main" while standing on main
and silently ships neither the plan commit nor the glossary fix that N2 just repaired. Beside it,
the corrected Agent-Teams heuristic is contradicted by the fenced block that sits above it and
depends on a precondition the skill gives no way to detect, and the new
`comments_read_through:` rewrite is asked for two steps after the file was written and scanned.
Three one-line edits inside this worker's own file list — substitute the placeholder in 5.4,
invert the 5.7 block, give the marker rewrite a numbered home — turn this into a 4.
