"""Data layer: one place that loads the pipeline's results.

The Streamlit app, the REST API, the insight engine and the tests all read results through here,
so they always agree. Plain pandas, no Streamlit, so it runs anywhere.
"""
import json
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATA = ROOT / "data"
FFB_PRICE_2025 = 930.0  # RM per tonne, MPOB 2025 average FFB mill-gate price


@dataclass
class Results:
    """Everything the pipeline produced for one data folder."""
    df: pd.DataFrame                       # one row per block per harvest cycle, with engineered features
    M: dict = field(default_factory=dict)  # model outputs (csv files), by name
    J: dict = field(default_factory=dict)  # model metrics (json files), by name
    QC: pd.DataFrame = None                # data quality checks


def load_results(base=DEFAULT_DATA) -> Results:
    base = Path(base)
    proc, model = base / "processed", base / "model"
    return Results(df=pd.read_parquet(proc / "harvest_cycle.parquet"),
                   M={p.stem: pd.read_csv(p) for p in model.glob("*.csv")},
                   J={p.stem: json.loads(p.read_text()) for p in model.glob("*.json")},
                   QC=pd.read_csv(proc / "quality_checks.csv"))


def wavg(d, col="yield_ann_t_ha_yr"):
    """Area-weighted average, the only correct way to roll yield up."""
    return float((d[col] * d.productive_area_ha).sum() / d.productive_area_ha.sum()) if len(d) else float("nan")


@dataclass
class View:
    """The results narrowed to a set of blocks (the app's filters), with the price used to value gains."""
    r: Results
    f: pd.DataFrame
    nxt: pd.DataFrame
    act: pd.DataFrame
    lev: pd.DataFrame
    price: float = FFB_PRICE_2025

    @property
    def total_gain_t(self):
        return float((self.lev.all_levers * self.lev.productive_area_ha).sum())


def make_view(r: Results, regions=None, estates=None, ages=None, price=FFB_PRICE_2025) -> View:
    f = r.df
    if regions:
        f = f[f.region_name.isin(regions)]
    if estates:
        f = f[f.estate_name.isin(estates)]
    if ages:
        f = f[f.palm_age_band.isin(ages)]
    ids = set(f.block_id)
    pick = lambda name: r.M[name][r.M[name].block_id.isin(ids)]  # noqa: E731
    return View(r, f, pick("forecast_next"), pick("actions"), pick("lever_gains"), price)


def block_record(r: Results, block_id: str):
    """Everything known about one block, or None if it does not exist."""
    hist = r.df[r.df.block_id == block_id].sort_values("harvest_cycle_no")
    if hist.empty:
        return None
    act = r.M["actions"].set_index("block_id")
    nxt = r.M["forecast_next"].set_index("block_id")
    return {"history": hist, "action": act.loc[block_id] if block_id in act.index else None,
            "forecast": nxt.loc[block_id] if block_id in nxt.index else None, "last": hist.iloc[-1]}
