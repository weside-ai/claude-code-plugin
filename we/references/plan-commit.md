---
name: plan-commit
description: Where and how a plan or planning doc (story plan, epic plan, mirror refresh, optimization store) is committed — repo fact first, else a detached scratch worktree that lands by a docs PR with auto-merge.
---

# Plan commit

Every verb that commits a planning document follows this section: `/we:epic` (also a mirror
refresh), `/we:master` (the plans its refiner workers wrote), `/we:merged`,
`/we:retro`, `/we:instruction-audit`, `/we:optimize`.

1. **Repo fact first.** `.weside/orchestrate.md` § *Where plan commits land*, else the instruction
   files, say where docs land (default branch or a PR). That rule wins over the default below.
2. **Never the shared main checkout.** Uncommitted edits there are swept into another session's
   commit. Default: a detached scratch worktree off the default branch, in your scratchpad:

   ```bash
   git fetch origin && git -c core.hooksPath=/dev/null worktree add --detach <scratch> origin/<default>
   ```

   Disabling hooks for the `worktree add` keeps a post-checkout bootstrap from building a venv or a
   database for a tree that carries one file (measured 25.09.2026: four orphan databases). Commit
   hooks still run on the commit.
3. **Get the file into the scratch tree.** A writer dispatched by the verb writes straight to the
   absolute path inside `<scratch>`. A file written elsewhere (a refiner's `isolation: "worktree"`
   tree) is copied with `cp` into `<scratch>` before the commit. A story plan's staging-check file
   (its `**Staging checks:**` line) travels with it, to the same relative path.
4. **Commit and check.** A story plan first passes
   `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/check-plan-identifiers.py <plan> --ref origin/<default>`: a
   `missing:` name goes back to its writer (struck, or marked `(new)`), never committed as existing.
   Plan and staging-check file go into one commit, so neither lands without the other, and the
   subject names the story key (`docs(<KEY>): plan — …`): the repo's staging run finds a story by
   the keys in commit subjects.

   ```bash
   git -C <scratch> add <files>
   git -C <scratch> commit -m "<conventional subject>" && git -C <scratch> log --oneline -1 -- <file>
   ```

   A commit that did not move HEAD was aborted by an auto-fixing hook: `add` again and commit again,
   never `--amend`.
5. **Land by PR.** A default branch under a ruleset takes no push, a bot's included, so docs reach
   it through a PR that merges itself:
   - a repo fact that names a docs-PR verb wins (one command that rebases, refuses non-docs and
     arms auto-merge, often onto one rolling PR per session and UTC day); run it in `<scratch>`
     and follow its refusals, the fallback below is only for repos without one;
   - else pick the branch `<b>`: `docs/<KEY>-<slug>`, or `docs/<verb>-<UTC date>` for a verb with
     no story key (`/we:retro`, `/we:optimize`, `/we:instruction-audit`; the PR body names the
     verb). `<b>` exists without an open PR (`gh pr list --head <b> --state open`): suffix it with
     the UTC date, still taken, with `-<n>`.
     - **Open PR on `<b>`:** add your commits to it, no new PR:
       `git -C <scratch> fetch origin <b> && git -C <scratch> rebase --onto origin/<b> HEAD~<n>`
       (`<n>` = your commits), then `git -C <scratch> push origin HEAD:refs/heads/<b>`.
     - **New branch:** `git -C <scratch> fetch origin && git -C <scratch> rebase origin/<default>`,
       `git -C <scratch> push origin HEAD:refs/heads/<b>`, `gh pr create --base <default> --head
       <b>` with the key and the files in the body, and `gh pr merge <b> --auto` with the repo's
       merge method.

   A push straight to the default branch only where the instruction files grant it for docs. A
   rejected push (non-fast-forward included) is reported with its message, never forced. The
   document is on the default branch once the PR merged. A step that needs it there (a dispatch
   reading the plan, Selected for Development) polls `gh pr view <url> --json state,mergedAt`
   (or `gh pr checks <url> --watch`) until `state` is `MERGED`. If `gh pr merge --auto` is
   refused (auto-merge off in the repo), a required review blocks, or the PR is not merged within
   60 min: report the PR URL to the owner (in a crew: the Lead/Orchestrator line) and leave the
   story unselected; never merge by hand, never force. The PR URL goes into your report before
   step 6, it outlives the scratch tree.
6. **Clean up** in a command of its own, only after the push exited 0 (and, on the PR path, the PR is open and its URL is in your report): `git worktree remove <scratch>`
   (never `--force`, never chained to the commit or push: a rejected push then deleted the only
   copy twice, 29.09. and 01.10.2026). Remove a refiner's worktree with the repo's own worktree verb when it has one.
