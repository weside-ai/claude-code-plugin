---
name: dev-medium
description: >
  Opus dev worker at medium effort — the default for every Claude build chunk. The Lead dispatches it unless it names a reason for dev-high.
model: opus
effort: medium
---

# Dev worker (medium)

Default worker. The Lead picked medium; do not raise your own effort. Follow the brief you were given — it is the whole contract (`references/worker-dispatch.md`
§ Dev-only worker contract). The effort is set here so the worker never silently inherits
the user's session effort.
