"""optimization_close.py against a fixture store: one entry closed by a merged PR, one expired,
one left open."""

import json
import os
import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).parent / "optimization_close.py"


def entry(key, *evidence):
    lines = "\n".join(f"- {e}" for e in evidence)
    return (
        f"---\nkey: {key}\npattern: gap\ntarget: AGENTS.md\ntarget_repo: this\naction: add\n"
        f"confidence: Medium\nsource: retro\n---\n\nThe finding.\n\n## Evidence\n\n{lines}\n"
    )


def store(tmp_path):
    s = tmp_path / ".weside" / "optimization"
    (s / "inbox").mkdir(parents=True)
    (s / "inbox" / "2026-11-10-gap--agents-md.md").write_text(
        entry("gap--agents-md", "2026-11-10 retro pr-7: missed", "2026-11-12 retro pr-9: again")
    )
    (s / "inbox" / "2026-10-20-g2-volatile--readme-md.md").write_text(
        entry("g2-volatile--readme-md", "2026-10-20 audit a.md #1: stale")
    )
    (s / "inbox" / "2026-11-15-gap--rules-x-md.md").write_text(
        entry("gap--rules-x-md", "2026-11-15 retro pr-11: seen once")
    )
    (s / "inbox" / "2026-10-01-gap--old-md.md").write_text(
        entry("gap--old-md", "2026-10-01 retro pr-1: a", "2026-10-03 retro pr-2: b")
    )
    (s / "LEDGER.md").write_text(
        "# Ledger\n\n| date | key | target | decision | evidence | metric | before → after | review_by | change |\n"
        "|---|---|---|---|---|---|---|---|---|\n| 2026-10-01 | k | t | rejected | e | — | — | — | — |\n"
    )
    prs = [
        {
            "number": 41,
            "title": "docs: rule for gap--agents-md",
            "body": "",
            "url": "https://x/pull/41",
            "mergedAt": "2026-11-14T10:00:00Z",
        },
        {
            "number": 7,
            "title": "older",
            "body": "applies GAP--RULES-X-MD",
            "url": "https://x/pull/7",
            "mergedAt": "2026-11-01T10:00:00Z",
        },
        {
            "number": 9,
            "title": "retro: gap--rules-x-md",
            "body": "",
            "url": "https://x/pull/9",
            "mergedAt": "2026-11-16T10:00:00Z",
            "files": [{"path": ".weside/optimization/inbox/2026-11-15-gap--rules-x-md.md"}],
        },
        {
            "number": 8,
            "title": "near miss",
            "body": "gap--agents-md-extra",
            "url": "https://x/pull/8",
            "mergedAt": "2026-11-16T10:00:00Z",
        },
    ]
    (tmp_path / "prs.json").write_text(json.dumps(prs))
    return s


def run(tmp_path, s, *extra):
    return subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--store",
            str(s),
            "--prs-json",
            str(tmp_path / "prs.json"),
            "--today",
            "2026-11-17",
            *extra,
        ],
        capture_output=True,
        text=True,
        check=False,
    )


def test_one_applied_by_a_merged_pr_one_expired_the_rest_open(tmp_path):
    s = store(tmp_path)
    out = run(tmp_path, s)
    assert out.returncode == 0, out.stderr
    assert out.stdout.splitlines() == [
        "expired g2-volatile--readme-md · 28 days, 1 evidence line(s)",
        "applied gap--agents-md · https://x/pull/41",
        "closed 1 applied, 1 expired, 2 open",
    ]
    assert (
        sorted(p.name for p in (s / "inbox").glob("*.md"))
        == [
            "2026-10-01-gap--old-md.md",  # old, but two evidence lines
            "2026-11-15-gap--rules-x-md.md",  # one line, young; one PR naming it is older, one a store PR
        ]
    )
    # the expired entry stays readable for a revival by retro_write.py
    assert [p.name for p in (s / "inbox" / "expired").iterdir()] == [
        "2026-10-20-g2-volatile--readme-md.md"
    ]
    rows = (s / "LEDGER.md").read_text().splitlines()
    assert (
        rows[4]
        == "| 2026-11-17 | g2-volatile--readme-md | AGENTS.md | expired | 1 evidence line(s) in 28 days | — | — | — | — |"
    )
    assert rows[5] == (
        "| 2026-11-17 | gap--agents-md | AGENTS.md | applied | merged PR https://x/pull/41 | recurrence"
        " | 2 → pending | 2026-12-17 | https://x/pull/41 |"
    )
    assert rows[6].startswith("| 2026-10-01 | k |")


def test_expire_days_comes_from_the_config(tmp_path):
    s = store(tmp_path)
    (s.parent / "config.json").write_text(json.dumps({"optimization": {"expire_days": 60}}))
    out = run(tmp_path, s)
    assert out.stdout.splitlines()[-1] == "closed 1 applied, 0 expired, 3 open"


def test_expire_all_before_expires_the_old_stock_whatever_its_evidence(tmp_path):
    s = store(tmp_path)
    out = run(tmp_path, s, "--expire-all-before", "2026-11-15")
    assert out.stdout.splitlines()[-1] == "closed 1 applied, 2 expired, 1 open"
    assert sorted(p.name for p in (s / "inbox" / "expired").iterdir()) == [
        "2026-10-01-gap--old-md.md",  # two evidence lines, but older than the date
        "2026-10-20-g2-volatile--readme-md.md",
    ]
    assert [p.name for p in (s / "inbox").glob("*.md")] == ["2026-11-15-gap--rules-x-md.md"]


def test_a_missing_ledger_is_created_with_its_header(tmp_path):
    s = store(tmp_path)
    (s / "LEDGER.md").unlink()
    assert run(tmp_path, s).returncode == 0
    rows = (s / "LEDGER.md").read_text().splitlines()
    assert rows[0].startswith("| date | key |") and len(rows) == 4


def test_no_inbox_exits_2(tmp_path):
    (tmp_path / "prs.json").write_text("[]")
    out = run(tmp_path, tmp_path / "none")
    assert out.returncode == 2 and "no inbox" in out.stderr


def upstream_store(tmp_path):
    s = tmp_path / ".weside" / "optimization"
    (s / "inbox").mkdir(parents=True)
    (s / "LEDGER.md").write_text(
        "# Ledger\n\n| date | key | target | decision | evidence | metric | before → after | review_by | change |\n"
        "|---|---|---|---|---|---|---|---|---|\n"
        "| 2026-11-10 | gap--skill-a | plugin | upstream | 2 retro lines | recurrence | 2 → pending | — | — |\n"
        "| 2026-11-10 | gap--skill-b | plugin | upstream | e | recurrence | 1 → pending | — | — |\n"
        "| 2026-11-10 | gap--skill-c | plugin | upstream | e | recurrence | 1 → pending | — | — |\n"
        "| 2026-11-12 | gap--skill-d | plugin | upstream | e | recurrence | 1 → pending | — | — |\n"
        "| 2026-10-10 | gap--skill-e | plugin | upstream | e \\| x | recurrence | 1 → pending | — | — |\n"
        "| 2026-10-01 | k | t | rejected | e | — | — | — | — |\n"
    )
    plugin_prs = [
        {
            "number": 300,
            "title": "fix: two findings",
            "body": "Applies gap--skill-a.\nrejected: gap--skill-b (not a plugin fault)\ndeferred: gap--skill-c",
            "url": "https://p/pull/300",
            "mergedAt": "2026-11-14T10:00:00Z",
        },
        {
            "number": 290,
            "title": "older: gap--skill-d",
            "body": "",
            "url": "https://p/pull/290",
            "mergedAt": "2026-11-11T10:00:00Z",
        },
    ]
    (tmp_path / "plugin-prs.json").write_text(json.dumps(plugin_prs))
    (tmp_path / "prs.json").write_text("[]")
    return s


def test_upstream_closes(tmp_path):
    s = upstream_store(tmp_path)
    out = run(tmp_path, s, "--plugin-prs-json", str(tmp_path / "plugin-prs.json"))
    assert out.returncode == 0, out.stderr
    assert out.stdout.splitlines() == [
        "closed 0 applied, 0 expired, 0 open",  # the inbox part as before
        "upstream applied gap--skill-a · https://p/pull/300",
        "upstream rejected gap--skill-b · https://p/pull/300",
        "upstream expired gap--skill-e · 38 days",
        "upstream: 1 applied, 1 rejected, 1 expired, 2 open",
    ]
    rows = (s / "LEDGER.md").read_text().splitlines()
    assert rows[4] == (
        "| 2026-11-10 | gap--skill-a | plugin | applied | 2 retro lines; plugin PR https://p/pull/300"
        " | recurrence | 2 → pending | 2026-12-14 | https://p/pull/300 |"
    )
    assert rows[5] == (
        "| 2026-11-10 | gap--skill-b | plugin | rejected | e; plugin PR https://p/pull/300"
        " | recurrence | 1 → pending | — | https://p/pull/300 |"
    )
    # deferred, and a PR merged before the row's date: both stay upstream
    assert "| upstream |" in rows[6] and "| upstream |" in rows[7]
    assert rows[8] == (
        "| 2026-10-10 | gap--skill-e | plugin | expired | e \\| x; no plugin PR in 38 days"
        " | recurrence | 1 → pending | — | — |"
    )
    assert rows[9] == "| 2026-10-01 | k | t | rejected | e | — | — | — | — |"


def fake_gh(tmp_path, payload):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    log = tmp_path / "gh-calls.log"
    gh = bin_dir / "gh"
    gh.write_text(f'#!/bin/sh\necho "$*" >> "{log}"\ncat \'{payload}\'\n')
    gh.chmod(0o755)
    return bin_dir, log


def run_env(tmp_path, s, env):
    return subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--store",
            str(s),
            "--prs-json",
            str(tmp_path / "prs.json"),
            "--today",
            "2026-11-17",
        ],
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )


def test_upstream_cache_and_no_call(tmp_path):
    bin_dir, log = fake_gh(tmp_path, tmp_path / "plugin-prs.json")
    env = {
        **os.environ,
        "HOME": str(tmp_path / "home"),
        "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
    }

    # no upstream row: gh is never called and the output is the inbox part alone
    plain = store(tmp_path / "plain")
    (tmp_path / "plain" / "prs.json").write_text("[]")
    out = run_env(tmp_path / "plain", plain, env)
    assert out.returncode == 0, out.stderr
    assert not log.exists()
    assert not any(line.startswith("upstream") for line in out.stdout.splitlines())

    # upstream rows: one search, then the cache serves the second run the same day
    s = upstream_store(tmp_path)
    first = run_env(tmp_path, s, env)
    assert first.returncode == 0, first.stderr
    assert "upstream: 1 applied, 1 rejected, 1 expired, 2 open" in first.stdout
    calls = log.read_text().splitlines()
    assert len(calls) == 1
    assert "--state merged" in calls[0] and "merged:>=2026-10-10" in calls[0]
    second = run_env(tmp_path, s, env)
    assert second.returncode == 0, second.stderr
    assert "upstream: 0 applied, 0 rejected, 0 expired, 2 open" in second.stdout
    assert len(log.read_text().splitlines()) == 1
    cache = next((tmp_path / "home" / ".cache" / "we" / "plugin-prs").glob("*.json"))
    assert json.loads(cache.read_text())["fetched"] == "2026-11-17"
