// Pure logic of the Zentrale pane: the lines of each section and the swimlanes. It renders what
// `scripts/command_center/zentrale.py --json` and `scripts/flow_intervals.py --json` print; every
// age arrives as text (`age`, crew_view.py age_text), so the pane formats none of its own.
import type { CrewEntry, ZentraleDoc, ZentraleRow } from '../../types'

export type Line = { key: string; text: string; indent?: number; color?: string; bold?: boolean; dim?: boolean }

// The sections in display order with their labels (Pia 20.11.: what lies with the owner first).
export const SECTIONS = [
  ['owner', 'With the owner'],
  ['red', 'Red'],
  ['waiting', 'Waiting'],
  ['working', 'Working'],
  ['ci', 'CI'],
  ['accounts', 'Accounts'],
] as const

// `Q4 · owner · for ABC-12-fix (alpha-7) · 0h50 · title`
export const rowLine = (r: ZentraleRow) =>
  [
    r.item,
    r.holder,
    ...(r.for ? [`for ${r.for}${r.master ? ` (${r.master})` : ''}`] : r.master ? [`(${r.master})`] : []),
    r.since === 'unknown' ? 'since ?' : `${r.age ?? '?'}${r.since_note ? ` ${r.since_note}` : ''}`,
    ...(r.classes.length ? [r.classes.join(', ')] : []),
    ...(r.title ? [r.title] : []),
  ].join(' · ')

// `samu · coordinator · Q-Triage PROJ-31 · since 0h12 · waits: human · 9.14.0`
export const crewLine = (e: CrewEntry) =>
  [
    e.name,
    e.role,
    e.doing ?? '-',
    `since ${e.age ?? '?'}`,
    ...(e.waits ? [`waits: ${e.waiting_on ?? '?'}${e.blocked_kind ? ` (${e.blocked_kind})` : ''}`] : []),
    e.plugin,
    ...(e.model ? [e.model] : []),
  ].join(' · ')

const pct = (v: number | null) => (v === null ? '?' : `${Math.round(v)} %`)

const nothing = (key: string): Line => ({ key: `${key}-nothing`, text: 'nothing', indent: 2, dim: true })

// Every line of the pane below its header, section by section; an empty section is one line "nothing".
export const sectionLines = (doc: ZentraleDoc): Line[] => {
  const out: Line[] = []
  for (const [key, label] of SECTIONS) {
    out.push({ key: `h-${key}`, text: label, bold: true })
    const body: Line[] = []
    if (key === 'owner' || key === 'red' || key === 'waiting') {
      for (const r of doc.sections[key]) {
        body.push({ key: `${key}-${r.kind}-${r.item}`, text: rowLine(r), indent: 2, color: key === 'red' ? 'error' : key === 'owner' ? 'warning' : undefined })
      }
    } else if (key === 'working') {
      for (const e of doc.sections.working) {
        body.push({ key: `w-${e.session_id || e.name}`, text: `${e.role === 'worker' ? '└ ' : ''}${crewLine(e)}`, indent: 2, color: e.waits ? 'warning' : undefined })
      }
    } else if (key === 'ci') {
      for (const repo of doc.sections.ci.repos) {
        body.push({ key: `ci-${repo.repo}`, text: `${repo.repo}: ${repo.default_head}`, indent: 2 })
        for (const c of repo.checks) body.push({ key: `ci-${repo.repo}-${c.pr}-${c.name}`, text: `#${c.pr} ${c.name} ${c.status.toLowerCase()} · ${c.age ?? '?'}`, indent: 4 })
      }
      if (body.length) body.push({ key: 'ci-locks', text: doc.sections.ci.locks, indent: 2 })
    } else {
      for (const a of doc.sections.accounts) {
        const state = a.stale ? 'stale' : a.status
        body.push({
          key: `acc-${a.name}`,
          indent: 2,
          text: `${a.name}${a.active ? ' (active)' : ''}${a.in_rotation ? '' : ' (off)'} · 5h ${pct(a.five_hour.pct)} · 7d ${pct(a.seven_day.pct)}${a.threshold !== null ? ` · limit ${Math.round(a.threshold)} %` : ''} · ${state}`,
          color: a.red ? 'error' : a.stale ? 'warning' : undefined,
        })
      }
    }
    out.push(...(body.length ? body : [nothing(key)]))
  }
  return out
}

// --- swimlanes ---------------------------------------------------------------------------------

export type Interval = { who: string; kind: string; start: string; end: string }

// One glyph and colour per lane kind of `flow_intervals.py` (its `LANE_KINDS`; `test_lane_kinds.py`
// binds the two lists); `waiting:human` alone is `claude`, so waiting on the owner stands out, and a
// blocked session is `error`, so a stuck worker never draws as an empty cell.
const GLYPH: Record<string, { glyph: string; color?: string; label: string }> = {
  working: { glyph: '█', color: 'success', label: 'working' },
  'waiting:human': { glyph: '▓', color: 'claude', label: 'waits on the owner' },
  'waiting:<role>': { glyph: '▒', color: 'warning', label: 'waits on a session' },
  'waiting:ci': { glyph: '░', color: 'suggestion', label: 'waits on CI' },
  blocked: { glyph: '▚', color: 'error', label: 'blocked' },
  'idle-after-end': { glyph: '-', color: 'inactive', label: 'idle after its worker ended' },
  idle: { glyph: '·', color: 'inactive', label: 'idle' },
  parked: { glyph: '_', color: 'inactive', label: 'parked' },
  'no-data': { glyph: ' ', label: 'no data' },
}

export const glyphOf = (kind: string) => GLYPH[kind] ?? (kind.startsWith('waiting:') ? GLYPH['waiting:<role>']! : GLYPH['no-data']!)

export const LEGEND = Object.keys(GLYPH)
  .filter(k => k !== 'no-data')
  .map(k => `${GLYPH[k]!.glyph} ${GLYPH[k]!.label}`)
  .join('  ')

export type Lane = { who: string; cells: { glyph: string; color?: string }[] }

// One lane per session over the last `hours` before `now`, `width` columns: each column takes the
// kind that covers most of its slice (on a tie waiting:human wins, then blocked, a wait, working).
export const lanes = (intervals: readonly Interval[], now: number, hours: number, width: number): Lane[] => {
  const from = now - hours * 3_600_000
  const slice = (now - from) / width
  const rank = (k: string) => (k === 'waiting:human' ? 4 : k === 'blocked' ? 3 : k.startsWith('waiting:') ? 2 : k === 'working' ? 1 : 0)
  const byWho = new Map<string, Interval[]>()
  for (const iv of intervals) {
    if (iv.kind.startsWith('holding:') || iv.kind.startsWith('stage:')) continue
    if (Date.parse(iv.end) <= from || Date.parse(iv.start) >= now) continue
    byWho.set(iv.who, [...(byWho.get(iv.who) ?? []), iv])
  }
  return [...byWho.entries()]
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([who, ivs]) => ({
      who,
      cells: Array.from({ length: width }, (_, i) => {
        const a = from + i * slice
        const b = a + slice
        const cover = new Map<string, number>()
        for (const iv of ivs) {
          const overlap = Math.min(b, Date.parse(iv.end)) - Math.max(a, Date.parse(iv.start))
          if (overlap > 0) cover.set(iv.kind, (cover.get(iv.kind) ?? 0) + overlap)
        }
        const best = [...cover.entries()].sort((x, y) => y[1] - x[1] || rank(y[0]) - rank(x[0]))[0]
        const g = glyphOf(best ? best[0] : 'no-data')
        return { glyph: g.glyph, ...(g.color ? { color: g.color } : {}) }
      }),
    }))
}
