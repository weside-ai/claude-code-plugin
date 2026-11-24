"""epic_owner.Resolver: who receives a row addressed to ``epic_master``."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import epic_owner


def resolver(tmp_path, lines):
    r = epic_owner.Resolver(tmp_path)  # no crew: no board, no snapshot
    r.lines = lines
    r.stories = {"PROJ-8": {"epic": "PROJ-7"}}
    return r


@pytest.mark.parametrize(
    "member, to, reason",
    [("mira", [], "no running master"), (None, ["sock-m"], "")],
)
def test_a_companions_tail_never_receives_epic_master_rows(tmp_path, member, to, reason):
    """A board line without `companion` whose keys hold the epic receives only through a master's
    tail (presence member null); a companion's tail (member set) does not (PR #7419, 24.11.)."""
    r = resolver(tmp_path, [{"name": "mirror", "session_id": "s1", "keys": ["PROJ-7"]}])
    presences = [{"name": "sock-m", "session_id": "s1", "member": member}]
    owners = r.owners("pr_merged", {"story": "PROJ-8"}, presences)
    assert (owners.to, owners.reason) == (to, reason)
