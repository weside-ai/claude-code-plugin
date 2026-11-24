#!/usr/bin/env bash
# Watch one PR's checks on its head and stay quiet otherwise.
#
# Usage: watch-pr-checks.sh <PR> [--fail-fast] [--sha <expected>] [--until-merged | --human-merge]
#                           [--max-hours <h>] [-R <owner/repo>]
#   --sha <expected>  judge nothing until the PR's head is <expected> (after a push:
#                     `--sha "$(git rev-parse HEAD)"`; GitHub reports the old head for seconds).
#   --until-merged    for an auto-merge PR: on green keep watching until MERGED or CLOSED, the
#                     interval doubling up to WATCH_MAX_INTERVAL while it waits; exit 0 then means
#                     merged (`final … merged`) or green but not merging (conflict, behind):
#                     read the final line, the code alone does not tell them apart. A failed check that is
#                     no review does not end it while the PR can still merge (armed, mergeStateStatus
#                     CLEAN, UNSTABLE or HAS_HOOKS: GitHub merges past a red non-required check).
#                     Green with auto-merge off prints `waiting <sha>: green · merge: <state> · auto-merge
#                     off — <who arms it> — watching to the merge` once per head and keeps polling
#                     (`arm_step`: a one-way class of the head, by the classifier arm_pr.sh asks, says
#                     `one-way <class>: arm only after the human's yes on the board`; a
#                     head it cannot classify adds `(class unknown: …)` to `arm: arm_pr.sh <PR>`) (a
#                     BLOCKED past WATCH_BLOCKED_GRACE still ends it, armed or not), and a
#                     moved head prints `head moved <old> -> <new> — watching it` and is followed: a
#                     watcher that ended there left its master sitting next to a PR that merged later.
#   --human-merge     for a one-way PR waiting for the human's go (not armed yet): --until-merged that
#                     waits past `auto-merge off` and BLOCKED (no go yet) until MERGED or CLOSED;
#                     only a conflict or a stale base (DIRTY, BEHIND) still ends it with exit 0 (as
#                     does the merge: `final … merged`).
#   --max-hours <h>   lifetime cap, default 6.
# Prints a failed or cancelled check once, when it concludes, and one final line:
#   final <sha>: green · merge: <state>                     exit 0
#   final <sha>: red · failed: <names> · merge: <state>     exit 1  (also on the first failure with --fail-fast;
#       a failed check matching WATCH_REVIEW_RX on an armed PR adds ` · auto-merge disarmed`)
#   gh failed <n> times in a row: <error>                   exit 2  (wrong PR, not logged in, offline)
#   head moved <old> -> <new>                               exit 3  (a push landed: watch again, never "green";
#       --until-merged follows the new head instead)
#   no checks on <sha> after <n>s                           exit 4
#   head never reached <expected> (still <sha>) after <n>s  exit 5
#   final <sha>: codex <WARNING|BLOCKING> · auto-merge <disarmed|off> — then /we:ci-review   exit 6
#       (the head's `<!-- codex-review -->` comment judged it and its check is not green: a skip with a reason turns it green)
#   final <sha>: merged[ · merge commit <c>]                exit 0  (a merge is the good end)
#   merged <sha> before its CI ended — watching the head's runs to their end   (a merge while a
#       required check of the head (required_checks.sh on the base) is still open in the rollup, a
#       human merging past the checks: the merge is no verdict, so the watch goes on in every mode and
#       ends with one of the next two lines; a run created after `mergedAt` (a `pull_request: closed`
#       workflow) counts for nothing then; an open non-required check, or a required list it cannot
#       read, leaves the merge the end: `merged` or `merged (red: …)`)
#   final <sha>: merged-green[ · merge commit <c>]          exit 0
#   final <sha>: merged-red[ · merge commit <c>] · failed: <names> — the base branch carries it: fix it first
#                                                            exit 15 (also `· codex <WARNING|BLOCKING>` in place of
#       `failed:`; after such a merge no other exit ends the watch: a red check, a job that never started, a
#       review quota or a Codex verdict all end merged-red)
#   final <sha>: merged (red: <names>)                      exit 7  (with --until-merged, the red
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
#   watcher already running on <repo>#<PR>: <holder> — this one exits      exit 14 (nothing judged:
#       the holder's notification carries the result)
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
# by its newest run only (`startedAt`; a run not started yet is the newest). The checks of a
# cancelled or failed run that a newer, still open run of the same workflow and event replaced
# count for nothing.
# Final means: the head's checks are non-empty, none pending, no workflow run for the head SHA
# queued or in progress (a rerun counts as pending until it completes), and the whole set
# unchanged for WATCH_QUIET seconds and at least two reads. Checks register seconds after a
# push, so a first read with a few skipped checks is not green. `gh pr checks --required` is not
# used: repos without a required-check ruleset answer "no required checks reported".
# The repo is resolved once at start (`-R`, else `gh repo view`, else a github.com `origin`)
# and every gh call carries `-R`; the calls run from the repo's main checkout (gh_anchor.sh), so
# removing the worktree it was started in does not break it and a per-directory gh account holds.
# Run it as a background command started from the main checkout: a shell left in a removed
# worktree fails its own `pwd` after the watcher ended (references/session-traps.md § CI and checks).
# Needs only `gh` (its built-in --jq).
# One watcher per PR: the first takes a lock (`flock` on
# `${WE_STATE_DIR:-~/.claude/we-state}/watch-locks/<owner>-<repo>-<PR>.lock`, holding its pid and
# head); a second on the same PR prints `watcher already running on <repo>#<PR>: <holder> — this one
# exits` and exits 14. A second started with `--sha` for another head than the holder's waits for the
# lock instead, up to the holder's longest gap between two reads (WATCH_MAX_INTERVAL doubled plus an
# hour of quota sleep): the holder ends with exit 3 on its next read. A holder started with
# --until-merged follows new heads and never ends there (its line says `follows new heads`), so the
# second exits 14 at once. Without `flock` there is no lock.
# REST only on red: each tick reads the GraphQL rollup; `gh run list` (REST, the scarcer quota) runs
# only on a red or cancelled check, no check at all or a merged PR, plus once per green state to confirm no run is open.
# Quota: before each read (once per interval) it reads `gh api rate_limit`; when core or graphql
# has fewer than WATCH_QUOTA_FLOOR calls left it prints `quota: <n> left, sleeping until <reset>`
# and sleeps until that reset instead of polling. The interval never drops under 60 s.
# Env: WATCH_INTERVAL (s, default 60, floor 60), WATCH_QUIET (s, default 60), WATCH_REGISTER_TIMEOUT (s,
# default 900), WATCH_HEAD_TIMEOUT (s, default 300), WATCH_MAX_ERRORS (default 10),
# WATCH_MAX_INTERVAL (s, the --until-merged backoff's cap, default 300),
# WATCH_CODEX_CHECK (default `Codex Review`), WATCH_CODEX_READS (comment reads per head after that
# check completed, default 10), WATCH_MAX_LIFETIME (s, overrides --max-hours), WATCH_REVIEW_RX
# (extended regex, case-insensitive, of the check names that count as a review, default `review`),
# WATCH_QUOTA_FLOOR (default 500), WATCH_MIN_INTERVAL (the floor, default 60; tests only),
# WATCH_RULES_NEWS (default 1; 0 skips the board news line a merged rule change gets).
set -uo pipefail

USAGE="usage: watch-pr-checks.sh <PR> [--fail-fast] [--sha <expected>] [--until-merged | --human-merge] [--max-hours <h>] [-R <owner/repo>]"
PR=""
FAIL_FAST=""
EXPECT=""
UNTIL_MERGED=""
HUMAN_MERGE=""
MAX_HOURS=6
REPO=${WATCH_REPO:-}
while [ $# -gt 0 ]; do
  case "$1" in
    --fail-fast) FAIL_FAST=1 ;;
    --until-merged) UNTIL_MERGED=1 ;;
    --human-merge) UNTIL_MERGED=1; HUMAN_MERGE=1 ;;
    --sha) EXPECT=${2:?$USAGE}; shift ;;
    --max-hours) MAX_HOURS=${2:?$USAGE}; shift ;;
    -R|--repo) REPO=${2:?$USAGE}; shift ;;
    -*) echo "$USAGE" >&2; exit 2 ;;
    *) PR=$1 ;;
  esac
  shift
done
[ -n "$PR" ] || { echo "$USAGE" >&2; exit 2; }
MIN_INTERVAL=${WATCH_MIN_INTERVAL:-60}
INTERVAL=${WATCH_INTERVAL:-60}
[ "$INTERVAL" -ge "$MIN_INTERVAL" ] 2>/dev/null || INTERVAL=$MIN_INTERVAL
BASE_INTERVAL=$INTERVAL
QUOTA_FLOOR=${WATCH_QUOTA_FLOOR:-500}
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

# Line 1: the head SHA. Line 2: mergeStateStatus<TAB>mergeable<TAB>state<TAB>auto-merge on|off
# <TAB>isDraft<TAB>the labels joined by a comma<TAB>merge commit<TAB>baseRefName<TAB>mergedAt.
# Then one line per check: <verdict>\t<name>\t<run id or empty>\t<details url>,
# verdict pending | pass | fail | cancelled. Only the newest run of each check (workflow and
# name) on the head counts: a draft run's red ci-summary beside the ready run is history, not red.
# A run not started yet (no startedAt, or gh's zero time 0001-01-01…) counts as the newest.
# A set conclusion is the verdict whatever the status says: GitHub can leave a check run at
# IN_PROGRESS beside its conclusion after the run completed, and judging the status first kept such
# a head pending until the lifetime cap. No conclusion and not COMPLETED is pending.
CLASSIFY='def ckey: [(.workflowName // ""), (.name // .context // "")];
  def at: ((.startedAt // .createdAt // "") | if . == "" or startswith("0001-") then "9999" else . end);
  def newest: . as $all | [$all[] | . as $c | select(all($all[]; ckey != ($c | ckey) or at <= ($c | at)))];
  .headRefOid, ((.mergeStateStatus // "UNKNOWN") + "\t" + (.mergeable // "UNKNOWN")
    + "\t" + (.state // "OPEN") + "\t" + (if .autoMergeRequest then "on" else "off" end)
    + "\t" + ((.isDraft // false) | tostring) + "\t" + ([(.labels // [])[].name] | join(","))
    + "\t" + (.mergeCommit.oid // "") + "\t" + (.baseRefName // "") + "\t" + (.mergedAt // "")),
  (((.statusCheckRollup // []) | newest)[] | (
  (if .__typename == "StatusContext" then
     (if .state == "SUCCESS" then "pass" elif (.state == "PENDING" or .state == "EXPECTED") then "pending" else "fail" end)
   elif (.conclusion == "SUCCESS" or .conclusion == "NEUTRAL" or .conclusion == "SKIPPED") then "pass"
   elif .conclusion == "CANCELLED" then "cancelled"
   elif (.conclusion // "") != "" then "fail"
   elif .status != "COMPLETED" then "pending"
   else "fail" end)
  + "\t" + (.name // .context)
  + "\t" + (((.detailsUrl // .targetUrl // "") | capture("/actions/runs/(?<id>[0-9]+)") | .id) // "")
  + "\t" + (.detailsUrl // .targetUrl // "")))'
# One line per workflow run on the head SHA:
# <id>\t<attempt>\t<status>\t<conclusion>\t<workflow>\t<event>\t<createdAt>.
RUNS='.[] | "\(.databaseId)\t\(.attempt)\t\(.status)\t\(.conclusion // "")\t\(.workflowName // "")\t\(.event // "")\t\(.createdAt // "")"'
# The body of the last Codex review comment (one sticky comment, edited per reviewed head).
CODEX_BODY='[.comments[]? | select(.body | contains("<!-- codex-review -->"))] | last | .body // ""'

ERRORS=0
GH_ERR=$(mktemp) && LOGS=$(mktemp -d) || { echo "no temp dir: mktemp failed" >&2; exit 2; }
trap 'rm -rf "$GH_ERR" "$LOGS"' EXIT
gh_try() {  # gh_try <var> <gh args...>: stores stdout in <var>; exits 2 after MAX_ERRORS failures
  # stdout only: gh prints notices (upgrade, preview commands) on stderr, even on success.
  local var=$1 out; shift
  if out=$(gh "$@" 2>"$GH_ERR"); then ERRORS=0; printf -v "$var" '%s' "$out"; return 0; fi
  ERRORS=$((ERRORS + 1))
  if [ "$ERRORS" -ge "$MAX_ERRORS" ]; then
    echo "gh failed $ERRORS times in a row: $(sed '/^[[:space:]]*$/d' "$GH_ERR" | tail -n 1)"; exit 2
  fi
  return 1
}
RATE='[.resources.core, .resources.graphql] | map(select(. != null)) | min_by(.remaining) | "\(.remaining) \(.reset)"'
quota_wait() {  # one rate_limit read per interval; under QUOTA_FLOOR left, sleep until the reset
  local line left reset now
  line=$(gh api rate_limit --jq "$RATE" 2>/dev/null) || return 0
  read -r left reset <<<"$line"
  [ "${left:-x}" -ge 0 ] 2>/dev/null && [ "${reset:-x}" -ge 0 ] 2>/dev/null || return 0
  [ "$left" -lt "$QUOTA_FLOOR" ] || return 0
  now=$(date +%s)
  [ "$reset" -gt "$now" ] || return 0
  echo "quota: $left left, sleeping until $(date -d "@$reset" +%H:%M:%S 2>/dev/null || date -r "$reset" +%H:%M:%S 2>/dev/null || echo "$reset")"
  sleep $((reset - now + 1)) 9>&-
}
tick() {  # sleep one interval, or exit 9 once the lifetime cap is reached; then the quota read
  if [ $(($(date +%s) - BORN)) -ge "$LIFETIME" ]; then
    echo "gave up after ${LIFETIME}s on ${SHA:-$PR}"; exit 9
  fi
  sleep "$INTERVAL" 9>&-
  quota_wait
}
backoff() {  # --until-merged, waiting for the merge: the interval doubles up to MAX_INTERVAL
  INTERVAL=$((INTERVAL * 2))
  [ "$INTERVAL" -ge 1 ] 2>/dev/null || INTERVAL=1
  [ "$INTERVAL" -le "$MAX_INTERVAL" ] || INTERVAL=$MAX_INTERVAL
  [ "$INTERVAL" -ge "$MIN_INTERVAL" ] || INTERVAL=$MIN_INTERVAL
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

LOCK=""
take_lock() {  # one watcher per PR; a second exits 14 naming the holder (header)
  local dir holder
  command -v flock >/dev/null 2>&1 || return 0
  dir="${WE_STATE_DIR:-$HOME/.claude/we-state}/watch-locks"
  mkdir -p "$dir" 2>/dev/null || return 0
  LOCK="$dir/${REPO//\//-}-${PR//[^A-Za-z0-9]/-}.lock"
  exec 9>>"$LOCK" || { LOCK=""; return 0; }
  if ! flock -n 9; then
    holder=$(head -n 1 "$LOCK" 2>/dev/null)
    case "$holder" in
      *"follows new heads"*) false ;;
      *" head "*) [ -n "$EXPECT" ] && case "${holder##* head }" in "$EXPECT"*) false ;; *) true ;; esac \
        && flock -w $((MAX_INTERVAL > INTERVAL ? MAX_INTERVAL * 2 + 3660 : INTERVAL * 2 + 3660)) 9 ;;
      *) false ;;
    esac || { echo "watcher already running on $REPO#$PR: ${holder:-pid unknown} — this one exits"; exit 14; }
  fi
  echo "pid $$" >"$LOCK"
}
lock_head() {  # the holder line names the head it watches
  [ -n "$LOCK" ] && echo "pid $$ head $1${UNTIL_MERGED:+ (follows new heads)}" >"$LOCK"
}

view() {
  gh_try OUT pr view "$PR" -R "$REPO" \
    --json headRefOid,statusCheckRollup,mergeStateStatus,mergeable,state,autoMergeRequest,isDraft,labels,mergeCommit,baseRefName,mergedAt \
    --jq "$CLASSIFY" && [ -n "$OUT" ]
}
field() { sed -n 2p <<<"$OUT" | cut -f"$1"; }
merge_commit() { local c; c=$(field 7); [ -n "$c" ] && echo " · merge commit ${c:0:12}"; return 0; }
rules_news() {  # a merged PR that changes .claude, .weside or workflows: one board news line (board.py news merged)
  [ "${WATCH_RULES_NEWS:-1}" = 1 ] || return 0
  local ref=$PR
  case "$PR" in *[!0-9]*) ;; *) [ -n "$REPO" ] && ref="$REPO#$PR" ;; esac
  python3 "$(dirname "${BASH_SOURCE[0]}")/board.py" news merged --pr "$ref" >/dev/null 2>&1 || true
}
closed_exit() {  # a merged or closed PR ends the watch with its own line, never "red"
  case "$(field 3)" in
    MERGED) rules_news; echo "final $1: merged$(merge_commit)${WAITING:+ (red: $WAITING)}"; [ -n "$WAITING" ] && exit 7; exit 0 ;;
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
  [ -n "$UNTIL_MERGED" ] && [ -z "$HUMAN_MERGE" ] && [ "$(field 4)" = off ] && note="$note · auto-merge off — $(arm_step)"
  echo "$note"
}
# The crew's merge block (crew.py merge), read once; an unreadable crew reads as the defaults.
CREW_ARMER=$(python3 "$(dirname "${BASH_SOURCE[0]}")/crew.py" merge armer 2>/dev/null) || CREW_ARMER=session
CREW_HOLD=$(python3 "$(dirname "${BASH_SOURCE[0]}")/crew.py" merge hold_labels 2>/dev/null) || CREW_HOLD=""
arm_step() {  # who arms this unarmed PR: a hold label's human, the repo's workflow, or arm_pr.sh
  local label
  while IFS= read -r label; do
    [ -n "$label" ] && [ -n "$CREW_HOLD" ] && grep -qxF -- "$label" <<<"$CREW_HOLD" \
      && { echo "label $label: the human merges"; return; }
  done < <(field 6 | tr ',' '\n')
  if [ "$CREW_ARMER" = workflow ]; then
    if [ "$(field 5)" = true ]; then echo "the repo's workflow arms it once ready: gh pr ready $PR"
    else echo "the repo's workflow arms a ready PR"; fi
    return
  fi
  local class; class=$(one_way_of "$SHA" "$(field 8)")
  case "$class" in
    -) echo "arm: arm_pr.sh $PR" ;;
    "") echo "arm: arm_pr.sh $PR (class unknown: a one-way class arms only after the human's yes on the board)" ;;
    *) echo "one-way $class: arm only after the human's yes on the board" ;;
  esac
}
one_way_of() {  # one_way_of <head> <base>: the head's one-way class, "-" for none, "" when unknown
  # The classifier arm_pr.sh asks (risk_runner.py head, the head commit fetched first when this
  # clone lacks it); a non-zero exit or an unknown line 1 is no class (fail closed).
  local out line
  [ -n "$1" ] && [ -n "$2" ] || return 0
  git cat-file -e "$1^{commit}" 2>/dev/null \
    || GIT_TERMINAL_PROMPT=0 git fetch -q --no-tags origin "$1" 2>/dev/null || true
  out=$(python3 "$(dirname "${BASH_SOURCE[0]}")/risk_runner.py" head "$1" "origin/$2" 2>/dev/null) || return 0
  line=$(head -n 1 <<<"$out")
  case "$line" in
    "T2 one-way "*) echo "${line#T2 one-way }" ;;
    T0 | T2) echo "-" ;;
  esac
}
merge_stuck() {  # green, but GitHub will not merge it by itself
  # BLOCKED while green and armed is normal for seconds before the merge; only after BLOCKED_GRACE
  # of a stable green does it mean a review or rule waits. A human merge waits on the human:
  # only a conflict or a stale base needs the session.
  if [ -n "$HUMAN_MERGE" ]; then
    [ "$(field 1)" = DIRTY ] || [ "$(field 1)" = BEHIND ]
    return
  fi
  [ "$(field 4)" = off ] || [ "$(field 1)" = DIRTY ] || [ "$(field 1)" = BEHIND ] \
    || { [ "$(field 1)" = BLOCKED ] && [ $(($(date +%s) - STABLE_SINCE)) -ge "$BLOCKED_GRACE" ]; }
}
disarm() {  # prints the auto-merge note after disarming an armed PR; never exits
  local out
  if [ "$(field 4)" != on ] || [ -n "$MERGED_EARLY" ]; then echo "auto-merge off"; return; fi
  if out=$(gh pr merge "$PR" -R "$REPO" --disable-auto 2>"$GH_ERR"); then
    echo "auto-merge disarmed"
  else
    echo "auto-merge on (disarm failed: $(sed '/^[[:space:]]*$/d' "$GH_ERR" | tail -n 1)) — run \`gh pr merge $PR --disable-auto\`"
  fi
}
failed_log() {  # failed_log <run id>: the last lines the failed steps printed, empty on any error
  # GitHub's log echoes each step's `run:` script first (`##[group]Run …`, then the script lines in
  # ANSI cyan): that echo is the workflow's text, not what happened, so it is dropped.
  # Read once per run attempt and head (LOGS, a file per run and attempt: callers run it in a
  # subshell); a rerun by anyone is a new attempt in RUNROWS and is read again.
  local out attempt cache
  attempt=$(awk -F'\t' -v r="$1" '$1 == r { print $2 }' <<<"$RUNROWS" | head -n 1)
  cache="${LOGS:?}/${1//[^0-9]/}-${attempt//[^0-9]/}"
  [ -n "$1" ] || return 0
  if [ ! -f "$cache" ]; then
    out=$(gh run view "$1" -R "$REPO" --log-failed 2>/dev/null) || return 0
    grep -v -e '##\[group\]' -e $'\x1b\\[36;1m' <<<"$out" | tail -n 200 >"$cache"
  fi
  cat "$cache"
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
required_open() {  # a required check of the merged head still open in the rollup at the merge
  # GitHub merges an armed PR once its required checks pass, past a non-required run still open:
  # only an open required check means a human merged past the checks. An unreadable or empty
  # required list says nothing, so the merge stays the end.
  local names open verdict name run _url base
  base=$(field 8)
  names=$("$(dirname "${BASH_SOURCE[0]}")/required_checks.sh" --repo "$REPO" ${base:+"$base"}) || return 1
  [ -n "$names" ] || return 1
  open=$(awk -F'\t' '$3 ~ /^(queued|in_progress|requested|pending)$/ { print $1 }' <<<"$RUNROWS")
  while IFS=$'\t' read -r verdict name run _url; do
    [ -n "$name" ] || continue
    grep -qxF -- "$name" <<<"$names" || continue
    [ "$verdict" = pending ] && return 0
    [ -n "$run" ] && grep -qx "$run" <<<"$open" && return 0
  done < <(tail -n +3 <<<"$OUT" | late_out)
  return 1
}
late_out() {  # drops the rollup rows whose run was created after the merge (stdin to stdout)
  awk -F'\t' -v late="$LATE" 'BEGIN { n = split(late, l, "\n"); for (i = 1; i <= n; i++) if (l[i] != "") skip[l[i]] = 1 }
    !($3 in skip)'
}
merged_red() {  # merged_red <what>: the one end of a watch whose PR merged before its CI ended
  rules_news
  echo "final $SHA: merged-red$(merge_commit) · $1 — the base branch carries it: fix it first"; exit 15
}
red_exit() {  # red_exit <failed names>: the red final line; a failed review check disarms first
  local note="" name run reason zero="" why="" all=1
  [ -n "$MERGED_EARLY" ] && merged_red "failed: $1"
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
  rm -f "${LOGS:?}/${run//[^0-9]/}"-*
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
      [ -n "$MERGED_EARLY" ] && merged_red "codex $verdict"
      echo "final $SHA: codex $verdict · $(disarm) — then /we:ci-review"
      exit 6 ;;
    ERROR)
      local why
      why=$(grep -iE "$QUOTA_RX" <<<"$BODY" | head -n 1)
      [ -n "$why" ] && [ -z "$MERGED_EARLY" ] && quota_exit "codex: $(grep -oiE "$QUOTA_RX" <<<"$why" | head -n 1)"
      why=$(grep -vE '^\s*<!--.*-->\s*$' <<<"$BODY" | grep -iE 'error|fail|reason' | head -n 1)
      echo "codex ERROR: ${why:-no reason in the comment} — rerun the Codex check" ;;
  esac
}

take_lock
quota_wait
SHA=""
MERGED_EARLY=""
WAITING=""  # closed_exit reads it; the --sha wait can reach it before watch_head
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
watch_head() {  # (re)start the per-head state: on start and, with --until-merged, on a moved head
  lock_head "$SHA"
  START=$(date +%s)
  SEEN=""
  LAST=""
  STABLE_SINCE=$START
  READS=0
  CODEX_SEEN=""
  CODEX_TRIES=0
  RERUN=""
  rm -f "${LOGS:?}"/* 2>/dev/null
  WAITING=""
  OFF_SAID=""
}
watch_head
runs_read() {  # the head's workflow runs into RUNROWS: REST, so only when the rollup needs them
  gh_try RUNROWS run list -R "$REPO" --commit "$SHA" --limit 100 --json databaseId,attempt,status,conclusion,workflowName,event,createdAt --jq "$RUNS"
}
needs_runs() {  # a red or cancelled check, no check at all, or a merged PR (merge time vs run time)
  local rows
  rows=$(tail -n +3 <<<"$OUT")
  [ -z "$rows" ] || [ "$(field 3)" = MERGED ] || cut -f1 <<<"$rows" | grep -qxE 'fail|cancelled'
}
CONFIRMED=""
while :; do
  RUNROWS=""
  if view && { ! needs_runs || runs_read; }; then
    # A run created after the merge (a `pull_request: closed` workflow) is no CI of this head.
    LATE=""
    if [ "$(field 3)" = MERGED ] && [ -n "$(field 9)" ]; then
      LATE=$(awk -F'\t' -v m="$(field 9)" '$7 != "" && $7 > m { print $1 }' <<<"$RUNROWS")
      RUNROWS=$(awk -F'\t' -v m="$(field 9)" '!($7 != "" && $7 > m)' <<<"$RUNROWS")
    fi
    # Merged while a required check of its head is still open (a human merged past the checks):
    # the merge is no verdict, so the watch goes on to the head's runs' end, merged-green or merged-red.
    if [ "$(field 3)" = MERGED ] && [ -z "$MERGED_EARLY" ] && required_open; then
      MERGED_EARLY=1
      echo "merged $SHA$(merge_commit) before its CI ended — watching the head's runs to their end"
    fi
    [ -n "$MERGED_EARLY" ] || closed_exit "$SHA"
    NOW_SHA=$(head -n 1 <<<"$OUT")
    if [ "$NOW_SHA" != "$SHA" ]; then
      [ -n "$UNTIL_MERGED" ] || { echo "head moved $SHA -> $NOW_SHA"; exit 3; }
      # The caller waits for the merge, not for this head: the new head is judged from scratch.
      echo "head moved $SHA -> $NOW_SHA — watching it"
      SHA=$NOW_SHA; INTERVAL=$BASE_INTERVAL; watch_head; tick; continue
    fi
    if [ -z "$MERGED_EARLY" ] && [ "$(field 2)" = CONFLICTING ]; then
      echo "final $SHA: conflicts with the base — merge it"; exit 12
    fi
    ROWS=$(tail -n +3 <<<"$OUT" | late_out)
    # Runs still queued or in progress (a fresh push, a `gh run rerun` not yet started). A run
    # parked in `waiting`/`action_required` waits for a human and does not hold the watcher.
    OPEN_RUNS=$(awk -F'\t' '$3 ~ /^(queued|in_progress|requested|pending)$/ { print $1 }' <<<"$RUNROWS")
    PENDING=""
    [ -n "$OPEN_RUNS" ] && PENDING=1
    # A cancelled run with a newer run of the same workflow and event on the head was replaced
    # (`gh pr ready` cancels the draft run, a push or edit cancels the older run): its checks are
    # history, never a failure, a progress line or a --fail-fast exit (a failed run too: the draft
    # run's red ci-summary while the ready run is open), but only while the newer
    # run is still open: once it finished, CLASSIFY already shows its result for every check it
    # reported, and a cancelled check it never reported stays the latest for its name, so red.
    SUPERSEDED=$(awk -F'\t' '{ id[NR] = $1; s[NR] = $3; c[NR] = $4; k[NR] = $5 "\t" $6 }
      END { for (i = 1; i <= NR; i++) if (c[i] == "cancelled" || c[i] == "failure") for (j = 1; j <= NR; j++)
        if (k[j] == k[i] && id[j] + 0 > id[i] + 0 && s[j] ~ /^(queued|in_progress|requested|pending)$/) {
          print id[i]; break } }' <<<"$RUNROWS")
    FAILED=""
    FAILED_RUNS=""
    STATE=""
    CODEX_DONE=""
    CODEX_GREEN=""
    LIVE=""
    while IFS=$'\t' read -r verdict name run url; do
      [ -z "$name" ] && continue
      if [ -n "$run" ] && grep -qx "$run" <<<"$SUPERSEDED"; then
        STATE="$STATE"$'\n'"superseded"$'\t'"$name"; continue
      fi
      LIVE=1
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
    if [ -z "$LIVE" ]; then
      if [ -z "$RUNROWS" ] && [ $((NOW - START)) -ge "$NO_RUN_TIMEOUT" ]; then
        echo "no workflow ran on $SHA after ${NO_RUN_TIMEOUT}s"; exit 10
      fi
      if [ $((NOW - START)) -ge "$REGISTER_TIMEOUT" ]; then
        echo "no checks on $SHA after ${REGISTER_TIMEOUT}s"; exit 4
      fi
    fi
    SNAP="$(sort <<<"$STATE")"$'\n--\n'"$(sort <<<"$RUNROWS")"
    if [ "$SNAP" != "$LAST" ]; then LAST=$SNAP; STABLE_SINCE=$NOW; READS=1; else READS=$((READS + 1)); fi
    if [ -n "$LIVE" ] && [ -z "$PENDING" ] && [ "$READS" -ge 2 ] && [ $((NOW - STABLE_SINCE)) -ge "$QUIET" ] \
      && [ -z "$FAILED" ] && [ "$CONFIRMED" != "$LAST" ] && [ -z "$RUNROWS" ]; then
      # A green rollup is confirmed by one run read per state: a run queued before its first check
      # registered is in no rollup yet. An open run keeps it pending and is read again next tick.
      if runs_read; then
        if awk -F'\t' '$3 ~ /^(queued|in_progress|requested|pending)$/ { f = 1 } END { exit !f }' <<<"$RUNROWS"; then
          PENDING=1
        else
          CONFIRMED=$LAST
        fi
      else
        PENDING=1
      fi
    fi
    if [ -n "$LIVE" ] && [ -z "$PENDING" ] && [ "$READS" -ge 2 ] && [ $((NOW - STABLE_SINCE)) -ge "$QUIET" ]; then
      if [ -n "$FAILED" ]; then
        # A red non-required check (an auto-merge workflow) does not stop a PR GitHub still merges.
        if [ -z "$MERGED_EARLY" ] && [ -n "$UNTIL_MERGED" ] && can_merge && ! grep -qiE "$REVIEW_RX" <<<"$(tr ',' '\n' <<<"$FAILED")"; then
          [ "$WAITING" = "$FAILED" ] || echo "still merging: $FAILED red, $(merge_note) — watching to the merge"
          WAITING=$FAILED; backoff; tick; continue
        fi
        red_exit "$FAILED"
      fi
      # Auto-merge off is said once and watched past: the caller arms it (or the human merges) and
      # still gets the `merged` exit; DIRTY, BEHIND and a long BLOCKED need the session, so they end.
      if [ -n "$MERGED_EARLY" ]; then
        rules_news; echo "final $SHA: merged-green$(merge_commit)"; exit 0
      elif [ -n "$UNTIL_MERGED" ] && [ -z "$HUMAN_MERGE" ] && [ "$(field 4)" = off ] \
        && [ "$(field 1)" != DIRTY ] && [ "$(field 1)" != BEHIND ] \
        && ! { [ "$(field 1)" = BLOCKED ] && [ $(($(date +%s) - STABLE_SINCE)) -ge "$BLOCKED_GRACE" ]; }; then
        [ "$OFF_SAID" = "$SHA" ] || echo "waiting $SHA: green · $(merge_note) — watching to the merge"
        OFF_SAID=$SHA
      elif [ -z "$UNTIL_MERGED" ] || merge_stuck; then
        echo "final $SHA: green · $(merge_note)"; exit 0
      fi
      backoff
    fi
  fi
  tick
done
