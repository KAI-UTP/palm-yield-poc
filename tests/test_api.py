"""REST API returns the same results as the app."""
from fastapi.testclient import TestClient

import api

client = TestClient(api.app)


def test_health():
    assert client.get("/health").json()["status"] == "ok"


def test_summary_matches_results(view):
    s = client.get("/summary").json()
    assert s["blocks"] == 640 and s["gain_t_ffb_yr"] == round(view.total_gain_t)
    assert client.get("/summary", params={"estate": "Nope"}).status_code == 404


def test_actions_filters():
    rows = client.get("/actions", params={"risk": "high", "limit": 5}).json()
    assert len(rows) == 5 and all(r["risk"] == "High" for r in rows)


def test_block_endpoint():
    b = client.get("/blocks/est005-d08-b01").json()
    assert b["block_id"] == "EST005-D08-B01" and len(b["history"]) == 5 and b["action"]["rank"] == 1
    assert client.get("/blocks/XYZ").status_code == 404


def test_insights_endpoint():
    j = client.get("/insights").json()
    assert set(j) == {"overview", "forecast", "actions", "agronomy"} and j["actions"]
