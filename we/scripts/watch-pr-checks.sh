#!/usr/bin/env bash
# Watch one PR's checks on its head and stay quiet otherwise.
#
# Usage: watch-pr-checks.sh <PR> [--fail-fast] [--sha <expected>] [--until-merged]
#                           [--max-hours <h>] [-R <owner/repo>]
#   --sha <expected>  judge nothing until the PR's head is <expected> (after a push:
#                     `--sha "$(git rev-parse HEAD)"`; GitHub reports the old head for seconds).
#   --until-merged    for an auto-merge PR: on green keep watching until MERGED or CLOSED, the
#                     interval doubling up to WATCH_MAX_INTERVAL while it waits; exit 0 then means
#                     green but not merging (conflict, behind, auto-merge off). A failed check that is
#                     no review does not end it while the PR can still merge (armed, mergeStateStatus
#                     CLEAN, UNSTABLE or HAS_HOOKS: GitHub merges past a red non-required check).
#   --max-hours <h>   lifetime cap, default 6.
# Prints a failed or cancelled check once, when it concludes, and one final line:
#   final <sha>: green · merge: <state>                     exit 0
#   final <sha>: red · failed: <names> · merge: <state>     exit 1  (also on the first failure with --fail-fast;
#       a failed check matching WATCH_REVIEW_RX on an armed PR adds ` · auto-merge disarmed`)
#   gh failed <n> times in a row: <error>                   exit 2  (wrong PR, not logged in, offline)
#   head moved <old> -> <new>                               exit 3  (a push landed: watch again, never "green")
#   no checks on <sha> after <n>s                           exit 4
#   head never reached <expected> (still <sha>) after <n>s  exit 5
#   final <sha>: codex <WARNING|BLOCKING> · auto-merge <disarmed|off> — then /we:ci-review   exit 6
#       (the head's `<!-- codex-review -->` comment judged it and its check is not green: a skip with a reason turns it green)
#   final <sha>: merged [(red: <names>)]                    exit 7  (with --until-merged, the red
#       non-required checks it watched past stay in the line)
#   final <sha>: closed                                     exit 8
#   gave up after <n>s on <sha>                             exit 9  (--max-hours reached)
#   no workflow ran on <sha> after <n>s                     exit 10 (no run and no check: a path
#       filter skipped every workflow, or Actions is down; WATCH_NO_RUN_TIMEOUT, default 600)
#   final <sha>: review quota · auto-merge stays on — quota: rerun after the next verdict   exit 11
#       (a failed review check whose own error annotation (`##[error]`, `::error::`) names a quota or
#       usage limit, or the Codex comment's VERDICT:ERROR naming one: the review did not judge, so
#       nothing is disarmed; the step's echoed script and the log's other lines never count)
#   final <sha>: conflicts with the base — merge it          exit 12 (mergeable CONFLICTING: no check
#       result can make it mergeable, so the watcher does not wait for them)
#   final <sha>: infra · <names>: job never started (<annotation>) — do not rerun, tell the coordinator
#                                                            exit 13 (every failed check is a job with
#       zero steps: the runner never ran it, billing or runner trouble; a rerun cannot fix that;
#       never when the PR changes a file under .github/workflows/, or its files are unreadable:
#       a broken `runs-on:` or `if:` fails a job before its first step too, so that stays red)
# A failed job whose failed-step log names a GitHub/registry 5xx or a network timeout
# (INFRA_RX) is rerun once (`gh run rerun <id> --failed`, only on its first attempt) with the line
# `infra: <name> failed on "<match>" — rerun once (run <id>)`, and counts as pending again.
# A red final line ends with ` · run predates <sha>` when the head lacks the newest commit of the
# default branch (`gh api …/compare`): the failure may be fixed there; merge the base and rerun.
# A Codex VERDICT:ERROR that is no quota prints `codex ERROR: <reason line>` once and the watch goes on.
# On exit 6, and on exit 1 with a failed review check, an armed PR is disarmed here
# (`gh pr merge --disable-auto`), so it cannot merge before its fix round; a failed disarm says
# `auto-merge on (disarm failed: <error>) — run gh pr merge <PR> --disable-auto`.
# <state> is `mergeStateStatus/mergeable` (UNKNOWN right after a push); `DIRTY/…` reads
# `DIRTY/… — conflicts with the base: merge it`, a stale branch `BEHIND/… — behind the base: merge
# it` (`mergeable` CONFLICTING ends the watch with exit 12 first).
# A check name that ran more than once on the head (a draft run, then the ready run) is judged
# by its newest run only (`startedAt`; a run not started yet is the newest).
# Final means: the head's checks are non-empty, none pending, no workflow run for the head SHA
# queued or in progress (a rerun counts as pending until it completes), and the whole set
# unchanged for WATCH_QUIET seconds and at least two reads. Checks register seconds after a
# push, so a first read with a few skipped checks is not green. `gh pr checks --required` is not
# used: repos without a required-check ruleset answer "no required checks reported".
# The repo is resolved once at start (`-R`, else `gh repo view`, else a github.com `origin`)
# and every gh call carries `-R`; the calls run from the repo's main checkout (gh_anchor.sh), so
# removing the worktree it was started in does not break it and a per-directory gh account holds.
# Run it as a background command.
# Needs only `gh` (its built-in --jq).
# Env: WATCH_INTERVAL (s, default 30), WATCH_QUIET (s, default 60), WATCH_REGISTER_TIMEOUT (s,
# default 900), WATCH_HEAD_TIMEOUT (s, default 300), WATCH_MAX_ERRORS (default 10),
# WATCH_MAX_INTERVAL (s, the --until-merged backoff's cap, default 300),
# WATCH_CODEX_CHECK (default `Codex Review`), WATCH_CODEX_READS (comment reads per head after that
# check completed, default 10), WATCH_MAX_LIFETIME (s, overrides --max-hours), WATCH_REVIEW_RX
# (extended regex, case-insensitive, of the check names that count as a review, default `review`).
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
BLOCKED_GRACE=${WATCH_BLOCKED_GRACE:-900}
CODEX_CHECK=${WATCH_CODEX_CHECK:-Codex Review}
CODEX_READS=${WATCH_CODEX_READS:-10}
REVIEW_RX=${WATCH_REVIEW_RX:-review}
NO_RUN_TIMEOUT=${WATCH_NO_RUN_TIMEOUT:-600}
MAX_INTERVAL=${WATCH_MAX_INTERVAL:-300}
# A failed job is infra, not code, when its failed-step log says so (case-insensitive).
# Anchored on runner and registry phrasing, so a failing assertion on a 500 is no infra.
INFRA_RX=${WATCH_INFRA_RX:-'HTTP/[0-9.]+ 50[0-9]|(returned|received|got|responded with)( status)?( code)? 50[0-9]|HTTP (error )?50[0-9]|50[234] (Bad Gateway|Service Unavailable|Gateway Time-?out)|ETIMEDOUT|ECONNRESET|i/o timeout|TLS handshake timeout|context deadline exceeded|Connection timed out'}
QUOTA_RX=${WATCH_QUOTA_RX:-'quota|usage limit|rate[ -]limit(ed)?|credit balance|limit (reached|exceeded)|hit your .*limit'}
LIFETIME=${WATCH_MAX_LIFETIME:-$((MAX_HOURS * 3600))}
BORN=$(date +%s)

# Line 1: the head SHA. Line 2: mergeStateStatus<TAB>mergeable<TAB>state<TAB>auto-merge on|off.
# Then one line per check: <verdict>\t<name>\t<run id or empty>\t<details url>,
# verdict pending | pass | fail | cancelled. Only the newest run of each check (workflow and
# name) on the head counts: a draft run's red ci-summary beside the ready run is history, not red.
# A run not started yet (no startedAt, or gh's zero time 0001-01-01…) counts as the newest.
CLASSIFY='def ckey: [(.workflowName // ""), (.name // .context // "")];
  def at: ((.startedAt // .createdAt // "") | if . == "" or startswith("0001-") then "9999" else . end);
  def newest: . as $all | [$all[] | . as $c | select(all($all[]; ckey != ($c | ckey) or at <= ($c | at)))];
  .headRefOid, ((.mergeStateStatus // "UNKNOWN") + "\t" + (.mergeable // "UNKNOWN")
    + "\t" + (.state // "OPEN") + "\t" + (if .autoMergeRequest then "on" else "off" end)),
  (((.statusCheckRollup // []) | newest)[] | (
  (if .__typename == "StatusContext" then
     (if .state == "SUCCESS" then "pass" elif (.state == "PENDING" or .state == "EXPECTED") then "pending" else "fail" end)
   elif .status != "COMPLETED" then "pending"
   elif (.conclusion == "SUCCESS" or .conclusion == "NEUTRAL" or .conclusion == "SKIPPED") then "pass"
   elif .conclusion == "CANCELLED" then "cancelled"
   else "fail" end)
  + "\t" + (.name // .context)
  + "\t" + (((.detailsUrl // .targetUrl // "") | capture("/actions/runs/(?<id>[0-9]+)") | .id) // "")
  + "\t" + (.detailsUrl // .targetUrl // "")))'
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
backoff() {  # --until-merged, waiting for the merge: the interval doubles up to MAX_INTERVAL
  INTERVAL=$((INTERVAL * 2))
  [ "$INTERVAL" -ge 1 ] 2>/dev/null || INTERVAL=1
  [ "$INTERVAL" -le "$MAX_INTERVAL" ] || INTERVAL=$MAX_INTERVAL
}
can_merge() {  # armed and GitHub would merge it past a red non-required check
  [ "$(field 4)" = on ] && case "$(field 1)" in CLEAN|UNSTABLE|HAS_HOOKS) true ;; *) false ;; esac
}

. "$(dirname "${BASH_SOURCE[0]}")/gh_anchor.sh"
gh_anchor
until [ -n "$REPO" ] || gh_try REPO repo view --json nameWithOwner --jq .nameWithOwner; do
  [ -n "$ORIGIN_REPO" ] && { REPO=$ORIGIN_REPO; break; }
  git rev-parse --git-dir >/dev/null 2>&1 || { echo "not inside a git repo: pass -R <owner/repo>" >&2; exit 2; }
  tick
done

view() {
  gh_try OUT pr view "$PR" -R "$REPO" \
    --json headRefOid,statusCheckRollup,mergeStateStatus,mergeable,state,autoMergeRequest \
    --jq "$CLASSIFY" && [ -n "$OUT" ]
}
field() { sed -n 2p <<<"$OUT" | cut -f"$1"; }
closed_exit() {  # a merged or closed PR ends the watch with its own line, never "red"
  case "$(field 3)" in
    MERGED) echo "final $1: merged${WAITING:+ (red: $WAITING)}"; exit 7 ;;
    CLOSED) echo "final $1: closed"; exit 8 ;;
  esac
}
merge_note() {
  local mss mergeable note
  mss=$(field 1); mergeable=$(field 2)
  note="merge: $mss/$mergeable"
  if [ "$mss" = DIRTY ]; then
    note="$note — conflicts with the base: merge it"
  elif [ "$mss" = BEHIND ]; then
    note="$note — behind the base: merge it"
  fi
  [ -n "$UNTIL_MERGED" ] && [ "$(field 4)" = off ] && note="$note · auto-merge off"
  echo "$note"
}
merge_stuck() {  # green, but GitHub will not merge it by itself
  # BLOCKED while green and armed is normal for seconds before the merge; only after BLOCKED_GRACE
  # of a stable green does it mean a review or rule waits.
  [ "$(field 4)" = off ] || [ "$(field 1)" = DIRTY ] || [ "$(field 1)" = BEHIND ] \
    || { [ "$(field 1)" = BLOCKED ] && [ $(($(date +%s) - STABLE_SINCE)) -ge "$BLOCKED_GRACE" ]; }
}
disarm() {  # prints the auto-merge note after disarming an armed PR; never exits
  local out
  if [ "$(field 4)" != on ]; then echo "auto-merge off"; return; fi
  if out=$(gh pr merge "$PR" -R "$REPO" --disable-auto 2>&1); then
    echo "auto-merge disarmed"
  else
    echo "auto-merge on (disarm failed: $(tail -n 1 <<<"$out")) — run \`gh pr merge $PR --disable-auto\`"
  fi
}
failed_log() {  # failed_log <run id>: the last lines the failed steps printed, empty on any error
  # GitHub's log echoes each step's `run:` script first (`##[group]Run …`, then the script lines in
  # ANSI cyan): that echo is the workflow's text, not what happened, so it is dropped.
  local out
  [ -n "$1" ] || return 0
  out=$(gh run view "$1" -R "$REPO" --log-failed 2>/dev/null) || return 0
  grep -v -e '##\[group\]' -e $'\x1b\\[36;1m' <<<"$out" | tail -n 200
}
error_lines() {  # error_lines <run id>: only the failure's own annotations (`##[error]`, `::error::`)
  failed_log "$1" | grep -E '##\[error\]|::error::'
}
predates() {  # " · run predates <sha>" when the head lacks the default branch's newest commit
  local default line behind newest
  default=$(gh api "repos/$REPO" --jq .default_branch 2>/dev/null) || return 0
  [ -n "$default" ] || return 0
  line=$(gh api "repos/$REPO/compare/$SHA...$default" --jq '"\(.ahead_by) \(.commits[-1].sha // "")"' 2>/dev/null) || return 0
  read -r behind newest <<<"$line"
  [ -n "$newest" ] && [ "${behind:-0}" -gt 0 ] 2>/dev/null && echo " · run predates ${newest:0:12} ($default is $behind ahead: merge it, then rerun)"
  return 0
}
quota_exit() {  # quota_exit <why>: the review did not judge; auto-merge stays as it is
  echo "final $SHA: review quota ($1) · auto-merge stays $(field 4) — quota: rerun after the next verdict"
  exit 11
}
zero_steps() {  # zero_steps <run id> <job id>: "<job>\t<annotation>" when that failed job ran no step
  local jobs job id
  [ -n "$1" ] && [ -n "$2" ] || return 0
  jobs=$(gh run view "$1" -R "$REPO" --json jobs \
    --jq '.jobs[] | select(.conclusion == "failure" and ((.steps // []) | length) == 0) | "\(.databaseId)\t\(.name)"' 2>/dev/null) || return 0
  while IFS=$'\t' read -r id job; do
    [ "$id" = "$2" ] || continue  # only the job behind this check, never a sibling in its run
    printf '%s\t%s\n' "$job" "$(gh api "repos/$REPO/check-runs/$id/annotations" --jq '.[0].message // "no annotation"' 2>/dev/null | head -n 1)"
  done <<<"$jobs"
}
touches_workflows() {  # the PR changes .github/workflows/, or its file list is unreadable (fail-closed)
  local files
  files=$(gh pr view "$PR" -R "$REPO" --json files --jq '.files[].path' 2>/dev/null) || return 0
  grep -q '^\.github/workflows/' <<<"$files"
}
infra_exit() {  # every failed check is a job that never started: no red, no rerun
  echo "final $SHA: infra · $1: job never started ($2) — do not rerun, tell the coordinator"
  exit 13
}
red_exit() {  # red_exit <failed names>: the red final line; a failed review check disarms first
  local note="" name run reason zero="" why="" all=1
  while IFS=$'\t' read -r name run job; do
    [ -n "$name" ] || continue
    reason=$(zero_steps "$run" "$job" | head -n 1)
    if [ -n "$reason" ]; then zero="${zero:+$zero, }$name"; why=${why:-$(cut -f2 <<<"$reason")}; else all=""; fi
  done <<<"$FAILED_RUNS"
  [ -n "$zero" ] && [ -n "$all" ] && ! touches_workflows && infra_exit "$zero" "$why"
  if grep -qiE "$REVIEW_RX" <<<"$(tr ',' '\n' <<<"$1")"; then
    # A review that failed on its quota judged nothing: no disarm, its own exit.
    while IFS=$'\t' read -r name run _job; do
      grep -qiE "$REVIEW_RX" <<<"$name" || continue
      reason=$(error_lines "$run" | grep -oiE "$QUOTA_RX" | head -n 1)
      [ -n "$reason" ] && quota_exit "$name: $reason"
    done <<<"$FAILED_RUNS"
    [ "$(field 4)" = on ] && note=" · $(disarm)"
  fi
  echo "final $SHA: red · failed: $1 · $(merge_note)$note$(predates)"; exit 1
}
infra_rerun() {  # infra_rerun <name> <run id>: rerun a first-attempt run that failed on infra; 0 if rerun
  local name=$1 run=$2 attempt match
  [ -n "$run" ] || return 1
  case $'\n'"$RERUN"$'\n' in *$'\n'"$run"$'\n'*) return 1 ;; esac
  attempt=$(awk -F'\t' -v r="$run" '$1 == r { print $2 }' <<<"$RUNROWS" | head -n 1)
  [ "${attempt:-1}" = 1 ] || return 1
  match=$(failed_log "$run" | grep -oiE "$INFRA_RX" | head -n 1)
  [ -n "$match" ] || return 1
  gh run rerun "$run" -R "$REPO" --failed >/dev/null 2>&1 || return 1
  RERUN="$RERUN"$'\n'"$run"
  echo "infra: $name failed on \"$match\" — rerun once (run $run)"
  return 0
}
codex_exit() {  # exit 6 when the Codex comment for this head carries WARNING or BLOCKING and the
  # Codex check is not green: a finding skipped with a reason turns the check green, the comment stays
  local reviewed verdict
  gh_try BODY pr view "$PR" -R "$REPO" --json comments --jq "$CODEX_BODY" || return 0
  reviewed=$(sed -n 's/.*Reviewed commit `\([0-9a-f]\{7,40\}\)`.*/\1/p' <<<"$BODY" | head -n 1)
  [ -n "$reviewed" ] && [ "${SHA#"$reviewed"}" != "$SHA" ] || return 0
  CODEX_SEEN=$SHA
  verdict=$(grep -o 'VERDICT:[A-Z]*' <<<"$BODY" | head -n 1 | cut -d: -f2)
  case "$verdict" in
    WARNING|BLOCKING)
      if [ -n "$CODEX_GREEN" ]; then
        echo "codex $verdict on $SHA, its check green: skipped with a reason, the watch goes on"
        return 0
      fi
      echo "final $SHA: codex $verdict · $(disarm) — then /we:ci-review"
      exit 6 ;;
    ERROR)
      local why
      why=$(grep -iE "$QUOTA_RX" <<<"$BODY" | head -n 1)
      [ -n "$why" ] && quota_exit "codex: $(grep -oiE "$QUOTA_RX" <<<"$why" | head -n 1)"
      why=$(grep -vE '^\s*<!--.*-->\s*$' <<<"$BODY" | grep -iE 'error|fail|reason' | head -n 1)
      echo "codex ERROR: ${why:-no reason in the comment} — rerun the Codex check" ;;
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
RERUN=""
WAITING=""
while :; do
  if view && gh_try RUNROWS run list -R "$REPO" --commit "$SHA" --limit 100 --json databaseId,attempt,status --jq "$RUNS"; then
    closed_exit "$SHA"
    NOW_SHA=$(head -n 1 <<<"$OUT")
    if [ "$NOW_SHA" != "$SHA" ]; then echo "head moved $SHA -> $NOW_SHA"; exit 3; fi
    if [ "$(field 2)" = CONFLICTING ]; then
      echo "final $SHA: conflicts with the base — merge it"; exit 12
    fi
    ROWS=$(tail -n +3 <<<"$OUT")
    # Runs still queued or in progress (a fresh push, a `gh run rerun` not yet started). A run
    # parked in `waiting`/`action_required` waits for a human and does not hold the watcher.
    OPEN_RUNS=$(awk -F'\t' '$3 ~ /^(queued|in_progress|requested|pending)$/ { print $1 }' <<<"$RUNROWS")
    PENDING=""
    [ -n "$OPEN_RUNS" ] && PENDING=1
    FAILED=""
    FAILED_RUNS=""
    STATE=""
    CODEX_DONE=""
    CODEX_GREEN=""
    while IFS=$'\t' read -r verdict name run url; do
      [ -z "$name" ] && continue
      # A stale failure whose run was re-queued is pending, not failed.
      if [ -n "$run" ] && grep -qx "$run" <<<"$OPEN_RUNS"; then verdict=pending; fi
      STATE="$STATE"$'\n'"$verdict"$'\t'"$name"
      [ "$name" = "$CODEX_CHECK" ] && [ "$verdict" != pending ] && CODEX_DONE=1
      [ "$name" = "$CODEX_CHECK" ] && [ "$verdict" = pass ] && CODEX_GREEN=1
      case "$verdict" in
        pending) PENDING=1 ;;
        fail|cancelled)
          if [ "$verdict" = fail ] && infra_rerun "$name" "$run"; then PENDING=1; continue; fi
          FAILED="${FAILED:+$FAILED, }$name"
          FAILED_RUNS="${FAILED_RUNS:+$FAILED_RUNS$'\n'}$name"$'\t'"$run"$'\t'"$(sed -n 's#.*/job/\([0-9]*\).*#\1#p' <<<"$url")"
          case $'\n'"$SEEN"$'\n' in
            *$'\n'"$name $url"$'\n'*) ;;
            *) echo "$verdict: $name"; SEEN="$SEEN"$'\n'"$name $url"
               if [ -n "$FAIL_FAST" ]; then
                 red_exit "$name"
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
      if [ -z "$RUNROWS" ] && [ $((NOW - START)) -ge "$NO_RUN_TIMEOUT" ]; then
        echo "no workflow ran on $SHA after ${NO_RUN_TIMEOUT}s"; exit 10
      fi
      if [ $((NOW - START)) -ge "$REGISTER_TIMEOUT" ]; then
        echo "no checks on $SHA after ${REGISTER_TIMEOUT}s"; exit 4
      fi
    fi
    SNAP="$(sort <<<"$STATE")"$'\n--\n'"$(sort <<<"$RUNROWS")"
    if [ "$SNAP" != "$LAST" ]; then LAST=$SNAP; STABLE_SINCE=$NOW; READS=1; else READS=$((READS + 1)); fi
    if [ -n "$ROWS" ] && [ -z "$PENDING" ] && [ "$READS" -ge 2 ] && [ $((NOW - STABLE_SINCE)) -ge "$QUIET" ]; then
      if [ -n "$FAILED" ]; then
        # A red non-required check (an auto-merge workflow) does not stop a PR GitHub still merges.
        if [ -n "$UNTIL_MERGED" ] && can_merge && ! grep -qiE "$REVIEW_RX" <<<"$(tr ',' '\n' <<<"$FAILED")"; then
          [ "$WAITING" = "$FAILED" ] || echo "still merging: $FAILED red, $(merge_note) — watching to the merge"
          WAITING=$FAILED; backoff; tick; continue
        fi
        red_exit "$FAILED"
      fi
      if [ -z "$UNTIL_MERGED" ] || merge_stuck; then echo "final $SHA: green · $(merge_note)"; exit 0; fi
      backoff
    fi
  fi
  tick
done
