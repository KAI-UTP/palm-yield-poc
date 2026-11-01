# Palm Yield Optimization POC

A working proof of concept that takes plantation field data from basic reporting to block-level action:
**Observe → Understand → Predict → Recommend.** Built on the synthetic SOPB sample (3,200 rows: 640 blocks × 5 harvest cycles).
The data is synthetic, not real SOPB results.

## Run it

```bash
pip install -r requirements.txt
streamlit run app.py
```

The sample data is bundled in `data/raw/`, and the prepared data and models are included, so the app opens straight away.
If they are missing, the app rebuilds them on first start (two to three minutes). To rebuild by hand:

```bash
python pipeline/prepare.py      # quality checks, cleaning, feature engineering
python pipeline/model.py        # five-model comparison, drivers, forecast, clustering, what-if, action plan
```

To run the whole POC on another file in the same format, use the **Run on your data** page, or
`python pipeline/prepare.py path/to/file.csv` and then `python pipeline/model.py`.

## Share it online (free)

1. Put this folder in a GitHub repository (public, or private with access granted).
2. Go to [share.streamlit.io](https://share.streamlit.io), choose **Create app**, pick the repository and set the main file to `app.py`. Any Python from 3.11 to 3.14 works (3.14 is the default).
3. Share the app link in the submission.

## What is inside

| Step | File | What it does |
|---|---|---|
| 1. Prepare | `pipeline/prepare.py` | 22 quality checks (readability, grain, completeness, ranges, consistency, outliers, analytical traps); unreadable values become blanks and rows without key fields are left out; cleaning; 20 engineered features |
| 2. Model | `pipeline/model.py` | Five algorithms compared for the forecast (linear, random forest, extra trees, gradient boosting, histogram boosting), best one used; driver importance and response curves; calibrated 80% forecast range and risk level; K-means block groups; tests of the 8 embedded patterns; model-based what-if gains; ranked action plan |
| 3. App | `app.py` | Eleven pages. POC: POC summary, Run on your data. Observe: Overview, Data quality. Understand: Yield drivers, Pattern check, Agronomy, Block groups. Predict: Forecast and risk. Recommend: Action plan, What-if simulator |

## Key methods

- **Annualised yield** = cycle yield × 365 ÷ harvest interval days. Raw cycle yield rises with longer rounds, so it is never compared directly.
- **Yield vs age peers** = block yield minus the median of its palm age band. This removes the age effect, which otherwise hides nutrient effects.
- **Validation**: every model is tested with 5-fold cross-validation grouped by block, so each score is on blocks the model never saw.
- **Forecast range**: split-conformal 80% range from held-out errors; checked coverage is about 80%.
- **What-if gains**: the driver model re-predicts each block with one controllable condition (or all) set to a good level. Overlapping issues are not double counted. Gains are valued at the FFB price set in the sidebar.
- **Design**: dark theme from a colour-blind-checked palette; one accent colour per chart; no dual axes; every chart has a table view.

## External references

- MPOB, *Overview of the Malaysian Oil Palm Industry 2025*: estate FFB yield Malaysia 17.77 t/ha and Sarawak 15.98 t/ha; OER Malaysia 19.74% and Sarawak 19.51%; FFB mill-gate price RM 930/t. https://bepi.mpob.gov.my/images/overview/Overview2025.pdf
- Leaf 17 critical levels (N 2.50%, P 0.15%, K 1.00%, Mg 0.24%): Ochs and Olvin (1977), as cited in Fairhurst and Mutert (1999), *Better Crops International* 13(1). Calibrate locally.
- Harvest interval of 7 to 10 days as good practice: Malaysian harvesting-practice studies, e.g. https://hrmars.com/papers_submitted/23345/improving-palm-oil-productivity-through-harvesting-practices.pdf
