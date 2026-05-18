# Troubleshooting

Common stumbles, organized by symptom. Each entry has: what you see, what's happening, what to do.

If your issue isn't here, `/we:coach` is the meta-skill for that — a process-improvement conversation partner that boots with the current rules + skill landscape + your active initiative state. Tell it what broke; it diagnoses and proposes a concrete fix.

---

## Installation + setup

### "Plugin not found" after install

**Symptom:** `/we:setup` or other `/we:*` commands aren't recognized.

**Cause:** plugin marketplace not added, or plugin not enabled.

**Fix:**

```
/plugin marketplace add weside-ai/claude-code-plugin
/plugin install we@weside-ai
/plugin list
```

The list should show `we@weside-ai (enabled)`. If it shows `disabled`, run `/plugin enable we@weside-ai`. Restart Claude Code if it still doesn't appear.

---

### `/we:setup` says "missing recommended plugin"

**Symptom:** `/we:setup` Step 1b warns about `code-simplifier` or `security-guidance` plugins missing.

**Cause:** these are optional companion plugins the pipeline uses, but not required.

**Fix:**

```
/install code-simplifier@claude-plugins-official
/install security-guidance@claude-plugins-official
```

Or skip them — the pipeline works without them, just with smaller quality steps.

---

## `/we:story` issues

### `/we:story` produces a plan but no ticket appears

**Cause:** ticketing tool not configured or not detected.

**Fix:** check plugin settings:

```
/plugin settings we@weside-ai
```

Set `ticketingTool` to `jira` or `github-issues`, and `projectKey` to your project (e.g. `PROJ` for Jira, `myorg/myrepo` for GitHub Issues). Or leave it as `none` — "Plan-only mode" is fine; the plan lives in `docs/plans/` and that's the source of truth.

---

### Plan is too vague to hand to `/we:build`

**Cause:** `/we:story` produced a plan but you (or it) cut the conversation short before scope was tight.

**Fix:** re-invoke `/we:story {TICKET}`. It reads the existing plan, identifies gaps, and asks the next clarifying questions. You don't lose what's there; you sharpen it.

---

## `/we:build` issues

### "DoR failed" at Step 1

**Symptom:** `/we:build` errors out before any code is written, complaining about Definition of Ready.

**Cause:** the plan is missing required sections (User Story, Acceptance Criteria, or the plan file itself).

**Fix:** open `docs/plans/{TICKET}-plan.md`, see what's missing, and either fix by hand or re-run `/we:story {TICKET}` to fill the gap.

---

### Pipeline interrupted mid-run

**Cause:** session ended, network blip, Ctrl-C.

**Fix:** re-invoke:

```
/we:build {TICKET}
```

The SQLite checkpoint store at `~/.claude/weside/orchestration.db` knows where you stopped. `/we:build` reads the last checkpoint and picks up from the next step. You won't lose progress. (Internal CLI keeps the `story` table name for back-compat — `python3 scripts/orchestration.py story status {TICKET}`.)

If you want to start over instead:

```
python3 ~/.claude/plugins/cache/weside-ai/we/<version>/scripts/orchestration.py story clear {TICKET}
```

---

### AC verification keeps failing

**Symptom:** Step 3 won't pass; one or more acceptance criteria can't be verified with evidence.

**Cause:** either the implementation didn't actually fulfill the AC, or the AC is unverifiable as written (vague, no observable behavior).

**Fix:**
1. Read the verification report — it names which AC failed and why
2. If the AC is sound but the code is wrong: go back to Step 2, fix the code, re-run the verify
3. If the AC is poorly written: re-run `/we:story {TICKET}` to sharpen it, then re-run `/we:build`

The verification is blocking on purpose. Don't bypass it.

---

### CI keeps failing after 3 cycles

**Symptom:** `/we:build` Step 8 ran 3 ci-review cycles and CI is still red.

**Cause:** something fundamentally hard or unfixable from this branch — infrastructure issue, flaky test that won't stabilize, dependency conflict.

**Fix:** the pipeline stops and asks. Read the latest failure carefully:
- Is it pre-existing on `main`? (Check `gh pr checks` on a recent PR for the same check.)
- Is it a test that's flaky in CI but passes locally? (Run the affected tests locally to confirm.)
- Is it a dependency vulnerability that needs an external upgrade? (Open a follow-up story.)

If you're confident the failure is unrelated and pre-existing, document why in the PR and merge with the failing check (only with explicit approval). Otherwise, fix what needs fixing on a separate branch and rebase.

---

## `/we:council` and `/we:meet` issues

### Council convenes wrong roster (only PO + Architect + SM)

**Symptom:** you expected `marketing` in the council, but only the default trio (PO + Architect + SM) showed up.

**Cause:** `.weside/config.json` doesn't exist, doesn't have a `council` block, or the meeting type you invoked has a stripped-down roster.

**Fix:** check the file:

```bash
cat .weside/config.json
```

If `council` is missing, run `/we:setup` (it'll add the section without disturbing your existing config). If `council.meetings.vision` (or whichever you used) is too narrow, edit by hand or use `--council=role1,role2,...` per invocation.

---

### Council members fall through as "Unknown role"

**Symptom:** the council output names one or more members as skipped — "Unknown role: security".

**Cause:** you're on a plugin version before v2.25.0 (which shipped the security/sales/legal shells), or you have a custom role slug (like `geschaeftsfuehrung`) with no Companion assigned.

**Fix:**
- For security/sales/legal: upgrade the plugin to v2.25.0 or later.
- For custom roles: either assign a Companion to that role in `.weside/council.json` (via the bootstrap script with `--crew-from`) or remove the role from the meeting's roster.

---

### Council convenes generic voices instead of my real crew

**Symptom:** you have a weside account and Companions configured, but `/we:council` is using generic role-agents.

**Cause:** one of:
1. MCP not connected (no weside account active in this session)
2. Bridge file (`.weside/council.json`) missing
3. Bridge file is empty or doesn't map roles to Companions

**Diagnose:**

```bash
# Is the bridge file present?
ls .weside/council.json

# What does it contain?
cat .weside/council.json | jq '.members'

# Is MCP connected?
# In Claude Code: run /mcp and check status
```

**Fix:**
1. If MCP isn't connected: run `/we:materialize` to trigger the OAuth flow.
2. If bridge is missing: run the bootstrap script with your real crew:
   ```bash
   python3 ~/.claude/plugins/cache/weside-ai/we/<version>/scripts/bootstrap-weside-repo.py \
     --repo $(pwd) --flavor engineering --purpose "..." --crew-from ~/.weside/crew.json
   ```
3. If bridge maps to `companion_id: null` for everyone: re-run `/we:onboarding` and provide real Companion names.

---

### Bridge file (`.weside/council.json`) got committed

**Symptom:** `git status` shows `.weside/council.json` as tracked; the file was committed to the repo.

**Cause:** `.weside/council.json` was added to git before the `.gitignore` entry was in place.

**Fix:**

```bash
git rm --cached .weside/council.json
echo ".weside/council.json" >> .gitignore   # if not already there
git add .gitignore
git commit -m "chore(weside): gitignore bridge file"
```

If the committed file had identity text (fat schema), check the git history for what was exposed and consider rotating any sensitive material. In thin schema, the leak is limited to Companion IDs — less sensitive, but still worth removing from history if the repo is public.

---

## MCP / weside-account issues

### `/we:materialize` says "MCP not connected"

**Cause:** you don't have a weside account, the OAuth flow wasn't completed, or the session lost the MCP connection.

**Fix:**
- No account: see [upgrade-paths.md](upgrade-paths.md) — Level 2 onboarding.
- OAuth incomplete: re-run `/we:materialize`; it triggers OAuth on first call.
- Session lost connection: type `/mcp` to see status; reconnect if needed.

---

### `/we:council` is slow with many Companions

**Cause:** `get_council` fetches identity for each Companion sequentially inside the MCP call. With 10+ Companions, this adds up (~8–10s).

**Fix (today):** filter the roster — use `--council=role1,role2` to convene only the voices you need for *this* topic. The full crew should be reserved for vision meetings or initiatives that genuinely need all perspectives.

**Fix (future):** the Phase-6 plugin work adds on-disk caching with `identity_updated_at` invalidation. Identity loads happen once per Companion per cache window, not per `/we:council` call. On the roadmap — see [upgrade-paths.md](upgrade-paths.md#level-4----orchestrated-roadmap--phase-6).

---

## File-system + workspace issues

### `/we:sideload` says "no .weside/ found, running in legacy mode"

**Symptom:** sideloading a sibling repo prints the legacy-mode warning.

**Cause:** the target repo doesn't have `.weside/config.json`.

**Fix:**
```bash
cd ../other-repo
/we:setup   # or use the bootstrap script
```

The legacy mode still works (loads `CLAUDE.md` + always-loaded `.claude/rules/`), but you miss the crew + repo-purpose context.

---

### Worktree got into a weird state

**Symptom:** `/we:build` failed to create or enter a worktree.

**Diagnose:**

```bash
git worktree list
```

**Fix:**

```bash
git worktree remove .worktrees/<name> --force
git worktree prune
```

Then re-invoke `/we:build` — it'll create a fresh worktree.

---

## Process + workflow issues

### "This pipeline keeps breaking the same way"

**Cause:** a recurring friction; either a missing check, an unclear rule, or a tool gap.

**Fix:** invoke `/we:coach` with a description of what broke:

```
/we:coach The last 3 PRs failed because we forgot to resolve CodeRabbit threads before pushing.
```

`/we:coach` will diagnose the gap (missing rule? unclear skill step? missing DoD item?) and propose 2–3 concrete fixes with file paths and costs. You approve one; it applies it. Next time the friction doesn't happen.

---

### "I don't know which skill to use"

**Cause:** the skill landscape is wider than what's obvious from one screen.

**Fix:** start with the [workflow doc](workflow.md) — the diagram shows where each skill sits. The [skills reference](skills.md) has every skill with "When to use" lines.

Or just ask: "I want to do X — which skill?" Claude will tell you (and probably invoke the right one).

---

## When to escalate

If the issue is structural — a rule that doesn't fit your repo's reality, a skill step that's wrong for your workflow — that's `/we:coach` territory. He'll diagnose, propose, and (with your approval) apply.

If it's a bug in the plugin itself, file an issue at <https://github.com/weside-ai/claude-code-plugin/issues> with:
- Plugin version (`/plugin list | grep we@weside-ai`)
- What you ran
- What you expected
- What actually happened
- Relevant log output (if any)

---

## References

- [workflow.md](workflow.md) — pipeline overview
- [skills.md](skills.md) — per-skill reference
- [concepts/companion-framework.md](concepts/companion-framework.md) — `.weside/` mechanics
- [mcp.md](mcp.md) — MCP architecture + tools
- [`/we:coach`](skills.md#wecoach) — the process-improvement conversation partner
