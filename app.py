"""Palm Yield Optimization POC: Streamlit app.

Run the pipeline first (python pipeline/prepare.py, then python pipeline/model.py), then:
    streamlit run app.py
"""
import json
import os
import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import plotly.io as pio
import streamlit as st

ROOT = Path(__file__).resolve().parent
DEFAULT_DATA = ROOT / "data"
PROC, MODEL = DEFAULT_DATA / "processed", DEFAULT_DATA / "model"  # the bundled sample; a visitor's upload uses its own folder
sys.path.insert(0, str(ROOT / "pipeline"))
from model import CONDITIONS, LABELS, LEVERS, design_matrix, load_driver_model  # noqa: E402
from prepare import RAW as RAW_SAMPLE, load_raw, quality_checks, required_columns  # noqa: E402

SESSIONS = DEFAULT_DATA / "sessions"   # one private folder per visitor who runs their own file
SESSION_TTL_HOURS = 24

# ---------- Design tokens (validated default data-viz palette, dark mode) ----------
INK, INK2, MUTED = "#f0efec", "#c3c2b7", "#898781"
GRID, AXIS, SURFACE, PAGE = "#2c2c2a", "#383835", "#1a1a19", "#0d0d0d"
BLUE, ORANGE = "#3987e5", "#d95926"          # categorical slots 1 and 2 (dark steps)
GREY = "#5f5e59"                              # de-emphasised marks
GOOD, WARN, CRIT = "#0ca30c", "#fab219", "#d03b3b"
DIVERGE = [[0, "#d03b3b"], [0.5, "#383835"], [1, "#3987e5"]]   # red <- grey -> blue
FONT = 'system-ui, -apple-system, "Segoe UI", Roboto, sans-serif'
RISK_ICON = {"High": "🔴 High", "Medium": "🟠 Medium", "Low": "🟢 Low"}

# What each what-if slider means: (unit, one-line explanation)
LEVER_HELP = {
    "harvest_interval_days": ("days", "Days between harvest rounds. Good practice is 7 to 10; longer rounds leave fruit to over-ripen and drop."),
    "road_accessibility_score_1_5": ("score 1–5", "Condition of field roads and paths, 1 poor to 5 good. Poor access slows harvesting and collection."),
    "drainage_maintenance_score_1_5": ("score 1–5", "How well drains are kept clear, 1 poor to 5 good. Blocked drains lead to waterlogging."),
    "flooding_days": ("days", "Days the block was flooded or waterlogged this cycle. Flooding damages roots and blocks access."),
    "leaf_k_pct": ("% in leaf", "Potassium in leaf 17. Below 1.00% is deficient; raise with MOP fertilizer."),
    "leaf_mg_pct": ("% in leaf", "Magnesium in leaf 17. Below 0.24% is deficient; raise with kieserite."),
    "ganoderma_incidence_pct": ("% of palms", "Palms with Ganoderma basal stem rot. Infected palms do not recover; remove and isolate them."),
    "bagworm_incidence_pct": ("% of palms", "Palms with bagworm leaf damage. Biological or targeted chemical control brings it down."),
    "missing_palm_pct": ("% of points", "Planting points with no productive palm. Supply-planting fills the gaps."),
    "weed_cover_pct": ("% of ground", "Ground covered by weeds that compete with palms for water and nutrients. Aim for under 15%."),
}

BENCH = {"Malaysia estates 2025": 17.77, "Sarawak estates 2025": 15.98}
MPOB_URL = "https://bepi.mpob.gov.my/images/overview/Overview2025.pdf"
FFB_PRICE_2025 = 930.0  # RM per tonne, MPOB 2025 average FFB mill-gate price

pio.templates["palm"] = go.layout.Template(layout=dict(
    font=dict(family=FONT, size=12, color=INK2), colorway=[BLUE, ORANGE, "#199e70", "#c98500", "#d55181", "#008300", "#9085e9", "#e66767"],
    paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", bargap=0.35, bargroupgap=0.08,
    xaxis=dict(showgrid=False, linecolor=AXIS, zeroline=False, ticks="", title_font=dict(color=MUTED, size=12), tickfont=dict(color=MUTED)),
    yaxis=dict(gridcolor=GRID, gridwidth=1, linecolor=AXIS, zeroline=False, ticks="", title_font=dict(color=MUTED, size=12), tickfont=dict(color=MUTED)),
    hoverlabel=dict(bgcolor="#262624", bordercolor=AXIS, font=dict(family=FONT, color=INK, size=12)),
    legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0, title_text="", font=dict(color=INK2)),
    margin=dict(l=4, r=12, t=8, b=4)))
px.defaults.template = "plotly_dark+palm"

st.set_page_config(page_title="Palm Yield Optimization", page_icon="🌴", layout="wide", initial_sidebar_state="expanded")
st.markdown(f"""<style>
  .block-container {{padding-top: 2.2rem; padding-bottom: 3rem; max-width: 1400px;}}
  h1 {{font-size: 1.9rem !important; font-weight: 650 !important; letter-spacing: -0.01em; margin-bottom: 0 !important;}}
  h3 {{font-size: 1.05rem !important; font-weight: 600 !important;}}
  .lede {{color: {INK2}; font-size: 1.02rem; line-height: 1.55; max-width: 72ch; margin: .2rem 0 1.1rem;}}
  .eyebrow {{color: {MUTED}; font-size: .78rem; letter-spacing: .06em; text-transform: uppercase; font-weight: 600;}}
  [data-testid="stMetric"] {{background: {SURFACE};}}
  [data-testid="stMetricLabel"] p {{color: {INK2}; font-size: .82rem; white-space: normal !important;}}
  [data-testid="stMetricLabel"] div {{white-space: normal !important; overflow: visible !important; text-overflow: clip !important;}}
  [data-testid="stMetricValue"] {{font-size: 1.7rem; font-weight: 600; color: {INK};}}
  [data-testid="stVerticalBlockBorderWrapper"] > div > [data-testid="stVerticalBlock"] {{background: {SURFACE};}}
  .pill {{display:inline-block; padding: 1px 9px; border-radius: 999px; font-size: .78rem; font-weight: 600;}}
  .pill.ok {{background: rgba(12,163,12,.16); color: #6fd66f;}} .pill.no {{background: {GRID}; color: {INK2};}}
  .synthetic {{background: #2a2416; border: 1px solid #5c4a1a; color: #f3d58a; border-radius: 8px; padding: 8px 10px; font-size: .82rem;}}
  [data-testid="stSidebarNav"] {{padding-top: .3rem;}}
  /* Map controls: keep the attribution inside the map's bottom-right corner (the map library's own CSS does not load here) */
  .maplibregl-control-container > div {{position: absolute; z-index: 2; pointer-events: none;}}
  .maplibregl-ctrl-top-left {{top: 0; left: 0;}} .maplibregl-ctrl-top-right {{top: 0; right: 0;}}
  .maplibregl-ctrl-bottom-left {{bottom: 0; left: 0;}} .maplibregl-ctrl-bottom-right {{bottom: 0; right: 0;}}
  .maplibregl-ctrl {{pointer-events: auto;}}
  .maplibregl-ctrl-attrib {{margin: 0 6px 6px 0; padding: 1px 6px; border-radius: 4px; background: rgba(13,13,13,.75);
                            font-size: 10px; line-height: 16px; color: {MUTED};}}
  .maplibregl-ctrl-attrib a {{color: {INK2};}}
  .maplibregl-ctrl-attrib-button {{display: none;}}
</style>""", unsafe_allow_html=True)


# ---------- Data ----------
@st.cache_data(max_entries=20)
def load(base):
    proc, model = Path(base) / "processed", Path(base) / "model"
    df = pd.read_parquet(proc / "harvest_cycle.parquet")
    m = {p.stem: pd.read_csv(p) for p in model.glob("*.csv")}
    j = {p.stem: json.loads(p.read_text()) for p in model.glob("*.json")}
    return df, m, j, pd.read_csv(proc / "quality_checks.csv")


@st.cache_resource(max_entries=20)
def driver_model(base):
    # Refits the what-if model if the host has a different scikit-learn than the one that saved it
    return load_driver_model(pd.read_parquet(Path(base) / "processed" / "harvest_cycle.parquet"), Path(base) / "model")


def clean_old_sessions():
    """Remove private folders nobody has used for a day, so the server does not fill up."""
    import shutil
    import time
    if SESSIONS.exists():
        for d in SESSIONS.iterdir():
            if d.is_dir() and time.time() - d.stat().st_mtime > SESSION_TTL_HOURS * 3600:
                shutil.rmtree(d, ignore_errors=True)


def data_base():
    """This visitor's data folder: their private upload if they ran one, else the shared sample."""
    base = st.session_state.get("data_dir")
    if base and (Path(base) / "model" / "actions.csv").exists():
        return Path(base)
    st.session_state.pop("data_dir", None)
    st.session_state.pop("source", None)
    return DEFAULT_DATA


needed = [PROC / "harvest_cycle.parquet", MODEL / "actions.csv", MODEL / "driver_model.joblib", MODEL / "lever_gains.csv", MODEL / "model_comparison.csv"]
if not all(p.exists() for p in needed):
    # First start on a fresh machine or cloud host: build everything from the bundled sample
    import subprocess
    with st.status("First start: preparing data and training models. This takes two to three minutes.", expanded=True) as boot:
        for script in ("prepare.py", "model.py"):
            st.write(f"Running {script}")
            res = subprocess.run([sys.executable, str(ROOT / "pipeline" / script)], capture_output=True, text=True, cwd=ROOT, timeout=1800)
            if res.returncode != 0:
                boot.update(label="Setup failed.", state="error")
                st.code(res.stderr[-2000:])
                st.stop()
        boot.update(label="Ready.", state="complete")
    st.rerun()
clean_old_sessions()
BASE = data_base()
df, M, J, QC = load(str(BASE))
fm, dm = J["forecast_metrics"], J["driver_metrics"]


# ---------- Helpers ----------
def wavg(d, col="yield_ann_t_ha_yr"):
    return float((d[col] * d.productive_area_ha).sum() / d.productive_area_ha.sum()) if len(d) else float("nan")


def lc(s):
    """Lower-case the first letter, except proper nouns."""
    return s if s.startswith("Ganoderma") else s[:1].lower() + s[1:]


def rm(v):
    return f"RM {v / 1e6:,.2f}m" if abs(v) >= 1e6 else f"RM {v:,.0f}"


def header(eyebrow, title, lede):
    st.markdown(f'<div class="eyebrow">{eyebrow}</div>', unsafe_allow_html=True)
    st.title(title)
    st.markdown(f'<div class="lede">{lede}</div>', unsafe_allow_html=True)


def chart(fig, key, h=320, data=None):
    """Render a chart in the house style, with a table view of its data."""
    fig.update_layout(height=h, legend_title_text="")
    fig.update_traces(marker_cornerradius=4, selector=dict(type="bar"))
    # Leave room for value labels drawn outside the bar ends
    for tr in fig.data:
        if tr.type == "bar" and tr.text is not None and getattr(tr, "textposition", None) == "outside":
            vals = np.asarray(tr.x if tr.orientation == "h" else tr.y, dtype=float)
            if len(vals) and np.isfinite(vals).any():
                lo, hi = min(0.0, float(np.nanmin(vals))), max(0.0, float(np.nanmax(vals)))
                pad = 0.22 * (hi - lo or 1)
                (fig.update_xaxes if tr.orientation == "h" else fig.update_yaxes)(range=[lo - (pad if lo < 0 else 0), hi + (pad if hi > 0 else 0)])
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False}, key=key)
    if data is not None:
        with st.expander("View as table"):
            st.dataframe(data, hide_index=True, use_container_width=True)


def card(title, note=None):
    c = st.container(border=True)
    c.markdown(f"### {title}")
    if note:
        c.caption(note)
    return c


def kpis(items):
    cols = st.columns(len(items))
    for col, (label, value, help_) in zip(cols, items):
        col.metric(label, value, help=help_, border=True)


# ---------- Sidebar: data source, filters, assumptions ----------
source = st.session_state.get("source", {"source": "sample"})
st.logo(str(ROOT / "assets" / "logo.svg"), size="large", icon_image=str(ROOT / "assets" / "icon.svg"))


def reset_filters():
    for k in ("f_region", "f_estate", "f_age"):
        st.session_state[k] = []


with st.sidebar:
    if source.get("source") == "upload":
        st.markdown(f'<div class="synthetic">Using your data: <b>{source.get("name", "file")}</b>. Only you see it; other visitors see the sample.</div>', unsafe_allow_html=True)
    else:
        st.markdown('<div class="synthetic">Synthetic sample data, not real SOPB results.</div>', unsafe_allow_html=True)
    st.markdown("#### Filters")
    if "f_region" in st.session_state:
        st.session_state.f_region = [r for r in st.session_state.f_region if r in set(df.region_name)]
    regions = st.multiselect("Region", sorted(df.region_name.unique()), placeholder="All regions", key="f_region")
    est_pool = df[df.region_name.isin(regions)] if regions else df
    if "f_estate" in st.session_state:  # an estate outside the chosen regions is dropped, not an error
        st.session_state.f_estate = [e for e in st.session_state.f_estate if e in set(est_pool.estate_name)]
    estates = st.multiselect("Estate", sorted(est_pool.estate_name.unique()), placeholder="All estates", key="f_estate")
    bands = df.drop_duplicates("palm_age_band").sort_values("palm_age_band_order").palm_age_band.tolist()
    if "f_age" in st.session_state:
        st.session_state.f_age = [a for a in st.session_state.f_age if a in bands]
    ages = st.multiselect("Palm age band", bands, placeholder="All ages", key="f_age")
    scope_note = st.empty()
    st.button("Reset filters", on_click=reset_filters, use_container_width=True, disabled=not (regions or estates or ages))
    st.markdown("#### Assumptions")
    price = float(st.number_input("FFB price, RM per tonne", 300, 2000, int(FFB_PRICE_2025), 10, format="%d",
                                  help="Default: MPOB 2025 average FFB mill-gate price. Used to value yield gains."))

f = df.copy()
if regions:
    f = f[f.region_name.isin(regions)]
if estates:
    f = f[f.estate_name.isin(estates)]
if ages:
    f = f[f.palm_age_band.isin(ages)]
if f.empty:
    st.info("No blocks match these filters. Clear a filter in the sidebar.")
    st.stop()
blocks_in = set(f.block_id)
scope_note.caption(f"Showing {len(blocks_in):,} of {df.block_id.nunique():,} blocks")
nxt =M["forecast_next"][M["forecast_next"].block_id.isin(blocks_in)]
act = M["actions"][M["actions"].block_id.isin(blocks_in)]
lev = M["lever_gains"][M["lever_gains"].block_id.isin(blocks_in)]
total_gain_t = float((lev.all_levers * lev.productive_area_ha).sum())
blk_y = f.groupby("block_id").apply(wavg, include_groups=False)
est_y = f.groupby("estate_name").apply(wavg, include_groups=False)


# ---------- Pages ----------
def page_overview():
    spread_b = f"blocks range from <b>{blk_y.quantile(.1):.1f}</b> to <b>{blk_y.quantile(.9):.1f} t/ha/yr</b> (10th to 90th percentile)"
    if len(est_y) > 1 and (est_y.max() - est_y.min()) < (blk_y.quantile(.9) - blk_y.quantile(.1)) / 3:
        lede = f"Estates differ by only <b>{est_y.max() - est_y.min():.1f} t/ha/yr</b>, but {spread_b}. The gains are found block by block."
    elif len(est_y) > 1:
        lede = f"Estates differ by <b>{est_y.max() - est_y.min():.1f} t/ha/yr</b>, and {spread_b}."
    else:
        lede = f"In {est_y.index[0]}, {spread_b}."
    header("Observe", "Yield overview", f"{lede} Fixing the controllable issues the model finds is worth about "
           f"<b>{total_gain_t:,.0f} t FFB a year ({rm(total_gain_t * price)})</b>.")
    first = f.drop_duplicates("block_id")
    oil = float((f.yield_ann_t_ha_yr * f.oil_to_bunch_pct / 100 * f.productive_area_ha).sum() / f.productive_area_ha.sum())
    kpis([("FFB yield, t/ha/yr", f"{wavg(f):.1f}", "Annualised: cycle yield × 365 ÷ days between rounds, weighted by productive area"),
          ("Oil yield, t/ha/yr", f"{oil:.1f}", "FFB yield × oil-to-bunch ratio"),
          ("Productive area, ha", f"{first.productive_area_ha.sum():,.0f}", None),
          ("Days per harvest round", f"{f.harvest_interval_days.mean():.1f}", "Average days between rounds. Good practice is 7 to 10."),
          ("High-risk blocks", f"{(nxt.risk == 'High').sum():,}", "Next-cycle forecast 2+ t/ha/yr below the age-band median")])

    l, r = st.columns(2)
    age = f.groupby(["palm_age_band_order", "palm_age_band"]).apply(wavg, include_groups=False).reset_index(name="t/ha/yr")
    age["Palm age, years"] = age.palm_age_band.str.extract(r"\((.*)\)")[0].str.replace("y", "")
    with l, card("Palm age sets the baseline", "Annualised yield by palm age band. Peak highlighted."):
        fig = px.bar(age, x="Palm age, years", y="t/ha/yr", hover_data={"palm_age_band": True})
        fig.update_traces(marker_color=[BLUE if v == age["t/ha/yr"].max() else GREY for v in age["t/ha/yr"]],
                          text=[f"{v:.1f}" if v in (age["t/ha/yr"].max(), age["t/ha/yr"].iloc[0], age["t/ha/yr"].iloc[-1]) else "" for v in age["t/ha/yr"]],
                          textposition="outside", textfont_color=INK2)
        chart(fig, "ov_age", data=age[["palm_age_band", "t/ha/yr"]].round(2))
    e = est_y.sort_values().reset_index(name="t/ha/yr").rename(columns={"estate_name": "Estate"})
    with r, card("Estates sit close together", f"Annualised yield by estate. Dotted lines: real [MPOB 2025]({MPOB_URL}) estate averages, for context only."):
        fig = px.bar(e, x="t/ha/yr", y="Estate", orientation="h")
        fig.update_traces(marker_color=GREY, hovertemplate="%{y}: %{x:.1f} t/ha/yr<extra></extra>")
        for (name, v), pos in zip(BENCH.items(), ["top right", "top left"]):
            fig.add_vline(x=v, line_dash="dot", line_color=MUTED, line_width=1,
                          annotation_text=name.replace(" estates 2025", f" {v}"), annotation_font_color=MUTED, annotation_font_size=11, annotation_position=pos)
        fig.update_layout(margin=dict(t=24))
        fig.update_layout(yaxis_title=None)
        chart(fig, "ov_est", data=e.round(2))

    bm = f.groupby("block_id").agg(lat=("block_latitude", "first"), lon=("block_longitude", "first"), estate=("estate_name", "first"),
                                   band=("palm_age_band", "first"), vs_peers=("yield_vs_age_peers", "mean"), y=("yield_ann_t_ha_yr", "mean")).reset_index()
    lim = max(3, bm.vs_peers.abs().quantile(.95))
    with card("Where blocks under-perform", "Each dot is a block, coloured by yield against palms of the same age (t/ha/yr). Red is below, blue above. Zoom into an estate."):
        fig = px.scatter_map(bm, lat="lat", lon="lon", color="vs_peers", color_continuous_scale=DIVERGE, range_color=(-lim, lim),
                             hover_name="block_id", hover_data={"estate": True, "band": True, "y": ":.1f", "vs_peers": ":+.1f", "lat": False, "lon": False},
                             zoom=6.6 if bm.estate.nunique() > 1 else 10, center=dict(lat=float(bm.lat.mean()), lon=float(bm.lon.mean())),
                             map_style="carto-darkmatter", labels={"vs_peers": "vs peers", "y": "t/ha/yr"})
        fig.update_traces(marker=dict(size=8))
        fig.update_layout(coloraxis_colorbar=dict(title="", thickness=10, len=0.6))
        chart(fig, "ov_map", h=460, data=bm.rename(columns={"vs_peers": "vs age peers", "y": "t/ha/yr"}).round(2))


def page_quality():
    header("Observe", "Data quality", "Every check the preparation step ran on the raw file, what it found, and how it was handled.")
    kpis([("Checks run", f"{len(QC)}", None), ("Passed", f"{int((QC.status == 'Pass').sum())}", None),
          ("Analytical traps handled", f"{int((QC.status == 'Handled').sum())}", None), ("Rows × columns", f"{len(df):,} × {df.shape[1]}", "After feature engineering")])
    with card("Quality checks"):
        q = QC.assign(status=QC.status.map({"Pass": "✅ Pass", "Handled": "🛠️ Handled", "Warning": "⚠️ Warning", "Fail": "❌ Fail"}), note=QC.note.fillna(""))
        st.dataframe(q[["area", "check", "status", "records_failed", "note"]], hide_index=True, use_container_width=True,
                     column_config={"note": st.column_config.TextColumn(width="large")})
    l, r = st.columns(2)
    with l, card("What the data mining found"):
        r_int = df[["ffb_yield_t_ha", "harvest_interval_days"]].corr().iloc[0, 1]
        r_flag = df[["flag_long_interval", "flag_poor_access"]].astype(int).corr().iloc[0, 1]
        no_fert = (df.fertilizer_total_kg_ha == 0).mean()
        wt_blank = df.water_table_depth_cm.isna().mean()
        st.markdown(f"""
- **Grain:** {len(df):,} rows = {df.block_id.nunique():,} blocks in {df.estate_name.nunique()} estates × {df.harvest_cycle_no.nunique()} harvest cycles, one row per block per cycle.
- **Blank by design:** water table depth is blank in {wt_blank:.0%} of rows, all on non-peat soils where it is not measured. Blanks are kept, not filled.
- **Yield trap:** raw cycle yield rises with longer harvest rounds (correlation {r_int:.2f}), so yield is annualised before any comparison.
- **Age hides nutrient effects:** they only show once each block is compared with palms of the same age.
- **Fertilizer goes on in rounds:** {no_fert:.0%} of cycles show none, so feeding is judged over the current and previous cycle.
- **Issues overlap:** long rounds and poor access go together (correlation {r_flag:.2f}), so gains come from a what-if model, not by adding effects.""")
    with r, card("Engineered features"):
        st.markdown("""
| Feature | Why |
|---|---|
| Annualised yield | Cycle yield × 365 ÷ interval days |
| Yield vs age peers | Yield minus its palm-age-band median |
| Previous and next cycle yield | History and the forecast target |
| Wet cycle, poor drainage | Wettest third of cycles; poor drainage classes |
| 9 issue flags | Water stress, waterlogging, low K or Mg, Ganoderma, bagworm, long round, poor access, missing palms |""")


def page_drivers():
    header("Understand", "What drives yield",
           f"A gradient-boosting model explains <b>{dm['r2_held_out_blocks']:.0%}</b> of the variation in annualised yield on blocks it never saw "
           f"(average error {dm['mae_t_ha_yr']:.2f} t/ha/yr). {M['driver_importance'].label.iloc[0]} matters most, then {lc(M['driver_importance'].label.iloc[1])} and {lc(M['driver_importance'].label.iloc[2])}.")
    imp = M["driver_importance"].head(12).iloc[::-1].rename(columns={"label": "Driver", "importance_t_ha_yr": "Importance"})
    l, r = st.columns([5, 4])
    with l, card("Top 12 drivers", "How much the model's error grows, in t/ha/yr, when a factor is scrambled. Longer bar = more influence."):
        fig = px.bar(imp, x="Importance", y="Driver", orientation="h", hover_data={"group": True})
        fig.update_traces(marker_color=[BLUE if i == len(imp) - 1 else GREY for i in range(len(imp))])
        fig.update_layout(yaxis_title=None, xaxis_title="t/ha/yr")
        chart(fig, "dr_imp", h=420, data=imp.iloc[::-1][["Driver", "group", "Importance", "share_pct"]])
    pdp = M["partial_dependence"]
    with r, card("How yield responds", "Average predicted yield as one condition changes, others as they are. Shows shape and thresholds, not proven cause."):
        pick = st.selectbox("Condition", pdp.label.unique(), index=list(pdp.label.unique()).index("Harvest interval") if "Harvest interval" in pdp.label.values else 0)
        d = pdp[pdp.label == pick].rename(columns={"value": pick, "yield_t_ha_yr": "t/ha/yr"})
        fig = px.line(d, x=pick, y="t/ha/yr")
        fig.update_traces(line=dict(color=BLUE, width=2))
        chart(fig, "dr_pdp", h=330, data=d[[pick, "t/ha/yr"]].round(2))


def page_patterns():
    P = M["patterns"]
    header("Understand", "Pattern check",
           f"The dataset guide says 8 patterns were built into the data. Each was tested independently: <b>{int((P.verdict == 'Confirmed').sum())} of {len(P)} confirmed</b>.")
    r_ = "yield_vs_age_peers"

    def mini(n):
        if n == 1:
            d = df.groupby(["palm_age_band_order", "palm_age_band"]).yield_ann_t_ha_yr.mean().reset_index()
            d["age"] = d.palm_age_band.str.extract(r"\((.*)\)")[0].str.replace("y", "")
            fig = px.line(d, x="age", y="yield_ann_t_ha_yr", markers=True, labels={"age": "Palm age, years", "yield_ann_t_ha_yr": "t/ha/yr"})
            return fig.update_traces(line_color=BLUE, marker_size=8), d[["palm_age_band", "yield_ann_t_ha_yr"]]
        if n == 2:
            d = df.assign(drainage=np.where(df.poor_drainage, "Poor drainage", "Good drainage"), cycle=np.where(df.wet_cycle, "Wet cycle", "Normal cycle"))
            d = d.groupby(["drainage", "cycle"])[r_].mean().reset_index()
            return px.bar(d, x="drainage", y=r_, color="cycle", barmode="group", color_discrete_map={"Normal cycle": GREY, "Wet cycle": BLUE},
                          labels={r_: "vs age peers, t/ha/yr", "drainage": ""}), d
        if n == 3:
            d = df.groupby(pd.cut(df.water_deficit_prior_90d_mm, [-1, 0, 25, 50, 100], labels=["None", "Under 25", "25–50", "50+"]), observed=True)[r_].mean().reset_index()
            fig = px.bar(d, x="water_deficit_prior_90d_mm", y=r_, labels={"water_deficit_prior_90d_mm": "Prior 90-day deficit, mm", r_: "vs age peers"})
            return fig.update_traces(marker_color=BLUE), d
        if n == 4:
            k = df.groupby(pd.qcut(df.leaf_k_pct, 4, labels=["Lowest", "Q2", "Q3", "Highest"]), observed=True)[r_].mean().rename("Leaf K")
            m = df.groupby(pd.qcut(df.leaf_mg_pct, 4, labels=["Lowest", "Q2", "Q3", "Highest"]), observed=True)[r_].mean().rename("Leaf Mg")
            d = pd.concat([k, m], axis=1).reset_index(names="quarter").melt("quarter", var_name="nutrient", value_name=r_)
            return px.bar(d, x="quarter", y=r_, color="nutrient", barmode="group", color_discrete_map={"Leaf K": BLUE, "Leaf Mg": ORANGE},
                          labels={r_: "vs age peers", "quarter": "Leaf level quarter"}), d
        if n == 5:
            d = df.groupby(df.road_accessibility_score_1_5.round().astype(int)).estimated_field_loss_pct.mean().reset_index()
            fig = px.bar(d, x="road_accessibility_score_1_5", y="estimated_field_loss_pct", labels={"road_accessibility_score_1_5": "Road access score (1 poor, 5 good)", "estimated_field_loss_pct": "Field loss %"})
            return fig.update_traces(marker_color=BLUE), d
        if n == 6:
            d = df.assign(group=np.where(df.treatment_program.str.startswith("Bagworm"), "Bagworm-treated", "Other blocks"))
            d = d.groupby(["group", "harvest_cycle_no"]).bagworm_incidence_pct.mean().reset_index()
            fig = px.line(d, x="harvest_cycle_no", y="bagworm_incidence_pct", color="group", markers=True, color_discrete_map={"Bagworm-treated": BLUE, "Other blocks": GREY},
                          labels={"harvest_cycle_no": "Harvest cycle", "bagworm_incidence_pct": "Bagworm %"})
            return fig.update_traces(line_width=2, marker_size=8), d
        if n == 7:
            d = df.groupby("genetic_line")[r_].mean().sort_values().reset_index()
            fig = px.bar(d, x=r_, y="genetic_line", orientation="h", labels={r_: "vs age peers, t/ha/yr", "genetic_line": ""})
            return fig.update_traces(marker_color=[BLUE if v > 0 else GREY for v in d[r_]]), d
        d = M["cluster_profiles"][["name", "blocks", "yield_vs_age_peers", "traits"]]
        fig = px.bar(d, x="name", y="yield_vs_age_peers", hover_data=["traits", "blocks"], labels={"name": "", "yield_vs_age_peers": "vs age peers"})
        return fig.update_traces(marker_color=[BLUE if v > 0 else CRIT for v in d.yield_vs_age_peers]), d

    cols = st.columns(2)
    for i, row in P.iterrows():
        with cols[i % 2]:
            pill = '<span class="pill ok">✓ Confirmed</span>' if row.verdict == "Confirmed" else '<span class="pill no">Not found</span>'
            with st.container(border=True):
                st.markdown(f"### {row.no}. {row.pattern} &nbsp;{pill}", unsafe_allow_html=True)
                st.caption(f"{row.test}. **{row.evidence}**")
                fig, data = mini(int(row.no))
                chart(fig, f"pat{row.no}", h=230, data=data.round(3) if hasattr(data, "round") else data)


def treat_summary(te):
    """One sentence on treatment effect, written from the results."""
    bw = te[te.pest == "Bagworm"].set_index("treatment_program").change_pct_points
    gn = te[te.pest == "Ganoderma"].change_pct_points
    out = []
    targeted = bw[[p for p in bw.index if p.startswith("Bagworm")]]
    other = bw[[p for p in bw.index if not p.startswith("Bagworm")]]
    if len(targeted) and len(other):
        out.append(f"Targeted bagworm control cuts incidence by {-targeted.mean():.2f} points a cycle, vs {-other.mean():.2f} without it.")
    if len(gn):
        out.append("Ganoderma does not recede under any programme." if gn.max() >= -0.05 else "Some programmes reduce Ganoderma.")
    return " ".join(out)


def page_agronomy():
    fmx, ns, te = M["feeding_matrix"], M["nutrient_status"], M["treatment_effect"]
    under_k = fmx[(fmx.nutrient == "K") & fmx.situation.str.startswith("Under")].share_pct.iloc[0]
    header("Understand", "Agronomy: fertilizer, harvesting, treatments",
           f"<b>{(f.harvest_interval_days > 10).mean():.1%}</b> of harvest rounds run past the 10-day good-practice limit. "
           f"<b>{under_k:.0f}%</b> of block cycles are low in leaf potassium with none applied. {treat_summary(te)}")
    l, r = st.columns(2)
    with l, card("Leaf 17 nutrients vs critical levels",
                 "Critical levels for mature palms as commonly cited from Ochs and Olvin (1977) in Fairhurst and Mutert (1999). Calibrate locally. "
                 "Below-critical N does not cost yield here, which suggests N is not limiting."):
        st.dataframe(ns.rename(columns={"nutrient": "Nutrient", "critical_level_pct": "Critical %", "share_below_pct": "Below %",
                                        "yield_vs_peers_below": "Yield if below", "yield_vs_peers_adequate": "Yield if adequate"}),
                     hide_index=True, use_container_width=True,
                     column_config={"Yield if below": st.column_config.NumberColumn(format="%+.2f", help="t/ha/yr vs palms of the same age"),
                                    "Yield if adequate": st.column_config.NumberColumn(format="%+.2f", help="t/ha/yr vs palms of the same age")})
    with r, card("Did fertilizer go where it was needed?", "Applied = any K2O or MgO this or last cycle. Under-fed blocks are the first fertilizer target."):
        d = fmx.rename(columns={"yield_vs_age_peers": "vs age peers, t/ha/yr", "situation": "Situation"})
        fig = px.bar(d, x="vs age peers, t/ha/yr", y="Situation", color="nutrient", barmode="group", orientation="h",
                     color_discrete_map={"K": BLUE, "Mg": ORANGE}, hover_data={"share_pct": ":.1f", "block_cycles": True})
        fig.update_layout(yaxis_title=None)
        chart(fig, "ag_feed", h=300, data=d)

    hd = f.groupby("harvest_interval_days").agg(cycles=("block_id", "size"), field_loss_pct=("estimated_field_loss_pct", "mean"), ffa_pct=("ffa_pct", "mean")).reset_index()
    l, r = st.columns(2)
    with l, card("Almost every round runs past 10 days", "Block cycles by days between harvest rounds. Shaded: good practice of 7 to 10 days."):
        fig = px.bar(hd, x="harvest_interval_days", y="cycles", labels={"harvest_interval_days": "Days between rounds", "cycles": "Block cycles"})
        fig.update_traces(marker_color=[BLUE if d <= 10 else GREY for d in hd.harvest_interval_days])
        fig.add_vrect(x0=6.5, x1=10.5, fillcolor=GOOD, opacity=0.08, line_width=0)
        chart(fig, "ag_int", h=280, data=hd[["harvest_interval_days", "cycles"]])
    with r, card("Each extra day costs fruit", "Average field loss and free fatty acid (FFA) per cycle, by days between rounds."):
        long = hd.melt("harvest_interval_days", ["field_loss_pct", "ffa_pct"], var_name="measure", value_name="%")
        long["measure"] = long.measure.map({"field_loss_pct": "Field loss %", "ffa_pct": "FFA %"})
        fig = px.line(long, x="harvest_interval_days", y="%", facet_col="measure", markers=True, labels={"harvest_interval_days": "Days between rounds"})
        fig.update_traces(line=dict(color=BLUE, width=2), marker_size=7)
        fig.update_yaxes(matches=None, showticklabels=True)
        fig.for_each_annotation(lambda a: a.update(text=a.text.split("=")[-1], font_color=INK2))
        chart(fig, "ag_loss", h=280, data=hd.round(2))

    t = te[te.pest.isin(["Bagworm", "Rhinoceros beetle"])].rename(columns={"treatment_program": "Program", "change_pct_points": "Change, points"})
    with card("Do treatments work?", "Change in incidence over the next cycle where pressure was high. More negative is better. "
              "Blue bars are programmes that target that pest."):
        cols = st.columns(2)
        for col, (pest, prefix) in zip(cols, [("Bagworm", "Bagworm"), ("Rhinoceros beetle", "Rhinoceros")]):
            d = t[t.pest == pest].sort_values("Change, points", ascending=False)
            with col:
                st.markdown(f"**{pest}**")
                if d.empty:
                    st.caption("Not enough high-pressure cycles to measure.")
                    continue
                fig = px.bar(d, x="Change, points", y="Program", orientation="h", hover_data={"block_cycles": True})
                fig.update_traces(marker_color=[BLUE if p.startswith(prefix) else GREY for p in d.Program])
                fig.update_layout(yaxis_title=None)
                chart(fig, f"ag_treat_{prefix}", h=240, data=d[["Program", "block_cycles", "incidence_now_pct", "incidence_next_pct", "Change, points"]])


def page_groups():
    prof = M["cluster_profiles"]
    top = prof.iloc[0]
    header("Understand", "Groups of similar blocks",
           f"K-means grouped blocks by field conditions into {len(prof)} groups. <b>{top['name']}</b> ({int(top.blocks)} blocks: {top.traits}) "
           f"out-yields its age peers by <b>{top.yield_vs_age_peers:+.1f} t/ha/yr</b>. Its practices are worth copying.")
    l, r = st.columns([2, 3])
    with l, card("Yield vs age peers by group"):
        fig = px.bar(prof, x="name", y="yield_vs_age_peers", hover_data=["traits", "blocks"], labels={"name": "", "yield_vs_age_peers": "t/ha/yr"})
        fig.update_traces(marker_color=[BLUE if v > 0 else CRIT for v in prof.yield_vs_age_peers], text=prof.yield_vs_age_peers.map("{:+.2f}".format),
                          textposition="outside", textfont_color=INK2)
        chart(fig, "gr_bar", h=320, data=prof[["name", "blocks", "yield_vs_age_peers", "traits"]].round(2))
    feats = ["harvest_interval_days", "road_accessibility_score_1_5", "soil_moisture_pct", "flooding_days", "water_deficit_prior_90d_mm",
             "bagworm_incidence_pct", "ganoderma_incidence_pct", "leaf_k_pct", "leaf_mg_pct", "missing_palm_pct", "weed_cover_pct"]
    z = prof.set_index("name")[feats]
    z = ((z - z.mean()) / z.std()).rename(columns=LABELS)
    with r, card("Group profile", "Each condition compared across groups (standardised). Blue is higher than average, red lower."):
        fig = px.imshow(z.T.round(2), color_continuous_scale=DIVERGE, zmin=-1.5, zmax=1.5, aspect="auto", labels=dict(color=""))
        fig.update_layout(coloraxis_colorbar=dict(thickness=10, len=0.7))
        chart(fig, "gr_heat", h=360, data=prof.set_index("name")[feats].rename(columns=LABELS).round(2).reset_index())
    sil = J.get("cluster_metrics", {}).get("silhouette")
    if sil is not None:
        st.caption(f"Separation between groups is {'modest' if sil < 0.25 else 'clear'} (silhouette {sil:.2f}, with the number of groups chosen from 3 to 7), "
                   f"so treat them as {'tendencies, not hard types' if sil < 0.25 else 'distinct types'}.")


def page_forecast():
    header("Predict", "Next-cycle forecast and risk",
           f"Tested on whole blocks held out from training, the model's average error is <b>{fm['model']['mae']:.2f} t/ha/yr</b>, "
           f"<b>{fm['mae_improvement_vs_last_cycle_pct']:.0f}% lower</b> than assuming next cycle equals this one. "
           f"Its 80% range (±{fm['range_80_half_width']:.1f} t/ha/yr) held the actual result {fm['range_80_coverage_pct']:.0f}% of the time.")
    rc = nxt.risk.value_counts().reindex(["High", "Medium", "Low"]).fillna(0).astype(int)
    kpis([("🔴 High risk", f"{rc['High']}", "Forecast 2+ t/ha/yr below its age-band median"), ("🟠 Medium risk", f"{rc['Medium']}", "1 to 2 below"),
          ("🟢 Low risk", f"{rc['Low']}", None), ("Forecast error vs baseline", f"−{fm['mae_improvement_vs_last_cycle_pct']:.0f}%", "Lower average error than 'same as last cycle'")])
    l, r = st.columns(2)
    mc = M["model_comparison"]
    cmp_ = pd.concat([pd.DataFrame({"Method": ["Baseline: age-band median", "Baseline: same as last cycle"],
                                    "Average error, t/ha/yr": [fm["baseline_age_band_median"]["mae"], fm["baseline_same_as_last_cycle"]["mae"]],
                                    "R²": [fm["baseline_age_band_median"]["r2"], fm["baseline_same_as_last_cycle"]["r2"]], "chosen": False}),
                      mc.rename(columns={"model": "Method", "mae": "Average error, t/ha/yr", "r2": "R²"})[["Method", "Average error, t/ha/yr", "R²", "chosen"]]])
    cmp_ = cmp_.sort_values("Average error, t/ha/yr", ascending=False)
    with l, card("Five algorithms tested, best one used", f"Average error on unseen blocks, lower is better. {fm.get('chosen_model', 'The best model')} wins and makes the forecast."):
        fig = px.bar(cmp_, x="Average error, t/ha/yr", y="Method", orientation="h", text=cmp_["Average error, t/ha/yr"].map("{:.2f}".format), hover_data={"R²": ":.2f"})
        fig.update_traces(marker_color=[BLUE if c else GREY for c in cmp_.chosen], textposition="outside", textfont_color=INK2)
        fig.update_layout(yaxis_title=None)
        chart(fig, "fc_cmp", h=300, data=cmp_.drop(columns="chosen").iloc[::-1])
    cv = M["forecast_cv"][M["forecast_cv"].block_id.isin(blocks_in)]
    with r, card("Predicted vs actual", "Each dot is a block-cycle the model never saw. Dots on the line are perfect forecasts."):
        fig = px.scatter(cv, x="actual_next", y="predicted", opacity=0.45, labels={"actual_next": "Actual, t/ha/yr", "predicted": "Predicted, t/ha/yr"}, hover_data=["block_id"])
        lo_, hi_ = cv[["actual_next", "predicted"]].min().min(), cv[["actual_next", "predicted"]].max().max()
        fig.add_trace(go.Scatter(x=[lo_, hi_], y=[lo_, hi_], mode="lines", line=dict(color=MUTED, width=1), hoverinfo="skip", showlegend=False))
        fig.update_traces(marker=dict(color=BLUE, size=8, line=dict(color=SURFACE, width=2)), selector=dict(mode="markers"))
        chart(fig, "fc_sc", h=260)
    with card("Blocks by forecast risk"):
        risk_pick = st.radio("Show", ["High", "Medium", "Low"], horizontal=True, key="risk_pick", format_func=lambda r: RISK_ICON[r])
        show = nxt[nxt.risk == risk_pick].sort_values("forecast_vs_age_peers").assign(risk=lambda d: d.risk.map(RISK_ICON))
        st.dataframe(show[["block_id", "estate_name", "palm_age_band", "yield_ann_t_ha_yr", "forecast_t_ha_yr", "forecast_low", "forecast_high", "forecast_vs_age_peers", "risk"]],
                     hide_index=True, use_container_width=True,
                     column_config={"block_id": "Block", "estate_name": "Estate", "palm_age_band": "Age band",
                                    "yield_ann_t_ha_yr": st.column_config.NumberColumn("Current", format="%.1f"),
                                    "forecast_t_ha_yr": st.column_config.NumberColumn("Forecast", format="%.1f"),
                                    "forecast_low": st.column_config.NumberColumn("Low (80%)", format="%.1f"),
                                    "forecast_high": st.column_config.NumberColumn("High (80%)", format="%.1f"),
                                    "forecast_vs_age_peers": st.column_config.NumberColumn("vs age peers", format="%+.1f"), "risk": "Risk"})


def page_actions():
    header("Recommend", "Action plan: where to act first",
           f"The what-if model sets each controllable condition to a good level and predicts the yield change, so overlapping issues are not double counted. "
           f"Across the selected blocks that is <b>{total_gain_t:,.0f} t FFB a year</b>, worth <b>{rm(total_gain_t * price)}</b> at RM {price:,.0f}/t.")
    by_lever = pd.DataFrame({"Issue": [v[2] for v in LEVERS.values()], "First action": [v[3] for v in LEVERS.values()],
                             "t FFB/yr": [float((lev[k] * lev.productive_area_ha).sum()) for k in LEVERS]}).sort_values("t FFB/yr")
    by_lever = by_lever[by_lever["t FFB/yr"] >= 1]
    by_lever["RM/yr"] = by_lever["t FFB/yr"] * price
    with card("Yield at stake by lever", "Each lever fixed on its own across the selected blocks, before costs."):
        fig = px.bar(by_lever, x="t FFB/yr", y="Issue", orientation="h", text=by_lever["RM/yr"].map(rm), hover_data={"First action": True})
        fig.update_traces(marker_color=[BLUE if i == len(by_lever) - 1 else GREY for i in range(len(by_lever))], textposition="outside", textfont_color=INK2)
        fig.update_layout(yaxis_title=None)
        chart(fig, "ac_lev", h=330, data=by_lever.iloc[::-1].round(0))

    n = st.slider("Blocks in plan", 10, 100, 25, step=5)
    top = act.head(n).assign(value_rm=lambda d: d.est_gain_t_yr * price, risk=lambda d: d.risk.map(RISK_ICON))
    kpis([("Blocks in plan", f"{len(top)}", None), ("What-if gain, t FFB/yr", f"{top.est_gain_t_yr.sum():,.0f}", None),
          ("Value a year", rm(top.value_rm.sum()), f"At RM {price:,.0f} per tonne FFB"), ("High risk among them", f"{(top.risk == RISK_ICON['High']).sum()}", None)])
    with card("Priority blocks", "Ranked by what-if gain plus forecast shortfall."):
        st.dataframe(top[["rank", "block_id", "estate_name", "palm_age_band", "yield_ann_t_ha_yr", "forecast_t_ha_yr", "risk", "issues", "top_action", "est_gain_t_yr", "value_rm"]],
                     hide_index=True, use_container_width=True,
                     column_config={"rank": "#", "block_id": "Block", "estate_name": "Estate", "palm_age_band": "Age band",
                                    "yield_ann_t_ha_yr": st.column_config.NumberColumn("Now, t/ha/yr", format="%.1f"),
                                    "forecast_t_ha_yr": st.column_config.NumberColumn("Forecast", format="%.1f"), "risk": "Risk", "issues": "Issues",
                                    "top_action": st.column_config.TextColumn("First action", width="large"),
                                    "est_gain_t_yr": st.column_config.NumberColumn("Gain, t/yr", format="%.0f"),
                                    "value_rm": st.column_config.NumberColumn("Value, RM/yr", format="localized")})
        st.download_button("Download full action plan (CSV)", act.assign(value_rm=act.est_gain_t_yr * price).to_csv(index=False).encode(), "palm_action_plan.csv", "text/csv")
    st.caption("Indicative: a model-based what-if on synthetic data, before costs. To be validated with agronomists and trial blocks on real data.")


def page_simulator():
    header("Recommend", "What-if simulator", "Pick a block, change its conditions, and see how the model expects its yield to respond.")
    last = df[df.harvest_cycle_no == df.harvest_cycle_no.max()]
    l, r = st.columns([3, 2])
    with l, card("Conditions"):
        options = [b for b in act.block_id if b in set(last.block_id)]
        if not options:
            st.info("No blocks in the latest harvest cycle match the filters.")
            return
        if st.session_state.get("sim_block") not in options:
            st.session_state.sim_block = options[0]
        bid = st.selectbox("Block, ranked by priority", options, key="sim_block")
        row = last[last.block_id == bid]
        dmod = driver_model(str(BASE))
        base_x = design_matrix(row, CONDITIONS).reindex(columns=dmod["columns"], fill_value=0)
        sim_x = base_x.copy()
        st.caption("Each slider starts at this block's latest value. Hover the ⓘ beside a condition to see what it means.")
        items = list(LEVERS.items())
        for i, (key, (feat, rule, issue, _)) in enumerate(items):
            if i % 2 == 0:
                cols = st.columns(2)  # a new row per pair, so the two sliders line up
            unit, what = LEVER_HELP[feat]
            label = f"{LABELS.get(feat, issue)} ({unit})"
            with cols[i % 2]:
                if df[feat].dtype.kind == "i":
                    cur = int(row[feat].iloc[0])
                    val = st.slider(label, int(df[feat].min()), int(df[feat].max()), cur, 1, key=f"sim_{bid}_{feat}", help=what)
                else:
                    lo_, hi_ = float(df[feat].min()), float(df[feat].max())
                    cur = float(row[feat].iloc[0])
                    wide = hi_ - lo_ > 20
                    val = st.slider(label, lo_, hi_, cur, 0.1 if wide else 0.01, format="%.1f" if wide else "%.2f", key=f"sim_{bid}_{feat}", help=what)
                sim_x[feat] = val
    y0, y1 = float(dmod["model"].predict(base_x)[0]), float(dmod["model"].predict(sim_x)[0])
    ha = float(row.productive_area_ha.iloc[0])
    info = act[act.block_id == bid].iloc[0]
    with r, card(f"Result for {bid}", f"{info.estate_name} · {info.palm_age_band} · {ha:.0f} ha"):
        st.metric("Yield now, t/ha/yr", f"{y0:.1f}", border=True)
        st.metric("Scenario, t/ha/yr", f"{y1:.1f}", f"{y1 - y0:+.2f} t/ha/yr", border=True)
        st.metric("Value a year", rm((y1 - y0) * ha * price), f"{(y1 - y0) * ha:+,.0f} t FFB", delta_color="off", border=True)
        st.caption(f"Model's suggested first action: {info.top_action}.")


def page_poc():
    P = M["patterns"]
    n_pat = int((P.verdict == "Confirmed").sum())
    n_fail = int((QC.status == "Fail").sum())
    tie = abs(df.ffb_tonnes.sum() - (df.ffb_yield_t_ha * df.productive_area_ha).sum()) / df.ffb_tonnes.sum() * 100
    all_gain = float((M["lever_gains"].all_levers * M["lever_gains"].productive_area_ha).sum())
    crit = [
        ("Observe", "Data is fit for analysis", "No failed quality checks", f"{int((QC.status == 'Pass').sum())} checks passed, {n_fail} failed", n_fail == 0),
        ("Observe", "Yield ties back to source tonnes", "Within 0.5%", f"{tie:.2f}% difference", tie <= 0.5),
        ("Understand", "Drivers explain yield on unseen blocks", "R² of 0.70 or more", f"R² {dm['r2_held_out_blocks']:.2f}", dm["r2_held_out_blocks"] >= 0.70),
        ("Understand", "Patterns built into the data are found", f"All {len(P)}", f"{n_pat} of {len(P)} confirmed", n_pat == len(P)),
        ("Predict", "Best of 5 algorithms chosen on evidence", "Lowest error on unseen blocks",
         f"{fm.get('chosen_model', '?')}: {M['model_comparison'].iloc[0].mae:.2f} vs {M['model_comparison'].iloc[-1].mae:.2f} for the weakest ({M['model_comparison'].iloc[-1].model.lower()})",
         "model_comparison" in M and bool(M["model_comparison"].iloc[0].chosen)),
        ("Predict", "Forecast beats 'same as last cycle'", "Lower average error", f"{fm['model']['mae']:.2f} vs {fm['baseline_same_as_last_cycle']['mae']:.2f} t/ha/yr ({fm['mae_improvement_vs_last_cycle_pct']:.0f}% better)",
         fm["model"]["mae"] < fm["baseline_same_as_last_cycle"]["mae"]),
        ("Predict", "80% forecast range is honest", "Coverage 75 to 85%", f"{fm['range_80_coverage_pct']:.1f}%", 75 <= fm["range_80_coverage_pct"] <= 85),
        ("Recommend", "Every block gets a ranked, valued action", "All blocks", f"{len(M['actions']):,} of {df.block_id.nunique():,} blocks, {rm(all_gain * price)} a year", len(M["actions"]) == df.block_id.nunique()),
    ]
    met = sum(c[4] for c in crit)
    header("POC", "Proof of concept summary",
           "This POC tests whether plantation data, analysed together, can explain why yield differs, forecast it, and point to actions worth money. "
           f"<b>{met} of {len(crit)} success criteria are met</b> on the {'uploaded' if source.get('source') == 'upload' else 'synthetic sample'} data.")
    kpis([("Success criteria met", f"{met} of {len(crit)}", None), ("Hidden patterns found", f"{n_pat} of {len(P)}", None),
          ("Forecast vs baseline", f"{fm['mae_improvement_vs_last_cycle_pct']:.0f}% better", "Lower average error than 'same as last cycle', on unseen blocks"),
          ("Value identified a year", rm(all_gain * price), f"What-if gain across all blocks at RM {price:,.0f}/t FFB")])

    with card("What was built", "One repeatable pipeline from raw file to ranked actions. Upload a new file on the Run on your data page and every step re-runs."):
        st.graphviz_chart(f"""digraph {{
  rankdir=LR; bgcolor="transparent"; nodesep=0.35; ranksep=0.45;
  node [shape=box style="rounded,filled" fillcolor="{SURFACE}" color="{AXIS}" fontname="Segoe UI" fontsize=11 fontcolor="{INK}" margin="0.18,0.1"];
  edge [color="{MUTED}" arrowsize=0.6];
  raw [label="Raw file\\nblock × harvest cycle"];
  prep [label="Prepare\\n{len(QC)} quality checks\\ncleaning, 20 features"];
  ml [label="Machine learning\\n5 algorithms compared\\ndrivers · forecast\\nclustering · what-if" fillcolor="#14304f" color="{BLUE}"];
  out [label="Storyboard\\n8 analysis pages"];
  act [label="Action plan\\nranked blocks in RM"];
  raw -> prep -> ml -> out; ml -> act;
}}""", use_container_width=True)

    with card("Success criteria", "Set before the analysis and measured by the pipeline. They update when the data changes."):
        st.dataframe(pd.DataFrame([(s, c, t, r, "✅ Met" if ok else "❌ Not met") for s, c, t, r, ok in crit],
                                  columns=["Stage", "Criterion", "Target", "Result", "Status"]), hide_index=True, use_container_width=True,
                     column_config={"Result": st.column_config.TextColumn(width="large")})

    ls = M["lever_summary"].sort_values("total_gain_t_yr", ascending=False)
    prof = M["cluster_profiles"].iloc[0]
    est_all = df.groupby("estate_name").apply(wavg, include_groups=False)
    blk_all = df.groupby("block_id").apply(wavg, include_groups=False)
    l, r = st.columns(2)
    with l, card("Key findings"):
        st.markdown(f"""
1. **The gap is at block level.** Estates differ by about {est_all.max() - est_all.min():.1f} t/ha/yr; blocks by about {blk_all.quantile(.9) - blk_all.quantile(.1):.0f} (10th to 90th percentile).
2. **Harvest discipline matters.** {(df.harvest_interval_days > 10).mean():.1%} of rounds run past the 10-day good practice; field loss and FFA rise with every extra day.
3. **Top blocks share a profile:** {prof.traits} ({prof.yield_vs_age_peers:+.1f} t/ha/yr vs age peers).
4. **Biggest levers:** {lc(ls.iloc[0].issue)}, {lc(ls.iloc[1].issue)} and {lc(ls.iloc[2].issue)}.
5. **Treatments:** {treat_summary(M["treatment_effect"]) or "no treatment effect could be measured."}""")
    with r, card("Recommendation: proceed to a project on real data"):
        st.markdown("""
The method works end to end and every criterion can be measured again on real data. Suggested next phase:
- **Connect real data:** at least 2 years of block-level history from the customer's systems, to capture seasonality and longer rainfall lags.
- **Validate with agronomists:** confirm thresholds and leaf critical levels locally.
- **Add costs:** cost per lever, so actions rank by net return, not gross gain.
- **Trial blocks:** test the top actions on matched blocks to measure real uplift.""")
    st.caption("Limits of this POC: synthetic data with 5 harvest cycles; findings show association, not proven cause; gains are model estimates before costs.")


def page_data():
    header("POC", "Run on your data",
           "Upload a file in the same format as the sample: one row per block per harvest cycle. The app checks it, then re-runs data preparation "
           "and every model, and all pages update. This is how the POC moves from sample data to real data. "
           "<b>Your file and results are private to your browser session</b>; other visitors keep seeing the sample.")
    req = required_columns()
    using = "Uploaded file: " + source.get("name", "") if source.get("source") == "upload" else "Synthetic sample (SOPB_Palm_Yield_Optimization_POC_SAC.csv)"
    kpis([("Data in use", "Uploaded" if source.get("source") == "upload" else "Sample", using),
          ("Rows", f"{len(df):,}", None), ("Blocks", f"{df.block_id.nunique():,}", None), ("Harvest cycles", f"{df.harvest_cycle_no.nunique()}", None)])
    l, r = st.columns([2, 3])
    with l, card("1. Get the template", f"The file needs these {len(req)} columns, with the same names. Extra columns are ignored."):
        st.download_button("Download CSV template", (",".join(req) + "\n").encode(), "palm_yield_template.csv", "text/csv", use_container_width=True)
        with st.expander("See required columns"):
            st.dataframe(pd.DataFrame({"column": req}), hide_index=True, use_container_width=True, height=260)
        if source.get("source") == "upload" and st.button("Back to the sample data", use_container_width=True):
            st.session_state.pop("data_dir", None)
            st.session_state.pop("source", None)
            st.rerun()
    path, ready, why = None, False, "Upload a file in step 2, or use the sample file, to turn on this button."
    with r, card("2. Upload and check", "Drag a CSV file here or browse for one. The file is checked straight away; nothing changes until you press Run in step 3."):
        up = st.file_uploader("CSV file", type="csv", label_visibility="collapsed", key="upload_file")
        if st.button("Or use the sample file to try it", use_container_width=True, disabled=up is not None):
            st.session_state.use_sample = True
        if up is not None:
            st.session_state.use_sample = False
            upload_dir = SESSIONS / session_id() / "upload"
            upload_dir.mkdir(parents=True, exist_ok=True)
            path = upload_dir / Path(up.name).name
            path.write_bytes(up.getvalue())
        elif st.session_state.get("use_sample"):
            path = RAW_SAMPLE
            st.caption(f"Using the sample file: {RAW_SAMPLE.name}")
        if path is not None:
            ready, why = check_upload(path, req)
    with card("3. Run the pipeline", "Re-runs data preparation and every model on the checked file, then updates every page for you only. Takes one to two minutes."):
        if ready:
            st.success("The file passed every check. Press Run to use it.", icon="✅")
        elif path is not None:
            st.warning(why, icon="⚠️")
        else:
            st.info(why, icon="ℹ️")
        if st.button("Run the pipeline on this file", type="primary", use_container_width=True, disabled=not ready, key="run_pipeline"):
            run_pipeline(path)


def check_upload(path, req):
    """Show the checks for a file; return (ready, reason it is not ready)."""
    head = pd.read_csv(path, encoding="utf-8-sig", nrows=0).columns
    missing = [c for c in req if c not in head]
    if missing:
        st.error(f"{len(missing)} required columns are missing. Download the template in step 1 to see the expected names.")
        st.dataframe(pd.DataFrame({"missing column": missing}), hide_index=True, use_container_width=True, height=220)
        return False, "Add the missing columns, then upload the file again."
    try:
        new = load_raw(path)
        qc = quality_checks(new)
    except Exception as e:  # noqa: BLE001
        st.error(f"The file could not be read: {e}")
        return False, "Fix the file so it can be read, then upload it again."
    blocks, cycles = new.block_id.nunique(), new.harvest_cycle_no.nunique()
    fit = [("Required columns present", True, f"{len(req)} of {len(req)}"),
           ("At least 50 blocks (for validation folds)", blocks >= 50, f"{blocks:,} blocks"),
           ("At least 3 harvest cycles (for forecasting)", cycles >= 3, f"{cycles} cycles")]
    st.dataframe(pd.DataFrame([(n, "✅" if ok else "❌", v) for n, ok, v in fit], columns=["Check", "Status", "Found"]), hide_index=True, use_container_width=True)
    st.caption(f"Quality checks: {int((qc.status == 'Pass').sum())} passed, {int((qc.status == 'Handled').sum())} handled, "
               f"{int((qc.status == 'Warning').sum())} warnings, {int((qc.status == 'Fail').sum())} failed. Failed checks are reported, not blocking.")
    with st.expander("See quality checks"):
        st.dataframe(qc.assign(note=qc.note.fillna(""))[["area", "check", "status", "records_failed", "note"]], hide_index=True, use_container_width=True)
    if all(ok for _, ok, _ in fit):
        return True, ""
    return False, "Fix the items marked ❌ in step 2, then upload the file again."


def session_id():
    """A random id for this browser session; names its private folder."""
    import uuid
    if "sid" not in st.session_state:
        st.session_state.sid = uuid.uuid4().hex
    return st.session_state.sid


def run_pipeline(path):
    """Run preparation and models on a file into this session's private folder, then switch this session to it."""
    import subprocess
    run_dir = SESSIONS / session_id() / "results"
    env = {**os.environ, "PALM_DATA_DIR": str(run_dir)}
    with st.status("Running the pipeline. This takes one to two minutes.", expanded=True) as status:
        for step, script in [("Preparing data and running quality checks", "prepare.py"), ("Training models and building the action plan", "model.py")]:
            st.write(step)
            res = subprocess.run([sys.executable, str(ROOT / "pipeline" / script), *([str(path)] if script == "prepare.py" else [])],
                                 capture_output=True, text=True, cwd=ROOT, env=env, timeout=1200)
            if res.returncode != 0:
                status.update(label="The pipeline stopped with an error.", state="error")
                st.code(res.stderr[-2000:])
                return
        status.update(label="Done. Every page now uses this data, for you only.", state="complete")
    load.clear()
    driver_model.clear()
    st.session_state.data_dir = str(run_dir)
    st.session_state.source = {"source": "upload", "name": "sample file (your own run)" if path == RAW_SAMPLE else Path(path).name}
    st.rerun()


pages = {
    "POC": [st.Page(page_poc, title="POC summary", icon="🧪", url_path="poc", default=True),
            st.Page(page_data, title="Run on your data", icon="📤", url_path="run-on-your-data")],
    "Observe": [st.Page(page_overview, title="Overview", icon="📊", url_path="overview"),
                st.Page(page_quality, title="Data quality", icon="🧹", url_path="data-quality")],
    "Understand": [st.Page(page_drivers, title="Yield drivers", icon="🔍", url_path="drivers"),
                   st.Page(page_patterns, title="Pattern check", icon="✅", url_path="patterns"),
                   st.Page(page_agronomy, title="Agronomy", icon="🌱", url_path="agronomy"),
                   st.Page(page_groups, title="Block groups", icon="🧩", url_path="groups")],
    "Predict": [st.Page(page_forecast, title="Forecast and risk", icon="📈", url_path="forecast")],
    "Recommend": [st.Page(page_actions, title="Action plan", icon="🎯", url_path="actions"),
                  st.Page(page_simulator, title="What-if simulator", icon="🎛️", url_path="simulator")],
}

if os.environ.get("PALM_RENDER_ALL"):  # test hook: render every page in one run
    for fn in [page_poc, page_data, page_overview, page_quality, page_drivers, page_patterns, page_agronomy, page_groups, page_forecast, page_actions, page_simulator]:
        fn()
else:
    st.navigation(pages).run()
