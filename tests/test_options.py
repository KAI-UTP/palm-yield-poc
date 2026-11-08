"""The workbench as one product: sign-in, AI with a key, built-in answers without one, usage log and data sources."""
import sqlite3

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

import core.ai as ai
from conftest import ROOT
from core import connectors as CN
from core import edition as ED
from core.connectors import SapConnector


class Answer:
    status_code = 200

    def json(self):
        return {"candidates": [{"content": {"parts": [{"text": "Mocked answer.\nCHART: estates"}]}}]}


@pytest.fixture
def app(monkeypatch):
    monkeypatch.delenv("PALM_RENDER_ALL", raising=False)
    calls = []
    monkeypatch.setattr(ai.requests, "post", lambda url, **kw: calls.append(url) or Answer())

    def make(user=None, key=True):
        if key:
            monkeypatch.setenv("GEMINI_API_KEY", "test-key")
        else:
            monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=240)
        if user:
            at.session_state["user"] = user
        return at.run(), calls
    return make


def test_asks_to_sign_in_first(app):
    at, _ = app()
    assert not at.exception and at.title[0].value == "Sign in with your company account"
    at.button(key="signin_manager").click().run()
    assert not at.exception and at.session_state["user"] == "manager"


def test_no_option_switch(app):
    at, _ = app("admin")
    assert not at.exception and not [r for r in at.radio if r.key == "edition"]


def test_ai_answers_with_a_key(app):
    at, calls = app("agronomist")
    at.button(key="home_q2").click().run()
    last = at.session_state["chat"][-1]
    assert not at.exception and len(calls) == 1 and last["chart"] == "estates" and "Gemini" in last["note"]


def test_built_in_answers_without_a_key(app):
    at, calls = app("manager", key=False)
    at.button(key="home_q2").click().run()
    assert not at.exception and calls == [] and at.session_state["chat"][-1]["note"].startswith("Built-in")


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


def test_database_source_round_trip(tmp_path):
    """A table in a database becomes an extract the pipeline accepts."""
    from prepare import RAW, load_raw, required_columns
    db = tmp_path / "plantation.db"
    with sqlite3.connect(db) as con:
        pd.read_csv(RAW, encoding="utf-8-sig").to_sql("harvest_cycle", con, index=False)
    data, cut = CN.read_database(CN.connect("SQLite file", sqlite_path=db), CN.build_query(table="harvest_cycle"))
    path = CN.save_extract(data, tmp_path / "out", "db_extract")
    loaded = load_raw(path)
    assert not cut and len(loaded) == 3200 and set(required_columns()) <= set(loaded.columns)


def test_database_query_is_read_only(tmp_path):
    db = tmp_path / "t.db"
    with sqlite3.connect(db) as con:
        con.execute("create table t (a int)")
        con.execute("insert into t values (1), (2), (3)")
    data, cut = CN.read_database(CN.connect("SQLite file", sqlite_path=db), CN.build_query(query="SELECT a FROM t WHERE a > 1;"), max_rows=1)
    assert list(data.a) == [2] and cut
    for bad_query in ["DROP TABLE t", "SELECT 1; DROP TABLE t", "selected"]:
        with pytest.raises(ValueError):
            CN.build_query(query=bad_query)
    for bad_table in ["", "t; drop table t", "t where 1=1"]:
        with pytest.raises(ValueError):
            CN.build_query(table=bad_table)
