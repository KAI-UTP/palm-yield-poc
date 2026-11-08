"""The Analytics Workbench: locked for the analytics team, and data comes in from a file, a database or SAP."""
import sqlite3

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from conftest import ROOT
from core import connectors as CN
from core.connectors import SapConnector


@pytest.fixture
def workbench(monkeypatch):
    monkeypatch.delenv("PALM_RENDER_ALL", raising=False)

    def make(password=None):
        if password:
            monkeypatch.setenv("WORKBENCH_PASSWORD", password)
        else:
            monkeypatch.delenv("WORKBENCH_PASSWORD", raising=False)
        return AppTest.from_file(str(ROOT / "app.py"), default_timeout=240).run()
    return make


def test_locked_until_the_right_password(workbench):
    at = workbench("s3cret")
    assert not at.exception and at.title[0].value == "For the analytics team" and not at.sidebar.button
    at.text_input[0].input("wrong").run()
    at.button[0].click().run()
    assert at.error and at.title[0].value == "For the analytics team"  # still locked
    at.text_input[0].input("s3cret").run()
    at.button[0].click().run()
    assert not at.exception and at.session_state["unlocked"] and at.title[0].value == "Find where yield is lost, and what to do first"


def test_open_without_a_password_and_says_so(workbench):
    at = workbench()
    assert not at.exception and at.title[0].value == "Find where yield is lost, and what to do first"
    assert any("Open access" in c.value for c in at.sidebar.caption)


def test_no_demo_sign_in_or_ai_page(workbench):
    at = workbench()
    assert not at.exception and not [b for b in at.button if b.key and b.key.startswith("signin_")]
    assert not at.chat_input


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
