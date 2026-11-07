"""Assistant charts: every chart builds from the results, and the right one is chosen."""
import pytest

from core import charts as C


@pytest.mark.parametrize("key", list(C.CATALOGUE))
def test_every_chart_builds(view, key):
    s = C.spec(view, key, "Tell me about EST005-D08-B01")
    assert s and len(s["data"]) and s["x"] in s["data"] and s["y"] in s["data"]


@pytest.mark.parametrize("question,key", [
    ("Which blocks should we fix first?", "top_blocks"), ("Where should fertilizer go?", "fertilizer"),
    ("How accurate is the forecast?", "forecast_models"), ("What is the biggest opportunity in RM?", "levers"),
    ("Why is EST002-D03-B07 low?", "block"), ("hello", None)])
def test_offline_pick(question, key):
    assert C.pick(question) == key


def test_top_block_drawn_first(view):
    d = C.spec(view, "top_blocks")["data"]
    assert d.Block.iloc[-1].startswith(view.act.block_id.iloc[0])  # horizontal bars: last row is drawn at the top


def test_ai_tag_is_removed_and_checked():
    assert C.split_tag("Text.\nCHART: levers") == ("Text.", "levers")
    assert C.split_tag("Text.\nCHART: made_up") == ("Text.", "none")  # unknown names never draw anything
    assert C.split_tag("Text only") == ("Text only", None)
    assert "top_blocks" in C.ai_instruction()
