---
name: plan-commit
description: Where and how a plan or planning doc (story plan, epic plan, an epic's updates-log line, optimization store) is committed — repo fact first, else a detached scratch worktree that lands by push (plans.land push) or by a docs PR with auto-merge.
---

# Plan commit

Every verb that commits a planning document follows this section: `/we:epic`, `/we:master`, `/we:plan-story` (when its brief makes it commit), `/we:merged`,
`/we:retro`, `/we:instruction-audit`, `/we:optimize`.

1. **Repo fact first.** `.weside/orchestrate.md` § *Where plan commits land*, else the instruction
   files, say where docs land (default branch or a PR). That rule wins over the default below.
2. **Never the shared main checkout.** Uncommitted edits there are swept into another session's
   commit. Default: a detached scratch worktree off the default branch, in your scratchpad:

   ```bash
   git fetch origin && git -c core.hooksPath=/dev/null worktree add --detach <scratch> origin/<default>
   ```

   Disabling hooks for the `worktree add` keeps a post-checkout bootstrap from building a venv or a
   database for a tree that carries one file. Commit
   hooks still run on the commit.
3. **Get the file into the scratch tree.** A writer dispatched by the verb writes straight to the
   absolute path inside `<scratch>`. A refiner that carries its plan to Selected commits in its own
   tree, a worktree off the default branch already, and needs no scratch tree. A file written elsewhere (a refiner's `isolation: "worktree"`
   tree) is copied with `cp` into `<scratch>` before the commit. A story plan's staging-check file
   (its `**Staging checks:**` line) travels with it, to the same relative path.
4. **Commit and check.** A story plan first passes
   `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/check-plan-identifiers.py <plan> --ref origin/<default>`: a
   `missing:` name goes back to its writer (struck, or marked `(new)`), never committed as existing; an
   `exists:` name (marked new, already on main) goes back the same way, to build on main's version.
   Plan and staging-check file go into one commit, so neither lands without the other, and the
   subject names the story key (`docs(<KEY>): plan — …`): the repo's staging run finds a story by
   the keys in commit subjects.

   ```bash
   git -C <scratch> add <files>
   git -C <scratch> commit -m "<conventional subject>" && git -C <scratch> log --oneline -1 -- <file>
   ```

   A commit that did not move HEAD: `references/session-traps.md` (Check HEAD after every commit).
5. **Land.** `plans.land` in the committed `.weside/config.json`
   (`git show origin/<default>:.weside/config.json`, the copy `plan_push.py` reads too; an uncommitted
   edit counts for neither) picks the way: `push` or `pr` (default; also every repo without the key).
   A repo fact of step 1 wins over both.
   - **`push`:** run `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/plan_push.py` in `<scratch>`. It rebases
     onto `origin/<default>`, refuses paths outside `plans.push_paths` (default `docs/plans/**`, plus
     a staging-check file still in its planned state travelling with its plan), runs the secret scan
     (`plans.secret_scan`, default gitleaks) and pushes, retrying a lost race up to three times.
     It refuses a merge commit in the range. Where `origin/<default>` carries
     `.github/workflows/docs-push.yml`, it lands through that workflow instead (branch
     `docs-push/<sha>`, dispatch, wait up to 10 min; its docstring maps each failed step to an exit).
     `plans.push_paths` may take dated records (ADRs, logbooks, handoffs, incidents, a date in the name;
     the human's decision); living docs take the PR way, which the drift check reads, and so does a mixed batch, unsplit.
     - Exit 0: the document is on the default branch. A step that needs it there (Ready gate,
       `board.py select`, a dispatch reading the plan) runs at once, after `git fetch origin`, on
       `origin/<default>`; no PR, no wait.
     - Exit 1, refused; nothing was pushed. Paths outside the globs: land these commits the PR
       way below. Main worktree, dirty tree, nothing to land: back to steps 2–4.
     - Exit 4, refused by the secret scan; nothing was pushed, and these commits land by no route,
       the PR way included (a PR pushes the finding to the forge). A finding names file and line:
       take the value out and commit again. No scanner, or the scan did not run: report it to the
       owner (in a crew: machinery) and stop. `plans.secret_scan: "none"` is the owner's setting,
       never written by the session that pushes.
     - Exit 3, "this repo takes no direct push" (the server named a rule): the PR way below, same commits.
     - Exit 2, never the PR way: a git error, a failed run or a `[remote rejected]` naming no rule; report its `server: !…` line. A run past the wait cap may still land: wait for its URL.
   - **`pr`** (and exit 3, or a path refusal): a default branch under a ruleset takes no push from
     an account without a bypass, so docs reach it through a PR that merges itself:
     - a repo fact that names a docs-PR verb wins (one command that rebases, refuses non-docs and
       arms auto-merge, often onto one rolling PR per session and UTC day); run it in `<scratch>`
       and follow its refusals, the fallback below is only for repos without one;
     - else pick the branch `<b>`: `docs/<KEY>-<slug>`, or `docs/<verb>-<UTC date>` for a verb with
       no story key (`/we:retro`, `/we:optimize`, `/we:instruction-audit`; the PR body names the
       verb). `<b>` exists without an open PR (`gh pr list --head <b> --state open`): suffix it with
       the UTC date, still taken, with `-<n>`.
       - A document that waits on a decision goes up as a draft PR (`gh pr create --draft`), armed once decided.
       - **Open PR on `<b>`:** add your commits to it, no new PR. A second change to a file already on
         the open PR starts from `origin/<b>`, not from the default branch:
         `git -C <scratch> fetch origin <b> && git -C <scratch> rebase --onto origin/<b> HEAD~<n>`
         (`<n>` = your commits), then `git -C <scratch> push origin HEAD:refs/heads/<b>`.
       - **New branch:** `git -C <scratch> fetch origin && git -C <scratch> rebase origin/<default>`,
         `git -C <scratch> push origin HEAD:refs/heads/<b>`, `gh pr create --base <default> --head
         <b>` with the key and the files in the body, and `${CLAUDE_PLUGIN_ROOT}/scripts/arm_pr.sh
         <number> --method <the repo's merge method>`; act on its final line as `/we:master` § Close
         the run says. Under the crew's `merge.armer: workflow` the repo's workflow arms the ready PR
         and `refused: armed by workflow` is that step done, not a failure. A worker arms nothing: it reports the PR URL to its starter, who arms.

   A push straight to the default branch only by `plan_push.py` under `plans.land: push`, or where
   the instruction files grant it for docs. Any other rejected push (non-fast-forward included) is
   reported with its message, never forced. On the PR way the document is on the default branch
   once the PR merged; a step that needs it there (a dispatch reading the plan, Selected for
   Development) waits with a background
   `watch-pr-checks.sh <number> --until-merged` until its final line reads `merged`. If `arm_pr.sh`'s
   verdict line is neither `armed`, `ready` nor `refused: armed by workflow` (auto-merge off in the repo, red, no checks), a required review blocks, or the PR is not merged within
   60 min: report the PR URL to the owner (in a crew: the coordinator) and leave the
   story unselected; never merge by hand (the `ready` line's merge is the arm's, not a hand merge), never force. The PR URL goes into your report before
   step 6, it outlives the scratch tree.
6. **Clean up** in a command of its own, only after the push (or `plan_push.py`) exited 0 (and, on the PR path, the PR is open and its URL is in your report): `git worktree remove <scratch>`
   (never `--force`, never chained to the commit or push: a rejected push then deletes the only
   copy). Remove a refiner's worktree with the repo's own worktree verb when it has one.
