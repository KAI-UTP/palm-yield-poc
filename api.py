"""REST API: the same results the app shows, for other systems (SAP Analytics Cloud, Power BI, a mobile app).

Run:   uvicorn api:app --port 8000      then open http://localhost:8000/docs
"""
from functools import lru_cache

from fastapi import FastAPI, HTTPException, Query

from core import insights as I
from core.store import FFB_PRICE_2025, load_results, make_view, wavg

app = FastAPI(title="Palm Yield Optimization API", version="1.0",
              description="Results of the palm yield POC pipeline (synthetic sample data). Read-only.")


@lru_cache(maxsize=1)
def results():
    return load_results()


def records(d):
    return d.round(3).where(d.notna(), None).to_dict(orient="records")


@app.get("/health")
def health():
    r = results()
    return {"status": "ok", "rows": len(r.df), "blocks": int(r.df.block_id.nunique()), "data": "synthetic sample"}


@app.get("/summary")
def summary(estate: list[str] = Query(default=[]), price: float = FFB_PRICE_2025):
    """Headline numbers, optionally for some estates, valued at a given FFB price (RM/t)."""
    v = make_view(results(), estates=estate, price=price)
    if v.f.empty:
        raise HTTPException(404, "No blocks match.")
    fm = results().J["forecast_metrics"]
    return {"blocks": int(v.f.block_id.nunique()), "yield_t_ha_yr": round(wavg(v.f), 2),
            "high_risk_blocks": int((v.nxt.risk == "High").sum()), "gain_t_ffb_yr": round(v.total_gain_t),
            "gain_rm_yr": round(v.total_gain_t * price), "forecast_mae": fm["model"]["mae"],
            "forecast_improvement_pct": fm["mae_improvement_vs_last_cycle_pct"]}


@app.get("/insights")
def insights(estate: list[str] = Query(default=[]), price: float = FFB_PRICE_2025):
    """Automated plain-language findings, grouped by topic."""
    v = make_view(results(), estates=estate, price=price)
    if v.f.empty:
        raise HTTPException(404, "No blocks match.")
    pack = lambda items: [{"kind": k, "headline": h, "detail": d} for k, h, d in items]  # noqa: E731
    return {"overview": pack(I.overview(v)), "forecast": pack(I.forecast(v)), "actions": pack(I.actions(v)), "agronomy": pack(I.agronomy(v))}


@app.get("/actions")
def actions(estate: list[str] = Query(default=[]), risk: str | None = None, limit: int = Query(25, ge=1, le=1000)):
    """The ranked action plan."""
    a = results().M["actions"]
    if estate:
        a = a[a.estate_name.isin(estate)]
    if risk:
        a = a[a.risk.str.lower() == risk.lower()]
    return records(a.head(limit))


@app.get("/forecast")
def forecast(risk: str | None = None, limit: int = Query(50, ge=1, le=1000)):
    """Next-cycle forecast per block with its 80% range."""
    n = results().M["forecast_next"].sort_values("forecast_vs_age_peers")
    if risk:
        n = n[n.risk.str.lower() == risk.lower()]
    return records(n.head(limit))


@app.get("/blocks/{block_id}")
def block(block_id: str):
    """One block: profile, history, forecast and first action."""
    r = results()
    story = I.block_story(r, block_id.upper(), FFB_PRICE_2025)
    if story is None:
        raise HTTPException(404, f"Block {block_id} not found.")
    hist = r.df[r.df.block_id == block_id.upper()].sort_values("harvest_cycle_no")
    act = r.M["actions"][r.M["actions"].block_id == block_id.upper()]
    return {"block_id": block_id.upper(), "summary": story,
            "history": records(hist[["harvest_cycle_no", "harvest_end_date", "yield_ann_t_ha_yr", "yield_vs_age_peers"]].astype({"harvest_end_date": str})),
            "action": records(act)[0] if len(act) else None}
