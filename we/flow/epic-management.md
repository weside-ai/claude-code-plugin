# Epic Management

**Epics steer project focus at the initiative level.**

---

## What is an Epic?

> **"A large, FINITE user story with epic scope."**

An Epic is:
- **Finite** — Has a clear end (not "Admin Dashboard" forever)
- **Too big for one story** — Multiple sprints, many stories
- **Too specific for a category** — Not "Infrastructure", but "Push Notifications & App Store"
- **Progressively refined** — Stories emerge during work, not all upfront

An Epic is NOT:
- Permanent category ("Mobile", "Backend", "Security")
- Catch-all for similar stories
- Fully planned before starting

---

## Epic vs Story vs Category

| Concept | Scope | Horizon | Example |
|---------|-------|---------|---------|
| **Story** | Feature/Task | 1-5 days | "Add push notification backend" |
| **Epic** | Initiative | 1-3 months | "Push Notifications & App Store" |
| **Category** | Permanent | Forever | "Mobile Client" (wrong as Epic!) |

---

## Progressive Refinement

```
Epic created → Vision + First Stories → More stories emerge during work → Epic closed
```

**This is normal and intended.** Not all stories are known upfront.

---

## Epic Status = Project Focus

| Status | Meaning |
|--------|---------|
| **In Progress** | Actively working (stories in progress/review) |
| **Selected** | Up next (stories ready, none active) |
| **Backlog** | Paused/Future (even with done stories!) |
| **Done** | Complete (all stories done AND no further scope) |

---

## When to Create an Epic

Create when:
- Initiative too big for one story (> 2 sprints)
- Multiple stories belong together thematically
- Clear end is foreseeable
- Vision + business context needs its own frame

Do NOT create when:
- It's a permanent category
- Only 2-3 small stories
- No clear end

---

## Epic Template

```markdown
## Vision
[Why does this Epic exist? What problem does it solve?]

## Scope
[What belongs IN? What belongs OUT?]

## Stories
[First 2-3 stories to start with]

## Success Metrics
[When is this Epic DONE?]
```

---

## Best Practices

- Epic status = project focus, not story completion
- Derive stories progressively during work
- Close Epic when success metrics are reached
- Never use Epics as permanent categories
