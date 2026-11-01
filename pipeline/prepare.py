"""Step 1: data quality checks, cleaning and feature engineering.

Reads the raw sample CSV (or a file given as the first argument) and writes:
  data/processed/harvest_cycle.parquet   one row per block per harvest cycle, with engineered features
  data/processed/quality_checks.csv      every check run and its result
  data/powerbi/*.csv                     a star schema ready to load into Power BI
"""
import os
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw" / "SOPB_Palm_Yield_Optimization_POC_SAC.csv"
if not RAW.exists():  # fall back to the copy next to the project folder
    RAW = ROOT.parent / RAW.name
# Outputs go under data/ unless PALM_DATA_DIR points elsewhere (the app uses this to keep each visitor's upload private)
BASE = Path(os.environ.get("PALM_DATA_DIR") or ROOT / "data")
OUT = BASE / "processed"
PBI = BASE / "powerbi"

PCT_COLS = [
    "missing_palm_pct", "soil_moisture_pct", "soil_organic_carbon_pct", "biocontrol_area_pct",
    "bagworm_incidence_pct", "rhinoceros_beetle_incidence_pct", "rat_damage_pct", "ganoderma_incidence_pct",
    "weed_cover_pct", "ground_cover_pct", "pruning_completion_pct", "ripe_bunch_pct", "unripe_bunch_pct",
    "overripe_bunch_pct", "empty_abnormal_bunch_pct", "estimated_field_loss_pct", "mesocarp_to_fruit_pct",
    "oil_to_bunch_pct", "kernel_to_bunch_pct", "ffa_pct",
]
BUNCH_MIX = ["ripe_bunch_pct", "unripe_bunch_pct", "overripe_bunch_pct", "empty_abnormal_bunch_pct"]
POOR_DRAINAGE = {"Poor", "Very Poor", "Waterlogged-prone", "Imperfect"}


def check(rows, area, name, failed, total, note=""):
    rows.append({
        "area": area, "check": name, "records_failed": int(failed), "records_checked": int(total),
        "pass_rate_pct": round(100 * (1 - failed / total), 2) if total else 100.0,
        "status": "Pass" if failed == 0 else ("Warning" if failed / total < 0.01 else "Fail"),
        "note": note,
    })


def quality_checks(df):
    rows, n = [], len(df)
    # Readability: values that could not be read as numbers or dates
    check(rows, "Validity", "Number and date columns readable", df.attrs.get("unreadable_numbers", 0) + df.attrs.get("unreadable_dates", 0), n,
          "Unreadable values were set to blank" if df.attrs.get("unreadable_numbers", 0) + df.attrs.get("unreadable_dates", 0) else "")
    key_missing = int(df[KEY_COLS].isna().any(axis=1).sum())
    check(rows, "Completeness", "Key fields present (block, cycle, yield, area, interval)", key_missing, n,
          f"{key_missing:,} rows without key fields are left out of the analysis" if key_missing else "")
    # Completeness and grain
    other = df.drop(columns=["water_table_depth_cm"])
    check(rows, "Completeness", "No missing values outside water table depth", int(other.isna().any(axis=1).sum()), n)
    peat = df.soil_type.str.startswith("Peat")
    wt_gap = (df.water_table_depth_cm.isna() & peat) | (df.water_table_depth_cm.notna() & ~peat)
    check(rows, "Completeness", "Water table depth recorded on peat soils only", wt_gap.sum(), n,
          f"{df.water_table_depth_cm.isna().sum():,} blanks are mineral and alluvial soils, where it is not measured. Left blank, not filled.")
    dup = df.duplicated(["block_id", "harvest_cycle_no"]).sum()
    check(rows, "Grain", "One row per block per harvest cycle", dup, n)
    expected = df.block_id.nunique() * df.harvest_cycle_no.nunique()
    check(rows, "Grain", "Every block has every harvest cycle (blocks x cycles)", abs(n - expected), n,
          f"{n:,} rows, {expected:,} expected")
    # Ranges
    bad_pct = ((df[PCT_COLS] < 0) | (df[PCT_COLS] > 100)).any(axis=1).sum()
    check(rows, "Validity", "Percentages between 0 and 100", bad_pct, n)
    check(rows, "Validity", "Soil pH between 3 and 8", (~df.soil_ph.between(3, 8)).sum(), n)
    num = df.select_dtypes("number").drop(columns=["block_latitude", "block_longitude", "estate_latitude", "estate_longitude"], errors="ignore")
    check(rows, "Validity", "No negative measurements", (num < 0).any(axis=1).sum(), n)
    check(rows, "Validity", "Productive area not larger than block area", (df.productive_area_ha > df.block_area_ha + 1e-6).sum(), n)
    # Internal consistency
    implied = df.ffb_tonnes / df.productive_area_ha
    check(rows, "Consistency", "Yield per ha = FFB tonnes / productive area (within 2%)",
          (np.abs(implied - df.ffb_yield_t_ha) / df.ffb_yield_t_ha > 0.02).sum(), n)
    bw = df.bunch_count * df.avg_bunch_weight_kg / 1000
    check(rows, "Consistency", "Bunch count x bunch weight = FFB tonnes (within 5%)",
          (np.abs(bw - df.ffb_tonnes) / df.ffb_tonnes > 0.05).sum(), n)
    mix = df[BUNCH_MIX].sum(axis=1)
    check(rows, "Consistency", "Bunch ripeness mix sums to 100% (within 1 point)", (np.abs(mix - 100) > 1).sum(), n)
    days = (df.harvest_end_date - df.harvest_start_date).dt.days
    check(rows, "Consistency", "Harvest start date before end date", (days < 0).sum(), n)
    age = df.harvest_end_date.dt.year - df.planting_year
    check(rows, "Consistency", "Palm age matches planting year (within 1 year)", (np.abs(age - df.palm_age_years) > 1).sum(), n)
    # Outliers: values more than 4 robust SDs from the median
    out_cols = ["ffb_yield_t_ha", "avg_bunch_weight_kg", "fertilizer_total_kg_ha", "rainfall_cycle_mm", "leaf_k_pct"]
    for c in out_cols:
        med = df[c].median()
        mad = 1.4826 * (df[c] - med).abs().median()
        flagged = ((df[c] - med).abs() > 4 * mad).sum() if mad else 0
        check(rows, "Outliers", f"{c}: within 4 robust SDs of median", flagged, n,
              "Flagged and kept as plausible field variation" if flagged else "")
    # Analytical traps found during exploration
    r = df[["ffb_yield_t_ha", "harvest_interval_days"]].corr().iloc[0, 1]
    rows.append({"area": "Analytical trap", "check": "Raw cycle yield rises with harvest interval",
                 "records_failed": 0, "records_checked": n, "pass_rate_pct": np.nan, "status": "Handled",
                 "note": f"Correlation {r:.2f}. Yield annualised (x 365 / interval days) before comparing blocks."})
    rows.append({"area": "Analytical trap", "check": "Weather repeats across blocks of one estate and cycle",
                 "records_failed": 0, "records_checked": n, "pass_rate_pct": np.nan, "status": "Handled",
                 "note": "Weather is averaged, never summed, at higher levels."})
    return pd.DataFrame(rows)


def engineer(df):
    df = df.sort_values(["block_id", "harvest_cycle_no"]).copy()
    # Fair yield measure
    df["yield_ann_t_ha_yr"] = df.ffb_yield_t_ha * 365 / df.harvest_interval_days
    # Compare each block with palms of the same age
    df["age_band_median_t_ha_yr"] = df.groupby("palm_age_band").yield_ann_t_ha_yr.transform("median")
    df["yield_vs_age_peers"] = df.yield_ann_t_ha_yr - df.age_band_median_t_ha_yr
    band_min = df.groupby("palm_age_band").palm_age_years.transform("min")
    df["palm_age_band_order"] = band_min.rank(method="dense").astype(int)
    # History features per block
    g = df.groupby("block_id").yield_ann_t_ha_yr
    df["prev_yield_ann"] = g.shift(1)
    df["yield_change_vs_prev"] = df.yield_ann_t_ha_yr - df.prev_yield_ann
    df["rolling_2_yield_ann"] = g.transform(lambda s: s.rolling(2, min_periods=1).mean())
    df["next_yield_ann"] = g.shift(-1)
    # Condition flags (thresholds chosen from exploration; see quality report)
    rain_cut = df.groupby("harvest_cycle_no").rainfall_cycle_mm.transform(lambda s: s.quantile(0.67))
    df["wet_cycle"] = df.rainfall_cycle_mm > rain_cut
    df["poor_drainage"] = df.drainage_class.isin(POOR_DRAINAGE)
    df["flag_water_stress"] = df.water_deficit_prior_90d_mm >= 25
    df["flag_waterlogging"] = (df.flooding_days >= 3) | (df.poor_drainage & df.wet_cycle)
    df["flag_low_leaf_k"] = df.leaf_k_pct < 1.0
    df["flag_low_leaf_mg"] = df.leaf_mg_pct < 0.28
    df["flag_ganoderma"] = df.ganoderma_incidence_pct >= 1.5
    df["flag_bagworm"] = df.bagworm_incidence_pct >= 3
    df["flag_long_interval"] = df.harvest_interval_days > 15
    df["flag_poor_access"] = df.road_accessibility_score_1_5 <= 2
    df["flag_missing_palms"] = df.missing_palm_pct >= 5
    df["is_prime_age"] = df.palm_age_band.str.contains("Prime")
    return df


def powerbi_tables(df):
    PBI.mkdir(parents=True, exist_ok=True)
    estate_cols = ["estate_id", "estate_name", "estate_subsidiary", "region_name", "mill_name",
                   "estate_reference_area_ha", "estate_latitude", "estate_longitude"]
    block_cols = ["block_id", "block_name", "division_id", "division_name", "estate_id", "block_area_ha",
                  "productive_area_ha", "soil_type", "terrain_class", "drainage_class", "planting_year",
                  "genetic_line", "block_latitude", "block_longitude", "elevation_m", "slope_pct"]
    df[estate_cols].drop_duplicates("estate_id").to_csv(PBI / "dim_estate.csv", index=False)
    df[block_cols].drop_duplicates("block_id").to_csv(PBI / "dim_block.csv", index=False)
    dates = pd.DataFrame({"date": pd.date_range(df.harvest_start_date.min(), df.harvest_end_date.max())})
    dates["year"], dates["month"], dates["month_name"] = dates.date.dt.year, dates.date.dt.month, dates.date.dt.strftime("%b")
    dates["week"] = dates.date.dt.isocalendar().week.astype(int)
    dates.to_csv(PBI / "dim_date.csv", index=False)
    drop = [c for c in estate_cols + block_cols if c not in ("estate_id", "block_id")]
    fact = df.drop(columns=drop)
    fact.to_csv(PBI / "fact_harvest_cycle.csv", index=False)


DATE_COLS = ["harvest_start_date", "harvest_end_date", "harvest_mid_date", "soil_sample_date", "leaf_sample_date"]
KEY_COLS = ["block_id", "estate_name", "harvest_cycle_no", "palm_age_band", "ffb_yield_t_ha", "ffb_tonnes", "harvest_interval_days", "productive_area_ha"]


def numeric_columns():
    """Columns that are numbers in the reference sample."""
    sample = pd.read_csv(RAW, encoding="utf-8-sig", nrows=500)
    return [c for c in sample.columns if pd.api.types.is_numeric_dtype(sample[c])]


def load_raw(path):
    """Read a file; text in a number column or a bad date becomes blank and is counted, never a crash."""
    df = pd.read_csv(path, encoding="utf-8-sig")
    bad_num = 0
    for c in numeric_columns():
        if c in df and not pd.api.types.is_numeric_dtype(df[c]):
            before = df[c].notna().sum()
            df[c] = pd.to_numeric(df[c], errors="coerce")
            bad_num += int(before - df[c].notna().sum())
    bad_date = 0
    for c in DATE_COLS:
        before = df[c].notna().sum()
        df[c] = pd.to_datetime(df[c], errors="coerce")
        bad_date += int(before - df[c].notna().sum())
    for c in df.select_dtypes("object"):
        df[c] = df[c].str.strip()
    df.attrs["unreadable_numbers"], df.attrs["unreadable_dates"] = bad_num, bad_date
    return df


def required_columns():
    """The columns the pipeline expects: the header of the original sample file."""
    return list(pd.read_csv(RAW, encoding="utf-8-sig", nrows=0).columns)


def main(raw=RAW):
    OUT.mkdir(parents=True, exist_ok=True)
    df = load_raw(raw)
    qc = quality_checks(df)
    qc.to_csv(OUT / "quality_checks.csv", index=False)
    df = df.dropna(subset=KEY_COLS)
    df = df[(df.harvest_interval_days > 0) & (df.productive_area_ha > 0)]
    df = engineer(df)
    df.to_parquet(OUT / "harvest_cycle.parquet", index=False)
    powerbi_tables(df)
    print(qc[["area", "check", "status", "records_failed", "note"]].to_string(index=False))
    print(f"\nWrote {len(df):,} rows x {df.shape[1]} columns")


if __name__ == "__main__":
    import sys
    main(Path(sys.argv[1]) if len(sys.argv) > 1 else RAW)
