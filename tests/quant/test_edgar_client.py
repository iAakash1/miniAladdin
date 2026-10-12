"""The EDGAR client: pacing, retries, 404 and 403 handling, and that the declared contact never reaches disk, a log line or an exception."""

import gzip
import json
import urllib.error

import pytest

from src.quant.pit.edgar_client import EdgarAccessError, EdgarClient

AGENT = "ResearchProject/9.9 someone.private@example.invalid"


class Script:
    """A scripted transport: returns the queued (status, headers, body) answers in order and records the headers it was given."""

    def __init__(self, answers):
        self.answers, self.headers_seen, self.urls = list(answers), [], []

    def __call__(self, url, headers):
        self.urls.append(url)
        self.headers_seen.append(dict(headers))
        return self.answers.pop(0)


class Clock:
    def __init__(self):
        self.now, self.slept = 0.0, []

    def time(self):
        return self.now

    def sleep(self, seconds):
        self.slept.append(seconds)
        self.now += seconds


def client(script, tmp_path, **kw):
    clock = Clock()
    c = EdgarClient(user_agent=AGENT, transport=script, manifest=tmp_path / "m.jsonl", sleep=clock.sleep, clock=clock.time, **kw)
    return c, clock


def test_refuses_to_run_without_a_declared_contact(monkeypatch):
    monkeypatch.delenv("EDGAR_USER_AGENT", raising=False)
    with pytest.raises(EdgarAccessError, match="EDGAR_USER_AGENT"):
        EdgarClient()
    with pytest.raises(EdgarAccessError):
        EdgarClient(user_agent="no-contact-here")
    with pytest.raises(ValueError):
        EdgarClient(user_agent=AGENT, requests_per_second=50)


def test_the_agent_is_sent_but_never_stored_logged_or_shown(tmp_path):
    script = Script([(200, {}, b'{"ok": 1}'), (403, {}, b"")])
    c, _ = client(script, tmp_path)
    assert c.get("https://data.sec.gov/x.json") == b'{"ok": 1}'
    assert script.headers_seen[0]["User-Agent"] == AGENT
    with pytest.raises(EdgarAccessError) as error:
        c.get("https://data.sec.gov/y.json")
    assert AGENT not in str(error.value) and "someone.private" not in repr(c) and "someone.private" not in str(error.value)
    assert "someone.private" not in (tmp_path / "m.jsonl").read_text()


def test_requests_are_paced_below_the_cap(tmp_path):
    script = Script([(200, {}, b"{}")] * 5)
    c, clock = client(script, tmp_path, requests_per_second=5.0)
    for i in range(5):
        c.get(f"https://data.sec.gov/{i}.json")
    assert clock.now >= 4 * 0.2 - 1e-9            # five requests at 5 per second take at least four intervals


def test_a_missing_document_raises_404_and_is_logged(tmp_path):
    c, _ = client(Script([(404, {}, b"")]), tmp_path)
    with pytest.raises(urllib.error.HTTPError) as error:
        c.get("https://data.sec.gov/none.json")
    assert error.value.code == 404
    assert json.loads((tmp_path / "m.jsonl").read_text().splitlines()[0])["status"] == 404


def test_throttling_and_server_errors_are_retried_and_retry_after_is_honoured(tmp_path):
    script = Script([(429, {"Retry-After": "7"}, b""), (503, {}, b""), (200, {}, b"payload")])
    c, clock = client(script, tmp_path)
    assert c.get("https://data.sec.gov/z.json") == b"payload"
    assert 7.0 in clock.slept and len(script.urls) == 3


def test_a_403_stops_at_once_instead_of_retrying(tmp_path):
    script = Script([(403, {}, b""), (200, {}, b"never reached")])
    c, _ = client(script, tmp_path)
    with pytest.raises(EdgarAccessError, match="403"):
        c.get("https://data.sec.gov/blocked.json")
    assert len(script.urls) == 1


def test_gzip_bodies_are_decoded_and_truncated_ones_retried(tmp_path):
    good = gzip.compress(b'{"a": 1}')
    script = Script([(200, {"Content-Encoding": "gzip"}, good[:10]), (200, {"Content-Encoding": "gzip"}, good)])
    c, _ = client(script, tmp_path)
    assert c.get("https://data.sec.gov/g.json") == b'{"a": 1}'
    assert len(script.urls) == 2


def test_exhausted_retries_raise_without_the_agent(tmp_path):
    script = Script([(503, {}, b"")] * 3)
    c, _ = client(script, tmp_path, max_retries=3)
    with pytest.raises(EdgarAccessError, match="gave up") as error:
        c.get("https://data.sec.gov/slow.json")
    assert "someone.private" not in str(error.value)
