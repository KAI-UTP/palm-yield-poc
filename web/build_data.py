"""Export the pipeline's results to web/data/app.json for the web app.

Run after the pipeline:  python web/build_data.py
The web app reads only this file, so it always matches the models.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import pandas as pd  # noqa: E402

from core.store import FFB_PRICE_2025, load_results  # noqa: E402

LEVER_COLS = ["harvest_round", "road_access", "drain_upkeep", "flooding", "leaf_k", "leaf_mg",
              "ganoderma", "bagworm", "missing_palms", "weeds"]
SIGNALS = ["flooding_days", "road_accessibility_score_1_5", "harvest_interval_days", "bagworm_incidence_pct",
           "ganoderma_incidence_pct", "leaf_k_pct", "leaf_mg_pct", "missing_palm_pct", "weed_cover_pct",
           "soil_moisture_pct", "water_deficit_prior_90d_mm"]


def r2(x, n=2):
    return None if pd.isna(x) else round(float(x), n)


def records(df, cols=None, n=3):
    d = df[cols] if cols else df
    return [{k: (r2(v, n) if isinstance(v, float) else (v.item() if hasattr(v, "item") else v)) for k, v in row.items()}
            for row in d.to_dict("records")]


def main(base=ROOT / "data", out=ROOT / "web" / "data" / "app.json"):
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
                 "cycles": int(df.harvest_cycle_no.nunique()), "cycle_dates": dates, "price": FFB_PRICE_2025},
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
        "cv_sample": records(r.M["forecast_cv"].sample(600, random_state=1)[["actual_next", "predicted"]]),
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(data, separators=(",", ":"), ensure_ascii=False), encoding="utf-8")
    print(f"wrote {out} ({out.stat().st_size / 1024:.0f} KB, {len(blocks)} blocks)")


if __name__ == "__main__":
    main()
