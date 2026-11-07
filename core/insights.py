"""Automated insights: plain-language findings written from the results, for whatever blocks are selected.

Every sentence is computed, never invented, so the same functions feed the insight cards, the AI
assistant's context and its offline answers. Each insight is (kind, headline, detail), where kind is
one of "gap", "risk", "action", "good", "info".
"""
import re

import pandas as pd

from .store import View, block_record, wavg

WORD_START = r"\b"  # keywords must start a word, so "rm" does not match "ganoderma"
LONG_ROUND = 10  # days; good practice is 7 to 10


def rm(v):
    return f"RM {v / 1e6:,.2f}m" if abs(v) >= 1e6 else f"RM {v:,.0f}"


def lc(s):
    """Lower-case the first letter, except proper nouns."""
    return s if s.startswith("Ganoderma") else s[:1].lower() + s[1:]


def _short(estate):
    return estate.replace(" Estate", "")


def estate_table(v: View) -> pd.DataFrame:
    """One row per estate: yield, yield vs age peers, high-risk blocks, what-if gain."""
    f = v.f
    t = f.groupby("estate_name").apply(lambda d: pd.Series({
        "yield_t_ha_yr": wavg(d), "vs_age_peers": float(d.yield_vs_age_peers.mean()),
        "blocks": d.block_id.nunique()}), include_groups=False)
    t["high_risk_blocks"] = v.nxt[v.nxt.risk == "High"].groupby("estate_name").size().reindex(t.index).fillna(0).astype(int)
    gain = v.lev.merge(v.act[["block_id", "estate_name"]], on="block_id")
    t["gain_t_yr"] = (gain.all_levers * gain.productive_area_ha).groupby(gain.estate_name).sum().reindex(t.index).fillna(0)
    return t.sort_values("vs_age_peers").round(2)


def overview(v: View):
    f, out = v.f, []
    est = f.groupby("estate_name").apply(wavg, include_groups=False)
    blk = f.groupby("block_id").apply(wavg, include_groups=False)
    b_spread = blk.quantile(.9) - blk.quantile(.1)
    if len(est) > 1:
        e_spread = est.max() - est.min()
        out.append(("gap", "The gap is block by block" if e_spread < b_spread / 3 else "Estates and blocks both differ",
                    f"Estates differ by {e_spread:.1f} t/ha/yr, but blocks by {b_spread:.1f} (10th to 90th percentile). "
                    "Estate averages hide where the losses are."))
        et = estate_table(v)
        worst, best = et.index[0], et.index[-1]
        out.append(("risk", f"{_short(worst)} lags its age peers most",
                    f"{_short(worst)} averages {et.vs_age_peers.iloc[0]:+.1f} t/ha/yr against palms of the same age, "
                    f"while {_short(best)} leads at {et.vs_age_peers.iloc[-1]:+.1f}."))
    else:
        out.append(("gap", "Blocks differ widely", f"In {est.index[0]}, blocks differ by {b_spread:.1f} t/ha/yr (10th to 90th percentile)."))
    hi = v.nxt[v.nxt.risk == "High"]
    if len(hi):
        top_est = hi.estate_name.value_counts()
        out.append(("risk", f"{len(hi)} blocks are high risk next cycle",
                    f"They are forecast 2+ t/ha/yr below their age peers; {top_est.iloc[0]} of them are in {_short(top_est.index[0])}."))
    out.append(("action", f"About {v.total_gain_t:,.0f} t FFB a year is at stake",
                f"Fixing the controllable issues the model finds is worth about {rm(v.total_gain_t * v.price)} a year at RM {v.price:,.0f}/t, before costs."))
    return out


def forecast(v: View):
    fm, nxt, out = v.r.J["forecast_metrics"], v.nxt, []
    out.append(("good", f"Forecast is {fm['mae_improvement_vs_last_cycle_pct']:.0f}% more accurate than the baseline",
                f"Average error {fm['model']['mae']:.2f} t/ha/yr on blocks the model never saw, against "
                f"{fm['baseline_same_as_last_cycle']['mae']:.2f} for 'same as last cycle'."))
    hi = nxt[nxt.risk == "High"]
    if len(hi):
        worst = hi.sort_values("forecast_vs_age_peers").iloc[0]
        share = hi.estate_name.value_counts(normalize=True)
        out.append(("risk", f"{len(hi)} high-risk blocks, {share.iloc[0]:.0%} in {_short(share.index[0])}",
                    f"Worst: {worst.block_id}, forecast {worst.forecast_t_ha_yr:.1f} t/ha/yr, {worst.forecast_vs_age_peers:+.1f} against its age peers."))
    drop = (nxt.forecast_t_ha_yr - nxt.yield_ann_t_ha_yr)
    falling = int((drop < -2).sum())
    if falling:
        out.append(("info", f"{falling} blocks are forecast to fall by more than 2 t/ha/yr",
                    "Check them for recent flooding, drought or disease before the next round."))
    return out


def actions(v: View):
    act, lev, out = v.act, v.lev, []
    if act.empty:
        return out
    from model import LEVERS  # the pipeline's lever definitions
    by = pd.Series({LEVERS[k][2]: float((lev[k] * lev.productive_area_ha).sum()) for k in LEVERS}).sort_values(ascending=False)
    out.append(("action", f"Biggest lever: {lc(by.index[0])}",
                f"Worth about {by.iloc[0]:,.0f} t FFB a year ({rm(by.iloc[0] * v.price)}), then {lc(by.index[1])} "
                f"({by.iloc[1]:,.0f} t) and {lc(by.index[2])} ({by.iloc[2]:,.0f} t)."))
    first = act.top_action.value_counts()
    out.append(("info", f"Most common first action: {first.index[0].split(';')[0].lower()}",
                f"It is the first action for {first.iloc[0]} of {len(act)} blocks."))
    top = act.iloc[0]
    out.append(("risk", f"Start with {top.block_id}",
                f"{_short(top.estate_name)}, {top.palm_age_band}, {top.risk.lower()} risk. Issues: {top.issues.lower()}. "
                f"First action: {lc(top.top_action)} (about {top.est_gain_t_yr:,.0f} t a year)."))
    n = max(1, len(act) // 10)
    share = act.head(n).est_gain_t_yr.sum() / max(act.est_gain_t_yr.sum(), 1)
    out.append(("good", f"The top 10% of blocks hold {share:.0%} of the value",
                f"Acting on the first {n} blocks in the plan captures {share:.0%} of the gain, so the team can focus."))
    return out


def agronomy(v: View):
    f, M, out = v.f, v.r.M, []
    over = (f.harvest_interval_days > LONG_ROUND).mean()
    out.append(("risk", f"{over:.1%} of harvest rounds run past {LONG_ROUND} days",
                "Good practice is 7 to 10 days; field loss and free fatty acid rise with every extra day."))
    fm = M["feeding_matrix"]
    k = fm[(fm.nutrient == "K") & fm.situation.str.startswith("Under")]
    if len(k):
        out.append(("action", f"{k.share_pct.iloc[0]:.0f}% of block cycles are under-fed with potassium",
                    f"Low leaf K with none applied; they yield {k.yield_vs_age_peers.iloc[0]:+.2f} t/ha/yr against age peers. First fertilizer target."))
    ns = M["nutrient_status"].set_index("nutrient")
    n = ns.loc[[i for i in ns.index if i.startswith("Nitrogen")]]
    if len(n) and n.yield_vs_peers_below.iloc[0] >= 0:
        out.append(("info", "Nitrogen is not limiting yield",
                    "Blocks below the nitrogen critical level do not yield less, so extra nitrogen is not the priority."))
    te = M["treatment_effect"]
    gn = te[te.pest == "Ganoderma"].change_pct_points
    if len(gn) and gn.max() >= -0.05:
        out.append(("risk", "Ganoderma does not recede under any programme",
                    "It cannot be cured, so early census, sanitation and isolating infected palms matter most."))
    return out


def home(v: View):
    """The four most useful findings for the landing page."""
    o, a = overview(v), actions(v)
    return [o[0]] + [x for x in o if x[1].endswith("next cycle")][:1] + a[:1] + [o[-1]]


def block_story(r, block_id, price):
    """A short, computed explanation of one block."""
    rec = block_record(r, block_id)
    if rec is None:
        return None
    last, a, fc = rec["last"], rec["action"], rec["forecast"]
    lines = [f"{block_id} is in {last.estate_name}, {last.division_name}: {last.productive_area_ha:.0f} ha of {last.palm_age_band.lower()} palms "
             f"({last.genetic_line})."]
    lines.append(f"Latest annualised yield is {last.yield_ann_t_ha_yr:.1f} t/ha/yr, {last.yield_vs_age_peers:+.1f} against palms of the same age.")
    if fc is not None:
        lines.append(f"Next cycle is forecast at {fc.forecast_t_ha_yr:.1f} t/ha/yr (80% range {fc.forecast_low:.1f} to {fc.forecast_high:.1f}), "
                     f"which makes it {fc.risk.lower()} risk.")
    if a is not None:
        lines.append(f"Issues found: {a.issues.lower() if isinstance(a.issues, str) and a.issues else 'none of note'}. "
                     f"First action: {lc(a.top_action)}. Expected gain about {a.est_gain_t_yr:,.0f} t FFB a year "
                     f"({rm(a.est_gain_t_yr * price)}). Priority rank {int(a['rank'])} of {len(r.M['actions'])}.")
    return " ".join(lines)


# ---------- Context for the AI assistant ----------
def ai_context(v: View, question=""):
    """A compact, factual brief of the results for the AI assistant. Only these facts may be used."""
    r = v.r
    fm, dm = r.J["forecast_metrics"], r.J["driver_metrics"]
    parts = ["DATA: synthetic sample of oil palm plantation data (not real company results). "
             f"Scope: {v.f.block_id.nunique()} blocks in {v.f.estate_name.nunique()} estates, {v.f.harvest_cycle_no.nunique()} harvest cycles. "
             f"Yield is annualised t FFB/ha/yr, area-weighted. FFB price used: RM {v.price:,.0f}/t.",
             f"OVERALL: yield {wavg(v.f):.1f} t/ha/yr; what-if gain {v.total_gain_t:,.0f} t/yr = {rm(v.total_gain_t * v.price)}/yr before costs; "
             f"risk counts {v.nxt.risk.value_counts().to_dict()}.",
             f"MODELS: driver model R2 {dm['r2_held_out_blocks']:.2f} on unseen blocks; forecast ({fm.get('chosen_model', 'gradient boosting')}) "
             f"MAE {fm['model']['mae']:.2f} vs baseline {fm['baseline_same_as_last_cycle']['mae']:.2f} "
             f"({fm['mae_improvement_vs_last_cycle_pct']:.0f}% better); 80% range +/-{fm['range_80_half_width']:.1f}, coverage {fm['range_80_coverage_pct']:.1f}%.",
             "INSIGHTS:\n" + "\n".join(f"- {h}: {d}" for h, d in
                                       [(x[1], x[2]) for x in overview(v) + forecast(v) + actions(v) + agronomy(v)]),
             "ESTATES (yield, vs age peers, blocks, high-risk blocks, gain t/yr):\n" + estate_table(v).to_csv(),
             "LEVERS (issue, blocks that gain, total gain t/yr, action):\n" +
             r.M["lever_summary"][["issue", "blocks_with_gain", "total_gain_t_yr", "action"]].to_csv(index=False),
             "TOP 15 PRIORITY BLOCKS:\n" + v.act.head(15)[["rank", "block_id", "estate_name", "palm_age_band", "yield_ann_t_ha_yr",
                                                           "forecast_t_ha_yr", "risk", "issues", "top_action", "est_gain_t_yr"]].to_csv(index=False),
             "PATTERNS CHECKED:\n" + r.M["patterns"][["no", "pattern", "evidence", "verdict"]].to_csv(index=False),
             "LEAF NUTRIENTS vs critical levels:\n" + r.M["nutrient_status"].to_csv(index=False)]
    for bid in sorted(set(re.findall(r"EST\d{3}-D\d{2}-B\d{2}", question.upper())))[:3]:
        story = block_story(r, bid, v.price)
        parts.append(f"BLOCK {bid}: {story or 'not found in the data.'}")
    for est in v.f.estate_name.unique():
        if _short(est).lower() in question.lower():
            parts.append(f"ESTATE {est} top 5 blocks:\n" + v.act[v.act.estate_name == est].head(5)[
                ["rank", "block_id", "risk", "issues", "top_action", "est_gain_t_yr"]].to_csv(index=False))
    return "\n\n".join(parts)


# ---------- Offline answers (no AI key, or the AI service is unavailable) ----------
SUGGESTED = ["Which blocks should we fix first?", "Why is yield different between blocks?", "Which estate needs the most attention?",
             "What is the biggest opportunity in RM?", "Where should fertilizer go?", "How accurate is the forecast?"]


def offline_answer(v: View, question: str) -> str:
    """Answer common questions from computed insights only, using simple keyword matching."""
    q = question.lower()
    bids = re.findall(r"EST\d{3}-D\d{2}-B\d{2}", question.upper())
    if bids:
        return "\n\n".join(block_story(v.r, b, v.price) or f"I can't find block {b} in the data." for b in bids[:3])
    fmt = lambda items: "\n".join(f"- **{h}.** {d}" for _, h, d in items)  # noqa: E731
    for est in v.f.estate_name.unique():
        if _short(est).lower() in q:
            et = estate_table(v).loc[est]
            a = v.act[v.act.estate_name == est].head(3)
            return (f"**{est}:** {et.yield_t_ha_yr:.1f} t/ha/yr, {et.vs_age_peers:+.2f} against age peers, "
                    f"{int(et.high_risk_blocks)} high-risk blocks, about {et.gain_t_yr:,.0f} t a year at stake.\n\nTop blocks:\n" +
                    "\n".join(f"- {x.block_id}: {lc(x.top_action)} (~{x.est_gain_t_yr:,.0f} t/yr)" for x in a.itertuples()))
    rules = [(("first", "priority", "fix", "start", "top block", "which block"), lambda: fmt(actions(v)[2:]) + "\n\nTop 5:\n" +
              "\n".join(f"- {x.block_id} ({_short(x.estate_name)}): {lc(x.top_action)}" for x in v.act.head(5).itertuples())),
             (("estate", "attention", "worst", "lag"), lambda: fmt(overview(v)[1:2]) + "\n\nEstates furthest below their age peers:\n" + "\n".join(
                 f"- {_short(e)}: {x.vs_age_peers:+.2f} t/ha/yr, {int(x.high_risk_blocks)} high-risk blocks" for e, x in estate_table(v).head(5).iterrows())),
             (("rm", "money", "value", "worth", "opportunity", "ringgit"), lambda: fmt(overview(v)[-1:] + actions(v)[:1] + actions(v)[-1:])),
             (("fertil", "potassium", "nutrient", "nitrogen", "magnesium", "leaf"), lambda: fmt([x for x in agronomy(v) if "potassium" in x[1] or "Nitrogen" in x[1]])),
             (("harvest", "round", "interval"), lambda: fmt(agronomy(v)[:1])),
             (("ganoderma", "bagworm", "pest", "disease", "treatment"), lambda: fmt(agronomy(v)[-1:]) + f"\n\n{v.r.M['patterns'].iloc[5].evidence} for bagworm-treated blocks."),
             (("forecast", "risk", "predict", "accura", "model", "next cycle"), lambda: fmt(forecast(v))),
             (("why", "driver", "cause", "differ", "pattern"), lambda: "The main drivers, from the model and the pattern checks:\n" +
              "\n".join(f"- {x.label}" for x in v.r.M["driver_importance"].head(5).itertuples()) + "\n\n" + fmt(overview(v)[:1]))]
    for words, answer in rules:
        if any(re.search(WORD_START + re.escape(w), q) for w in words):
            return answer()
    return "Here is what stands out in the selected blocks:\n" + fmt(home(v)) + "\n\nTry asking about a block (e.g. EST005-D08-B01), an estate, risk, fertilizer or value."
