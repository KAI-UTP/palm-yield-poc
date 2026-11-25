"""Export the pipeline's results to web/data/app.json for the web app.

Run after the pipeline:  python web/build_data.py
The web app reads only this file, so it always matches the models.
The Analytics Workbench calls build() and publishes the result to PalmYield (core/publish.py).
"""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import pandas as pd  # noqa: E402

from core.store import FFB_PRICE_2025, load_results  # noqa: E402

LEVER_COLS = ["harvest_round", "road_access", "drain_upkeep", "flooding", "leaf_k", "leaf_mg",
              "ganoderma", "bagworm", "missing_palms", "weeds"]
SIGNALS = ["flooding_days", "road_accessibility_score_1_5", "harvest_interval_days", "bagworm_incidence_pct",
           "ganoderma_incidence_pct", "leaf_k_pct", "leaf_mg_pct", "missing_palm_pct", "weed_cover_pct",
           "soil_moisture_pct", "water_deficit_prior_90d_mm", "soil_ph", "rainfall_prior_90d_mm", "soil_organic_carbon_pct"]

# Field conditions whose link with yield the chatbot can explain from the data (column, label, unit, fixed bins or None = fifths)
RELATIONS = [
    ("soil_ph", "Soil pH", "pH", None),
    ("rainfall_prior_90d_mm", "Rainfall in the 90 days before harvest", "mm", None),
    ("rainfall_cycle_mm", "Rainfall during the harvest cycle", "mm", None),
    ("water_deficit_prior_90d_mm", "Water deficit in the 90 days before harvest", "mm", [0, 0.5, 25, 1000]),
    ("soil_moisture_pct", "Soil moisture", "%", None),
    ("flooding_days", "Flooding days in the cycle", "days", [0, 1.5, 2.5, 100]),
    ("soil_organic_carbon_pct", "Soil organic carbon (high = peat)", "%", None),
    ("leaf_k_pct", "Leaf potassium (K)", "%", None),
    ("leaf_mg_pct", "Leaf magnesium (Mg)", "%", None),
    ("leaf_n_pct", "Leaf nitrogen (N)", "%", None),
    ("fertilizer_total_kg_ha", "Fertilizer applied", "kg/ha", None),
    ("drainage_maintenance_score_1_5", "Drainage upkeep score", "1-5", [0, 2.5, 3.5, 5]),
]


def relations(df):
    """Yield in each range of a field condition, measured as t/ha/yr vs age peers so palm age doesn't hide the effect."""
    out = []
    for col, label, unit, bins in RELATIONS:
        if col not in df:
            continue
        x = df[col]
        cut = pd.cut(x, bins, include_lowest=True) if bins else pd.qcut(x, 5, duplicates="drop")
        g = df.groupby(cut, observed=True).agg(lo=(col, "min"), hi=(col, "max"), n=(col, "size"),
                                                 gap=("yield_vs_age_peers", "mean"), y=("yield_ann_t_ha_yr", "median"))
        rows = [{"lo": r2(r.lo), "hi": r2(r.hi), "n": int(r.n), "gap": r2(r.gap), "y": r2(r.y, 1)} for r in g.itertuples()]
        best, worst = max(rows, key=lambda r: r["gap"]), min(rows, key=lambda r: r["gap"])
        out.append({"key": col, "label": label, "unit": unit, "rho": r2(x.corr(df.yield_vs_age_peers, method="spearman")),
                    "bins": rows, "best": best, "worst": worst, "spread": r2(best["gap"] - worst["gap"])})
    return out


def rain_lags(df):
    """Correlation of yield (vs age peers) with rainfall 0-3 harvest cycles earlier, within each block."""
    s = df.sort_values(["block_id", "harvest_cycle_no"])
    return [{"lag": k, "rho": r2(s.groupby("block_id").rainfall_cycle_mm.shift(k).corr(s.yield_vs_age_peers, method="spearman"), 3)}
            for k in range(4)]


def r2(x, n=2):
    return None if pd.isna(x) else round(float(x), n)


def records(df, cols=None, n=3):
    d = df[cols] if cols else df
    return [{k: (r2(v, n) if isinstance(v, float) else (v.item() if hasattr(v, "item") else v)) for k, v in row.items()}
            for row in d.to_dict("records")]


def build(base=ROOT / "data", source_name=None, published_by=None):
    """Return the web app's data (a dict) built from the pipeline results in `base`."""
    r = load_results(base)
    df = r.df.sort_values(["block_id", "harvest_cycle_no"])
    last = df.groupby("block_id").tail(1).set_index("block_id")
    geo = pd.read_csv(base / "powerbi" / "dim_block.csv").set_index("block_id")
    est = pd.read_csv(base / "powerbi" / "dim_estate.csv")
    nxt = r.M["forecast_next"].set_index("block_id")
    act = r.M["actions"].set_index("block_id")
    lev = r.M["lever_gains"].set_index("block_id")
    clu = r.M["block_clusters"].set_index("block_id")
    hist = df.groupby("block_id").yield_ann_t_ha_yr.apply(lambda s: [r2(v) for v in s])
    gap_all = df.groupby("block_id").yield_vs_age_peers.mean()
    dates = df.groupby("harvest_cycle_no").harvest_end_date.max().astype(str).tolist()

    blocks = []
    for bid, b in last.iterrows():
        a, f, lv = act.loc[bid], nxt.loc[bid], lev.loc[bid]
        blocks.append({
            "id": bid, "name": geo.loc[bid, "block_name"], "estate": b.estate_name, "division": b.division_name,
            "region": b.region_name, "age_band": b.palm_age_band, "age": int(b.palm_age_years),
            "area": r2(b.productive_area_ha), "lat": r2(geo.loc[bid, "block_latitude"], 5), "lon": r2(geo.loc[bid, "block_longitude"], 5),
            "soil": geo.loc[bid, "soil_type"], "genetic": geo.loc[bid, "genetic_line"],
            "fert": b.fertilizer_program, "treat": b.treatment_program,
            "yield": r2(f.yield_ann_t_ha_yr), "peer": r2(f.age_band_median_t_ha_yr), "vs_peers": r2(b.yield_vs_age_peers), "vs_peers_all": r2(gap_all.loc[bid]),
            "fc": r2(f.forecast_t_ha_yr), "fc_low": r2(f.forecast_low), "fc_high": r2(f.forecast_high),
            "fc_vs_peers": r2(f.forecast_vs_age_peers), "risk": f.risk,
            "rank": int(a["rank"]), "priority": r2(a.priority_score, 1), "issues": a.issues if isinstance(a.issues, str) else "",
            "action": a.top_action, "gain_ha": r2(a.est_gain_t_ha_yr), "gain_t": r2(a.est_gain_t_yr, 1),
            "group": clu.loc[bid, "cluster_name"],
            "levers": {k: r2(lv[k], 3) for k in LEVER_COLS if lv[k] > 0}, "all_levers": r2(lv.all_levers, 3),
            "signals": {k: r2(b[k]) for k in SIGNALS},
            "history": hist.loc[bid],
        })

    age = (df.groupby("palm_age_band").agg(age=("palm_age_years", "mean"), y=("yield_ann_t_ha_yr", "median"))
           .sort_values("age").reset_index())
    data = {
        "meta": {"synthetic": True, "source": "SOPB_Palm_Yield_Optimization_POC_SAC.csv (synthetic sample)",
                 "rows": len(df), "blocks": len(blocks), "estates": int(df.estate_name.nunique()),
                 "cycles": int(df.harvest_cycle_no.nunique()), "cycle_dates": dates, "price": FFB_PRICE_2025,
                 "published_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                 "published_from": source_name or "Synthetic sample (SOPB_Palm_Yield_Optimization_POC_SAC.csv)",
                 "published_by": published_by or "pipeline"},
        "estates": records(est[["estate_id", "estate_name", "region_name", "mill_name", "estate_latitude", "estate_longitude"]], n=4),
        "blocks": blocks,
        "levers": records(r.M["lever_summary"]),
        "drivers": records(r.M["driver_importance"].head(12)),
        "patterns": records(r.M["patterns"]),
        "nutrients": records(r.M["nutrient_status"]),
        "feeding": records(r.M["feeding_matrix"]),
        "treatments": records(r.M["treatment_effect"]),
        "groups": records(r.M["cluster_profiles"].sort_values("rank")),
        "models": records(r.M["model_comparison"]),
        "forecast_metrics": r.J["forecast_metrics"], "driver_metrics": r.J["driver_metrics"],
        "quality": records(r.QC.fillna("")),
        "age_curve": records(age),
        "relations": relations(df),
        "rain_lags": rain_lags(df),
        "cycle_days": r2(df.harvest_interval_days.median(), 0),
        "cv_sample":records(r.M["forecast_cv"].sample(600, random_state=1)[["actual_next", "predicted"]]),
    }
    return data


def to_json(data):
    return json.dumps(data, separators=(",", ":"), ensure_ascii=False)


def main(base=ROOT / "data", out=ROOT / "web" / "data" / "app.json"):
    data = build(base)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(to_json(data), encoding="utf-8")
    print(f"wrote {out} ({out.stat().st_size / 1024:.0f} KB, {len(data['blocks'])} blocks)")


if __name__ == "__main__":
    main()
