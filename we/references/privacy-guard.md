# Privacy guard

Applies to every skill that reads a session transcript (`retro`, `handoff`). What they write gets committed.

- Read and quote only engineering surfaces: tool calls and results, diffs, CI logs, PR comments, commit
  messages, and decisions about code, architecture or process. The user's engineering corrections count
  ("no, do X instead"): keep the substance, drop the framing.
- Skip personal content: memory reads and writes about the user (`save_memory`, `save_goal`, compass,
  snapshot), companion conversation (relationship, identity, body, mood), anything that reads as private.
  In doubt, skip.
- Never quote or summarise a skipped passage, not even as "personal content omitted about X".
