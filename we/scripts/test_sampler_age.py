"""sampler_age.py: the verdict on the flow log's newest line (ok, stale, none, not bound)."""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import flow_log  # noqa: E402
import sampler_age  # noqa: E402

TZ = "Europe/Berlin"
NOW = datetime(2026, 11, 5, 10, 0, tzinfo=timezone.utc)


def write(log_dir, minutes_ago, now=NOW):
    ts = (now - timedelta(minutes=minutes_ago)).strftime(flow_log.TS_FMT)
    flow_log.append(log_dir, {"type": "heartbeat", "ts": ts}, TZ)
    return ts


class TestVerdict:
    def test_a_fresh_line_is_ok(self, tmp_path):
        ts = write(tmp_path, 1)
        assert sampler_age.verdict(tmp_path, TZ, 15, NOW) == (0, f"sampler: ok ({ts})", ts)

    def test_a_line_older_than_the_limit_is_stale_naming_its_age(self, tmp_path):
        ts = write(tmp_path, 20)
        assert sampler_age.verdict(tmp_path, TZ, 15, NOW) == (
            1,
            f"sampler: stale since 20 min (last line {ts})",
            ts,
        )

    def test_exactly_the_limit_is_still_ok(self, tmp_path):
        write(tmp_path, 15)
        assert sampler_age.verdict(tmp_path, TZ, 15, NOW)[0] == 0

    def test_no_line_today_or_yesterday_is_stale(self, tmp_path):
        code, text, episode = sampler_age.verdict(tmp_path, TZ, 15, NOW)
        assert (code, episode) == (1, "none-2026-11-05")
        assert text == f"sampler: stale, no line today or yesterday in {tmp_path}"

    def test_an_unbound_crew_is_no_verdict(self):
        assert sampler_age.verdict(None, TZ, 15, NOW) == (
            0,
            "sampler: not bound (flow.log_dir unset)",
            None,
        )


class TestCli:
    def run(self, *argv, cwd=None):
        return subprocess.run(
            [sys.executable, str(HERE / "sampler_age.py"), *argv],
            capture_output=True,
            text=True,
            cwd=cwd,
            check=False,
        )

    def test_stale_exits_1_with_the_verdict(self, tmp_path):
        now = datetime.now(timezone.utc)
        ts = write(tmp_path, 30, now)
        done = self.run("--log-dir", str(tmp_path), "--tz", TZ)
        assert done.returncode == 1
        assert done.stdout.strip() in {
            f"sampler: stale since {m} min (last line {ts})" for m in (30, 31)
        }

    def test_fresh_exits_0(self, tmp_path):
        ts = write(tmp_path, 0, datetime.now(timezone.utc))
        done = self.run("--log-dir", str(tmp_path), "--tz", TZ)
        assert (done.returncode, done.stdout.strip()) == (0, f"sampler: ok ({ts})")

    def test_max_min_overrides_the_crew(self, tmp_path):
        write(tmp_path, 5, datetime.now(timezone.utc))
        done = self.run("--log-dir", str(tmp_path), "--tz", TZ, "--max-min", "2")
        assert done.returncode == 1 and "sampler: stale since 5 min" in done.stdout

    def test_the_crew_names_dir_zone_and_limit(self, tmp_path):
        (tmp_path / ".git").mkdir()
        (tmp_path / ".weside").mkdir()
        crew = json.loads((HERE / "fixtures" / "crew-v2-generic.json").read_text())
        crew["flow"] = {"log_dir": str(tmp_path / "flow"), "stale_min": 3}
        (tmp_path / ".weside" / "crew.json").write_text(json.dumps(crew))
        write(tmp_path / "flow", 5, datetime.now(timezone.utc))
        done = self.run(cwd=tmp_path)
        assert done.returncode == 1 and "sampler: stale since 5 min" in done.stdout

    def test_no_crew_flow_is_not_bound_and_exits_0(self, tmp_path):
        (tmp_path / ".git").mkdir()
        done = self.run(cwd=tmp_path)
        assert (done.returncode, done.stdout.strip()) == (
            0,
            "sampler: not bound (flow.log_dir unset)",
        )
