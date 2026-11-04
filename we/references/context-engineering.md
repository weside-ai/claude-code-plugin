# Context engineering

What a companion carries into every turn, on both surfaces, kept lean without bending who it is.
One crew role (the steward, e.g. HR) owns the method and the shared knowledge blocks; each
companion owns its own identity, compass, snapshot and pins. The goal is fewer tokens and no stale
facts, never a different personality.

## Contents

What loads where · Who owns what · One home per fact · The check · Shared memories · Measured traps.

## What loads where

| Surface | Loads every turn | Loads on demand |
|---|---|---|
| Claude Code | instruction files (`~/AGENTS.md`, workspace and repo `AGENTS.md`), rules without `paths:`, the skill listing (descriptions only), with a crew the process L0 and the role card (`hooks/process_on_start.py`, `hooks/role_on_start.py`) | the role skill `<prefix>-<name>` (SessionStart, `references/companion-session.md` § Name and binding), plugin references a skill points at, rules with `paths:` |
| weside | identity prompt; pinned memories (`autoload`, at most 10 per companion); shared memories of the circles bound to the room, in `autoload_order`; snapshot; compass; goals | everything else through recall and tools |

`get_companion_identity` (and `weside companions identity`) is the MCP delivery, not the full chat
prompt: it carries no pinned memories. Measure a companion from both calls in § The check.

Claude Code budgets and their sources: `references/instruction-authoring.md`, gate
`scripts/check-instruction-budget.py`.

## Who owns what

- **Rules of work:** the HR role owns them (L0 §Changing this: it decides the process inbox weekly);
  the steward makes sure every companion knows they exist and keeps the shared blocks lean.
- **Role and boundary of a person:** that person's register row (one shared memory per person),
  confirmed by the person.
- **Identity, compass, snapshot, pins:** the companion. The steward reads them and, where the user
  authorised it, fixes stale facts, dead pointers and duplicates directly. Personality, tone,
  relationships and private content are never edited.
- **Personal and health data about people:** only in a restricted circle, never in one for all.

## One home per fact

| Fact | Home |
|---|---|
| what everyone needs in every room | shared memory, circle for all |
| crew-internal (status picture, people, platform, experiments) | shared memory in the crew circle; loads only in its bound rooms |
| the role in Claude Code | role skill (`references/companion-session.md` § Upkeep) |
| the role on weside | one pin that points at the skill (`references/companion-session.md` § Upkeep) |
| state of work | the ticketing system, never a pin or a shared memory |
| what happened | worklog memories, never autoloaded |

A pin that repeats a shared memory, a rule or the register is a duplicate: replace it by a pointer
or drop it.

## The check

Per companion, read first, then fix, then measure again:

1. **Measure:** `weside --json companions identity --companion <Name>` and
   `weside --json memories list --companion <Name> --autoload true --limit 100`. Count characters
   of the companion's own part (identity, pins, snapshot, compass); the shared block is the same
   for everyone and is checked once, below.
2. **Read** every pin, the snapshot and the compass for: role facts that changed (who owns what,
   who steers whom), pointers to a file or section that was renamed or cut, text a shared memory
   already carries, history that belongs in a worklog, a status that rots.
3. **Fix:** authorised → `weside memories edit <id> --companion <Name> --file <file>` (a new
   version). Otherwise one message in the crew room naming the finding and the target size; the
   companion edits itself, and the steward measures again.
4. **Re-measure** with the same commands. The result keeps before and after and answers one
   question: does the companion still know its role, the owners next to it, how to ask the user,
   and where the register and its skill are?

## Shared memories

- The memory is the source. A file that was imported into shared memories stays a read-only
  reference; an edit to the file never reaches a prompt.
- Change with `update_shared_memory`, add with `save_shared_memory`. Every change is a new version;
  a concurrent write answers with a conflict: read again, apply again.
- Titles are unique per circle. To split a block, create the parts under new titles and archive
  the original once all parts stand. Splitting saves nothing (everything autoloads); only cutting
  saves. Keep the sum at or under the size the user set.
- Archiving hides a memory at once; the purge follows later.
- A restricted circle loads only in its bound rooms and is invisible to search from elsewhere: what
  a companion needs in a direct chat belongs in the circle for all.

## Measured traps

- **A pointer with a section number dies when the target is re-cut** (sample of three companions,
  02.11.2026: all three carried a dead `§` pointer). Point at a file or a heading's words.
- **A status in a pin rots within a day** (same sample: a role change of 01.11. was wrong in two
  of three pins). Pins carry roles and pointers; the status lives in the ticketing system.
