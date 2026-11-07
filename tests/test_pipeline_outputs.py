"""The pipeline's results meet the POC's success criteria."""


def test_grain_and_quality(results):
    df, qc = results.df, results.QC
    assert len(df) == df[["block_id", "harvest_cycle_no"]].drop_duplicates().shape[0]
    assert (qc.status == "Fail").sum() == 0


def test_models_meet_criteria(results):
    fm, dm = results.J["forecast_metrics"], results.J["driver_metrics"]
    assert dm["r2_held_out_blocks"] >= 0.70
    assert fm["model"]["mae"] < fm["baseline_same_as_last_cycle"]["mae"]
    assert 75 <= fm["range_80_coverage_pct"] <= 85
    assert bool(results.M["model_comparison"].iloc[0].chosen)


def test_patterns_and_actions(results):
    assert (results.M["patterns"].verdict == "Confirmed").all()
    act = results.M["actions"]
    assert act.block_id.nunique() == results.df.block_id.nunique()
    assert list(act["rank"]) == sorted(act["rank"])
    assert (act.est_gain_t_yr >= 0).all()
