#!/usr/bin/env bash
# Claim the auto retro for PR <N>, or say who already covers it. Run from any checkout of the repo.
#
# Usage: retro_claim.sh <N>
#   claimed <path>                  exit 0  (the claim file is new: dispatch the retro)
#   covered: <path>                 exit 1  (a claim or an evidence line `PR #<N>` exists: skip)
#   no origin remote: <error>       exit 2
# The claim lives in `~/.claude/we-inbox/<owner>-<name>/claims/pr-<N>` (references/optimization-store.md
# § Staging), `<owner>-<name>` from `git remote get-url origin`; it never goes into the repo.
set -uo pipefail

N=${1:?usage: retro_claim.sh <N>}
N=${N#\#}
case "$N" in *[!0-9]*|"") echo "usage: retro_claim.sh <N> (a PR number)" >&2; exit 2 ;; esac
if ! URL=$(git remote get-url origin 2>&1); then echo "no origin remote: $URL"; exit 2; fi
SLUG=$(sed -E 's#^.*[:/]([^/:]+)/([^/]+)$#\1-\2#; s#\.git$##; s#/$##' <<<"${URL%/}")
STAGE="$HOME/.claude/we-inbox/$SLUG"
CLAIM="$STAGE/claims/pr-$N"
if [ -e "$CLAIM" ]; then echo "covered: $CLAIM"; exit 1; fi
TOP=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
for dir in "$STAGE" "$TOP/.weside/optimization/inbox"; do
  [ -d "$dir" ] || continue
  hit=$(grep -rlE "PR #$N([^0-9]|$)" "$dir" --include='*.md' 2>/dev/null | head -n 1)
  if [ -n "$hit" ]; then echo "covered: $hit"; exit 1; fi
done
mkdir -p "$STAGE/claims" && touch "$CLAIM" && echo "claimed $CLAIM"
