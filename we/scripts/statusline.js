#!/usr/bin/env node
// Claude Code Statusline — shipped by the "we" plugin (weside.ai).
// Installed by /we:setup via scripts/install_statusline.py, which copies this
// file to ~/.claude/we-statusline.js and points settings.json at the copy.
// Shows: companion | model | branch (+ PR) | dirname | context bar | bg sessions | RAM | cost | rate limits
// With WE_CSWAP_FEED_ACCOUNTS set it also feeds rate limits to cswap (section "Rate limits per account").
// Single line, width-aware: segments are built as {plain, colorize} pairs so
// truncation always cuts the plain text (never mid-escape-sequence), and the
// whole line is fit against the terminal width before ANSI colors are applied.

const path = require('path');
const os = require('os');
const fs = require('fs');
const { execFileSync, spawn, spawnSync } = require('child_process');

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

// ── Background sessions ─────────────────────────────────────────────────────
//
// Sessions started with `claude --bg` have no window: the user sees them only
// after opening the agents view. This segment counts them so a running worker
// is visible at a glance. `claude agents --json` costs ~300 ms, so it follows
// the PR cache's stale-while-revalidate: render reads the cache, a detached
// refresh rewrites it once it is older than the TTL.
const BG_CACHE = path.join(os.homedir(), '.claude', '.we-statusline-bg-cache.json');
const BG_TTL_MS = 10_000;

function readBgCache() {
  try {
    return JSON.parse(fs.readFileSync(BG_CACHE, 'utf8'));
  } catch (e) {
    return null;
  }
}

const BG_LOCK = `${BG_CACHE}.lock`;
const BG_LOCK_STALE_MS = 20_000; // longer than the refresh child's 15 s timeout

// Claims the one refresh per TTL window across every open session (O_EXCL), so a cold cache does
// not start a `claude agents` per redraw; a lock older than the child's timeout is taken over.
function claimSlot(file, staleMs) {
  try {
    fs.closeSync(fs.openSync(file, 'wx'));
    return true;
  } catch (e) {
    try {
      if (Date.now() - fs.statSync(file).mtimeMs < staleMs) return false;
      fs.unlinkSync(file);
      fs.closeSync(fs.openSync(file, 'wx'));
      return true;
    } catch (e2) {
      return false;
    }
  }
}

function claimBgRefresh() {
  return claimSlot(BG_LOCK, BG_LOCK_STALE_MS);
}

function refreshBgCacheDetached() {
  if (!claimBgRefresh()) return;
  try {
    const child = spawn(process.execPath, [__filename, '--refresh-bg'], { detached: true, stdio: 'ignore' });
    child.unref();
  } catch (e) {}
}

if (process.argv[2] === '--refresh-bg') {
  let sessions = [];
  try {
    const out = execFileSync('claude', ['agents', '--json'], {
      encoding: 'utf8', stdio: ['ignore', 'pipe', 'ignore'], timeout: 15_000,
    });
    sessions = JSON.parse(out)
      .filter((a) => a.kind === 'background')
      .map((a) => ({ sessionId: a.sessionId, working: a.state === 'working' || a.status === 'busy' }));
  } catch (e) {
    // No claude on PATH or an unparsable answer: cache "none" so we do not respawn on every render.
  }
  try {
    const tmp = `${BG_CACHE}.${process.pid}.tmp`;
    fs.writeFileSync(tmp, JSON.stringify({ ts: Date.now(), sessions }));
    fs.renameSync(tmp, BG_CACHE);
  } catch (e) {}
  try {
    fs.unlinkSync(BG_LOCK);
  } catch (e) {}
  process.exit(0);
}

// ── Rate limits per account → cswap (opt-in) ────────────────────────────────
//
// claude-swap (`cswap`) switches accounts on usage it reads from the usage endpoint. For an account
// logged in with a long-lived setup-token that endpoint answers 429, so cswap never sees headroom
// and `cswap auto` never activates the account. Claude Code hands this script the numbers cswap
// lacks (`rate_limits`). With WE_CSWAP_FEED_ACCOUNTS set (comma-separated cswap emails), every
// session records its account's readings and, at most once a minute across all sessions, feeds the
// listed accounts to `cswap import-usage`. Unset, none of this runs.
//
// Never in the render path: render claims a per-minute slot (one O_EXCL create per config home) and
// spawns a detached child, which reads the identity, merges the reading and runs the feed. The
// identity comes from the same `.claude.json` cswap reads (`oauthAccount`), never a credential.
const RL_FILE = path.join(os.homedir(), '.claude', '.we-rate-limits.json');
const RL_INTERVAL_MS = 60_000;
const FEED_STAMP = path.join(os.homedir(), '.claude', '.we-cswap-feed.stamp');
const FEED_STATUS = path.join(os.homedir(), '.claude', '.we-cswap-feed.last');
// Keeps cswap's own collectors off a fed account between two feeds (cswap bounds it by the reading's
// earliest reset and an hour). Three feed intervals: one missed feed does not hand polling back.
const FEED_HOLD_S = 180;

function feedAccounts() {
  return (process.env.WE_CSWAP_FEED_ACCOUNTS || '')
    .split(',').map((s) => s.trim().toLowerCase()).filter(Boolean);
}

// Claude Code's global config for this session, resolved like cswap's paths.get_global_config_path.
function claudeConfigPath() {
  const env = process.env.CLAUDE_CONFIG_DIR;
  const home = env || path.join(os.homedir(), '.claude');
  const legacy = path.join(home, '.config.json');
  try {
    if (fs.statSync(legacy).size > 0) return legacy;
  } catch (e) {}
  return path.join(env || os.homedir(), '.claude.json');
}

function shortHash(str) {
  let h = 5381;
  for (let i = 0; i < str.length; i++) h = ((h * 33) ^ str.charCodeAt(i)) >>> 0;
  return h.toString(16);
}

function maybeRecordRateLimits(data) {
  if (feedAccounts().length === 0) return;
  const cfg = claudeConfigPath();
  if (!claimSlot(`${RL_FILE}.${shortHash(cfg)}.stamp`, RL_INTERVAL_MS)) return;
  try {
    const child = spawn(
      process.execPath,
      [__filename, '--record-rate-limits', cfg, JSON.stringify(data.rate_limits || {})],
      { detached: true, stdio: 'ignore' },
    );
    child.unref();
  } catch (e) {}
}

// Claude Code: `{used_percentage, resets_at}` with resets_at in Unix epoch seconds.
function windowFromStatusline(w) {
  if (!w || typeof w.used_percentage !== 'number' || !Number.isFinite(w.used_percentage)) return null;
  const out = { pct: w.used_percentage };
  if (typeof w.resets_at === 'number' && Number.isFinite(w.resets_at)) out.resetsAt = w.resets_at;
  return out;
}

function readRateLimitsFile(file) {
  try {
    const doc = JSON.parse(fs.readFileSync(file, 'utf8'));
    if (doc && doc.schemaVersion === 1 && doc.accounts && typeof doc.accounts === 'object') return doc;
  } catch (e) {}
  return null;
}

function recordRateLimits(cfg, rateLimits, nowS) {
  let identity = null;
  try {
    const acct = JSON.parse(fs.readFileSync(cfg, 'utf8')).oauthAccount || {};
    if (typeof acct.emailAddress === 'string' && acct.emailAddress) {
      identity = { email: acct.emailAddress, organizationUuid: acct.organizationUuid || '' };
    }
  } catch (e) {}
  if (!identity) return;
  const fiveHour = windowFromStatusline(rateLimits.five_hour);
  const sevenDay = windowFromStatusline(rateLimits.seven_day);
  if (!fiveHour && !sevenDay) return; // no observation: never bump observedAt without one

  const lock = `${RL_FILE}.lock`;
  const deadline = Date.now() + 2000;
  while (!claimSlot(lock, 5000)) {
    if (Date.now() > deadline) return;
    Atomics.wait(new Int32Array(new SharedArrayBuffer(4)), 0, 0, 50);
  }
  try {
    const doc = readRateLimitsFile(RL_FILE) || { schemaVersion: 1, accounts: {} };
    const key = `${identity.email}\u0000${identity.organizationUuid}`;
    const prev = doc.accounts[key] || {};
    // A window Claude Code stopped reporting (its reset passed) keeps the last reading: the feed
    // derives the new window from that reset.
    doc.accounts[key] = {
      ...identity,
      observedAt: nowS,
      fiveHour: fiveHour || prev.fiveHour || null,
      sevenDay: sevenDay || prev.sevenDay || null,
    };
    const tmp = `${RL_FILE}.${process.pid}.tmp`;
    fs.writeFileSync(tmp, JSON.stringify(doc));
    fs.renameSync(tmp, RL_FILE);
  } finally {
    try {
      fs.unlinkSync(lock);
    } catch (e) {}
  }
}

// One window as of `nowS`. A window whose reset has passed is per definition new, and a new window
// carries no usage until a request opens it; every request on a fed account runs in a session
// whose statusline would have recorded a newer reading. So "reset passed, no newer reading" means
// pct 0 — a derivation from those two facts, not an estimate. It carries no resetsAt: an unopened
// window has none (the usage endpoint reports exactly `{pct: 0}` for it), and an invented reset
// would cap cswap's hold and trust at a time nobody measured. A window before its reset keeps the
// last reading: usage only rises within a window, and any rise would have produced a newer reading.
function deriveWindow(w, nowS) {
  if (!w || typeof w.pct !== 'number') return null;
  if (typeof w.resetsAt === 'number' && w.resetsAt <= nowS) return { pct: 0 };
  const out = { pct: w.pct };
  if (typeof w.resetsAt === 'number') out.resetsAt = new Date(w.resetsAt * 1000).toISOString();
  return out;
}

// The `cswap import-usage` document (shape of `cswap list --json`) for the listed accounts, or
// null when there is nothing to feed. usageAgeSeconds is 0 because the row is the state now, under
// the premise above (every use of the account shows in a statusline on this machine); the time of
// the last real reading stays in the rate-limits file as observedAt.
function buildFeedDocument(doc, accounts, nowS) {
  if (!doc) return null;
  const rows = [];
  for (const entry of Object.values(doc.accounts)) {
    if (!entry || typeof entry.email !== 'string') continue;
    if (!accounts.includes(entry.email.toLowerCase())) continue;
    const usage = {};
    const fiveHour = deriveWindow(entry.fiveHour, nowS);
    const sevenDay = deriveWindow(entry.sevenDay, nowS);
    if (fiveHour) usage.fiveHour = fiveHour;
    if (sevenDay) usage.sevenDay = sevenDay;
    if (!fiveHour && !sevenDay) continue;
    rows.push({
      email: entry.email,
      organizationUuid: entry.organizationUuid || '',
      usageStatus: 'ok',
      usageAgeSeconds: 0,
      usage,
    });
  }
  return rows.length ? { schemaVersion: 1, accounts: rows } : null;
}

function feedCswap({ dryRun = false, file = RL_FILE } = {}) {
  const feed = buildFeedDocument(readRateLimitsFile(file), feedAccounts(), Date.now() / 1000);
  if (!feed) return;
  const text = JSON.stringify(feed, null, 2);
  if (dryRun) {
    process.stdout.write(`${text}\n`);
    return;
  }
  // The global cswap store, not the profile of whichever session ran this statusline.
  const env = { ...process.env };
  delete env.CLAUDE_CONFIG_DIR;
  let status;
  try {
    const out = spawnSync(
      'cswap', ['import-usage', '-', '--hold', String(FEED_HOLD_S)],
      { input: text, encoding: 'utf8', env, timeout: 30_000 },
    );
    status = { ts: Date.now(), exit: out.status, error: out.error ? String(out.error.code || out.error) : null,
      stderr: String(out.stderr || '').trim().split('\n').slice(-3) };
  } catch (e) {
    status = { ts: Date.now(), exit: null, error: String(e && e.message), stderr: [] };
  }
  try {
    fs.writeFileSync(FEED_STATUS, JSON.stringify(status));
  } catch (e) {}
}

if (process.argv[2] === '--record-rate-limits') {
  try {
    recordRateLimits(process.argv[3], JSON.parse(process.argv[4] || '{}'), Date.now() / 1000);
  } catch (e) {}
  try {
    if (claimSlot(FEED_STAMP, RL_INTERVAL_MS)) feedCswap();
  } catch (e) {}
  process.exit(0);
}

// Manual run and test entry: `--feed-cswap [--dry-run] [--file PATH]`.
if (process.argv[2] === '--feed-cswap') {
  const args = process.argv.slice(3);
  const fileIdx = args.indexOf('--file');
  try {
    feedCswap({ dryRun: args.includes('--dry-run'), file: fileIdx >= 0 ? args[fileIdx + 1] : RL_FILE });
  } catch (e) {}
  process.exit(0);
}

let input = '';
process.stdin.setEncoding('utf8');
process.stdin.on('data', chunk => input += chunk);
process.stdin.on('end', () => {
  try {
    const data = JSON.parse(input);
    try {
      maybeRecordRateLimits(data);
    } catch (e) {}

    // ---- gather raw values ----

    // Companion — only for a session /we:materialize bound (scripts/identity_cache.py
    // bind owns the file and its WE_SESSION_DIR override); an unbound session shows no segment.
    let companionName = '';
    if (/^[A-Za-z0-9_-]{1,128}$/.test(String(data.session_id || ''))) {
      try {
        const override = process.env.WE_SESSION_DIR || '';
        const sessionDir = override
          ? override.replace(/^~(?=$|\/)/, os.homedir())
          : path.join(os.homedir(), '.claude', 'we', 'sessions');
        const bound = JSON.parse(fs.readFileSync(
          path.join(sessionDir, `${data.session_id}.json`), 'utf8'));
        if (typeof bound.companion === 'string') companionName = bound.companion.trim();
      } catch {}
    }

    // Model (from actual runtime, not config)
    const modelName = data.model?.display_name || 'Claude';
    const modelId = data.model?.id || '';
    const is1M = modelId.includes('1m') && !modelName.includes('1M');
    const modelPlain = is1M ? `${modelName} (1M)` : modelName;

    // Git branch
    // A Lead runs from the main worktree while the work lives elsewhere. If the
    // session declared a focus (written by /we:orchestrate § Push, PR, CI), show
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

    const worktree = data.worktree?.name || (focus?.dir ? path.basename(focus.dir) : undefined);
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

    // Background sessions — every `claude --bg` session but this one.
    // "bg 2" when all wait, "bg 1/2" (yellow) when one of two is working.
    let bgSeg = null;
    const bgCache = readBgCache();
    if (!bgCache || Date.now() - (bgCache.ts || 0) > BG_TTL_MS) refreshBgCacheDetached();
    const others = (bgCache?.sessions || []).filter((s) => s.sessionId !== data.session_id);
    if (others.length > 0) {
      const working = others.filter((s) => s.working).length;
      const plain = working > 0 ? `bg ${working}/${others.length}` : `bg ${others.length}`;
      const color = working > 0 ? '33' : '2';
      bgSeg = { plain, color: (s) => `\x1b[${color}m${s}\x1b[0m` };
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
    const companionSeg = companionName
      ? { plain: companionName, floor: Math.min(companionName.length, 12), color: (s) => `\x1b[1;35m${s}\x1b[0m`, dir: 'right' }
      : null;
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

    let required = [companionSeg, model, branchSeg, prSeg, dirSeg, ctxSeg, bgSeg];

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
      const shrinkable = [companionSeg, model, branchSeg, dirSeg].filter((s) => s && s.plain.length > s.floor);
      if (shrinkable.length === 0) break;
      shrinkable.sort((a, b) => b.plain.length - a.plain.length);
      const s = shrinkable[0];
      const newLen = Math.max(s.floor, s.plain.length - 1);
      s.plain = s.dir === 'left' ? truncateLeft(s.plain, newLen) : truncateRight(s.plain, newLen);
    }

    // ---- assemble ----
    const parts = [companionSeg, model, branchSeg, prSeg, dirSeg, ctxSeg, bgSeg, ...opts]
      .filter(Boolean)
      .map((s) => s.color(s.plain));

    process.stdout.write(parts.join(SEP));
  } catch (e) {
    // Silent fail
  }
});
