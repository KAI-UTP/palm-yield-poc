"""Both proposal options work: A without the AI assistant, B with login, AI, usage log and SAP link."""
import pytest
from streamlit.testing.v1 import AppTest

import core.ai as ai
from conftest import ROOT
from core import edition as ED
from core.connectors import SapConnector


class Answer:
    status_code = 200

    def json(self):
        return {"candidates": [{"content": {"parts": [{"text": "Mocked answer.\nCHART: estates"}]}}]}


@pytest.fixture
def app(monkeypatch, tmp_path):
    monkeypatch.delenv("PALM_RENDER_ALL", raising=False)
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    calls = []
    monkeypatch.setattr(ai.requests, "post", lambda url, **kw: calls.append(url) or Answer())

    def make(edition, user=None):
        at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=240)
        at.session_state["edition"] = edition
        if user:
            at.session_state["user"] = user
        return at.run(), calls
    return make


def test_option_b_asks_to_sign_in_first(app):
    at, _ = app("B")
    assert not at.exception and at.title[0].value == "Sign in with your company account"
    at.button(key="signin_manager").click().run()
    assert not at.exception and at.session_state["user"] == "manager"


def test_option_a_never_calls_the_ai(app):
    at, calls = app("A")
    at.button(key="home_q2").click().run()  # "Which estate needs the most attention?" opens the assistant
    assert not at.exception and calls == [] and at.session_state["chat"][-1]["note"].startswith("Built-in")


def test_option_b_uses_the_ai(app):
    at, calls = app("B", "agronomist")
    at.button(key="home_q2").click().run()
    last = at.session_state["chat"][-1]
    assert not at.exception and len(calls) == 1 and last["chart"] == "estates" and "Gemini" in last["note"]


def test_switching_options_keeps_working(app):
    at, _ = app("B", "admin")
    at.radio(key="edition").set_value("A").run()
    assert not at.exception and at.title[0].value == "Find where yield is lost, and what to do first"


def test_usage_log_round_trip(tmp_path):
    log = tmp_path / "ai.jsonl"
    ED.log_ai_use(log, "admin", "q1", "Google Gemini", True)
    ED.log_ai_use(log, "manager", "q2", "Google Gemini", False)
    rows = ED.read_log(log)
    assert [r["question"] for r in rows] == ["q2", "q1"] and rows[1]["answered"] is True


def test_sap_connector_extract(tmp_path):
    from prepare import RAW
    path, summary = SapConnector(RAW).extract(tmp_path)
    assert path.exists() and summary["rows"] == 3200 and summary["blocks"] == 640 and SapConnector.simulated
