import { expect, mock, test } from 'claude-code/testing'

const STORY = 'docs/plans/PROJ-12-story.md'
const answers: [RegExp, string][] = [
  [/^git rev-parse --show-toplevel/, '/repo\n'],
  [/^git grep -l -E \^ticket: PROJ-10\$/, 'origin/main:docs/plans/channels-epic.md\n'],
  [/^git grep -h -m1/, '# Epic: Channels\n'],
  [/^git grep -l -E \^epic: \(PROJ-10\|channels\)\$/, `origin/main:${STORY}\norigin/main:docs/plans/PROJ-14-story.md\n`],
  [/^git grep -E -e/, [
    `origin/main:${STORY}:story: PROJ-12`, `origin/main:${STORY}:epic: PROJ-10`, `origin/main:${STORY}:status: approved`,
    `origin/main:${STORY}:# Plan: Discord groups`,
    'origin/main:docs/plans/PROJ-14-story.md:story: PROJ-14', 'origin/main:docs/plans/PROJ-14-story.md:epic: PROJ-10',
    'origin/main:docs/plans/PROJ-14-story.md:status: approved', 'origin/main:docs/plans/PROJ-14-story.md:# Plan: Guild identity',
  ].join('\n')],
  [/^git for-each-ref/, 'main\norigin/feat/PROJ-14-guild\n'],
  [/^git worktree list/, 'worktree /repo\nbranch refs/heads/main\n'],
  [/^git rev-list --count/, '3\n'],
  [/^gh pr list/, JSON.stringify([
    { number: 5072, state: 'MERGED', headRefName: 'feat/PROJ-12-discord', title: 'x', autoMergeRequest: null, statusCheckRollup: [] },
    { number: 5090, state: 'OPEN', headRefName: 'feat/PROJ-14-guild', title: 'y', autoMergeRequest: null,
      statusCheckRollup: [{ name: 'CI Summary', status: 'COMPLETED', conclusion: 'FAILURE' }, { name: 'Claude Review', status: 'IN_PROGRESS', conclusion: null }] },
  ])],
]

test('/flow PROJ-10 fills the pane after the command returned', async ($, on) => {
  const clock = mock.clock(on)
  mock.store(on)
  on('process.run', (_$, e) => {
    const line = e.argv.join(' ')
    const hit = answers.find(([pattern]) => pattern.test(line))
    return { value: { exitCode: 0, stdout: hit?.[1] ?? '', stderr: '', isStdoutTruncated: false, isStderrTruncated: false } }
  })
  // The Board button opens the board pane, which looks for its file.
  on('env.get', () => ({ value: '/home/me' }))
  on('fs.exists', () => ({ value: false }))
  const toasts: string[] = []
  on('ui.toast', (_$, e) => {
    toasts.push(String((e as { text?: unknown }).text))
    return { value: undefined }
  })
  const opened: string[] = []
  on('ui.open', (_$, e) => {
    opened.push(String((e as { id?: unknown }).id))
    return { value: { isPlaced: true } }
  })
  on('ui.status', () => ({ value: undefined }))
  const logged: string[] = []
  on('ui.log', (_$, e) => {
    logged.push(String((e as { text?: unknown }).text))
    return { value: undefined }
  })
  const ran: string[] = []
  on('command.run', { command: 'we:ci-review' }, (_$, e) => {
    ran.push(`${e.command} ${e.args}`)
    return { text: 'ok' }
  })
  on('command.run', { command: 'we:standup' }, (_$, e) => {
    ran.push(`${e.command} ${e.args}`)
    return { text: 'ok' }
  })

  const answer = await $.command.run({ command: 'flow', args: 'PROJ-10', origin: { kind: 'composer' } } as never)
  expect(answer.text).toContain('PROJ-10')
  await clock.settle()
  expect(logged).toEqual([])

  for (const surface of ['terminal', 'desktop'] as const) {
    const ui = await $.ui.mount({ plugin: 'we', surface, component: 'Pane', requestId: 'we-flow', props: { bodyColumns: 70 } as never })
    expect(await ui.find({ type: 'Text', text: /CI red/ })).toBeDefined()
    expect(await ui.find({ type: 'Text', text: /PROJ-12/ })).toBeDefined()
    expect(await ui.find({ type: 'Text', text: /1\/2 merged/ })).toBeDefined()
    expect(await ui.find({ type: 'Text', text: /✗ CI Summary/ })).toBeDefined()
    expect(await ui.find({ type: 'Text', text: /Claude running/ })).toBeDefined()
    await ui.press({ key: 'PROJ-14-ci' })
    await ui.press({ key: 'PROJ-14-standup' })
    await ui.press({ key: 'board' })
    await ui.unmount()
  }
  expect(ran).toEqual(['we:ci-review 5090', 'we:standup PROJ-14', 'we:ci-review 5090', 'we:standup PROJ-14'])
  await clock.settle()
  expect(toasts).toEqual([])
  expect(opened).toEqual(['we-flow', 'we-board', 'we-board'])
})
