"""flow_log.py: the one owner of the flow JSONL (path by crew-zone day, line types, O_APPEND, age)."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import flow_log  # noqa: E402

TZ = "Europe/Berlin"
NOW = datetime(2026, 11, 5, 10, 0, tzinfo=timezone.utc)


def lines(path):
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines()]


class TestAppend:
    def test_one_line_in_the_zone_days_file_with_a_stamped_ts(self, tmp_path):
        path = flow_log.append(tmp_path, {"type": "heartbeat"}, TZ, now=NOW)
        assert path == tmp_path / "sampler-2026-11-05.jsonl"
        assert lines(path) == [{"type": "heartbeat", "ts": "2026-11-05T10:00:00Z"}]

    def test_the_day_is_the_zones_not_utcs(self, tmp_path):
        late = datetime(2026, 11, 5, 23, 30, tzinfo=timezone.utc)  # 00:30 on the 6th in Berlin
        path = flow_log.append(tmp_path, {"type": "heartbeat"}, TZ, now=late)
        assert path.name == "sampler-2026-11-06.jsonl"

    def test_a_given_ts_decides_the_file_and_stays(self, tmp_path):
        rec = {"type": "correction", "ts": "2026-11-04T12:00:00Z", "session": "s", "kind": "k"}
        path = flow_log.append(tmp_path, rec, TZ, now=NOW)
        assert path.name == "sampler-2026-11-04.jsonl"
        assert lines(path) == [rec]

    @pytest.mark.parametrize(
        "record, message",
        [
            ({"type": "gossip"}, "type 'gossip' is not one of sample, heartbeat"),
            ({}, "type None is not one of"),
            ({"type": "kill", "ts": "yesterday"}, "ts 'yesterday' is no UTC ISO time"),
            ([1], "a line is a JSON object"),
        ],
    )
    def test_a_bad_line_is_refused_and_nothing_written(self, tmp_path, record, message):
        with pytest.raises(flow_log.FlowLogError, match=message):
            flow_log.append(tmp_path, record, TZ, now=NOW)
        assert list(tmp_path.iterdir()) == []

    def test_lines_only_grow_and_concurrent_writers_stay_whole(self, tmp_path):
        writer = (
            "import sys; sys.path.insert(0, sys.argv[1]); import flow_log\n"
            "for i in range(200): flow_log.append(sys.argv[2], "
            "{'type': 'heartbeat', 'ts': '2026-11-05T10:00:00Z', 'pad': 'x' * 300}, 'UTC')"
        )
        procs = [
            subprocess.Popen([sys.executable, "-c", writer, str(HERE), str(tmp_path)])
            for _ in range(3)
        ]
        assert [p.wait(timeout=60) for p in procs] == [0, 0, 0]
        got = lines(tmp_path / "sampler-2026-11-05.jsonl")
        assert len(got) == 600 and all(g["pad"] == "x" * 300 for g in got)


class TestNewest:
    def test_no_file_is_none(self, tmp_path):
        assert flow_log.newest(tmp_path, TZ, NOW) is None

    def test_the_last_whole_line_of_today_wins(self, tmp_path):
        flow_log.append(tmp_path, {"type": "heartbeat", "ts": "2026-11-05T09:00:00Z"}, TZ)
        flow_log.append(tmp_path, {"type": "sample", "ts": "2026-11-05T09:50:00Z"}, TZ)
        with open(tmp_path / "sampler-2026-11-05.jsonl", "a", encoding="utf-8") as fh:
            fh.write('{"type": "heart')  # a torn tail
        ts, age = flow_log.newest(tmp_path, TZ, NOW)
        assert (ts, age) == ("2026-11-05T09:50:00Z", 600)

    def test_yesterdays_file_counts_after_midnight(self, tmp_path):
        flow_log.append(tmp_path, {"type": "heartbeat", "ts": "2026-11-04T22:55:00Z"}, TZ)
        just_after = datetime(2026, 11, 4, 23, 5, tzinfo=timezone.utc)  # 00:05 Berlin, the 5th
        assert flow_log.newest(tmp_path, TZ, just_after) == ("2026-11-04T22:55:00Z", 600)

    def test_a_long_file_is_read_from_its_end(self, tmp_path):
        path = tmp_path / "sampler-2026-11-05.jsonl"
        with open(path, "w", encoding="utf-8") as fh:
            for i in range(3000):
                fh.write(json.dumps({"type": "heartbeat", "ts": "2026-11-05T08:00:00Z", "i": i}))
                fh.write("\n")
            fh.write(json.dumps({"type": "heartbeat", "ts": "2026-11-05T09:59:00Z"}) + "\n")
        assert os.path.getsize(path) > flow_log.TAIL_BYTES
        assert flow_log.newest(tmp_path, TZ, NOW) == ("2026-11-05T09:59:00Z", 60)


class TestCli:
    def run(self, *argv, cwd=None):
        return subprocess.run(
            [sys.executable, str(HERE / "flow_log.py"), *argv],
            capture_output=True,
            check=False,
            text=True,
            cwd=cwd,
        )

    def test_append_and_newest_by_log_dir(self, tmp_path):
        done = self.run(
            "--log-dir", str(tmp_path), "--tz", "UTC", "append", '{"type":"heartbeat"}'
        )
        assert done.returncode == 0, done.stderr
        [path] = tmp_path.iterdir()
        assert done.stdout.strip() == str(path)
        newest = self.run("--log-dir", str(tmp_path), "--tz", "UTC", "newest")
        assert newest.returncode == 0 and newest.stdout.startswith("20")

    def test_a_bad_line_exits_1_naming_it(self, tmp_path):
        done = self.run("--log-dir", str(tmp_path), "append", '{"type":"gossip"}')
        assert done.returncode == 1
        assert "flow_log.py: type 'gossip' is not one of" in done.stderr

    def test_no_log_dir_anywhere_exits_2(self, tmp_path):
        (tmp_path / ".git").mkdir()
        done = self.run("append", '{"type":"heartbeat"}', cwd=tmp_path)
        assert done.returncode == 2
        assert "flow_log.py: flow.log_dir is unset" in done.stderr

    def test_the_crew_names_the_dir_and_the_zone(self, tmp_path):
        (tmp_path / ".git").mkdir()
        (tmp_path / ".weside").mkdir()
        crew = json.loads((HERE / "fixtures" / "crew-v2-generic.json").read_text())
        crew["flow"] = {"log_dir": str(tmp_path / "flow")}
        (tmp_path / ".weside" / "crew.json").write_text(json.dumps(crew))
        done = self.run("append", '{"type":"heartbeat","ts":"2026-11-05T23:30:00Z"}', cwd=tmp_path)
        assert done.returncode == 0, done.stderr
        assert (tmp_path / "flow" / "sampler-2026-11-06.jsonl").exists()  # sla.tz Berlin
