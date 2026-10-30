import { expect, test } from 'claude-code/testing'

import { parsePlanFiles, planGrep } from './plans'

test('parsePlanFiles reads every link field and the first heading; the first value wins, null is none', async () => {
  const out = [
    'origin/main:docs/plans/wire-saga.md:saga: wire',
    'origin/main:docs/plans/wire-saga.md:status: active',
    'origin/main:docs/plans/wire-saga.md:# Saga: Wire layer',
    'origin/main:docs/plans/money-epic.md:epic: money',
    'origin/main:docs/plans/money-epic.md:saga: null',
    'origin/main:docs/plans/money-epic.md:ticket: PROJ-60',
    'origin/main:docs/plans/money-epic.md:status: selected',
    'origin/main:docs/plans/money-epic.md:# Epic: Account currency',
    'origin/main:docs/plans/money-epic.md:status: a later body line',
    'origin/main:docs/plans/PROJ-62-story.md:story: PROJ-62',
    'origin/main:docs/plans/PROJ-62-story.md:epic: PROJ-60',
    'origin/main:docs/plans/PROJ-62-story.md:# Plan: Prices per currency',
    'origin/main:docs/plans/PROJ-62-story.md:# a second heading',
  ].join('\n')
  expect(parsePlanFiles(out)).toEqual([
    { path: 'docs/plans/wire-saga.md', kind: 'saga', saga: 'wire', status: 'active', title: 'Wire layer' },
    { path: 'docs/plans/money-epic.md', kind: 'epic', epic: 'money', ticket: 'PROJ-60', status: 'selected', title: 'Account currency' },
    { path: 'docs/plans/PROJ-62-story.md', kind: 'story', story: 'PROJ-62', epic: 'PROJ-60', title: 'Prices per currency' },
  ])
})

test('planGrep asks for the link fields and headings of the given paths on the base', async () => {
  expect(planGrep('origin/main', ['docs/plans/*-story.md'])).toEqual([
    'grep', '-E', '-e', '^(story|epic|saga|ticket|status):', '-e', '^# ', 'origin/main', '--', 'docs/plans/*-story.md',
  ])
})
