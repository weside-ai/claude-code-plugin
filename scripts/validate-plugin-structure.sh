#!/usr/bin/env bash
# Validate the plugin directory structure.
# Checks that required files exist and JSON files are valid.

set -euo pipefail

ERRORS=0
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

check_file() {
    local file="$1"
    local description="$2"
    if [[ ! -f "$REPO_ROOT/$file" ]]; then
        echo "FAIL: Missing $description ($file)"
        ERRORS=$((ERRORS + 1))
    else
        echo "  OK: $description"
    fi
}

check_json() {
    local file="$1"
    local description="$2"
    if [[ ! -f "$REPO_ROOT/$file" ]]; then
        echo "FAIL: Missing $description ($file)"
        ERRORS=$((ERRORS + 1))
    elif ! python3 -m json.tool "$REPO_ROOT/$file" > /dev/null 2>&1; then
        echo "FAIL: Invalid JSON in $description ($file)"
        ERRORS=$((ERRORS + 1))
    else
        echo "  OK: $description (valid JSON)"
    fi
}

check_glob() {
    local pattern="$1"
    local description="$2"
    # shellcheck disable=SC2086
    if ! compgen -G "$REPO_ROOT"/$pattern > /dev/null 2>&1; then
        echo "FAIL: No files matching $description ($pattern)"
        ERRORS=$((ERRORS + 1))
    else
        local count
        count=$(find "$REPO_ROOT" -path "$REPO_ROOT/$pattern" 2>/dev/null | wc -l)
        echo "  OK: $description ($count found)"
    fi
}

echo "=== Plugin Structure Validation ==="
echo ""

echo "--- Required files ---"
check_file "README.md" "Repository README"
check_file "CLAUDE.md" "Developer guide"
check_file "we/CLAUDE.md" "Plugin instructions"

echo ""
echo "--- JSON configs ---"
check_json ".claude-plugin/marketplace.json" "Marketplace config"
check_json "we/.claude-plugin/plugin.json" "Plugin manifest"
check_json "we/.mcp.json" "MCP server config"
check_json "we/hooks/hooks.json" "Hooks config"

echo ""
echo "--- Plugin content ---"
check_glob "we/skills/*/SKILL.md" "Skills"
check_glob "we/commands/*.md" "Commands"
check_glob "we/agents/*.md" "Agents"

echo ""
if [[ $ERRORS -gt 0 ]]; then
    echo "FAILED: $ERRORS error(s) found"
    exit 1
else
    echo "PASSED: All structure checks OK"
fi
