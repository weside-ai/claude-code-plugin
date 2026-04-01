#!/usr/bin/env python3
"""
SQLite Orchestration CLI for the 'we' Claude Code Plugin.

Provides:
- Atomic task claiming with SQLite locking
- Worker heartbeat and timeout detection
- Checkpoint/resume support for /story phases
- Headless multi-instance management with worktree coordination
- Event logging for debugging

Usage:
    python cli.py task create <story_key> <description> [--phase <phase>] [--deps <task_ids>]
    python cli.py task list [--status <status>] [--story <story_key>]
    python cli.py task claim <task_id> <worker_id>
    python cli.py task update <task_id> --status <status> [--result <json>]
    python cli.py task get <task_id>

    python cli.py worker register <worker_id> [--terminal <name>] [--worktree <path>] [--headless]
    python cli.py worker unregister <worker_id> [--cleanup-worktree]
    python cli.py worker heartbeat <worker_id>
    python cli.py worker list [--active] [--headless-only]
    python cli.py worker status  # Pretty-print worker status with worktrees
    python cli.py worker cleanup [--timeout <minutes>] [--remove-worktrees]

    python cli.py checkpoint save <task_id> <phase> <state_json>
    python cli.py checkpoint load <task_id> [--phase <phase>]
    python cli.py checkpoint list [--task <task_id>] [--story <story_key>]
    python cli.py checkpoint clear <task_id> [--keep-latest]

    python cli.py story checkpoint <story_key> <phase> [--branch <name>] [--files <json>] [--commits <json>]
    python cli.py story resume <story_key>  # Get latest checkpoint for resume
    python cli.py story status <story_key>  # Get comprehensive story status
    python cli.py story list [--active]  # List stories with checkpoints

    python cli.py circuit check <story_key> <phase>  # Check if phase is allowed
    python cli.py circuit fail <story_key> <phase> [--error <msg>]  # Record failure
    python cli.py circuit success <story_key> <phase>  # Record success (resets circuit)
    python cli.py circuit reset <story_key> [--phase <phase>]  # Manual reset
    python cli.py circuit list [--story <key>] [--state <state>]  # List circuits
    python cli.py circuit get <story_key> <phase>  # Get circuit state
    python cli.py circuit config  # Show configuration

    python cli.py dor check <description>  # Check if description meets DoR
    python cli.py dor generate <summary> [--description <desc>]  # Generate DoR sections
    python cli.py dor refine <summary> [--description <desc>]  # Build refined description

    python cli.py cifix start <story_key> <pr_number>  # Start CI-fix tracking for a PR
    python cli.py cifix attempt <story_key> <fix_type> [--error <msg>]  # Record a fix attempt
    python cli.py cifix success <story_key>  # Mark CI as passing
    python cli.py cifix status <story_key>  # Get current CI-fix status
    python cli.py cifix reset <story_key>  # Reset CI-fix tracking
    python cli.py cifix list [--story <key>] [--active]  # List CI-fix sessions
    python cli.py cifix config  # Show configuration

    python cli.py event log <event_type> <message> [--task <task_id>] [--worker <worker_id>]
    python cli.py event list [--task <task_id>] [--limit <n>]

    python cli.py init  # Initialize/migrate database
    python cli.py cleanup [--timeout <minutes>]  # Release stale claimed tasks
"""

import argparse
import json
import re
import shutil
import sqlite3
import subprocess
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

# Valid worker ID pattern: alphanumeric, underscores, hyphens, dots
WORKER_ID_PATTERN = re.compile(r"^[\w\-\.]+$")

# Story phases for checkpoint tracking (WA-170, updated for unified workflow)
# Planning phases (before /story):
#   - refined: /refine completed (Business Context, AC, Testing Req)
#   - architected: /arch completed (Implementation Notes, ADRs, Security)
# Development phases (during /story):
#   - git_prepared through jira_transitioned
STORY_PHASES = [
    "refined",  # /we:refine — Story + Plan created
    "git_prepared",  # /we:develop — Branch created, story loaded
    "implementation_complete",  # /we:develop — Code + tests committed
    "ac_verified",  # /we:story — All ACs verified with evidence
    "simplified",  # /we:story — Code simplified
    "review_passed",  # /we:review — Code review passed
    "static_analysis_passed",  # /we:static — Lint/format/types passed
    "test_passed",  # /we:test — Tests + coverage passed
    "pr_created",  # /we:pr — PR created
    "ci_passed",  # /we:story — CI/Reviews green
]

# Stale checkpoint threshold in hours
STALE_CHECKPOINT_HOURS = 24

# Circuit Breaker configuration (WA-172)
CIRCUIT_BREAKER_CONFIG = {
    "max_failures_per_phase": 3,  # After 3 failures, circuit opens
    "cooldown_seconds": 60,  # Cooldown before HALF-OPEN test
    "auto_rollback": True,  # Automatically rollback to last checkpoint
}

# Circuit breaker states
CIRCUIT_STATE_CLOSED = "closed"  # Normal operation
CIRCUIT_STATE_OPEN = "open"  # Failed too many times, blocked
CIRCUIT_STATE_HALF_OPEN = "half_open"  # Testing if recovered

# CI-Fix Loop configuration (WA-174)
# Success rates based on historical analysis of CI failure categories
CIFIX_LINT_SUCCESS_RATE = 0.90  # High: ruff --fix resolves most lint issues
CIFIX_FORMAT_SUCCESS_RATE = 0.95  # Very high: ruff format is deterministic
CIFIX_TYPE_ERROR_SUCCESS_RATE = 0.50  # Medium: requires code analysis
CIFIX_TEST_FAILURE_SUCCESS_RATE = 0.30  # Low: often needs logic fixes
CIFIX_BUILD_ERROR_SUCCESS_RATE = 0.40  # Medium-low: config or dependency issues
CIFIX_MAX_ATTEMPTS = 3  # Maximum fix attempts before giving up

CIFIX_CONFIG = {
    "max_attempts": CIFIX_MAX_ATTEMPTS,
    "auto_fixable": {
        "lint": {
            "command": "ruff check --fix .",
            "success_rate": CIFIX_LINT_SUCCESS_RATE,
        },
        "format": {
            "command": "ruff format .",
            "success_rate": CIFIX_FORMAT_SUCCESS_RATE,
        },
        "type_error": {
            "command": None,
            "success_rate": CIFIX_TYPE_ERROR_SUCCESS_RATE,
        },  # Requires analysis
        "test_failure": {
            "command": None,
            "success_rate": CIFIX_TEST_FAILURE_SUCCESS_RATE,
        },  # Requires analysis
        "build_error": {
            "command": None,
            "success_rate": CIFIX_BUILD_ERROR_SUCCESS_RATE,
        },  # Requires analysis
    },
    "non_fixable": [
        "security_vulnerability",
        "complex_logic_error",
        "missing_env_var",
        "dependency_conflict",
    ],
}

# CI-Fix session states
CIFIX_STATE_ACTIVE = "active"  # Actively attempting fixes
CIFIX_STATE_SUCCESS = "success"  # CI passed
CIFIX_STATE_FAILED = "failed"  # Exceeded max attempts
CIFIX_STATE_BLOCKED = "blocked"  # Non-fixable error encountered

# Definition of Ready (DoR) markers for section detection (WA-173)
# Supports Jira Textile (h2.) and Markdown (##) formats
DOR_USER_STORY_MARKERS = ["h2. user story", "## user story", "as a ", "as an "]
DOR_ACCEPTANCE_MARKERS = [
    "h2. acceptance criteria",
    "## acceptance criteria",
    "acceptance criteria",
    "given ",
    "when ",
    "then ",
]
DOR_IMPLEMENTATION_MARKERS = [
    "h2. implementation notes",
    "## implementation notes",
    "implementation notes",
    "layers:",
    "pattern:",
]

# Database location - in ~/.claude/we/ (shared across worktrees)
# Using home directory ensures all worktrees share the same database
DB_PATH = Path.home() / ".claude" / "we" / "orchestration.db"

# Legacy path for migration
_LEGACY_DB_PATH = (
    Path(__file__).parent.parent.parent
    / ".claude"
    / "orchestration"
    / "orchestration.db"
)

# Worker timeout in minutes (tasks from offline workers get released)
DEFAULT_WORKER_TIMEOUT = 10


def _migrate_legacy_db() -> None:
    """Migrate database from legacy location to new home directory location.

    Legacy: .claude/orchestration/orchestration.db (per-worktree)
    New: ~/.claude/we/orchestration.db (shared across worktrees)
    """
    if _LEGACY_DB_PATH.exists() and not DB_PATH.exists():
        # Ensure parent directory exists
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)

        # Copy database and WAL files
        shutil.copy2(_LEGACY_DB_PATH, DB_PATH)
        wal_path = _LEGACY_DB_PATH.with_suffix(".db-wal")
        shm_path = _LEGACY_DB_PATH.with_suffix(".db-shm")
        if wal_path.exists():
            shutil.copy2(wal_path, DB_PATH.with_suffix(".db-wal"))
        if shm_path.exists():
            shutil.copy2(shm_path, DB_PATH.with_suffix(".db-shm"))

        print(f"✓ Migrated orchestration DB from {_LEGACY_DB_PATH} to {DB_PATH}")

        # Remove legacy files
        _LEGACY_DB_PATH.unlink()
        if wal_path.exists():
            wal_path.unlink()
        if shm_path.exists():
            shm_path.unlink()

        # Remove legacy directory if empty
        legacy_dir = _LEGACY_DB_PATH.parent
        if legacy_dir.exists() and not any(legacy_dir.iterdir()):
            legacy_dir.rmdir()
            print(f"✓ Removed empty legacy directory: {legacy_dir}")


def get_db() -> sqlite3.Connection:
    """Get database connection with proper settings."""
    # Auto-migrate from legacy location on first access
    _migrate_legacy_db()

    # Ensure parent directory exists
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(str(DB_PATH), timeout=30.0)
    conn.row_factory = sqlite3.Row
    # Enable WAL mode for better concurrent access
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=30000")  # 30 second timeout
    return conn


def init_db() -> None:
    """Initialize database schema with migrations."""
    conn = get_db()
    try:
        conn.executescript("""
            -- Task management
            CREATE TABLE IF NOT EXISTS tasks (
                id TEXT PRIMARY KEY,
                story_key TEXT NOT NULL,
                description TEXT NOT NULL,
                status TEXT DEFAULT 'pending' CHECK(status IN ('pending', 'claimed', 'running', 'completed', 'failed', 'blocked')),
                worker_id TEXT,
                phase TEXT,
                dependencies TEXT,  -- JSON array of task IDs
                started_at DATETIME,
                completed_at DATETIME,
                result_json TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            );

            -- Worker registration (extended for headless support - WA-176)
            CREATE TABLE IF NOT EXISTS workers (
                id TEXT PRIMARY KEY,
                terminal TEXT,
                status TEXT DEFAULT 'idle' CHECK(status IN ('idle', 'working', 'offline')),
                current_task_id TEXT,
                worktree_path TEXT,  -- Path to git worktree (for headless instances)
                is_headless BOOLEAN DEFAULT FALSE,  -- True for headless Claude instances
                last_heartbeat DATETIME DEFAULT CURRENT_TIMESTAMP,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            );

            -- Checkpoints for task resume
            CREATE TABLE IF NOT EXISTS checkpoints (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id TEXT NOT NULL,
                phase TEXT NOT NULL,
                state_json TEXT NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (task_id) REFERENCES tasks(id)
            );

            -- Story checkpoints for /story resume (WA-170)
            CREATE TABLE IF NOT EXISTS story_checkpoints (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                story_key TEXT NOT NULL,
                phase TEXT NOT NULL,  -- One of STORY_PHASES
                phase_index INTEGER NOT NULL,  -- Index in STORY_PHASES for ordering
                branch TEXT,  -- Git branch name
                files_modified TEXT,  -- JSON array of modified files
                commits TEXT,  -- JSON array of commit hashes
                pr_number INTEGER,  -- PR number if created
                test_coverage REAL,  -- Test coverage percentage
                extra_data TEXT,  -- JSON for additional phase-specific data
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            );

            -- Circuit breaker state tracking (WA-172)
            CREATE TABLE IF NOT EXISTS circuit_breakers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                story_key TEXT NOT NULL,
                phase TEXT NOT NULL,
                failure_count INTEGER DEFAULT 0,
                state TEXT DEFAULT 'closed' CHECK(state IN ('closed', 'open', 'half_open')),
                last_failure_at DATETIME,
                opened_at DATETIME,  -- When circuit transitioned to OPEN
                last_error TEXT,  -- Error message from last failure
                rollback_commit TEXT,  -- Commit hash rolled back to (if any)
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(story_key, phase)
            );

            -- CI-Fix session tracking (WA-174)
            CREATE TABLE IF NOT EXISTS cifix_sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                story_key TEXT NOT NULL,
                pr_number INTEGER NOT NULL,
                state TEXT DEFAULT 'active' CHECK(state IN ('active', 'success', 'failed', 'blocked')),
                attempt_count INTEGER DEFAULT 0,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                completed_at DATETIME,
                UNIQUE(story_key, pr_number)
            );

            -- CI-Fix attempt history (WA-174)
            CREATE TABLE IF NOT EXISTS cifix_attempts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id INTEGER NOT NULL,
                attempt_number INTEGER NOT NULL,
                fix_type TEXT NOT NULL,  -- lint, format, type_error, test_failure, build_error
                error_message TEXT,
                fix_applied TEXT,  -- Description of fix or command run
                success BOOLEAN DEFAULT FALSE,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (session_id) REFERENCES cifix_sessions(id)
            );

            -- Event log for debugging
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id TEXT,
                worker_id TEXT,
                event_type TEXT NOT NULL,
                message TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            );

            -- Story workflow tracking for crash recovery (WA-234)
            CREATE TABLE IF NOT EXISTS story_workflow (
                story_key TEXT PRIMARY KEY,
                phase TEXT NOT NULL,  -- Current phase in STORY_PHASES
                branch_name TEXT,
                pr_number INTEGER,
                started_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                error_message TEXT,
                retry_count INTEGER DEFAULT 0
            );

            -- Story metrics for retrospective analysis (WA-234)
            CREATE TABLE IF NOT EXISTS story_metrics (
                story_key TEXT PRIMARY KEY,
                pr_number INTEGER,
                ci_attempts INTEGER DEFAULT 1,
                failure_types TEXT,  -- JSON array of failure types
                first_ci_green BOOLEAN,
                time_to_merge_minutes INTEGER,
                lessons_learned TEXT,
                retro_completed BOOLEAN DEFAULT FALSE,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME,
                merged_at DATETIME
            );

            -- Indexes for common queries
            CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);
            CREATE INDEX IF NOT EXISTS idx_tasks_story ON tasks(story_key);
            CREATE INDEX IF NOT EXISTS idx_workers_status ON workers(status);
            CREATE INDEX IF NOT EXISTS idx_workers_headless ON workers(is_headless);
            CREATE INDEX IF NOT EXISTS idx_events_task ON events(task_id);
            CREATE INDEX IF NOT EXISTS idx_checkpoints_task ON checkpoints(task_id);
            CREATE INDEX IF NOT EXISTS idx_story_checkpoints_story ON story_checkpoints(story_key);
            CREATE INDEX IF NOT EXISTS idx_story_checkpoints_phase ON story_checkpoints(phase);
            CREATE INDEX IF NOT EXISTS idx_circuit_breakers_story ON circuit_breakers(story_key);
            CREATE INDEX IF NOT EXISTS idx_circuit_breakers_state ON circuit_breakers(state);
            CREATE INDEX IF NOT EXISTS idx_circuit_breakers_story_phase ON circuit_breakers(story_key, phase);
            CREATE INDEX IF NOT EXISTS idx_cifix_sessions_story ON cifix_sessions(story_key);
            CREATE INDEX IF NOT EXISTS idx_cifix_sessions_state ON cifix_sessions(state);
            CREATE INDEX IF NOT EXISTS idx_cifix_attempts_session ON cifix_attempts(session_id);
            CREATE INDEX IF NOT EXISTS idx_story_workflow_phase ON story_workflow(phase);
            CREATE INDEX IF NOT EXISTS idx_story_metrics_retro ON story_metrics(retro_completed);
        """)

        # Run migrations for existing databases
        _migrate_db(conn)

        conn.commit()
        print(json.dumps({"success": True, "message": "Database initialized"}))
    finally:
        conn.close()


def _migrate_db(conn: sqlite3.Connection) -> None:
    """Run schema migrations for existing databases."""
    # Check if workers table needs worktree_path column
    cursor = conn.execute("PRAGMA table_info(workers)")
    columns = {row[1] for row in cursor.fetchall()}

    if "worktree_path" not in columns:
        conn.execute("ALTER TABLE workers ADD COLUMN worktree_path TEXT")

    if "is_headless" not in columns:
        conn.execute("ALTER TABLE workers ADD COLUMN is_headless BOOLEAN DEFAULT FALSE")

    # Check if story_metrics table needs updated_at column (WA-234)
    cursor = conn.execute("PRAGMA table_info(story_metrics)")
    metrics_columns = {row[1] for row in cursor.fetchall()}

    if "updated_at" not in metrics_columns:
        conn.execute("ALTER TABLE story_metrics ADD COLUMN updated_at DATETIME")


def task_create(
    story_key: str,
    description: str,
    phase: str | None = None,
    dependencies: list[str] | None = None,
    task_id: str | None = None,
) -> dict[str, Any]:
    """Create a new task."""
    conn = get_db()
    try:
        tid = task_id or f"task-{uuid.uuid4().hex[:8]}"
        deps_json = json.dumps(dependencies) if dependencies else None

        conn.execute(
            """
            INSERT INTO tasks (id, story_key, description, phase, dependencies)
            VALUES (?, ?, ?, ?, ?)
            """,
            (tid, story_key, description, phase, deps_json),
        )
        conn.commit()

        # Log event
        _log_event(
            conn, "task_created", f"Task {tid} created for {story_key}", task_id=tid
        )
        conn.commit()

        return {"success": True, "task_id": tid, "story_key": story_key}
    finally:
        conn.close()


def task_list(
    status: str | None = None, story_key: str | None = None
) -> list[dict[str, Any]]:
    """List tasks with optional filters."""
    conn = get_db()
    try:
        query = "SELECT * FROM tasks WHERE 1=1"
        params: list[Any] = []

        if status:
            query += " AND status = ?"
            params.append(status)
        if story_key:
            query += " AND story_key = ?"
            params.append(story_key)

        query += " ORDER BY created_at DESC"

        cursor = conn.execute(query, params)
        return [dict(row) for row in cursor.fetchall()]
    finally:
        conn.close()


def task_get(task_id: str) -> dict[str, Any] | None:
    """Get a single task by ID."""
    conn = get_db()
    try:
        cursor = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,))
        row = cursor.fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def task_claim(task_id: str, worker_id: str) -> dict[str, Any]:
    """
    Atomically claim a task for a worker.

    Returns success only if:
    - Task exists and is pending
    - All dependencies are completed
    - No other worker has claimed it
    """
    conn = get_db()
    try:
        # Start exclusive transaction for atomic claim
        conn.execute("BEGIN EXCLUSIVE")

        # Check task exists and is pending
        cursor = conn.execute(
            "SELECT * FROM tasks WHERE id = ? AND status = 'pending'",
            (task_id,),
        )
        task = cursor.fetchone()

        if not task:
            conn.rollback()
            # Check if task exists at all
            cursor = conn.execute("SELECT status FROM tasks WHERE id = ?", (task_id,))
            existing = cursor.fetchone()
            if existing:
                return {
                    "success": False,
                    "error": f"Task {task_id} is not pending (status: {existing['status']})",
                }
            return {"success": False, "error": f"Task {task_id} not found"}

        # Check dependencies
        deps = json.loads(task["dependencies"]) if task["dependencies"] else []
        if deps:
            placeholders = ",".join("?" * len(deps))
            cursor = conn.execute(
                f"SELECT id, status FROM tasks WHERE id IN ({placeholders})",  # nosec B608 - placeholders are ? only
                deps,
            )
            dep_statuses = {row["id"]: row["status"] for row in cursor.fetchall()}

            incomplete = [d for d in deps if dep_statuses.get(d) != "completed"]
            if incomplete:
                conn.rollback()
                return {
                    "success": False,
                    "error": f"Dependencies not complete: {incomplete}",
                    "blocked_by": incomplete,
                }

        # Claim the task
        now = datetime.now().isoformat()
        conn.execute(
            """
            UPDATE tasks
            SET status = 'claimed', worker_id = ?, started_at = ?
            WHERE id = ?
            """,
            (worker_id, now, task_id),
        )

        # Update worker status
        conn.execute(
            """
            UPDATE workers
            SET status = 'working', current_task_id = ?, last_heartbeat = ?
            WHERE id = ?
            """,
            (task_id, now, worker_id),
        )

        # Log event
        _log_event(
            conn,
            "task_claimed",
            f"Task {task_id} claimed by {worker_id}",
            task_id=task_id,
            worker_id=worker_id,
        )

        conn.commit()
        return {"success": True, "task_id": task_id, "worker_id": worker_id}
    except Exception as e:
        conn.rollback()
        return {"success": False, "error": str(e)}
    finally:
        conn.close()


def task_update(
    task_id: str,
    status: str | None = None,
    result: str | None = None,
    phase: str | None = None,
) -> dict[str, Any]:
    """Update a task's status and/or result."""
    conn = get_db()
    try:
        updates: list[str] = []
        params: list[Any] = []

        if status:
            updates.append("status = ?")
            params.append(status)
            if status == "completed":
                updates.append("completed_at = ?")
                params.append(datetime.now().isoformat())
            elif status == "running":
                updates.append("started_at = COALESCE(started_at, ?)")
                params.append(datetime.now().isoformat())

        if result:
            updates.append("result_json = ?")
            params.append(result)

        if phase:
            updates.append("phase = ?")
            params.append(phase)

        if not updates:
            return {"success": False, "error": "No updates provided"}

        params.append(task_id)
        query = f"UPDATE tasks SET {', '.join(updates)} WHERE id = ?"  # nosec B608 - parameterized

        cursor = conn.execute(query, params)
        if cursor.rowcount == 0:
            return {"success": False, "error": f"Task {task_id} not found"}

        # If completed, free up the worker
        if status == "completed":
            conn.execute(
                """
                UPDATE workers
                SET status = 'idle', current_task_id = NULL
                WHERE current_task_id = ?
                """,
                (task_id,),
            )

        # Log event
        _log_event(
            conn,
            f"task_{status or 'updated'}",
            f"Task {task_id} updated",
            task_id=task_id,
        )

        conn.commit()
        return {"success": True, "task_id": task_id}
    finally:
        conn.close()


def worker_register(
    worker_id: str,
    terminal: str | None = None,
    worktree_path: str | None = None,
    is_headless: bool = False,
) -> dict[str, Any]:
    """Register a new worker or update existing.

    Security: Validates worker_id format to prevent injection attacks.
    """
    # Security: Validate worker_id format
    if not WORKER_ID_PATTERN.match(worker_id):
        return {
            "success": False,
            "error": f"Invalid worker_id format: {worker_id!r}. "
            "Only alphanumeric, underscores, hyphens, and dots allowed.",
        }

    conn = get_db()
    try:
        now = datetime.now().isoformat()
        conn.execute(
            """
            INSERT INTO workers (id, terminal, worktree_path, is_headless, last_heartbeat)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                terminal = COALESCE(excluded.terminal, terminal),
                worktree_path = COALESCE(excluded.worktree_path, worktree_path),
                is_headless = excluded.is_headless,
                last_heartbeat = excluded.last_heartbeat,
                status = 'idle'
            """,
            (worker_id, terminal, worktree_path, is_headless, now),
        )

        msg = f"Worker {worker_id} registered"
        if is_headless:
            msg += f" (headless, worktree: {worktree_path})"
        _log_event(conn, "worker_registered", msg, worker_id=worker_id)
        conn.commit()
        return {"success": True, "worker_id": worker_id, "is_headless": is_headless}
    finally:
        conn.close()


def worker_unregister(worker_id: str, cleanup_worktree: bool = False) -> dict[str, Any]:
    """Unregister a worker and optionally cleanup its worktree."""
    conn = get_db()
    try:
        # Get worker info first
        cursor = conn.execute(
            "SELECT worktree_path, current_task_id FROM workers WHERE id = ?",
            (worker_id,),
        )
        worker = cursor.fetchone()

        if not worker:
            return {"success": False, "error": f"Worker {worker_id} not found"}

        worktree_path = worker["worktree_path"]
        current_task = worker["current_task_id"]

        # Release any claimed task
        if current_task:
            conn.execute(
                """
                UPDATE tasks SET status = 'pending', worker_id = NULL, started_at = NULL
                WHERE id = ? AND status IN ('claimed', 'running')
                """,
                (current_task,),
            )
            _log_event(
                conn,
                "task_released",
                f"Task {current_task} released due to worker unregister",
                task_id=current_task,
                worker_id=worker_id,
            )

        # Delete the worker
        conn.execute("DELETE FROM workers WHERE id = ?", (worker_id,))
        _log_event(
            conn,
            "worker_unregistered",
            f"Worker {worker_id} unregistered",
            worker_id=worker_id,
        )
        conn.commit()

        # Cleanup worktree if requested
        worktree_removed = False
        if cleanup_worktree and worktree_path:
            worktree_removed = _remove_worktree(worktree_path)

        return {
            "success": True,
            "worker_id": worker_id,
            "worktree_removed": worktree_removed,
            "task_released": current_task,
        }
    finally:
        conn.close()


def _remove_worktree(worktree_path: str) -> bool:
    """Remove a git worktree safely.

    Security: Validates path is under workspace root to prevent path traversal attacks.
    """
    try:
        path = Path(worktree_path).resolve()
        workspace_root = Path(__file__).parent.parent.parent.resolve()

        # Security: Validate path is under workspace root to prevent path traversal
        if workspace_root not in path.parents and path != workspace_root:
            return False  # Path escape attempt blocked

        if not path.exists():
            return False

        # Try git worktree remove first
        result = subprocess.run(
            ["git", "worktree", "remove", str(path), "--force"],
            capture_output=True,
            text=True,
            cwd=workspace_root,
        )

        if result.returncode == 0:
            return True

        # Fallback: manual removal if git command fails
        if path.exists():
            shutil.rmtree(path)
            return True

        return False
    except Exception:
        return False


def worker_heartbeat(worker_id: str) -> dict[str, Any]:
    """Update worker heartbeat timestamp."""
    conn = get_db()
    try:
        now = datetime.now().isoformat()
        cursor = conn.execute(
            "UPDATE workers SET last_heartbeat = ? WHERE id = ?",
            (now, worker_id),
        )
        if cursor.rowcount == 0:
            return {"success": False, "error": f"Worker {worker_id} not found"}
        conn.commit()
        return {"success": True, "worker_id": worker_id, "timestamp": now}
    finally:
        conn.close()


def worker_list(
    active_only: bool = False, headless_only: bool = False
) -> list[dict[str, Any]]:
    """List workers with optional filters."""
    conn = get_db()
    try:
        query = "SELECT * FROM workers WHERE 1=1"
        params: list[Any] = []

        if active_only:
            timeout = datetime.now() - timedelta(minutes=DEFAULT_WORKER_TIMEOUT)
            query += " AND last_heartbeat > ? AND status != 'offline'"
            params.append(timeout.isoformat())

        if headless_only:
            query += " AND is_headless = TRUE"

        query += " ORDER BY created_at DESC"
        cursor = conn.execute(query, params)
        return [dict(row) for row in cursor.fetchall()]
    finally:
        conn.close()


def worker_status() -> dict[str, Any]:
    """Get detailed worker status with pretty formatting."""
    conn = get_db()
    try:
        timeout = datetime.now() - timedelta(minutes=DEFAULT_WORKER_TIMEOUT)
        cursor = conn.execute("SELECT * FROM workers ORDER BY created_at DESC")
        workers = [dict(row) for row in cursor.fetchall()]

        active = []
        stale = []
        offline = []

        for w in workers:
            heartbeat = (
                datetime.fromisoformat(w["last_heartbeat"])
                if w["last_heartbeat"]
                else None
            )
            is_stale = heartbeat and heartbeat < timeout if heartbeat else True

            info = {
                "id": w["id"],
                "status": w["status"],
                "task": w["current_task_id"],
                "worktree": w["worktree_path"],
                "headless": bool(w["is_headless"]),
                "terminal": w["terminal"],
                "last_heartbeat": w["last_heartbeat"],
            }

            if w["status"] == "offline":
                offline.append(info)
            elif is_stale:
                stale.append(info)
            else:
                active.append(info)

        return {
            "active": active,
            "stale": stale,
            "offline": offline,
            "summary": {
                "total": len(workers),
                "active": len(active),
                "stale": len(stale),
                "offline": len(offline),
            },
        }
    finally:
        conn.close()


def checkpoint_save(task_id: str, phase: str, state_json: str) -> dict[str, Any]:
    """Save a checkpoint for a task."""
    conn = get_db()
    try:
        conn.execute(
            """
            INSERT INTO checkpoints (task_id, phase, state_json)
            VALUES (?, ?, ?)
            """,
            (task_id, phase, state_json),
        )

        _log_event(
            conn,
            "checkpoint_saved",
            f"Checkpoint saved for {task_id} at {phase}",
            task_id=task_id,
        )
        conn.commit()
        return {"success": True, "task_id": task_id, "phase": phase}
    finally:
        conn.close()


def checkpoint_load(task_id: str, phase: str | None = None) -> dict[str, Any] | None:
    """Load the latest checkpoint for a task."""
    conn = get_db()
    try:
        if phase:
            cursor = conn.execute(
                """
                SELECT * FROM checkpoints
                WHERE task_id = ? AND phase = ?
                ORDER BY created_at DESC LIMIT 1
                """,
                (task_id, phase),
            )
        else:
            cursor = conn.execute(
                """
                SELECT * FROM checkpoints
                WHERE task_id = ?
                ORDER BY created_at DESC LIMIT 1
                """,
                (task_id,),
            )
        row = cursor.fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def event_log(
    event_type: str,
    message: str,
    task_id: str | None = None,
    worker_id: str | None = None,
) -> dict[str, Any]:
    """Log an event."""
    conn = get_db()
    try:
        _log_event(conn, event_type, message, task_id, worker_id)
        conn.commit()
        return {"success": True}
    finally:
        conn.close()


def _log_event(
    conn: sqlite3.Connection,
    event_type: str,
    message: str,
    task_id: str | None = None,
    worker_id: str | None = None,
) -> None:
    """Internal function to log events (uses existing connection)."""
    conn.execute(
        """
        INSERT INTO events (event_type, message, task_id, worker_id)
        VALUES (?, ?, ?, ?)
        """,
        (event_type, message, task_id, worker_id),
    )


def event_list(task_id: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
    """List events with optional task filter."""
    conn = get_db()
    try:
        if task_id:
            cursor = conn.execute(
                """
                SELECT * FROM events
                WHERE task_id = ?
                ORDER BY created_at DESC LIMIT ?
                """,
                (task_id, limit),
            )
        else:
            cursor = conn.execute(
                "SELECT * FROM events ORDER BY created_at DESC LIMIT ?",
                (limit,),
            )
        return [dict(row) for row in cursor.fetchall()]
    finally:
        conn.close()


def cleanup(
    timeout_minutes: int = DEFAULT_WORKER_TIMEOUT, remove_worktrees: bool = False
) -> dict[str, Any]:
    """
    Release tasks from timed-out workers and optionally remove their worktrees.

    Tasks that were claimed by workers that haven't sent a heartbeat
    in timeout_minutes will be reset to 'pending'.
    """
    conn = get_db()
    try:
        timeout = datetime.now() - timedelta(minutes=timeout_minutes)

        # Find timed-out workers
        cursor = conn.execute(
            """
            SELECT id, current_task_id, worktree_path, is_headless FROM workers
            WHERE last_heartbeat < ? AND status = 'working'
            """,
            (timeout.isoformat(),),
        )
        timed_out = cursor.fetchall()

        released_tasks = []
        removed_worktrees = []

        for worker in timed_out:
            if worker["current_task_id"]:
                # Release the task
                conn.execute(
                    """
                    UPDATE tasks
                    SET status = 'pending', worker_id = NULL, started_at = NULL
                    WHERE id = ? AND status IN ('claimed', 'running')
                    """,
                    (worker["current_task_id"],),
                )
                released_tasks.append(worker["current_task_id"])

                _log_event(
                    conn,
                    "task_released",
                    f"Task {worker['current_task_id']} released due to worker {worker['id']} timeout",
                    task_id=worker["current_task_id"],
                    worker_id=worker["id"],
                )

            # Mark worker offline
            conn.execute(
                "UPDATE workers SET status = 'offline', current_task_id = NULL WHERE id = ?",
                (worker["id"],),
            )

            # Remove worktree if requested and worker is headless
            if remove_worktrees and worker["worktree_path"] and worker["is_headless"]:
                if _remove_worktree(worker["worktree_path"]):
                    removed_worktrees.append(worker["worktree_path"])
                    # Also delete the worker record since worktree is gone
                    conn.execute("DELETE FROM workers WHERE id = ?", (worker["id"],))

        conn.commit()
        return {
            "success": True,
            "released_tasks": released_tasks,
            "offline_workers": [w["id"] for w in timed_out],
            "removed_worktrees": removed_worktrees,
        }
    finally:
        conn.close()


# =============================================================================
# Story Checkpoint Functions (WA-170)
# =============================================================================


def story_checkpoint(
    story_key: str,
    phase: str,
    branch: str | None = None,
    files_modified: list[str] | None = None,
    commits: list[str] | None = None,
    pr_number: int | None = None,
    test_coverage: float | None = None,
    extra_data: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Save a checkpoint for a /story phase."""
    if phase not in STORY_PHASES:
        return {
            "success": False,
            "error": f"Invalid phase: {phase}. Valid: {STORY_PHASES}",
        }

    phase_index = STORY_PHASES.index(phase)

    conn = get_db()
    try:
        conn.execute(
            """
            INSERT INTO story_checkpoints
            (story_key, phase, phase_index, branch, files_modified, commits, pr_number, test_coverage, extra_data)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                story_key,
                phase,
                phase_index,
                branch,
                json.dumps(files_modified) if files_modified else None,
                json.dumps(commits) if commits else None,
                pr_number,
                test_coverage,
                json.dumps(extra_data) if extra_data else None,
            ),
        )

        # Also update story_workflow for crash recovery (C3 fix)
        conn.execute(
            """
            INSERT INTO story_workflow (story_key, phase, branch_name, pr_number, started_at, updated_at)
            VALUES (?, ?, ?, ?, datetime('now'), datetime('now'))
            ON CONFLICT(story_key) DO UPDATE SET
                phase = excluded.phase,
                branch_name = COALESCE(excluded.branch_name, branch_name),
                pr_number = COALESCE(excluded.pr_number, pr_number),
                updated_at = datetime('now')
            """,
            (story_key, phase, branch, pr_number),
        )

        _log_event(
            conn, "story_checkpoint", f"Story {story_key} checkpointed at phase {phase}"
        )
        conn.commit()

        return {
            "success": True,
            "story_key": story_key,
            "phase": phase,
            "phase_index": phase_index,
        }
    finally:
        conn.close()


def story_resume(story_key: str) -> dict[str, Any]:
    """Get the latest checkpoint for a story to enable resume."""
    conn = get_db()
    try:
        # Get all checkpoints for this story, ordered by phase
        cursor = conn.execute(
            """
            SELECT * FROM story_checkpoints
            WHERE story_key = ?
            ORDER BY phase_index DESC, created_at DESC
            LIMIT 1
            """,
            (story_key,),
        )
        checkpoint = cursor.fetchone()

        if not checkpoint:
            return {"success": False, "error": f"No checkpoint found for {story_key}"}

        checkpoint_data = dict(checkpoint)

        # Parse JSON fields
        if checkpoint_data.get("files_modified"):
            checkpoint_data["files_modified"] = json.loads(
                checkpoint_data["files_modified"]
            )
        if checkpoint_data.get("commits"):
            checkpoint_data["commits"] = json.loads(checkpoint_data["commits"])
        if checkpoint_data.get("extra_data"):
            checkpoint_data["extra_data"] = json.loads(checkpoint_data["extra_data"])

        # Check if checkpoint is stale
        created_at = datetime.fromisoformat(checkpoint_data["created_at"])
        is_stale = datetime.now() - created_at > timedelta(hours=STALE_CHECKPOINT_HOURS)

        # Get next phase to continue from
        current_phase_index = checkpoint_data["phase_index"]
        next_phase = (
            STORY_PHASES[current_phase_index + 1]
            if current_phase_index < len(STORY_PHASES) - 1
            else None
        )

        return {
            "success": True,
            "checkpoint": checkpoint_data,
            "is_stale": is_stale,
            "stale_hours": STALE_CHECKPOINT_HOURS,
            "next_phase": next_phase,
            "completed_phases": STORY_PHASES[: current_phase_index + 1],
            "remaining_phases": STORY_PHASES[current_phase_index + 1 :],
        }
    finally:
        conn.close()


def story_list(active_only: bool = False) -> list[dict[str, Any]]:
    """List stories with their checkpoint status."""
    conn = get_db()
    try:
        query = """
            SELECT
                story_key,
                MAX(phase_index) as latest_phase_index,
                MAX(created_at) as last_checkpoint,
                COUNT(*) as checkpoint_count
            FROM story_checkpoints
            GROUP BY story_key
            ORDER BY last_checkpoint DESC
        """
        cursor = conn.execute(query)
        stories = []

        for row in cursor.fetchall():
            story = dict(row)
            story["latest_phase"] = STORY_PHASES[story["latest_phase_index"]]
            story["is_complete"] = story["latest_phase_index"] == len(STORY_PHASES) - 1

            # Check if stale
            last_cp = datetime.fromisoformat(story["last_checkpoint"])
            story["is_stale"] = datetime.now() - last_cp > timedelta(
                hours=STALE_CHECKPOINT_HOURS
            )

            if active_only and story["is_complete"]:
                continue

            stories.append(story)

        return stories
    finally:
        conn.close()


def story_clear(story_key: str, keep_latest: bool = False) -> dict[str, Any]:
    """Clear checkpoints for a story."""
    conn = get_db()
    try:
        if keep_latest:
            # Keep only the latest checkpoint per phase
            conn.execute(
                """
                DELETE FROM story_checkpoints
                WHERE story_key = ? AND id NOT IN (
                    SELECT MAX(id) FROM story_checkpoints
                    WHERE story_key = ?
                    GROUP BY phase
                )
                """,
                (story_key, story_key),
            )
        else:
            conn.execute(
                "DELETE FROM story_checkpoints WHERE story_key = ?", (story_key,)
            )

        deleted = conn.total_changes
        conn.commit()

        return {"success": True, "story_key": story_key, "deleted": deleted}
    finally:
        conn.close()


def story_status(story_key: str) -> dict[str, Any]:
    """
    Get comprehensive status for a story including:
    - Current phase (latest checkpoint)
    - All checkpoints with timestamps
    - Circuit breaker states
    - CI-fix session status
    """
    conn = get_db()
    try:
        result: dict[str, Any] = {
            "story_key": story_key,
            "current_phase": None,
            "checkpoints": [],
            "circuit_breakers": [],
            "cifix_session": None,
        }

        # Get all checkpoints for this story
        cursor = conn.execute(
            """
            SELECT phase, branch, pr_number, test_coverage,
                   files_modified, commits, extra_data, created_at
            FROM story_checkpoints
            WHERE story_key = ?
            ORDER BY created_at DESC
            """,
            (story_key,),
        )
        checkpoints = [dict(row) for row in cursor.fetchall()]
        result["checkpoints"] = checkpoints

        # Get current phase (latest checkpoint)
        if checkpoints:
            result["current_phase"] = checkpoints[0]["phase"]

        # Get circuit breaker states
        cursor = conn.execute(
            """
            SELECT phase, state, failure_count, last_error, last_failure_at, opened_at
            FROM circuit_breakers
            WHERE story_key = ?
            """,
            (story_key,),
        )
        result["circuit_breakers"] = [dict(row) for row in cursor.fetchall()]

        # Get CI-fix session
        cursor = conn.execute(
            """
            SELECT pr_number, attempt_count, state, created_at, completed_at
            FROM cifix_sessions
            WHERE story_key = ?
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (story_key,),
        )
        row = cursor.fetchone()
        if row:
            result["cifix_session"] = dict(row)

        # Determine overall status
        phases_completed = {cp["phase"] for cp in checkpoints}
        if "jira_transitioned" in phases_completed:
            result["status"] = "complete"
        elif result["current_phase"]:
            result["status"] = "in_progress"
        else:
            result["status"] = "not_started"

        # Check for blocking circuit breakers
        open_circuits = [
            cb for cb in result["circuit_breakers"] if cb["state"] == "open"
        ]
        if open_circuits:
            result["blocked"] = True
            result["blocked_by"] = [cb["phase"] for cb in open_circuits]
        else:
            result["blocked"] = False

        return result
    finally:
        conn.close()


# =============================================================================
# Circuit Breaker Functions (WA-172)
# =============================================================================


def circuit_get(story_key: str, phase: str) -> dict[str, Any] | None:
    """Get current circuit breaker state for a story/phase."""
    conn = get_db()
    try:
        cursor = conn.execute(
            """
            SELECT * FROM circuit_breakers
            WHERE story_key = ? AND phase = ?
            """,
            (story_key, phase),
        )
        row = cursor.fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def circuit_check(story_key: str, phase: str) -> dict[str, Any]:
    """
    Check if phase execution is allowed (circuit is CLOSED or HALF-OPEN after cooldown).

    Returns:
        {"allowed": True/False, "state": str, "failure_count": int, ...}
    """
    conn = get_db()
    try:
        cursor = conn.execute(
            """
            SELECT * FROM circuit_breakers
            WHERE story_key = ? AND phase = ?
            """,
            (story_key, phase),
        )
        row = cursor.fetchone()

        if not row:
            # No circuit breaker record = CLOSED, allowed
            return {
                "allowed": True,
                "state": CIRCUIT_STATE_CLOSED,
                "failure_count": 0,
                "message": "Circuit closed, proceed",
            }

        circuit = dict(row)
        state = circuit["state"]
        failure_count = circuit["failure_count"]

        if state == CIRCUIT_STATE_CLOSED:
            return {
                "allowed": True,
                "state": state,
                "failure_count": failure_count,
                "message": "Circuit closed, proceed",
            }

        if state == CIRCUIT_STATE_OPEN:
            # Check if cooldown has passed
            opened_at = (
                datetime.fromisoformat(circuit["opened_at"])
                if circuit["opened_at"]
                else None
            )
            if opened_at:
                elapsed = (datetime.now() - opened_at).total_seconds()
                cooldown = CIRCUIT_BREAKER_CONFIG["cooldown_seconds"]

                if elapsed >= cooldown:
                    # Transition to HALF-OPEN for test retry
                    conn.execute(
                        """
                        UPDATE circuit_breakers
                        SET state = ?, updated_at = ?
                        WHERE story_key = ? AND phase = ?
                        """,
                        (
                            CIRCUIT_STATE_HALF_OPEN,
                            datetime.now().isoformat(),
                            story_key,
                            phase,
                        ),
                    )
                    conn.commit()

                    _log_event(
                        conn,
                        "circuit_half_open",
                        f"Circuit for {story_key}/{phase} transitioned to HALF-OPEN after cooldown",
                    )
                    conn.commit()

                    return {
                        "allowed": True,
                        "state": CIRCUIT_STATE_HALF_OPEN,
                        "failure_count": failure_count,
                        "message": f"Cooldown passed ({int(elapsed)}s), testing recovery",
                    }
                else:
                    remaining = int(cooldown - elapsed)
                    return {
                        "allowed": False,
                        "state": state,
                        "failure_count": failure_count,
                        "remaining_cooldown": remaining,
                        "message": f"Circuit OPEN, {remaining}s remaining in cooldown",
                        "last_error": circuit.get("last_error"),
                    }

            return {
                "allowed": False,
                "state": state,
                "failure_count": failure_count,
                "message": "Circuit OPEN, blocked",
                "last_error": circuit.get("last_error"),
            }

        if state == CIRCUIT_STATE_HALF_OPEN:
            # HALF-OPEN allows one test attempt
            return {
                "allowed": True,
                "state": state,
                "failure_count": failure_count,
                "message": "Circuit HALF-OPEN, test attempt allowed",
            }

        # Unknown state, allow by default
        return {
            "allowed": True,
            "state": state,
            "failure_count": failure_count,
            "message": "Unknown state, allowing",
        }
    finally:
        conn.close()


def circuit_fail(
    story_key: str,
    phase: str,
    error_message: str | None = None,
) -> dict[str, Any]:
    """
    Record a phase failure. If max failures reached, open circuit and trigger rollback.

    Returns:
        {"circuit_opened": bool, "rollback_triggered": bool, "failure_count": int, ...}
    """
    conn = get_db()
    try:
        now = datetime.now().isoformat()
        max_failures = CIRCUIT_BREAKER_CONFIG["max_failures_per_phase"]

        # Upsert circuit breaker record
        conn.execute(
            """
            INSERT INTO circuit_breakers (story_key, phase, failure_count, last_failure_at, last_error, updated_at)
            VALUES (?, ?, 1, ?, ?, ?)
            ON CONFLICT(story_key, phase) DO UPDATE SET
                failure_count = failure_count + 1,
                last_failure_at = excluded.last_failure_at,
                last_error = excluded.last_error,
                updated_at = excluded.updated_at
            """,
            (story_key, phase, now, error_message, now),
        )
        conn.commit()

        # Get updated state
        cursor = conn.execute(
            "SELECT * FROM circuit_breakers WHERE story_key = ? AND phase = ?",
            (story_key, phase),
        )
        circuit = dict(cursor.fetchone())
        failure_count = circuit["failure_count"]
        current_state = circuit["state"]

        result: dict[str, Any] = {
            "failure_count": failure_count,
            "max_failures": max_failures,
            "circuit_opened": False,
            "rollback_triggered": False,
            "state": current_state,
        }

        # Check if we need to open circuit
        if failure_count >= max_failures and current_state != CIRCUIT_STATE_OPEN:
            # Open the circuit
            conn.execute(
                """
                UPDATE circuit_breakers
                SET state = ?, opened_at = ?, updated_at = ?
                WHERE story_key = ? AND phase = ?
                """,
                (CIRCUIT_STATE_OPEN, now, now, story_key, phase),
            )

            _log_event(
                conn,
                "circuit_opened",
                f"Circuit OPENED for {story_key}/{phase} after {failure_count} failures",
            )

            result["circuit_opened"] = True
            result["state"] = CIRCUIT_STATE_OPEN

            # Trigger auto-rollback if configured
            if CIRCUIT_BREAKER_CONFIG["auto_rollback"]:
                rollback_result = _perform_rollback(conn, story_key, phase)
                result["rollback_triggered"] = rollback_result.get("success", False)
                result["rollback_details"] = rollback_result

            conn.commit()
            result["message"] = (
                f"Circuit OPENED after {failure_count} failures. Rollback {'triggered' if result['rollback_triggered'] else 'skipped'}."
            )
        elif current_state == CIRCUIT_STATE_HALF_OPEN:
            # Failed during HALF-OPEN test, reopen circuit
            conn.execute(
                """
                UPDATE circuit_breakers
                SET state = ?, opened_at = ?, updated_at = ?
                WHERE story_key = ? AND phase = ?
                """,
                (CIRCUIT_STATE_OPEN, now, now, story_key, phase),
            )

            _log_event(
                conn,
                "circuit_reopened",
                f"Circuit REOPENED for {story_key}/{phase} - failed during HALF-OPEN test",
            )
            conn.commit()

            result["state"] = CIRCUIT_STATE_OPEN
            result["message"] = "Failed during HALF-OPEN test, circuit reopened"
        else:
            result["message"] = f"Failure {failure_count}/{max_failures} recorded"

        return result
    finally:
        conn.close()


def circuit_success(story_key: str, phase: str) -> dict[str, Any]:
    """
    Record a phase success. Resets failure count and closes circuit.

    Returns:
        {"circuit_closed": bool, "previous_state": str}
    """
    conn = get_db()
    try:
        now = datetime.now().isoformat()

        # Get current state before reset
        cursor = conn.execute(
            "SELECT state, failure_count FROM circuit_breakers WHERE story_key = ? AND phase = ?",
            (story_key, phase),
        )
        row = cursor.fetchone()

        if not row:
            return {
                "circuit_closed": False,
                "previous_state": None,
                "message": "No circuit breaker record, nothing to reset",
            }

        previous_state = row["state"]
        previous_failures = row["failure_count"]

        # Reset circuit to CLOSED with zero failures
        conn.execute(
            """
            UPDATE circuit_breakers
            SET state = ?, failure_count = 0, opened_at = NULL, updated_at = ?
            WHERE story_key = ? AND phase = ?
            """,
            (CIRCUIT_STATE_CLOSED, now, story_key, phase),
        )

        _log_event(
            conn,
            "circuit_closed",
            f"Circuit CLOSED for {story_key}/{phase} after success (was {previous_state} with {previous_failures} failures)",
        )
        conn.commit()

        return {
            "circuit_closed": True,
            "previous_state": previous_state,
            "previous_failures": previous_failures,
            "message": f"Circuit closed, reset from {previous_state}",
        }
    finally:
        conn.close()


def circuit_reset(story_key: str, phase: str | None = None) -> dict[str, Any]:
    """
    Manually reset circuit breaker(s) for a story.

    Args:
        story_key: The story to reset
        phase: Specific phase to reset, or None to reset all phases

    Returns:
        {"reset_count": int}
    """
    conn = get_db()
    try:
        if phase:
            cursor = conn.execute(
                "DELETE FROM circuit_breakers WHERE story_key = ? AND phase = ?",
                (story_key, phase),
            )
        else:
            cursor = conn.execute(
                "DELETE FROM circuit_breakers WHERE story_key = ?",
                (story_key,),
            )

        deleted = cursor.rowcount
        conn.commit()

        _log_event(
            conn,
            "circuit_reset",
            f"Circuit breaker(s) reset for {story_key}"
            + (f"/{phase}" if phase else " (all phases)"),
        )
        conn.commit()

        return {
            "success": True,
            "story_key": story_key,
            "phase": phase,
            "reset_count": deleted,
        }
    finally:
        conn.close()


def circuit_list(
    story_key: str | None = None, state: str | None = None
) -> list[dict[str, Any]]:
    """List circuit breakers with optional filters."""
    conn = get_db()
    try:
        query = "SELECT * FROM circuit_breakers WHERE 1=1"
        params: list[Any] = []

        if story_key:
            query += " AND story_key = ?"
            params.append(story_key)
        if state:
            query += " AND state = ?"
            params.append(state)

        query += " ORDER BY updated_at DESC"

        cursor = conn.execute(query, params)
        return [dict(row) for row in cursor.fetchall()]
    finally:
        conn.close()


# =============================================================================
# Auto-Refine DoR Functions (WA-173)
# =============================================================================


def dor_check(description: str) -> dict[str, Any]:
    """
    Check if a story description meets Definition of Ready (DoR) requirements.

    Checks for:
    1. User Story section (h2. User Story or ## User Story)
    2. Acceptance Criteria section (h2. Acceptance Criteria or ## Acceptance Criteria)
    3. Implementation Notes section (h2. Implementation Notes or ## Implementation Notes)

    Returns:
        {"passes": bool, "issues": list[str], "sections_found": list[str]}
    """
    issues: list[str] = []
    sections_found: list[str] = []

    if not description:
        return {
            "passes": False,
            "issues": ["No description provided"],
            "sections_found": [],
        }

    # Normalize description for checking
    desc_lower = description.lower()

    # Check for User Story section
    has_user_story = any(marker in desc_lower for marker in DOR_USER_STORY_MARKERS)
    if has_user_story:
        sections_found.append("User Story")
    else:
        issues.append("Missing User Story section")

    # Check for Acceptance Criteria section
    has_acceptance = any(marker in desc_lower for marker in DOR_ACCEPTANCE_MARKERS)
    if has_acceptance:
        sections_found.append("Acceptance Criteria")
    else:
        issues.append("Missing Acceptance Criteria section")

    # Check for Implementation Notes section
    has_impl = any(marker in desc_lower for marker in DOR_IMPLEMENTATION_MARKERS)
    if has_impl:
        sections_found.append("Implementation Notes")
    else:
        issues.append("Missing Implementation Notes section")

    return {
        "passes": len(issues) == 0,
        "issues": issues,
        "sections_found": sections_found,
    }


def dor_auto_generate(summary: str) -> dict[str, Any]:
    """
    Auto-generate missing DoR sections based on the story summary.

    This generates placeholder content that should be reviewed and refined.

    Args:
        summary: Story summary/title

    Returns:
        {"user_story": str, "acceptance_criteria": str, "implementation_notes": str, "auto_generated": bool}
    """
    # Parse summary for role/action/benefit pattern if possible
    # Common patterns: "Implement X", "Add X to Y", "Fix X in Y"
    summary_words = summary.lower()

    # Try to extract action verb
    action_verbs = [
        "implement",
        "add",
        "create",
        "fix",
        "update",
        "enable",
        "allow",
        "support",
    ]
    action = "perform the action"
    feature = summary

    for verb in action_verbs:
        if verb in summary_words:
            action = verb
            # Extract feature name (everything after the verb)
            parts = summary.lower().split(verb, 1)
            if len(parts) > 1:
                feature = parts[1].strip()
            break

    # Generate User Story
    user_story = f"""As a developer,
I want to {action} {feature},
so that the system has improved functionality."""

    # Generate basic Acceptance Criteria
    acceptance_criteria = """1. **Given** the feature is implemented
   **When** it is used
   **Then** it works as expected

2. **Given** the feature encounters an error
   **When** the error is handled
   **Then** appropriate feedback is provided

3. **Given** the feature is complete
   **When** tests are run
   **Then** all tests pass with adequate coverage"""

    # Generate Implementation Notes placeholder
    implementation_notes = """**Layers:** [Backend / Frontend / CLI / Full-Stack]
**Pattern:** [To be determined based on implementation]

### Technical Guidance
[Add specific architecture guidance here]

*⚠️ AUTO-GENERATED: This section requires manual refinement.*"""

    return {
        "user_story": user_story,
        "acceptance_criteria": acceptance_criteria,
        "implementation_notes": implementation_notes,
        "auto_generated": True,
        "summary_used": summary,
        "note": "Auto-generated content - please review and refine before implementation",
    }


def dor_build_refined_description(
    original_description: str | None,
    summary: str,
    check_result: dict[str, Any],
) -> dict[str, Any]:
    """
    Build a refined description by filling in missing DoR sections.

    Args:
        original_description: Existing description or None
        summary: Story summary for auto-generation
        check_result: Result from dor_check()

    Returns:
        {"description": str, "added_sections": list[str], "auto_refined": bool}
    """
    if check_result["passes"]:
        return {
            "description": original_description or "",
            "added_sections": [],
            "auto_refined": False,
            "message": "DoR already satisfied",
        }

    # Generate missing content
    generated = dor_auto_generate(summary)
    added_sections: list[str] = []

    # Build refined description
    sections: list[str] = []

    # Add auto-refine header
    sections.append(
        "*⚠️ AUTO-REFINED: Some sections were auto-generated and require review.*\n"
    )

    # Preserve existing content or add User Story
    if "User Story" not in check_result["sections_found"]:
        sections.append("h2. User Story\n")
        sections.append(generated["user_story"])
        sections.append("")
        added_sections.append("User Story")

    # Add original description if it exists
    if original_description:
        sections.append(original_description)
        sections.append("")

    # Add missing Acceptance Criteria
    if "Acceptance Criteria" not in check_result["sections_found"]:
        sections.append("\nh2. Acceptance Criteria\n")
        sections.append(generated["acceptance_criteria"])
        sections.append("")
        added_sections.append("Acceptance Criteria")

    # Add missing Implementation Notes
    if "Implementation Notes" not in check_result["sections_found"]:
        sections.append("\nh2. Implementation Notes\n")
        sections.append(generated["implementation_notes"])
        added_sections.append("Implementation Notes")

    refined_description = "\n".join(sections)

    return {
        "description": refined_description,
        "added_sections": added_sections,
        "auto_refined": True,
        "message": f"Added {len(added_sections)} sections: {', '.join(added_sections)}",
    }


def _perform_rollback(
    conn: sqlite3.Connection, story_key: str, phase: str
) -> dict[str, Any]:
    """
    Perform rollback to the last successful checkpoint.

    This restores:
    1. Git state (reset to checkpoint commit)
    2. SQLite checkpoint state
    """
    # Find the previous phase checkpoint to roll back to
    if phase not in STORY_PHASES:
        return {"success": False, "error": f"Invalid phase: {phase}"}

    phase_index = STORY_PHASES.index(phase)
    if phase_index == 0:
        return {"success": False, "error": "Cannot rollback from first phase"}

    # Get the previous phase's checkpoint
    previous_phase = STORY_PHASES[phase_index - 1]
    cursor = conn.execute(
        """
        SELECT * FROM story_checkpoints
        WHERE story_key = ? AND phase = ?
        ORDER BY created_at DESC
        LIMIT 1
        """,
        (story_key, previous_phase),
    )
    checkpoint = cursor.fetchone()

    if not checkpoint:
        return {
            "success": False,
            "error": f"No checkpoint found for {story_key} at phase {previous_phase}",
        }

    checkpoint_data = dict(checkpoint)
    commits = (
        json.loads(checkpoint_data["commits"]) if checkpoint_data.get("commits") else []
    )
    branch = checkpoint_data.get("branch")

    rollback_commit = commits[-1] if commits else None

    # Security: Validate commit hash format (40-char hex)
    if rollback_commit and not re.match(r"^[0-9a-f]{40}$", rollback_commit):
        return {
            "success": False,
            "error": f"Invalid commit hash format: {rollback_commit}",
        }

    # Perform git rollback if we have a commit to roll back to
    git_result: dict[str, Any] = {"performed": False}
    if rollback_commit:
        try:
            # Get the repository root
            workspace_root = Path(__file__).parent.parent.parent.resolve()

            # Check for uncommitted changes first (with timeout to prevent hangs)
            status_result = subprocess.run(
                ["git", "status", "--porcelain"],
                capture_output=True,
                text=True,
                cwd=workspace_root,
                timeout=30,
            )

            if status_result.stdout.strip():
                # Stash uncommitted changes and save reference for recovery
                stash_result = subprocess.run(
                    [
                        "git",
                        "stash",
                        "push",
                        "-u",  # Include untracked files to prevent data loss
                        "-m",
                        f"Auto-stash before rollback for {story_key}",
                    ],
                    capture_output=True,
                    text=True,
                    cwd=workspace_root,
                    timeout=30,
                )
                if stash_result.returncode == 0:
                    git_result["stashed"] = True
                    git_result["stash_ref"] = "stash@{0}"  # Save for manual recovery
                    _log_event(
                        conn,
                        "rollback_stash",
                        f"Uncommitted changes stashed as stash@{{0}} before rollback for {story_key}",
                    )

            # Reset to the checkpoint commit (with timeout)
            reset_result = subprocess.run(
                ["git", "reset", "--hard", rollback_commit],
                capture_output=True,
                text=True,
                cwd=workspace_root,
                timeout=60,
            )

            if reset_result.returncode == 0:
                git_result["performed"] = True
                git_result["commit"] = rollback_commit
                git_result["message"] = f"Reset to {rollback_commit[:8]}"
            else:
                git_result["error"] = reset_result.stderr

        except subprocess.TimeoutExpired:
            git_result["error"] = "Git operation timed out"
        except Exception as e:
            git_result["error"] = str(e)

    # Update circuit breaker with rollback info
    conn.execute(
        """
        UPDATE circuit_breakers
        SET rollback_commit = ?, updated_at = ?
        WHERE story_key = ? AND phase = ?
        """,
        (rollback_commit, datetime.now().isoformat(), story_key, phase),
    )

    _log_event(
        conn,
        "rollback_performed",
        f"Rolled back {story_key} from {phase} to {previous_phase} (commit: {rollback_commit[:8] if rollback_commit else 'N/A'})",
    )

    return {
        "success": True,
        "rolled_back_to_phase": previous_phase,
        "rolled_back_to_commit": rollback_commit,
        "branch": branch,
        "git_result": git_result,
    }


# ============================================================================
# CI-Fix Functions (WA-174)
# ============================================================================


def cifix_start(story_key: str, pr_number: int) -> dict[str, Any]:
    """
    Start a new CI-fix session for a story's PR.

    Args:
        story_key: Story/ticket key (e.g., 'WA-174')
        pr_number: GitHub PR number

    Returns:
        {"success": bool, "session_id": int, "max_attempts": int}
    """
    conn = get_db()
    try:
        # Check if session already exists
        cursor = conn.execute(
            """
            SELECT id, state, attempt_count FROM cifix_sessions
            WHERE story_key = ? AND pr_number = ?
            """,
            (story_key, pr_number),
        )
        existing = cursor.fetchone()

        if existing:
            existing_data = dict(existing)
            # Reset if in failed/blocked state for retry
            if existing_data["state"] in (CIFIX_STATE_FAILED, CIFIX_STATE_BLOCKED):
                conn.execute(
                    """
                    UPDATE cifix_sessions
                    SET state = ?, attempt_count = 0, updated_at = ?, completed_at = NULL
                    WHERE id = ?
                    """,
                    (
                        CIFIX_STATE_ACTIVE,
                        datetime.now().isoformat(),
                        existing_data["id"],
                    ),
                )
                conn.commit()
                _log_event(
                    conn,
                    "cifix_restart",
                    f"CI-fix session restarted for {story_key} PR#{pr_number}",
                )
                conn.commit()
                return {
                    "success": True,
                    "session_id": existing_data["id"],
                    "restarted": True,
                    "max_attempts": CIFIX_CONFIG["max_attempts"],
                }
            return {
                "success": True,
                "session_id": existing_data["id"],
                "already_exists": True,
                "state": existing_data["state"],
                "attempt_count": existing_data["attempt_count"],
                "max_attempts": CIFIX_CONFIG["max_attempts"],
            }

        # Create new session (atomic upsert to prevent race condition)
        cursor = conn.execute(
            """
            INSERT INTO cifix_sessions (story_key, pr_number, state, attempt_count)
            VALUES (?, ?, ?, 0)
            ON CONFLICT(story_key, pr_number) DO UPDATE SET
                state = CASE
                    WHEN state IN ('failed', 'blocked') THEN ?
                    ELSE state
                END,
                attempt_count = CASE
                    WHEN state IN ('failed', 'blocked') THEN 0
                    ELSE attempt_count
                END,
                updated_at = datetime('now')
            RETURNING id
            """,
            (story_key, pr_number, CIFIX_STATE_ACTIVE, CIFIX_STATE_ACTIVE),
        )
        result = cursor.fetchone()
        session_id = result[0] if result else cursor.lastrowid
        conn.commit()

        _log_event(
            conn,
            "cifix_started",
            f"CI-fix session started for {story_key} PR#{pr_number}",
        )
        conn.commit()

        return {
            "success": True,
            "session_id": session_id,
            "max_attempts": CIFIX_CONFIG["max_attempts"],
        }
    finally:
        conn.close()


def cifix_attempt(
    story_key: str,
    fix_type: str,
    error_message: str | None = None,
    fix_applied: str | None = None,
) -> dict[str, Any]:
    """
    Record a CI-fix attempt.

    Args:
        story_key: Story/ticket key
        fix_type: Type of fix (lint, format, type_error, test_failure, build_error)
        error_message: Error message from CI
        fix_applied: Description of fix applied

    Returns:
        {"success": bool, "attempt_number": int, "can_continue": bool, "recommendation": str}
    """
    conn = get_db()
    try:
        # Get active session
        cursor = conn.execute(
            """
            SELECT id, attempt_count, state FROM cifix_sessions
            WHERE story_key = ? AND state = ?
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (story_key, CIFIX_STATE_ACTIVE),
        )
        session = cursor.fetchone()

        if not session:
            return {
                "success": False,
                "error": f"No active CI-fix session for {story_key}",
            }

        session_data = dict(session)
        session_id = session_data["id"]
        current_attempt_count = session_data["attempt_count"]
        new_attempt_count = current_attempt_count + 1

        # Check if fix type is non-fixable
        if fix_type in CIFIX_CONFIG["non_fixable"]:
            conn.execute(
                """
                UPDATE cifix_sessions
                SET state = ?, updated_at = ?, completed_at = ?
                WHERE id = ?
                """,
                (
                    CIFIX_STATE_BLOCKED,
                    datetime.now().isoformat(),
                    datetime.now().isoformat(),
                    session_id,
                ),
            )

            # Record the blocked attempt
            conn.execute(
                """
                INSERT INTO cifix_attempts
                (session_id, attempt_number, fix_type, error_message, fix_applied, success)
                VALUES (?, ?, ?, ?, ?, FALSE)
                """,
                (
                    session_id,
                    new_attempt_count,
                    fix_type,
                    error_message,
                    "BLOCKED - Non-fixable",
                ),
            )
            conn.commit()

            _log_event(
                conn,
                "cifix_blocked",
                f"CI-fix blocked for {story_key}: non-fixable error type '{fix_type}'",
            )
            conn.commit()

            return {
                "success": True,
                "attempt_number": new_attempt_count,
                "can_continue": False,
                "state": CIFIX_STATE_BLOCKED,
                "recommendation": f"Manual intervention required: {fix_type} is not auto-fixable",
            }

        # Check if we've exceeded max attempts (check BEFORE recording - off-by-one fix)
        # When new_attempt_count > max_attempts, we've already made max_attempts attempts
        # and this call is just discovering we've exceeded the limit - don't record another attempt
        if new_attempt_count > CIFIX_CONFIG["max_attempts"]:
            conn.execute(
                """
                UPDATE cifix_sessions
                SET state = ?, updated_at = ?, completed_at = ?
                WHERE id = ?
                """,
                (
                    CIFIX_STATE_FAILED,
                    datetime.now().isoformat(),
                    datetime.now().isoformat(),
                    session_id,
                ),
            )
            conn.commit()

            _log_event(
                conn,
                "cifix_failed",
                f"CI-fix failed for {story_key}: exceeded {CIFIX_CONFIG['max_attempts']} attempts",
            )
            conn.commit()

            return {
                "success": True,
                "attempt_number": new_attempt_count,
                "can_continue": False,
                "state": CIFIX_STATE_FAILED,
                "recommendation": "Max attempts exceeded. Manual intervention required.",
            }

        # Record the attempt
        conn.execute(
            """
            INSERT INTO cifix_attempts
            (session_id, attempt_number, fix_type, error_message, fix_applied, success)
            VALUES (?, ?, ?, ?, ?, FALSE)
            """,
            (session_id, new_attempt_count, fix_type, error_message, fix_applied),
        )

        # Update session with optimistic locking to prevent race conditions
        cursor = conn.execute(
            """
            UPDATE cifix_sessions
            SET attempt_count = ?, updated_at = ?
            WHERE id = ? AND attempt_count = ?
            """,
            (
                new_attempt_count,
                datetime.now().isoformat(),
                session_id,
                current_attempt_count,
            ),
        )

        if cursor.rowcount == 0:
            conn.rollback()
            return {
                "success": False,
                "error": "Concurrent modification detected. Please retry.",
            }

        conn.commit()

        _log_event(
            conn,
            "cifix_attempt",
            f"CI-fix attempt {new_attempt_count}/{CIFIX_CONFIG['max_attempts']} for {story_key}: {fix_type}",
        )
        conn.commit()

        # Get fix recommendation
        fix_config = CIFIX_CONFIG["auto_fixable"].get(fix_type, {})
        command = fix_config.get("command")
        success_rate = fix_config.get("success_rate", 0)

        recommendation = ""
        if command:
            recommendation = f"Run: {command} (success rate: {success_rate:.0%})"
        else:
            recommendation = (
                f"Analyze and fix manually (success rate: {success_rate:.0%})"
            )

        return {
            "success": True,
            "attempt_number": new_attempt_count,
            "attempts_remaining": CIFIX_CONFIG["max_attempts"] - new_attempt_count,
            "can_continue": True,
            "fix_type": fix_type,
            "recommendation": recommendation,
            "auto_command": command,
        }
    finally:
        conn.close()


def cifix_success(story_key: str) -> dict[str, Any]:
    """
    Mark CI as passing for a story.

    Args:
        story_key: Story/ticket key

    Returns:
        {"success": bool, "total_attempts": int}
    """
    conn = get_db()
    try:
        # Get active session
        cursor = conn.execute(
            """
            SELECT id, attempt_count FROM cifix_sessions
            WHERE story_key = ? AND state = ?
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (story_key, CIFIX_STATE_ACTIVE),
        )
        session = cursor.fetchone()

        if not session:
            return {
                "success": False,
                "error": f"No active CI-fix session for {story_key}",
            }

        session_data = dict(session)
        session_id = session_data["id"]

        # Update session to success
        conn.execute(
            """
            UPDATE cifix_sessions
            SET state = ?, updated_at = ?, completed_at = ?
            WHERE id = ?
            """,
            (
                CIFIX_STATE_SUCCESS,
                datetime.now().isoformat(),
                datetime.now().isoformat(),
                session_id,
            ),
        )
        conn.commit()

        _log_event(
            conn,
            "cifix_success",
            f"CI passed for {story_key} after {session_data['attempt_count']} attempt(s)",
        )
        conn.commit()

        return {
            "success": True,
            "state": CIFIX_STATE_SUCCESS,
            "total_attempts": session_data["attempt_count"],
        }
    finally:
        conn.close()


def cifix_status(story_key: str) -> dict[str, Any]:
    """
    Get current CI-fix status for a story.

    Args:
        story_key: Story/ticket key

    Returns:
        {"session": {...}, "attempts": [...], "can_continue": bool}
    """
    conn = get_db()
    try:
        # Get latest session
        cursor = conn.execute(
            """
            SELECT * FROM cifix_sessions
            WHERE story_key = ?
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (story_key,),
        )
        session = cursor.fetchone()

        if not session:
            return {
                "success": False,
                "error": f"No CI-fix session found for {story_key}",
            }

        session_data = dict(session)

        # Get attempts
        cursor = conn.execute(
            """
            SELECT * FROM cifix_attempts
            WHERE session_id = ?
            ORDER BY attempt_number ASC
            """,
            (session_data["id"],),
        )
        attempts = [dict(row) for row in cursor.fetchall()]

        can_continue = (
            session_data["state"] == CIFIX_STATE_ACTIVE
            and session_data["attempt_count"] < CIFIX_CONFIG["max_attempts"]
        )

        return {
            "success": True,
            "session": session_data,
            "attempts": attempts,
            "can_continue": can_continue,
            "attempts_remaining": max(
                0, CIFIX_CONFIG["max_attempts"] - session_data["attempt_count"]
            ),
        }
    finally:
        conn.close()


def cifix_reset(story_key: str) -> dict[str, Any]:
    """
    Reset CI-fix tracking for a story.

    Args:
        story_key: Story/ticket key

    Returns:
        {"success": bool, "sessions_reset": int}
    """
    conn = get_db()
    try:
        # Get sessions to reset
        cursor = conn.execute(
            """
            SELECT id FROM cifix_sessions
            WHERE story_key = ?
            """,
            (story_key,),
        )
        sessions = cursor.fetchall()

        if not sessions:
            return {
                "success": True,
                "sessions_reset": 0,
                "message": f"No CI-fix sessions found for {story_key}",
            }

        # Delete attempts first (foreign key)
        for session in sessions:
            conn.execute(
                "DELETE FROM cifix_attempts WHERE session_id = ?",
                (session["id"],),
            )

        # Delete sessions
        cursor = conn.execute(
            "DELETE FROM cifix_sessions WHERE story_key = ?",
            (story_key,),
        )
        count = cursor.rowcount
        conn.commit()

        _log_event(
            conn,
            "cifix_reset",
            f"CI-fix sessions reset for {story_key}: {count} deleted",
        )
        conn.commit()

        return {
            "success": True,
            "sessions_reset": count,
        }
    finally:
        conn.close()


def cifix_list(
    story_key: str | None = None, active_only: bool = False
) -> dict[str, Any]:
    """
    List CI-fix sessions.

    Args:
        story_key: Optional filter by story key
        active_only: Only show active sessions

    Returns:
        {"sessions": [...], "count": int}
    """
    conn = get_db()
    try:
        query = "SELECT * FROM cifix_sessions WHERE 1=1"
        params: list[Any] = []

        if story_key:
            query += " AND story_key = ?"
            params.append(story_key)

        if active_only:
            query += " AND state = ?"
            params.append(CIFIX_STATE_ACTIVE)

        query += " ORDER BY created_at DESC"

        cursor = conn.execute(query, params)
        sessions = [dict(row) for row in cursor.fetchall()]

        return {
            "success": True,
            "sessions": sessions,
            "count": len(sessions),
        }
    finally:
        conn.close()


def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(description="SQLite Orchestration CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # init command
    subparsers.add_parser("init", help="Initialize database")

    # cleanup command
    cleanup_parser = subparsers.add_parser("cleanup", help="Release stale tasks")
    cleanup_parser.add_argument("--timeout", type=int, default=DEFAULT_WORKER_TIMEOUT)
    cleanup_parser.add_argument(
        "--remove-worktrees",
        action="store_true",
        help="Remove worktrees of stale headless workers",
    )

    # task commands
    task_parser = subparsers.add_parser("task", help="Task operations")
    task_sub = task_parser.add_subparsers(dest="action", required=True)

    task_create_p = task_sub.add_parser("create")
    task_create_p.add_argument("story_key")
    task_create_p.add_argument("description")
    task_create_p.add_argument("--phase")
    task_create_p.add_argument("--deps", help="Comma-separated task IDs")
    task_create_p.add_argument("--id", dest="task_id", help="Custom task ID")

    task_list_p = task_sub.add_parser("list")
    task_list_p.add_argument("--status")
    task_list_p.add_argument("--story")

    task_get_p = task_sub.add_parser("get")
    task_get_p.add_argument("task_id")

    task_claim_p = task_sub.add_parser("claim")
    task_claim_p.add_argument("task_id")
    task_claim_p.add_argument("worker_id")

    task_update_p = task_sub.add_parser("update")
    task_update_p.add_argument("task_id")
    task_update_p.add_argument("--status")
    task_update_p.add_argument("--result")
    task_update_p.add_argument("--phase")

    # worker commands (extended for WA-176)
    worker_parser = subparsers.add_parser("worker", help="Worker operations")
    worker_sub = worker_parser.add_subparsers(dest="action", required=True)

    worker_reg_p = worker_sub.add_parser("register")
    worker_reg_p.add_argument("worker_id")
    worker_reg_p.add_argument("--terminal")
    worker_reg_p.add_argument("--worktree", help="Path to git worktree")
    worker_reg_p.add_argument(
        "--headless", action="store_true", help="Mark as headless instance"
    )

    worker_unreg_p = worker_sub.add_parser("unregister")
    worker_unreg_p.add_argument("worker_id")
    worker_unreg_p.add_argument(
        "--cleanup-worktree", action="store_true", help="Remove git worktree"
    )

    worker_hb_p = worker_sub.add_parser("heartbeat")
    worker_hb_p.add_argument("worker_id")

    worker_list_p = worker_sub.add_parser("list")
    worker_list_p.add_argument("--active", action="store_true")
    worker_list_p.add_argument("--headless-only", action="store_true")

    worker_sub.add_parser("status", help="Get detailed worker status")

    worker_cleanup_p = worker_sub.add_parser("cleanup")
    worker_cleanup_p.add_argument("--timeout", type=int, default=DEFAULT_WORKER_TIMEOUT)
    worker_cleanup_p.add_argument("--remove-worktrees", action="store_true")

    # checkpoint commands
    cp_parser = subparsers.add_parser("checkpoint", help="Checkpoint operations")
    cp_sub = cp_parser.add_subparsers(dest="action", required=True)

    cp_save_p = cp_sub.add_parser("save")
    cp_save_p.add_argument("task_id")
    cp_save_p.add_argument("phase")
    cp_save_p.add_argument("state_json")

    cp_load_p = cp_sub.add_parser("load")
    cp_load_p.add_argument("task_id")
    cp_load_p.add_argument("--phase")

    # story commands (WA-170)
    story_parser = subparsers.add_parser("story", help="Story checkpoint operations")
    story_sub = story_parser.add_subparsers(dest="action", required=True)

    story_cp_p = story_sub.add_parser("checkpoint")
    story_cp_p.add_argument("story_key")
    story_cp_p.add_argument("phase", choices=STORY_PHASES)
    story_cp_p.add_argument("--branch", help="Git branch name")
    story_cp_p.add_argument("--files", help="JSON array of modified files")
    story_cp_p.add_argument("--commits", help="JSON array of commit hashes")
    story_cp_p.add_argument("--pr", type=int, help="PR number")
    story_cp_p.add_argument("--coverage", type=float, help="Test coverage percentage")
    story_cp_p.add_argument("--extra", help="JSON object with extra data")

    story_resume_p = story_sub.add_parser("resume")
    story_resume_p.add_argument("story_key")

    story_list_p = story_sub.add_parser("list")
    story_list_p.add_argument(
        "--active", action="store_true", help="Only show incomplete stories"
    )

    story_clear_p = story_sub.add_parser("clear")
    story_clear_p.add_argument("story_key")
    story_clear_p.add_argument(
        "--keep-latest", action="store_true", help="Keep latest checkpoint per phase"
    )

    story_status_p = story_sub.add_parser(
        "status", help="Get comprehensive story status"
    )
    story_status_p.add_argument("story_key")

    story_sub.add_parser("phases", help="List valid story phases")

    # circuit breaker commands (WA-172)
    circuit_parser = subparsers.add_parser("circuit", help="Circuit breaker operations")
    circuit_sub = circuit_parser.add_subparsers(dest="action", required=True)

    circuit_check_p = circuit_sub.add_parser("check", help="Check if phase is allowed")
    circuit_check_p.add_argument("story_key")
    circuit_check_p.add_argument("phase", choices=STORY_PHASES)

    circuit_fail_p = circuit_sub.add_parser("fail", help="Record a phase failure")
    circuit_fail_p.add_argument("story_key")
    circuit_fail_p.add_argument("phase", choices=STORY_PHASES)
    circuit_fail_p.add_argument("--error", help="Error message")

    circuit_success_p = circuit_sub.add_parser("success", help="Record phase success")
    circuit_success_p.add_argument("story_key")
    circuit_success_p.add_argument("phase", choices=STORY_PHASES)

    circuit_reset_p = circuit_sub.add_parser("reset", help="Reset circuit breaker(s)")
    circuit_reset_p.add_argument("story_key")
    circuit_reset_p.add_argument(
        "--phase", choices=STORY_PHASES, help="Specific phase to reset"
    )

    circuit_list_p = circuit_sub.add_parser("list", help="List circuit breakers")
    circuit_list_p.add_argument("--story", help="Filter by story key")
    circuit_list_p.add_argument("--state", choices=["closed", "open", "half_open"])

    circuit_get_p = circuit_sub.add_parser("get", help="Get circuit breaker state")
    circuit_get_p.add_argument("story_key")
    circuit_get_p.add_argument("phase", choices=STORY_PHASES)

    circuit_sub.add_parser("config", help="Show circuit breaker configuration")

    # dor commands (WA-173)
    dor_parser = subparsers.add_parser("dor", help="Definition of Ready operations")
    dor_sub = dor_parser.add_subparsers(dest="action", required=True)

    dor_check_p = dor_sub.add_parser("check", help="Check if description meets DoR")
    dor_check_p.add_argument("description", help="Story description to check")

    dor_generate_p = dor_sub.add_parser(
        "generate", help="Generate DoR sections from summary"
    )
    dor_generate_p.add_argument("summary", help="Story summary")
    dor_generate_p.add_argument("--description", help="Existing description (optional)")

    dor_refine_p = dor_sub.add_parser(
        "refine", help="Build refined description with missing sections"
    )
    dor_refine_p.add_argument("summary", help="Story summary")
    dor_refine_p.add_argument("--description", help="Existing description (optional)")

    # cifix commands (WA-174)
    cifix_parser = subparsers.add_parser("cifix", help="CI-Fix Loop operations")
    cifix_sub = cifix_parser.add_subparsers(dest="action", required=True)

    cifix_start_p = cifix_sub.add_parser("start", help="Start CI-fix tracking for a PR")
    cifix_start_p.add_argument("story_key", help="Story/ticket key (e.g., PROJ-123)")
    cifix_start_p.add_argument("pr_number", type=int, help="GitHub PR number")

    cifix_attempt_p = cifix_sub.add_parser("attempt", help="Record a fix attempt")
    cifix_attempt_p.add_argument("story_key", help="Story/ticket key")
    cifix_attempt_p.add_argument(
        "fix_type",
        choices=["lint", "format", "type_error", "test_failure", "build_error"]
        + list(CIFIX_CONFIG["non_fixable"]),
        help="Type of fix being attempted",
    )
    cifix_attempt_p.add_argument("--error", help="Error message from CI")
    cifix_attempt_p.add_argument(
        "--fix", dest="fix_applied", help="Description of fix applied"
    )

    cifix_success_p = cifix_sub.add_parser("success", help="Mark CI as passing")
    cifix_success_p.add_argument("story_key", help="Story/ticket key")

    cifix_status_p = cifix_sub.add_parser("status", help="Get current CI-fix status")
    cifix_status_p.add_argument("story_key", help="Story/ticket key")

    cifix_reset_p = cifix_sub.add_parser("reset", help="Reset CI-fix tracking")
    cifix_reset_p.add_argument("story_key", help="Story/ticket key")

    cifix_list_p = cifix_sub.add_parser("list", help="List CI-fix sessions")
    cifix_list_p.add_argument("--story", help="Filter by story key")
    cifix_list_p.add_argument(
        "--active", action="store_true", help="Only show active sessions"
    )

    cifix_sub.add_parser("config", help="Show CI-fix configuration")

    # event commands
    event_parser = subparsers.add_parser("event", help="Event operations")
    event_sub = event_parser.add_subparsers(dest="action", required=True)

    event_log_p = event_sub.add_parser("log")
    event_log_p.add_argument("event_type")
    event_log_p.add_argument("message")
    event_log_p.add_argument("--task")
    event_log_p.add_argument("--worker")

    event_list_p = event_sub.add_parser("list")
    event_list_p.add_argument("--task")
    event_list_p.add_argument("--limit", type=int, default=50)

    args = parser.parse_args()

    # Execute command
    result: Any = None

    if args.command == "init":
        init_db()
        return

    if args.command == "cleanup":
        result = cleanup(args.timeout, args.remove_worktrees)

    elif args.command == "task":
        if args.action == "create":
            deps = args.deps.split(",") if args.deps else None
            result = task_create(
                args.story_key, args.description, args.phase, deps, args.task_id
            )
        elif args.action == "list":
            result = task_list(args.status, args.story)
        elif args.action == "get":
            result = task_get(args.task_id)
        elif args.action == "claim":
            result = task_claim(args.task_id, args.worker_id)
        elif args.action == "update":
            result = task_update(args.task_id, args.status, args.result, args.phase)

    elif args.command == "worker":
        if args.action == "register":
            result = worker_register(
                args.worker_id, args.terminal, args.worktree, args.headless
            )
        elif args.action == "unregister":
            result = worker_unregister(args.worker_id, args.cleanup_worktree)
        elif args.action == "heartbeat":
            result = worker_heartbeat(args.worker_id)
        elif args.action == "list":
            result = worker_list(args.active, args.headless_only)
        elif args.action == "status":
            result = worker_status()
        elif args.action == "cleanup":
            result = cleanup(args.timeout, args.remove_worktrees)

    elif args.command == "checkpoint":
        if args.action == "save":
            result = checkpoint_save(args.task_id, args.phase, args.state_json)
        elif args.action == "load":
            result = checkpoint_load(args.task_id, args.phase)

    elif args.command == "story":
        if args.action == "checkpoint":
            files = json.loads(args.files) if args.files else None
            commits = json.loads(args.commits) if args.commits else None
            extra = json.loads(args.extra) if args.extra else None
            result = story_checkpoint(
                args.story_key,
                args.phase,
                args.branch,
                files,
                commits,
                args.pr,
                args.coverage,
                extra,
            )
        elif args.action == "resume":
            result = story_resume(args.story_key)
        elif args.action == "list":
            result = story_list(args.active)
        elif args.action == "clear":
            result = story_clear(args.story_key, args.keep_latest)
        elif args.action == "status":
            result = story_status(args.story_key)
        elif args.action == "phases":
            result = {"phases": STORY_PHASES, "count": len(STORY_PHASES)}

    elif args.command == "circuit":
        if args.action == "check":
            result = circuit_check(args.story_key, args.phase)
        elif args.action == "fail":
            result = circuit_fail(args.story_key, args.phase, args.error)
        elif args.action == "success":
            result = circuit_success(args.story_key, args.phase)
        elif args.action == "reset":
            result = circuit_reset(args.story_key, args.phase)
        elif args.action == "list":
            result = circuit_list(args.story, args.state)
        elif args.action == "get":
            result = circuit_get(args.story_key, args.phase)
        elif args.action == "config":
            result = {
                "config": CIRCUIT_BREAKER_CONFIG,
                "states": {
                    "CLOSED": CIRCUIT_STATE_CLOSED,
                    "OPEN": CIRCUIT_STATE_OPEN,
                    "HALF_OPEN": CIRCUIT_STATE_HALF_OPEN,
                },
            }

    elif args.command == "dor":
        if args.action == "check":
            result = dor_check(args.description)
        elif args.action == "generate":
            result = dor_auto_generate(args.summary)
        elif args.action == "refine":
            check_result = dor_check(args.description or "")
            result = dor_build_refined_description(
                args.description, args.summary, check_result
            )

    elif args.command == "cifix":
        if args.action == "start":
            result = cifix_start(args.story_key, args.pr_number)
        elif args.action == "attempt":
            result = cifix_attempt(
                args.story_key, args.fix_type, args.error, args.fix_applied
            )
        elif args.action == "success":
            result = cifix_success(args.story_key)
        elif args.action == "status":
            result = cifix_status(args.story_key)
        elif args.action == "reset":
            result = cifix_reset(args.story_key)
        elif args.action == "list":
            result = cifix_list(args.story, args.active)
        elif args.action == "config":
            result = {
                "config": CIFIX_CONFIG,
                "states": {
                    "ACTIVE": CIFIX_STATE_ACTIVE,
                    "SUCCESS": CIFIX_STATE_SUCCESS,
                    "FAILED": CIFIX_STATE_FAILED,
                    "BLOCKED": CIFIX_STATE_BLOCKED,
                },
            }

    elif args.command == "event":
        if args.action == "log":
            result = event_log(args.event_type, args.message, args.task, args.worker)
        elif args.action == "list":
            result = event_list(args.task, args.limit)

    # Output JSON result
    print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()
