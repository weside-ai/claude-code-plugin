import type { FlowLight as Light, FlowPhase, FlowStage as Stage } from '../../types'

export type Check = {
  name?: string
  context?: string
  status?: string
  conclusion?: string | null
  state?: string
}

export type Pr = {
  number: number
  state: 'OPEN' | 'MERGED' | 'CLOSED'
  headRefName: string
  title: string
  autoMergeRequest: unknown
  statusCheckRollup: Check[] | null
  mergeStateStatus?: string
  isDraft?: boolean
}

export type Plan = { key: string; title: string; status?: string; epic?: string }

export type Evidence = {
  plan?: Plan
  prs: Pr[]
  aheadBranches: string[]
}

// Codex Review is advisory (AUTHORING.md § Measured facts): its red never makes a PR red here.
const ADVISORY = /codex review/i
const RED = new Set(['FAILURE', 'CANCELLED', 'TIMED_OUT', 'ACTION_REQUIRED', 'STARTUP_FAILURE', 'ERROR'])

export const checksPhase = (checks: Check[]): 'ci' | 'ci-red' | 'ready' => {
  let isPending = false
  for (const check of checks) {
    if (ADVISORY.test(check.name ?? check.context ?? '')) continue
    const verdict = check.conclusion ?? check.state ?? ''
    if (RED.has(verdict)) return 'ci-red'
    if (check.status !== undefined ? check.status !== 'COMPLETED' : verdict === 'PENDING' || verdict === 'EXPECTED') isPending = true
  }
  return isPending ? 'ci' : 'ready'
}

// First match wins, as in /we:orchestrate § State per story, with the PR state split into CI steps.
export const phaseOf = (ev: Evidence): FlowPhase => {
  if (ev.prs.some(pr => pr.state === 'MERGED')) return 'merged'
  const open = ev.prs.find(pr => pr.state === 'OPEN')
  if (open) return checksPhase(open.statusCheckRollup ?? [])
  if (ev.aheadBranches.length > 0) return 'dev'
  if (ev.prs.length > 0) return 'closed'
  if (ev.plan?.status === 'approved') return 'refined'
  if (ev.plan) return 'draft'
  return 'idea'
}

// Parses `git grep -e ... <rev> -- <files>` output: `<rev>:<path>:<line>` per hit.
export const parsePlans = (grepOut: string): Plan[] => {
  const byPath = new Map<string, Plan>()
  for (const raw of grepOut.split('\n')) {
    const m = /^[^:]+:(docs\/plans\/[^:]+):(.*)$/.exec(raw)
    const path = m?.[1]
    const line = m?.[2] ?? ''
    const key = path && ANY_KEY.exec(path)?.[0]
    if (!path || !key) continue
    const plan = byPath.get(path) ?? { key, title: '' }
    const field = /^(story|status|epic):\s*(.*)$/.exec(line)
    if (field) {
      const value = (field[2] ?? '').trim()
      if (field[1] === 'story') plan.key = value
      if (field[1] === 'status') plan.status = value
      if (field[1] === 'epic') plan.epic = value
    } else if (!plan.title && line.startsWith('# ')) {
      plan.title = line.replace(/^#\s*(Plan:\s*)?/, '').trim()
    }
    byPath.set(path, plan)
  }
  return [...byPath.values()]
}

export const matchesKey = (name: string, key: string): boolean =>
  new RegExp(`(^|[^0-9])${key}([^0-9]|$)`, 'i').test(name)

const ANY_KEY = /[A-Z][A-Z0-9]+-\d+/

// Ticket keys in a text, each once in order. With `prefix` (ticketing.project_key) any case
// matches, so `feat/proj-12-x` counts; without it only upper case, or `utf-8` would be a key.
export const keysIn = (text: string, prefix?: string): string[] => {
  const pattern = prefix ? new RegExp(`\\b${prefix}-\\d+\\b`, 'gi') : /\b[A-Z][A-Z0-9]+-\d+\b/g
  return [...new Set(text.match(pattern)?.map(k => k.toUpperCase()) ?? [])]
}

const REVIEW = /claude review/i
const PASS = new Set(['SUCCESS', 'NEUTRAL', 'SKIPPED'])

const nameOf = (check: Check) => check.name ?? check.context ?? '?'

type Tally = { pass: number; red: string[]; pending: number }
const tally = (checks: Check[]): Tally => {
  const t: Tally = { pass: 0, red: [], pending: 0 }
  for (const check of checks) {
    const verdict = check.conclusion ?? check.state ?? ''
    if (RED.has(verdict)) t.red.push(nameOf(check))
    else if (PASS.has(verdict)) t.pass++
    else t.pending++
  }
  return t
}

const lightOf = (t: Tally, total: number): Light => (t.red.length ? 'red' : t.pending || total === 0 ? 'active' : 'done')

const noteOf = (t: Tally, total: number): string =>
  total === 0
    ? 'no checks yet'
    : [t.red.length && `✗ ${t.red.join(', ')}`, t.pending && `${t.pending} running`, `${t.pass}/${total} ✓`].filter(Boolean).join(' · ')

// The steps /we:orchestrate walks a story through, each with what the evidence says about it.
export const stagesOf = (ev: Evidence & { ahead: number; branch?: string }): Stage[] => {
  const merged = ev.prs.find(pr => pr.state === 'MERGED')
  const open = ev.prs.find(pr => pr.state === 'OPEN')
  const closed = !merged && !open && ev.prs.length > 0
  const built = Boolean(merged || open || ev.ahead > 0)
  const isApproved = ev.plan?.status === 'approved'

  const plan: Stage = ev.plan
    ? { name: 'Plan', light: 'done', note: 'story plan on the default branch' }
    : built
      ? { name: 'Plan', light: 'skip', note: 'built without a plan file' }
      : { name: 'Plan', light: 'active', note: 'no plan yet; /we:orchestrate refines it' }
  const approval: Stage = isApproved
    ? { name: 'Approval', light: 'done', note: 'status: approved' }
    : ev.plan
      ? built
        ? { name: 'Approval', light: 'skip', note: `status: ${ev.plan.status ?? '–'}, built anyway` }
        : { name: 'Approval', light: 'active', note: `status: ${ev.plan.status ?? '–'}, waiting for approval` }
      : { name: 'Approval', light: built ? 'skip' : 'todo', note: '' }
  const build: Stage = merged || open
    ? { name: 'Build', light: 'done', note: ev.ahead ? `${ev.ahead} commits` : 'built' }
    : ev.ahead > 0
      ? { name: 'Build', light: closed ? 'red' : 'active', note: `${ev.ahead} commits on ${ev.branch ?? 'a branch'}, no PR yet` }
      : { name: 'Build', light: 'todo', note: isApproved ? 'ready; no worker started yet' : '' }
  const pr: Stage = merged
    ? { name: 'PR', light: 'done', note: `#${merged.number} merged` }
    : open
      ? { name: 'PR', light: open.isDraft ? 'active' : 'done', note: `#${open.number}${open.isDraft ? ' (Draft)' : ''}` }
      : closed
        ? { name: 'PR', light: 'red', note: 'closed without a merge' }
        : { name: 'PR', light: 'todo', note: '' }

  if (merged) {
    return [plan, approval, build, pr,
      { name: 'CI', light: 'done', note: '' }, { name: 'Review', light: 'done', note: '' }, { name: 'Merge', light: 'done', note: 'merged' }]
  }
  if (!open) {
    return [plan, approval, build, pr,
      { name: 'CI', light: 'todo', note: '' }, { name: 'Review', light: 'todo', note: '' }, { name: 'Merge', light: 'todo', note: '' }]
  }

  const checks = open.statusCheckRollup ?? []
  const ciChecks = checks.filter(c => !REVIEW.test(nameOf(c)) && !ADVISORY.test(nameOf(c)))
  const reviewChecks = checks.filter(c => REVIEW.test(nameOf(c)))
  const codex = tally(checks.filter(c => ADVISORY.test(nameOf(c))))
  const ci = tally(ciChecks)
  const review = tally(reviewChecks)
  const ciStage: Stage = { name: 'CI', light: lightOf(ci, ciChecks.length), note: noteOf(ci, ciChecks.length) }
  const reviewNote = [
    reviewChecks.length ? (review.red.length ? 'Claude ✗' : review.pending ? 'Claude running' : 'Claude ✓') : 'Claude missing',
    codex.red.length ? 'Codex ✗ (advisory)' : codex.pending ? 'Codex running' : codex.pass ? 'Codex ✓' : '',
  ].filter(Boolean).join(' · ')
  const reviewStage: Stage = { name: 'Review', light: lightOf(review, reviewChecks.length), note: reviewNote }

  const isGreen = ciStage.light === 'done' && reviewStage.light === 'done'
  const conflict = open.mergeStateStatus === 'DIRTY'
  const merge: Stage = conflict
    ? { name: 'Merge', light: 'red', note: 'conflicts with the default branch' }
    : open.autoMergeRequest
      ? { name: 'Merge', light: 'active', note: isGreen ? 'auto-merge armed, merging' : 'auto-merge armed, waiting for green' }
      : { name: 'Merge', light: isGreen ? 'active' : 'todo', note: isGreen ? 'green, auto-merge not armed (user merge?)' : '' }
  return [plan, approval, build, pr, ciStage, reviewStage, merge]
}
