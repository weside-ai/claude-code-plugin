#!/usr/bin/env bash
# Wake a PR's owner when the default branch moved under it: one background loop per owner, armed
# next to watch-pr-checks.sh and kept until its PRs are merged or closed.
#
# Usage: watch-pr-conflicts.sh [-R <owner/repo>] <PR> [<PR>…]
# Polls `mergeStateStatus`/`mergeable` per PR and exits on the first PR that is DIRTY, CONFLICTING
# or BEHIND (already so at start counts; UNKNOWN is GitHub still computing and waits). One line:
#   <PR> <state> — merge origin/<base>, run the after-merge check, push   exit 1
#   gh failed <n> times in a row: <error>                                 exit 2
#   all merged or closed: <PR>…                                           exit 7
#   gave up after <n>s                                                    exit 9  (WATCH_MAX_LIFETIME)
# A merged or closed PR leaves the set silently. Re-arm after the owner pushed the merge.
# The repo is resolved once and the loop runs from `/` (a removed worktree does not break it).
# Env: WATCH_INTERVAL (s, default 180), WATCH_MAX_ERRORS (default 10), WATCH_MAX_LIFETIME (s,
# default 21600 = 6 h).
set -uo pipefail

USAGE="usage: watch-pr-conflicts.sh [-R <owner/repo>] <PR> [<PR>…]"
REPO=${WATCH_REPO:-}
PRS=()
while [ $# -gt 0 ]; do
  case "$1" in
    -R|--repo) REPO=${2:?$USAGE}; shift ;;
    -*) echo "$USAGE" >&2; exit 2 ;;
    *) PRS+=("$1") ;;
  esac
  shift
done
[ ${#PRS[@]} -gt 0 ] || { echo "$USAGE" >&2; exit 2; }
INTERVAL=${WATCH_INTERVAL:-180}
MAX_ERRORS=${WATCH_MAX_ERRORS:-10}
LIFETIME=${WATCH_MAX_LIFETIME:-21600}
BORN=$(date +%s)

ERRORS=0
gh_try() {  # gh_try <var> <gh args...>: stores stdout in <var>; exits 2 after MAX_ERRORS failures
  local var=$1 out; shift
  if out=$(gh "$@" 2>&1); then ERRORS=0; printf -v "$var" '%s' "$out"; return 0; fi
  ERRORS=$((ERRORS + 1))
  if [ "$ERRORS" -ge "$MAX_ERRORS" ]; then
    echo "gh failed $ERRORS times in a row: $(tail -n 1 <<<"$out")"; exit 2
  fi
  return 1
}
tick() {
  if [ $(($(date +%s) - BORN)) -ge "$LIFETIME" ]; then echo "gave up after ${LIFETIME}s"; exit 9; fi
  sleep "$INTERVAL"
}

until [ -n "$REPO" ] || gh_try REPO repo view --json nameWithOwner --jq .nameWithOwner; do tick; done
cd / || exit 2

DONE=()
while :; do
  OPEN=()
  for pr in "${PRS[@]}"; do
    if ! gh_try ROW pr view "$pr" -R "$REPO" --json state,mergeStateStatus,mergeable,baseRefName \
      --jq '"\(.state)\t\(.mergeStateStatus // "UNKNOWN")\t\(.mergeable // "UNKNOWN")\t\(.baseRefName)"'; then
      OPEN+=("$pr"); continue
    fi
    IFS=$'\t' read -r state mss mergeable base <<<"$ROW"
    if [ "$state" != OPEN ]; then DONE+=("$pr"); continue; fi
    OPEN+=("$pr")
    if [ "$mss" = DIRTY ] || [ "$mss" = BEHIND ] || [ "$mergeable" = CONFLICTING ]; then
      echo "$pr $mss/$mergeable — merge origin/$base, run the after-merge check, push"; exit 1
    fi
  done
  if [ ${#OPEN[@]} -eq 0 ]; then echo "all merged or closed: ${DONE[*]}"; exit 7; fi
  PRS=("${OPEN[@]}")
  tick
done
