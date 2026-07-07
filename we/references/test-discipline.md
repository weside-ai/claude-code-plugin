# Test Discipline

What a test worth keeping looks like, where tests go, and what the project's configured
test discipline level means. Terms (`seam`, `tracer bullet`) per
`references/design-vocabulary.md`.

Consumers: `/we:develop`, `/we:build`, the `test-runner` and `code-reviewer` agents,
worker briefs (which inline the level — workers can't load references).

## The `test_discipline` levels (single owner)

`/we:setup` writes `test_discipline` to `.weside/config.json`. Skills read it before
implementing:

| Level | Meaning |
|---|---|
| `tdd` | Red before green wherever a seam exists: write the failing test first, then only enough code to pass it. One seam, one test, one minimal implementation per cycle — each test a tracer bullet. Where no seam exists (config, styling, throwaway code), fall back to `tests-after` behavior for that change. |
| `tests-after` *(default)* | Tests are written after the code, as part of the same change — they are a Definition-of-Done item, not a starting point. |
| `off` | The pipeline writes no tests unless the plan explicitly asks for them. Quality gates still run whatever tests already exist. |

Absent key → `tests-after` (back-compat). The rules below apply at **every** level — when
tests are written is configuration; what a good test is, is not.

## Seams first

Before writing any test, name the seams under test and confirm them with the user (or record
them in the plan when running autonomously). Testing effort lands on critical paths and
complex logic, not on every edge case — agreeing the seams up front is how.

## What a good test is

Tests verify behaviour through the seam, not implementation details. Code can change
entirely; tests shouldn't. A good test reads like a specification and survives refactors.

```typescript
// GOOD: observes behaviour through the seam
test("user can checkout with valid cart", async () => {
  const cart = createCart();
  cart.add(product);
  const result = await checkout(cart, paymentMethod);
  expect(result.status).toBe("confirmed");
});

// BAD: coupled to internals — breaks on refactor, behaviour unchanged
test("checkout calls paymentService.process", async () => {
  const mockPayment = jest.mock(paymentService);
  await checkout(cart, payment);
  expect(mockPayment.process).toHaveBeenCalledWith(cart.total);
});
```

```typescript
// BAD: expected value recomputed the way the code computes it — passes by construction
const expected = items.reduce((sum, i) => sum + i.price, 0);
expect(calculateTotal(items)).toBe(expected);

// GOOD: expected value from an independent source of truth
expect(calculateTotal([{ price: 10 }, { price: 5 }])).toBe(15);
```

## Anti-patterns (each paired with the fix)

- **Implementation-coupled** — mocks internal collaborators, tests private methods, or
  verifies through a side channel (querying the DB instead of the interface). Fix: test
  through the seam; verify by reading back through the same interface you wrote through.
- **Tautological** — the assertion restates the implementation, so it can never disagree
  with the code. Fix: expected values come from an independent source — a known-good
  literal, a worked example, the spec.
- **Horizontal slicing** — all tests first, then all implementation; bulk tests verify
  *imagined* behaviour. Fix: work in tracer bullets — one test, one implementation, repeat.

## Mocking

Mock at **system boundaries only**: external APIs, time/randomness, sometimes the
filesystem. Don't mock your own modules or internal collaborators — use the real thing
through its seam. Design boundaries for mockability: accept dependencies rather than
constructing them, and prefer SDK-style interfaces (one function per external operation)
over generic fetchers, so each mock returns one specific shape.

## Replace, don't layer

After deepening a module, old tests written against the shallow internals are waste: delete
them and test through the new seam. Keeping both layers means every refactor breaks tests
that were never protecting behaviour.

---

*Adapted from [Matt Pocock's skills](https://github.com/mattpocock/skills) (MIT).*
