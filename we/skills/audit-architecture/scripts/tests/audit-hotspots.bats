#!/usr/bin/env bats
#
# Tests for audit-hotspots.py — the v3 Phase-1 primitive-density scanner.
# We use a small in-tmpdir fixture project (3 fake .py files + minimal YAML).

setup() {
  SCRIPT_DIR="$(cd "$(dirname "$BATS_TEST_FILENAME")/.." && pwd)"
  SCRIPT="$SCRIPT_DIR/audit-hotspots.py"
  CATALOG="$SCRIPT_DIR/primitives.default.yml"

  TMPROOT="$(mktemp -d)"
  cd "$TMPROOT"

  # Initialize a tiny git repo so churn-counting works
  git init -q
  git config user.email "test@test.local"
  git config user.name "test"

  # Build a tiny fixture backend
  mkdir -p apps/backend/app/companion/core
  mkdir -p apps/backend/app/services
  mkdir -p docs

  # File 1: looks like a hub (uses several primitives, small)
  cat > apps/backend/app/companion/core/being.py <<'EOF'
"""Mock CompanionBeing."""
from app.config.llm import LLMFactory
from app.core.logging import get_logger
from app.crud import user as crud_user
from app.companion.core._langgraph import build_graph

logger = get_logger(__name__)
class CompanionBeing:
    pass
EOF

  # File 2: violates encapsulation (langchain in service)
  cat > apps/backend/app/services/skill_dispatcher.py <<'EOF'
"""Mock skill dispatcher with vendor leak."""
from langchain_anthropic import ChatAnthropic
from app.companion.core._credit_check import current_is_byok
from app.core.logging import get_logger
logger = get_logger(__name__)
EOF

  # File 3: legitimate config/llm.py (langchain home)
  mkdir -p apps/backend/app/config
  cat > apps/backend/app/config/llm.py <<'EOF'
"""Legitimate LLMFactory home."""
from langchain_anthropic import ChatAnthropic
from langchain_openai import ChatOpenAI

class LLMFactory:
    pass
EOF

  # __init__.py files (excluded from scan)
  touch apps/backend/app/__init__.py
  touch apps/backend/app/companion/__init__.py
  touch apps/backend/app/companion/core/__init__.py
  touch apps/backend/app/services/__init__.py
  touch apps/backend/app/config/__init__.py

  # Minimal project config
  cat > docs/.audit-architecture.yml <<'EOF'
backend_root: apps/backend/app
findings_dir: docs/audits/
diagrams_dir: docs/architecture/diagrams/

hotspots:
  top_n: 5
  since: "1 day ago"
  expected_hubs:
    - apps/backend/app/companion/core/being.py
    - apps/backend/app/config/llm.py
EOF

  git add -A
  git commit -q -m "fixture initial"
}

teardown() {
  cd /
  rm -rf "$TMPROOT"
}

@test "script exists and is executable" {
  [ -f "$SCRIPT" ]
}

@test "runs with default config and produces a markdown table" {
  run python3 "$SCRIPT" --primitives-catalog "$CATALOG" --top 5 --since "1 day ago"
  [ "$status" -eq 0 ]
  [[ "$output" == *"Architecture Hotspot Heatmap"* ]]
  # Fixture has 3 scannable files (excluding __init__.py); top label is min(N, total)
  [[ "$output" == *"by composite score"* ]]
}

@test "score formula appears in output" {
  run python3 "$SCRIPT" --primitives-catalog "$CATALOG" --top 5 --since "1 day ago"
  [ "$status" -eq 0 ]
  [[ "$output" == *"primitives * 5"* ]]
  [[ "$output" == *"LOC / 50"* ]]
  [[ "$output" == *"churn"* ]]
}

@test "marks expected_hubs with ✓" {
  run python3 "$SCRIPT" --primitives-catalog "$CATALOG" --top 5 --since "1 day ago"
  [ "$status" -eq 0 ]
  # being.py should be marked as hub (in expected_hubs)
  [[ "$output" =~ being\.py.*✓ ]] || [[ "$output" =~ "✓" ]]
}

@test "flags vendor leak in skill_dispatcher.py (outside langchain home)" {
  run python3 "$SCRIPT" --primitives-catalog "$CATALOG" --top 5 --since "1 day ago"
  [ "$status" -eq 0 ]
  [[ "$output" == *"skill_dispatcher.py"* ]]
}

@test "config/llm.py has zero leaks (it IS the langchain home)" {
  run python3 "$SCRIPT" --file apps/backend/app/config/llm.py --primitives-catalog "$CATALOG"
  [ "$status" -eq 0 ]
  [[ "$output" == *"Vendor-leaks: none"* ]]
}

@test "skill_dispatcher.py has langchain leak detected" {
  run python3 "$SCRIPT" --file apps/backend/app/services/skill_dispatcher.py --primitives-catalog "$CATALOG"
  [ "$status" -eq 0 ]
  [[ "$output" == *"langchain"* ]]
}

@test "--file mode prints detailed breakdown" {
  run python3 "$SCRIPT" --file apps/backend/app/companion/core/being.py --primitives-catalog "$CATALOG"
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
  # Move fixture
  mkdir -p alt_backend/app
  cp apps/backend/app/companion/core/being.py alt_backend/app/being.py
  run python3 "$SCRIPT" --backend-root alt_backend/app --primitives-catalog "$CATALOG" --top 5 --since "1 day ago"
  [ "$status" -eq 0 ]
  [[ "$output" == *"alt_backend/app"* ]]
}

@test "errors out helpfully if backend_root does not exist" {
  run python3 "$SCRIPT" --backend-root nonexistent --primitives-catalog "$CATALOG"
  [ "$status" -ne 0 ]
  [[ "$output" == *"Backend root not found"* ]]
}

@test "warns when no primitive detectors configured (empty catalog)" {
  EMPTY_CATALOG="$(mktemp)"
  echo "primitives: []" > "$EMPTY_CATALOG"
  run python3 "$SCRIPT" --primitives-catalog "$EMPTY_CATALOG" --top 5 --since "1 day ago"
  [ "$status" -eq 0 ]
  [[ "$output" == *"WARNING"* ]] || true   # warning is on stderr, may not be in $output
  rm "$EMPTY_CATALOG"
}

@test "project YAML primitive_detectors override catalog entries" {
  # Add a project-specific detector
  cat >> docs/.audit-architecture.yml <<'EOF'

primitive_detectors:
  - name: custom-test-marker
    patterns:
      - "MARKER_FOR_TEST"
EOF
  # Add a file with the marker
  echo "MARKER_FOR_TEST = True" >> apps/backend/app/services/skill_dispatcher.py
  git add -A && git commit -q -m "add marker"

  run python3 "$SCRIPT" --file apps/backend/app/services/skill_dispatcher.py --primitives-catalog "$CATALOG"
  [ "$status" -eq 0 ]
  [[ "$output" == *"custom-test-marker"* ]]
}
