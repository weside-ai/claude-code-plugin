---
name: smoketest
description: >
  Manual API smoketest against a running backend. Discovers endpoints via OpenAPI
  or route scanning, authenticates, builds a test plan, executes curl requests,
  checks logs for errors. Use when asked to "smoketest", "test endpoints",
  "manual API test", "integration test local", "test the backend", or "/we:smoketest".
---

# API Smoketest

Run a systematic manual API smoketest against a running backend. Discovers
endpoints dynamically, authenticates, tests each area, and checks server logs.

**This is NOT unit testing.** This is end-to-end HTTP testing against a live
server — the kind of testing that catches issues unit tests miss: broken
wiring, missing migrations, auth misconfiguration, serialization bugs.

---

## When to Use

- After significant refactoring (CRUD, service layer, auth changes)
- After database migrations
- Before tagging a release
- When unit tests pass but you want confidence the server actually works
- When the user says "test it", "smoketest", "does it work?"

---

## Workflow

```
Phase 1: Discovery    — Find running server, endpoints, auth method
Phase 2: Test Plan    — Group endpoints by area, prioritize by risk
Phase 3: Execute      — curl each endpoint, check status + response shape
Phase 4: Log Audit    — Scan server logs for errors/warnings
Phase 5: Report       — Summary table with PASS/FAIL per area
```

---

## Phase 1 — Discovery

### 1.1 Find the Running Server

Check common local ports for a running backend:

```bash
# Try common ports
for port in 8000 3000 5000 8080 4000; do
  curl -s --max-time 2 "http://localhost:$port/health" && echo " -> port $port" && break
  curl -s --max-time 2 "http://localhost:$port/" && echo " -> port $port" && break
done
```

If no server found, tell the user and offer to start it (check for common
start commands in package.json scripts, Makefile, docker-compose, etc.).

Store the base URL for all subsequent requests.

### 1.2 Discover Endpoints

**Priority order** (use the first that works):

1. **OpenAPI/Swagger spec** — `GET /openapi.json`, `GET /docs`, `GET /swagger.json`, `GET /api-docs`
2. **Route listing** — framework-specific: FastAPI `/openapi.json`, Express route listing, Rails routes
3. **Codebase scan** — Grep for route definitions (`@router`, `@app.route`, `app.get(`, etc.)
4. **CLAUDE.md / README** — Check project docs for API documentation

Parse discovered endpoints into a structured list:
- HTTP method
- Path (with path parameters noted)
- Whether auth is likely required (heuristic: admin/me/private paths = auth)
- Whether it's a read (GET) or write (POST/PUT/DELETE) operation

### 1.3 Discover Auth Method

Check in this order:

1. **Project docs** — CLAUDE.md, README for auth instructions
2. **Dev token/login** — Look for dev auth scripts, CLI login commands, test user setup
3. **Environment files** — `.env`, `.env.local` for test credentials
4. **OpenAPI security schemes** — Bearer, API key, Cookie, OAuth2

**Try to get a valid auth token.** If the project has a dev-mode login or
test user, use it. If not, ask the user how to authenticate.

**IMPORTANT:** Never use production credentials. Only use test/dev accounts.

### 1.4 Find Log Files

Look for server logs:
- Common paths: `logs/`, `*.log`, stdout of running process
- Docker: `docker logs <container>`
- Framework defaults: uvicorn, express, rails log locations

Truncate or mark the log position BEFORE testing so you only analyze
logs generated during the smoketest.

---

## Phase 2 — Test Plan

Group discovered endpoints into **test areas** by resource/domain:

```
Example grouping:
  - Health & Status (health checks, version info)
  - Auth (login, me, token refresh)
  - Core CRUD (main business entities — list, get, create, update, delete)
  - Search & Filtering (search endpoints, query parameters)
  - User Profile (profile read/update, settings, preferences)
  - Public Endpoints (no auth required)
  - Admin Endpoints (elevated permissions)
  - File Upload / Media (multipart, binary)
  - Webhooks / Callbacks (external integrations)
```

### Prioritization

Test in this order:
1. **Health** — Is the server even alive?
2. **Auth** — Can we authenticate? Everything else depends on this.
3. **Read endpoints (GET)** — Safe, no side effects, catch most wiring issues
4. **Write endpoints (POST/PUT)** — Test with minimal safe payloads
5. **Delete endpoints** — Only if safe (test data, or create-then-delete)
6. **Edge cases** — Invalid input, missing auth, wrong content-type

### What to Test Per Endpoint

| Check | How |
|-------|-----|
| HTTP status | 200/201/204 for success, expected 4xx for errors |
| Response shape | JSON parseable, expected top-level keys present |
| Auth enforcement | Unauthenticated request returns 401/403 |
| Content-Type | Response has correct Content-Type header |
| No 500s | Server never returns 500 (check response AND logs) |

### Write Test Safety

For POST/PUT/DELETE endpoints:

- **Prefer read-only testing** when possible (GET endpoints)
- For write endpoints: use obviously-test data, then clean up
- **NEVER** delete real user data without asking
- **NEVER** trigger external side effects (emails, payments, webhooks to prod)
- If unsure whether a write is safe, **ask the user first**

---

## Phase 3 — Execute

### Execution Pattern

For each test area:

```bash
# 1. Set up auth header
AUTH="-H 'Authorization: Bearer $TOKEN'"

# 2. Execute request
RESP=$(curl -s -w "\nHTTP_STATUS:%{http_code}" $AUTH "$BASE/path")
STATUS=$(echo "$RESP" | grep "HTTP_STATUS:" | cut -d: -f2)
BODY=$(echo "$RESP" | grep -v "HTTP_STATUS:")

# 3. Validate
# - Status code in expected range
# - Body is valid JSON (for JSON APIs)
# - Expected fields present
# - No error messages in success responses
```

### Parallel Execution

Run independent test areas in parallel where possible (e.g., health check
and public endpoints don't depend on auth). Use sequential execution for
areas that depend on previous results (auth before protected endpoints).

### Handling Failures

- **Connection refused** — Server not running, wrong port
- **401/403** — Auth token invalid or expired, try refreshing
- **404** — Endpoint doesn't exist (maybe wrong path/version)
- **422** — Validation error (check request body schema)
- **500** — Server error — **always check logs for the stack trace**
- **307** — Redirect (try with/without trailing slash)

### Trailing Slash Handling

Many frameworks redirect between `/path` and `/path/`. If you get a 307:
- Try the other variant (with/without trailing slash)
- Note it in results but don't count as failure
- Use `-L` (follow redirects) for subsequent requests to that path

---

## Phase 4 — Log Audit

After all tests complete, scan server logs for the test period:

```bash
# Look for errors
grep -iE "error|exception|traceback|500|critical" $LOG_FILE | grep -v "expected_error_pattern"

# Count by severity
grep -c '"level":"error"' $LOG_FILE    # or equivalent log format
grep -c '"level":"warning"' $LOG_FILE

# Look for unexpected SQL errors
grep -iE "sqlalchemy|database|constraint|violation" $LOG_FILE
```

### Classify Log Findings

| Category | Severity | Example |
|----------|----------|---------|
| Unhandled exception / 500 | FAIL | Stack trace in logs |
| SQL error / constraint violation | FAIL | Broken migration, bad query |
| Auth error on protected endpoint | INFO | Expected when testing without auth |
| Deprecation warning | INFO | Note but don't fail |
| Connection pool warning | WARN | May indicate load issues |
| Third-party API errors | WARN | External dependency, not our bug |

---

## Phase 5 — Report

Present a summary table:

```
## Smoketest Results

| Area | Endpoints | Pass | Fail | Skip | Notes |
|------|-----------|------|------|------|-------|
| Health | 2 | 2 | 0 | 0 | |
| Auth | 3 | 3 | 0 | 0 | |
| Users | 5 | 4 | 1 | 0 | PUT /users/me returns 422 |
| ... | | | | | |

**Server Logs:** X errors, Y warnings during test period
**Overall:** PASS / FAIL (with details)
```

### Result Classification

- **PASS** — All tested endpoints return expected status, no unexpected 500s in logs
- **WARN** — Minor issues (deprecation warnings, trailing slash redirects, empty responses on fresh DB)
- **FAIL** — Any 500 error, unexpected auth failures, broken serialization, SQL errors in logs

### What to Include in Report

- Total endpoints discovered vs tested
- Per-area breakdown
- Any endpoints skipped (and why: requires special setup, dangerous write, etc.)
- Log error summary
- Specific failure details with request/response snippets
- Suggestions for next steps (fix bugs, test on staging, etc.)

---

## Rules

- **Read-only first.** Test all GET endpoints before attempting any writes.
- **No production credentials.** Only dev/test accounts.
- **No destructive writes without asking.** If you need to DELETE something, ask first.
- **Always check logs.** A 200 response doesn't mean the server is healthy.
- **Report honestly.** Don't hide failures or skip broken areas.
- **Clean up after yourself.** Delete any test data you created.
- **Note environmental issues.** Missing API keys, empty DB, no Redis — these aren't bugs, they're setup issues. Distinguish clearly.

---

## Arguments

The skill accepts optional arguments:

- **No args** — Full smoketest (discover + test all areas)
- **`--read-only`** — Only test GET endpoints (no writes)
- **`--area <name>`** — Test only a specific area (e.g., `--area auth`)
- **`--port <n>`** — Skip port discovery, use this port
- **`--base-url <url>`** — Skip discovery entirely, use this base URL
- **`--skip-logs`** — Skip log audit phase
