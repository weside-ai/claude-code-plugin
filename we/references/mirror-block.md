# Children Mirror Block

`/we:saga` and `/we:epic` mirror child items (Epics / Stories) from the ticketing tool into the plan doc, between HTML markers, so user prose is never touched:

```markdown
## Sub-Epics            ← saga doc (or "## Stories" in an epic doc)

<!-- mirror:start (auto-generated; do not edit by hand — run /we:saga to refresh) -->

_Mirror of child Epics in the ticketing tool, refreshed YYYY-MM-DD._

| Key | Title | Status | Last activity | Notes |
|---|---|---|---|---|

<!-- mirror:end -->
```

The epic doc's Stories table adds a **Plan** column: `✓` if `docs/plans/<KEY>-story.md` exists (prefer `-story.md`; legacy `-plan.md` accepted), `—` otherwise — that is the refined-vs-not signal.

Rules:

- The markers are mandatory. Everything between them is owned by the skill and overwritten on every refresh; everything outside is user-owned and never touched. If markers are missing, insert the block under the section heading (create the heading if missing).
- Normalise the ticketing status vocabulary into the buckets **Done / Active / Refined (epic only) / Backlog / Blocked** — project mapping if configured, shipped default otherwise.
- No ticketing tool configured → populate from filesystem scan of the child plan files' frontmatter, with a footnote saying so.
- A refresh also updates the `updated:` frontmatter date and appends one Updates-Log line: `- YYYY-MM-DD — mirror refresh (<N> children; +<a> added, −<b> removed, !<c> status-changed)`.
