---
name: instruction-sources
description: The generic sources an instruction audit fetches fresh as raw Markdown, what each one governs, and how to fetch and hash them. Read by /we:instruction-audit; repo extras live in .weside/optimization/sources.md.
---

# Instruction sources

Fetch every source with `curl -sL <url>` as raw Markdown. A summarising fetch tool returns a
model's paraphrase, which neither hashes nor diffs reproducibly. A response whose content type is
not `text/markdown`, or whose HTTP status is not 200, is a fetch failure: report it and keep the
source's previous lock entry. The lock format: `references/optimization-store.md` § Source lock.

| URL | Governs |
|---|---|
| `https://code.claude.com/docs/en/memory.md` | `CLAUDE.md` / `AGENTS.md` size, rules, `paths:` globs and brace expansion, load order |
| `https://code.claude.com/docs/en/skills.md` | skill frontmatter, listing cap, `SKILL.md` size |
| `https://code.claude.com/docs/en/sub-agents.md` | subagent definitions, combined description budget |
| `https://code.claude.com/docs/en/best-practices.md` | Claude Code working practices |
| `https://code.claude.com/docs/en/debug-your-config.md` | how to see what actually loaded |
| `https://code.claude.com/docs/en/features-overview.md` | which mechanism fits which job |
| `https://code.claude.com/docs/en/context-window.md` | what costs context and when |
| `https://code.claude.com/docs/en/plugin-evals.md` | `claude plugin eval` for measuring skills |
| `https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices.md` | progressive disclosure, references one level deep, tables of contents |
| `https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/claude-prompting-best-practices.md` | prompt wording for current models |
| `https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/prompting-claude-opus-5-5.md` | target-model specifics; swap for the page of the configured `target_model` |

```bash
mkdir -p ~/.cache/we/sources
SRC=$(mktemp)   # one per source: parallel fetches never share a file
curl -sL -o "$SRC" -w '%{http_code} %{content_type}\n' "$URL"
SHA=$( (sha256sum "$SRC" 2>/dev/null || shasum -a 256 "$SRC") | cut -d' ' -f1)
mv "$SRC" ~/.cache/we/sources/"$SHA".md
```

Two fetches of one page returned the same hash for every source above (2026-10-02), so a changed
hash means the page changed.
