---
name: ci-review
description: >
  Collects every CI and PR-review finding, fixes by severity, resolves bot threads, pushes once.
  Triggers: "/we:ci-review", "fix ci", "fix reviews", "ci failed".
---

# /we:ci-review — every finding fixed, one push per round

Longer than 150 lines because the thread query and the gate checks are load-bearing shell that exists nowhere else.

1. The gate is every required check (`gh pr checks $PR --required`, read live) concluded non-red, plus zero unresolved bot threads.
2. A required reviewer's BLOCKING or WARNING is fixed. A skip needs cited evidence posted on the PR.
3. Codex is advisory, with no end date (Foxy 30.09.2026). Only a Codex BLOCKING turns its check red. Read every Codex review and check each finding against the code: fix a real defect, skip the rest with a cited line, and never spend a round on it alone. The report carries `Codex: <n> findings · <x> real · <y> fixed · <z> skipped (<reason>)`; Foxy decides the subscription on these numbers.
4. One round means collect, fix, validate locally, commit once, resolve the threads, and push once. Wait with `Monitor` or a background `gh pr checks --watch`, never a sleep loop.
5. The run stops only in a terminal state (green · cap · blocked) or before a protected action (merge, force-push, rebase). Every other status note goes in the same message as the next tool call.

The built-in `/autofix-pr` covers the same job and is the benchmark this skill is measured against.
It needs a real PR. This skill does not call it.

`--ci-only` collects sources 1 and 4 only, skips the thread steps, and still fixes and pushes.

## Severity

| Severity | Source | Policy |
|---|---|---|
| BLOCKING | a red required check · a required reviewer's BLOCKING · a direct instruction contradiction (§ 1) | fix |
| WARNING | a required reviewer's WARNING (it turns Claude Review red since 2026-09-27) | fix |
| SUGGESTION · NITPICK | any reviewer | fix or skip, with a one-line reason in the report |
| advisory | any finding from a non-required reviewer (Codex, `chatgpt-codex-connector[bot]`) | fix a real defect; skip a rewrite of prose, a rename, a defensive branch for an input the code cannot receive, or a test the PR's red arm already covers |

A skip is legitimate only when one of these holds:

- the finding is factually wrong, and you cite the line that falsifies it;
- the fix would break existing behaviour;
- the finding is a pre-existing pattern moved 1:1 and fixing it belongs to another story.

"The framework handles this", with no citation, is not a skip.

- **Every skipped BLOCKING or WARNING needs the evidence on the PR.** Reply in the thread, or post
  `gh pr comment $PR --body …` for a summary finding. Otherwise the re-review posts the same verdict and
  the gate stays red. In the report, say that the gate needs a human override.
- **A small defect on the seam this PR touches is fixed here**, even when it is pre-existing. A finding that cannot ride along
  (a product decision, a money-path change, a foreign subsystem, a change that buries the diff) goes into
  the report with its reason and a recommendation. It is not filed as a ticket unless the user asks, and you never ask whether to file one.
- **Human threads are surfaced to the user before fixing.** One may make a bot finding moot. They are never resolved by you.

## 1 · Collect

Each Bash call is a fresh shell. Prepend this block to every later block that uses its variables:
an empty `$ALLOW` matches every login, and the resolve step then touches human threads.

```bash
PR=$(gh pr view --json number --jq .number); REPO=$(gh repo view --json nameWithOwner --jq .nameWithOwner)
OWNER=${REPO%%/*}; NAME=${REPO#*/}; BASE=$(gh pr view $PR --json baseRefName --jq .baseRefName)
ALLOW=$(jq -r '(.review.available // ["claude","codex","coderabbit"]) | join("|")' .weside/config.json 2>/dev/null || echo "claude|codex|coderabbit")
THREADS_Q='query($pr:Int!,$owner:String!,$repo:String!){repository(owner:$owner,name:$repo){pullRequest(number:$pr){reviewThreads(first:100){nodes{id isResolved comments(first:1){nodes{databaseId author{login} body path line}}}}}}}'
BOT_OPEN='.data.repository.pullRequest.reviewThreads.nodes[] | select(.isResolved==false) | select(.comments.nodes[0].author.login | endswith("[bot]") or test("'"$ALLOW"'";"i"))'
```

Without an authenticated `gh` or without a PR, the local gates are the only gate. Say that once.

**Merge state first:** `gh pr view $PR --json mergeable,mergeStateStatus,autoMergeRequest`.

- `UNKNOWN` for a few seconds after a push: GitHub is still computing it, and a single read makes a
  conflicted PR look clean. Arm `Monitor` until the value changes, and report a lasting `UNKNOWN` as `UNKNOWN`.
- `DIRTY` / `CONFLICTING`: required checks may never start. Keep collecting, and resolve it in step 3 by merging.
- `BEHIND`: not visible in the checks table, but it blocks where the branch must be up to date. Also resolved by merging in step 3.
- `BLOCKED`: a required check or review is missing. The findings cover it, so do not merge the base for it.

**Sources:** one path for every bot. Severity comes from the finding's text, never from the reviewer's name.

```bash
gh pr checks $PR --required; gh pr checks $PR                                  # 1 CI: gate, then all
gh api graphql -f query="$THREADS_Q" -F pr=$PR -F owner="$OWNER" -F repo="$NAME" \
  --jq '.data.repository.pullRequest.reviewThreads.nodes[]|select(.isResolved==false)'   # 2 open threads, any author
gh api repos/$REPO/pulls/$PR/reviews --jq 'group_by(.user.login)[]|last|select(.user.login|endswith("[bot]"))|"=== \(.user.login)\n\(.body)"'  # 3 review bodies
gh api repos/$REPO/issues/$PR/comments --paginate --jq '[.[]|select(.user.type=="Bot")|select(.body|test("VERDICT:|SEV:|Code Review"))]|group_by(.user.login)[]|last|.body'  # 4 summary comments
```

Claude Review can post as `claude[bot]` or as `github-actions[bot]`. Source 4 filters on the comment's shape so it catches both.
Each comment carries `<!-- SEV:… -->` per finding and a final `<!-- VERDICT:BLOCKING|WARNING|PASS -->`.

**Every non-pass check is a BLOCKING row**, even when no bot commented on it. Read the failure with `gh run view <run-id> --log-failed`
and classify it from the log:

- **Real:** an assertion, lint, type or coverage failure, or a verdict the review never posted. Fix it,
  including a pre-existing failure that blocks this PR.
- **Review runner:** `VERDICT:ERROR`, no verdict, or a checkout HTTP 429. Run `gh run rerun <id> --failed`, change no code,
  and do not count it as a round.
- **Test noise:** an xdist worker crash or timeout, or shared DB state in a test your diff does not touch. In a large monorepo this is a
  big share of red test jobs. Re-run once. A re-run that fails on different tests confirms the noise. The same failure
  twice is either real or infrastructure: report it rather than inventing a fix. A gate that is still red after confirmed noise is
  terminal state 3 (blocked), with both run ids. A red run rarely turns green on the same SHA, so the re-run
  diagnoses the failure and does not fix it.
- **Never started:** check the merge state before waiting.

**Instruction files in the diff.** Only when `git diff --name-only origin/$BASE...HEAD` lists a
`.claude/rules/**` file, a `SKILL.md` or a file beside it, an `agents/*.md`, an `AGENTS.md` or a `CLAUDE.md`:

1. Run `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/check-instruction-budget.py`. A violation on a changed file is a
   SUGGESTION row, source `instruction-gate`.
2. List what loads beside the changed text: the `AGENTS.md` / `CLAUDE.md` chain from the repo root,
   `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/load-rules.py --list <changed files>`, and for a changed
   path-scoped rule the same list for one file its `paths:` match. Compare each changed passage with them.
3. A **direct contradiction** (the changed text and a loaded instruction prescribe opposite actions
   in the same situation, and neither scopes itself as the override) is a BLOCKING row quoting both
   places. Fix it in this PR by aligning the side the PR did not mean to change. Overlap,
   duplication or tone is a SUGGESTION row.

Findings table: `| # | Source | Bot? | Severity | File:Line | Issue | Thread ID | Action |`.

- A summary comment splits into one row per `SEV:` marker, with Thread ID `—`.
- A `—` row cannot be resolved. It clears when the next review posts PASS, or when your evidence comment for a skip is on the PR.

**Reviews before tests.** A review posts within minutes; the slowest test job often takes several times as long.
Fix and push a review finding without waiting for the test job. Check the CI workflow's `concurrency:` once:
with `cancel-in-progress: true` the push cancels the stale run. Wait for the test job only when it is the last thing open.

**Green → stop** only when three things hold: every required check concluded non-red, 0 unresolved bot threads, and no open BLOCKING or WARNING row.

## 2 · Fix and validate

- Collect every fix before the one commit.
- Validate the changed surface only: the repo's static gates, the affected tests by name, and the pre-push hooks.
  Never run a full sweep. CI runs the full suite on main.
- For a finding that touches money, auth or tenant isolation, run `/security-review` as well.

## 3 · Commit, resolve, merge the base, push

1. **Commit once**, with subject `fix: address CI and review findings` and the ticket key in the body.
   Chain `&& git log --oneline -1`, because a pre-commit auto-fixer can abort the commit silently.
   If nothing changed (everything was skipped or re-run), skip the commit.
2. **Reply, then resolve** only the bot threads in your findings table, fixed or skipped. A skip gets its evidence as a reply first:
   `gh api repos/$REPO/pulls/$PR/comments/<databaseId>/replies -f body="Skipped: <evidence>"`.
   A thread that arrived after collection is a new finding, not something to resolve unread (Codex posts about 2 min after Claude).

   ```bash
   HANDLED="<thread ids from the table, space-separated>"
   for id in $HANDLED; do
     gh api graphql -f query='mutation($id:ID!){resolveReviewThread(input:{threadId:$id}){thread{isResolved}}}' -f id="$id"
   done
   LEFT=$(gh api graphql -f query="$THREADS_Q" -F pr=$PR -F owner="$OWNER" -F repo="$NAME" --jq "$BOT_OPEN | .id")
   [ -z "$LEFT" ] || { echo "open bot threads not handled: $LEFT"; exit 1; }   # red → collect again
   ```

   The count covers threads only. Check the Action column for open `—` rows.
3. **Merge `origin/$BASE`**, never rebase, when the PR is `DIRTY`, is `BEHIND`, or adds a migration. A rebase of
   pushed commits needs a force-push, and that is the user's call. After a merge that changed the diff, collect again.
   On a migration branch, `alembic heads` must show exactly one head. If the second head came in from the base,
   the merge-heads migration belongs on the base branch: keep your fixes unpushed, report it, and stop as blocked.
4. **Push once:** `git push`.

## 4 · Wait and repeat

- After the push, run `gh pr checks $PR --required --watch --fail-fast` as a background command. `--fail-fast` wakes you on a red
  review without waiting for the test job. End the turn and act on the notification. Do not poll in the foreground.
- If the watch exits at once with "no checks reported", the new head has no checks registered yet. Arm `Monitor` until
  `gh pr checks $PR --required` lists them, then start the watch.
- Each round runs sections 1 to 3 again in full, including the thread resolve.
- The default is at most three rounds. A budget the user states replaces that default, and you never raise it yourself.
- **A repeat** is the same finding text on the same `file:line` after a fix aimed at it. It means the fix
  does not land where the reviewer looks: stop and report it. A new finding caused by your fix is a new row.
- **A chain**: a second fix in a row that produces a new finding in the same function means the
  contract is wrong. Change it (the verb, the signature, a parser instead of a regex) instead of
  patching again, and say so in the report.

Terminal states. Report exactly one:

1. **Green.** The report is `merge-ready`, the PR link and each required check. Findings on the PR's own diff are
   decided per finish-first and reported; none becomes a question to the product owner. If auto-merge is armed and the merge state is `CLEAN`, the merge fires on its own: say so. Only
   when the user asked for the merge itself ("bis gemerged"), wait on `gh pr view $PR --json state,mergedAt`
   with `Monitor`, then report `MERGED` or green but not yet merged. You never run `gh pr merge` without the user's word; `/we:orchestrate` arming `--auto` after green is that word, standing.
2. **Cap reached, still red.** Report what is open and what you tried.
3. **Blocked.** Infrastructure is red after a re-run, a required BLOCKING was skipped as wrong, or there are two migration heads.
   The PR needs a human.

When the user is away, take the safest branch, record the open question in the report, and stop.

## 5 · Report

- the findings table with the Action column (Fixed · Skipped with evidence · Re-run · Advisory skipped), and the Codex line from rule 3;
- the push SHA, each required check's status, the terminal state, and the run ids you read. A status from before the push is not current;
- the merge state in one line: `CLEAN`, `BEHIND`, `DIRTY` with the conflicting files, `BLOCKED`, or a lasting `UNKNOWN`;
- 0 unresolved bot threads, and every human thread quoted verbatim;
- follow-ups named with a recommendation, never filed without the user asking.
