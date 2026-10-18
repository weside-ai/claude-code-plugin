import { expect, test } from 'claude-code/testing'

import * as phaseModule from './phase'
import { checksPhase, parsePlans, phaseOf } from './phase'
import type { Pr } from './phase'

const pr = (state: Pr['state'], checks: Pr['statusCheckRollup'] = []): Pr => ({
  number: 1, state, headRefName: 'feat/PROJ-1-x', title: 'x', autoMergeRequest: null, statusCheckRollup: checks,
})

test('phase follows the orchestrate state table, first match wins', async () => {
  expect(phaseOf({ prs: [], aheadBranches: [] })).toBe('idea')
  expect(phaseOf({ plan: { key: 'PROJ-1', title: '' }, prs: [], aheadBranches: [] })).toBe('draft')
  expect(phaseOf({ plan: { key: 'PROJ-1', title: '', status: 'approved' }, prs: [], aheadBranches: [] })).toBe('refined')
  expect(phaseOf({ prs: [], aheadBranches: ['feat/PROJ-1-x'] })).toBe('dev')
  expect(phaseOf({ prs: [pr('OPEN', [{ name: 'CI Summary', status: 'IN_PROGRESS', conclusion: null }])], aheadBranches: [] })).toBe('ci')
  expect(phaseOf({ prs: [pr('CLOSED'), pr('MERGED')], aheadBranches: ['feat/PROJ-1-x'] })).toBe('merged')
})

test('a red Codex Review is advisory, any other red check is not', async () => {
  expect(checksPhase([{ name: 'Codex Review', status: 'COMPLETED', conclusion: 'FAILURE' }, { name: 'CI Summary', status: 'COMPLETED', conclusion: 'SUCCESS' }])).toBe('ready')
  expect(checksPhase([{ name: 'Claude Review', status: 'COMPLETED', conclusion: 'FAILURE' }])).toBe('ci-red')
  expect(checksPhase([{ context: 'legacy', state: 'PENDING' }])).toBe('ci')
})

test('parsePlans reads key, status and title from git grep output', async () => {
  const out = [
    'origin/main:docs/plans/PROJ-12-story.md:story: PROJ-12',
    'origin/main:docs/plans/PROJ-12-story.md:epic: PROJ-10',
    'origin/main:docs/plans/PROJ-12-story.md:status: approved',
    'origin/main:docs/plans/PROJ-12-story.md:# Plan: Discord groups like Telegram',
  ].join('\n')
  expect(parsePlans(out)).toEqual([{ key: 'PROJ-12', title: 'Discord groups like Telegram', status: 'approved', epic: 'PROJ-10' }])
})

test('stages: a story on an open PR with red CI and a green Claude review', async () => {
  const stages = phaseModule.stagesOf({
    plan: { key: 'PROJ-1', title: '', status: 'approved' },
    prs: [{ ...pr('OPEN', [
      { name: 'CI Summary', status: 'COMPLETED', conclusion: 'FAILURE' },
      { name: 'Claude Review', status: 'COMPLETED', conclusion: 'SUCCESS' },
      { name: 'Codex Review', status: 'COMPLETED', conclusion: 'FAILURE' },
    ]), autoMergeRequest: { enabledAt: 'x' } }],
    aheadBranches: ['feat/PROJ-1-x'],
    ahead: 3,
  })
  expect(stages.map(s => `${s.name}:${s.light}`)).toEqual([
    'Plan:done', 'Approval:done', 'Build:done', 'PR:done', 'CI:red', 'Review:done', 'Merge:active',
  ])
  expect(stages[4]?.note).toContain('CI Summary')
  expect(stages[5]?.note).toContain('Codex ✗ (advisory)')
})

test('stages: a draft plan waits for approval, nothing built yet', async () => {
  const stages = phaseModule.stagesOf({ plan: { key: 'PROJ-1', title: '', status: 'draft' }, prs: [], aheadBranches: [], ahead: 0 })
  expect(stages.map(s => s.light)).toEqual(['done', 'active', 'todo', 'todo', 'todo', 'todo', 'todo'])
})

test('keysIn finds each ticket key once, in order', async () => {
  expect(phaseModule.keysIn('feat/PROJ-12-discord and PROJ-10, PROJ-12')).toEqual(['PROJ-12', 'PROJ-10'])
  expect(phaseModule.keysIn('main, utf-8')).toEqual([])
  expect(phaseModule.keysIn('feat/proj-12-x', 'PROJ')).toEqual(['PROJ-12'])
})
