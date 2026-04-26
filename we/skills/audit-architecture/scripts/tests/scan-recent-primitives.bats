#!/usr/bin/env bats
#
# Tests for scan-recent-primitives.sh.
# We don't hit the real `gh` CLI — we stub it via PATH manipulation.

setup() {
  SCRIPT_DIR="$(cd "$(dirname "$BATS_TEST_FILENAME")/.." && pwd)"
  STUB_DIR="$(mktemp -d)"
  export ORIG_PATH="$PATH"
  export PATH="$STUB_DIR:$PATH"

  # Stub gh: returns canned PR list JSON
  cat > "$STUB_DIR/gh" <<'EOF'
#!/usr/bin/env bash
case "$*" in
  *"pr list"*)
    cat <<'JSON'
[
  {"number": 1, "title": "feat: introduce DispatchService", "body": "Centralize all time-driven work", "files": [{"path": "apps/backend/app/dispatch/service.py"}]},
  {"number": 2, "title": "fix: bug in dispatch", "body": "small fix", "files": [{"path": "apps/backend/app/dispatch/service.py"}]},
  {"number": 3, "title": "feat: extend dispatch", "body": "more", "files": [{"path": "apps/backend/app/dispatch/queue.py"}]},
  {"number": 4, "title": "chore: cleanup", "body": "noise", "files": [{"path": "apps/backend/app/utils/dates.py"}]}
]
JSON
    ;;
  *) echo "stub: unhandled gh args: $*" >&2; exit 1 ;;
esac
EOF
  chmod +x "$STUB_DIR/gh"

  # Minimal config fixture
  cat > "$STUB_DIR/config.yml" <<'EOF'
healthcheck:
  missing_primitive_scan:
    enabled: true
    pr_count: 100
    repo_paths: [apps/backend/app/]
    keyword_patterns: ["introduce", "centralize"]
EOF

  CONFIG="$STUB_DIR/config.yml"
}

teardown() {
  export PATH="$ORIG_PATH"
  rm -rf "$STUB_DIR"
}

@test "script exists and is executable" {
  [ -x "$SCRIPT_DIR/scan-recent-primitives.sh" ]
}

@test "outputs a Verdachts-Pfade section" {
  run bash "$SCRIPT_DIR/scan-recent-primitives.sh" --config "$CONFIG" --repo /tmp --pr-count 10 --output-md
  [ "$status" -eq 0 ]
  [[ "$output" == *"Verdachts-Pfade"* ]]
}

@test "flags apps/backend/app/dispatch/ as ≥3 PRs" {
  run bash "$SCRIPT_DIR/scan-recent-primitives.sh" --config "$CONFIG" --repo /tmp --pr-count 10 --output-md
  [ "$status" -eq 0 ]
  [[ "$output" == *"apps/backend/app/dispatch"* ]]
}

@test "lists keyword hits (introduce, centralize)" {
  run bash "$SCRIPT_DIR/scan-recent-primitives.sh" --config "$CONFIG" --repo /tmp --pr-count 10 --output-md
  [ "$status" -eq 0 ]
  [[ "$output" == *"#1"* ]]
  [[ "$output" == *"introduce DispatchService"* ]]
}

@test "errors out with non-zero on missing --config" {
  run bash "$SCRIPT_DIR/scan-recent-primitives.sh" --repo /tmp --pr-count 10 --output-md
  [ "$status" -ne 0 ]
}
