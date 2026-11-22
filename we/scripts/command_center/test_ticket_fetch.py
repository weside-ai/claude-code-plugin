"""ticket_fetch.py: paging, mapping into the one writer, a code per failure class, no secret out."""

from __future__ import annotations

import io
import json
import sys
import urllib.error
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))
import ticket_fetch as tf  # noqa: E402

TOKEN = "tok-Zq8xVw3LmN0pRsT5uY7k"  # a fake value
EMAIL = "bot@example.com"
ENV = {
    "JIRA_BASE_URL": "https://acme.example.net/",
    "JIRA_EMAIL": EMAIL,
    "JIRA_SNAPSHOT_TOKEN": TOKEN,
}
JQL = "project = ABC AND statusCategory != Done"
AUTH = tf.auth_header(EMAIL, TOKEN)
SECRETS = (TOKEN, AUTH.split(" ", 1)[1])


def issue(key, status):
    return {"key": key, "fields": {"status": {"name": status}}}


class Resp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()


class Fake:
    """An opener answering from a list: a dict is a 200 body, an exception is raised."""

    def __init__(self, *answers):
        self.answers = list(answers)
        self.requests = []
        self.timeouts = []

    def __call__(self, req, timeout):
        self.requests.append(req)
        self.timeouts.append(timeout)
        answer = self.answers.pop(0)
        if isinstance(answer, BaseException):
            raise answer
        return Resp(json.dumps(answer).encode())


def http_error(code, body):
    return urllib.error.HTTPError("https://acme.example.net", code, "x", {}, io.BytesIO(body))


def run(tmp_path, opener, env=ENV, extra=()):
    argv = ["--board", str(tmp_path / "board.json"), "--jql", JQL, *extra]
    return tf.main(argv, env=env, opener=opener)


def test_pages_until_the_last_and_writes_through_the_one_writer(tmp_path, capsys):
    fake = Fake(
        {"issues": [issue("ABC-3", "In Progress")], "nextPageToken": "p2"},
        {"issues": [issue("ABC-2", "Selected for Development")], "nextPageToken": "p3"},
        {"issues": [issue("ABC-1", "Backlog")], "isLast": True},
    )
    assert run(tmp_path, fake) == 0
    bodies = [json.loads(r.data) for r in fake.requests]
    assert [b.get("nextPageToken") for b in bodies] == [None, "p2", "p3"]
    assert {b["jql"] for b in bodies} == {JQL} and bodies[0]["fields"] == tf.FIELDS
    req = fake.requests[0]
    assert req.full_url == "https://acme.example.net/rest/api/3/search/jql"
    assert req.get_method() == "POST" and TOKEN not in req.full_url
    assert fake.timeouts == [30, 30, 30]  # every page has a timeout
    doc = json.loads((tmp_path / "board-tickets.json").read_text())
    assert doc["stories"] == {
        "ABC-3": {"status": "In Progress"},
        "ABC-2": {"status": "Selected for Development"},
        "ABC-1": {"status": "Backlog"},
    }
    assert doc["schema_version"] == 2 and "@taken" in doc and doc["epics"] == {}
    assert "(3 stories, 0 epics)" in capsys.readouterr().out


def test_jql_from_the_crew(tmp_path, monkeypatch):
    (tmp_path / ".weside").mkdir()
    crew = {
        "version": 2,
        "roles": {"coordinator": "coord"},
        "members": {"coord": {"name": "Coord"}},
        "flow": {"tickets_jql": "project = XYZ"},
    }
    (tmp_path / ".weside" / "crew.json").write_text(json.dumps(crew))
    monkeypatch.chdir(tmp_path)
    fake = Fake({"issues": []})
    assert tf.main(["--board", str(tmp_path / "b.json")], env=ENV, opener=fake) == 0
    assert json.loads(fake.requests[0].data)["jql"] == "project = XYZ"
    assert len(fake.requests) == 1  # no flow.epics_jql: no epic query
    # flow.epics_jql: a second query, its epics land beside the stories, not among them
    crew["flow"]["epics_jql"] = "project = XYZ AND issuetype = Epic"
    (tmp_path / ".weside" / "crew.json").write_text(json.dumps(crew))
    epic = {
        "key": "XYZ-1",
        "fields": {"status": {"name": "In Progress"}, "issuetype": {"name": "Epic"}},
    }
    fake = Fake({"issues": [issue("XYZ-2", "Backlog")]}, {"issues": [epic]})
    assert tf.main(["--board", str(tmp_path / "b.json")], env=ENV, opener=fake) == 0
    assert [json.loads(r.data)["jql"] for r in fake.requests] == [
        "project = XYZ",
        "project = XYZ AND issuetype = Epic",
    ]
    doc = json.loads((tmp_path / "b-tickets.json").read_text())
    assert (list(doc["stories"]), doc["epics"]) == (
        ["XYZ-2"],
        {"XYZ-1": {"status": "In Progress"}},
    )


@pytest.mark.parametrize(
    ("env", "extra", "code", "says"),
    [
        ({**ENV, "JIRA_SNAPSHOT_TOKEN": ""}, (), 2, "not set: JIRA_SNAPSHOT_TOKEN"),
        ({**ENV, "JIRA_BASE_URL": "http://acme.example.net"}, (), 2, "https://"),
    ],
)
def test_config_missing_fetches_nothing(tmp_path, capsys, env, extra, code, says):
    fake = Fake()
    assert run(tmp_path, fake, env=env, extra=extra) == code
    assert fake.requests == [] and says in capsys.readouterr().err


def test_no_jql_anywhere(tmp_path, capsys, monkeypatch):
    monkeypatch.chdir(tmp_path)
    fake = Fake()
    assert tf.main(["--board", str(tmp_path / "b.json")], env=ENV, opener=fake) == 2
    assert fake.requests == [] and "flow.tickets_jql" in capsys.readouterr().err
    # no crew and no --board: no board to write for, nothing fetched
    assert tf.main(["--jql", JQL], env=ENV, opener=fake) == 2
    assert fake.requests == [] and "config: no board" in capsys.readouterr().err


ECHO = json.dumps(
    {"errorMessages": [f"bad credentials for {EMAIL} {TOKEN} Authorization: {AUTH}"]}
).encode()


@pytest.mark.parametrize(
    ("answer", "code"),
    [
        (http_error(401, ECHO), 3),  # auth: credentials refused, the answer echoes them
        (http_error(403, ECHO), 3),  # auth: the token lacks the project's permission
        (urllib.error.URLError(f"connect refused {TOKEN}"), 4),  # network: no connection
        (TimeoutError("timed out"), 4),  # network: no answer within --timeout
        (http_error(503, f"<html>down {TOKEN}</html>".encode()), 5),  # server: a 5xx page
        (http_error(400, ECHO), 6),  # refused: another status (here an invalid JQL)
        ({"no": "issues"}, 6),  # refused: a 200 that is no search result
    ],
)
def test_each_failure_class_has_its_code_writes_nothing_and_leaks_no_secret(
    tmp_path, capsys, answer, code
):
    # the second page fails: the first page is never written alone
    fake = Fake({"issues": [issue("ABC-1", "Backlog")], "nextPageToken": "p2"}, answer)
    assert run(tmp_path, fake) == code
    out, err = capsys.readouterr()
    assert err.startswith(f"ticket_fetch: {tf.CLASS[code]}: ") and err.count("\n") == 1
    assert len(err) < tf.LINE_CHARS + 80
    for secret in SECRETS:
        assert secret not in out + err
    assert EMAIL not in err
    assert list(tmp_path.iterdir()) == []


def test_fetch_raises_without_the_secret_or_its_cause():
    fake = Fake(http_error(401, ECHO))
    with pytest.raises(tf.FetchError) as info:
        tf.fetch("https://acme.example.net", EMAIL, TOKEN, JQL, fake)
    exc = info.value
    assert exc.__cause__ is None and exc.__suppress_context__
    for secret in SECRETS:
        assert secret not in str(exc) and secret not in repr(exc.args)


def test_a_page_token_that_never_ends_is_refused(tmp_path, monkeypatch):
    monkeypatch.setattr(tf, "MAX_PAGES", 3)
    fake = Fake(*[{"issues": [], "nextPageToken": "again"}] * 3)
    assert run(tmp_path, fake) == 6
    assert len(fake.requests) == 3 and list(tmp_path.iterdir()) == []
