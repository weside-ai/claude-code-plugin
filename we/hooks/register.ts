// The we plugin's one hooks module: the /flow and /board panes. The engine takes one
// session.start hook per module without a matcher, so it starts both here.
import type { Register } from 'claude-code'

import { registerBoard, startBoard } from './board/register'
import { registerFlow, startFlow } from './flow/register'

export const register: Register = (on, options) => {
  registerFlow(on, options)
  registerBoard(on, options)
  on('session.start', async ($, e, next) => {
    await startFlow($)
    await startBoard($, options)
    return next(e)
  })
}
