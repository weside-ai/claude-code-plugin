#!/usr/bin/env bash
# Watchdog for one dispatched worker: exits on the events nobody else reports (a stall, the tree
# gone, the session ended) and on its lifetime cap; a commit is a line it prints and keeps watching
# (the worker reports its terminal facts itself), so the Lead re-arms per lifetime, not per commit.
#
# Usage: watch-worker.sh [--on-commit] <worktree> <name>
# Run it with `run_in_background: true` in a Bash call of its own (never `&`/`disown`: a detached
# watchdog notifies nobody and survives the next one); stop it with TaskStop by its task id.
# Each new commit prints `<short sha> <subject>` and counts as activity; `--on-commit` ends on it
# instead (exit 0). One final line:
#   <short sha> <subject>                                   exit 0  (--on-commit only: a new commit)
#   STALL <n> min: <name>[ · test slot held by <holder>]    exit 1  (no commit, tree unchanged; the
#                                                                     holder is the note a run wrote
#                                                                     into the held $WESIDE_TESTS_LOCK)
#   gone: <name> (<worktree> is no git worktree)             exit 2  (removed or never existed)
#   alive: <name> · no commit in <n> min, tree changing      exit 3  (lifetime cap; re-arm; with
#                                                                     commits: `<k> commit(s) in <n> min`)
#   exited: <name>[ · <cause> · resume: <command>]          exit 4  (a process worker's session
#                                                                     ended; the worktree carries the
#                                                                     marker of worker_launch.py; an
#                                                                     end on `auth` or `usage-limit`
#                                                                     names it and the resume command
#                                                                     from `we-worker status`)
# Env: WATCH_WORKER_INTERVAL (s, default 60), WATCH_WORKER_STALL (s, default 1500),
# WATCH_WORKER_MAX (s, default 1500: stays under a background command's 30-min default),
# WESIDE_TESTS_LOCK (the host's test slot, default /tmp/weside-tests.lock).
set -uo pipefail

ON_COMMIT=0
if [ "${1:-}" = --on-commit ]; then ON_COMMIT=1; shift; fi
WT=${1:?usage: watch-worker.sh [--on-commit] <worktree> <name>}
NAME=${2:?usage: watch-worker.sh [--on-commit] <worktree> <name>}
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
cause() {  # " · <auth|usage-limit> · resume: <command>" from `we-worker status`, else nothing
  local st
  st=$(bash "$(dirname "$0")/we-worker" status "$NAME" 2>/dev/null) || return 0
  local mark resume
  mark=$(head -n 1 <<<"$st" | grep -oE ' (auth|usage-limit)( |$)' | tr -d ' ' | head -n 1)
  resume=$(sed -n 's/^  resume after [^:]*: //p' <<<"$st" | head -n 1)
  [ -n "$mark" ] && printf ' · %s%s' "$mark" "${resume:+ · resume: $resume}"
  return 0
}
slot() {  # " · test slot held by <note>" while another process holds the test slot's flock
  python3 - "${WESIDE_TESTS_LOCK:-/tmp/weside-tests.lock}" 2>/dev/null <<'PY' || true
import fcntl, os, sys
try:
    fd = os.open(sys.argv[1], os.O_RDONLY)
except OSError:
    sys.exit(0)
try:
    fcntl.flock(fd, fcntl.LOCK_SH | fcntl.LOCK_NB)
except BlockingIOError:
    note = os.pread(fd, 400, 0).decode(errors="replace").strip().splitlines()
    print(f" · test slot held by {note[0] if note else 'unknown'}", end="")
PY
}
head_of() { git -C "$WT" rev-parse HEAD 2>/dev/null; }
tree_of() {  # status plus the tracked diff: an edit to an already-modified file counts too
  { git -C "$WT" status --porcelain && git -C "$WT" diff HEAD; } 2>/dev/null | cksum
}

# `gone` runs here, never inside $(…), where its exit would end only the subshell.
H0=$(head_of) && S0=$(tree_of) || gone
BORN=$(date +%s); T=$BORN; COMMITS=0
while :; do
  sleep "$INTERVAL"
  H=$(head_of) && S=$(tree_of) || gone
  NOW=$(date +%s)
  if [ "$H" != "$H0" ]; then
    if [ "$ON_COMMIT" -eq 1 ]; then git -C "$WT" log --oneline -1; exit 0; fi
    git -C "$WT" log --oneline --reverse "$H0..$H" 2>/dev/null || git -C "$WT" log --oneline -1
    COMMITS=$((COMMITS + $(git -C "$WT" rev-list --count "$H0..$H" 2>/dev/null || echo 1)))
    H0=$H; T=$NOW
  fi
  if exited; then echo "exited: $NAME$(cause)"; exit 4; fi
  if [ "$S" != "$S0" ]; then S0=$S; T=$NOW; fi
  if [ $((NOW - T)) -ge "$STALL" ]; then echo "STALL $(((NOW - T) / 60)) min: $NAME$(slot)"; exit 1; fi
  if [ $((NOW - BORN)) -ge "$MAX" ]; then
    if [ "$COMMITS" -gt 0 ]; then
      echo "alive: $NAME · $COMMITS commit(s) in $(((NOW - BORN) / 60)) min"
    else
      echo "alive: $NAME · no commit in $(((NOW - BORN) / 60)) min, tree changing"
    fi
    exit 3
  fi
done
