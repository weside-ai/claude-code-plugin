# Orchestration System

**SQLite-based checkpoint and coordination system for the /we:story pipeline.**

---

## CLI Reference

All orchestration commands use the plugin's bundled script:

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/orchestration.py <command> <args>
```

**Never access the .db file directly. Never use sqlite3 commands. Always use the CLI.**

---

## Story Checkpoints

Track progress through the development pipeline. Enable resume after interruption.

```bash
# Save checkpoint
story checkpoint {TICKET} {phase}

# Check current status
story status {TICKET}

# Resume from last checkpoint
story resume {TICKET}

# List all tracked stories
story list [--active]
```

### Checkpoint Phases

| Phase | Written By | After |
|---|---|---|
| `refined` | /we:refine | Story + Plan created |
| `git_prepared` | /we:develop | Branch created, story loaded |
| `implementation_complete` | /we:develop | Code committed |
| `ac_verified` | /we:story | All ACs verified with evidence |
| `simplified` | /we:story | Code simplified |
| `review_passed` | /we:review | Code review passed |
| `static_analysis_passed` | /we:static | Lint/format/types passed |
| `test_passed` | /we:test | Tests + coverage passed |
| `pr_created` | /we:pr | PR created on GitHub |
| `ci_passed` | /we:story | CI/Reviews green |

---

## Circuit Breaker

Prevents infinite failure loops. After 3 failures in the same phase, the circuit opens and blocks further attempts.

```bash
# Check if phase is allowed
circuit check {TICKET} {phase}

# Record failure
circuit fail {TICKET} {phase} --error "description"

# Record success (resets counter)
circuit success {TICKET} {phase}

# Manual reset
circuit reset {TICKET} [--phase {phase}]
```

**Configuration:** Max 3 failures per phase. After circuit opens → stop and ask the user.

---

## CI-Fix Loop

Track CI fix attempts for a PR. Max 3 cycles.

```bash
# Start tracking
cifix start {TICKET} {pr_number}

# Record fix attempt
cifix attempt {TICKET} {fix_type} [--error "msg"] [--fix "what was fixed"]

# Mark CI as passing
cifix success {TICKET}

# Check status
cifix status {TICKET}
```

---

## Database Location

`~/.claude/we/orchestration.db` — Shared across worktrees via home directory.

## Initialize

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/orchestration.py init
```

Run this on first use or after schema changes.
