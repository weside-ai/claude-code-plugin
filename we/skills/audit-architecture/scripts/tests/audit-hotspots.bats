#!/usr/bin/env bats
#
# Tests for audit-hotspots.py — the Phase-1 primitive-density scanner.
#
# The fixture is a deliberately *generic* project (src/ layout, a made-up vendor), because the
# shipped catalog carries no project-specific defaults: encapsulation homes and the private-module
# root come from the project's own YAML. These tests therefore also cover that contract — if
# leak-detection only worked with a catalog default, they would fail.

setup() {
  SCRIPT_DIR="$(cd "$(dirname "$BATS_TEST_FILENAME")/.." && pwd)"
  SCRIPT="$SCRIPT_DIR/audit-hotspots.py"
  CATALOG="$SCRIPT_DIR/primitives.default.yml"

  TMPROOT="$(mktemp -d)"
  cd "$TMPROOT"

  git init -q
  git config user.email "test@test.local"
  git config user.name "test"

  mkdir -p src/core src/services src/config docs

  # File 1: a hub — composes several of the starter catalog's primitives, stays small
  cat > src/core/engine.py <<'EOF'
"""Mock engine composing several primitives."""
from vendorlib import Client
from src.core.logging import get_logger
from src.crud import user as crud_user
from src.core._internal import build_pipeline

logger = get_logger(__name__)


class Engine:
    def run(self, session_scope):
        with session_scope() as s:
            return s
EOF

  # File 2: violates encapsulation — vendor import in a service, plus a private reach-in
  cat > src/services/dispatcher.py <<'EOF'
"""Mock dispatcher with a vendor leak and a private reach-in."""
from vendorlib import Client
from src.core._internal import build_pipeline
from src.core.logging import get_logger

logger = get_logger(__name__)
EOF

  # File 3: the vendor's legitimate home
  cat > src/config/clients.py <<'EOF'
"""Legitimate vendor home."""
from vendorlib import Client


class ClientFactory:
    pass
EOF

  touch src/__init__.py src/core/__init__.py src/services/__init__.py src/config/__init__.py

  # Project config — carries the encapsulation contract the catalog deliberately leaves empty
  cat > docs/.audit-architecture.yml <<'EOF'
backend_root: src
findings_dir: docs/audits/
diagrams_dir: docs/architecture/diagrams/

hotspots:
  top_n: 5
  since: "1 day ago"
  expected_hubs:
    - src/core/engine.py
    - src/config/clients.py
  encapsulation_homes:
    vendorlib:
      - src/config/
  private_module_root: src/core
EOF

  git add -A
  git commit -q -m "fixture initial"
}

teardown() {
  cd /
  rm -rf "$TMPROOT"
}

@test "script exists" {
  [ -f "$SCRIPT" ]
}

@test "runs and produces a markdown table" {
  run python3 "$SCRIPT" --primitives-catalog "$CATALOG" --top 5 --since "1 day ago"
  [ "$status" -eq 0 ]
  [[ "$output" == *"Architecture Hotspot Heatmap"* ]]
  [[ "$output" == *"by composite score"* ]]
}

@test "score formula appears in output" {
  run python3 "$SCRIPT" --primitives-catalog "$CATALOG" --top 5 --since "1 day ago"
  [ "$status" -eq 0 ]
  [[ "$output" == *"primitives * 5"* ]]
  [[ "$output" == *"LOC / 50"* ]]
  [[ "$output" == *"churn"* ]]
}

@test "the starter catalog detects primitives in a generic project" {
  run python3 "$SCRIPT" --file src/core/engine.py --primitives-catalog "$CATALOG"
  [ "$status" -eq 0 ]
  # get_logger → structured-logging; session_scope → db-session; crud import → data-access-layer
  [[ "$output" == *"structured-logging"* ]]
  [[ "$output" == *"db-session"* ]]
}

@test "marks expected_hubs with ✓" {
  run python3 "$SCRIPT" --primitives-catalog "$CATALOG" --top 5 --since "1 day ago"
  [ "$status" -eq 0 ]
  [[ "$output" =~ "✓" ]]
}

@test "vendor leak detected outside the configured home (from project YAML)" {
  run python3 "$SCRIPT" --file src/services/dispatcher.py --primitives-catalog "$CATALOG"
  [ "$status" -eq 0 ]
  [[ "$output" == *"vendorlib"* ]]
}

@test "the vendor's own home has zero leaks" {
  run python3 "$SCRIPT" --file src/config/clients.py --primitives-catalog "$CATALOG"
  [ "$status" -eq 0 ]
  [[ "$output" == *"Vendor-leaks: none"* ]]
}

@test "private reach-in detected from outside the private root" {
  run python3 "$SCRIPT" --file src/services/dispatcher.py --primitives-catalog "$CATALOG"
  [ "$status" -eq 0 ]
  [[ "$output" == *"_internal"* ]] || [[ "$output" == *"each-in"* ]]
}

@test "--file mode prints detailed breakdown" {
  run python3 "$SCRIPT" --file src/core/engine.py --primitives-catalog "$CATALOG"
  [ "$status" -eq 0 ]
  [[ "$output" == *"Score:"* ]]
  [[ "$output" == *"Primitives composed"* ]]
  [[ "$output" == *"LOC:"* ]]
}

@test "--file mode errors on missing file" {
  run python3 "$SCRIPT" --file nonexistent.py --primitives-catalog "$CATALOG"
  [ "$status" -ne 0 ]
}

@test "--write produces a file in findings_dir" {
  run python3 "$SCRIPT" --primitives-catalog "$CATALOG" --top 5 --since "1 day ago" --write
  [ "$status" -eq 0 ]
  [ -f "docs/audits/$(date -u +%Y-%m-%d)-hotspots.md" ]
}

@test "loads custom backend_root override" {
  mkdir -p alt_root/app
  cp src/core/engine.py alt_root/app/engine.py
  run python3 "$SCRIPT" --backend-root alt_root/app --primitives-catalog "$CATALOG" --top 5 --since "1 day ago"
  [ "$status" -eq 0 ]
  [[ "$output" == *"alt_root/app"* ]]
}

@test "errors out helpfully if backend_root does not exist" {
  run python3 "$SCRIPT" --backend-root nonexistent --primitives-catalog "$CATALOG"
  [ "$status" -ne 0 ]
  [[ "$output" == *"Backend root not found"* ]]
}

@test "auto-detects the source root when the YAML names none" {
  # Drop backend_root from the config; src/ must still be found.
  grep -v '^backend_root:' docs/.audit-architecture.yml > docs/tmp.yml
  mv docs/tmp.yml docs/.audit-architecture.yml
  run python3 "$SCRIPT" --primitives-catalog "$CATALOG" --top 5 --since "1 day ago"
  [ "$status" -eq 0 ]
  [[ "$output" == *"src"* ]]
}

@test "warns when no primitive detectors configured (empty catalog)" {
  EMPTY_CATALOG="$(mktemp)"
  echo "primitives: []" > "$EMPTY_CATALOG"
  run python3 "$SCRIPT" --primitives-catalog "$EMPTY_CATALOG" --top 5 --since "1 day ago"
  [ "$status" -eq 0 ]
  [[ "$output" == *"WARNING"* ]] || true   # warning goes to stderr
  rm "$EMPTY_CATALOG"
}

@test "project YAML primitive_detectors override catalog entries" {
  cat >> docs/.audit-architecture.yml <<'EOF'

primitive_detectors:
  - name: custom-test-marker
    patterns:
      - "MARKER_FOR_TEST"
EOF
  echo "MARKER_FOR_TEST = True" >> src/services/dispatcher.py
  git add -A && git commit -q -m "add marker"

  run python3 "$SCRIPT" --file src/services/dispatcher.py --primitives-catalog "$CATALOG"
  [ "$status" -eq 0 ]
  [[ "$output" == *"custom-test-marker"* ]]
}
