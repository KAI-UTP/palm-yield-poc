"""Publishing checked results from the Analytics Workbench to the PalmYield web app."""
import base64
import io
import json
import sys
import urllib.error

import pytest
from streamlit.testing.v1 import AppTest

from conftest import ROOT
from core import publish as PUB

sys.path.insert(0, str(ROOT / "web"))
import build_data as BUILD  # noqa: E402


def test_build_stamps_when_and_where_from():
    d = BUILD.build(source_name="estates_q4.xlsx", published_by="Analytics Workbench")
    assert d["meta"]["published_from"] == "estates_q4.xlsx" and d["meta"]["published_by"] == "Analytics Workbench"
    assert d["meta"]["published_at"].endswith("+00:00") and len(d["blocks"]) == d["meta"]["blocks"] == 640
    assert json.loads(BUILD.to_json(d))["meta"] == d["meta"]


class FakeGitHub:
    """Stands in for api.github.com: remembers the requests, answers like GitHub."""

    def __init__(self, fail=None):
        self.calls, self.fail = [], fail

    def __call__(self, req, timeout=0):
        body = json.loads(req.data) if req.data else None
        self.calls.append((req.get_method(), req.full_url, body, req.headers.get("Authorization")))
        if self.fail:
            raise urllib.error.HTTPError(req.full_url, self.fail, "x", {}, io.BytesIO(b'{"message":"Bad credentials"}'))
        out = {"sha": "oldsha"} if req.get_method() == "GET" else {"commit": {"sha": "abcdef1234567", "html_url": "https://github.com/x/commit/abcdef1"}}
        return io.BytesIO(json.dumps(out).encode())


def test_publish_updates_the_web_data_file(monkeypatch):
    gh = FakeGitHub()
    monkeypatch.setattr(PUB.urllib.request, "urlopen", gh)
    res = PUB.publish('{"meta":{}}', "tok", "Publish data", repo="o/r", branch="main")
    (m1, u1, _, a1), (m2, u2, body, _) = gh.calls
    assert (m1, m2) == ("GET", "PUT") and a1 == "Bearer tok"
    assert u2 == "https://api.github.com/repos/o/r/contents/web/data/app.json" and "ref=main" in u1
    assert body["sha"] == "oldsha" and body["branch"] == "main" and base64.b64decode(body["content"]) == b'{"meta":{}}'
    assert res["sha"] == "abcdef1"


def test_publish_explains_a_bad_token(monkeypatch):
    monkeypatch.setattr(PUB.urllib.request, "urlopen", FakeGitHub(fail=401))
    with pytest.raises(PUB.PublishError, match="token is not valid"):
        PUB.publish("{}", "bad", "m")
    with pytest.raises(PUB.PublishError, match="No GitHub token"):
        PUB.publish("{}", "", "m")


def test_workbench_says_how_to_switch_publishing_on(monkeypatch):
    monkeypatch.setenv("PALM_RENDER_ALL", "1")
    monkeypatch.delenv("WORKBENCH_PASSWORD", raising=False)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=240).run()
    assert not at.exception
    assert any("Publishing is switched off" in i.value for i in at.info)
    assert not [b for b in at.button if b.key == "publish_btn"]


def test_workbench_publishes_after_the_analyst_confirms(monkeypatch):
    monkeypatch.setenv("PALM_RENDER_ALL", "1")
    monkeypatch.delenv("WORKBENCH_PASSWORD", raising=False)
    monkeypatch.setenv("GITHUB_TOKEN", "tok")
    gh = FakeGitHub()
    monkeypatch.setattr(PUB.urllib.request, "urlopen", gh)
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=240).run()
    btn = next(b for b in at.button if b.key == "publish_btn")
    assert btn.disabled and not gh.calls           # nothing happens until the analyst confirms
    at.checkbox(key="publish_ok").check().run()
    next(b for b in at.button if b.key == "publish_btn").click().run()
    assert not at.exception and any("Published (abcdef1)" in s.value for s in at.success)
    sent = json.loads(base64.b64decode(gh.calls[-1][2]["content"]))
    assert sent["meta"]["published_by"] == "Analytics Workbench" and len(sent["blocks"]) == 640
