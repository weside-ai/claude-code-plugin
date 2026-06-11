---
name: audit-architecture-module-depth
description: Deep-vs-shallow module analysis — deletion test, seam quality, pass-through detection (Ousterhout vocabulary)
type: reference
---

# Module Depth

## Purpose

Find **shallow modules** — interfaces nearly as complex as their implementation — and propose deepening opportunities. Depth = a lot of behaviour behind a small interface; depth gives callers *leverage* and maintainers *locality* (change, bugs, and knowledge concentrated in one place).

## When to apply

- Phase 2 via `extra_lens: [module-depth]`, or Phase 3 via `--lens=module-depth`
- Scope: per-subsystem or project-wide
- Project requirements: none — applies to any codebase

## Vocabulary (use these terms exactly in findings)

- **Module** — anything with an interface and an implementation (function, class, package, slice).
- **Interface** — everything a caller must know: types, invariants, error modes, ordering, config. Not just the signature.
- **Depth** — leverage at the interface. **Deep** = high leverage. **Shallow** = interface ≈ implementation complexity.
- **Seam** — where an interface lives; a place behaviour can be altered without editing in place. One adapter = hypothetical seam; two adapters = real seam.

## Method

1. **Deletion test** on suspect modules: imagine deleting the module. Complexity vanishes → it was a pass-through (finding). Complexity reappears across N callers → it earns its keep (clean).
2. **Bounce check:** does understanding one concept require hopping between many small modules? Fragmented depth is a finding.
3. **Testability-extraction check:** pure functions extracted "for testability" whose real bugs hide in how they're called (no locality) — the interface is the test surface; if the seam can't host the real bug pattern, flag it.
4. **Seam-leak check:** tightly-coupled modules that leak internals across their seam (caller must know ordering, hidden state, error idiosyncrasies).

## Output format

Per finding: `[SEVERITY] <module> — shallow|pass-through|fragmented|leaking seam` + the deletion-test verdict + a one-line deepening proposal (what moves behind which interface), in terms of leverage and locality. Use the project's `CONTEXT.md` glossary for domain names, this file's vocabulary for architecture.

## Example

`[MAJOR] notification_formatter.py — pass-through: 7 functions each wrapping one template call; deletion test shows complexity just moves to call sites. Deepen: fold into NotificationService.render(event) — one seam, callers stop knowing template names.`

---

*Vocabulary adapted from John Ousterhout ("A Philosophy of Software Design") via [Matt Pocock's skills](https://github.com/mattpocock/skills) (MIT).*
