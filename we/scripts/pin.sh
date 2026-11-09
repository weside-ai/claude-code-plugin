#!/usr/bin/env bash
# pin.sh status|on|off — the account pin of the running master session (skills/pin/SKILL.md).
#
# Pinned: the session runs in its own config profile (CLAUDE_CONFIG_DIR set, started through
# $WCLAUDE_PIN, e.g. a claude-swap profile) and stays on that account. Unpinned: it runs on the
# global login like any plain `claude` and follows the account switcher.
# on/off cannot switch a live session: the profile's credential belongs to the switcher, a link to
# the global login would let it write through. So it starts the successor with `--resume <id>` in
# a new tmux window that waits until this session has exited; outside tmux it prints the command.
#   status   prints pinned|unpinned and the account the session bills
#   on|off   schedules the successor; then /exit this session
# A crew with launch.allow_bypass true (scripts/crew.py) gives the successor
# --allow-dangerously-skip-permissions, on and off alike; its start mode stays permissions.defaultMode.
set -euo pipefail

# is_claude <args of a process>: the command is Claude Code, run as `claude` or as
# `node|bun …/claude[.js]|…/claude-code/cli.js` (an npm install runs under node).
is_claude() {
  local first=${1%% *} rest=""
  [[ "$1" == *" "* ]] && rest=${1#* }
  [[ "$(basename "${first:-x}")" == claude ]] && return 0
  case $(basename "${first:-x}") in
    node | nodejs | bun) ;;
    *) return 1 ;;
  esac
  local second=${rest%% *}
  case $second in
    */claude | */claude.js | */claude-code/cli.js | */claude-code/*.js) return 0 ;;
  esac
  return 1
}

mode=${1:-status}
if [[ $mode == --is-claude ]]; then # test hook for is_claude
  is_claude "${2:-}"
  exit
fi
sid=${CLAUDE_CODE_SESSION_ID:-}

account_of() { # <.claude.json> → the e-mail of the logged-in account, from Claude Code's own config
  python3 - "$1" <<'PY'
import json, sys
try:
    with open(sys.argv[1]) as fh:
        print((json.load(fh).get("oauthAccount") or {}).get("emailAddress") or "unknown")
except (OSError, ValueError, AttributeError):
    print("unknown")
PY
}

if [[ -n "${CLAUDE_CONFIG_DIR:-}" ]]; then
  state=pinned
  account=$(account_of "$CLAUDE_CONFIG_DIR/.claude.json")
else
  state=unpinned
  account=$(account_of "$HOME/.claude.json")
fi

case $mode in
  status)
    echo "$state · bills $account${CLAUDE_CONFIG_DIR:+ · profile $(basename "$CLAUDE_CONFIG_DIR")}"
    exit 0
    ;;
  on | off) ;;
  *)
    echo "usage: pin.sh status|on|off" >&2
    exit 2
    ;;
esac

want=$([[ $mode == on ]] && echo pinned || echo unpinned)
if [[ $state == "$want" ]]; then
  echo "already $state · bills $account"
  exit 0
fi
[[ -n "$sid" ]] || { echo "pin.sh: CLAUDE_CODE_SESSION_ID missing; run it from the session's Bash tool" >&2; exit 1; }

if [[ $mode == on ]]; then
  [[ -n "${WCLAUDE_PIN:-}" ]] || { echo "pin.sh: WCLAUDE_PIN is not set; nothing to pin with" >&2; exit 1; }
  launch=$(printf '%q' "$WCLAUDE_PIN")
  prefix=""
else
  # --resume finds the transcript only in the target's projects/; the profile must share it.
  here=$(cd "$CLAUDE_CONFIG_DIR/projects" 2>/dev/null && pwd -P || true)
  there=$(cd "$HOME/.claude/projects" 2>/dev/null && pwd -P || true)
  if [[ -z "$here" || "$here" != "$there" ]]; then
    echo "pin.sh: $CLAUDE_CONFIG_DIR/projects is not ~/.claude/projects; link it first, or --resume will not find this session" >&2
    exit 1
  fi
  launch=claude
  prefix="-u CLAUDE_CONFIG_DIR"
fi
name_args=""
[[ -n "${WESIDE_COMPANION:-}" ]] && name_args=$(printf ' --name %q' "$WESIDE_COMPANION")
here_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
if [[ "$(python3 "$here_dir/crew.py" launch allow_bypass 2>/dev/null || true)" == true ]]; then
  name_args="$name_args --allow-dangerously-skip-permissions"
fi
cmd="cd $(printf '%q' "$PWD") && env $prefix WESIDE_COMPANION=$(printf '%q' "${WESIDE_COMPANION:-}") WE_ROLE=master $launch$name_args --resume $(printf '%q' "$sid")"

if [[ -n "${TMUX:-}" ]] && command -v tmux >/dev/null 2>&1; then
  # The session's own claude process: the nearest ancestor whose command is claude.
  pid=$$
  while [[ "$pid" -gt 1 ]]; do
    pid=$(ps -o ppid= -p "$pid" | tr -d ' ')
    is_claude "$(ps -o args= -p "$pid")" && break
  done
  [[ "$pid" -gt 1 ]] || { echo "pin.sh: no claude process above this shell" >&2; exit 1; }
  tmux new-window -d -n "${WESIDE_COMPANION:-pin-$mode}" \
    "while kill -0 $pid 2>/dev/null; do sleep 1; done; $cmd"
  echo "scheduled: the session restarts $want in a new tmux window as soon as this one exits — /exit now"
else
  echo "not in tmux: /exit, then run"
  echo "  $cmd"
fi
