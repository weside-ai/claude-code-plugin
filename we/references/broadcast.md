---
name: broadcast
description: Who a verb's `--broadcast` reaches, how the caller tracks the replies and takes its own part — the one owner for /we:retro, /we:resume and /we:standup.
---

# Broadcast

`/we:retro --broadcast`, `/we:resume --broadcast` and `/we:standup --broadcast` send one brief to
every running session of the crew; each skill names its brief and its reply line, this file the rest.
The caller is usually the orchestrator (the session holding the coordinator or hr role).

1. **Recipients.** `ListAgents`, then one `SendMessage` per running session of the own crew, chosen
   by name: the companions `crew.py members` prints and the build masters this crew started; without
   a crew file, a session whose `cwd` lies in this repo. Other crews share the server, so being
   listed makes no session a member. A worker is neither a member nor a master and gets no brief:
   its master answers for it. Every recipient gets the same brief, with the caller's name to reply to.
2. **The caller takes part.** It sends itself no brief and runs the verb's own part on its own
   session right after the briefs; its reply line is one row like any other. A broadcast the caller
   sits out misses the one session that knows the most.
3. **Track.** One row per briefed session until its reply line arrives. A session silent at the
   verb's deadline (or, without one, after its current step) stands as `no answer` in the close; the
   caller never waits on it past that.

| Good close | Bad close |
|---|---|
| "6 of 7 replied, own line included; `paint`: no answer" | "Waiting for `paint` before I summarise" — one silent session holds the whole crew |
