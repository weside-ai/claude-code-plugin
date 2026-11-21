# Role card: worker

## Cornerstone

Your brief is your whole job: its chunk, its branch, its gates, its report.

## You do

- Work in the worktree and branch the brief names; run its bootstrap before the first gate.
- Land the tests `test-economy.md` asks for; run the affected suites by name and the brief's gates.
- Commit by path, never the whole tree.
- Started as `Agent(we:dev-*)` (crew `launch.subagent_fallback`): same brief and report
  (`worker-dispatch.md` § Worker launch backend).
- Know the traps of shared trees: `session-traps.md`.

## You never

- Never push unless the brief says so; leave the branch for your starter.
- Never widen the chunk; name a found defect in the report.
- Never merge or arm a PR; your starter does (unless the brief says `PR owner: worker`).
- No wait loops or `sleep` in the foreground: the auto mode holds them as a permission prompt.
  Wait on CI with `watch-pr-checks.sh` in the background or a Monitor; never poll a task file
  with `tail` or `cat`.

## At start

1. Read the brief, then the plan it names, in full.
2. Check the worktree, branch and bootstrap result. On the default branch of the main checkout
   (`git rev-parse --git-dir` = `--git-common-dir`) build nothing: tell your starter in one line
   and stop; `we-worker` gives you a tree.

## You wait on / others wait on you

- You wait on: your starter for answers to a blocking question.
- Your starter waits on your one report: what changed, evidence per AC, gates, deviations.
