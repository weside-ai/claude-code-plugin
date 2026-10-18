import { expect, mock, test } from 'claude-code/testing'

const PLAN = 'origin/main:docs/plans/PROJ-7-story.md'
const answers: [RegExp, string][] = [
  [/^git rev-parse --show-toplevel/, '/repo\n'],
  [/^git grep -E -e/, [`${PLAN}:story: PROJ-7`, `${PLAN}:epic: PROJ-3`, `${PLAN}:status: approved`, `${PLAN}:# Plan: Tenant onboarding`].join('\n')],
  [/^git for-each-ref/, 'main\norigin/fix/PROJ-7-claim\n'],
  [/^git worktree list/, 'worktree /repo\nbranch refs/heads/main\n'],
  [/^git rev-list --count/, '1\n'],
  [/^gh pr list/, JSON.stringify([
    { number: 41, state: 'MERGED', headRefName: 'feat/PROJ-7-probe', title: 'a', autoMergeRequest: null, statusCheckRollup: [] },
    { number: 52, state: 'MERGED', headRefName: 'feat/PROJ-7-tenants', title: 'b', autoMergeRequest: null, statusCheckRollup: [] },
    { number: 60, state: 'OPEN', headRefName: 'fix/PROJ-7-claim', title: 'c', autoMergeRequest: null,
      statusCheckRollup: [{ name: 'CI Summary', status: 'IN_PROGRESS', conclusion: null }] },
  ])],
]

test('a story on its own is a card: its open follow-up PR, the merged ones before it, its epic', async ($, on) => {
  const clock = mock.clock(on)
  mock.store(on)
  on('process.run', (_$, e) => {
    const hit = answers.find(([pattern]) => pattern.test(e.argv.join(' ')))
    return { value: { exitCode: 0, stdout: hit?.[1] ?? '', stderr: '', isStdoutTruncated: false, isStderrTruncated: false } }
  })
  on('ui.open', () => ({ value: { isPlaced: true } }))
  on('ui.status', () => ({ value: undefined }))

  await $.command.run({ command: 'flow', args: 'proj-7', origin: { kind: 'composer' } } as never)
  await clock.settle()

  const ui = await $.ui.mount({ plugin: 'we', surface: 'terminal', component: 'Pane', requestId: 'we-flow', props: { bodyColumns: 70 } as never })
  expect(await ui.find({ type: 'Text', text: /CI running/ })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: /#60 · earlier #41 ✓ #52 ✓/ })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: /epic PROJ-3/ })).toBeDefined()
  await ui.unmount()
})
