"""Insights are computed from the results and follow the filters."""
from core import insights as I
from core.store import make_view

KINDS = {"gap", "risk", "action", "good", "info"}


def test_every_insight_is_well_formed(view):
    for fn in (I.overview, I.forecast, I.actions, I.agronomy, I.home):
        items = fn(view)
        assert items, fn.__name__
        for kind, head, detail in items:
            assert kind in KINDS and head and detail


def test_insights_follow_filters(results):
    one = make_view(results, estates=["Taniku 1 Estate"])
    assert one.f.estate_name.nunique() == 1
    text = " ".join(h + d for _, h, d in I.overview(one))
    assert "Taniku 1" in text


def test_value_matches_action_plan(view):
    assert f"{view.total_gain_t:,.0f}" in I.overview(view)[-1][1]


def test_block_story(results):
    assert "EST005-D08-B01" in I.block_story(results, "EST005-D08-B01", 930)
    assert I.block_story(results, "NOPE", 930) is None


def test_offline_answers(view):
    assert "EST005-D08-B01" in I.offline_answer(view, "Which blocks should we fix first?")
    # "rm" inside "ganoderma" must not trigger the money answer
    assert "Ganoderma" in I.offline_answer(view, "what about ganoderma?")
    assert "Taniku 1" in I.offline_answer(view, "tell me about taniku 1")
    assert I.offline_answer(view, "hello")


def test_ai_context_is_grounded(view):
    ctx = I.ai_context(view, "Why is EST005-D08-B01 high risk?")
    assert "synthetic" in ctx and "BLOCK EST005-D08-B01" in ctx and "TOP 15 PRIORITY BLOCKS" in ctx
    assert len(ctx) < 40_000  # small enough for a free-tier model
