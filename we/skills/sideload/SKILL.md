---
name: sideload
description: >
  Work in a neighbour repo from here: reading via --add-dir, editing via a background session in
  that repo steered with SendMessage. Triggers: "/we:sideload", "load context for", "cross-repo".
---

# /we:sideload <repo>

A basename resolves against the sibling directories of this repo; a path is used as-is. Pick the
mode by what the task does in the other repo.

**Reading only** (answer a question, compare code): the other repo's instructions must load as
instructions, not as a file dump. Start the session with
`CLAUDE_CODE_ADDITIONAL_DIRECTORIES_CLAUDE_MD=1 claude --add-dir <repo>`. Measured (2.1.283,
27.09.2026): this loads the repo's `CLAUDE.md` and `.claude/rules/`, but not its `AGENTS.md`, so
`Read <repo>/AGENTS.md` yourself when the repo has one. Without the variable, `--add-dir` grants
file access only. Mid-session, when no restart is possible: `Read` the instruction file and the
rules the task touches.

**Editing** (a change lands in the other repo): never edit it from this session, because its
path-bound rules, hooks and worktree conventions do not apply here. Start a native session there:
`cd <repo> && claude --bg "<task, with the context a human would give>"`. It prints an id;
`claude agents` lists it. Steer it with `SendMessage` to its name from `ListAgents`, and pass
`notify_when_idle: true` to hear when it finishes instead of polling. A session in a different
permission mode holds cross-session messages for its user's approval, so a send is not proof it
read the message. The other session commits, pushes and reports under its own repo's rules.
