<!-- markdownlint-disable -->

# Round 4 — Scenario (a), verification round

Method note: I played the session from the skill text before opening round 3's report, and
I executed three real probes against the live harness rather than reasoning about them —
the Step 5.0 `awk`, `$CLAUDE_PLUGIN_ROOT` in a Bash call, and `orchestration.py`'s
`STORY_PHASES` / DB bootstrap. Two of the three changed my verdict.

## Trace

**Invocation:** `/we:story PROJ-812`. Session Sonnet, Agent Teams OFF, mode `acceptEdits`,
cwd `/home/user/proj` on `main`.

### Prerequisites

1. `Read(we/quality/dor.md)` — [UNPROMPTED-adjacent: I would read the DoR anyway, but not
   `long-running.md`.]
2. `Read(we/references/verification.md)`
3. `Read(we/references/long-running.md)` — read here, used once, 900 tokens later, at item 7.
4. `Bash: git rev-parse --show-toplevel` → `/home/user/proj`
5. `Read(/home/user/proj/.weside/dor.md)` → one extra row: *Every story names the rollback
   step.* Noted for `## Constraints and Pins` as `**Rollback step:** …`.
6. `Read(/home/user/proj/CONTEXT.md)` → `workspace` is `_Avoid_`, canonical term `tenant`.

Friction: the repo's `.weside/` is read in four separate places across four steps
(`dor.md` here, `vision.md` at Step 2, `config.json` at Step 3, `verify.md` at Step 3's
Verification block, `orchestrate.md` at Step 5.3). Nothing tells you to stat the directory
once, so I improvised a single `ls .weside/` to avoid five negative lookups later:

7. `Bash: ls -a /home/user/proj/.weside/` → `weside.md council.json config.json dor.md`.
   No `vision.md`, no `verify.md`, no `orchestrate.md`. [UNPROMPTED]

### Step 1: Load

8. `Read(we/references/ticketing.md)` — detection order. weside MCP has no `JIRA_*` tools in
   this session → path 2, Atlassian MCP.
9. `mcp__atlassian__jira_get_issue(issue_key="PROJ-812", fields="*all", comment_limit=20)`
   → Summary *Workspace admins can revoke a member's API token*; Status **Backlog**; parent
   **PROJ-800**; three comments — 10401 (14d, PO), 10437 (3d, tech lead), 10453 (yesterday, PO).
   - `epic:` = `PROJ-800`.
   - `comments_read_through:` = `10453` (provisional; item 3b rewrites it).
   - **Conflict, named to the user** as `ticketing.md` requires — not silently resolved:
     10401 grants a 60 s cache window; 10437 revokes that grant and adds an unstated
     requirement (auditable, one row per revoke); 10453 confirms 10437 and opens a fork
     (self-revoke) that nobody has closed. Newest wins → no 60 s window.
10. `Glob("docs/plans/PROJ-812-story.md")` → no match. New plan.
11. `Read(docs/plans/PROJ-800-epic.md)` → *Tenant access control*; success criteria mention
    per-tenant admin surfaces. [UNPROMPTED — Step 1 only asks for the parent *key*; reading the
    epic plan is my own habit and it is where the `tenant` vocabulary is already used
    consistently, which is evidence the CONTEXT.md rule is live and not aspirational.]

### Step 2: Understand (interactive, grill-style)

`.weside/vision.md` absent and no Companion connected → vision check skipped silently, as
instructed. Requirements are not vague (clear why, clear actor) → no brainstorming detour.
"Too big?" → **one coherent change with several phases**, not an Epic: one user-visible
capability, one PR's worth of value. Stays a Story.

12. **Q1 (the contradiction).** "10437 overrides 10401: no 60 s grace, the token cache is
    invalidated on revoke. 10453 agrees. My recommendation: synchronous invalidation, and the
    AC asserts the revoked token is rejected on the *next* request, not within 60 s. Confirm?"
    `[USER] Yes. The 60s window is dead — the lead is right, that was the whole point of the ticket.`
13. **Q2 (the open fork).** "10453 asks whether a member can revoke their own token, and marks
    it Open. Recommendation: out of scope here, admin-only; I park it as a comment on the ticket
    and a line for PROJ-800. Agree?"
    `[USER] Park it. Admin-only for now, self-revoke is a separate story.`
14. `Grep(pattern="class AuditLog|audit_log", include="*.py")` → `app/models/audit.py`:
    `AuditLog(actor_id, action, target_type, target_id, metadata, created_at)`.
15. **Q3 (auditable, one row per revoke).** "There is an `AuditLog` model. Recommendation: a new
    action `api_token.revoked` with `target_type='api_token'`, `metadata` carrying the tenant and
    the member — reuse rather than a new table, and make re-revoking idempotent so 'one row per
    revoke' means one row per *effective* revoke. Agree?"
    `[USER] Reuse AuditLog. Idempotent is right — a second revoke should not write a second row.`
16. **Q4 (blast of "instantly").** "Does revoke also terminate in-flight sessions/cookies, or
    API tokens only? Recommendation: tokens only — sessions are a different credential."
    `[USER] Tokens only.`
17. **Q5 (glossary offer).** "Two terms got resolved. `CONTEXT.md` already prefers **tenant**
    over *workspace*, and the ticket summary violates it. And 'instant revocation' now has a
    precise meaning. Offer: add a `revocation` entry — *the token is rejected on the next
    request; there is no grace window* — and mark `revocation window` as `_Avoid_`. Add it?"
    `[USER] Yes, add both. And fix the ticket summary while you're at it.`
18. **Q6 (the repo-local DoR row).** "`.weside/dor.md` requires a named rollback step.
    Recommendation: the change is additive — a nullable `revoked_at`/`revoked_by` plus a cache
    eviction call — so rollback is reverting the release; already-revoked tokens then fall back
    to expiring with the 60 s cache TTL, i.e. still rejected, just later. Acceptable?"
    `[USER] Yes, that's an acceptable rollback.`

### Step 3: Create Plan

19. TurboVault MCP unavailable → printed once, verbatim:
    *"⚠️ TurboVault unavailable — using grep fallback; architecture context may be incomplete.
    Check the MCP config."*
20. `Grep(pattern="API token|token cache|revoke", include="*.md")` → `docs/architecture/auth.md`,
    `docs/architecture/caching.md`.
21. `Glob("docs/architecture/**/*.md")` → 6 files; read `auth.md` and `caching.md`.
22. **Blast radius.** `Read(.weside/config.json)` → `tools.graphify: false`. The skill's
    condition is *true, or the file absent and `graphify --version` answers*. The file is present
    and false → **neither branch holds, and I correctly did not run `graphify --version` at all**.
    This is right, and it is the only place in the skill where a three-state config is handled
    without a wasted probe. → `rg` fallback plus the mandated sentence in Technical Approach.
23. `rg -n "ApiToken|api_token" --type py -l` → 7 files.
24. `rg -n "TokenCache|token_cache" -l` → 3 files.
25. `rg -n "ApiToken" apps/*/tests -l` → 2 test files (pulled into the phase `Files:` lists).
26. `Read(docs/plan-format.md)` — [UNPROMPTED; the skill embeds its own template and never
    points here, so this was a hedge. It matched.]
27. `EnterPlanMode` with the plan below.

### Step 4: Approval

28. `ExitPlanMode` → `[USER] Approved. Go.`

### Step 5

29–43: item by item in the next section.

---

## Step 5, item by item

| # | Executable exactly as written here? | Actual effect |
|---|---|---|
| **0** | **YES** — probed for real. `git worktree list --porcelain \| awk '/^worktree /{p=$2} /^branch refs\/heads\/main$/{print p; exit}'` runs against a live multi-worktree repo and prints the `main` path. | Printed `/home/user/proj`. Non-empty → item 4 stays in play. The "print the path and use it literally" instruction is the single best line in Step 5 and I obeyed it. |
| **1** | **YES.** `Write` to `/home/user/proj/docs/plans/PROJ-812-story.md` with `status: approved`, `story: PROJ-812`. Plus `Edit(CONTEXT.md)` for the accepted glossary entry. | Plan on disk (full text below). `CONTEXT.md` gains `revocation` and `revocation window (_Avoid_)`. Nothing ambiguous — the path came from item 0 as a literal. |
| **2** | **YES**, but it is a `Read` + three human regex checks, not a command. `Read(we/references/dor-scan.md)` then inspect. | All three pass: `Given/When/Then` present (AC1), `## Context` has ~700 chars, `### Phase 1:` matches `^### Phase [0-9]+:`. No fix loop. |
| **3** | **NO — not "in one pass", and it forces a user question inside a block headed EXECUTE IMMEDIATELY.** Under `ticketing.md` it expands to five calls, and the ready-state name is ambiguous here because `.weside/orchestrate.md` does not exist. | (a) `jira_get_transitions(PROJ-812)` → `To Do`, `Selected for Development`, `In Progress`, `Done`. Two of those plausibly mean *refined, not yet started* → the skill's "ask once when ambiguous" fires. **I had to stop and ask the user, after approval, mid-execute.** `[USER] Selected for Development.` (b) `jira_transition_issue(transition_id="21")`, bare, no `comment` field — `ticketing.md`'s ADF trap avoided. (c) `jira_get_issue(PROJ-812, fields="status")` → verified `Selected for Development`. (d) `jira_update_issue(fields='{"summary":"Tenant admins can revoke a member API token","description":"## User Story\\nAs a tenant admin I want to revoke a member API token so that a leaked token stops working.\\n\\n## Plan\\nImplementation Plan: docs/plans/PROJ-812-story.md"}')` — summary rewritten because it carried the `_Avoid_` term `Workspace`. (e) `jira_add_comment(...)` → **id 10461**, naming: the 10401↔10437 contradiction and that 10437+10453 win (no 60 s window); the parked self-revoke fork; the summary rewrite. |
| **3b** | **YES.** The `jira_add_comment` schema returns "the added comment object", which carries `id` — I loaded the schema rather than assuming it. | `Edit` on the plan frontmatter: `comments_read_through: 10453` → `10461`. The plan now says "read through my own answer", which is exactly what orchestrate Step 3 signal 5 needs. This is a genuine, working mechanic. |
| **4** | **YES here** — and only because `CONTEXT.md` exists *and* was modified. | `cd /home/user/proj`; `git add docs/plans/PROJ-812-story.md CONTEXT.md && git commit -m "docs: add PROJ-812 plan — Tenant admins can revoke a member API token"` → commit created; `git push` → succeeded (no protection on this repo's `main` in the scenario). **Latent, does not fire here:** in a repo with no `CONTEXT.md`, `git add` fails, the `&&` short-circuits, and the fallback prints `WARN: commit failed (hook rewrite?)` — a message that misdiagnoses the one failure it was written to disambiguate. The step's own stated goal is "one failure mode per message". |
| **5** | **NO. This is round 4's Step-5 command that cannot run.** `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/orchestration.py story checkpoint PROJ-812 refined`. I measured it: `echo "[$CLAUDE_PLUGIN_ROOT]"` in a Bash tool call prints `[]`, and `env \| grep -c CLAUDE_PLUGIN_ROOT` returns 0. The variable is a *skill-text* token the model substitutes, not a shell env var — and every other use of it in this skill is inside a `Read(...)`, where the model does substitute. Item 5 is the only place it is handed to a shell. As written it expands to `python3 /scripts/orchestration.py …` → `can't open file '/scripts/orchestration.py'`. | I improvised the substitution by hand: `python3 <worktree>/we/scripts/orchestration.py story checkpoint PROJ-812 refined`. **After substitution it works** — I verified `refined` is the first entry of `STORY_PHASES` (so the `choices=` check passes) and that `_ensure_db()` creates `~/.claude/weside/orchestration.db` on first use, so no `init` is owed. The defect is purely the unsubstituted variable, and the skill never says to substitute it. Worse: item 0 goes out of its way to warn about a *different* shell hazard ("shell state does not survive between tool calls"), which primes the reader to trust the remaining snippets verbatim. |
| **6** | **YES** (as a no-op). TurboVault MCP unavailable. | Skipped silently. Correct — no output, no apology. |
| **7** | **PARTIALLY — the template contradicts the heuristic it is supposed to render.** First, the precondition *is* detectable now: *Execution Surface* points at `references/agent-teams.md`, which names the flag, so I ran `Read(~/.claude/settings.json)` → no `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS` key → OFF. That is a real detection path and it did not need the scenario briefing. Agent Teams is OFF, so *Execution Surface* says `--solo` is the only shape that runs and dispatch "aborts on orchestrate's own prerequisites". But the mandated block ends with `(or <the other shape> if you'd rather run it the other way.)` — literally following it offers the user a shape that aborts. I improvised: I kept the parenthetical but rewrote it into the "enabling Agent Teams unlocks it" sentence the heuristic also asks for. | Printed the block below. Also: the plan has **4 phases** → `long-running.md`'s structural trigger fires → `/loop` printed. And it is an **auth path** → `/goal`'s critical bar is met too. The skill says "`/loop` (or, at its bar, `/goal`)" — exclusive — while `long-running.md`'s own template is additive (`/goal` is an extra line *under* the `/loop` line). Both files are mine; they disagree, and in this world both fire, so the disagreement is not theoretical. |

Where the skill left me guessing, in order of cost:

- **The ready-state name** (item 3). No `.weside/orchestrate.md`, two plausible Jira states.
  The skill's escape hatch is "ask once" — but it places that question *after* ExitPlanMode,
  inside a block whose header is a ⛔ demanding immediate uninterrupted execution.
- **Where item 3b re-opens the plan from.** It says "Re-open the plan", not
  "`<main-worktree>/docs/plans/…`". Item 1 was careful about this; 3b forgot. Harmless here
  because cwd *is* the main worktree; a lie in the exact case item 0 exists to handle.
- **`.weside/verify.md` absent.** `verification.md` says "propose adding it in the same PR" —
  but `/we:story` opens no PR (item 7's ⛔ forbids it). I improvised: proposed it under
  *Documentation Impact → New doc* with the reason, as SKILL.md's Verification block directs.
  The two files give different homes for the same proposal.
- **`## Documentation Impact` has no row for a repo-config file.** `.weside/verify.md` is not a
  docstring, an architecture doc, an ADR, or generated. It lands under "New doc", which demands
  "the reason the code cannot hold it" — a question that does not apply to a config recipe.

---

## The plan I would have written

```markdown
---
type: story-plan
story: PROJ-812
epic: PROJ-800
depends_on: []
comments_read_through: 10461
created: 2026-08-27
status: approved
parallel_groups: [[3, 4]]
---

# Plan: Tenant admins can revoke a member API token

## Context

A leaked API token is currently unstoppable short of rotating the member's whole credential
set, and the ticket exists because that happened. The description still reflects an older
agreement — comment 10401 accepted a 60 s window because tokens are cached for that long —
but comment 10437 withdrew it and comment 10453 confirmed the withdrawal: revocation must
invalidate the token cache, not wait it out. That reversal is the single most important thing
about this story, and it turns a one-column migration into a cache-coherence change. The tech
lead also added a requirement the description never mentions: every revoke is auditable, one
row per revoke. We settled that "one row per revoke" means one row per *effective* revoke —
re-revoking an already-revoked token is idempotent and writes nothing. Self-revoke by the
member themselves (10453) is explicitly parked, not built. Scope is API tokens only; sessions
and cookies are a different credential and out of scope.

## Acceptance Criteria

1. **Given** a tenant admin and a member with an active API token
   **When** the admin revokes that token
   **Then** the very next request authenticated with it is rejected with 401 — with no grace
   window, and specifically not after a 60 s cache TTL.
2. **Given** a token that was just revoked
   **When** the audit log is read for that tenant
   **Then** exactly one `api_token.revoked` row exists, carrying the acting admin, the tenant,
   the member and the token id.
3. **Given** an already-revoked token
   **When** the admin revokes it again
   **Then** the call succeeds idempotently and **no** second audit row is written.
4. **Given** an admin of a *different* tenant
   **When** they attempt to revoke this token
   **Then** the call is rejected with 404 (not 403) and no audit row is written.
5. **Given** a member (non-admin) of the same tenant
   **When** they attempt to revoke another member's token
   **Then** the call is rejected with 403.

## User Journey

1. A member reports a leaked token. 2. The tenant admin opens the member's token list and
revokes the token. 3. The next call made with that token fails immediately. 4. The admin sees
the revocation in the tenant's audit log with their own name on it.

## Testing Requirements

- Unit tests for the revocation service: idempotency (AC3), audit-row shape (AC2), cache-key
  derivation. Phase 2.
- Unit tests for the authz predicate: cross-tenant 404 vs same-tenant-non-admin 403. Phase 3.
- Integration tests — `pytest tests/integration/test_token_revocation.py` against the real
  Postgres test database (`alembic upgrade head` on the test DB first) and a real Redis, not a
  mocked cache: the eviction is the thing under test and a mocked cache makes AC1 vacuously
  green. Phases 2 and 3.
- Migration test: the Alembic revision applies and reverses cleanly. Phase 1.

## Verification

> The repo has no `.weside/verify.md` — said once here, proposed under Documentation Impact.

- **Oracle:** `cli` only. Every AC is an API/state assertion; nothing in this story says the
  user *sees*, *taps* or *navigates to* anything, so rung 2 is not demanded and I do not claim
  it. Rung 3/4 do not apply — there is a running local backend. **Not claimed:** that any UI
  surfaces the revoke action; no AC asks for one and no UI ships in this story.
- **Seed:** `./manage.py tokens:issue --tenant acme --member bob` (does not exist yet — see
  *Missing CLI verb*), then `curl -sS -H "Authorization: Bearer $T" localhost:8000/v1/me` → 200.
- **Asserted:** `./manage.py tokens:revoke --token-id $ID` exits 0; the same `curl` returns
  **401** on the immediately following request; `GET /v1/tenants/acme/audit?action=api_token.revoked`
  returns exactly one row whose `actor_id` is the admin; a second `tokens:revoke` exits 0 and
  the audit query still returns exactly one row.
- **Not proven:** behaviour under a multi-node cache (this asserts one Redis, one app process),
  and that no admin UI regressed — nobody built one. Owed by whoever ships the admin surface.
- **Exit criterion:** `pytest tests/integration/test_token_revocation.py` green **and** the
  four-command seed/assert sequence above reproduced by hand on DEV, with the 401 observed on
  the first request after revoke.
- **Missing CLI verb:** `tokens:issue` and `tokens:revoke` — the seed cannot create a token and
  the assert cannot revoke one without them. They ship in **Phase 4**, not Phase 1: the revoke
  verb is a thin caller of the revocation service that Phase 2 introduces, and shipping it
  earlier would mean shipping a verb with nothing behind it. Phase 4 is as early as its own
  dependency allows. Until Phase 4 lands, phases 1–3 verify through the integration suite only,
  and that is stated in each phase's Risk line.

## Technical Approach

**Patterns:** `AuditLog` (`app/models/audit.py`) is reused rather than a second audit table —
one action name `api_token.revoked`. The token cache is the existing `TokenCache` wrapper; the
revocation service evicts the key inside the same transaction boundary that writes
`revoked_at`, so a crash between them leaves the token *revoked in the DB and stale in cache*
for at most the TTL — the fail direction we chose, because the reverse (cache evicted, DB not
written) would silently un-revoke. Architecture refs: `docs/architecture/auth.md` (token
lifecycle), `docs/architecture/caching.md` (TTL and key scheme) — found by grep.

`Files:` lists are grep-derived — no code graph (`.weside/config.json` → `tools.graphify` is
false). The disjointness guard on `parallel_groups: [[3,4]]` is worth exactly what `rg` on
`ApiToken`, `TokenCache` and `AuditLog` is worth; a shared seam in a file neither grep named is
invisible to it.

## Implementation Phases

### Phase 1: Revocation columns + audit action
- **Goal:** an API token can be *marked* revoked, and the audit vocabulary exists.
- **Files:** `app/models/api_token.py`, `app/models/audit.py`,
  `migrations/versions/<new>_api_token_revocation.py`, `tests/unit/test_api_token_model.py`
- **Risk:** migration — on `api_token`, a table every authenticated request reads. Nullable
  columns only, no backfill, no index rebuild.
- **Approach:** nullable `revoked_at: datetime`, `revoked_by: FK(user)`. Add the
  `api_token.revoked` action constant. No behaviour reads the columns yet.

### Phase 2: Revocation service + synchronous cache invalidation
- **Goal:** revoking makes the token stop working on the next request, once, auditably.
- **Files:** `app/services/token_revocation.py` (new), `app/services/token_cache.py`,
  `app/auth/verify.py`, `tests/unit/test_token_revocation_service.py`,
  `tests/integration/test_token_revocation.py` (new)
- **Risk:** auth — this is the code path that decides whether a credential is still valid.
  Named integration suite, real Redis, no mocked cache.
- **Approach:** `revoke(token_id, actor)` → early-return when `revoked_at` is already set
  (AC3), else set the columns, write one `AuditLog` row, evict the cache key, commit. The
  verify path treats a `revoked_at` that is not null as invalid.

### Phase 3: Admin endpoint + authz
- **Goal:** a tenant admin can reach the revocation over the API, and nobody else can.
- **Files:** `app/api/tenants/tokens.py`, `app/api/deps/authz.py`, `openapi.json`,
  `packages/client/src/generated/*` (regenerated), `tests/unit/test_token_authz.py`,
  `tests/integration/test_token_revocation.py`
- **Risk:** tenant-isolation — the boundary is the tenant scope on the token lookup; a
  cross-tenant token id must 404 before authz is even consulted (AC4).
- **Approach:** `DELETE /v1/tenants/{tenant}/members/{member}/tokens/{token_id}`. Scope the
  lookup by tenant first (404), then require the tenant-admin role (403). Regenerate the spec
  and the TS client in the same phase.

### Phase 4: CLI verbs + verification recipe
- **Goal:** the story is verifiable by someone who was not in the room.
- **Files:** `manage.py`, `app/cli/tokens.py` (new), `.weside/verify.md` (new),
  `tests/unit/test_cli_tokens.py`
- **Risk:** ordinary — thin callers over Phase 2's service; no new decision logic.
- **Approach:** `tokens:issue` and `tokens:revoke` as thin wrappers. `.weside/verify.md` gets
  the DEV bring-up, these two verbs, and the revoke journey as its first recipe.

## Constraints and Pins

**Constraints:** reuse `AuditLog`, do not add a second audit table; the token cache is only
touched through `TokenCache`, never through the Redis client directly; the tenant scope goes on
the *query*, not on a post-fetch check.
**Pins:** an unrevoked token's verify path stays on the cached happy path — no extra DB read per
request; the 60 s cache TTL itself is unchanged (revocation evicts, it does not shorten the
TTL); `AuditLog`'s existing action names are untouched.
**Rollback step:** the change is additive — revert the release. Already-revoked tokens then
stop being rejected by the verify path and fall back to expiring with the 60 s cache TTL plus
their own expiry; no data is lost and the migration's columns can stay in place. Reverting the
migration is a separate, optional step and is not required to restore service.

## Design Decisions

| Decision | Alternatives Considered | Why This |
|---|---|---|
| Synchronous cache invalidation, no grace window | The 60 s window agreed in comment 10401 | Comment 10437 withdrew it and 10453 confirmed; a leaked token that keeps working for 60 s is the exact failure the ticket exists to stop |
| Reuse `AuditLog` with a new action | A dedicated `token_revocations` table | One audit surface; the ask was "auditable, one row per revoke", not a new query surface |
| Idempotent re-revoke, no second row | Write a row per call | "One row per revoke" read as one row per *effective* revoke; a retry must not forge a second event |
| Cross-tenant → 404, same-tenant non-admin → 403 | 403 for both | 403 on a foreign id confirms the id exists; that is a tenant leak |
| Admin-only; self-revoke parked | Ship self-revoke now (comment 10453) | 10453 marks it Open, not agreed — it is a product decision, and it changes the authz shape |
| API tokens only | Also terminate sessions | Different credential, different lifecycle; nothing in the ticket asks for it |

## Code Guidance

**DO:** early-return on an already-revoked token before writing anything; evict the cache key
inside the same commit boundary as the column write; scope the token lookup by tenant in the
query itself.
**DON'T:** mock the cache in the integration test — AC1 is exactly the cache behaviour and a
mock makes it vacuously green; don't add a per-request DB read to the verify happy path;
don't write the audit row from the endpoint (it belongs to the service, so the CLI verb gets it
too).

## Security Review Required

Yes — this is an authentication credential's lifecycle plus a cross-tenant authorization
boundary. AC4 and AC5 are the review's focus.

## Documentation Impact

- **Docstrings** — `token_revocation.revoke()` carries the idempotency reasoning and the
  chosen crash-failure direction (revoked-in-DB, stale-in-cache); `app/auth/verify.py` carries
  why `revoked_at` is checked on the cache-miss path.
- **Architecture doc** — `docs/architecture/auth.md`: the token lifecycle gains a revoked
  state; one paragraph plus the state list.
- **ADR** — no. Reversible, unsurprising, no live trade-off left open.
- **Generated** — `openapi.json` and the TS client, in Phase 3.
- **New doc** — `.weside/verify.md`. Named because the code genuinely cannot hold it: it is
  the repo's verification *recipe* (how DEV comes up, which verbs exist, which journeys), read
  by `/we:orchestrate` and `we:ac-reviewer` before any code is read. Phase 4.
```

And the item-7 output I would have printed:

```
Plan saved to docs/plans/PROJ-812-story.md. /we:story DONE.
State file: docs/plans/PROJ-812-state.md (the Lead creates it on the first run).

Recommended next: /we:orchestrate PROJ-812 --solo   ← Agent Teams is off, so phase dispatch
aborts on orchestrate's own prerequisites; --solo is the only shape that runs. (The plan
would otherwise argue for dispatch: 4 phases, parallel wave [[3,4]], auth risk class.)
Enabling CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1 in ~/.claude/settings.json and restarting
unlocks the dispatched shape.

Long-running:
  ⚠ The oracle is not scriptable yet — the seed needs `tokens:issue`, which Phase 4 ships.
    Round 1's job is to make Phase 4's verbs exist before the loop can judge itself.
  /loop Run PROJ-812 phase by phase until: pytest tests/integration/test_token_revocation.py
        is green AND the seed/assert sequence in the plan's Verification block reproduces the
        401 on the first request after revoke.
  /goal integration suite green and the post-revoke 401 observed on DEV   ← auth path;
        wrong-about-done is expensive
```

---

## Round-3 verdict table

*(filled after everything above was written to disk — see the Method note.)*

| # | Round-3 defect | Verdict | Evidence from this run |
|---|---|---|---|
| **N1** (partial half) | 5.4 references `$MAIN_WORKTREE`, a variable the skill assigns nowhere; a literal run prints "no worktree on main" while standing on main and commits nothing · *blocking* | **FIXED** | Item 4 now opens `cd <main-worktree> \|\| exit` with the `[ -n … ]` guard gone entirely — round 3's proposed smallest fix, adopted exactly. I substituted item 0's printed `/home/user/proj` and the commit + push ran. No variable survives anywhere in Step 5's shell snippets. The empty-output branch it used to guard is handled where it belongs, in item 0's own sentence ("say so, skip step 4, and keep going"). |
| **N3** (partial half) | The `comments_read_through` rewrite is semantically right but has no home in the numbered order; every run improvises an unlisted `Edit` · *friction, silently corrupting* | **FIXED** | There is now a numbered **item 3b**: "Re-open the plan and set `comments_read_through:` to the id of the comment you just posted … A frontmatter value; the step-2 scan still holds." Both open questions answered in one line — where the write happens, and whether 5.2 re-runs. I executed it as a listed step (10453 → 10461), improvising nothing. I also checked the mechanic is real rather than assumed: `jira_add_comment`'s schema returns "the added comment object", which carries the id 3b needs. Residue, one line: 3b says "the plan", not `<main-worktree>/docs/plans/…` — the one place in Step 5 that reverts to an implicit path, in a step block whose item 0 exists precisely to forbid that. |
| **N5** (partial half) | 5.7's fenced block hardcodes `/we:orchestrate {TICKET}` and demotes `--solo`, contradicting the Agent-Teams clause below it; and nothing says how to detect Agent Teams · *blocking* | **PARTIALLY FIXED** | Both halves round 3 named are closed. The block is now parameterised — `Recommended next: /we:orchestrate {TICKET} [--solo]` with a `← why` slot — so a literal reader no longer emits a fixed wrong default; and *Execution Surface* now names the detection path ("the env flag in `${CLAUDE_PLUGIN_ROOT}/references/agent-teams.md`; ask when you cannot read it"), which I followed to `~/.claude/settings.json` and resolved without the scenario telling me. **The disease survives one layer down:** the block still mandates a closing `(or <the other shape> if you'd rather run it the other way.)`, and with Agent Teams off the other shape is precisely the one the same section says "aborts on orchestrate's own prerequisites". The last line the user reads still offers something that cannot run — a smaller version of exactly what N5 was about. See S2. |
| **R1** | `$MAIN_WORKTREE` has zero assignments and two uses · *blocking* | **FIXED** | Same evidence as N1. Round 3's exact proposed edit. |
| **R2** | 5.3's marker rewrite has no home in the numbered order · *friction* | **FIXED** | Same evidence as N3 — the `5.3b` round 3 asked for exists, near-verbatim. |
| **R3** | The `_Avoid_` term sits in the ticket summary, the one field Step 5 never writes · *friction* | **FIXED** | Item 3 now reads "Set the summary too when it carries a glossary `_Avoid_` term — it is the field every board and roll-up shows — and say in the comment that you rewrote it." All three clauses fired in my run: `Workspace admins…` → `Tenant admins…`, in the same `jira_update_issue` call as the description, and the rewrite is named in comment 10461. Round 3 had to improvise that call; I did not. |
| **R4** | The repo-local DoR row has a format but no slot; three rounds put it in three places · *friction, carried twice* | **FIXED** (in this file list) | Prerequisites now ends "… appended to the plan's `## Constraints and Pins`, because `/we:orchestrate` gates on it and names the failing row — **one fixed home, so the gate knows where to look**." I wrote `**Rollback step:**` there with no deliberation at all — the first round in which this cost zero thought. Two residues, both small and one of them a FORK: the Step-3 template's `## Constraints and Pins` block still shows only `**Constraints:**` / `**Pins:**`, so a reader working from the template alone gets no reminder; and orchestrate Step 1 still says only "a plan that fails a row there goes back to the refine lane" without naming the section it now has a right to expect — **FORK**, orchestrate's wording. |
| **R5** | 5.7's `/loop` clause tells the reader both to print and not to print when the oracle is not yet scriptable · *friction* | **FIXED** | Item 7 now picks one branch: "When the plan's `## Verification` does not yet name a scriptable oracle, print it anyway with the blocker named on the line above it, and make the first round's job to make the oracle scriptable." My world exercises it — the seed needs `tokens:issue`, which Phase 4 ships — and the coin flip round 3 had to make was gone; I printed the invocation with the blocker line above it, as the sentence says. |
| **R6** | Nothing closes the loop on a parked open question; orchestrate signal 1 may bounce a plan whose parked question was answered in the story's own comment · *friction* | **FORK — and still open** | Round 3 already classified this as a FORK and I agree with the scoping. Confirmed unchanged on the other side: orchestrate Step 3 signal 1 still reads "an open question in the ticket (summary, description, or an unanswered comment)", with no notion of "answered by the refiner's own comment". What `/we:story` owes it, it now delivers — item 3's comment names the parked fork, and 3b sets `comments_read_through:` to that comment's id, which is exactly the handle orchestrate would need. The consuming wording is orchestrate's to write. |

**Tally:** 6 FIXED, 1 PARTIALLY FIXED, 0 STILL OPEN, 1 FORK. Every one-line edit round 3 named
as the path to a 4 was made, and made in round 3's own wording.

---

## New defects introduced by this revision

### S1 — item 5's `${CLAUDE_PLUGIN_ROOT}` is a shell variable that is never set · **blocking**

**Honest framing first: this revision did not introduce it.** It is unchanged from round 1, and
all three prior rounds certified item 5 as executable — round 3's table says "**Yes.** … The
script exists in the plugin tree, so this is a real invocation." That check confirmed the *file
exists*. It never checked that the *path expands*.

I measured it instead of reading it:

```
$ echo "PLUGIN_ROOT=[$CLAUDE_PLUGIN_ROOT]"
PLUGIN_ROOT=[]
$ env | grep -c CLAUDE_PLUGIN_ROOT
0
```

`CLAUDE_PLUGIN_ROOT` is a skill-text token the model substitutes when it composes a call — which
is why the three `Read("${CLAUDE_PLUGIN_ROOT}/…")` lines in Prerequisites work fine. Item 5 is
the **only** place in this skill where the token is handed to a shell, and there nothing
substitutes it. Run literally:

```
python3 /scripts/orchestration.py story checkpoint PROJ-812 refined
python3: can't open file '/scripts/orchestration.py': [Errno 2] No such file or directory
```

Two things make this worse than a typo. First, item 0 spends a sentence warning about a
*different* shell hazard ("shell state does not survive between tool calls"), which certifies the
snippets as shell-aware and primes the reader to run the rest verbatim. Second, the checkpoint is
the artifact `/we:orchestrate` Step 2 reads to classify PROJ-812 as `refined` — a silently
skipped item 5 puts the story in the `draft` lane and sends a finished plan back to a refiner.

I verified the fix is only the path: after hand-substituting, the command works — `refined` is
the first entry of `STORY_PHASES` so the `choices=` check passes, and `orchestration.py` creates
`~/.claude/weside/orchestration.db` on first use, so no `init` is owed.

**Smallest fix:** make item 5 a `Bash` call with the plugin root substituted the way item 0
teaches — "print the plugin root once and use it literally" — or drop the shell entirely and
state the command with an explicit note that the reader substitutes the plugin path. The same
line in `quality/dor.md` § Checkpoint has the identical defect — **FORK**.

### S2 — item 7 mandates offering a shape that cannot run · **friction, introduced here**

The fenced block ends with `(or <the other shape> if you'd rather run it the other way.)`. With
Agent Teams off — this world — the other shape is dispatch, and *Execution Surface* twelve lines
below says dispatch "aborts on orchestrate's own prerequisites there". Following the block
literally hands the user a command that dies on its prerequisites; following the prose means not
following the block. I improvised: I kept the line but rewrote it into the "enabling Agent Teams
unlocks it" sentence the heuristic separately asks for.

This is N5's disease at one-tenth scale, and it is new — round 3's block had no such
parenthetical.

**Smallest fix:** make the parenthetical conditional in the block itself — "(or `<the other
shape>` if you'd rather run it the other way — **or, when Agent Teams is off, what enabling it
would unlock.**)"

### S3 — item 7 makes `/loop` and `/goal` exclusive; `long-running.md` makes them additive · **friction, introduced here**

Item 7: "Print the `/loop` (or, at its bar, `/goal`) invocation when …". The parenthetical reads
as *either/or*. `long-running.md` — also in this file list — shows the opposite: a `/loop` line,
with `/goal` **added below it** ("Add `/goal` **only** when the story meets the critical bar
above"). This is not theoretical here: the plan has 4 phases, so `/loop`'s structural trigger
fires, and it is an auth path, so `/goal`'s critical bar is met. Both fire, and the two files
disagree about whether that is legal. I followed `long-running.md` (additive) because it is the
file that owns the mechanic.

**Smallest fix:** item 7 — "Print the `/loop` invocation when `references/long-running.md`'s
trigger fires, and add its `/goal` line when the story also meets the critical bar."

### S4 — item 3 forces a user question inside a ⛔ "EXECUTE IMMEDIATELY" block · **friction, carried and now sharper**

The "ask once when the board's names are ambiguous" clause was round 2's fix and it is genuinely
good — it stopped me guessing between `To Do` and `Selected for Development`. But it fires at
item 3, *after* ExitPlanMode, inside a block headed "⛔ ExitPlanMode approval means 'run Step 5',
not 'stop and summarize'." The user approves a plan and is then stopped for a board-vocabulary
question that has nothing to do with the plan and could have been asked at any point in Step 2,
when they were already in the room.

**Smallest fix:** move the detection into Step 2's tail — "if the ticketing tool is connected and
`.weside/orchestrate.md` is absent, resolve the ready state now, while the user is present" —
leaving item 3 to execute a decision already made.

### S5 — item 3b is the one Step-5 line with an implicit path · **friction, introduced here**

"Re-open the plan" — items 1 and 4 both name `<main-worktree>/…`. Harmless in this world because
cwd *is* the main worktree; wrong in exactly the case item 0 was written to handle. One word.

### S6 — item 4's `git add … CONTEXT.md` fails closed, and the WARN misdiagnoses it · **latent here, does not fire**

`git add docs/plans/{TICKET}-story.md CONTEXT.md` runs fine in this world: `CONTEXT.md` exists
and the accepted glossary entry modified it. In a repo with **no** `CONTEXT.md` — the majority
case, and the case the skill's own "read `CONTEXT.md` … if it exists" anticipates — `git add`
errors on the missing pathspec, the `&&` short-circuits, and the fallback prints
`WARN: commit failed (hook rewrite?) — re-add and commit by hand.` The step's stated design goal
is "one failure mode per message, so a wrong diagnosis never sends the reader to the wrong
place", and this is a wrong diagnosis. Reported as latent, not as this world's failure.

**Smallest fix:** `git add docs/plans/{TICKET}-story.md && git add CONTEXT.md 2>/dev/null; git commit …`

### S7 — the ticket is marked ready before the plan it links exists on origin · **ordering, this file's to fix**

Item 3 transitions PROJ-812 to `Selected for Development` and sets a description pointing at
`docs/plans/PROJ-812-story.md`. Item 4, two steps later, commits and pushes that file — and it
soft-warns on failure (`WARN: committed locally, push failed (branch protection?)`), which is the
*likely* outcome on any repo with a protected `main`. The board then says refined-and-ready while
the linked plan exists on one laptop. The transition-and-verify *mechanics* are `ticketing.md`'s
(FORK), but the **order of items 3 and 4 is this file's**.

**Smallest fix:** swap — commit and push the plan (item 4), then move the ticket (item 3). The
only reason 3 precedes 4 today is that 3b needs the comment id before the commit; that is
satisfied by ordering as write-plan → ticket pass → 3b → commit.

---

## Still cuttable

Round 3's list was actioned in full — every one of its five entries is gone from the file
(`Legacy -plan.md`, "the urge to split into phases", the two Execution Surface table rows, the
`story` table-name trivia, the `ticket-briefs.md` wording summary). I did not want any of them
back. What is left is thinner and mostly structural:

> `Read("${CLAUDE_PLUGIN_ROOT}/references/long-running.md")` — *Prerequisites*

The strongest cut available, and it is not about redundancy. `long-running.md` is a
**mandatory** read on every single `/we:story` invocation, and it is consumed at exactly one
place: item 7, at the very end. Its trigger is structural and stated in one sentence ("4+ phases,
or a non-empty `depends_on:`, or the user says they will be away") — which the skill could carry
inline. Every run that ends with three phases pays ~1.5 k tokens of context for a file it never
uses. `verification.md` earns its prerequisite slot (it shapes the plan template the whole way
through); this one does not. Move it to a conditional read inside item 7.

> "Anything beyond this template follows `${CLAUDE_PLUGIN_ROOT}/references/ticket-briefs.md`."
> *(item 3, after the minimal template)*

Round 3 listed the appended summary; that is gone, but the pointer remains and it is dead by
construction. `/we:story`'s ticket **is** the template — item 3 says so, `dor.md` says so
("Details are in the Plan, NOT in the ticket"), and `ticket-briefs.md` itself opens by scoping
its `/we:story` consumer to "ticket *wording* only — its ticket stays minimal and the ACs live
in the plan". There is no "beyond" for this skill. I read the reference and it changed nothing I
wrote. It is a legitimate reference for `/we:triage` and worker briefs; the call site here is
the cut.

> "Audit the verbs `.weside/verify.md` already lists against the ACs before you conclude none is
> missing: **a verb that cannot go red is as absent as one that does not exist.**" *(Step 3)*

Two lines guarding a file that, per `verification.md`'s own framing, is usually absent — as it is
here. The sharp half ("a verb that cannot go red is as absent as one that does not exist")
belongs in `verification.md` next to the *missing verb* contract it qualifies, not restated in
the plan template.

> "**Plans are living.** … See `references/programme-discipline.md`." *(Rules)*

A DoD obligation for a *later* skill, sitting in the file that ends with a ⛔ forbidding any work
past Step 5. It never touched a decision in this run, and `programme-discipline.md` owns it.

Rough count: ~10 lines plus one prerequisite read. The file is lean; the remaining weight is a
context tax, not padding.

---

## Grade

**4/5** — the first round where the revision cleared everything that was named. Round 3 ended
with "three one-line edits inside this worker's own file list turn this into a 4", and all three
were made in round 3's own wording, plus R3, R4 and R5 on top: item 4 no longer references a
variable nobody assigns and the commit actually ran; item 3b exists as a numbered step, so the
`comments_read_through` rewrite happens where the procedure says instead of by improvisation, and
I confirmed against the tool schema that the id it needs is really returned; the summary rewrite
that three rounds improvised is now instructed and fired; the repo-local DoR row has one fixed
home and cost me zero deliberation for the first time; and the `/loop`-when-the-oracle-is-not-yet-
scriptable coin flip is decided. The plan that came out is build-ready in a way the earlier rounds'
were not — five ACs that include the two negative tenant/authz cases, four phases with grep-derived
`Files:` lists honestly labelled as grep-derived, `parallel_groups: [[3,4]]`, two missing CLI verbs
landing in the earliest phase their own dependency allows with the reason written down, and a
rollback step that says what happens to already-revoked tokens rather than "revert the release".
What holds it off a 5 is that Step 5 still contains a command that cannot run — item 5's
`${CLAUDE_PLUGIN_ROOT}` never expands in a shell, which I measured rather than assumed, and which
all three prior rounds passed as executable while checking only that the script file exists. That
is a fourth consecutive round with a broken Step-5 command, but for the first time it is **not** a
regression the last fix caused: it is a defect nobody had looked at, it fails loudly (`can't open
file`) instead of silently lying, and an operator recovers by substituting one path. The two
genuinely new defects this revision introduced — the parenthetical offering a shape that aborts,
and the exclusive-or between `/loop` and `/goal` — are both one-line contradictions at the last
thing the user reads, and both are inside this file list. Fix item 5's path, condition the
parenthetical, and make `/goal` additive, and the next round is arguing about a 5.
