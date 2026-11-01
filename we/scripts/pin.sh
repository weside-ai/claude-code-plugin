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
set -euo pipefail

mode=${1:-status}
sid=${CLAUDE_CODE_SESSION_ID:-}

account_of() { # <config dir> → the e-mail of the logged-in account, from Claude Code's own config
  python3 - "$1" <<'PY'
import json, sys
from pathlib import Path
d = Path(sys.argv[1])
for f in (d / ".claude.json", Path.home() / ".claude.json"):
    if f.is_file():
        try:
            print((json.loads(f.read_text()).get("oauthAccount") or {}).get("emailAddress") or "unknown")
        except ValueError:
            print("unknown")
        break
else:
    print("unknown")
PY
}

if [[ -n "${CLAUDE_CONFIG_DIR:-}" ]]; then
  state=pinned
  account=$(account_of "$CLAUDE_CONFIG_DIR")
else
  state=unpinned
  account=$(account_of "$HOME")
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
  launch=claude
  prefix="-u CLAUDE_CONFIG_DIR"
fi
name_args=""
[[ -n "${WESIDE_COMPANION:-}" ]] && name_args=$(printf ' --name %q' "$WESIDE_COMPANION")
cmd="cd $(printf '%q' "$PWD") && env $prefix WESIDE_COMPANION=$(printf '%q' "${WESIDE_COMPANION:-}") WE_ROLE=master $launch$name_args --resume $(printf '%q' "$sid")"

if [[ -n "${TMUX:-}" ]] && command -v tmux >/dev/null 2>&1; then
  # The session's own claude process: the nearest ancestor whose command is claude.
  pid=$$
  while [[ "$pid" -gt 1 ]]; do
    pid=$(ps -o ppid= -p "$pid" | tr -d ' ')
    argv0=$(ps -o args= -p "$pid" | awk '{print $1}')
    [[ "$(basename "${argv0:-x}")" == claude ]] && break
  done
  [[ "$pid" -gt 1 ]] || { echo "pin.sh: no claude process above this shell" >&2; exit 1; }
  tmux new-window -d -n "${WESIDE_COMPANION:-pin-$mode}" \
    "while kill -0 $pid 2>/dev/null; do sleep 1; done; $cmd"
  echo "scheduled: the session restarts $want in a new tmux window as soon as this one exits — /exit now"
else
  echo "not in tmux: /exit, then run"
  echo "  $cmd"
fi
