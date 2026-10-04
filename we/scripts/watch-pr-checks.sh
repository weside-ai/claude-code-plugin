#!/usr/bin/env bash
# Watch one PR's checks on its CURRENT head and stay quiet otherwise.
#
# Usage: watch-pr-checks.sh <PR> [--fail-fast]
# Prints a failed or cancelled check once, when it concludes, and one final line:
#   final <sha>: green                       exit 0
#   final <sha>: red · failed: <names>       exit 1  (also on the first failure with --fail-fast)
#   gh failed <n> times in a row: <error>    exit 2  (wrong PR, not logged in, offline)
#   head moved <old> -> <new>                exit 3  (a push landed: watch again, never "green")
#   no checks on <sha> after <n>s            exit 4
# An empty rollup is pending, never green. Run it as a background command: it has no expiry.
# Needs only `gh` (its built-in --jq). Env: WATCH_INTERVAL (s, default 30),
# WATCH_REGISTER_TIMEOUT (s, default 900), WATCH_MAX_ERRORS (default 10).
set -uo pipefail

PR=${1:?usage: watch-pr-checks.sh <PR> [--fail-fast]}
FAIL_FAST=${2:-}
INTERVAL=${WATCH_INTERVAL:-30}
REGISTER_TIMEOUT=${WATCH_REGISTER_TIMEOUT:-900}
MAX_ERRORS=${WATCH_MAX_ERRORS:-10}

# First line: the head SHA. Then one line per check: <verdict>\t<name>,
# verdict pending | pass | fail | cancelled.
CLASSIFY='.headRefOid, (.statusCheckRollup[]? |
  (if .__typename == "StatusContext" then
     (if .state == "SUCCESS" then "pass" elif (.state == "PENDING" or .state == "EXPECTED") then "pending" else "fail" end)
   elif .status != "COMPLETED" then "pending"
   elif (.conclusion == "SUCCESS" or .conclusion == "NEUTRAL" or .conclusion == "SKIPPED") then "pass"
   elif .conclusion == "CANCELLED" then "cancelled"
   else "fail" end) + "\t" + (.name // .context))'

ERRORS=0
view() {
  local out
  if out=$(gh pr view "$PR" --json headRefOid,statusCheckRollup --jq "$CLASSIFY" 2>&1) && [ -n "$out" ]; then
    ERRORS=0; OUT=$out; return 0
  fi
  ERRORS=$((ERRORS + 1))
  if [ "$ERRORS" -ge "$MAX_ERRORS" ]; then
    echo "gh failed $ERRORS times in a row: $(tail -n 1 <<<"$out")"; exit 2
  fi
  return 1
}

until view; do sleep "$INTERVAL"; done
SHA=$(head -n 1 <<<"$OUT")
START=$(date +%s)
SEEN=""
while :; do
  if view; then
    NOW_SHA=$(head -n 1 <<<"$OUT")
    if [ "$NOW_SHA" != "$SHA" ]; then echo "head moved $SHA -> $NOW_SHA"; exit 3; fi
    ROWS=$(tail -n +2 <<<"$OUT")
    if [ -z "$ROWS" ]; then
      if [ $(( $(date +%s) - START )) -ge "$REGISTER_TIMEOUT" ]; then
        echo "no checks on $SHA after ${REGISTER_TIMEOUT}s"; exit 4
      fi
    else
      FAILED=""
      while IFS=$'\t' read -r verdict name; do
        case "$verdict" in
          fail|cancelled)
            FAILED="${FAILED:+$FAILED, }$name"
            case $'\n'"$SEEN"$'\n' in
              *$'\n'"$name"$'\n'*) ;;
              *) echo "$verdict: $name"; SEEN="$SEEN"$'\n'"$name"
                 if [ "$FAIL_FAST" = "--fail-fast" ]; then echo "final $SHA: red · failed: $name"; exit 1; fi ;;
            esac ;;
        esac
      done <<<"$ROWS"
      if ! grep -q '^pending' <<<"$ROWS"; then
        if [ -z "$FAILED" ]; then echo "final $SHA: green"; exit 0; fi
        echo "final $SHA: red · failed: $FAILED"; exit 1
      fi
    fi
  fi
  sleep "$INTERVAL"
done
