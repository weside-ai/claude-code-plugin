#!/usr/bin/env bash
# Watchdog for one dispatched worker: exits on the first event so the Lead reports and re-arms.
#
# Usage: watch-worker.sh <worktree> <name>
# Run it with `run_in_background: true` in a Bash call of its own (never `&`/`disown`: a detached
# watchdog notifies nobody and survives the next one); stop it with TaskStop by its task id.
# One final line:
#   <short sha> <subject>                                   exit 0  (a new commit: one status line)
#   STALL <n> min: <name>                                    exit 1  (no commit, tree unchanged)
#   gone: <name> (<worktree> is no git worktree)             exit 2  (removed or never existed)
#   alive: <name> · no commit in <n> min, tree changing      exit 3  (lifetime cap; re-arm)
#   exited: <name>                                           exit 4  (a process worker's session
#                                                                     ended; the worktree carries the
#                                                                     marker of worker_launch.py)
# Env: WATCH_WORKER_INTERVAL (s, default 60), WATCH_WORKER_STALL (s, default 1500),
# WATCH_WORKER_MAX (s, default 1500: stays under a background command's 30-min default).
set -uo pipefail

WT=${1:?usage: watch-worker.sh <worktree> <name>}
NAME=${2:?usage: watch-worker.sh <worktree> <name>}
INTERVAL=${WATCH_WORKER_INTERVAL:-60}
STALL=${WATCH_WORKER_STALL:-1500}
MAX=${WATCH_WORKER_MAX:-1500}

gone() { echo "gone: $NAME ($WT is no git worktree)"; exit 2; }
# A process worker (marker in the worktree's git dir) that is no longer running: exit 4.
# `alive` exits 1 only when `claude agents --json` answered and lists no such session.
exited() {
  local gd
  gd=$(git -C "$WT" rev-parse --absolute-git-dir 2>/dev/null) || return 1
  [ -f "$gd/we-worker.json" ] || return 1
  python3 "$(dirname "$0")/worker_launch.py" alive --name "$NAME" >/dev/null 2>&1
  [ $? -eq 1 ]
}
head_of() { git -C "$WT" rev-parse HEAD 2>/dev/null; }
tree_of() {  # status plus the tracked diff: an edit to an already-modified file counts too
  { git -C "$WT" status --porcelain && git -C "$WT" diff HEAD; } 2>/dev/null | cksum
}

# `gone` runs here, never inside $(…), where its exit would end only the subshell.
H0=$(head_of) && S0=$(tree_of) || gone
BORN=$(date +%s); T=$BORN
while :; do
  sleep "$INTERVAL"
  H=$(head_of) && S=$(tree_of) || gone
  NOW=$(date +%s)
  if [ "$H" != "$H0" ]; then git -C "$WT" log --oneline -1; exit 0; fi
  if exited; then echo "exited: $NAME"; exit 4; fi
  if [ "$S" != "$S0" ]; then S0=$S; T=$NOW; fi
  if [ $((NOW - T)) -ge "$STALL" ]; then echo "STALL $(((NOW - T) / 60)) min: $NAME"; exit 1; fi
  if [ $((NOW - BORN)) -ge "$MAX" ]; then
    echo "alive: $NAME · no commit in $(((NOW - BORN) / 60)) min, tree changing"; exit 3
  fi
done
