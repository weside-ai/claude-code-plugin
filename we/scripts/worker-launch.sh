#!/usr/bin/env bash
# worker-launch.sh — dispatch a headless claude worker using a named engine profile
#
# Usage:
#   worker-launch.sh [--engine <name>] [--cwd <worktree>] [--dry-run] -- <brief>
#
# Engine profiles live in .weside/engines.local.json (gitignored, per-repo).
# Keys are never stored in that file — only references (env-var name or
# ~/.weside/secrets.env key name). This script never logs a key value.
#
# Defaults: engine = first profile in the file; cwd = current directory.

set -euo pipefail

ENGINE=""
WORKTREE="$(pwd)"
DRY_RUN=false
BRIEF=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        --engine)  ENGINE="$2";   shift 2 ;;
        --cwd)     WORKTREE="$2"; shift 2 ;;
        --dry-run) DRY_RUN=true;  shift   ;;
        --)        shift; BRIEF="$*"; break ;;
        *) printf 'Unknown option: %s\n' "$1" >&2; exit 1 ;;
    esac
done

# --- locate engines.local.json (walk up from worktree) ---
ENGINES_FILE=""
dir="$WORKTREE"
while [[ "$dir" != "/" ]]; do
    if [[ -f "$dir/.weside/engines.local.json" ]]; then
        ENGINES_FILE="$dir/.weside/engines.local.json"
        break
    fi
    dir="$(dirname "$dir")"
done

if [[ -z "$ENGINES_FILE" ]]; then
    printf 'No .weside/engines.local.json found (searched up from %s)\n' "$WORKTREE" >&2
    printf 'Run /we:setup to create engine profiles.\n' >&2
    exit 1
fi

# --- resolve engine name ---
if [[ -z "$ENGINE" ]]; then
    ENGINE=$(python3 - "$ENGINES_FILE" <<'EOF'
import json, sys
data = json.load(open(sys.argv[1]))
if not data:
    print("engines.local.json is empty", file=sys.stderr); sys.exit(1)
print(next(iter(data)))
EOF
)
fi

# --- read profile fields ---
read_field() {
    python3 - "$ENGINES_FILE" "$ENGINE" "$1" <<'EOF'
import json, sys
data = json.load(open(sys.argv[1]))
engine, field = sys.argv[2], sys.argv[3]
if engine not in data:
    print(f"Engine '{engine}' not found in {sys.argv[1]}", file=sys.stderr); sys.exit(1)
val = data[engine].get(field)
if val is None:
    print(f"Engine '{engine}' missing field '{field}'", file=sys.stderr); sys.exit(1)
print(val if isinstance(val, str) else json.dumps(val))
EOF
}

BASE_URL=$(read_field "base_url")
MODEL=$(read_field "model")
KEY_REF=$(read_field "key_ref")

# --- resolve key by reference (never log the value) ---
KEY_REF_TYPE=$(python3 -c "import json,sys; kr=json.loads(sys.argv[1]); print('env' if 'env' in kr else 'secrets_env' if 'secrets_env' in kr else 'unknown')" "$KEY_REF")

API_KEY=""
case "$KEY_REF_TYPE" in
    env)
        VAR_NAME=$(python3 -c "import json,sys; print(json.loads(sys.argv[1])['env'])" "$KEY_REF")
        API_KEY="${!VAR_NAME:-}"
        if [[ -z "$API_KEY" ]]; then
            printf "Engine '%s': env var '%s' is not set\n" "$ENGINE" "$VAR_NAME" >&2; exit 1
        fi
        ;;
    secrets_env)
        KEY_NAME=$(python3 -c "import json,sys; print(json.loads(sys.argv[1])['secrets_env'])" "$KEY_REF")
        SECRETS_FILE="$HOME/.weside/secrets.env"
        if [[ ! -f "$SECRETS_FILE" ]]; then
            printf "Engine '%s': ~/.weside/secrets.env not found\n" "$ENGINE" >&2; exit 1
        fi
        API_KEY=$(grep "^${KEY_NAME}=" "$SECRETS_FILE" | cut -d= -f2- | head -1)
        if [[ -z "$API_KEY" ]]; then
            printf "Engine '%s': key '%s' not found in ~/.weside/secrets.env\n" "$ENGINE" "$KEY_NAME" >&2; exit 1
        fi
        ;;
    *)
        printf "Engine '%s': unrecognized key_ref form (expected 'env' or 'secrets_env')\n" "$ENGINE" >&2; exit 1
        ;;
esac

# --- dry-run: show config with key redacted ---
if [[ "$DRY_RUN" == "true" ]]; then
    printf 'engine:   %s\n' "$ENGINE"
    printf 'base_url: %s\n' "$BASE_URL"
    printf 'model:    %s\n' "$MODEL"
    printf 'key:      [REDACTED]\n'
    printf 'cwd:      %s\n' "$WORKTREE"
    printf 'brief:    %s\n' "${BRIEF:-(not provided)}"
    exit 0
fi

if [[ -z "$BRIEF" ]]; then
    printf 'No brief provided — pass it after --\n' >&2; exit 1
fi

# --- dispatch ---
export ANTHROPIC_BASE_URL="$BASE_URL"
export ANTHROPIC_AUTH_TOKEN="$API_KEY"
export ANTHROPIC_MODEL="$MODEL"

cd "$WORKTREE"
exec claude -p "$BRIEF"
