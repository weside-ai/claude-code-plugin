#!/usr/bin/env bash
# Check that the plugin version is above the main branch's (SemVer, numeric per part).
# Used in CI for PRs targeting main.
#
# Usage: check-version-bump.sh [--armed]
#   --armed  also refuse a version that an open PR with auto-merge armed already carries, or a
#            higher one (the master runs it right before it arms; needs an authenticated `gh`).
# Workers do not bump: the master sets the version as the last commit before it arms auto-merge
# (AGENTS.md § Versioning).
# Env: VERSION_MAIN_REF (default origin/main), VERSION_SELF_PR (this PR's number, skipped by --armed).

set -euo pipefail

PLUGIN_JSON="we/.claude-plugin/plugin.json"
ARMED=""
for arg in "$@"; do
    case "$arg" in
        --armed) ARMED=1 ;;
        *) echo "usage: check-version-bump.sh [--armed]" >&2; exit 2 ;;
    esac
done

# vercmp A B: prints -1, 0 or 1 (numeric per dot-separated part, missing parts count 0)
vercmp() {
    local IFS=.
    local -a a=($1) b=($2)
    local i x y
    for i in 0 1 2; do
        x=${a[$i]:-0}; y=${b[$i]:-0}
        if ((10#$x > 10#$y)); then echo 1; return; fi
        if ((10#$x < 10#$y)); then echo -1; return; fi
    done
    echo 0
}

pr_version=$(jq -r '.version' "$PLUGIN_JSON")
main_version=$(git show "${VERSION_MAIN_REF:-origin/main}:$PLUGIN_JSON" 2>/dev/null | jq -r '.version' || true)

if [[ -z "$main_version" || "$main_version" == "null" ]]; then
    echo "Could not read version from main branch — skipping check"
    exit 0
fi

if [[ "$(vercmp "$pr_version" "$main_version")" != 1 ]]; then
    echo "ERROR: Version not above main!"
    echo "  Current (PR):   $pr_version"
    echo "  Current (main): $main_version"
    echo ""
    echo "Every PR to main must raise the version in $PLUGIN_JSON."
    echo "  Patch (x.y.Z): bugfixes, typos, doc updates"
    echo "  Minor (x.Y.0): new skills, agents, commands, behavior changes"
    echo "  Major (X.0.0): breaking changes"
    echo "Workers do not bump: the master sets the version as the last commit before it arms auto-merge."
    exit 1
fi

if [[ -n "$ARMED" ]]; then
    self=${VERSION_SELF_PR:-$(gh pr view --json number --jq .number 2>/dev/null || true)}
    repo=$(gh repo view --json nameWithOwner --jq .nameWithOwner)
    clash=""
    while IFS=$'\t' read -r number sha; do
        [[ -z "$number" || "$number" == "$self" ]] && continue
        # by head SHA: a fork's or a deleted branch's head stays readable, no ref to encode
        if ! other=$(gh api "repos/$repo/contents/$PLUGIN_JSON?ref=$sha" --jq .content \
            | base64 -d | jq -r .version) || [[ -z "$other" ]]; then
            clash="${clash}  #$number: version unreadable"$'\n'
            continue
        fi
        if [[ "$(vercmp "$pr_version" "$other")" != 1 ]]; then
            clash="${clash}  #$number carries $other"$'\n'
        fi
    done < <(gh pr list -R "$repo" --state open --limit 100 \
        --json number,headRefOid,autoMergeRequest \
        --jq '.[] | select(.autoMergeRequest != null) | "\(.number)\t\(.headRefOid)"')
    if [[ -n "$clash" ]]; then
        echo "ERROR: Version $pr_version is not above every armed open PR:"
        printf '%s' "$clash"
        echo "Set the next free version above them, then arm."
        exit 1
    fi
fi

echo "Version bumped: $main_version -> $pr_version"
