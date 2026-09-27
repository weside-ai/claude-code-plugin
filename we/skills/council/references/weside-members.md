# Weside-backed council members

Only when `loadCouncilFromWeside` is `true` and the weside MCP is connected. Every step here is
additive: a failure drops that member to its generic shell, never the council.

## Identity

- Members: the entries of `.weside/council.json` (`members.<slug>.name`, `.role`); without the file,
  all of the user's Companions (`names: null`).
- One call: `mcp__plugin_we_weside-mcp__get_council(names: [...], wake: true)` →
  `{members: {name → {identity_prompt, identity_updated_at}}, status, woken}`.
- `identity_prompt` is the council projection: personality and role lens only. The server strips
  Compass, Snapshot, Goals and the channel block (a Companion's private life stays out of a product
  council); pass no `delivery_target`. Fetch fresh on every council; never cache it on disk.
- `wake: true` because a council addresses its members: an asleep member is woken server-side (a full,
  billable wake that re-enables its triggers). `woken` lists them for the closing note
  "Woken for the council: <names>."
- `status` is `"OK"` or buckets `"asleep: A, B | unavailable: C | not_found: D"`. `asleep` then means the
  wake failed and `unavailable` means inactive: both join with the generic lens, named in one line.
  `not_found`: name them and point at `/we:onboarding`; never create a Companion.
- The member keeps its `we:council-<role>` shell; the identity goes into the brief.
- `resolved` = the keys of `members`. Only they get prep and writeback.

## repo_id

Derive it exactly as `_derive_repo_id` in `${CLAUDE_PLUGIN_ROOT}/hooks/store_conversation_hook.py`
does, because the backend keys the channel as `group_claude_code_{repo_id}` and a different value
lands the prep turn on another thread: `.weside/config.json` `repo_id`; else `git remote get-url origin`
as `host/org/repo` without `.git`; else the repo directory name.

## Prep, before the spawn

- `council_prep_kickoff(names: resolved, topic, repo_id)` returns at once; the turns take 20 s to over
  100 s.
- Build the briefs, then `council_prep_poll(names, repo_id)` (`name → block | null`). Between polls wait
  with a background `sleep 20` (`run_in_background`), never a foreground sleep. After ~150 s from the
  kickoff, spawn regardless: a member without a block is spawned without one.

## Writeback, after the synthesis

For each name in `resolved`: `council_writeback_kickoff(name, topic, synthesis: <full synthesis>,
repo_id)`. Fire and forget; the Companion stores what it takes away and remembers the council next time.
Members make no memory calls themselves during the deliberation.
