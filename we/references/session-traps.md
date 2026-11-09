# Session traps

Measured traps of parallel sessions on one host, each with its fix. Every master and worker
follows them; the worker contract (`worker-dispatch.md` § Dev-only worker contract) and the role
cards point here instead of repeating them.

## Contents

- Git in a shared clone
- Workers and their trees
- CI and checks
- Commands and processes
- Gates and checks you build
- Briefs and PR bodies

## Git in a shared clone

- **No `git stash`.** `refs/stash` lives in the common `.git`: every worktree and session shares one
  stack, and pre-commit tools push onto it too, so `stash@{0}` is often someone else's backup and
  `pop` drops what it applies. Keep scratch state with `git diff > <file>.patch`, `git checkout --
  <file>`, `git apply`. If it must be a stash: `git stash list` first, then `git stash pop
  stash@{N}` by index.
- **Check HEAD after every commit:** `git commit … && git log --oneline -1`. A pre-commit fixer that
  rewrites files aborts the commit silently; then stage again and commit again, never `--amend` (it
  can hit a commit that is not yours). A concurrent `.git/index.lock` looks like the same abort:
  wait for it, never delete it.
- **The main checkout belongs to no session.** Work, commit and push only in your own worktree; an
  uncommitted file left in the main checkout blocks the next fast-forward there.
- **One writer per worktree.** Pre-commit stashes unstaged changes while its hooks run, so a second
  committer in the same tree sees its edit vanish. Each worker gets its own worktree; the Lead merges.
- **Parked code goes to a pushed `wip/<KEY>-<slug>` branch**, never only to a scratch directory: a
  host restart wipes `/tmp`. A brief that resumes parked work names the branch.
- Remove a worktree in a command of its own, after the push exited 0, never chained to it.

## Workers and their trees

- **A worker stopped by a usage limit comes back** when its account refreshes. Stop it first, then
  start a replacement; two live workers on one branch race each other's commits.
- Stop processes by PID, never `pkill -f <pattern>`: the pattern matches the shell running it.

## CI and checks

- **A watcher's exit 0 is not green.** `gh run watch` ends on an expired token, and a chained
  `; echo` exits 0 anyway: act only on `gh run view <id> --json status,conclusion` or on
  `watch-pr-checks.sh`'s verdict line.
- **Cancelled is red, absent is not green.** A required check that never reported blocks like a red
  one.
- **Red in a file your diff does not touch:** reproduce it on `origin/main` first. Red there → one
  fix on main, the other PRs merge main; never patch it per branch.
- **One heavy gate run at a time per host**, under the repo's gate lock or test slot. "Waiting for
  lock" means wait. A run that ended without a verdict (killed, out of memory) is never restarted
  automatically: read why, report it.

## Commands and processes

- **Long commands write to a file, not a pipe.** The harness backgrounds a command that runs longer
  than a few seconds, so a `| tail` or `| grep` loses the output: redirect (`cmd > out.txt 2>&1`) and
  read the file.

## Gates and checks you build

- **Red arm:** before the PR goes up, construct what the new gate must reject and show it red. The
  first arm is the control: the unfixed case must go red, or the probe measures nothing. Assert the
  message, not only the exit code; a mutation asserts that it changed the file. Commit the fix
  before an arm mutates, or the arm's `git checkout -- <file>` reverts the fix too.

## Briefs and PR bodies

- Write a PR body file in one Bash call and run `gh pr create|edit --body-file` in the next: the
  verification gate reads the file before the command runs and would judge stale content.
- A brief passed through the shell goes in a quoted heredoc (`<<'EOF'`), so `$`, backticks and
  quotes reach the worker unchanged.
