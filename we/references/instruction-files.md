---
name: instruction-files
description: Which file carries a repo's always-loaded instructions, and how a skill resolves the name.
---

# Instruction files

A directory's project instructions live in **`AGENTS.md`**, or in `CLAUDE.md` where a repo has
not moved yet. Claude Code reads AGENTS.md since 2.1.277; Codex, Gemini and the other agents
read it too. CLAUDE.md keeps working and stays the Claude-only name.

## Resolving the name

```bash
instruction_file() {           # $1 = directory, defaults to .
  for name in AGENTS.md CLAUDE.md; do
    [ -f "${1:-.}/$name" ] && { echo "${1:-.}/$name"; return; }
  done
  echo "${1:-.}/AGENTS.md"     # what to create when neither exists
}
```

- **Reading:** try `AGENTS.md`, then `CLAUDE.md`. A repo carrying both is mid-migration; the
  `AGENTS.md` wins, because that is the file every agent sees.
- **Writing:** edit the file that exists. Where neither does, create `AGENTS.md`.
- **Never** assume the name from the agent you happen to be — the repo decides, not the runtime.

## Which mode the user's Claude Code runs

`/config` → **Project instructions** picks one of `claude-md`, `claude-md-or-agents-md`
(default: AGENTS.md only where the ancestor chain holds no CLAUDE.md), `claude-md-and-agents-md`
(both, de-duplicated) and `managed-only`. A skill never depends on the mode — it resolves the
name from the filesystem, which is true in every mode.

## Regeln für Agenten ohne Claude-Code-Regelladen

`.claude/rules/**` lädt nur Claude Code von selbst. Jeder andere Agent holt sie über
`we/scripts/load-rules.py` — repo-unabhängig, der Root kommt aus `git rev-parse
--show-toplevel` oder `--root`:

```bash
python3 "$LOADER" path/to/file.py     # vor der ersten Änderung
python3 "$LOADER" --changed           # gegen den aktuellen Diff
python3 "$LOADER" --explain path.py   # warum eine Regel greift oder nicht
python3 "$LOADER" --list              # nur die Pfade
```

`/we:setup` legt dafür `.agents/skills/claude-rules/SKILL.md` aus
`templates/agents-skill/` an, wenn das Repo Regeln hat. Der Loader selbst wandert nie ins
Repo — er gehört dem Plugin und zieht mit ihm mit.
