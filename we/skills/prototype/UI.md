---
name: prototype-ui
description: UI-branch reference for /we:prototype — radically different variants behind ?variant=
type: reference
---

# UI Prototype

Generate **several radically different UI variants** on a single route, switchable from a
floating bar. The user flips between them in the browser, picks one (or steals bits from
each), then throws the rest away.

If the question is about logic/state rather than looks — wrong branch, use
[LOGIC.md](LOGIC.md).

## Two sub-shapes — strongly prefer A

A UI prototype is much easier to judge when it butts up against the rest of the app — real
header, real data, real density. A route in a vacuum makes every variant look fine.

- **Sub-shape A — inside an existing page (default).** Variants render on the existing
  route, gated by a `?variant=` URL param. Data fetching, params, and auth stay; only the
  rendered subtree swaps. Something new that would naturally live *inside* an existing page
  (a new dashboard section, a new settings card) is still sub-shape A.
- **Sub-shape B — a new throwaway route (last resort).** Only when the thing genuinely has
  no existing page to live in. Follow the project's routing convention, name it obviously
  prototype. Sanity-check first: is there really no page this could be embedded in?

## Process

1. **State the question and pick N.** Default **3 variants**; more than 5 stops being
   radically different and starts being noise — cap there. Write the plan in one line at the
   top of the file: "Three variants of the settings page via `?variant=` on `/settings`."
2. **Generate radically different variants.** Structurally different — different layout,
   information hierarchy, primary affordance — not just different colours. Three
   slightly-tweaked card grids isn't a prototype, it's wallpaper: if two drafts come out
   similar, redo one with an explicit structural constraint ("no card grid"). Use the
   project's component library; export clear names (`VariantA`, `VariantB`, `VariantC`).
3. **Wire the switcher.** One switcher component on the route renders the variant matching
   the URL param. Existing data fetching stays above the switcher.
4. **Build the floating bar.** Fixed bottom-centre: prev-arrow · variant label · next-arrow,
   wrapping. Arrows update the URL param via the framework's router (shareable,
   reload-stable); `←`/`→` keys cycle too, except when an input is focused. Visually
   distinct from the design under evaluation, and hidden in production builds — gate on the
   project's env check so a stray merge can't ship it.
5. **Hand it over.** Surface the URL and the variant keys. The interesting feedback is
   usually "the header from B with the sidebar from C" — that's the actual design.
6. **Capture and clean up.** Record which variant won and why (see SKILL.md "When done").
   Then fold the winner in and delete the losers and the switcher — variant code rots fast.

## Anti-patterns (each paired with the fix)

- **Variants that differ only in colour or copy — make them disagree about structure.**
- **Sharing a `<Layout>` between variants — share at most leaf components**; each variant
  must be free to throw the layout away.
- **Wiring variants to real mutations — point them at stubs**; the question is "what should
  this look like", not "does the backend work".
- **Promoting prototype code directly to production — rewrite the winner properly**; it was
  written under prototype constraints (no tests, minimal error handling).
