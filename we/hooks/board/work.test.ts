import { expect, test } from 'claude-code/testing'

import type { PlanFile } from '../plans/plans'
import { buildWork, layoutWork, storiesInScope, workOf } from './work'

const FILES: PlanFile[] = [
  { path: 'docs/plans/wire-saga.md', kind: 'saga', saga: 'wire', status: 'active', title: 'Wire layer' },
  { path: 'docs/plans/wire-cards-epic.md', kind: 'epic', epic: 'wire-cards', saga: 'wire', ticket: 'PROJ-20', status: 'active', title: 'Card goldens' },
  { path: 'docs/plans/money-epic.md', kind: 'epic', epic: 'money', ticket: 'PROJ-60', status: 'selected', title: 'Account currency' },
  { path: 'docs/plans/PROJ-21-story.md', kind: 'story', story: 'PROJ-21', epic: 'wire-cards', title: 'Golden runner' },
  { path: 'docs/plans/PROJ-61-story.md', kind: 'story', story: 'PROJ-61', epic: 'PROJ-60', status: 'approved', title: 'Currency column' },
  { path: 'docs/plans/PROJ-62-story.md', kind: 'story', story: 'PROJ-62', epic: 'PROJ-60', status: 'approved', title: 'Prices per currency' },
  { path: 'docs/plans/PROJ-63-story.md', kind: 'story', story: 'PROJ-63', epic: 'PROJ-60', status: 'approved', title: 'Metering in the account currency' },
  { path: 'docs/plans/PROJ-70-story.md', kind: 'story', story: 'PROJ-70', status: 'draft', title: 'A story without an epic' },
]

test('the keys grow a saga → epic → story tree; a key without a plan is a leaf', async () => {
  const phases = { 'PROJ-21': 'ci', 'PROJ-61': 'merged', 'PROJ-62': 'dev', 'PROJ-63': 'ci-red', 'PROJ-70': 'draft' } as const
  // A story key brings its epic with every story of it, the session's own story first.
  expect(storiesInScope(['PROJ-62', 'PROJ-20', 'PROJ-70', 'PROJ-99'], FILES)).toEqual(['PROJ-21', 'PROJ-61', 'PROJ-62', 'PROJ-63', 'PROJ-70'])
  expect(buildWork(['PROJ-62', 'PROJ-20', 'PROJ-70', 'PROJ-99'], FILES, phases)).toEqual([
    { kind: 'epic', key: 'PROJ-60', title: 'Account currency', status: 'selected', children: [
      { kind: 'story', key: 'PROJ-62', title: 'Prices per currency', phase: 'dev' },
      { kind: 'story', key: 'PROJ-63', title: 'Metering in the account currency', phase: 'ci-red' },
      { kind: 'story', key: 'PROJ-61', title: 'Currency column', phase: 'merged' },
    ] },
    { kind: 'saga', key: 'wire', title: 'Wire layer', status: 'active', children: [
      { kind: 'epic', key: 'PROJ-20', title: 'Card goldens', status: 'active', children: [
        { kind: 'story', key: 'PROJ-21', title: 'Golden runner', phase: 'ci' },
      ] },
    ] },
    { kind: 'story', key: 'PROJ-70', title: 'A story without an epic', phase: 'draft' },
    { kind: 'key', key: 'PROJ-99' },
  ])
})

test('the layout counts merged stories, shows at most eight open ones and fits the room', async () => {
  const stories = Array.from({ length: 11 }, (_, i) => ({
    kind: 'story' as const, key: `PROJ-${100 + i}`, title: `Story number ${i} with a long title to cut`, phase: i < 2 ? ('merged' as const) : ('refined' as const),
  }))
  const text = (room: number) => layoutWork([{ kind: 'epic', key: 'PROJ-1', title: 'Big epic', status: 'active', children: stories }, { kind: 'key', key: 'PROJ-9' }], room)
    .map(line => '  '.repeat(line.depth) + line.parts.map(p => p.text).join(''))
  expect(text(80)).toEqual([
    'Epic PROJ-1 Big epic (active) · 2/11 stories merged',
    '  ● PROJ-102 Story number 2 with a long title to cut  approved',
    '  ● PROJ-103 Story number 3 with a long title to cut  approved',
    '  ● PROJ-104 Story number 4 with a long title to cut  approved',
    '  ● PROJ-105 Story number 5 with a long title to cut  approved',
    '  ● PROJ-106 Story number 6 with a long title to cut  approved',
    '  ● PROJ-107 Story number 7 with a long title to cut  approved',
    '  ● PROJ-108 Story number 8 with a long title to cut  approved',
    '  ● PROJ-109 Story number 9 with a long title to cut  approved',
    'PROJ-9 (no plan)',
    '+ 1 more',
  ])
  expect(text(40)[1]).toBe('  ● PROJ-102 Story number 2 w…  approved')
  for (const line of text(40)) expect(line.length).toBeLessThanOrEqual(40)
})

test('workOf keeps only nodes the pane can draw', async () => {
  expect(workOf(null)).toBeUndefined()
  expect(workOf([
    { kind: 'epic', key: 'LC-1', title: 'Launch', children: [{ kind: 'story', key: 'LC-2', phase: 'nonsense', status: 'drafting' }, { kind: 'bogus' }] },
    'text',
  ])).toEqual([
    { kind: 'epic', key: 'LC-1', title: 'Launch', status: undefined, phase: undefined, children: [
      { kind: 'story', key: 'LC-2', title: undefined, status: 'drafting', phase: undefined, children: undefined },
    ] },
  ])
})
