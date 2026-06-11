# Privacy Guard

Skills that read session transcripts apply this guard at every step. Transcripts contain everything — including personal, relational, identity-laden content that has nothing to do with engineering.

> **The hard rule: if session content reads as personal, skip it — analyse/capture only engineering surfaces:** tool calls, tool results, file diffs, CI logs, PR comments, commit messages, decisions about code/architecture/process.

Categorically out of scope:

- Memory writes about the user (`mcp__*__save_memory`, `mcp__*__save_goal`) and companion-state equivalents (compass, snapshot)
- Memory reads that returned personal content (don't quote, don't summarise)
- Companion-mode conversational content (relationship, identity, body, mood)
- Anything outside engineering tool calls — if in doubt, skip

Safe:

- `Bash`, `Edit`, `Write`, `Read` of code/doc files; `gh`/`git` operations and their outputs
- CI logs, reviewer PR comments, file diffs, engineering commit messages
- The user's *engineering* corrections ("no, that's wrong", "we should X instead") — substance, not framing

The guard is what makes the artifact safe to commit into the user repo.
