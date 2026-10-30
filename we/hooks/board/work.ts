// Pure logic of a master's work tree on /board (docs/board.md § Work): the session's keys, placed in
// the saga → epic → story hierarchy of the plan files, and laid out as lines for the box.
import type { FlowPhase, WorkNode } from '../../types'
import { PHASE_COLOR, PHASE_URGENCY, matchesKey, phaseOf } from '../flow/phase'
import type { PlanFile, Pr } from '../plans/plans'
import type { SessionGroup } from './board'

export const MAX_STORIES = 8

// A run of text that stays on one line, in parts that colour it.
export type Part = { text: string; color?: string; bold?: boolean; dim?: boolean }

export const widthOf = (seg: readonly Part[]) => seg.reduce((n, p) => n + p.text.length, 0)

// The keys a box's tree grows from: its master's first, then its workers', each once.
export const groupKeys = (group: SessionGroup): string[] =>
  [...new Set([group.head, ...group.workers].flatMap(s => s?.keys ?? []).filter(Boolean))]

// A tree the board file carries itself (`sessions[].work`), cut to the fields the pane draws.
export const workOf = (raw: unknown): WorkNode[] | undefined => {
  if (!Array.isArray(raw)) return undefined
  const text = (v: unknown) => (typeof v === 'string' && v.trim() ? v.trim() : undefined)
  const node = (n: unknown): WorkNode[] => {
    if (!n || typeof n !== 'object') return []
    const o = n as Record<string, unknown>
    const kind = (['saga', 'epic', 'story', 'key'] as const).find(k => k === o.kind)
    if (!kind) return []
    const phase = typeof o.phase === 'string' && o.phase in PHASE_COLOR ? (o.phase as FlowPhase) : undefined
    const children = Array.isArray(o.children) ? o.children.flatMap(node) : undefined
    return [{ kind, key: text(o.key), title: text(o.title), status: text(o.status), phase, children }]
  }
  return raw.flatMap(node)
}

export const storyKey = (file: PlanFile) => file.story ?? /[A-Z][A-Z0-9]+-\d+/.exec(file.path)?.[0]

// The story keys whose PRs the tree needs: every story of an epic it shows, and each key's own story.
export const storiesInScope = (keys: readonly string[], files: readonly PlanFile[]): string[] => {
  const epics = files.filter(f => f.kind === 'epic')
  const stories = files.filter(f => f.kind === 'story' && storyKey(f))
  const refs = new Set<string>()
  for (const key of keys) {
    const epic = epics.find(e => e.ticket === key)
    const story = stories.find(s => storyKey(s) === key)
    if (epic) [epic.ticket, epic.epic].forEach(r => r && refs.add(r))
    const parent = story?.epic && epics.find(e => e.ticket === story.epic || e.epic === story.epic)
    if (parent) [parent.ticket, parent.epic].forEach(r => r && refs.add(r))
  }
  const out = stories.filter(s => keys.includes(storyKey(s)!) || (s.epic && refs.has(s.epic))).map(s => storyKey(s)!)
  return [...new Set(out)]
}

// A story's /flow phase from its plan, its PRs and the branches ahead of the default branch.
export const storyPhase = (key: string, file: PlanFile | undefined, prs: readonly Pr[], aheadBranches: string[]): FlowPhase =>
  phaseOf({
    plan: file ? { key, title: file.title, status: file.status, epic: file.epic } : undefined,
    prs: prs.filter(pr => matchesKey(pr.headRefName, key) || matchesKey(pr.title, key)),
    aheadBranches,
  })

// Saga → epic → story from the plan files. A key that is an epic brings the epic; a story brings its
// epic, or stands alone without one; a key without a plan file is a `key` leaf. The session's own
// stories lead their epic, then the most urgent.
export const buildWork = (keys: readonly string[], files: readonly PlanFile[], phases: Readonly<Record<string, FlowPhase>>): WorkNode[] => {
  const epics = files.filter(f => f.kind === 'epic')
  const stories = files.filter(f => f.kind === 'story' && storyKey(f))
  const roots: WorkNode[] = []
  const placed = new Map<string, WorkNode>()
  const rank = (k: string) => (keys.includes(k) ? keys.indexOf(k) : keys.length)
  const storyNode = (s: PlanFile): WorkNode => {
    const key = storyKey(s)!
    return { kind: 'story', key, title: s.title, phase: phases[key] }
  }
  const placeEpic = (e: PlanFile) => {
    if (placed.has(e.path)) return
    const children = stories
      .filter(s => s.epic && (s.epic === e.ticket || s.epic === e.epic))
      .map(storyNode)
      .sort((a, b) => rank(a.key!) - rank(b.key!) || PHASE_URGENCY[a.phase ?? 'idea'] - PHASE_URGENCY[b.phase ?? 'idea'] || a.key!.localeCompare(b.key!))
    const node: WorkNode = { kind: 'epic', key: e.ticket ?? e.epic, title: e.title, status: e.status, children }
    placed.set(e.path, node)
    if (!e.saga) {
      roots.push(node)
      return
    }
    let saga = placed.get(`saga:${e.saga}`)
    if (!saga) {
      const file = files.find(f => f.kind === 'saga' && f.saga === e.saga)
      saga = { kind: 'saga', key: e.saga, title: file?.title || e.saga, status: file?.status, children: [] }
      placed.set(`saga:${e.saga}`, saga)
      roots.push(saga)
    }
    saga.children!.push(node)
  }
  for (const key of keys) {
    const epic = epics.find(e => e.ticket === key)
    if (epic) {
      placeEpic(epic)
      continue
    }
    const story = stories.find(s => storyKey(s) === key)
    const parent = story?.epic ? epics.find(e => e.ticket === story.epic || e.epic === story.epic) : undefined
    if (parent) placeEpic(parent)
    else if (story && !placed.has(story.path)) {
      const node = storyNode(story)
      placed.set(story.path, node)
      roots.push(node)
    } else if (!story) roots.push({ kind: 'key', key })
  }
  return roots
}

const PHASE_LABEL: Record<FlowPhase, string> = {
  idea: 'idea',
  draft: 'plan',
  refined: 'approved',
  dev: 'build',
  ci: 'CI',
  'ci-red': 'CI red',
  ready: 'PR',
  merged: 'merged',
  closed: 'PR closed',
}

// One line: the title takes what the parts before and after it leave of the room.
const fit = (before: Part[], title: string | undefined, after: Part[], room: number): Part[] => {
  const left = room - widthOf(before) - widthOf(after) - 1
  const text = title && title.length > left ? `${title.slice(0, Math.max(0, left - 1))}…` : title
  // Too narrow for a title: the line itself is cut at the room.
  let rest = room
  return [...before, ...(text && left >= 4 ? [{ text: ` ${text}` }] : []), ...after].flatMap(p => {
    const cut = p.text.length > rest ? `${p.text.slice(0, Math.max(0, rest - 1))}…` : p.text
    rest -= cut.length
    return cut && rest >= 0 ? [{ ...p, text: cut }] : []
  })
}

// One line of the tree: its depth (two columns each) and its parts.
export type WorkLine = { depth: number; parts: Part[] }

// The tree as lines no wider than `room`, indent included: at most `max` open stories, the rest as one `+ k more` line;
// merged stories count only in their epic's line.
export const layoutWork = (nodes: readonly WorkNode[], room: number, max = MAX_STORIES): WorkLine[] => {
  const out: WorkLine[] = []
  let shown = 0
  let hidden = 0
  const walk = (n: WorkNode, depth: number) => {
    const width = room - 2 * depth
    const push = (parts: Part[]) => out.push({ depth, parts })
    const status: Part[] = n.status ? [{ text: ` (${n.status})`, dim: true }] : []
    if (n.kind === 'saga') {
      push(fit([{ text: 'Saga', color: 'claude', bold: true }], n.title ?? n.key, status, width))
    } else if (n.kind === 'epic') {
      const stories = (n.children ?? []).filter(c => c.kind === 'story')
      const merged = stories.filter(c => c.phase === 'merged').length
      const count: Part[] = stories.length ? [{ text: ` · ${merged}/${stories.length} stories merged`, dim: true }] : []
      const head: Part[] = [{ text: 'Epic', color: 'claude', bold: true }, ...(n.key ? [{ text: ` ${n.key}`, bold: true }] : [])]
      push(fit(head, n.title, [...status, ...count], width))
    } else if (n.kind === 'story') {
      if (n.phase === 'merged' && depth) return
      if (shown >= max) {
        hidden++
        return
      }
      shown++
      const color = n.phase ? PHASE_COLOR[n.phase] : 'inactive'
      const label: Part[] = n.phase
        ? [{ text: `  ${PHASE_LABEL[n.phase]}`, color, bold: true }]
        : n.status ? [{ text: `  ${n.status}`, dim: true }] : []
      push(fit([{ text: '●', color, bold: true }, ...(n.key ? [{ text: ` ${n.key}`, bold: true }] : [])], n.title, label, width))
    } else {
      push(fit([{ text: n.key ?? '?', bold: true }], n.title, n.title ? [] : [{ text: ' (no plan)', dim: true }], width))
    }
    for (const c of n.kind === 'story' ? [] : n.children ?? []) walk(c, depth + 1)
  }
  for (const n of nodes) walk(n, 0)
  if (hidden) out.push({ depth: 0, parts: [{ text: `+ ${hidden} more`, dim: true }] })
  return out
}
