"""Step 2: machine learning and analytics on the prepared data.

Writes to data/model/:
  driver_importance.csv, partial_dependence.csv, driver_metrics.json   what drives yield
  forecast_cv.csv, forecast_metrics.json, forecast_next.csv           next-cycle forecast and risk
  block_clusters.csv, cluster_profiles.csv                            groups of similar blocks
  patterns.csv                                                        the dataset's 8 embedded patterns, tested
  flag_effects.csv, actions.csv                                       ranked block action list
"""
import json
import os
import time
from pathlib import Path

os.environ.setdefault("LOKY_MAX_CPU_COUNT", str(os.cpu_count() or 4))

import joblib
import numpy as np
import pandas as pd
from scipy import stats
from sklearn.cluster import KMeans
from sklearn.ensemble import ExtraTreesRegressor, GradientBoostingRegressor, HistGradientBoostingRegressor, RandomForestRegressor
from sklearn.linear_model import Ridge
from sklearn.pipeline import make_pipeline
from sklearn.inspection import partial_dependence, permutation_importance
from sklearn.metrics import mean_absolute_error, r2_score, root_mean_squared_error, silhouette_score
from sklearn.model_selection import GroupKFold
from sklearn.preprocessing import StandardScaler

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "processed" / "harvest_cycle.parquet"
OUT = ROOT / "data" / "model"
SEED = 42

LABELS = {
    "palm_age_years": "Palm age", "stand_density_palms_ha": "Stand density", "missing_palm_pct": "Missing palms",
    "harvest_interval_days": "Harvest interval", "rainfall_prior_90d_mm": "Prior 90-day rainfall",
    "water_deficit_prior_90d_mm": "Prior 90-day water deficit", "rainfall_cycle_mm": "Rainfall in cycle",
    "max_dry_spell_days": "Longest dry spell", "soil_moisture_pct": "Soil moisture", "flooding_days": "Flooding days",
    "soil_ph": "Soil pH", "soil_organic_carbon_pct": "Soil organic carbon", "soil_n_pct": "Soil N",
    "soil_p_mg_kg": "Soil P", "soil_k_cmol_kg": "Soil K", "soil_mg_cmol_kg": "Soil Mg", "leaf_n_pct": "Leaf N",
    "leaf_p_pct": "Leaf P", "leaf_k_pct": "Leaf K", "leaf_mg_pct": "Leaf Mg", "leaf_b_ppm": "Leaf B",
    "fertilizer_total_kg_ha": "Fertilizer applied", "fertilizer_k2o_kg_ha": "K2O applied",
    "fertilizer_mgo_kg_ha": "MgO applied", "efb_mulch_t_ha": "EFB mulch", "days_since_last_fertilizer": "Days since fertilizer",
    "bagworm_incidence_pct": "Bagworm", "rhinoceros_beetle_incidence_pct": "Rhinoceros beetle", "rat_damage_pct": "Rat damage",
    "ganoderma_incidence_pct": "Ganoderma", "weed_cover_pct": "Weed cover", "drainage_maintenance_score_1_5": "Drainage upkeep",
    "pruning_completion_pct": "Pruning completion", "road_accessibility_score_1_5": "Road access",
    "field_labour_hours_ha": "Field labour", "elevation_m": "Elevation", "slope_pct": "Slope",
    "yield_ann_t_ha_yr": "Current cycle yield", "prev_yield_ann": "Previous cycle yield",
}
CONDITIONS = [c for c in LABELS if c not in ("yield_ann_t_ha_yr", "prev_yield_ann")]
CATEGORIES = ["drainage_class", "soil_type", "genetic_line", "fertilizer_program", "treatment_program"]
GROUPS = {
    "Palm and stand": ["palm_age_years", "stand_density_palms_ha", "missing_palm_pct"],
    "Water and weather": ["rainfall_prior_90d_mm", "water_deficit_prior_90d_mm", "rainfall_cycle_mm", "max_dry_spell_days", "soil_moisture_pct", "flooding_days", "drainage_class", "drainage_maintenance_score_1_5"],
    "Soil and nutrients": ["soil_ph", "soil_organic_carbon_pct", "soil_n_pct", "soil_p_mg_kg", "soil_k_cmol_kg", "soil_mg_cmol_kg", "leaf_n_pct", "leaf_p_pct", "leaf_k_pct", "leaf_mg_pct", "leaf_b_ppm", "soil_type"],
    "Inputs": ["fertilizer_total_kg_ha", "fertilizer_k2o_kg_ha", "fertilizer_mgo_kg_ha", "efb_mulch_t_ha", "days_since_last_fertilizer", "fertilizer_program"],
    "Pests and disease": ["bagworm_incidence_pct", "rhinoceros_beetle_incidence_pct", "rat_damage_pct", "ganoderma_incidence_pct", "treatment_program"],
    "Field operations": ["harvest_interval_days", "weed_cover_pct", "pruning_completion_pct", "road_accessibility_score_1_5", "field_labour_hours_ha"],
    "Site and genetics": ["elevation_m", "slope_pct", "genetic_line"],
}
GROUP_OF = {f: g for g, fs in GROUPS.items() for f in fs}
FLAG_ACTIONS = {
    "flag_water_stress": ("Water stress", "Conserve soil water: EFB mulch and cover crops; prioritise for any irrigation"),
    "flag_waterlogging": ("Waterlogging", "Clear and deepen drains and check outlets before the wet season"),
    "flag_low_leaf_k": ("Low leaf K", "Raise potassium (MOP) in the next round, then re-sample leaves"),
    "flag_low_leaf_mg": ("Low leaf Mg", "Apply kieserite for magnesium, then re-sample leaves"),
    "flag_ganoderma": ("Ganoderma", "Run a Ganoderma census; sanitise and isolate infected palms"),
    "flag_bagworm": ("Bagworm", "Census bagworm; apply biological or targeted chemical control"),
    "flag_long_interval": ("Long harvest round", "Shorten the harvest round to 10 to 12 days; rebalance teams"),
    "flag_poor_access": ("Poor access", "Repair field roads and paths to cut harvest delays"),
    "flag_missing_palms": ("Missing palms", "Supply-plant vacant points"),
}


def design_matrix(df, numeric):
    X = pd.concat([df[numeric], pd.get_dummies(df[CATEGORIES], prefix_sep="=", dtype=float)], axis=1)
    return X.fillna(X.median(numeric_only=True))


def gbm(**kw):
    return GradientBoostingRegressor(n_estimators=300, learning_rate=0.05, max_depth=3, subsample=0.8, random_state=SEED, **kw)


CANDIDATES = {
    "Linear regression (ridge)": lambda: make_pipeline(StandardScaler(), Ridge(alpha=1.0)),
    "Random forest": lambda: RandomForestRegressor(n_estimators=300, min_samples_leaf=3, n_jobs=-1, random_state=SEED),
    "Extra trees": lambda: ExtraTreesRegressor(n_estimators=400, min_samples_leaf=2, n_jobs=-1, random_state=SEED),
    "Gradient boosting": lambda: gbm(),
    "Histogram gradient boosting": lambda: HistGradientBoostingRegressor(max_iter=300, learning_rate=0.05, random_state=SEED),
}


def drivers(df):
    """Which conditions explain annualised yield? Tested on whole blocks held out from training."""
    X, y, groups = design_matrix(df, CONDITIONS), df.yield_ann_t_ha_yr, df.block_id
    oof, imps = np.zeros(len(df)), []
    for tr, te in GroupKFold(5).split(X, y, groups):
        m = gbm().fit(X.iloc[tr], y.iloc[tr])
        oof[te] = m.predict(X.iloc[te])
        pi = permutation_importance(m, X.iloc[te], y.iloc[te], n_repeats=5, random_state=SEED, scoring="neg_mean_absolute_error")
        imps.append(pd.Series(pi.importances_mean, X.columns))
    imp = pd.concat(imps, axis=1).mean(axis=1)
    # Roll one-hot columns back up to their source field
    src = imp.index.map(lambda c: c.split("=")[0])
    imp = imp.groupby(src).sum().sort_values(ascending=False)
    out = pd.DataFrame({"feature": imp.index, "importance_t_ha_yr": imp.values.round(3)})
    out["label"] = out.feature.map(lambda f: LABELS.get(f, f.replace("_", " ").capitalize()))
    out["group"] = out.feature.map(GROUP_OF).fillna("Other")
    out["share_pct"] = (100 * out.importance_t_ha_yr.clip(lower=0) / out.importance_t_ha_yr.clip(lower=0).sum()).round(1)
    out.to_csv(OUT / "driver_importance.csv", index=False)
    metrics = {"r2_held_out_blocks": round(r2_score(y, oof), 3), "mae_t_ha_yr": round(mean_absolute_error(y, oof), 2),
               "mean_yield_t_ha_yr": round(y.mean(), 2), "folds": 5, "rows": len(df)}
    (OUT / "driver_metrics.json").write_text(json.dumps(metrics, indent=2))
    # How yield responds to each top numeric driver, holding the rest as they are
    final = gbm().fit(X, y)
    joblib.dump({"model": final, "columns": list(X.columns), "medians": X.median().to_dict()}, OUT / "driver_model.joblib")
    curves = []
    for f in [f for f in out.feature if f in CONDITIONS][:8]:
        pd_ = partial_dependence(final, X, [f], grid_resolution=25, method="brute")
        curves.append(pd.DataFrame({"feature": f, "label": LABELS[f], "value": pd_["grid_values"][0], "yield_t_ha_yr": pd_["average"][0]}))
    pd.concat(curves).round(3).to_csv(OUT / "partial_dependence.csv", index=False)
    print("Drivers:", metrics)
    return final, list(X.columns)


def forecast(df):
    """Predict next cycle's annualised yield; compare with simple baselines on unseen blocks."""
    feats = ["yield_ann_t_ha_yr", "prev_yield_ann"] + CONDITIONS
    train = df.dropna(subset=["next_yield_ann"]).reset_index(drop=True)
    X, y, groups = design_matrix(train, feats), train.next_yield_ann, train.block_id
    # Compare five algorithms on the same unseen-block folds; the lowest average error wins
    folds = list(GroupKFold(5).split(X, y, groups))
    rows, oofs = [], {}
    for name, make in CANDIDATES.items():
        t0, o = time.time(), np.zeros(len(train))
        for tr, te in folds:
            o[te] = make().fit(X.iloc[tr], y.iloc[tr]).predict(X.iloc[te])
        oofs[name] = o
        rows.append({"model": name, "mae": round(mean_absolute_error(y, o), 3), "rmse": round(root_mean_squared_error(y, o), 3),
                     "r2": round(r2_score(y, o), 3), "train_seconds": round(time.time() - t0, 1)})
    comp = pd.DataFrame(rows).sort_values("mae")
    best = comp.iloc[0].model
    comp["chosen"] = comp.model == best
    comp.to_csv(OUT / "model_comparison.csv", index=False)
    oof = oofs[best]
    base_last = train.yield_ann_t_ha_yr
    base_age = train.age_band_median_t_ha_yr

    def score(p):
        return {"mae": round(mean_absolute_error(y, p), 3), "rmse": round(root_mean_squared_error(y, p), 3), "r2": round(r2_score(y, p), 3)}

    metrics = {"model": score(oof), "chosen_model": best, "baseline_same_as_last_cycle": score(base_last), "baseline_age_band_median": score(base_age),
               "rows": len(train), "blocks": int(train.block_id.nunique())}
    metrics["mae_improvement_vs_last_cycle_pct"] = round(100 * (1 - metrics["model"]["mae"] / metrics["baseline_same_as_last_cycle"]["mae"]), 1)
    (OUT / "forecast_metrics.json").write_text(json.dumps(metrics, indent=2))
    cv = train[["block_id", "estate_name", "harvest_cycle_no", "palm_age_band", "next_yield_ann", "yield_ann_t_ha_yr"]].copy()
    cv["predicted"] = oof.round(2)
    cv.rename(columns={"next_yield_ann": "actual_next", "yield_ann_t_ha_yr": "current"}).to_csv(OUT / "forecast_cv.csv", index=False)
    # Forecast the cycle after the last one, with an 80% range from quantile models
    latest = df.harvest_cycle_no == df.harvest_cycle_no.max()
    Xt = X
    Xl = design_matrix(df, feats)[latest].reindex(columns=Xt.columns, fill_value=0)
    point = CANDIDATES[best]().fit(Xt, y).predict(Xl)
    # 80% range by split conformal: the 80th percentile of held-out errors. Coverage checked fold by fold.
    err = np.abs(y.values - oof)
    hits = [np.mean(err[te] <= np.quantile(np.delete(err, te), 0.8)) for _, te in folds]
    q80 = float(np.quantile(err, 0.8))
    metrics["range_80_half_width"] = round(q80, 2)
    metrics["range_80_coverage_pct"] = round(100 * float(np.mean(hits)), 1)
    (OUT / "forecast_metrics.json").write_text(json.dumps(metrics, indent=2))
    nxt = df.loc[latest, ["block_id", "estate_name", "division_name", "palm_age_band", "productive_area_ha", "yield_ann_t_ha_yr", "age_band_median_t_ha_yr"]].copy()
    nxt["forecast_t_ha_yr"], nxt["forecast_low"], nxt["forecast_high"] = point.round(2), (point - q80).round(2), (point + q80).round(2)
    nxt["forecast_vs_age_peers"] = (nxt.forecast_t_ha_yr - nxt.age_band_median_t_ha_yr).round(2)
    nxt["risk"] = pd.cut(nxt.forecast_vs_age_peers, [-np.inf, -2, -1, np.inf], labels=["High", "Medium", "Low"]).astype(str)
    nxt.to_csv(OUT / "forecast_next.csv", index=False)
    print("Forecast:", metrics)
    return nxt


def clusters(df):
    """Group blocks by their conditions, then see which group yields best for its age."""
    feats = ["soil_moisture_pct", "water_deficit_prior_90d_mm", "flooding_days", "road_accessibility_score_1_5", "harvest_interval_days",
             "bagworm_incidence_pct", "ganoderma_incidence_pct", "leaf_k_pct", "leaf_mg_pct", "missing_palm_pct", "weed_cover_pct"]
    blk = df.groupby("block_id").agg({**{f: "mean" for f in feats}, "yield_vs_age_peers": "mean", "yield_ann_t_ha_yr": "mean",
                                      "is_prime_age": "first", "estate_name": "first", "palm_age_band": "first", "productive_area_ha": "first"})
    Z = StandardScaler().fit_transform(blk[feats])
    scores = {k: silhouette_score(Z, KMeans(k, n_init=10, random_state=SEED).fit_predict(Z)) for k in range(3, 8)}
    k = max(scores, key=scores.get)
    blk["cluster"] = KMeans(k, n_init=10, random_state=SEED).fit_predict(Z)
    zdf = pd.DataFrame(Z, columns=feats, index=blk.index)
    prof = blk.groupby("cluster").agg(blocks=("yield_vs_age_peers", "size"), yield_vs_age_peers=("yield_vs_age_peers", "mean"),
                                      yield_t_ha_yr=("yield_ann_t_ha_yr", "mean"), prime_share=("is_prime_age", "mean"))
    zmean = zdf.groupby(blk.cluster).mean()
    names = {}
    for c in zmean.index:
        top = zmean.loc[c].abs().sort_values(ascending=False).index[:3]
        names[c] = ", ".join(("high " if zmean.loc[c, f] > 0 else "low ") + LABELS[f].lower() for f in top)
    prof["traits"] = prof.index.map(names)
    prof = prof.join(blk.groupby("cluster")[feats].mean().round(2)).sort_values("yield_vs_age_peers", ascending=False)
    prof["rank"] = range(1, len(prof) + 1)
    prof["name"] = prof["rank"].map(lambda r: f"Group {chr(64 + r)}")
    blk["cluster_name"] = blk.cluster.map(prof["name"])
    prof.round(3).reset_index().to_csv(OUT / "cluster_profiles.csv", index=False)
    blk.round(3).reset_index().to_csv(OUT / "block_clusters.csv", index=False)
    (OUT / "cluster_metrics.json").write_text(json.dumps({"k": int(k), "silhouette": round(float(scores[k]), 3)}))
    print(f"Clusters: k={k} silhouette={scores[k]:.3f}")
    return blk, prof, k, scores[k]


def patterns(df, blk, prof):
    """Test each pattern the dataset guide says was embedded."""
    r, rows = df.yield_vs_age_peers, []

    def add(n, name, test, evidence, ok):
        rows.append({"no": n, "pattern": name, "test": test, "evidence": evidence, "verdict": "Confirmed" if ok else "Not found"})

    age = df.groupby(["palm_age_band_order", "palm_age_band"]).yield_ann_t_ha_yr.mean().reset_index()
    pk = age.loc[age.yield_ann_t_ha_yr.idxmax()]
    add(1, "Palm age curve", "Yield rises to prime age then falls",
        f"Peak {pk.yield_ann_t_ha_yr:.1f} t/ha/yr at {pk.palm_age_band}; youngest {age.yield_ann_t_ha_yr.iloc[0]:.1f}, oldest {age.yield_ann_t_ha_yr.iloc[-1]:.1f}",
        "Prime" in pk.palm_age_band and age.yield_ann_t_ha_yr.iloc[0] < pk.yield_ann_t_ha_yr > age.yield_ann_t_ha_yr.iloc[-1])
    a, b = r[df.poor_drainage & df.wet_cycle].mean(), r[~df.poor_drainage & ~df.wet_cycle].mean()
    add(2, "Waterlogging vs drainage", "Poor drainage in wet cycles vs good drainage in dry cycles, vs age peers",
        f"{a:+.2f} vs {b:+.2f} t/ha/yr; flood days {df[df.poor_drainage & df.wet_cycle].flooding_days.mean():.1f} vs {df[~df.poor_drainage & ~df.wet_cycle].flooding_days.mean():.1f}", a < b)
    a, b = r[df.water_deficit_prior_90d_mm >= 25].mean(), r[df.water_deficit_prior_90d_mm == 0].mean()
    add(3, "Lagged water deficit", "Prior 90-day deficit of 25 mm or more vs none, vs age peers", f"{a:+.2f} vs {b:+.2f} t/ha/yr", a < b)
    qk, qm = pd.qcut(df.leaf_k_pct, 4, labels=False), pd.qcut(df.leaf_mg_pct, 4, labels=False)
    k0, k3, m0, m3 = r[qk == 0].mean(), r[qk == 3].mean(), r[qm == 0].mean(), r[qm == 3].mean()
    add(4, "Leaf K and Mg status", "Lowest vs highest quarter of leaf K and Mg, vs age peers",
        f"K {k0:+.2f} vs {k3:+.2f}; Mg {m0:+.2f} vs {m3:+.2f} t/ha/yr (hidden until age is removed)", k0 < k3 and m0 < m3)
    poor, good = df.road_accessibility_score_1_5 <= 2, df.road_accessibility_score_1_5 >= 4
    add(5, "Harvest discipline", "Poor vs good road access: harvest interval and field loss",
        f"{df[poor].harvest_interval_days.mean():.1f} vs {df[good].harvest_interval_days.mean():.1f} days; field loss {df[poor].estimated_field_loss_pct.mean():.1f}% vs {df[good].estimated_field_loss_pct.mean():.1f}%",
        df[poor].estimated_field_loss_pct.mean() > df[good].estimated_field_loss_pct.mean())
    bw = df[df.treatment_program.str.startswith("Bagworm")].groupby("harvest_cycle_no").bagworm_incidence_pct.mean()
    add(6, "Pest treatment response", "Bagworm incidence in bagworm-treated blocks, first vs last cycle",
        f"{bw.iloc[0]:.2f}% to {bw.iloc[-1]:.2f}% ({100 * (bw.iloc[-1] / bw.iloc[0] - 1):+.0f}%)", bw.iloc[-1] < bw.iloc[0])
    gl = df.groupby("genetic_line").yield_vs_age_peers.mean().sort_values()
    f, p = stats.f_oneway(*[g.values for _, g in df.groupby("genetic_line").yield_vs_age_peers])
    add(7, "Genetic line differences", "Yield vs age peers by genetic line (one-way ANOVA)",
        f"{gl.index[-1]} {gl.iloc[-1]:+.2f} vs {gl.index[0]} {gl.iloc[0]:+.2f} t/ha/yr; p = {p:.1g}", p < 0.05)
    best = prof.iloc[0]
    other = blk[blk.cluster_name != best["name"]].yield_vs_age_peers.mean()
    add(8, "Top-performing combination", "Clustering blocks by conditions; best group vs the rest",
        f"{best['name']} ({int(best.blocks)} blocks, {best.traits}): {best.yield_vs_age_peers:+.2f} vs {other:+.2f} t/ha/yr", best.yield_vs_age_peers > other)
    out = pd.DataFrame(rows)
    out.to_csv(OUT / "patterns.csv", index=False)
    print(out[["no", "pattern", "verdict", "evidence"]].to_string(index=False))


# Controllable levers for the what-if: feature, target value rule, issue name, first action.
LEVERS = {
    "harvest_round": ("harvest_interval_days", lambda v: np.minimum(v, 10), "Long harvest round", "Cut the harvest round to 10 days (good practice is 7 to 10); rebalance harvest teams"),
    "road_access": ("road_accessibility_score_1_5", lambda v: np.maximum(v, 4), "Poor road access", "Repair field roads and harvesting paths"),
    "drain_upkeep": ("drainage_maintenance_score_1_5", lambda v: np.maximum(v, 4), "Drains poorly kept", "Clear and deepen drains; check outlets before the wet season"),
    "flooding": ("flooding_days", lambda v: np.minimum(v, 0), "Flooding", "Install or repair water gates and outlets in flood-prone blocks"),
    "leaf_k": ("leaf_k_pct", lambda v: np.maximum(v, 1.10), "Low leaf K", "Raise potassium (MOP) in the next round, then re-sample leaf 17"),
    "leaf_mg": ("leaf_mg_pct", lambda v: np.maximum(v, 0.30), "Low leaf Mg", "Apply kieserite for magnesium, then re-sample leaf 17"),
    "ganoderma": ("ganoderma_incidence_pct", lambda v: np.minimum(v, 0.5), "Ganoderma", "Run a Ganoderma census; sanitise and isolate infected palms"),
    "bagworm": ("bagworm_incidence_pct", lambda v: np.minimum(v, 1.0), "Bagworm", "Census bagworm; apply biological or targeted chemical control"),
    "missing_palms": ("missing_palm_pct", lambda v: np.minimum(v, 2.0), "Missing palms", "Supply-plant vacant points"),
    "weeds": ("weed_cover_pct", lambda v: np.minimum(v, 15), "Weed competition", "Bring weed cover under 15% with targeted circle and path weeding"),
}
# Commonly cited critical levels for leaf 17 of mature palms (Ochs and Olvin 1977, via Fairhurst and Mutert 1999)
LEAF17_CRITICAL = {"leaf_n_pct": ("Nitrogen (N)", 2.50), "leaf_p_pct": ("Phosphorus (P)", 0.15), "leaf_k_pct": ("Potassium (K)", 1.00), "leaf_mg_pct": ("Magnesium (Mg)", 0.24)}


def levers(df, final, cols):
    """What-if: predicted yield gain for each block if one lever (or all) is brought to a good level.
    Uses the driver model, so overlapping issues are not double counted."""
    last = df[df.harvest_cycle_no == df.harvest_cycle_no.max()].reset_index(drop=True)
    X = design_matrix(last, CONDITIONS).reindex(columns=cols, fill_value=0)
    base = final.predict(X)
    out = last[["block_id", "productive_area_ha"]].copy()
    allx = X.copy()
    for key, (feat, rule, _, _) in LEVERS.items():
        xc = X.copy()
        xc[feat] = rule(X[feat])
        allx[feat] = rule(allx[feat])
        out[key] = np.clip(final.predict(xc) - base, 0, None).round(3)
    out["all_levers"] = np.clip(final.predict(allx) - base, 0, None).round(3)
    out["predicted_now"] = base.round(2)
    out.to_csv(OUT / "lever_gains.csv", index=False)
    summ = []
    for key, (feat, _, issue, action) in LEVERS.items():
        g = out[key]
        summ.append({"lever": key, "issue": issue, "action": action, "blocks_with_gain": int((g >= 0.1).sum()),
                     "avg_gain_where_applies_t_ha_yr": round(g[g >= 0.1].mean(), 2) if (g >= 0.1).any() else 0.0,
                     "total_gain_t_yr": round(float((g * out.productive_area_ha).sum()), 0)})
    summ = pd.DataFrame(summ).sort_values("total_gain_t_yr", ascending=False)
    summ.to_csv(OUT / "lever_summary.csv", index=False)
    print(f"Levers: all-lever gain {float((out.all_levers * out.productive_area_ha).sum()):,.0f} t/yr; sum of single levers {summ.total_gain_t_yr.sum():,.0f} t/yr")
    return out


def nutrients(df):
    """Leaf status against literature critical levels, and whether fertilizer went where it was needed."""
    r, rows = df.yield_vs_age_peers, []
    for col, (name, crit) in LEAF17_CRITICAL.items():
        low = df[col] < crit
        rows.append({"nutrient": name, "critical_level_pct": crit, "share_below_pct": round(100 * low.mean(), 1),
                     "yield_vs_peers_below": round(r[low].mean(), 2) if low.any() else np.nan, "yield_vs_peers_adequate": round(r[~low].mean(), 2)})
    pd.DataFrame(rows).to_csv(OUT / "nutrient_status.csv", index=False)
    d = df.sort_values(["block_id", "harvest_cycle_no"])
    rows = []
    labels = {(True, False): "Under-fed: low leaf, none applied", (True, True): "Low leaf despite fertilizer",
              (False, True): "Adequate and fertilized", (False, False): "Adequate, none applied"}
    for nut, leaf, fert, crit in [("K", "leaf_k_pct", "fertilizer_k2o_kg_ha", 1.00), ("Mg", "leaf_mg_pct", "fertilizer_mgo_kg_ha", 0.24)]:
        applied = (d[fert] > 0) | (d.groupby("block_id")[fert].shift(1).fillna(0) > 0)
        low = d[leaf] < crit
        for lo in (True, False):
            for ap in (True, False):
                m = (low == lo) & (applied == ap)
                rows.append({"nutrient": nut, "situation": labels[(lo, ap)], "block_cycles": int(m.sum()), "share_pct": round(100 * m.mean(), 1),
                             "yield_vs_age_peers": round(d.yield_vs_age_peers[m].mean(), 2) if m.any() else np.nan})
    pd.DataFrame(rows).to_csv(OUT / "feeding_matrix.csv", index=False)


def treatments(df):
    """Do treatments work? Change in incidence over the next cycle where pressure was high."""
    d = df.sort_values(["block_id", "harvest_cycle_no"]).copy()
    rows = []
    for pest, col, thr in [("Bagworm", "bagworm_incidence_pct", 3.0), ("Rhinoceros beetle", "rhinoceros_beetle_incidence_pct", 2.0), ("Ganoderma", "ganoderma_incidence_pct", 1.5)]:
        d["nxt"] = d.groupby("block_id")[col].shift(-1)
        h = d[(d[col] >= thr) & d.nxt.notna()]
        for prog, g in h.groupby("treatment_program"):
            if len(g) >= 10:
                rows.append({"pest": pest, "treatment_program": prog, "block_cycles": len(g), "incidence_now_pct": round(g[col].mean(), 2),
                             "incidence_next_pct": round(g.nxt.mean(), 2), "change_pct_points": round((g.nxt - g[col]).mean(), 2)})
    pd.DataFrame(rows).sort_values(["pest", "change_pct_points"]).to_csv(OUT / "treatment_effect.csv", index=False)


def actions(df, nxt, blk, lv):
    """Rank blocks by the what-if gain from all levers plus forecast shortfall."""
    rows = []
    for _, row in lv.iterrows():
        gains = sorted(((row[k], k) for k in LEVERS if row[k] >= 0.1), reverse=True)
        rows.append({"block_id": row.block_id, "issues": ", ".join(LEVERS[k][2] for _, k in gains[:4]) or "None",
                     "top_action": LEVERS[gains[0][1]][3] if gains else "Keep current practice",
                     "est_gain_t_ha_yr": round(row.all_levers, 2), "est_gain_t_yr": round(row.all_levers * row.productive_area_ha, 1)})
    act = pd.DataFrame(rows)
    meta = df[df.harvest_cycle_no == df.harvest_cycle_no.max()][["block_id", "estate_name", "division_name", "palm_age_band", "productive_area_ha"]]
    act = meta.merge(act, on="block_id").merge(nxt[["block_id", "yield_ann_t_ha_yr", "forecast_t_ha_yr", "forecast_vs_age_peers", "risk"]], on="block_id")
    act = act.merge(blk[["cluster_name"]].reset_index(), on="block_id")
    act["priority_score"] = (act.est_gain_t_yr + np.maximum(0, -act.forecast_vs_age_peers) * act.productive_area_ha).round(1)
    act = act.sort_values("priority_score", ascending=False)
    act.insert(0, "rank", range(1, len(act) + 1))
    act.to_csv(OUT / "actions.csv", index=False)
    print(f"Actions: top 50 blocks hold {act.head(50).est_gain_t_yr.sum():,.0f} t/yr of what-if gain")


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    df = pd.read_parquet(DATA)
    final, cols = drivers(df)
    nxt = forecast(df)
    blk, prof, k, sil = clusters(df)
    patterns(df, blk, prof)
    lv = levers(df, final, cols)
    nutrients(df)
    treatments(df)
    actions(df, nxt, blk, lv)


if __name__ == "__main__":
    main()
