// /flow in a master: what that master orchestrates, from `standup.py --orchestration` (the one
// owner of the master → epic → stories → workers map; /flow parses it and assigns nothing).
import type { EngineInterface } from 'claude-code'

type $ = EngineInterface

const TIMEOUT_MS = 30_000

export type MasterWorker = { name: string; state?: string; key?: string }

export type MasterOrchestration = {
  name: string
  epic?: string
  stories: { key: string; workers: MasterWorker[] }[]
  otherWorkers: MasterWorker[]
  // the repo whose plans and crew the script read; absent when it found none from this session
  crewRepo?: string
}

const str = (value: unknown) => (typeof value === 'string' && value ? value : undefined)

const workersOf = (value: unknown): MasterWorker[] =>
  (Array.isArray(value) ? value : []).flatMap(w => {
    const name = str((w as { name?: unknown })?.name)
    if (!name) return []
    const { state, key } = w as { state?: unknown; key?: unknown }
    return [{ name, state: str(state), key: str(key) }]
  })

async function lookup($: $): Promise<MasterOrchestration | string> {
  const id = await $.session.id()
  const argv = ['python3', '-I', `${$.plugin.root}/scripts/standup.py`, '--orchestration', '--session', id, '--json']
  const run = await $.process.run(argv, { timeoutMs: TIMEOUT_MS })
  if (run.exitCode !== 0) return `standup.py exit ${run.exitCode}`
  let doc: { orchestration?: unknown; scope?: { crew_repo?: unknown } }
  try {
    doc = JSON.parse(run.stdout)
  } catch {
    return 'standup.py printed no JSON'
  }
  const orchestration = doc?.orchestration as { masters?: unknown } | null | undefined
  if (!orchestration) return 'orchestration: null'
  const entry = (Array.isArray(orchestration.masters) ? orchestration.masters : [])[0] as Record<string, unknown> | undefined
  const name = str(entry?.master)
  if (!entry || !name) return 'no entry for this session'
  const stories = (Array.isArray(entry.stories) ? entry.stories : []).flatMap(s => {
    const key = str((s as { key?: unknown })?.key)
    return key ? [{ key, workers: workersOf((s as { workers?: unknown }).workers) }] : []
  })
  return { name, epic: str(entry.epic), stories, otherWorkers: workersOf(entry.other_workers), crewRepo: str(doc.scope?.crew_repo) }
}

// The gate and the fallback: a session whose WE_ROLE is not `master` runs no process; any failure
// of the lookup (exit, no JSON, timeout, `orchestration: null`, no entry) is one ui.log line and
// undefined, so /flow resolves its keys exactly as without a master.
export async function masterView($: $): Promise<MasterOrchestration | undefined> {
  if ((await $.env.get('WE_ROLE')) !== 'master') return undefined
  let got: MasterOrchestration | string
  try {
    got = await lookup($)
  } catch (err) {
    got = err instanceof Error ? err.message : String(err)
  }
  if (typeof got !== 'string') return got
  $.ui.log(`flow: master view unavailable: ${got}`)
  return undefined
}

// The keys /flow shows for a master: its epic, else its stories.
export const masterKeys = (m: MasterOrchestration) => (m.epic ? [m.epic] : m.stories.map(s => s.key))

export const workerLine = (w: MasterWorker) => `⚙ ${w.name} · ${w.state ?? '?'}`

export const otherWorkersLine = (m: MasterOrchestration) =>
  m.otherWorkers.length
    ? `other workers: ${m.otherWorkers.map(w => `${w.name}${w.key ? ` (${w.key})` : ''} · ${w.state ?? '?'}`).join(', ')}`
    : undefined
