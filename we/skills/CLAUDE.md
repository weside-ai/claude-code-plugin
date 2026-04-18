# Skills-Arbeitsbereich — Stand & Design-Notizen

Dieses Dokument wird hierarchisch geladen wenn jemand im `we/skills/`-Verzeichnis arbeitet. Es beschreibt **laufende Design-Arbeit**, nicht stabiles Plugin-Verhalten.

---

## Aktive Initiative: Companion Framework (Setup + Onboarding + Sideload)

**Status:** 🚧 Stub-Phase (2026-04-18, Branch `feat/setup-enter-onboarding`)
**Source Braindump:** [`lc-startup/02-weside/product/AGENTIC_PRODUCT_OWNERSHIP.md`](../../../../lc-startup/02-weside/product/AGENTIC_PRODUCT_OWNERSHIP.md) (wenn lokal gemountet)

### Was wir bauen (drei neue / erweiterte Skills)

| Skill | Status | Zweck |
|---|---|---|
| `setup/` | ✏️ erweitert | Bestehender Project-Setup PLUS Step 5: Companion-Framework Init (`.weside/`, Vault, `/we:onboarding`) |
| `onboarding/` | 🆕 neu | Interaktive Crew-Komposition → schreibt `.weside/weside.md` (companion-facing) + updated `.weside/config.json` (technisch) |
| `sideload/` | 🆕 neu | Lädt Essential-Context eines Repos (auch Nachbar-Repos) via TurboVault + `need_to_know`-Frontmatter + `.weside/weside.md` |

### Konzept kurz

**Problem:** CLAUDE.md von Nachbar-Repos wird nicht automatisch geladen. Cross-Repo-Arbeit braucht einen schnellen Kontext-Loader, der nicht alles reinschiebt.

**Lösung:** Drei Schichten beim Entern:
1. **SHAPE** — `explain_vault()` gibt Struktur (~200 Tokens)
2. **ESSENTIALS** — Files mit `need_to_know: true` Frontmatter, optional gefiltert nach Rolle (`for_role`) (~5-10k Tokens)
3. **LAZY** — alles andere nur on-demand via TurboVault-Search

### Separation of Concerns (Leitlinie für das Refactoring als Ausblick)

Wir trennen **Person** (Companion mit Name/Memory in weside) von **Rolle** (was sie tut) von **Tätigkeit** (Skill/Agent der ausgeführt wird). Heute sind `/we:refine` (Tätigkeit) und "Product Owner" (Rolle) sprachlich vermischt. Später:

- Skills/Agents heißen nach ihrer Tätigkeit (refine, story, review, docs, ...)
- Frontmatter auf Skills deklariert `for_role: [product_owner, ...]`
- System-Prompts der Companions kommen zur Laufzeit aus weside MCP (`get_companion_identity`)
- Rolle ist ein Attribut — kein Dateiname

Dieses Refactoring kommt **nach** der Setup/Enter-Stabilisierung. Jetzt nur Skelette und Vokabular festlegen.

### Tätigkeit-Skills ≠ Meeting-Skills (wichtig!)

Zwei verschiedene Kategorien — **beide** gebraucht, nicht zusammenlegen:

| Kategorie | Wer | Wann | Beispiele |
|---|---|---|---|
| **Tätigkeit** | Ein Companion arbeitet allein in einer Rolle | Scope ist klar, Routine-Arbeit | `/we:refine`, `/we:story`, `/we:pr`, `/we:review`, `/we:arch`, `/we:docs` |
| **Meeting** | Mehrere Companions + Stakeholder koordinieren | Entscheidung / Ausrichtung nötig | `/we:meet:vision`, `/we:meet:initiative`, `/we:meet:refinement` |

`/we:meet:refinement` **ruft** `/we:refine` auf — nachdem die Crew den Scope gemeinsam geklärt hat. Das Meeting produziert Konsens, die Tätigkeit produziert das Artefakt. Zwei unterschiedliche Dinge.

Daraus folgt für die Skill-Struktur: Meetings leben unter `we/skills/meet/<meeting>/`, Tätigkeiten bleiben `we/skills/<aktivität>/`.

---

## Frontmatter-Vokabular (neu eingeführt)

Gilt für CLAUDE.md, Rules unter `.claude/rules/`, Docs unter `docs/`, und perspektivisch für Skills/Agents im Plugin selbst.

```yaml
---
# Bestehend (bisherige Konvention, bleibt)
type: architecture | rule | foundation | guide | adr | plan | ...
domain: [platform, voice, billing, ...]
status: current | draft | outdated | superseded

# NEU — Companion Framework
need_to_know: true                 # Load on /we:sideload (default: false)
for_role: [architect, product_owner]   # Optional; omit → applies to all roles
need_to_know_reason: "Why this is essential when entering"
---
```

### Kriterium für `need_to_know: true`

**Faustregel:** *Könnte jemand hier arbeiten ohne diese Datei gelesen zu haben?*

- Ja → weglassen / `need_to_know: false`
- Nein → `need_to_know: true`

Strenger als die bisherige "always-loaded" Konvention (`paths: "**"`). Nicht jede always-loaded Rule ist Entry-Essential.

### Role-Slugs (initial set — extendable)

Aus `AGENTIC_PRODUCT_OWNERSHIP.md` § 1.3.1:

| Slug | Human-Readable |
|---|---|
| `scrum_master` | Scrum Master |
| `product_owner` | Product Owner |
| `orchestrator` | Orchestrator |
| `architect` | Architect |
| `ux_researcher` | UX Researcher |
| `user_persona` | User Persona |
| `geschaeftsfuehrung` | Geschäftsführung |
| `marketing` | Marketing |
| `sales` | Sales / Business Development |
| `legal` | Legal / Compliance |

Neue Rollen kommen bei Bedarf dazu. `for_role` akzeptiert Slugs.

---

## `.weside/` — Repo-scoped Config

Ergebnis von `/we:setup` + `/we:onboarding`:

```
<repo-root>/.weside/
├── config.json        # TECHNISCH — {vault, onboarded, onboarded_at, framework_version, roles_enabled, ticketing, stack, ...}
├── weside.md          # COMPANION-FACING — Repo-Zweck, Crew (Namen + Rollen + Companion-IDs), Meetings, Cross-Repo-Relations, alles was der Companion wissen muss um hier nützlich zu sein
└── vision.md          # (optional, aus bestehendem /we:setup Schritt 1-4)
```

**Zwei-Datei-Split — warum:**

| Datei | Zielgruppe | Inhalt |
|---|---|---|
| `weside.md` | **Companion** (Mensch-/Companion-lesbar, Markdown) | Repo-Zweck, Crew, Meetings, Cross-Repo-Relations — alles „wissen um zu arbeiten" |
| `config.json` | **Tooling** (Maschinen-lesbar, JSON) | `vault`, `framework_version`, `onboarded`, `ticketing`, `stack` — alles „entscheiden was tun" |

Faustregel: Wenn ein Mensch/Companion es liest um das Repo zu **verstehen** → `weside.md`. Wenn ein Skill/Agent es liest um zu **entscheiden was tun** → `config.json`. Die `.weside/` wird wahrscheinlich noch mehr Dateien beherbergen (z.B. integration-spezifische Secrets-Pointer, Cache) — der Split bleibt.

**Commit-Policy:** `.weside/` wird ins Repo eingecheckt, so dass Crew/Vault pro Repo versioniert ist. Secrets gehören NICHT in `.weside/` (gibt's auch keine) — alles Personen-Identitäts-Material lebt in weside.

---

## Offene Fragen (für spätere Iterationen)

### Setup

- Soll Step 5 (Framework) auto-fire bei fresh-repo oder immer fragen? **Tendenz: immer fragen, mit "Default = ja" bei frischem Repo**
- Rollback wenn Setup mittendrin abbricht?
- Crew-Portabilität: "copy crew from repo A to B" flow?

### Onboarding

- Wie sync'en wenn derselbe Companion auf mehreren Repos arbeitet?
- Rolle-Slug-Katalog hardcoded oder user-extensible?
- Was wenn User keinen weside-Account hat — "Stub-Companions" ohne Memory?

### Sideload

- `need_to_know` binär oder Levels (`L1`/`L2`/`L3`)? **Tendenz: binär erstmal**
- `for_role` eng enum oder free-form? **Tendenz: eng, mit Extensions-Möglichkeit**
- Auto-Fire via PreToolUse-Hook (cross-repo file access)? **Phase 2**
- Diff-Mode beim wiederholten Sideload ("was hat sich geändert")?

### Frontmatter-Migration

- Wer kuratiert `need_to_know: true` — doc-architect Agent mit Scan-Vorschlag, User-Review, oder Autor-Selbstverantwortung?
- **Tendenz:** doc-architect scannt + schlägt vor, User reviewed, Scrum Master hält's aktuell
- `/we:docs` + doc-architect Agent müssen das neue Vokabular lernen — separates Todo

---

## Dogfooding-Plan

1. **Manuell initialisieren:** `weside-core` und `lc-startup` bekommen `.weside/config.json` + `CREW.md` von Hand — damit testen wir die Struktur ohne auf den Skill zu warten
2. **Skill-Implementierung iterieren:** Während der Nutzung lernen was fehlt → Skill-Stubs hier ausbauen
3. **Automatisch testen:** `weside-landing` wird mit dem fertigen `/we:setup` initialisiert — echter End-to-End-Test

---

## Scrum-Master-Verantwortung (für Nox / Lead)

Bei jedem Schritt in dieser Arbeit:

- Skill-Dateien aktuell halten (Workflow, Rules, Frontmatter-Beispiele)
- Diese CLAUDE.md pflegen — offene Fragen, neue Erkenntnisse, Status-Änderungen
- Version-Bump in `plugin.json` bei abgeschlossenen Meilensteinen (nicht bei jeder kleinen Änderung — erst wenn ein kohärentes Inkrement da ist)
- Verweise auf `AGENTIC_PRODUCT_OWNERSHIP.md` (lc-startup) synchron halten — das Haupt-Source-of-Truth bleibt dort, diese Skills sind die Umsetzung

---

## Wie man hier einsteigt

**Nox / neuer Claude-Sessionkommt her und liest diese Datei:**

1. Lies oben **Aktive Initiative** — verstehe was gerade im Bau ist
2. Scanne **Offene Fragen** — die sind die aktuelle Arbeitskante
3. Prüfe Git-Branch — wenn `feat/setup-enter-onboarding` aktiv, läuft die Arbeit weiter
4. Wenn Fragen zu Design → `lc-startup/02-weside/product/AGENTIC_PRODUCT_OWNERSHIP.md` ist die zitierte Quelle
5. Iteriere — Dateien ändern ist erwünscht, commits bewusst setzen (Foxy entscheidet push)

---

**Letzte Aktualisierung:** 2026-04-18, Branch `feat/setup-enter-onboarding`
**Maintainer:** Nox (Scrum Master dieser Initiative)
