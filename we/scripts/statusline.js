#!/usr/bin/env node
// Claude Code Statusline — shipped by the "we" plugin (weside.ai).
// Installed by /we:setup via scripts/install_statusline.py, which copies this
// file to ~/.claude/we-statusline.js and points settings.json at the copy.
// Shows: model | branch (+ PR) | dirname | context bar | RAM | cost | rate limits
// Single line, width-aware: segments are built as {plain, colorize} pairs so
// truncation always cuts the plain text (never mid-escape-sequence), and the
// whole line is fit against the terminal width before ANSI colors are applied.

const path = require('path');
const os = require('os');
const { execFileSync } = require('child_process');

// Fallback terminal width: stdout is a pipe when Claude Code invokes this
// script, so process.stdout.columns is undefined. Claude Code sets COLUMNS to
// the terminal width before running the script; FALLBACK_WIDTH covers a manual
// run (piped mock input) where neither is set.
const FALLBACK_WIDTH = 150;
const RIGHT_MARGIN = 15; // room for Claude Code's own right-aligned status text
const SEP = ' │ ';

function truncateRight(str, max) {
  // Cuts off the END, keeps the start. Use for branch names: "feat/WA-1915-…"
  // keeps the ticket key, which is the part that matters.
  if (str.length <= max) return str;
  if (max <= 1) return str.slice(0, max);
  return str.slice(0, max - 1) + '…';
}

function truncateLeft(str, max) {
  // Cuts off the START, keeps the end. Use for paths: ".../my-service" keeps
  // the meaningful tail.
  if (str.length <= max) return str;
  if (max <= 1) return str.slice(-max);
  return '…' + str.slice(-(max - 1));
}

let input = '';
process.stdin.setEncoding('utf8');
process.stdin.on('data', chunk => input += chunk);
process.stdin.on('end', () => {
  try {
    const data = JSON.parse(input);

    // ---- gather raw values ----

    // Model (from actual runtime, not config)
    const modelName = data.model?.display_name || 'Claude';
    const modelId = data.model?.id || '';
    const is1M = modelId.includes('1m') && !modelName.includes('1M');
    const modelPlain = is1M ? `${modelName} (1M)` : modelName;

    // Git branch
    const dir = data.workspace?.current_dir || process.cwd();
    let branch = '';
    try {
      branch = execFileSync(
        'git',
        ['--no-optional-locks', 'branch', '--show-current'],
        { cwd: dir, encoding: 'utf8', stdio: ['ignore', 'pipe', 'ignore'] },
      ).trim();
    } catch (e) {}

    const worktree = data.worktree?.name;
    const branchPlainFull = worktree ? `${branch || '(detached)'} (${worktree})` : branch;

    // PR (documented in the statusline JSON schema; absent when there is none)
    const prNumber = data.pr?.number;
    const prState = data.pr?.review_state; // approved | pending | changes_requested | draft
    const prPlain = prNumber != null ? `PR #${prNumber}` : '';
    const prColor =
      prState === 'approved' ? '32' :
      prState === 'changes_requested' ? '31' :
      prState === 'draft' ? '2' : '33'; // pending / unknown

    // Directory
    const dirnamePlain = path.basename(dir);

    // Context window (used_percentage from runtime) — fixed width
    let ctxSeg = null;
    const used = data.context_window?.used_percentage;
    if (used != null) {
      const u = Math.round(used);
      const filled = Math.floor(u / 10);
      const bar = '█'.repeat(filled) + '░'.repeat(10 - filled);
      const color = u < 50 ? '32' : u < 70 ? '33' : u < 85 ? '38;5;208' : '5;31';
      ctxSeg = { plain: `${bar} ${u}%`, color: (s) => `\x1b[${color}m${s}\x1b[0m` };
    }

    // RAM — fixed width, optional (dropped first if the line is too long)
    let ram = null;
    try {
      const pct = Math.round(((os.totalmem() - os.freemem()) / os.totalmem()) * 100);
      const color = pct < 70 ? '32' : pct < 85 ? '33' : '31';
      ram = { plain: `RAM ${pct}%`, color: (s) => `\x1b[${color}m${s}\x1b[0m` };
    } catch (e) {}

    // Cost — fixed width, optional
    let cost = null;
    const totalCost = data.cost?.total_cost_usd;
    if (totalCost != null) {
      cost = { plain: `$${totalCost.toFixed(3)}`, color: (s) => `\x1b[2m${s}\x1b[0m` };
    }

    // Rate limits — fixed width, optional
    let rateLimits = null;
    const rl5h = data.rate_limits?.five_hour?.used_percentage;
    const rl7d = data.rate_limits?.seven_day?.used_percentage;
    if (rl5h != null || rl7d != null) {
      const r5 = rl5h != null ? Math.round(rl5h) : null;
      const r7 = rl7d != null ? Math.round(rl7d) : null;
      const colorOf = (p) => (p == null ? '2' : p < 50 ? '32' : p < 80 ? '33' : '31');
      rateLimits = {
        plain: `5h:${r5 != null ? r5 + '%' : '-'} 7d:${r7 != null ? r7 + '%' : '-'}`,
        color: () =>
          `\x1b[2m5h:\x1b[0m\x1b[${colorOf(r5)}m${r5 != null ? r5 + '%' : '-'}\x1b[0m ` +
          `\x1b[2m7d:\x1b[0m\x1b[${colorOf(r7)}m${r7 != null ? r7 + '%' : '-'}\x1b[0m`,
      };
    }

    // ---- fit against terminal width ----

    const width = process.stdout.columns || Number(process.env.COLUMNS) || FALLBACK_WIDTH;
    const budget = Math.max(40, width - RIGHT_MARGIN);

    // Variable-length segments, each with a floor it may be truncated down
    // to. Branch and PR are never dropped whole — they're the whole point.
    const model = { plain: modelPlain, floor: 10, color: (s) => `\x1b[2m${s}\x1b[0m` };
    const branchSeg = (branch || worktree)
      ? { plain: branchPlainFull, floor: 14, color: (s) => `\x1b[36m${s}\x1b[0m`, dir: 'right' }
      : null;
    const prSeg = prPlain
      ? { plain: prPlain, floor: prPlain.length, color: (s) => `\x1b[${prColor}m${s}\x1b[0m` }
      : null;
    const dirSeg = { plain: dirnamePlain, floor: 10, color: (s) => `\x1b[2m${s}\x1b[0m`, dir: 'left' };

    // Optional fixed-width segments, dropped whole (in this order) if the
    // line still doesn't fit after shrinking the variable ones.
    let opts = [ram, cost, rateLimits];

    function widthOf(list) {
      const visible = list.filter(Boolean);
      const sum = visible.reduce((acc, s) => acc + s.plain.length, 0);
      return sum + Math.max(0, visible.length - 1) * SEP.length;
    }

    let required = [model, branchSeg, prSeg, dirSeg, ctxSeg];

    // Drop optional segments (lowest priority first) while over budget.
    while (widthOf(required.concat(opts)) > budget && opts.some(Boolean)) {
      const idx = opts.findIndex(Boolean);
      if (idx === -1) break;
      opts[idx] = null;
    }

    // Still over budget: shrink variable segments (model, dirname, branch —
    // never PR) down to their floors, largest offender first.
    let guard = 0;
    while (widthOf(required.concat(opts)) > budget && guard < 400) {
      guard++;
      const shrinkable = [model, branchSeg, dirSeg].filter((s) => s && s.plain.length > s.floor);
      if (shrinkable.length === 0) break;
      shrinkable.sort((a, b) => b.plain.length - a.plain.length);
      const s = shrinkable[0];
      const newLen = Math.max(s.floor, s.plain.length - 1);
      s.plain = s.dir === 'left' ? truncateLeft(s.plain, newLen) : truncateRight(s.plain, newLen);
    }

    // ---- assemble ----
    const parts = [model, branchSeg, prSeg, dirSeg, ctxSeg, ...opts]
      .filter(Boolean)
      .map((s) => s.color(s.plain));

    process.stdout.write(parts.join(SEP));
  } catch (e) {
    // Silent fail
  }
});
