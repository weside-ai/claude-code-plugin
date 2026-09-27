---
name: plan-commit
description: Where and how a plan or planning doc (story plan, epic, saga, PRD, mirror refresh, handoff, retro log) is committed — repo fact first, else a detached scratch worktree pushed to the default branch.
---

# Plan commit

Every verb that commits a planning document follows this section: `/we:story`, `/we:vision`,
`/we:saga`, `/we:epic` (also a mirror refresh), `/we:orchestrate` (refined plans), `/we:merged`,
`/we:handoff`, `/we:retro`.

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
   tree) is copied with `cp` into `<scratch>` before the commit.
4. **Commit and check.**

   ```bash
   git -C <scratch> add <files>
   git -C <scratch> commit -m "<conventional subject>" && git -C <scratch> log --oneline -1 -- <file>
   ```

   A commit that did not move HEAD was aborted by an auto-fixing hook: `add` again and commit again,
   never `--amend`.
5. **Push** `git -C <scratch> push origin HEAD:<default>`. Set a direct-commit variable (such as
   `ALLOW_COMMIT_TO_MAIN=1`) only where the instruction files grant it for docs. A rejected push is
   reported with its message, never forced. A repo that takes docs only through a PR gets a branch
   and a PR instead; a plugin repo always does.
6. **Clean up** `git worktree remove <scratch>`, and remove a refiner's worktree with the repo's own worktree verb when it has one.
