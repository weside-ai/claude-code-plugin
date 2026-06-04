# Getting Started

You'll have the plugin installed and your first story shipped end-to-end in about 30 minutes. This guide assumes you've used Claude Code before and have a real project (any language, any size) to work on.

If you want the philosophy first, read [agenticproductownership.com](https://agenticproductownership.com). If you want to dive in, keep reading.

---

## 1. Install (2 minutes)

In a Claude Code session:

```
/plugin marketplace add weside-ai/claude-code-plugin
/plugin install we@weside-ai
```

Verify:

```
/plugin list
# should show: we@weside-ai (enabled)
```

The plugin is now active. All `/we:*` skills are available.

### Recommended companion plugins

Two plugins enhance the pipeline. They're optional — the framework works without them, but `/we:build` runs better with them:

```
/install code-simplifier@claude-plugins-official
/install security-guidance@claude-plugins-official
```

`/we:setup` will check for these and tell you what's missing.

---

## 2. Set up your project (5 minutes)

`cd` into your project and run:

```
/we:setup
```

Four questions:

1. **Vision** — link, file, or short description. *Optional* — say "skip" if you don't have one. Vision is the anchor `/we:story` uses to evaluate priority; without it, every feature seems equally important.
2. **Ticketing** — auto-detected. Confirm Jira / GitHub Issues / none.
3. **Stack** — auto-detected from `pyproject.toml` / `package.json` / `Cargo.toml` / `go.mod`. Confirm or override.
4. **Companion Framework** *(optional)* — the set of `.weside/` files and skills that define your crew, rosters, and deliberation config for this repo. Writing `.weside/config.json` + invoking `/we:onboarding` composes your crew. Say yes if you want to use `/we:council` and `/we:meet` — otherwise skip and revisit later.

If you said yes to the Companion Framework step, `/we:onboarding` walks you through naming who fills each role. You can use generic names ("PO", "Architect") to start; refine later. Two files appear in `.weside/`:

- `config.json` — machine-readable: rosters, meetings, ticketing, stack
- `weside.md` — human-readable: crew, repo purpose, meetings held here

See [concepts/companion-framework.md](concepts/companion-framework.md) for the full mechanics.

---

## 3. Your first story (15 minutes)

> **What about Vision / Saga / Epic?** For a brand-new product you'd start at `/we:vision`; for a new multi-bet theme (called a *Saga*), `/we:saga`; for a new bounded initiative (called an *Epic*), `/we:epic`. Each Solo skill walks down to the next altitude. Most stories — refactors, bug fixes, small features inside an existing Epic — skip straight to Story. That's what this section does. See [concepts/meetings.md](concepts/meetings.md) for the full altitude map.

Pick something small — a refactor, a small feature, a typo cluster. Then:

```
/we:story "Brief description of what you want"
```

`/we:story` is **interactive**. Claude will:

1. Ask clarifying questions about scope, users, edge cases
2. Probe trade-offs and rejected alternatives
3. Propose acceptance criteria and ask you to confirm or adjust
4. Sketch a phased implementation plan
5. Write the ticket (in your ticketing tool, if connected)
6. Write `docs/plans/{TICKET}-story.md` with the full plan

You'll know it worked when:

- A new file exists at `docs/plans/{TICKET}-story.md`
- The ticket has been created in Jira / GitHub Issues
- The plan has a *Context* section (the why), *Acceptance Criteria*, and *Phases*

Take five minutes to read the plan. If something's off, tell `/we:story` — it'll adjust. The plan is the contract for the next step.

---

## 4. Hand it to `/we:build` (10 minutes of watching)

When you're happy with the plan:

```
/we:build {TICKET}
```

`/we:build` runs the full pipeline autonomously. You watch:

```
Step 1: git_prepared          ← worktree, branch, ticket → In Progress
Step 2: implementation_complete ← code + tests, phase by phase
Step 3: ac_verified            ← every AC has evidence
Step 4: simplified             ← code quality pass
Step 5: review_passed          ← parallel: review + static + test
        static_analysis_passed
        test_passed
Step 6: docs_updated           ← doc-architect proposes diffs, you approve
Step 7: pr_created             ← PR opened with all gates passed
Step 8: ci_passed              ← CI + review findings, fixed in batch
Step 9: ticket → In Review     ← awaiting your merge
```

Checkpoint names (`git_prepared`, `ac_verified`, etc.) come from the internal orchestration CLI — if a build is interrupted, just re-invoke `/we:build {TICKET}` and it resumes from the last checkpoint.

Don't tab away the whole time — there are two checkpoints where Claude might ask you something:

- **Step 3 (AC verification)** — if an AC can't be satisfied with evidence, you'll be told.
- **Step 8 (CI fix)** — review findings (CodeRabbit on GitHub, or local quality gates elsewhere) are addressed here; if 3 cycles can't clear them, you're asked.

Otherwise it runs.

---

## 5. Review + merge

When `/we:build` finishes, you have a PR. Open it. Review it like any PR — your eyes, your call. When you're happy:

- Merge via your platform's UI (GitHub, GitLab, Bitbucket, or `git merge` locally)
- Close the ticket (or watch it auto-transition, depending on your ticketing config)

Done. You've shipped a story end-to-end through Agentic Product Ownership.

---

## What just happened

You went from a sentence to a merged PR with:

- A real ticket
- A detailed plan you can refer back to
- Implementation that meets every acceptance criterion
- Tests with coverage
- Code review (programmatic + automated review bot, if configured)
- Static analysis (lint, format, types)
- Updated docs (whatever the change touched)
- A passing CI

The plugin enforced the *discipline*. You stayed responsible for the *decisions* — what to build, what the AC are, when to merge.

---

## Next steps

Pick one based on where you want to go next:

- **Use the pipeline again** — do another story. The second one goes faster; you'll start to feel the rhythm.
- **Try a council** — when you next have a tricky decision: `/we:council "<question>"`. See [concepts/meetings.md](concepts/meetings.md).
- **Set up cross-repo work** — `/we:sideload <other-repo>` from inside your current one. See [concepts/companion-framework.md](concepts/companion-framework.md#how-wesideload-uses-the-framework).
- **Read the workflow doc** — [workflow.md](workflow.md) has the full pipeline diagram + every skill's place in it.
- **Upgrade to a Companion** — if the lack of cross-session memory is starting to hurt, see [upgrade-paths.md](upgrade-paths.md).

---

## Common first-time issues

- **`/we:story` produces a plan but the ticket wasn't created** → check `/plugin settings` for `ticketingTool` and `projectKey`. Or no ticketing tool detected — that's "Plan-only mode", which is fine.
- **`/we:build` errors at Step 1 with "DoR failed"** → the plan is missing required sections. Open it, see what's flagged, re-run `/we:story` to fill the gap.
- **`/we:build` interrupted mid-pipeline** → run `/we:build {TICKET}` again. It picks up from the last checkpoint.
- **CI keeps failing** → see the [ci-review skill reference](skills.md#weci-review) and [troubleshooting.md](troubleshooting.md).

---

## References

- [workflow.md](workflow.md) — the full pipeline with diagrams
- [skills.md](skills.md) — every skill explained
- [concepts/meetings.md](concepts/meetings.md) — the four meeting altitudes
- [concepts/companion-framework.md](concepts/companion-framework.md) — what `.weside/` is and why
- [upgrade-paths.md](upgrade-paths.md) — Maturity Model L1 → L4
- [agenticproductownership.com](https://agenticproductownership.com) — the philosophy
- [troubleshooting.md](troubleshooting.md) — when something doesn't go as planned
