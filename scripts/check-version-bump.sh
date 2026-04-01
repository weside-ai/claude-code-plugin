#!/usr/bin/env bash
# Check that the plugin version has been bumped compared to the main branch.
# Used in CI for PRs targeting main.

set -euo pipefail

PLUGIN_JSON="we/.claude-plugin/plugin.json"

pr_version=$(jq -r '.version' "$PLUGIN_JSON")
main_version=$(git show origin/main:"$PLUGIN_JSON" 2>/dev/null | jq -r '.version')

if [[ -z "$main_version" || "$main_version" == "null" ]]; then
    echo "Could not read version from main branch — skipping check"
    exit 0
fi

if [[ "$pr_version" == "$main_version" ]]; then
    echo "ERROR: Version not bumped!"
    echo "  Current (PR):   $pr_version"
    echo "  Current (main): $main_version"
    echo ""
    echo "Every PR to main must bump the version in $PLUGIN_JSON."
    echo "  Patch (x.y.Z): bugfixes, typos, doc updates"
    echo "  Minor (x.Y.0): new skills, agents, commands, behavior changes"
    echo "  Major (X.0.0): breaking changes"
    exit 1
fi

echo "Version bumped: $main_version -> $pr_version"
