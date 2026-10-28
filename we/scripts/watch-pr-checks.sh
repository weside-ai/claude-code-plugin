#!/usr/bin/env bash
# Watch one PR's checks on its head and stay quiet otherwise.
#
# Usage: watch-pr-checks.sh <PR> [--fail-fast] [--sha <expected>] [--until-merged]
#                           [--max-hours <h>] [-R <owner/repo>]
#   --sha <expected>  judge nothing until the PR's head is <expected> (after a push:
#                     `--sha "$(git rev-parse HEAD)"`; GitHub reports the old head for seconds).
#   --until-merged    for an auto-merge PR: on green keep watching until MERGED or CLOSED; exit 0
#                     then means green but not merging (conflict, behind, auto-merge off).
#   --max-hours <h>   lifetime cap, default 6.
# Prints a failed or cancelled check once, when it concludes, and one final line:
#   final <sha>: green · merge: <state>                     exit 0
#   final <sha>: red · failed: <names> · merge: <state>     exit 1  (also on the first failure with --fail-fast)
#   gh failed <n> times in a row: <error>                   exit 2  (wrong PR, not logged in, offline)
#   head moved <old> -> <new>                               exit 3  (a push landed: watch again, never "green")
#   no checks on <sha> after <n>s                           exit 4
#   head never reached <expected> (still <sha>) after <n>s  exit 5
#   final <sha>: codex <WARNING|BLOCKING> · auto-merge <on|off> — …   exit 6  (the head's
#       `<!-- codex-review -->` comment judged it: `gh pr merge --disable-auto`, then /we:ci-review)
#   final <sha>: merged                                     exit 7
#   final <sha>: closed                                     exit 8
#   gave up after <n>s on <sha>                             exit 9  (--max-hours reached)
# <state> is `mergeStateStatus/mergeable` (UNKNOWN right after a push); a conflict with the base
# reads `DIRTY/CONFLICTING — conflicts with the base: merge it`, a stale branch `BEHIND/… — behind
# the base: merge it`.
# Final means: the head's checks are non-empty, none pending, no workflow run for the head SHA
# queued or in progress (a rerun counts as pending until it completes), and the whole set
# unchanged for WATCH_QUIET seconds and at least two reads. Checks register seconds after a
# push, so a first read with a few skipped checks is not green. `gh pr checks --required` is not
# used: repos without a required-check ruleset answer "no required checks reported".
# The repo is resolved once at start and every gh call carries `-R`; the script then runs from `/`,
# so removing the worktree it was started in does not break it. Run it as a background command.
# Needs only `gh` (its built-in --jq).
# Env: WATCH_INTERVAL (s, default 30), WATCH_QUIET (s, default 60), WATCH_REGISTER_TIMEOUT (s,
# default 900), WATCH_HEAD_TIMEOUT (s, default 300), WATCH_MAX_ERRORS (default 10),
# WATCH_CODEX_CHECK (default `Codex Review`), WATCH_CODEX_READS (comment reads per head after that
# check completed, default 10), WATCH_MAX_LIFETIME (s, overrides --max-hours).
set -uo pipefail

USAGE="usage: watch-pr-checks.sh <PR> [--fail-fast] [--sha <expected>] [--until-merged] [--max-hours <h>] [-R <owner/repo>]"
PR=""
FAIL_FAST=""
EXPECT=""
UNTIL_MERGED=""
MAX_HOURS=6
REPO=${WATCH_REPO:-}
while [ $# -gt 0 ]; do
  case "$1" in
    --fail-fast) FAIL_FAST=1 ;;
    --until-merged) UNTIL_MERGED=1 ;;
    --sha) EXPECT=${2:?$USAGE}; shift ;;
    --max-hours) MAX_HOURS=${2:?$USAGE}; shift ;;
    -R|--repo) REPO=${2:?$USAGE}; shift ;;
    -*) echo "$USAGE" >&2; exit 2 ;;
    *) PR=$1 ;;
  esac
  shift
done
[ -n "$PR" ] || { echo "$USAGE" >&2; exit 2; }
INTERVAL=${WATCH_INTERVAL:-30}
QUIET=${WATCH_QUIET:-60}
REGISTER_TIMEOUT=${WATCH_REGISTER_TIMEOUT:-900}
HEAD_TIMEOUT=${WATCH_HEAD_TIMEOUT:-300}
MAX_ERRORS=${WATCH_MAX_ERRORS:-10}
CODEX_CHECK=${WATCH_CODEX_CHECK:-Codex Review}
CODEX_READS=${WATCH_CODEX_READS:-10}
LIFETIME=${WATCH_MAX_LIFETIME:-$((MAX_HOURS * 3600))}
BORN=$(date +%s)

# Line 1: the head SHA. Line 2: mergeStateStatus<TAB>mergeable<TAB>state<TAB>auto-merge on|off.
# Then one line per check: <verdict>\t<name>\t<run id or empty>\t<details url>,
# verdict pending | pass | fail | cancelled.
CLASSIFY='.headRefOid, ((.mergeStateStatus // "UNKNOWN") + "\t" + (.mergeable // "UNKNOWN")
    + "\t" + (.state // "OPEN") + "\t" + (if .autoMergeRequest then "on" else "off" end)),
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
# The body of the last Codex review comment (one sticky comment, edited per reviewed head).
CODEX_BODY='[.comments[]? | select(.body | contains("<!-- codex-review -->"))] | last | .body // ""'

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
tick() {  # sleep one interval, or exit 9 once the lifetime cap is reached
  if [ $(($(date +%s) - BORN)) -ge "$LIFETIME" ]; then
    echo "gave up after ${LIFETIME}s on ${SHA:-$PR}"; exit 9
  fi
  sleep "$INTERVAL"
}

until [ -n "$REPO" ] || gh_try REPO repo view --json nameWithOwner --jq .nameWithOwner; do tick; done
cd / || exit 2

view() {
  gh_try OUT pr view "$PR" -R "$REPO" \
    --json headRefOid,statusCheckRollup,mergeStateStatus,mergeable,state,autoMergeRequest \
    --jq "$CLASSIFY" && [ -n "$OUT" ]
}
field() { sed -n 2p <<<"$OUT" | cut -f"$1"; }
closed_exit() {  # a merged or closed PR ends the watch with its own line, never "red"
  case "$(field 3)" in
    MERGED) echo "final $1: merged"; exit 7 ;;
    CLOSED) echo "final $1: closed"; exit 8 ;;
  esac
}
merge_note() {
  local mss mergeable note
  mss=$(field 1); mergeable=$(field 2)
  note="merge: $mss/$mergeable"
  if [ "$mss" = DIRTY ] || [ "$mergeable" = CONFLICTING ]; then
    note="$note — conflicts with the base: merge it"
  elif [ "$mss" = BEHIND ]; then
    note="$note — behind the base: merge it"
  fi
  [ -n "$UNTIL_MERGED" ] && [ "$(field 4)" = off ] && note="$note · auto-merge off"
  echo "$note"
}
merge_stuck() {  # green, but GitHub will not merge it by itself
  [ "$(field 4)" = off ] || [ "$(field 1)" = DIRTY ] || [ "$(field 1)" = BEHIND ] \
    || [ "$(field 2)" = CONFLICTING ]
}
codex_exit() {  # exit 6 when the Codex comment for this head carries WARNING or BLOCKING
  local reviewed verdict
  gh_try BODY pr view "$PR" -R "$REPO" --json comments --jq "$CODEX_BODY" || return 0
  reviewed=$(sed -n 's/.*Reviewed commit `\([0-9a-f]\{7,40\}\)`.*/\1/p' <<<"$BODY" | head -n 1)
  [ -n "$reviewed" ] && [ "${SHA#"$reviewed"}" != "$SHA" ] || return 0
  CODEX_SEEN=$SHA
  verdict=$(grep -o 'VERDICT:[A-Z]*' <<<"$BODY" | head -n 1 | cut -d: -f2)
  case "$verdict" in
    WARNING|BLOCKING)
      echo "final $SHA: codex $verdict · auto-merge $(field 4) — run \`gh pr merge $PR --disable-auto\`, then /we:ci-review"
      exit 6 ;;
  esac
}

SHA=""
until view; do tick; done
SHA=$(head -n 1 <<<"$OUT")
if [ -n "$EXPECT" ]; then
  WAIT_START=$(date +%s)
  while :; do
    case "$SHA" in "$EXPECT"*) break ;; esac
    closed_exit "$SHA"
    if [ $(($(date +%s) - WAIT_START)) -ge "$HEAD_TIMEOUT" ]; then
      echo "head never reached $EXPECT (still $SHA) after ${HEAD_TIMEOUT}s"; exit 5
    fi
    tick
    view && SHA=$(head -n 1 <<<"$OUT")
  done
fi
START=$(date +%s)
SEEN=""
LAST=""
STABLE_SINCE=$START
READS=0
CODEX_SEEN=""
CODEX_TRIES=0
while :; do
  if view && gh_try RUNROWS run list -R "$REPO" --commit "$SHA" --limit 100 --json databaseId,attempt,status --jq "$RUNS"; then
    closed_exit "$SHA"
    NOW_SHA=$(head -n 1 <<<"$OUT")
    if [ "$NOW_SHA" != "$SHA" ]; then echo "head moved $SHA -> $NOW_SHA"; exit 3; fi
    ROWS=$(tail -n +3 <<<"$OUT")
    # Runs still queued or in progress (a fresh push, a `gh run rerun` not yet started). A run
    # parked in `waiting`/`action_required` waits for a human and does not hold the watcher.
    OPEN_RUNS=$(awk -F'\t' '$3 ~ /^(queued|in_progress|requested|pending)$/ { print $1 }' <<<"$RUNROWS")
    PENDING=""
    [ -n "$OPEN_RUNS" ] && PENDING=1
    FAILED=""
    STATE=""
    CODEX_DONE=""
    while IFS=$'\t' read -r verdict name run url; do
      [ -z "$name" ] && continue
      # A stale failure whose run was re-queued is pending, not failed.
      if [ -n "$run" ] && grep -qx "$run" <<<"$OPEN_RUNS"; then verdict=pending; fi
      STATE="$STATE"$'\n'"$verdict"$'\t'"$name"
      [ "$name" = "$CODEX_CHECK" ] && [ "$verdict" != pending ] && CODEX_DONE=1
      case "$verdict" in
        pending) PENDING=1 ;;
        fail|cancelled)
          FAILED="${FAILED:+$FAILED, }$name"
          case $'\n'"$SEEN"$'\n' in
            *$'\n'"$name $url"$'\n'*) ;;
            *) echo "$verdict: $name"; SEEN="$SEEN"$'\n'"$name $url"
               if [ -n "$FAIL_FAST" ]; then
                 echo "final $SHA: red · failed: $name · $(merge_note)"; exit 1
               fi ;;
          esac ;;
      esac
    done <<<"$ROWS"
    # The Codex comment is read only after its check completed, at most CODEX_READS times per head.
    if [ -n "$CODEX_DONE" ] && [ "$CODEX_SEEN" != "$SHA" ] && [ "$CODEX_TRIES" -lt "$CODEX_READS" ]; then
      CODEX_TRIES=$((CODEX_TRIES + 1))
      codex_exit
    fi
    NOW=$(date +%s)
    if [ -z "$ROWS" ]; then
      if [ $((NOW - START)) -ge "$REGISTER_TIMEOUT" ]; then
        echo "no checks on $SHA after ${REGISTER_TIMEOUT}s"; exit 4
      fi
    fi
    SNAP="$(sort <<<"$STATE")"$'\n--\n'"$(sort <<<"$RUNROWS")"
    if [ "$SNAP" != "$LAST" ]; then LAST=$SNAP; STABLE_SINCE=$NOW; READS=1; else READS=$((READS + 1)); fi
    if [ -n "$ROWS" ] && [ -z "$PENDING" ] && [ "$READS" -ge 2 ] && [ $((NOW - STABLE_SINCE)) -ge "$QUIET" ]; then
      if [ -n "$FAILED" ]; then echo "final $SHA: red · failed: $FAILED · $(merge_note)"; exit 1; fi
      if [ -z "$UNTIL_MERGED" ] || merge_stuck; then echo "final $SHA: green · $(merge_note)"; exit 0; fi
    fi
  fi
  tick
done
