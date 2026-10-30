import { expect, mock, test } from 'claude-code/testing'

import { paint } from './paint'

// Two masters in one repo with plan files, one carrying its own tree (`work`), one without keys.
const BOARD = JSON.stringify({
  updated: '2026-10-30T21:00:00+00:00',
  updated_by: 'Orchestrator',
  sessions: [
    { name: 'billing', role: 'master', keys: ['PROJ-60'], now: 'three stories in build', state: 'build', priority: 1, cwd: '/repo' },
    { name: 'meter', role: 'worker', parent: 'billing', keys: ['PROJ-63'], now: 'CI', state: 'ci', pr: 564 },
    { name: 'wire', role: 'master', keys: ['PROJ-21', 'PROJ-99'], state: 'build', priority: 2, cwd: '/repo' },
    { name: 'brand', role: 'master', state: 'build', priority: 3, cwd: '/docs',
      work: [{ kind: 'epic', key: 'LC-1', title: 'Launch kit', status: 'active', children: [
        { kind: 'story', key: 'LC-2', title: 'Press page', phase: 'dev' },
        { kind: 'story', key: 'LC-3', title: 'Logo files', phase: 'merged' },
      ] }] },
    { name: 'ops', role: 'master', state: 'build', priority: 4 },
  ],
})

const P = 'origin/main:docs/plans'
const GREP = [
  `${P}/wire-saga.md:saga: wire`, `${P}/wire-saga.md:status: active`, `${P}/wire-saga.md:# Saga: Wire layer in Rust`,
  `${P}/wire-cards-epic.md:epic: wire-cards`, `${P}/wire-cards-epic.md:saga: wire`, `${P}/wire-cards-epic.md:ticket: PROJ-20`,
  `${P}/wire-cards-epic.md:status: active`, `${P}/wire-cards-epic.md:# Epic: Card goldens`,
  `${P}/money-epic.md:epic: money`, `${P}/money-epic.md:saga: null`, `${P}/money-epic.md:ticket: PROJ-60`,
  `${P}/money-epic.md:status: selected`, `${P}/money-epic.md:# Epic: Account currency — one currency everywhere money appears`,
  ...[
    ['PROJ-21', 'wire-cards', 'approved', 'Golden runner for the card suite'],
    ['PROJ-61', 'PROJ-60', 'approved', 'Currency column on the account'],
    ['PROJ-62', 'PROJ-60', 'approved', 'Prices per currency in the catalogue'],
    ['PROJ-63', 'PROJ-60', 'approved', 'Metering in the account currency'],
    ['PROJ-64', 'PROJ-60', 'draft', 'Invoices name the currency'],
  ].flatMap(([key, epic, status, title]) => [
    `${P}/${key}-story.md:story: ${key}`, `${P}/${key}-story.md:epic: ${epic}`, `${P}/${key}-story.md:status: ${status}`, `${P}/${key}-story.md:# Plan: ${title}`,
  ]),
].join('\n')

const pr = (number: number, state: string, branch: string, checks: unknown[] = []) =>
  ({ number, state, headRefName: branch, title: branch, autoMergeRequest: null, statusCheckRollup: checks })
const PRS = JSON.stringify([
  pr(560, 'MERGED', 'feat/PROJ-61-column'),
  pr(564, 'OPEN', 'feat/PROJ-63-metering', [{ name: 'CI Summary', status: 'IN_PROGRESS', conclusion: null }]),
  pr(570, 'OPEN', 'feat/PROJ-21-runner', [{ name: 'CI Summary', status: 'COMPLETED', conclusion: 'FAILURE' }]),
])

const RUN = (stdout: string) => ({ value: { exitCode: 0, stdout, stderr: '', isStdoutTruncated: false, isStderrTruncated: false } })

const BILLING_100 = `
╭──────────────────────────────────────────────────────────────────────────────────────────────────╮
│ ● billing  PROJ-60  gone  P1  [ ▾ Work ]                                                         │
│ three stories in build                                                                           │
│ Epic PROJ-60 Account currency — one currency everywhere money a… (selected) · 1/4 stories merged │
│   ● PROJ-63 Metering in the account currency  CI                                                 │
│   ● PROJ-62 Prices per currency in the catalogue  build                                          │
│   ● PROJ-64 Invoices name the currency  plan                                                     │
│                                                                                                  │
│ └ ● meter  PROJ-63  #564  gone  CI                                                               │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯`

test('/board: the Work toggle opens a box tree derived from plan files and PRs, one fetch per repo', async ($, on) => {
  const clock = mock.clock(on, { now: Date.parse('2026-10-30T21:10:00Z') })
  mock.store(on)
  on('env.get', () => ({ value: '/home/me' }))
  on('fs.exists', (_$, e) => ({ value: !String((e as { path?: unknown }).path).endsWith('.jsonl') }))
  on('fs.stat', () => ({ value: { kind: 'file', size: 1, mtimeMs: 1, isLink: false } }))
  on('fs.read', () => ({ value: BOARD }))
  on('ui.open', () => ({ value: { isPlaced: true } }))
  const logged: string[] = []
  on('ui.log', (_$, e) => {
    logged.push(String((e as { text?: unknown }).text))
    return { value: undefined }
  })
  const ran: string[] = []
  on('process.run', (_$, e) => {
    const line = e.argv.join(' ')
    ran.push(`${e.init?.cwd ?? ''} ${line}`)
    if (e.argv[0] === 'python3') return RUN('{"sessions":[]}')
    if (line.startsWith('git symbolic-ref')) return RUN('origin/main\n')
    if (line.startsWith('git grep')) return RUN(GREP)
    if (line.startsWith('gh pr list')) return RUN(PRS)
    if (line.startsWith('git for-each-ref')) return RUN('main\nfeat/PROJ-62-prices\n')
    if (line.startsWith('git rev-list')) return RUN('4\n')
    return RUN('')
  })
  const work = () => ran.filter(r => / (git (fetch|grep|for-each-ref)|gh pr list)/.test(r))

  await $.command.run({ command: 'board', args: '', origin: { kind: 'composer' } } as never)
  await clock.settle()

  const draw = async (columns: number) => {
    const ui = await $.ui.mount({ plugin: 'we', surface: 'terminal', component: 'Pane', requestId: 'we-board', props: { bodyColumns: columns } as never })
    const lines = paint((await ui.drawn()) as never, columns)
    await ui.unmount()
    return lines
  }
  const press = async (key: string) => {
    const ui = await $.ui.mount({ plugin: 'we', surface: 'terminal', component: 'Pane', requestId: 'we-board', props: { bodyColumns: 100 } as never })
    await ui.press({ key })
    await ui.unmount()
    await clock.settle()
  }

  // Closed, every box is today's plus its toggle, and nothing reads git or GitHub.
  const closed = await draw(100)
  expect(closed).toContain('│ ● billing  PROJ-60  gone  P1  [ ▸ Work ]'.padEnd(99) + '│')
  expect(closed.some(line => line.startsWith('│ ● ops') && !line.includes('Work'))).toBe(true)
  expect(work()).toEqual([])

  await press('work-billing')
  await press('work-wire')
  await press('work-brand')
  expect(logged).toEqual([])
  const wide = await draw(100)
  expect(`\n${wide.slice(wide.findIndex(l => l.includes('billing')) - 1, wide.findIndex(l => l.includes('└ ● meter')) + 2).join('\n')}`).toBe(BILLING_100)
  expect(wide).toContain('│ Epic LC-1 Launch kit (active) · 1/2 stories merged'.padEnd(99) + '│')
  expect(wide.some(line => line.includes('PROJ-99 (no plan)'))).toBe(true)
  expect(wide.some(line => line.includes('Saga Wire layer in Rust (active)'))).toBe(true)
  const narrow = await draw(60)
  expect(narrow.filter(line => line.startsWith('│')).every(line => line.length === 60 && line.endsWith('│'))).toBe(true)
  // Two boxes in one repo shared one fetch; the box with its own tree read nothing.
  expect(work().filter(r => r.includes('git fetch'))).toEqual(['/repo git fetch origin --quiet'])
  expect(work().some(r => r.startsWith('/docs'))).toBe(false)

  // A refresh fetches each repo once for all its open boxes; a closed box keeps its toggle closed.
  const before = work().length
  await press('refresh')
  expect(work().slice(before).filter(r => r.includes('git fetch'))).toEqual(['/repo git fetch origin --quiet'])
  await press('work-billing')
  const again = await draw(100)
  expect(again).toContain('│ ● billing  PROJ-60  gone  P1  [ ▸ Work ]'.padEnd(99) + '│')
  expect(again.some(line => line.includes('Prices per currency'))).toBe(false)
})
