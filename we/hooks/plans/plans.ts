// What /flow and /board both read from a repo: the plan files on the default branch (git grep) and the
// PRs of their keys (gh). Everything that takes $ is a function declaration, the only form the engine
// follows past an import.
import type { EngineInterface } from 'claude-code'

type $ = EngineInterface

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

export type PlanKind = 'saga' | 'epic' | 'story'

// One plan file's frontmatter links (epic-plan.md § Links; `saga` read only for older files) and its first heading.
export type PlanFile = {
  path: string
  kind?: PlanKind
  story?: string
  epic?: string
  saga?: string
  ticket?: string
  status?: string
  // An epic's finish line (epic-plan.md § Finish line): its story keys, its start, its open extensions.
  line?: string[]
  created?: string
  extensions?: number
  title: string
}

// The `git grep` arguments that print every link field, the finish line, the level-1 and level-2
// headings and the open checklist items of `paths` on `base` (an open item counts only under an
// epic's `## Extensions`).
export const planGrep = (base: string, paths: readonly string[]) =>
  ['grep', '-E', '-e', '^(story|epic|saga|ticket|status|line|created):', '-e', '^##? ', '-e', '^- \\[ \\] ', base, '--', ...paths]

export const ALL_PLANS = ['docs/plans/*-saga.md', 'docs/plans/*-epic.md', 'docs/plans/*-story.md']

const KIND = /-(saga|epic|story)\.md$/
const NONE = new Set(['', 'null', '~'])

// Parses `git grep -e ... <rev> -- <files>` output, `<rev>:<path>:<line>` per hit. The first value of a
// field wins (the frontmatter comes before the body); `null` counts as no value.
export const parsePlanFiles = (grepOut: string): PlanFile[] => {
  const byPath = new Map<string, PlanFile>()
  const section = new Map<string, string>()
  for (const raw of grepOut.split('\n')) {
    const m = /^[^:]+:(docs\/plans\/[^:]+):(.*)$/.exec(raw)
    const path = m?.[1]
    if (!path) continue
    const line = m?.[2] ?? ''
    const plan = byPath.get(path) ?? { path, kind: KIND.exec(path)?.[1] as PlanKind | undefined, title: '' }
    const field = /^(story|epic|saga|ticket|status|line|created):\s*(.*)$/.exec(line)
    if (field && !section.has(path)) {
      const value = (field[2] ?? '').trim()
      if (field[1] === 'line') {
        if (plan.line === undefined) plan.line = value.replace(/^\[|\]$/g, '').split(',').map(k => k.trim()).filter(Boolean)
      } else {
        const name = field[1] as 'story' | 'epic' | 'saga' | 'ticket' | 'status' | 'created'
        if (plan[name] === undefined && !NONE.has(value)) plan[name] = value
      }
    } else if (line.startsWith('## ')) {
      section.set(path, line.slice(3).trim())
    } else if (line.startsWith('- [ ] ')) {
      if (plan.kind === 'epic' && section.get(path) === 'Extensions') plan.extensions = (plan.extensions ?? 0) + 1
    } else if (!plan.title && line.startsWith('# ')) {
      plan.title = line.replace(/^#\s*((Plan|Epic|Saga):\s*)?/, '').trim()
    }
    byPath.set(path, plan)
  }
  return [...byPath.values()]
}

export async function git($: $, cwd: string, argv: string[], timeoutMs = 30_000): Promise<string> {
  const run = await $.process.run(['git', ...argv], { cwd, timeoutMs })
  // git grep answers 1 for "no match", which is a valid empty answer here.
  if (run.exitCode !== 0 && !(argv[0] === 'grep' && run.exitCode === 1)) {
    throw new Error(`git ${argv[0]}: ${run.stderr.trim().split('\n')[0] ?? run.exitCode}`)
  }
  return run.stdout
}

export async function defaultBranch($: $, top: string): Promise<string> {
  const head = await $.process.run(['git', 'symbolic-ref', '--short', 'refs/remotes/origin/HEAD'], { cwd: top })
  return head.exitCode === 0 && head.stdout.trim() ? head.stdout.trim() : 'origin/main'
}

export async function loadPrs($: $, cwd: string, keys: string[]): Promise<Pr[]> {
  const prs: Pr[] = []
  // GitHub search takes at most five boolean operators per query.
  for (let i = 0; i < keys.length; i += 6) {
    const run = await $.process.run(
      [
        'gh', 'pr', 'list', '--state', 'all', '--limit', '100',
        '--search', keys.slice(i, i + 6).join(' OR '),
        '--json', 'number,state,headRefName,title,autoMergeRequest,statusCheckRollup,mergeStateStatus,isDraft',
      ],
      { cwd, timeoutMs: 30_000 },
    )
    if (run.exitCode !== 0) throw new Error(`gh pr list: ${run.stderr.trim().split('\n')[0]}`)
    prs.push(...(JSON.parse(run.stdout) as Pr[]))
  }
  return prs
}
