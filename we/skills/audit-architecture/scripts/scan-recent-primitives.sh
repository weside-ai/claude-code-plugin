#!/usr/bin/env bash
#
# scan-recent-primitives.sh — Phase 0 helper for /we:audit-architecture.
#
# Scans the last N merged PRs for paths that show up in 3+ PRs and
# (optionally) for PR titles/bodies matching keyword patterns.
# Output is markdown ready to inline into the Findings-MD.
#
# Args:
#   --config   path to .audit-architecture.yml
#   --repo     path to the repo root (used to derive `gh` working dir)
#   --pr-count number of recent merged PRs to scan
#   --output-md emit markdown (default; reserved for future --output-json)
#
# Dependencies: gh (authenticated), jq, python3 (for YAML parsing).

set -euo pipefail

CONFIG=""
REPO=""
PR_COUNT=""
OUTPUT="md"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --config)    CONFIG="$2"; shift 2 ;;
    --repo)      REPO="$2"; shift 2 ;;
    --pr-count)  PR_COUNT="$2"; shift 2 ;;
    --output-md) OUTPUT="md"; shift ;;
    *) echo "Unknown arg: $1" >&2; exit 2 ;;
  esac
done

[[ -z "$CONFIG" ]] && { echo "ERROR: --config required" >&2; exit 2; }
[[ -z "$REPO" ]]   && { echo "ERROR: --repo required" >&2; exit 2; }
[[ -z "$PR_COUNT" ]] && PR_COUNT=100

# --- Read keyword patterns and repo_paths from YAML ---
read_yaml_list() {
  local key="$1"
  python3 -c "
import yaml, sys
d = yaml.safe_load(open('$CONFIG'))
items = d.get('healthcheck', {}).get('missing_primitive_scan', {}).get('$key', []) or []
for x in items:
    print(x)
"
}

mapfile -t KEYWORD_PATTERNS < <(read_yaml_list keyword_patterns)
mapfile -t REPO_PATHS < <(read_yaml_list repo_paths)

# --- Fetch recent PRs ---
PRS_JSON="$(gh pr list --state merged --limit "$PR_COUNT" \
  --json number,title,body,files 2>/dev/null || echo '[]')"

# --- Path frequency: count PRs per path-prefix matching repo_paths ---
PATH_COUNTS_TSV=""
if [[ ${#REPO_PATHS[@]} -gt 0 ]]; then
  REPO_PATHS_REGEX=$(printf '|%s' "${REPO_PATHS[@]}")
  REPO_PATHS_REGEX="${REPO_PATHS_REGEX:1}"  # drop leading |
  PATH_COUNTS_TSV=$(echo "$PRS_JSON" | jq -r --arg re "$REPO_PATHS_REGEX" '
    [.[] | {pr: .number, files: [.files[].path]}]
    | map(.files |= (
        map(select(test("^(\($re))")))
        | map(capture("^(?<p>(\($re))[^/]+/?)").p)
        | unique
      ))
    | map(select(.files | length > 0))
    | [.[] | .files[] as $p | $p]
    | group_by(.)
    | map({path: .[0], count: length})
    | sort_by(-.count)[]
    | "\(.path)\t\(.count)"
  ' || true)
fi

# --- Keyword matches ---
KEYWORD_HITS=""
if [[ ${#KEYWORD_PATTERNS[@]} -gt 0 ]]; then
  RE=$(IFS='|'; echo "${KEYWORD_PATTERNS[*]}")
  KEYWORD_HITS=$(echo "$PRS_JSON" | jq -r --arg re "$RE" '
    .[]
    | select((.title | test($re; "i")) or (.body // "" | test($re; "i")))
    | "- #\(.number) \"\(.title)\""
  ')
fi

# --- Emit markdown ---
echo "**Verdachts-Pfade (≥3 PRs in last $PR_COUNT):**"
echo
if [[ -z "$PATH_COUNTS_TSV" ]]; then
  echo "_(no paths matched)_"
else
  echo "| Path | PR Count |"
  echo "|---|---|"
  echo "$PATH_COUNTS_TSV" | awk -F'\t' '$2 >= 3 { printf("| `%s` | %d |\n", $1, $2) }'
fi

echo
echo "**PR-Schlagwort-Treffer (manuell prüfen):**"
echo
if [[ -z "$KEYWORD_HITS" ]]; then
  echo "_(no keyword hits)_"
else
  echo "$KEYWORD_HITS"
fi
