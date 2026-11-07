"""Charts for the AI assistant: a fixed catalogue built from computed results.

The AI (or a keyword rule when offline) only picks a chart by name; the data always comes from the
pipeline, so charts can never show invented numbers. Each chart is a plain spec, drawn by the app.
"""
import re

import pandas as pd

from .store import View, wavg

CATALOGUE = {
    "top_blocks": "Top 10 priority blocks by yearly gain",
    "estates": "Estates by yield against age peers",
    "levers": "Yearly gain by lever (what to fix)",
    "risk": "High-risk blocks by estate",
    "age_curve": "Yield by palm age",
    "drivers": "What drives yield (model importance)",
    "forecast_models": "Forecast error of the 5 algorithms vs baselines",
    "harvest": "Field loss by days between harvest rounds",
    "fertilizer": "Fertilizer situation vs yield (K and Mg)",
    "block": "Yield history of the block named in the question",
}

# Offline choice: first rule whose words start a word in the question
RULES = [("block", r"EST\d{3}-D\d{2}-B\d{2}"),
         ("fertilizer", r"\b(fertil|potassium|magnesium|nutrient|leaf|nitrogen|mop)"),
         ("harvest", r"\b(harvest|round|interval|field loss)"),
         ("forecast_models", r"\b(accura|model|algorithm|error)"),
         ("risk", r"\b(risk|forecast|predict|next cycle)"),
         ("levers", r"\b(lever|rm\b|money|value|worth|opportunit|ringgit|gain)"),
         ("drivers", r"\b(why|driver|cause|factor|differ)"),
         ("age_curve", r"\b(age|old|young)"),
         ("estates", r"\b(estate|attention|worst|best|compare)"),
         ("top_blocks", r"\b(first|priority|fix|start|top|which block)")]


def pick(question):
    q = question.lower()
    for key, pattern in RULES:
        if re.search(pattern, question if key == "block" else q, flags=re.I if key == "block" else 0):
            return key
    return None


def spec(v: View, key, question=""):
    """A chart spec: {title, kind ('barh' | 'bar' | 'line'), data, x, y, color, note} or None."""
    M, f = v.r.M, v.f
    if key == "top_blocks":
        d = v.act.head(10).iloc[::-1].assign(label=lambda d: d.block_id + " · " + d.estate_name.str.replace(" Estate", ""))
        return dict(title=CATALOGUE[key], kind="barh", data=d[["label", "est_gain_t_yr", "top_action"]].rename(
            columns={"label": "Block", "est_gain_t_yr": "Gain, t FFB/yr", "top_action": "First action"}), x="Gain, t FFB/yr", y="Block")
    if key == "estates":
        d = f.groupby("estate_name").yield_vs_age_peers.mean().sort_values().reset_index()
        d.columns = ["Estate", "vs age peers, t/ha/yr"]
        return dict(title=CATALOGUE[key], kind="barh", data=d.round(2), x="vs age peers, t/ha/yr", y="Estate", signed=True)
    if key == "levers":
        ls = M["lever_summary"]
        lev = v.lev
        d = pd.DataFrame({"Issue": ls.issue, "Gain, t FFB/yr": [float((lev[k] * lev.productive_area_ha).sum()) for k in ls.lever]})
        d = d[d["Gain, t FFB/yr"] >= 1].sort_values("Gain, t FFB/yr")
        d["Value, RM/yr"] = (d["Gain, t FFB/yr"] * v.price).round(0)
        return dict(title=CATALOGUE[key], kind="barh", data=d.round(0), x="Gain, t FFB/yr", y="Issue",
                    note=f"Each lever fixed on its own, before costs, at RM {v.price:,.0f}/t.")
    if key == "risk":
        d = v.nxt[v.nxt.risk == "High"].estate_name.str.replace(" Estate", "").value_counts().sort_values().reset_index()
        d.columns = ["Estate", "High-risk blocks"]
        return dict(title=CATALOGUE[key], kind="barh", data=d, x="High-risk blocks", y="Estate") if len(d) else None
    if key == "age_curve":
        d = f.groupby(["palm_age_band_order", "palm_age_band"]).apply(wavg, include_groups=False).reset_index(name="t/ha/yr")
        return dict(title=CATALOGUE[key], kind="bar", data=d[["palm_age_band", "t/ha/yr"]].rename(columns={"palm_age_band": "Palm age"}).round(1),
                    x="Palm age", y="t/ha/yr")
    if key == "drivers":
        d = M["driver_importance"].head(8).iloc[::-1][["label", "importance_t_ha_yr"]]
        d.columns = ["Driver", "Importance, t/ha/yr"]
        return dict(title=CATALOGUE[key], kind="barh", data=d.round(3), x="Importance, t/ha/yr", y="Driver",
                    note="How much the model's error grows when a factor is scrambled.")
    if key == "forecast_models":
        fm = v.r.J["forecast_metrics"]
        d = pd.concat([M["model_comparison"][["model", "mae"]],
                       pd.DataFrame({"model": ["Baseline: same as last cycle"], "mae": [fm["baseline_same_as_last_cycle"]["mae"]]})])
        d = d.sort_values("mae", ascending=False).rename(columns={"model": "Method", "mae": "Average error, t/ha/yr"})
        return dict(title=CATALOGUE[key], kind="barh", data=d.round(3), x="Average error, t/ha/yr", y="Method", note="Lower is better.")
    if key == "harvest":
        d = f.groupby("harvest_interval_days").estimated_field_loss_pct.mean().reset_index()
        d.columns = ["Days between rounds", "Field loss %"]
        return dict(title=CATALOGUE[key], kind="line", data=d.round(2), x="Days between rounds", y="Field loss %",
                    note="Good practice is 7 to 10 days.")
    if key == "fertilizer":
        d = M["feeding_matrix"][["nutrient", "situation", "yield_vs_age_peers"]]
        d.columns = ["Nutrient", "Situation", "vs age peers, t/ha/yr"]
        return dict(title=CATALOGUE[key], kind="barh", data=d.round(2), x="vs age peers, t/ha/yr", y="Situation", color="Nutrient", signed=True)
    if key == "block":
        ids = re.findall(r"EST\d{3}-D\d{2}-B\d{2}", question.upper())
        h = v.r.df[v.r.df.block_id == ids[0]].sort_values("harvest_cycle_no") if ids else pd.DataFrame()
        if h.empty:
            return None
        d = pd.DataFrame({"Harvest cycle": h.harvest_cycle_no, "This block": h.yield_ann_t_ha_yr.round(2),
                          "Age peers (median)": (h.yield_ann_t_ha_yr - h.yield_vs_age_peers).round(2)})
        d = d.melt("Harvest cycle", var_name="Series", value_name="t/ha/yr")
        return dict(title=f"Yield history of {ids[0]}", kind="line", data=d, x="Harvest cycle", y="t/ha/yr", color="Series")
    return None


CHART_TAG = re.compile(r"\n?\s*CHART:\s*([a-z_]+|none)\s*$", re.I)


def split_tag(answer):
    """Remove a trailing 'CHART: name' line the AI adds; return (answer, chart key or None)."""
    m = CHART_TAG.search(answer.strip())
    if not m:
        return answer, None
    key = m.group(1).lower()
    return answer.strip()[:m.start()].rstrip(), (key if key in CATALOGUE else "none")


def ai_instruction():
    return ("\nCHARTS: after your answer, add one last line 'CHART: <name>' choosing the single chart that best supports it, "
            "or 'CHART: none' if no chart helps. Names: " + "; ".join(f"{k} = {t}" for k, t in CATALOGUE.items()) + ".")
