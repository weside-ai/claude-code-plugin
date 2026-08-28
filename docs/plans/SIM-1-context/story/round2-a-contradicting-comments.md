<!-- markdownlint-disable -->

# Round 2 — Scenario (a)

World state as briefed: `/we:story PROJ-812`, Sonnet, Agent Teams **off**, mode `acceptEdits`,
cwd `/home/user/proj` (main worktree, on `main`). `.weside/` present with `dor.md`
(+1 row: "Every story names the rollback step") and `config.json` → `tools.graphify: false`.
No `.weside/verify.md`, no `.weside/vision.md`. `CONTEXT.md` at repo root marks **workspace**
as `_Avoid_` → **tenant**. TurboVault not available, graphify not installed. Jira connected.

TABLE-TOP: nothing below was executed.

---

## Trace

### Prerequisites

**1.** `Read("${CLAUDE_PLUGIN_ROOT}/quality/dor.md")` — prompted, Prerequisites block.

**2.** `Read("${CLAUDE_PLUGIN_ROOT}/references/verification.md")` — prompted.

**3.** `Read("${CLAUDE_PLUGIN_ROOT}/references/long-running.md")` — prompted.

**4.** `Bash("git rev-parse --show-toplevel")` → `/home/user/proj`. Prompted.

**5.** `Read("/home/user/proj/.weside/dor.md")` → one additive row: *"Every story names the
rollback step."* The skill now tells me the **format** — "its own labelled line in the plan
(`**<Row name>:** …`)" — but not the **section**. → **Guessing point.** I put
`**Rollback step:** …` under `## Constraints and Pins`. A second session would plausibly put it
under Technical Approach, or invent a `## Rollback` heading (which is what round 1 did). Since
`/we:orchestrate` Step 1 gates on this row and "names the failing row", the slot is still a coin
flip on a blocking gate — the format half of D4 closed, the location half did not.

**6.** `Read("/home/user/proj/CONTEXT.md")` — prompted, and now **before** the ticket is written.
Notes: `workspace` → `_Avoid_`, canonical `tenant`. I hold this for ticket *and* plan, as the
skill now says explicitly.

**7.** `Glob("/home/user/proj/.weside/*")` → `weside.md`, `council.json`, `config.json`,
`dor.md`. `[UNPROMPTED]` — the skill only names `dor.md` here and `config.json` much later in
Step 3; I look at the directory once so I know what exists before I need it. I also note the
**absence** of `verify.md` and `vision.md` here rather than discovering it twice later.

*(No model-tier notice this run — the "run this on Opus" line round 1 called cuttable is gone.
I did not miss it. Good cut.)*

### Step 1: Load

**8.** `ToolSearch("select:mcp__atlassian__jira_get_issue,mcp__atlassian__jira_get_transitions,mcp__atlassian__jira_add_comment,mcp__atlassian__jira_update_issue,mcp__atlassian__jira_transition_issue")`.

**9.** `Read("${CLAUDE_PLUGIN_ROOT}/references/ticketing.md")` — the skill cites the path inline
twice (Step 1 and Step 5.3); I read it. → **Guessing point (small).** `ticketing.md`'s priority
order puts **weside MCP** (`JIRA_*` via `execute_tool`) above Atlassian MCP, and the scenario says
only "Jira connected". I improvised: Atlassian MCP tools are visibly present, so I use path 2 and
do not spend a `discover_tools` round-trip probing path 1.

**10.** `mcp__atlassian__jira_get_issue(issue_key="PROJ-812", fields="*all", comment_limit=20)`
→ Summary "Workspace admins can revoke a member's API token"; Description as briefed; Status
`Backlog`; parent `PROJ-800`; three comments.

I record the newest comment id for `comments_read_through:` → `10453 (2026-08-26)`.
Prompted, and this is new since round 1.

**11.** `Bash("ls /home/user/proj/docs/plans/ | grep -E 'PROJ-812|PROJ-800'")` → only
`PROJ-800-epic.md`. So: new plan, no in-place refine. The Step-1 branch now has a defined
consequence for both outcomes (D9's fix), and I exercised the "otherwise" leg.

**12.** `Read("/home/user/proj/docs/plans/PROJ-800-epic.md")` → "Tenant access control", success
criteria, a `## Stories` mirror block with PROJ-812 row `Backlog / Plan —`.
`[UNPROMPTED]` — **still nothing tells me to fetch the epic.** The frontmatter comment calls
`epic:` REQUIRED and warns that omitting it makes the story invisible, but no step says take the
ticket's parent, or read the epic doc, or resolve which of "SLUG-OR-KEY" the ready-set matches
on. Round 1 raised this under "What I needed and did not find"; it is unchanged. I used the
ticket's parent key, `PROJ-800`.

### Step 2: Understand (INTERACTIVE)

Contradictions and gaps I extract before asking anything:

- **C1** comment 1 (PO, 14d): accept a 60s revocation window ⟂ comment 2 (tech lead, 3d): no
  window, invalidate the cache on revoke; comment 3 (PO, yesterday) agrees with comment 2.
  Newest wins → invalidate.
- **C2** comment 2 adds a requirement the description does not carry: **auditable, one row per
  revoke**.
- **C3** comment 3 leaves an **open question**: self-revoke by the member. Unresolved.
- **C4** the summary says "**Workspace** admins" — the `_Avoid_` term.

`.weside/vision.md` absent and no Companion → **skip silently**, as instructed. I say nothing.
Prompted and correct; round 1's version made me guess here.

Grill, one question at a time, each with a recommendation (prompted):

**13.** Q1 — "Comments 2 and 3 supersede comment 1: revoke invalidates the token cache
synchronously, no 60s window. I'll plan it that way. Confirm?"
`[USER]` *"Yes. Invalidate on revoke, no window."*

**14.** Q2 — "Comment 3 leaves self-revoke open. Recommendation: out of scope here — admin-revoke
only — and I park it as a named follow-up in the ticket comment. OK?"
`[USER]` *"Agreed, park it. Separate ticket later."*

**15.** Q3 — "Audit row: recommendation is token id, tenant id, actor user id, revoked_at,
append-only. OK?"
`[USER]` *"Yes, plus the token's last four characters so support can match a report. No reason
field for now."*

**16.** Q4 — "`CONTEXT.md` marks 'workspace' `_Avoid_` in favour of 'tenant', and the ticket
summary says 'Workspace admins'. I'll use **tenant admin** in the plan and the ticket
description, and I'd add an `API token` row to `CONTEXT.md` while I'm there. OK?"
`[USER]` *"Yes, use tenant. Add the API token row."*
→ **Guessing point.** The skill templates only the ticket **description**. The summary keeps the
banned term and is the field every board view shows. I left it. (Round 1 flagged this; unchanged.)

**17.** Q5 — "Your `.weside/dor.md` requires a named rollback step. Recommendation: the change is
additive — a nullable column plus a new table — so rollback is a deploy revert, no data
destroyed. OK?"
`[USER]` *"Yes. And say explicitly that if the invalidation code is reverted, revocation degrades
to the existing 60s TTL expiry rather than failing open."*

**18.** `Grep(pattern="api_token|ApiToken|APIToken", path="/home/user/proj", output_mode="files_with_matches")`
→ `api/auth/tokens.py`, `api/auth/cache.py`, `api/routes/tenant_members.py`,
`api/tests/test_tokens.py`, `web/src/api/tokens.ts`.

**19.** `Read("/home/user/proj/api/auth/tokens.py")` → model `ApiToken`, `verify_token()`.

**20.** `Read("/home/user/proj/api/auth/cache.py")` → Redis, `TOKEN_TTL = 60`, key
`tok:{token_hash}`, no invalidation entry point.

**21.** `Grep(pattern="audit|activity_log", include="*.py")` → `api/models/activity_log.py`
(per-tenant feed, mutable, no immutability guarantee).

**22.** Q6 — "Reuse `activity_log`, or a dedicated table? Recommendation: dedicated
`api_token_revocations` — 'one row per revoke, auditable' is a different guarantee than a
mutable activity feed."
`[USER]` *"Dedicated table."*

**23.** Q7 — "Is this API-only or does the admin UI get a control? Recommendation: UI too — the
AC says an admin *can* revoke, and an endpoint nothing calls is not reachability."
`[USER]` *"UI too. Button on the member row, confirm dialog."*

**24.** Too-big check, prompted and genuinely useful: this is **one coherent change with several
phases**, not many independent slices → stays a single Story with a phased plan. No `/we:epic`
print. The skill's two-shape framing settled this in one pass.

### Step 3: Create Plan

**25.** → **Guessing point.** The heading says `(EnterPlanMode)` but **there is no
`EnterPlanMode` tool** in my toolset — only `ExitPlanMode` — and no numbered step issues it. I
improvised: I stayed in `acceptEdits`, wrote nothing, composed the plan in-message and passed it
to `ExitPlanMode`. Unchanged from round 1 (D20).

**26.** TurboVault absent → I say once, verbatim as instructed:
> ⚠️ TurboVault unavailable — using grep fallback; architecture context may be incomplete. Check
> the MCP config.

**27.** `Grep(pattern="token|revoke|auth", include="*.md", path="/home/user/proj/docs")`.

**28.** `Glob("/home/user/proj/docs/architecture/**/*.md")` → `auth.md`, `tenancy.md`.

**29.** `Read("/home/user/proj/docs/architecture/auth.md")` → token issuance + the 60s cache
contract, which is exactly the thing comment 2 changes. Referenced in Technical Approach.

**30.** `Read("/home/user/proj/.weside/config.json")` → `tools.graphify: false`.
Prompted this time. → I skip the graph, derive `Files:` with `rg`, and write the required
sentence into Technical Approach. **This block ran clean.** In round 1 it hard-errored.

**31.** `Bash("rg -n 'verify_token|get_cached_token' /home/user/proj --type py --type ts")` →
call sites in `api/auth/middleware.py`, `api/tests/test_tokens.py`,
`api/tests/test_middleware.py`.

**32.** `Bash("rg -l 'TenantMembers|member row' /home/user/proj/web/src")` →
`web/src/pages/TenantMembers.tsx`, `web/src/pages/__tests__/TenantMembers.test.tsx`.

**33.** `Bash("ls /home/user/proj/migrations/versions | tail -3")` → head revision for the
migration's `down_revision`.

**34.** `.weside/verify.md` absent → prompted: "say so once and propose it under Documentation
Impact". I say it once and add the proposal. This worked exactly as written.

→ **Guessing point (minor, new).** The Verification block's `**Oracle:**` is single-valued
(`cli | ui | substitute | not-applicable`), but this story has an API AC *and* a UI AC, and the
ladder says climb only as far as the ACs demand — which here is both. I improvised
`ui — with a cli sub-assert on the endpoint and the audit row`.

**35.** `ExitPlanMode(plan=<the plan below>)`.

### Step 4: User Approval

**36.** `[USER]` *"Approved. Go."*

### Step 5: Post-Approval

**37.** `Bash("MAIN_WORKTREE=$(git worktree list --porcelain | awk '/^worktree /{p=$2} /^branch refs\\/heads\\/main$/{print p; exit}')")`
→ **the tool result is empty.** The command is a bare assignment; it prints nothing. I never
learn the path from it, and shell state does not survive to the next Bash call either. →
**Improvised:** I re-ran it with an `echo` appended so I could actually read `/home/user/proj`,
then substituted the literal path into steps 5.1 and 5.4. A literal follower does not, and pays
for it twice below. → **New defect N1.**

**38.** `Write("/home/user/proj/docs/plans/PROJ-812-story.md", <plan, status: approved>)`.
The skill's text is `Write($MAIN_WORKTREE/docs/plans/{TICKET}-story.md)` — a `Write` path is not
a shell string, so without step 37's value substituted by hand this creates a directory literally
named `$MAIN_WORKTREE`.

**39.** `Edit("/home/user/proj/CONTEXT.md", …)` — adds the `API token` row and the
`tenant admin` cross-reference. Prompted now (Step 2 → "write it in Step 5.1's commit", Step 5.1
→ "Write the accepted `CONTEXT.md` glossary entry, if any, now"). D8b closed at the write end —
but see **N2** for the commit end.

**40.** `Read("${CLAUDE_PLUGIN_ROOT}/references/dor-scan.md")`.

**41.** `Bash("grep -cE 'Given|When|Then' … ; grep -nE '^### Phase [0-9]+:' … ; sed -n '/## Context/,/## Acceptance/p' … | wc -c")`
→ GWT present, 5 phase headers, Context 780 chars. Pass.

**42.** `mcp__atlassian__jira_get_transitions(issue_key="PROJ-812")` → `In Progress`,
`Selected for Development`, `Done`. → **Guessing point.** Step 5.3 says "transition the ticket to
**the repo's ready state**" and nothing in `/we:story`'s reading list defines what that is for
this repo (`.weside/orchestrate.md` is orchestrate's file, is not read here, and need not exist).
I picked `Selected for Development`. → **New defect N4.**

**43.** `mcp__atlassian__jira_transition_issue(issue_key="PROJ-812", transition_id=<Selected for Development>)`.

**44.** `mcp__atlassian__jira_get_issue(issue_key="PROJ-812", fields="status")` → verify the move
landed (prompted by `ticketing.md`). → `Selected for Development`. Good.

**45.** `mcp__atlassian__jira_update_issue(issue_key="PROJ-812", fields={description: <minimal body>})`
→ **Guessing point (minor).** Step 5.3's prose orders it "set the description … add ONE comment
… and transition", while its own parenthetical and `ticketing.md` both say *transition first*. I
followed the parenthetical. → **N7.**

**46.** `mcp__atlassian__jira_add_comment(issue_key="PROJ-812", comment=…)`:

> Refined into `docs/plans/PROJ-812-story.md`.
> **Resolved:** the 60s revocation window (comment of 14d ago) is superseded — revoke invalidates
> the token cache synchronously; the description's "instantly" now has a mechanism.
> **Resolved:** revocation is auditable — one immutable row per revoke (token id, tenant id,
> actor, timestamp, token last-4).
> **Parked:** member self-revoke is out of scope for this story; it needs its own ticket.
> Vocabulary: this story says **tenant**, not workspace (repo glossary).

This is the step round 1 said was missing, and it is the reason the scenario exists. It is here
and it does the job. → **but see N3:** this comment is now the newest, and the plan's
`comments_read_through: 10453` points at the one before it, with nothing telling me to advance it.

**47.** `Bash(<Step 5.4 block, with the literal path substituted>)`. As written, with
`$MAIN_WORKTREE` unset, the first line trips: `[ -n "$MAIN_WORKTREE" ] || { echo "WARN: no
worktree on main — plan saved, not committed."; exit; }` — on a repo that *is* on main.
Also: `git add docs/plans/PROJ-812-story.md` only. **`CONTEXT.md` is never staged**, so step 39's
accepted glossary entry is not in "Step 5.1's commit". I added it by hand. → **N1, N2.**

**48.** `Bash("python3 ${CLAUDE_PLUGIN_ROOT}/scripts/orchestration.py story checkpoint PROJ-812 refined")`.

**49.** TurboVault absent → Step 5.6 skipped silently. Prompted.

**50.** Step 5.7 output. Execution surface: 5 phases, `parallel_groups: [[1,2]]` non-empty,
coherent multi-layer change → the heuristic says **dispatched `/we:orchestrate`**, and
`--solo` is reserved for "genuinely trivial, straight-line single-phase". So I emit:

```
Plan saved to docs/plans/PROJ-812-story.md. /we:story DONE.
State file: docs/plans/PROJ-812-state.md (the Lead creates it on the first run).

Recommended next: /we:orchestrate PROJ-812   ← 5 phases, phases 1+2 parallel, auth-risk phases 3–4 want neutral review
(or /we:orchestrate PROJ-812 --solo if you'd rather run it inline.)

Long-running:
  /loop Run the next PROJ-812 phase to green, then re-run `proj-cli tokens revoke` against DEV
        and confirm the revoked token 401s and one audit row exists.
```

`long-running.md`'s trigger is now structural — **4+ phases** — and fires cleanly on 5. But its
gate ("only once the plan's `## Verification` names a scriptable oracle") is not met until Phase 1
ships the CLI verb, so I add the required sentence: *"The oracle is not scriptable until Phase 1
lands `proj-cli tokens issue|revoke`; the first round's job is to make it so."* Prompted, and it
worked — round 1 had to invent this whole trigger.

→ **New defect N5, and it is the last thing the user reads.** Agent Teams is **off** in this
world. `/we:orchestrate PROJ-812` (Mode B, dispatched) hits orchestrate's Prerequisites —
"Agent Teams must be enabled … abort" — and dies before Step 0. The Execution Surface heuristic
never checks the flag, and it actively steers *away* from `--solo`, the one shape that can run
here.

**51.** ⛔ STOP. No branch, no code.

---

## The plan I would have written

```markdown
---
type: story-plan
story: PROJ-812
epic: PROJ-800
depends_on: []
comments_read_through: 10453 (2026-08-26)
created: 2026-08-27
status: approved
parallel_groups: [[1, 2]]
---

# Plan: Tenant admins can revoke a member's API token

## Context

A leaked API token is currently only as dead as the auth cache lets it be: `verify_token()`
reads through a Redis entry with a fixed 60-second TTL, so today "revoked" means "stops working
within a minute". The ticket description asks for instant revocation and the thread spent two
weeks converging on what that means — the PO first offered to accept the 60s window, the tech
lead rejected it three days ago, and the PO agreed yesterday: the cache is invalidated
synchronously on revoke, not waited out. The same comment added a requirement the description
never carried — revocation must be auditable, one immutable row per revoke — because support
needs to answer "when was this token killed, and by whom" after an incident, which the mutable
`activity_log` feed cannot promise. What the tenant admin cares about most is the moment between
"I clicked revoke" and "the token is dead": it has to be zero, and it has to leave a trace. One
question stayed open and is deliberately not in this story: whether a member can revoke their own
token. Vocabulary note: the ticket summary says "workspace admin"; this repo's `CONTEXT.md`
makes **tenant** canonical, and this plan uses it throughout.

## Acceptance Criteria

1. **Given** a tenant admin viewing a member with an active API token
   **When** they press **Revoke** on that token's row and confirm the dialog
   **Then** the token disappears from the member's active-token list without a page reload.
2. **Given** a token that has just been revoked
   **When** any request presents that token, within the same second
   **Then** the API answers `401` with `error.code = "token_revoked"` — no 60-second grace.
3. **Given** a revoke has completed
   **When** the `api_token_revocations` table is queried for that token
   **Then** exactly one row exists carrying token id, tenant id, revoking actor id, revoked_at,
   and the token's last four characters.
4. **Given** the same revoke request is retried (double-click, client retry)
   **When** it reaches the endpoint a second time
   **Then** it answers `200` and the audit table still holds exactly one row.
5. **Given** an admin of tenant A
   **When** they call the revoke endpoint for a token belonging to tenant B
   **Then** the API answers `404`, and no row is written.
6. **Given** a member (non-admin) of the tenant
   **When** they call the revoke endpoint for another member's token
   **Then** the API answers `403`.

## User Journey

1. A member reports their laptop was stolen. 2. The tenant admin opens **Members**, finds the
member, and sees their active API tokens with a **Revoke** action per row. 3. They press
**Revoke**; a confirm dialog names the token by its last four characters and says this cannot be
undone. 4. On confirm the row disappears, a toast says "Token revoked", and any request still
carrying that token gets `401` immediately.

## Testing Requirements

- Unit: `revoke_token()` — happy path, idempotent second call, cross-tenant refusal,
  cache-invalidation call asserted (not mocked away).
- Integration: `pytest api/tests/test_tokens.py api/tests/test_middleware.py` against the real
  Postgres test database (`alembic upgrade head` on `proj_test` first) plus a real Redis — the
  `ON CONFLICT` arbiter on the audit table and the cache-key derivation are both invisible to a
  mocked session.
- Migration: `alembic upgrade head` then `downgrade -1` on `proj_test`, both clean.
- Frontend: `web/src/pages/__tests__/TenantMembers.test.tsx` — the Revoke action renders for
  admins only, the confirm dialog gates the call, the row leaves the list on success.
- Edge cases: already-revoked token; token belonging to a removed member; two admins revoking the
  same token concurrently.

## Verification

- **Oracle:** ui — with a cli sub-assert. AC 1 is a reachability claim ("the admin presses
  Revoke"), which an endpoint cannot prove; ACs 2–5 are machine-readable and are asserted
  through the CLI in the same run.
- **Seed:** `proj-cli tokens issue --tenant acme --member bob --label stolen-laptop`
  (ships in Phase 1), then `proj-cli tokens revoke --token <id> --as alice@acme`.
- **Asserted:** `curl -H "Authorization: Bearer <tok>" $DEV/api/me` → `401`,
  `error.code == "token_revoked"`; `proj-cli tokens audit --token <id>` → exactly one row with
  actor `alice@acme` and last-4 matching; in the browser at `/tenants/acme/members`, the member
  row's token entry is gone after confirming the dialog.
- **Not proven:** that the revoke propagates across multiple API replicas — DEV runs one. The
  staging round after merge owes it, and it is the first thing to check there.
- **Exit criterion:** `proj-cli tokens issue` → `revoke` → `curl` returns `401` and
  `tokens audit` returns exactly 1 row, on a freshly migrated DEV, with the browser walkthrough
  of AC 1 recorded in the PR's `## Verification` block.
- **Missing CLI verb:** `proj-cli tokens issue|revoke|audit` — the seed is otherwise a
  psql-plus-curl dance. **Phase 1** ships `issue` and `audit`; `revoke` lands with Phase 4,
  because it needs the service Phase 3 builds — it cannot be first, and that is why.

⚠️ No `.weside/verify.md` in this repo — the commands above are derived from the stack, not from
a repo recipe. Proposed under Documentation Impact.

## Technical Approach

**Patterns:** the revoke path composes the existing tenant-scoping guard in
`api/routes/tenant_members.py` and the auth cache in `api/auth/cache.py`; the audit write and the
`revoked_at` update happen in one transaction so a crash cannot produce a dead token with no row,
nor a row with a live token. Cache invalidation is a delete of `tok:{token_hash}` issued *after*
the transaction commits and retried once — a failed delete degrades to TTL expiry, never to
"revoke succeeded but nothing changed". `docs/architecture/auth.md` documents the 60s cache
contract this story changes; that section is rewritten in Phase 3.

`Files:` lists are grep-derived — no code graph (`.weside/config.json` → `tools.graphify: false`).

## Implementation Phases

### Phase 1: Token CLI verbs — `issue` and `audit`

- **Goal:** the story is verifiable unattended from the first phase onward.
- **Files:** `cli/commands/tokens.py`, `cli/registry.py`, `cli/tests/test_tokens_cmd.py`,
  `docs/cli-reference.md` (generated)
- **Risk:** ordinary — read/seed-only surface, no production call path.
- **Approach:** `issue` wraps the existing token-creation service; `audit` reads the table
  Phase 2 adds and prints JSON. `audit` is written against the Phase 2 schema and merges after
  it, or ships stubbed and is filled in Phase 2's PR — whichever the Lead sequences.

### Phase 2: Schema — `api_tokens.revoked_at` and `api_token_revocations`

- **Goal:** a revoke has somewhere to be recorded, immutably.
- **Files:** `migrations/versions/<new>_token_revocation.py`, `api/models/api_token.py`,
  `api/models/api_token_revocation.py`, `api/tests/test_models.py`
- **Risk:** migration — additive only (nullable column + new table + unique index on
  `token_id`), safe in one deploy, but it is a schema change on the auth path.
- **Approach:** nullable `revoked_at`, `revoked_by`; new table with a unique constraint on
  `token_id` so AC 4's idempotency is enforced by the database, not by application logic.

### Phase 3: Revoke service and synchronous cache invalidation

- **Goal:** revoking kills the token now, not in 60 seconds.
- **Files:** `api/services/token_revocation.py`, `api/auth/cache.py`, `api/auth/tokens.py`,
  `api/tests/test_tokens.py`, `api/tests/test_middleware.py`,
  `docs/architecture/auth.md`
- **Risk:** auth — this is the token verification path; a mistake fails open.
- **Approach:** one transaction writes `revoked_at` and the audit row; on commit, delete the
  cache key and retry once. `verify_token()` additionally rejects a token with `revoked_at` set,
  so a stale cache entry cannot resurrect it.

### Phase 4: Admin endpoint and the `revoke` CLI verb

- **Goal:** a tenant admin can reach the service; a script can too.
- **Files:** `api/routes/tenant_members.py`, `api/schemas/tokens.py`, `openapi.json`
  (generated), `web/src/api/generated/` (generated), `cli/commands/tokens.py`,
  `api/tests/test_routes_tokens.py`
- **Risk:** auth — the authorization check (admin of *this* tenant) is the whole of ACs 5 and 6.
- **Approach:** `POST /api/tenants/{tenant_id}/members/{member_id}/tokens/{token_id}/revoke`.
  Cross-tenant is `404`, not `403` — do not leak the token's existence.

### Phase 5: Members page — Revoke action

- **Goal:** the journey completes in the product, not in curl.
- **Files:** `web/src/pages/TenantMembers.tsx`, `web/src/components/ConfirmDialog.tsx`,
  `web/src/api/tokens.ts`, `web/src/pages/__tests__/TenantMembers.test.tsx`
- **Risk:** ordinary.
- **Approach:** per-token Revoke action, admin-gated, confirm dialog naming the last four
  characters, optimistic row removal with rollback on error and the native error in the toast.

`parallel_groups: [[1, 2]]` — Phase 1 touches only `cli/`, Phase 2 only `migrations/` and
`api/models/`; disjoint, no ordering dependency between them. Phases 3, 4, 5 are strictly
sequential.

## Constraints and Pins

**Constraints:** the tenant-scoping guard in `api/routes/tenant_members.py` is composed, never
re-implemented; the audit row is written in the same transaction as `revoked_at`; the audit table
is append-only (no UPDATE, no DELETE path anywhere in the diff).

**Pins:** unrevoked tokens keep the existing 60s cache behaviour and its performance profile —
this story adds an invalidation edge, it does not shorten the TTL. `activity_log` semantics are
untouched. Token issuance is untouched.

**Rollback step:** *(repo DoR — `.weside/dor.md`)* revert the deploy. The migration is additive
and is **not** downgraded: a nullable column and an unused table cost nothing, and downgrading
would destroy the audit rows a revert is most likely to need. With the invalidation code
reverted, revocation degrades to `revoked_at` being checked on cache miss, i.e. the old 60s
window — degraded, not fail-open. Ship Phase 2 before Phase 3 so this ordering holds at every
intermediate deploy.

## Design Decisions

| Decision | Alternatives Considered | Why This |
|---|---|---|
| Invalidate the cache on revoke | Accept a 60s window (PO, comment of 14d ago) | Superseded by the tech lead 3d ago and agreed by the PO yesterday; the description's "instantly" has no mechanism otherwise |
| Dedicated `api_token_revocations` table | Reuse `activity_log` | "One immutable row per revoke" is a durability guarantee the mutable activity feed does not make |
| Uniqueness on `token_id` in the DB | Application-level idempotency check | AC 4 is enforced by the arbiter, not by a read-then-write race |
| Cross-tenant revoke returns `404` | `403` | `403` confirms the token exists to an attacker who guessed the id |
| Self-revoke excluded | Include it now (PO's open question, comment of yesterday) | Undecided product question; deciding it inside a build pass is the thing the DoR forbids. Parked on the ticket for its own story |
| Admin UI in this story | API-only, UI later | AC 1 is a reachability claim; an endpoint nothing calls is not a delivered feature |
| Delete the cache key after commit, retry once | Delete inside the transaction | A rolled-back transaction must not have already evicted; a failed delete degrades to TTL, never to a live revoked token |

## Code Guidance

**DO:** compose the existing tenant guard; write `revoked_at` and the audit row in one
transaction; check `revoked_at` in `verify_token()` so a stale cache cannot resurrect a token;
name the tenant concept **tenant** in code, tests, copy and commit messages.

**DON'T:** write "workspace" anywhere (repo glossary marks it `_Avoid_`); add a self-revoke path
"while we're in here"; shorten the global cache TTL as a shortcut to instant revocation; make the
audit table mutable or add a delete path to it; swallow a failed cache delete silently.

## Security Review Required

**Yes** — this is the auth token verification path. Three things to look at specifically: the
authorization check on the endpoint (ACs 5 and 6), that a failed cache invalidation degrades to
TTL rather than to a live token, and that the `404`-not-`403` choice holds on every branch.

## Documentation Impact

- **Docstrings** — `token_revocation.py` (why post-commit invalidation, why retry once) and
  `api_token_revocation.py` (why append-only). Default; carries most of it.
- **Architecture doc** — `docs/architecture/auth.md`: the 60s cache contract is no longer the
  whole story; rewrite that section in Phase 3.
- **ADR** — no. Reversible and unsurprising.
- **Generated** — `openapi.json`, `web/src/api/generated/`, `docs/cli-reference.md`.
- **New doc** — `.weside/verify.md` does not exist in this repo, so this plan's Verification
  block had to invent its own commands. Phase 1 ships the CLI verbs that make them real;
  proposing `.weside/verify.md` in the same PR is the cheap way to stop the next story inventing
  them again.
```

---

## Round-1 verdict table

Every defect below was judged by re-running the scenario, not by diffing.

| # | Round-1 defect | Verdict | Evidence from this run |
|---|---|---|---|
| **D1** | `{codename}` defined nowhere · blocking | **FIXED** | Step 5.1 now reads "write the approved plan to `$MAIN_WORKTREE/docs/plans/{TICKET}-story.md`". At trace **38** I had the plan in context and wrote it directly — no path indirection, no stale-plan risk. `grep -rn codename we/ docs/` returns nothing outside the SIM report. |
| **D2** | graphify block cannot run; escape hatch describes the wrong failure · blocking | **FIXED** | At trace **30** I read `.weside/config.json` → `tools.graphify: false`, took the else-branch, ran `rg` (**31**, **32**) and wrote the required sentence "`Files:` lists are grep-derived — no code graph" into Technical Approach. No command was issued against a script this repo does not vendor. The flag is now the gate, exactly as round 1 asked. |
| **D3** | SKILL and `plan-format.md` disagree on required frontmatter · blocking | **FORK** (`docs/plan-format.md`, not in this file list) | Still live, and **wider than round 1**: my frontmatter carries `type`, `epic`, `depends_on` and `comments_read_through`; `plan-format.md`'s table and Full Template still list only `story`, `created`, `status`, `parallel_groups`. The revision added two of those four fields, so the drift grew inside this file even though the fix belongs in the other one. |
| **D4** | repo-local DoR row has no home in the plan · blocking | **PARTIALLY FIXED** | The skill now specifies the **format** — "its own labelled line in the plan (`**<Row name>:** …`)" — and says why (`/we:orchestrate` gates on it and names the row). It still does not say **which section**. At trace **5** I had to pick; I put `**Rollback step:**` under `## Constraints and Pins`, round 1 invented a `## Rollback` heading. Two sessions, two locations, on a row that blocks a gate. |
| **D5** | Step 3 and `ticket-briefs.md` demand opposite ticket bodies · blocking | **FIXED** | Both ends closed. Step 5.3 now says the pointer applies "for *wording* — behavioural, durable, no file paths or line numbers", and `ticket-briefs.md` itself now carries the carve-out in two places ("Consumers: `/we:story` (ticket *wording* only …)" and, on the AC principle, "A `/we:story` ticket carries none of these — its plan does"). At trace **45** there was nothing left to resolve: minimal body, no coin flip. |
| **D6** | nothing writes the refinement back to the ticket; orchestrate bounces the story · blocking | **FIXED** | Step 5.3 is now one pass: transition, verify, one comment naming resolved contradictions and parked questions. Traces **42–46**. PROJ-812 leaves `Backlog`, and orchestrate's Step-3 signals 1 and 5 now meet a newest comment that answers them. This is the scenario's whole point and it closed. (One residue: **N3**.) |
| **D7** | Step 6.3 shell misreports a failed push; pushes to main ungated · friction | **PARTIALLY FIXED** | The misreporting half is fixed: three failure modes, three distinct messages, and the push failure now suggests branch protection instead of the wrong branch. The **ungated push to `main` is unchanged** — trace **47** pushes the plan commit to `main` with no user gate, in a skill that otherwise stops dead before touching anything. And the guard now misfires for a new reason (**N1**). |
| **D8** | glossary read one step after the ticket is written · friction | **FIXED** | `CONTEXT.md` moved into Prerequisites (trace **6**) and the scope changed to "the **ticket and the plan**". At trace **45** I wrote the description with **tenant**, not workspace. Residue unchanged and still outside the fix: the ticket **summary** keeps the banned term, and no step makes it mine to change (trace **16**). |
| **D8b** | glossary offer has no write step · friction | **FIXED** at the write, **broken at the commit** | Step 2 now says "write it in Step 5.1's commit" and Step 5.1 says "Write the accepted `CONTEXT.md` glossary entry, if any, now" — I did (trace **39**). But Step 5.4 stages `docs/plans/{TICKET}-story.md` only, so the entry is never in that commit. See **N2**. |
| **D9** | "check if plan already exists" with no consequence · friction | **FIXED** | Step 1 now branches both ways: "read it in full and refine **in place**, preserving its Design Decisions rows; otherwise you are writing a new one." At trace **11** I took the "otherwise" leg with no ambiguity, and I knew what the other leg would have been. |
| **D10** | main worktree resolved twice, two ways · friction | **FIXED as stated, and it created N1** | The prose parenthetical is gone; one `MAIN_WORKTREE=` command, now a numbered Step 5.0. Exactly what round 1 asked. But hoisting it into its own step put a shell variable across a tool-call boundary that does not carry it — trace **37**. |
| **D11** | plan Verification field names don't match the PR receipt · friction | **FIXED** | The template now reads `Oracle` / `Seed` / `Asserted` / `Not proven`, verbatim the four names in `verification.md`'s receipt, with `Exit criterion` and `Missing CLI verb` as plan-only extras. `Exit criterion` is the one `long-running.md` names too, so the three files now agree. I filled all six without translating anything. |
| **D12** | "read the plan in full" inside the step that creates the plan · friction | **FIXED** | Gone from Step 3. The equivalent instruction now lives in Step 1, conditioned on the plan existing ("If `docs/plans/{TICKET}-story.md` exists, read it in full"), which is where its precondition can actually hold. |
| **D20** | plan-mode entry never established · friction | **STILL OPEN** | Heading is still `## Step 3: Create Plan (EnterPlanMode)`; no step issues it. I hit it at trace **25**: there is no `EnterPlanMode` tool in my toolset at all, only `ExitPlanMode`. I improvised — stayed in `acceptEdits`, wrote nothing, called `ExitPlanMode` with the composed plan. Unchanged from round 1, and in scope for this file. |
| **D22** | "more than one sitting" undefined · friction | **FIXED** | Step 5.7 now delegates to `references/long-running.md`, which states it structurally: "the plan has 4+ phases, or a non-empty `depends_on:`, or the user says they will be away." Five phases → it fires, deterministically. The added gate ("only once `## Verification` names a scriptable oracle") also caught my case honestly: not scriptable until Phase 1, so I said so instead of printing a dishonest `/loop`. |
| **D13** | checkpoint command has two owners · no-op | **FORK** (`we/quality/dor.md`, not in this file list) | `dor.md` still ends with the `## Checkpoint` block carrying the identical command that Step 5.5 carries. Both loaded in the same session (traces **1** and **48**). Unchanged, and the fix is in a file this worker does not own. |

**Score:** of the 6 blocking defects — 4 FIXED, 1 PARTIAL, 1 FORK. Of the 9 friction defects —
5 FIXED, 2 PARTIAL, 1 STILL OPEN, 1 FORK. Nothing in scope regressed on its own terms; the two
regressions below are new mechanics introduced by round-1 fixes.

---

## New defects introduced by the revision

All eight live in `we/skills/story/SKILL.md` — every one of them is **in scope**, none is a FORK.

### N1 — Step 5.0 produces no output, so Steps 5.1 and 5.4 have no value to use · **blocking**

> Step 5.0: `MAIN_WORKTREE=$(git worktree list --porcelain | awk …)`
> Step 5.1: "write the approved plan to `$MAIN_WORKTREE/docs/plans/{TICKET}-story.md`"
> Step 5.4: `[ -n "$MAIN_WORKTREE" ] || { echo "WARN: no worktree on main — plan saved, not committed."; exit; }`

The Step 5.0 command is a **bare assignment: it prints nothing.** The agent running it reads an
empty tool result and never learns the path. Two consequences, both in the same run:

1. Step 5.1 is a `Write`, not a shell command — a `Write` path is a literal string, and there is
   nothing to expand. A literal follower creates a directory named `$MAIN_WORKTREE`.
2. Step 5.4 is a separate Bash invocation; shell state does not survive between tool calls, so
   `$MAIN_WORKTREE` is empty there regardless. The guard trips and prints **"no worktree on main
   — plan saved, not committed"** on a repo that is standing on `main` — which is precisely the
   false-message failure mode round 1's D7 was raised to kill, re-created one line up.

I improvised (trace **37**): re-ran with `; echo "$MAIN_WORKTREE"` appended and substituted the
literal path by hand.

**Smallest fix:** append `; echo "$MAIN_WORKTREE"` to Step 5.0 and add one clause — "use the
printed path literally in 5.1 and 5.4" — or fold the resolution back into 5.4's own block and
have 5.1 say "the worktree where `main` is checked out (resolved in 5.0)".

### N2 — the accepted glossary entry is written but never staged · **blocking (silently)**

> Step 2: "offer to record it in the project glossary (`CONTEXT.md`) … and write it in **Step
> 5.1's commit**."
> Step 5.1: "Write the accepted `CONTEXT.md` glossary entry, if any, now."
> Step 5.4: `git add docs/plans/{TICKET}-story.md && git commit …`

The promise is explicit and the `git add` contradicts it. The user accepted my glossary offer at
trace **16**; I wrote the row at trace **39**; Step 5.4 stages one file and commits. `CONTEXT.md`
is left dirty in the main worktree of a repo the skill has just pushed to — the next agent finds
an uncommitted glossary change with no story attached, and this is the *quiet* failure: nothing
warns, the commit succeeds, the entry is simply not in it.

**Smallest fix:** `git add docs/plans/{TICKET}-story.md CONTEXT.md` — `git add` on an unmodified
path is a no-op, so the "no glossary entry" case needs no branch.

### N3 — `comments_read_through` is stale the moment Step 5.3 posts · **friction, but it is the new field's whole job**

> Step 1: "Note the newest comment's id or timestamp; it becomes the plan's
> `comments_read_through:`, which is how a later Lead tells 'the comments have overtaken this
> plan' from 'this plan already answered them'."
> Step 5.3: "add ONE comment naming each contradiction you resolved and each question you parked"

Step 5.3 makes *my own* comment the newest one on PROJ-812. The plan's
`comments_read_through: 10453` now points one comment behind the head, by construction, on every
single run — and the field carries no way to distinguish a self-authored comment from a foreign
one. The pointer-vs-head comparison the field exists to serve returns a mismatch on a plan that
is fresh. Nothing in Step 5 says to advance the marker after commenting.

**Smallest fix:** in Step 5.3, after the comment lands, "update the plan's
`comments_read_through:` to your own comment's id, so the marker means 'everything through my
answer'."

### N4 — "the repo's ready state" is undefined for `/we:story` · **friction**

> Step 5.3: "transition the ticket to **the repo's ready state**"

Nothing in `/we:story`'s reading list says what that is. `/we:orchestrate` sources its
state-name facts from `.weside/orchestrate.md`, which `/we:story` never reads and which need not
exist. At trace **42** I listed the transitions and picked `Selected for Development` over
`In Progress`, on the reasoning that `/we:story` stops before any build. That is a guess about
the board a PO looks at, and two sessions will make it differently.

**Smallest fix:** name the default and the source — "the repo's ready state
(`.weside/orchestrate.md` if present; otherwise the transition that means *refined, not yet
started* — ask once if the names are ambiguous)."

### N5 — Execution Surface recommends a shape that cannot run without Agent Teams · **blocking, and it is the last line the user reads**

> Step 5.7 output block: `Recommended next: /we:orchestrate {TICKET}` … "(or `--solo` if you'd
> rather run it inline.)"
> Execution Surface: "**Recommend `--solo`** **only** for a genuinely trivial, straight-line
> single-phase story."
> `we/skills/orchestrate/SKILL.md` Prerequisites: "**Agent Teams must be enabled** — flag, abort
> text and teardown: `references/agent-teams.md`."

Agent Teams is off in this world state. My plan has 5 phases and a non-empty `parallel_groups`,
so the heuristic recommends dispatched `/we:orchestrate PROJ-812` — which aborts on orchestrate's
Prerequisites before Step 0. And the heuristic does not merely fail to mention the flag: it
*actively steers away* from `--solo`, the one shape that runs here, by reserving it for trivial
single-phase work. The very last thing the session prints is an instruction that dead-ends.

**Smallest fix:** one clause in the Execution Surface section — "If Agent Teams is not enabled,
`--solo` is the only shape that runs: lead with it and say why, and mention that enabling Agent
Teams unlocks the dispatched shape."

### N6 — `Oracle:` is single-valued but the ladder is not · **friction**

> Plan template: "**Oracle:** cli | ui | substitute | not-applicable — *why this one*"
> `verification.md`: "Climb only as far as the ACs demand."

This story's ACs demand both: AC 1 is a reachability claim only a UI walkthrough proves, ACs 2–5
are machine-readable and belong on the CLI rung — and the CLI rung is also what makes the `/loop`
honest. "*why this one*" presumes exactly one. I wrote `ui — with a cli sub-assert` (trace **34**)
and hoped `we:ac-reviewer` reads the prose rather than matching the token.

**Smallest fix:** "**Oracle:** the highest rung the ACs demand, plus any lower rung you also
assert (e.g. `ui + cli`) — *why*."

### N7 — Step 5.3's prose and its own parenthetical order the calls differently · **friction**

> Step 5.3: "(`references/ticketing.md` — **transition first, comment second**, verify the move):
> **set the description** to the minimal body below, **add ONE comment** …, and **transition** the
> ticket"

The parenthetical and `ticketing.md` both say transition first; the sentence they introduce lists
transition last. I followed the parenthetical (traces **43–46**). Harmless in outcome here — the
description update is independent — but it is a contradiction inside one sentence, in the step
round 1's D6 fix just added, and it is the kind that survives because both readings work most of
the time.

**Smallest fix:** reorder the prose to match: "transition the ticket to the repo's ready state,
verify the move, then set the description to the minimal body below and add ONE comment naming …"

### N8 — nothing tells me how to derive `epic:` · **friction (carried, not introduced)**

The frontmatter comment calls `epic:` REQUIRED and warns that a missing value makes the story
invisible to the ready-set. No step says to take the ticket's parent, to read
`docs/plans/{EPIC}-epic.md`, or which of "`{EPIC-SLUG-OR-KEY}`" orchestrate actually matches on.
At trace **12** I read the epic plan unprompted and used the parent key. Round 1 raised this
under "What I needed and did not find" and it is unchanged; I list it here because it is the one
frontmatter field the skill itself calls load-bearing, and it is in this file.

**Smallest fix:** in Step 1, "take `epic:` from the ticket's parent key (or, with no ticketing
tool, the slug of the `-epic.md` plan that lists this story)."

---

## Still cuttable

The revision cut hard and cut well — the model-tier notice, the dead `.weside/` setup check, the
30-line AC-formula section, and two of the three stop-boundary restatements are gone, and I did
not miss any of them. What is left:

> "**Ticket is MINIMAL. Plan contains ALL details.**" *(under the Output table)*

The table one line above it already has a "Detail Level" column reading "minimal" and
"Acceptance Criteria, Technical Approach, Phases, Tests". Step 5.3's template says it a third
time by being a template. `dor.md` says it a fourth. `[UNPROMPTED]` — I wrote a minimal ticket
because the template is minimal.

> "Load more files than feel necessary; a wrong assumption costs more than a wide read." *(Step 3)*

`[UNPROMPTED]`. Traces **18–21** and **31–33** were driven by needing `Files:` lists and a
`Patterns:` line I could defend, not by this sentence.

> "User reviews the plan. On feedback → adjust and present again. On approval → Step 5
> immediately." *(Step 4, first sentence)*

That is a description of `ExitPlanMode`. The ⛔ line directly underneath carries the only part
that changes behaviour ("approval means run Step 5, not stop and summarize"). Round 1's open
question — what to do when approval comes back *with* edits — is still unanswered by this
sentence, so it is long without being complete.

> "- The plan filename suffix is `-story.md` (legacy `-plan.md` still read for back-compat)."
> *(Rules)*

Stated by the Output table's path, by every `{TICKET}-story.md` literal in Steps 1 and 5, and
verbatim in `docs/plan-format.md`'s own blockquote.

> "- **User-visible surfaces owe a proof block.** … 'tests are green' is a claim about units, not
> about the app." *(Rules, last bullet)*

The `## Verification` blockquote in the template already gates on this, `verification.md` argues
it at length in its "Why this exists" section, and both are in context. Third copy.

> "Lead with the recommended shape and name the phase count plus which phases parallelise."
> *(Step 5.7, after the output block)*

The output block it follows already shows exactly that, with the `←` comment slot spelling out
"phases N, parallel waves {…}". Prose restating a template it sits under.

Rough count: ~15 lines, against ~90 in round 1. The file is no longer meaningfully padded.

---

## Grade

**3/5** — a large, real improvement over round 1's 2/5 that stops short of a pass because the one
section round 1 singled out is still not executable. Every *conceptual* gap round 1 named has
closed, and closed properly rather than cosmetically: the ticket write-back loop that this
scenario exists to expose now runs end to end (transition, verify, one comment naming both
resolved contradictions and the parked self-revoke question), the graphify block is gated on the
flag that was always there to answer it and took the else-branch cleanly, the Verification field
names now match the receipt three files agree on, the `/loop` trigger is structural instead of a
feeling and honestly refused to fire on an unscriptable oracle, the glossary is read before the
ticket instead of after it, and the refine-in-place branch has a defined consequence. Blocking
count went 6 → 3. What holds it at 3 is that Step 5 — the rigid, numbered, "run these in order"
procedure round 1 called out for containing an unexecutable command — *still contains one*, for a
new reason its own D10 fix created: Step 5.0 prints nothing, so the path it resolves reaches
neither the `Write` in 5.1 nor the guard in 5.4, and 5.4 then announces "no worktree on main" on a
repo that is on main. Beside it, the accepted glossary entry is written and never staged despite
two lines promising it lands in that commit, and the session's final printed line routes this
user — Agent Teams off — into an `/we:orchestrate` that aborts on its own prerequisites while the
heuristic actively discourages the one shape that would run. All three are one-line fixes in the
file this worker already owns, which is why this is not a 2; that all three sit in the last
fifteen lines of the skill's most procedural section, after a round that named that section
specifically, is why it is not a 4.
