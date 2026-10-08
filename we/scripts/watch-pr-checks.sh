#!/usr/bin/env bash
# Watch one PR's checks on its CURRENT head and stay quiet otherwise.
#
# Usage: watch-pr-checks.sh <PR> [--fail-fast]
# Prints a failed or cancelled check once, when it concludes, and one final line:
#   final <sha>: green · merge: <state>                  exit 0
#   final <sha>: red · failed: <names> · merge: <state>  exit 1  (also on the first failure with --fail-fast)
#   gh failed <n> times in a row: <error>                exit 2  (wrong PR, not logged in, offline)
#   head moved <old> -> <new>                            exit 3  (a push landed: watch again, never "green")
#   no checks on <sha> after <n>s                        exit 4
# <state> is `mergeStateStatus/mergeable` (UNKNOWN right after a push); a conflict with the base
# reads `DIRTY/CONFLICTING — conflicts with the base: merge it`.
# Final means: the head's checks are non-empty, none pending, no workflow run for the head SHA
# queued or in progress (a rerun counts as pending until it completes), and the whole set
# unchanged for WATCH_QUIET seconds and at least two reads. Checks register seconds after a
# push, so a first read with a few skipped checks is not green. `gh pr checks --required` is not
# used: repos without a required-check ruleset answer "no required checks reported".
# Run it as a background command: it has no expiry. Needs only `gh` (its built-in --jq).
# Env: WATCH_INTERVAL (s, default 30), WATCH_QUIET (s, default 60),
# WATCH_REGISTER_TIMEOUT (s, default 900), WATCH_MAX_ERRORS (default 10).
set -uo pipefail

PR=${1:?usage: watch-pr-checks.sh <PR> [--fail-fast]}
FAIL_FAST=${2:-}
INTERVAL=${WATCH_INTERVAL:-30}
QUIET=${WATCH_QUIET:-60}
REGISTER_TIMEOUT=${WATCH_REGISTER_TIMEOUT:-900}
MAX_ERRORS=${WATCH_MAX_ERRORS:-10}

# Line 1: the head SHA. Line 2: mergeStateStatus<TAB>mergeable. Then one line per check:
# <verdict>\t<name>\t<run id or empty>\t<details url>, verdict pending | pass | fail | cancelled.
CLASSIFY='.headRefOid, ((.mergeStateStatus // "UNKNOWN") + "\t" + (.mergeable // "UNKNOWN")),
  (.statusCheckRollup[]? |
  (if .__typename == "StatusContext" then
     (if .state == "SUCCESS" then "pass" elif (.state == "PENDING" or .state == "EXPECTED") then "pending" else "fail" end)
   elif .status != "COMPLETED" then "pending"
   elif (.conclusion == "SUCCESS" or .conclusion == "NEUTRAL" or .conclusion == "SKIPPED") then "pass"
   elif .conclusion == "CANCELLED" then "cancelled"
   else "fail" end)
  + "\t" + (.name // .context)
  + "\t" + (((.detailsUrl // .targetUrl // "") | capture("/actions/runs/(?<id>[0-9]+)") | .id) // "")
  + "\t" + (.detailsUrl // .targetUrl // ""))'
# One line per workflow run on the head SHA: <id>\t<attempt>\t<status>.
RUNS='.[] | "\(.databaseId)\t\(.attempt)\t\(.status)"'

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
view() {
  gh_try OUT pr view "$PR" --json headRefOid,statusCheckRollup,mergeStateStatus,mergeable --jq "$CLASSIFY" \
    && [ -n "$OUT" ]
}
merge_note() {
  local mss mergeable
  IFS=$'\t' read -r mss mergeable <<<"$MERGE"
  if [ "$mss" = DIRTY ] || [ "$mergeable" = CONFLICTING ]; then
    echo "merge: $mss/$mergeable — conflicts with the base: merge it"
  else
    echo "merge: $mss/$mergeable"
  fi
}

until view; do sleep "$INTERVAL"; done
SHA=$(head -n 1 <<<"$OUT")
START=$(date +%s)
SEEN=""
LAST=""
STABLE_SINCE=$START
READS=0
while :; do
  if view && gh_try RUNROWS run list --commit "$SHA" --limit 100 --json databaseId,attempt,status --jq "$RUNS"; then
    NOW_SHA=$(head -n 1 <<<"$OUT")
    if [ "$NOW_SHA" != "$SHA" ]; then echo "head moved $SHA -> $NOW_SHA"; exit 3; fi
    MERGE=$(sed -n 2p <<<"$OUT")
    ROWS=$(tail -n +3 <<<"$OUT")
    # Runs still queued or in progress (a fresh push, a `gh run rerun` not yet started). A run
    # parked in `waiting`/`action_required` waits for a human and does not hold the watcher.
    OPEN_RUNS=$(awk -F'\t' '$3 ~ /^(queued|in_progress|requested|pending)$/ { print $1 }' <<<"$RUNROWS")
    PENDING=""
    [ -n "$OPEN_RUNS" ] && PENDING=1
    FAILED=""
    STATE=""
    while IFS=$'\t' read -r verdict name run url; do
      [ -z "$name" ] && continue
      # A stale failure whose run was re-queued is pending, not failed.
      if [ -n "$run" ] && grep -qx "$run" <<<"$OPEN_RUNS"; then verdict=pending; fi
      STATE="$STATE"$'\n'"$verdict"$'\t'"$name"
      case "$verdict" in
        pending) PENDING=1 ;;
        fail|cancelled)
          FAILED="${FAILED:+$FAILED, }$name"
          case $'\n'"$SEEN"$'\n' in
            *$'\n'"$name $url"$'\n'*) ;;
            *) echo "$verdict: $name"; SEEN="$SEEN"$'\n'"$name $url"
               if [ "$FAIL_FAST" = "--fail-fast" ]; then
                 echo "final $SHA: red · failed: $name · $(merge_note)"; exit 1
               fi ;;
          esac ;;
      esac
    done <<<"$ROWS"
    NOW=$(date +%s)
    if [ -z "$ROWS" ]; then
      if [ $((NOW - START)) -ge "$REGISTER_TIMEOUT" ]; then
        echo "no checks on $SHA after ${REGISTER_TIMEOUT}s"; exit 4
      fi
    fi
    SNAP="$(sort <<<"$STATE")"$'\n--\n'"$(sort <<<"$RUNROWS")"
    if [ "$SNAP" != "$LAST" ]; then LAST=$SNAP; STABLE_SINCE=$NOW; READS=1; else READS=$((READS + 1)); fi
    if [ -n "$ROWS" ] && [ -z "$PENDING" ] && [ "$READS" -ge 2 ] && [ $((NOW - STABLE_SINCE)) -ge "$QUIET" ]; then
      if [ -z "$FAILED" ]; then echo "final $SHA: green · $(merge_note)"; exit 0; fi
      echo "final $SHA: red · failed: $FAILED · $(merge_note)"; exit 1
    fi
  fi
  sleep "$INTERVAL"
done
