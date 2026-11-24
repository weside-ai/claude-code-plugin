#!/usr/bin/env bash
# shellcheck disable=SC2016  # GraphQL and jq variables stay literal
# Arm one PR's auto-merge on the head it read. It never merges, in any branch of its code.
#
# Usage: arm_pr.sh <PR> [--method merge|squash|rebase] [--repo <owner/repo>] [--check [--sha <sha>]]
#
# Arms only through the GraphQL mutation `enablePullRequestAutoMerge`, with the head SHA it read as
# `expectedHeadOid`: GitHub then merges that head once the repo's required checks pass, and a push
# after the read makes the mutation fail instead of arming a head nobody looked at. `gh pr merge`
# with its auto flag is never called: when the PR looks clean (right after a push GitHub reports the
# old head's state for seconds) gh merges at once instead of arming, and a bypass actor merges past
# every check of the new head.
#
# When GitHub answers that the PR is already in a clean (or unstable) state, the helper does not
# merge: it waits until check runs of the head are registered, re-reads, arms if a required check is
# still pending, and reports `ready` once every required check of the base branch is green on that
# head, GitHub calls the PR mergeable (CLEAN, UNSTABLE, HAS_HOOKS) and no required review is
# missing. The caller then merges as a separate, explicit command with `--match-head-commit <sha>`.
#
# Before the arm the crew's risk classifier (the crew's `risk.command`, else `risk_paths.py` over
# `.weside/risk-paths`, both from origin/main) classifies the PR head against its base, wherever the
# helper runs: in a checkout whose HEAD is the PR head on the checkout itself (`risk_runner.py here`,
# uncommitted risk paths included), elsewhere on the head commit after a fetch of `pull/<PR>/head`
# into `refs/we-arm/pr-<PR>`, dropped again after the class (`risk_runner.py head`). Outside a git
# clone there is no class. Fail closed: no class is a refusal. A one-way class is no refusal: it
# merges only after the human's yes on the board (the asking session posts the merge question,
# `/we:master` § Close the run), and the session that asked arms it. The helper checks no board
# line; it says the class loudly instead: the
# line `one-way <class>: merges only after the human's yes on the board (L0)` before the verdict,
# and after the arm, or before the `ready` line, a PR comment `one-way <class> armed` or
# `one-way <class> ready for the printed merge` with that reminder and `(head <sha>)`, once per head (a run that
# finds the comment for this head does not post it again). A process worker (`WE_ROLE=worker`)
# never arms a one-way class and gets no `ready` for it: the session that asked the human does.
#
# One verdict line and its exit code:
#   armed: auto-merge on <sha> (<method>)                                        exit 0
#     then one more line, what the merge waits for: `pending: <names>` (the head's required checks
#     still running or not yet registered), `pending: none`, or `pending: unknown (<error>)`
#   gh failed: <error>                                                           exit 2  (also usage)
#   crew: <reason> (the crew file's merge block is unreadable)                   exit 2
#   ready: all required checks green on <sha> — merge: gh pr merge <PR> --<method> --match-head-commit <sha>
#                                                                                exit 3
#   refused: draft | refused: <state>                                            exit 4
#   refused: label <name> — only the human merges it                             exit 4
#   refused: armed by workflow — the step is gh pr ready                         exit 4
#   refused: head moved <old> -> <new>                                           exit 5
#   refused: one-way <class> — the session that asked the human arms it        exit 6  (WE_ROLE=worker)
#   refused: one-way not classified (<why>) — the classifier failed or printed no class   exit 6
#   red: <names> on <sha> — not armed                                            exit 7
#   no checks on <sha> after <n>s — not armed, run again                         exit 8
#   not armed on <sha> after <n>s (<mergeStateStatus>, review <decision>) — run again   exit 8
#
# The crew's `merge` block (crew.py merge) decides two refusals right after the first PR read:
# `merge.armer: workflow` (the repo's own workflow arms every ready PR, so no session arms) and a
# label of `merge.hold_labels` on the PR (a human merges it). The block is read from the PR's base
# (`crew.py merge --rev origin/<base>`, fetched first), the checkout's only when the base has no crew
# file or the caller is outside any git repo: the base is the merged truth, and a PR's own worktree
# carries its crew file. A base that cannot be read is a `crew:` error.
#
# `--check` reads once and arms nothing: the same facts as above (crew merge block, hold labels,
# one-way class, required names absent = pending, mergeStateStatus, reviewDecision) give one line
# and exit 0 only on `ready`. `--sha` binds it to that head (a different head is `refused: head
# moved`). A one-way class prints its line first and refuses only a worker. The worker rights gate
# calls it, with `WE_ROLE=worker`, before a worker's own merge line:
#   ready: … (as above)                                                         exit 0
#   pending: <names> on <sha> — not ready                                        exit 8
#   not ready on <sha> (<mergeStateStatus>, review <decision>)                   exit 8
#   refused: one-way not classified (<reason>)                                   exit 6
#   every other line and code as above (gh failed, crew, refused, red: … — not ready)
#
# Env: ARM_INTERVAL (seconds between reads, default 10), ARM_REGISTER_TIMEOUT (default 300).
set -uo pipefail

usage() { echo "gh failed: usage: arm_pr.sh <PR> [--method merge|squash|rebase] [--repo <owner/repo>] [--check [--sha <sha>]]"; exit 2; }

PR="" METHOD=merge REPO="" CHECK="" SHA="" ONE_WAY=""
while [ $# -gt 0 ]; do
  case "$1" in
    --method) METHOD=${2:-}; shift 2 || usage ;;
    --repo|-R) REPO=${2:-}; shift 2 || usage ;;
    --check) CHECK=1; shift ;;
    --sha) SHA=${2:-}; shift 2 || usage ;;
    -h|--help) sed -n '3,/^set -uo/p' "$0" | sed '$d'; exit 0 ;;
    -*) usage ;;
    *) [ -z "$PR" ] || usage; PR=$1; shift ;;
  esac
done
[[ "$PR" =~ ^[0-9]+$ ]] || usage
case "$METHOD" in merge|squash|rebase) ;; *) usage ;; esac
[ -z "$SHA" ] || { [ -n "$CHECK" ] && [[ "$SHA" =~ ^[0-9a-f]{40}$ ]]; } || usage
INTERVAL=${ARM_INTERVAL:-10}
TIMEOUT=${ARM_REGISTER_TIMEOUT:-300}
HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)

# stdout only is a gh value: gh prints notices (upgrade, preview commands) on stderr, even on success.
ARM_REF=""  # refs/we-arm/pr-<N> while one_way holds a fetched PR head; dropped after the class
drop_ref() { [ -z "$ARM_REF" ] || git update-ref -d "$ARM_REF" 2>/dev/null; ARM_REF=""; }
GH_ERR=$(mktemp) && trap 'rm -f "$GH_ERR"; drop_ref' EXIT
gh_err() { sed '/^[[:space:]]*$/d' "$GH_ERR" | tail -n 1; }
if [ -z "$REPO" ]; then
  REPO=$(gh repo view --json nameWithOwner --jq .nameWithOwner 2>"$GH_ERR") || { echo "gh failed: $(gh_err)"; exit 2; }
fi
OWNER=${REPO%%/*} NAME=${REPO#*/}

crew_merge() {  # the base's merge.$1 (a warning on stderr passes through); a broken crew: crew.py's reason
  local err rc
  err=$(mktemp) && python3 "$HERE/crew.py" merge "$1" --rev "origin/$BASE" 2>"$err"
  rc=$?
  if [ "$rc" -ne 0 ]; then echo "crew: $(tail -n 1 "$err" | sed 's/^crew: //')"; rm -f "$err"; return 2; fi
  cat "$err" >&2; rm -f "$err"
}
HOLD="" MERGE_READ=""
merge_block() {  # once, after the first read names the base: the armer refusal, then HOLD
  [ -z "$MERGE_READ" ] || return 0
  git fetch -q origin "$BASE" 2>/dev/null || true  # a stale or missing base ref reads an old rule
  ARMER=$(crew_merge armer) || { echo "$ARMER"; exit 2; }
  if [ "$ARMER" = workflow ]; then echo "refused: armed by workflow — the step is gh pr ready"; exit 4; fi
  HOLD=$(crew_merge hold_labels) || { echo "$HOLD"; exit 2; }
  MERGE_READ=1
}

# Line 1: id, state, isDraft, head, base, mergeStateStatus, reviewDecision (NONE when the repo
# requires no review), the PR's labels joined by a comma. Then one line per check on the head:
# <pending|pass|fail>\t<required by the PR: true|false>\t<name>. Checks of another commit (the
# last commit lagging behind the head) are not listed.
READ='query($owner:String!,$name:String!,$number:Int!){repository(owner:$owner,name:$name){pullRequest(number:$number){
  id state isDraft headRefOid baseRefName mergeStateStatus reviewDecision labels(first:100){nodes{name}}
  commits(last:1){nodes{commit{oid statusCheckRollup{contexts(first:100){nodes{__typename
    ... on CheckRun{name status conclusion isRequired(pullRequestNumber:$number)}
    ... on StatusContext{context state isRequired(pullRequestNumber:$number)}}}}}}}}}}'
JQ='.data.repository.pullRequest as $p
  | ([$p.id, $p.state, ($p.isDraft|tostring), $p.headRefOid, $p.baseRefName,
      ($p.mergeStateStatus // "UNKNOWN"), ($p.reviewDecision // "NONE"),
      ([($p.labels.nodes // [])[].name] | join(","))] | @tsv),
    ($p.commits.nodes[0].commit // {} | select(.oid == $p.headRefOid)
     | (.statusCheckRollup.contexts.nodes // [])[]
     | [(if .__typename == "StatusContext" then
           (if .state == "SUCCESS" then "pass" elif (.state == "PENDING" or .state == "EXPECTED") then "pending" else "fail" end)
         elif (.conclusion == "SUCCESS" or .conclusion == "NEUTRAL" or .conclusion == "SKIPPED") then "pass"
         elif (.conclusion // "") != "" then "fail"
         elif .status != "COMPLETED" then "pending"
         else "fail" end),
        (.isRequired | tostring), (.name // .context)] | @tsv)'
ARM='mutation($id:ID!,$sha:GitObjectID!,$method:PullRequestMergeMethod!){
  enablePullRequestAutoMerge(input:{pullRequestId:$id,expectedHeadOid:$sha,mergeMethod:$method}){
    pullRequest{autoMergeRequest{enabledAt}}}}'

read_pr() {  # sets ID STATE DRAFT HEAD BASE MSTATE REVIEW LABELS CHECKS; exits on a gh failure or a moved head
  local out
  out=$(gh api graphql -f query="$READ" -f owner="$OWNER" -f name="$NAME" -F number="$PR" --jq "$JQ" 2>"$GH_ERR") \
    || { echo "gh failed: $(gh_err)"; exit 2; }
  IFS=$'\t' read -r ID STATE DRAFT HEAD BASE MSTATE REVIEW LABELS <<<"$(head -n 1 <<<"$out")"
  CHECKS=$(tail -n +2 <<<"$out")
  [ -n "${HEAD:-}" ] || { echo "gh failed: no PR $PR in $REPO"; exit 2; }
  merge_block
  [ "$STATE" = OPEN ] || { echo "refused: $(tr "[:upper:]" "[:lower:]" <<<"$STATE")"; exit 4; }
  [ "$DRAFT" = false ] || { echo "refused: draft"; exit 4; }
  local label
  while IFS= read -r label; do
    [ -n "$label" ] || continue
    if grep -qxF -- "$label" <<<"$HOLD"; then echo "refused: label $label — only the human merges it"; exit 4; fi
  done < <(tr ',' '\n' <<<"${LABELS:-}")
  if [ -n "$SHA" ] && [ "$HEAD" != "$SHA" ]; then echo "refused: head moved $SHA -> $HEAD"; exit 5; fi
  SHA=$HEAD
}

one_way() {  # the PR head's class against its base, wherever this runs; fail closed
  # The crew's classifier (risk_runner.py: `risk.command`, else risk_paths.py, else no rules = T0).
  # In a checkout whose HEAD is the PR head it runs on the checkout, so an uncommitted risk path
  # is seen (risk_paths.py's exit 3); anywhere else on the head commit, fetched first. A non-zero
  # exit or an unknown line 1 is no class.
  local out line rc=0
  if [ "$(git rev-parse HEAD 2>/dev/null)" = "$SHA" ]; then
    out=$(python3 "$HERE/risk_runner.py" here "origin/$BASE" 2>/dev/null) || rc=$?
  else
    if ! git cat-file -e "$SHA^{commit}" 2>/dev/null; then
      ARM_REF="refs/we-arm/pr-$PR"  # the EXIT trap drops it too, whatever ends the run
      git fetch -q --no-tags origin "+refs/pull/$PR/head:$ARM_REF" 2>/dev/null \
        || git fetch -q --no-tags origin "$SHA" 2>/dev/null || true
    fi
    out=$(python3 "$HERE/risk_runner.py" head "$SHA" "origin/$BASE" 2>/dev/null) || rc=$?
    drop_ref
  fi
  line=$(head -n 1 <<<"$out")
  if [ "$rc" -ne 0 ]; then echo "refused: one-way not classified (${line:-risk_runner.py exit $rc})"; exit 6; fi
  case "$line" in
    "T2 one-way "*)
      ONE_WAY=${line#T2 one-way }
      if [ "${WE_ROLE:-}" = worker ]; then echo "refused: one-way $ONE_WAY — the session that asked the human arms it"; exit 6; fi
      echo "one-way $ONE_WAY: merges only after the human's yes on the board (L0)" ;;
    T0 | T2) ;;
    *) echo "refused: one-way not classified (line 1: ${line:-empty})"; exit 6 ;;
  esac
}

one_way_comment() {  # after an arm or before a ready line of a one-way PR: the class on the PR, once per head; never exits
  [ -n "$ONE_WAY" ] || return 0
  local tail="(head $SHA)" bodies
  bodies=$(gh pr view "$PR" --repo "$REPO" --json comments --jq '.comments[].body' 2>/dev/null) || bodies=""
  if grep -F -- "$tail" <<<"$bodies" | grep -q "^one-way $ONE_WAY .* — merges only after "; then return 0; fi
  gh pr comment "$PR" --repo "$REPO" \
    --body "one-way $ONE_WAY $1 — merges only after the human's yes on the board $tail" >/dev/null 2>"$GH_ERR" \
    || echo "one-way comment failed: $(gh_err)" >&2
}

REQUIRED=""
required_names() {  # the base branch's required check names (required_checks.sh, the one reader)
  REQUIRED=$("$HERE/required_checks.sh" --repo "$REPO" "$BASE") || { echo "$REQUIRED"; exit 2; }
}

pending_line() {  # after `armed:`: the head's required checks still pending, by name; never exits
  local names name v req pending=""
  names=$REQUIRED
  if [ -z "$names" ]; then
    names=$("$HERE/required_checks.sh" --repo "$REPO" "$BASE") || { echo "pending: unknown (${names#gh failed: })"; return 0; }
  fi
  while IFS=$'\t' read -r v req name; do  # a check GitHub marks required for this PR counts too
    [ "$req" = true ] && [ -n "${name:-}" ] && names="$names"$'\n'"$name"
  done <<<"$CHECKS"
  while IFS= read -r name; do
    [ -n "$name" ] || continue
    v=$(awk -F'\t' -v n="$name" '$3 == n { print $1 }' <<<"$CHECKS")
    case "$v" in ""|*pending*) pending="$pending, $name" ;; esac
  done < <(sed '/^$/d' <<<"$names" | sort -u)
  pending=${pending#, }
  echo "pending: ${pending:-none}"
}

arm() {  # 0 armed (exits), 1 GitHub calls the PR clean, exits on any other answer
  local out
  if out=$(gh api graphql -f query="$ARM" -f id="$ID" -f sha="$SHA" -f method="$(tr "[:lower:]" "[:upper:]" <<<"$METHOD")" 2>"$GH_ERR"); then
    echo "armed: auto-merge on $SHA ($METHOD)"; pending_line; one_way_comment armed; exit 0
  fi
  local why; why=$(gh_err)
  if grep -qiE 'is in (clean|unstable) status' "$GH_ERR"; then return 1; fi
  read_pr  # a head that moved since the read refuses here, with both SHAs
  echo "gh failed: $why"; exit 2
}

verdict() {  # pending | pass | fail:<names> for the required checks on the head
  local name v req fails="" pending="" seen=0
  if [ -n "$REQUIRED" ]; then
    while IFS= read -r name; do
      v=$(awk -F'\t' -v n="$name" '$3 == n { print $1 }' <<<"$CHECKS")
      case "$v" in
        "") pending=1 ;;  # absent is not green
        *fail*) fails="$fails, $name" ;;
        *pending*) pending=1 ;;
      esac
    done <<<"$REQUIRED"
  fi
  # A check GitHub marks required for this PR counts too; with no required check at all, every
  # registered check must pass.
  while IFS=$'\t' read -r v req name; do
    [ -n "${name:-}" ] || continue
    seen=1
    grep -qxF -- "$name" <<<"$REQUIRED" && continue  # judged above by name
    if [ "$req" = true ] || [ -z "$REQUIRED" ]; then
      case "$v" in fail) fails="$fails, $name" ;; pending) pending=1 ;; esac
    fi
  done <<<"$CHECKS"
  if [ -n "$fails" ]; then echo "fail:${fails#, }"
  elif [ "$seen" = 0 ] || [ -n "$pending" ]; then echo pending
  else echo pass; fi
}

ready_line() { echo "ready: all required checks green on $SHA — merge: gh pr merge $PR --$METHOD --match-head-commit $SHA"; }

if [ -n "$CHECK" ]; then  # one read, no arm, no wait
  read_pr
  one_way
  required_names
  [ -n "$CHECKS" ] || { echo "no checks on $SHA — not ready"; exit 8; }
  v=$(verdict)
  case "$v" in
    fail:*) echo "red: ${v#fail:} on $SHA — not ready"; exit 7 ;;
    pending) p=$(pending_line); echo "${p} on $SHA — not ready"; exit 8 ;;
  esac
  case "$MSTATE" in CLEAN|UNSTABLE|HAS_HOOKS) ;; *) echo "not ready on $SHA ($MSTATE, review $REVIEW)"; exit 8 ;; esac
  if [ "$REVIEW" = REVIEW_REQUIRED ] || [ "$REVIEW" = CHANGES_REQUESTED ]; then
    echo "not ready on $SHA ($MSTATE, review $REVIEW)"; exit 8
  fi
  ready_line; exit 0
fi

read_pr
one_way
arm  # returns only on a clean answer
required_names
start=$(date +%s)
while :; do
  if [ $(($(date +%s) - start)) -ge "$TIMEOUT" ]; then
    if [ -z "${CHECKS:-}" ]; then echo "no checks on $SHA after ${TIMEOUT}s — not armed, run again"
    else echo "not armed on $SHA after ${TIMEOUT}s ($MSTATE, review $REVIEW) — run again"; fi
    exit 8
  fi
  sleep "$INTERVAL"
  read_pr
  [ -n "$CHECKS" ] || continue  # the head's check runs are not registered yet
  v=$(verdict)
  case "$v" in
    fail:*) echo "red: ${v#fail:} on $SHA — not armed"; exit 7 ;;
    pending) arm ;;  # a required check runs: GitHub can wait for it now
    pass)
      # Green checks are not every requirement: a review or another rule GitHub still waits for
      # leaves the PR BLOCKED, and then it is armed instead. UNSTABLE (a red check that is not
      # required) and HAS_HOOKS merge like CLEAN: the required checks were judged by name above.
      case "$MSTATE" in CLEAN|UNSTABLE|HAS_HOOKS) ;; *) arm; continue ;; esac
      [ "$REVIEW" != REVIEW_REQUIRED ] && [ "$REVIEW" != CHANGES_REQUESTED ] || { arm; continue; }
      one_way_comment "ready for the printed merge"; ready_line; exit 3 ;;
  esac
done
