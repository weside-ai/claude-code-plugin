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
const fs = require('fs');
const { execFileSync, spawn } = require('child_process');

// Fallback terminal width: stdout is a pipe when Claude Code invokes this
// script, so process.stdout.columns is undefined. Claude Code sets COLUMNS to
// the terminal width before running the script; FALLBACK_WIDTH covers a manual
// run (piped mock input) where neither is set.
const FALLBACK_WIDTH = 150;
const RIGHT_MARGIN = 15; // room for Claude Code's own right-aligned status text
const SEP = ' │ ';

function truncateRight(str, max) {
  // Cuts off the END, keeps the start. Use for branch names: "feat/PROJ-1915-…"
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

// ── PR resolution ───────────────────────────────────────────────────────────
//
// Claude Code supplies `data.pr` when it has associated one with the session.
// It does not always have one: a session whose directory is a plain worktree
// the host never linked shows no PR at all, which is exactly the case an
// orchestration Lead sits in for a whole run. So when the host is silent we
// resolve the PR ourselves — from the branch this script already computed.
//
// Never in the render path. `gh` costs hundreds of milliseconds and the
// statusline runs on every keystroke-ish redraw, so this is
// stale-while-revalidate: the cached answer is returned immediately, and a
// detached refresh is started when it has aged past the TTL. The first render
// on a new branch therefore shows no PR and the next one does.
const PR_CACHE = path.join(os.homedir(), '.claude', '.we-statusline-pr-cache.json');
const PR_TTL_MS = 90_000;

function prCacheKey(dir, branch) {
  return `${dir}\u0000${branch}`;
}

function readPrCache(dir, branch) {
  try {
    const all = JSON.parse(fs.readFileSync(PR_CACHE, 'utf8'));
    return all[prCacheKey(dir, branch)] || null;
  } catch (e) {
    return null; // absent, unreadable or corrupt — all mean "no cached answer"
  }
}

function writePrCache(dir, branch, entry) {
  let all = {};
  try {
    all = JSON.parse(fs.readFileSync(PR_CACHE, 'utf8'));
  } catch (e) {}
  all[prCacheKey(dir, branch)] = entry;
  // Bound the file: keep the 50 most recent keys, so a machine that has seen
  // hundreds of branches does not grow an unbounded cache.
  const keys = Object.keys(all).sort((a, b) => (all[b].ts || 0) - (all[a].ts || 0));
  const trimmed = {};
  for (const k of keys.slice(0, 50)) trimmed[k] = all[k];
  try {
    const tmp = `${PR_CACHE}.${process.pid}.tmp`;
    fs.writeFileSync(tmp, JSON.stringify(trimmed));
    fs.renameSync(tmp, PR_CACHE); // atomic: a concurrent reader never sees a half file
  } catch (e) {}
}

function refreshPrCacheDetached(dir, branch) {
  try {
    const child = spawn(
      process.execPath,
      [__filename, '--refresh-pr', dir, branch],
      { detached: true, stdio: 'ignore' },
    );
    child.unref();
  } catch (e) {}
}

// Re-entry point for the detached refresh above. Runs `gh`, writes the cache,
// exits — it never reads stdin, so it cannot be confused with a render.
if (process.argv[2] === '--refresh-pr') {
  const [, , , dir, branch] = process.argv;
  let entry = { number: null, state: null, ts: Date.now() };
  try {
    const out = execFileSync(
      'gh',
      ['pr', 'list', '--head', branch, '--state', 'open', '--limit', '1',
       '--json', 'number,reviewDecision,isDraft'],
      { cwd: dir, encoding: 'utf8', stdio: ['ignore', 'pipe', 'ignore'], timeout: 15_000 },
    );
    const rows = JSON.parse(out);
    if (rows.length > 0) {
      const decision = rows[0].reviewDecision; // APPROVED | CHANGES_REQUESTED | REVIEW_REQUIRED | null
      entry = {
        number: rows[0].number,
        state: rows[0].isDraft
          ? 'draft'
          : decision === 'APPROVED'
            ? 'approved'
            : decision === 'CHANGES_REQUESTED'
              ? 'changes_requested'
              : 'pending',
        ts: Date.now(),
      };
    }
    // rows.length === 0 keeps `number: null` — that is what clears a PR that
    // was merged or closed, instead of showing a dead number forever.
  } catch (e) {
    // No gh, not authenticated, no network, not a GitHub remote: cache the
    // "nothing known" answer so we do not respawn on every render.
  }
  writePrCache(dir, branch, entry);
  process.exit(0);
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
    // A Lead runs from the main worktree while the work lives elsewhere. If the
    // session declared a focus (written by /we:orchestrate at Step 5.6), show
    // that — cwd would name a branch nobody in this session is working on.
    let focus = null;
    try {
      focus = JSON.parse(fs.readFileSync(
        path.join(os.homedir(), '.claude', 'we-focus', `${data.session_id}.json`), 'utf8'));
    } catch {}
    const dir = focus?.dir || data.workspace?.current_dir || process.cwd();
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

    // PR — the host's own association first (it is authoritative when present),
    // then our cached lookup for the branch above, so a directory the host never
    // linked still shows its PR.
    let prNumber = focus?.pr ?? data.pr?.number;
    let prState = data.pr?.review_state; // approved | pending | changes_requested | draft
    if (prNumber == null && branch) {
      const cached = readPrCache(dir, branch);
      if (cached) {
        prNumber = cached.number;
        prState = cached.state;
      }
      if (!cached || Date.now() - (cached.ts || 0) > PR_TTL_MS) {
        refreshPrCacheDetached(dir, branch);
      }
    }
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
